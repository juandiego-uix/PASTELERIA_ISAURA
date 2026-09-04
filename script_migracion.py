"""Migra las imagenes locales al bucket y catalogo de Supabase.

Uso desde la raiz del proyecto:
    python script_migracion.py

El script es idempotente: si el registro ya existe por su nombre o la imagen ya
esta en Storage, no crea duplicados innecesarios.
"""

import mimetypes
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client


BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIRS = (BASE_DIR / "uploads", BASE_DIR / "public" / "uploads")
BUCKET = "productos"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def get_client() -> Client:
    load_dotenv(BASE_DIR / ".env")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL y SUPABASE_KEY en .env")
    return create_client(url, key)


def image_directory() -> Path:
    for directory in IMAGE_DIRS:
        if directory.is_dir():
            return directory
    raise FileNotFoundError("No existe uploads/ ni public/uploads/")


def public_url(url: str, filename: str) -> str:
    return f"{url.rstrip('/')}/storage/v1/object/public/{BUCKET}/{filename}"


def product_name(filename: str) -> str:
    return Path(filename).stem.replace("_", " ").replace("-", " ").strip().title()


def migrate_image(client: Client, url: str, image_path: Path, existing_names: set[str]) -> str:
    filename = image_path.name
    name = product_name(filename)
    if name in existing_names:
        return f"omitido, producto existente: {name}"

    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    with image_path.open("rb") as image_file:
        client.storage.from_(BUCKET).upload(
            filename,
            image_file.read(),
            {"content-type": content_type, "upsert": "true"},
        )

    image_url = public_url(url, filename)
    client.table("productos").insert(
        {
            "nombre": name,
            "categoria": "Por editar",
            "descripcion": "Producto migrado; edita este texto desde el panel de administración.",
            "imagen": image_url,
        }
    ).execute()
    existing_names.add(name)
    return f"migrado: {name}"


def main() -> int:
    try:
        load_dotenv(BASE_DIR / ".env")
        url = os.environ.get("SUPABASE_URL")
        client = get_client()
        directory = image_directory()
        products = client.table("productos").select("nombre").execute().data or []
        existing_names = {row["nombre"] for row in products if row.get("nombre")}
        images = sorted(
            path for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        if not images:
            print(f"No hay imagenes compatibles en {directory}")
            return 0
        print(f"Migrando {len(images)} imagenes desde {directory}")
        for image_path in images:
            try:
                print(migrate_image(client, url, image_path, existing_names))
            except Exception as error:
                print(f"ERROR {image_path.name}: {error}", file=sys.stderr)
        print("Migracion finalizada. Revisa los productos desde el panel de administracion.")
        return 0
    except Exception as error:
        print(f"No se pudo iniciar la migracion: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
