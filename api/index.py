import hashlib
import hmac
import os
import secrets
from datetime import date, datetime, timezone
from functools import wraps
from pathlib import Path

import httpx
from flask import Flask, jsonify, request, session
from dotenv import load_dotenv
from postgrest.exceptions import APIError
from supabase import Client, create_client
from werkzeug.exceptions import HTTPException


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
ALLOWED_STATUSES = {"Pendiente", "En Preparación", "Entregado"}
ALLOWED_PAYMENTS = {"Pagado Completo", "Mitad / Abono", "Pendiente de Pago"}

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.secret_key = os.environ.get("ADMIN_SESSION_SECRET")


def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL y SUPABASE_KEY/SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def with_image_url(product):
    image = product.get("imagen")
    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if image and str(image).startswith(("http://", "https://")):
        product["image_url"] = image
    elif image and base_url:
        product["image_url"] = f"{base_url}/storage/v1/object/public/productos/{image}"
    return product


def error_response(message: str, status: int = 400):
    return jsonify({"error": message}), status


def database_error(error):
    app.logger.exception("Error de Supabase", exc_info=error)
    return jsonify({
        "error": "Supabase no pudo completar la operación.",
        "details": str(error),
    }), 503


def require_admin(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if session.get("admin_authenticated") is True:
            return handler(*args, **kwargs)
        authorization = request.headers.get("Authorization", "")
        token = authorization.removeprefix("Bearer ").strip()
        secret = os.environ.get("ADMIN_SESSION_SECRET")
        if not secret or not _valid_admin_token(token, secret):
            return error_response("Autenticación requerida", 401)
        return handler(*args, **kwargs)

    return wrapped


def _admin_token(secret: str) -> str:
    issued_at = str(int(datetime.now(timezone.utc).timestamp()))
    signature = hmac.new(secret.encode(), f"isaura-admin:{issued_at}".encode(), hashlib.sha256).hexdigest()
    return f"{issued_at}.{signature}"


def _valid_admin_token(token: str, secret: str) -> bool:
    try:
        issued_at, signature = token.split(".", 1)
        age = datetime.now(timezone.utc).timestamp() - int(issued_at)
        max_age = int(os.environ.get("ADMIN_SESSION_TTL", "28800"))
        expected = hmac.new(secret.encode(), f"isaura-admin:{issued_at}".encode(), hashlib.sha256).hexdigest()
        return 0 <= age <= max_age and hmac.compare_digest(signature, expected)
    except (TypeError, ValueError):
        return False


def _text(payload, key, maximum=160, required=True):
    value = str(payload.get(key, "")).strip()
    if required and not value:
        raise ValueError(f"El campo {key} es obligatorio")
    if len(value) > maximum:
        raise ValueError(f"El campo {key} supera el límite permitido")
    return value


def _order_payload(payload, partial=False):
    fields = {}
    for key in ("nombre_cliente", "contacto", "fecha", "hora", "descripcion", "tipo_pago"):
        if partial and key not in payload:
            continue
        fields[key] = _text(payload, key, 1000 if key == "descripcion" else 160)
    if "tipo_pago" in fields and fields["tipo_pago"] not in ALLOWED_PAYMENTS:
        raise ValueError("Tipo de pago no válido")
    for key in ("precio", "abono"):
        if partial and key not in payload:
            continue
        try:
            value = float(payload.get(key, 0))
        except (TypeError, ValueError):
            raise ValueError(f"{key} debe ser numérico")
        if value < 0:
            raise ValueError(f"{key} no puede ser negativo")
        fields[key] = value
    if "fecha" in fields:
        date.fromisoformat(fields["fecha"])
    if "hora" in fields:
        datetime.strptime(fields["hora"], "%H:%M")
    if fields.get("abono", 0) > fields.get("precio", float("inf")):
        raise ValueError("El abono no puede superar el precio")
    return fields


def _product_payload(payload):
    return {
        "nombre": _text(payload, "nombre", 120),
        "categoria": _text(payload, "categoria", 80),
        "descripcion": _text(payload, "descripcion", 1000, required=False),
    }


@app.errorhandler(Exception)
def handle_unexpected(error):
    app.logger.exception("Error no controlado", exc_info=error)
    return error_response("Error interno del servidor. Consulta los logs de la función para más detalles.", 500)


@app.errorhandler(HTTPException)
def handle_http_error(error):
    return error_response(error.description, error.code)


@app.errorhandler(APIError)
def handle_supabase_error(error):
    return database_error(error)


@app.errorhandler(RuntimeError)
def handle_configuration_error(error):
    return database_error(error)


@app.errorhandler(httpx.HTTPError)
def handle_supabase_network_error(error):
    return database_error(error)


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "isaura-api"})


@app.get("/api/")
def api_root():
    return jsonify({"mensaje": "API de Pastelería Isaura funcionando"}), 200


@app.get("/api/products")
@app.get("/api/productos")
def products():
    try:
        result = get_supabase().table("productos").select("id,nombre,categoria,descripcion,imagen,created_at").order("id", desc=True).execute()
        return jsonify({"data": [with_image_url(product) for product in (result.data or [])]})
    except (APIError, RuntimeError) as error:
        return database_error(error)


@app.get("/api/categories")
def categories():
    try:
        result = get_supabase().table("productos").select("categoria").execute()
        values = sorted({row["categoria"] for row in (result.data or []) if row.get("categoria")})
        return jsonify({"data": values})
    except (APIError, RuntimeError) as error:
        return database_error(error)


@app.get("/api/citas")
def citas():
    try:
        result = get_supabase().table("citas").select("id,nombre_cliente,contacto,fecha,hora,descripcion,estado,precio,tipo_pago,abono,origen,created_at").order("fecha").order("hora").execute()
        return jsonify({"data": result.data or []})
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


@app.post("/api/orders")
@app.post("/api/citas")
def create_order():
    try:
        payload = request.get_json(silent=True) or {}
        fields = _order_payload(payload)
        fields.update({"estado": "Pendiente", "origen": "web"})
        result = get_supabase().table("citas").insert(fields).execute()
        return jsonify({"data": result.data[0] if result.data else None}), 201
    except ValueError as error:
        return error_response(str(error))
    except (APIError, RuntimeError) as error:
        return database_error(error)


@app.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    expected_user = os.environ.get("ADMIN_USERNAME", "isaura")
    expected_password = os.environ.get("ADMIN_PASSWORD", "1052243510familiacerpa")
    if not secrets.compare_digest(username, expected_user) or not secrets.compare_digest(password, expected_password):
        return error_response("Usuario o contraseña incorrectos", 401)
    session_secret = os.environ.get("ADMIN_SESSION_SECRET")
    if not session_secret:
        return error_response("Falta ADMIN_SESSION_SECRET en la configuración", 503)
    app.secret_key = session_secret
    session["admin_authenticated"] = True
    return jsonify({"success": True, "token": _admin_token(session_secret)})


@app.get("/api/admin/dashboard")
@require_admin
def dashboard():
    client = get_supabase()
    orders = client.table("citas").select("*").order("fecha").order("hora").execute().data or []
    products_data = [with_image_url(product) for product in (client.table("productos").select("*").order("id", desc=True).execute().data or [])]
    year = date.today().year
    delivered_by_month = [sum(1 for order in orders if order.get("estado") == "Entregado" and str(order.get("fecha", "")).startswith(f"{year}-{month:02d}")) for month in range(1, 13)]
    today = date.today().isoformat()
    return jsonify({
        "orders": orders,
        "products": products_data,
        "metrics": {
            "pending_today": sum(1 for order in orders if order.get("estado") == "Pendiente" and order.get("fecha") == today),
            "delivered_month": sum(1 for order in orders if order.get("estado") == "Entregado" and str(order.get("fecha", "")).startswith(f"{year}-{date.today().month:02d}")),
            "monthly_delivered": delivered_by_month,
        },
    })


@app.post("/api/admin/orders")
@require_admin
def admin_create_order():
    try:
        fields = _order_payload(request.get_json(silent=True) or {})
        fields["estado"] = "Pendiente"
        result = get_supabase().table("citas").insert(fields).execute()
        return jsonify({"data": result.data[0]}), 201
    except ValueError as error:
        return error_response(str(error))


@app.patch("/api/admin/orders/<int:order_id>")
@require_admin
def admin_update_order(order_id):
    try:
        payload = request.get_json(silent=True) or {}
        fields = _order_payload(payload, partial=True)
        if "estado" in payload:
            if payload["estado"] not in ALLOWED_STATUSES:
                raise ValueError("Estado no válido")
            fields["estado"] = payload["estado"]
        if not fields:
            raise ValueError("No hay cambios para guardar")
        result = get_supabase().table("citas").update(fields).eq("id", order_id).execute()
        return jsonify({"data": result.data[0] if result.data else None})
    except ValueError as error:
        return error_response(str(error))


@app.delete("/api/admin/orders/<int:order_id>")
@require_admin
def admin_delete_order(order_id):
    get_supabase().table("citas").delete().eq("id", order_id).execute()
    return ("", 204)


@app.post("/api/admin/products")
@require_admin
def admin_create_product():
    try:
        payload = _product_payload(request.form or request.get_json(silent=True) or {})
        image = request.files.get("imagen")
        if not image or image.mimetype not in {"image/jpeg", "image/png", "image/webp"}:
            return error_response("La imagen debe ser JPG, PNG o WebP")
        extension = image.filename.rsplit(".", 1)[-1].lower()
        filename = f"{secrets.token_hex(12)}.{extension}"
        client = get_supabase()
        client.storage.from_("productos").upload(filename, image.read(), {"content-type": image.mimetype, "upsert": "false"})
        payload["imagen"] = filename
        result = client.table("productos").insert(payload).execute()
        return jsonify({"data": result.data[0]}), 201
    except ValueError as error:
        return error_response(str(error))


@app.patch("/api/admin/products/<int:product_id>")
@require_admin
def admin_update_product(product_id):
    try:
        fields = _product_payload(request.get_json(silent=True) or {})
        result = get_supabase().table("productos").update(fields).eq("id", product_id).execute()
        return jsonify({"data": result.data[0] if result.data else None})
    except ValueError as error:
        return error_response(str(error))


@app.delete("/api/admin/products/<int:product_id>")
@require_admin
def admin_delete_product(product_id):
    client = get_supabase()
    product = client.table("productos").select("imagen").eq("id", product_id).single().execute().data
    if product and product.get("imagen"):
        client.storage.from_("productos").remove([product["imagen"]])
    client.table("productos").delete().eq("id", product_id).execute()
    return ("", 204)









