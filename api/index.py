import hashlib
import hmac
import io
import json
import os
import secrets
from datetime import date, datetime, timezone
from functools import wraps
from pathlib import Path

import httpx
import sentry_sdk
from flask import Flask, jsonify, request, send_file, session
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from postgrest.exceptions import APIError
from supabase import Client, create_client
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    send_default_pii=False,
    traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
    environment=os.environ.get("VERCEL_ENV", os.environ.get("APP_ENV", "production")),
)
ALLOWED_STATUSES = {"Pendiente", "Confirmado", "En producción", "Listo", "Entregado", "Cancelado"}
ALLOWED_PAYMENTS = {"Pagado Completo", "Mitad / Abono", "Pendiente de Pago"}

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.secret_key = os.environ.get("ADMIN_SESSION_SECRET")
if not app.secret_key:
    raise RuntimeError("ADMIN_SESSION_SECRET es obligatorio")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get("VERCEL", "").lower() == "1",
    SESSION_COOKIE_SAMESITE="Lax",
)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)


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
        session_authenticated = session.get("admin") is True or session.get("admin_authenticated") is True
        authenticated = session_authenticated
        if not authenticated:
            authorization = request.headers.get("Authorization", "")
            token = authorization.removeprefix("Bearer ").strip()
            secret = os.environ.get("ADMIN_SESSION_SECRET")
            authenticated = bool(secret and _valid_admin_token(token, secret))
        if not authenticated:
            return error_response("Autenticación requerida", 401)
        if session_authenticated and request.method not in {"GET", "HEAD", "OPTIONS"}:
            csrf_header = request.headers.get("X-CSRF-Token", "")
            csrf_session = session.get("csrf_token", "")
            if not csrf_session or not hmac.compare_digest(csrf_header, csrf_session):
                return error_response("Token CSRF inválido", 403)
        return handler(*args, **kwargs)

    return wrapped


def role_required(*allowed_roles):
    def decorator(handler):
        @wraps(handler)
        @require_admin
        def wrapped(*args, **kwargs):
            role = session.get("role", "administrador")
            if role not in allowed_roles:
                return error_response("No tienes permisos para esta operación", 403)
            return handler(*args, **kwargs)
        return wrapped
    return decorator


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
    if "items" in payload:
        if not isinstance(payload["items"], list) or len(payload["items"]) > 50:
            raise ValueError("items debe ser una lista de máximo 50 productos")
        fields["items"] = [{
            "id": int(item["id"]),
            "cantidad": max(1, min(int(item.get("cantidad", 1)), 99)),
        } for item in payload["items"]]
    if "personalizacion" in payload:
        if not isinstance(payload["personalizacion"], dict) or len(str(payload["personalizacion"])) > 4000:
            raise ValueError("La personalización no es válida")
        fields["personalizacion"] = payload["personalizacion"]
    if "fecha" in fields:
        date.fromisoformat(fields["fecha"])
    if "hora" in fields:
        datetime.strptime(fields["hora"], "%H:%M")
    if fields.get("abono", 0) > fields.get("precio", float("inf")):
        raise ValueError("El abono no puede superar el precio")
    return fields


def _resolve_order_items(client, items):
    if not items:
        raise ValueError("El pedido debe incluir al menos un producto")
    product_ids = [item["id"] for item in items]
    if len(set(product_ids)) != len(product_ids):
        raise ValueError("No se permiten productos repetidos en el pedido")
    result = client.table("productos").select("id,nombre,precio").in_("id", product_ids).execute()
    products = {int(product["id"]): product for product in (result.data or [])}
    if len(products) != len(product_ids):
        raise ValueError("Uno o más productos ya no están disponibles")
    normalized = []
    total = 0
    for item in items:
        product = products[item["id"]]
        price = float(product.get("precio") or 0)
        quantity = item["cantidad"]
        normalized.append({"id": item["id"], "nombre": product["nombre"], "cantidad": quantity, "precio": price})
        total += price * quantity
    return normalized, total


def _product_payload(payload):
    fields = {
        "nombre": _text(payload, "nombre", 120),
        "categoria": _text(payload, "categoria", 80),
        "descripcion": _text(payload, "descripcion", 1000, required=False),
    }
    if "precio" in payload:
        fields["precio"] = max(0, float(payload.get("precio", 0)))
    for key in ("destacado", "disponible"):
        if key in payload:
            fields[key] = bool(payload[key])
    if "descuento_porcentaje" in payload:
        discount = float(payload["descuento_porcentaje"])
        if not 0 <= discount <= 100:
            raise ValueError("El descuento debe estar entre 0 y 100")
        fields["descuento_porcentaje"] = discount
    return fields


def _inventory_payload(payload):
    ingrediente = _text(payload, "ingrediente", 120)
    unidad = _text(payload, "unidad", 30)
    try:
        stock_actual = float(payload.get("stock_actual", 0))
        stock_minimo = float(payload.get("stock_minimo", 0))
    except (TypeError, ValueError):
        raise ValueError("El stock debe ser numérico")
    if stock_actual < 0 or stock_minimo < 0:
        raise ValueError("El stock no puede ser negativo")
    fields = {
        "ingrediente": ingrediente,
        "stock_actual": stock_actual,
        "unidad": unidad,
        "stock_minimo": stock_minimo,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload.get("id"):
        fields["id"] = int(payload["id"])
    return fields


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
        result = get_supabase().table("productos").select("id,nombre,categoria,descripcion,imagen,precio,destacado,disponible,descuento_porcentaje,created_at").eq("disponible", True).order("id", desc=True).execute()
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
@app.get("/api/pedidos")
def citas():
    try:
        result = get_supabase().table("citas").select("id,nombre_cliente,contacto,fecha,hora,descripcion,estado,precio,tipo_pago,abono,origen,items,created_at").order("fecha").order("hora").execute()
        return jsonify({"data": result.data or []})
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


@app.post("/api/orders")
@app.post("/api/citas")
@app.post("/api/pedidos")
@limiter.limit("10 per hour")
def create_order():
    try:
        payload = request.get_json(silent=True) or {}
        fields = _order_payload(payload)
        fields["items"], fields["precio"] = _resolve_order_items(get_supabase(), fields.get("items", []))
        if fields.get("abono", 0) > fields["precio"]:
            raise ValueError("El abono no puede superar el precio calculado")
        fields.update({"estado": "Pendiente", "origen": "web"})
        result = get_supabase().table("citas").insert(fields).execute()
        return jsonify({"data": result.data[0] if result.data else None}), 201
    except ValueError as error:
        return error_response(str(error))
    except (APIError, RuntimeError) as error:
        return database_error(error)


@app.post("/api/login")
@app.post("/api/auth/login")
@limiter.limit("10 per minute")
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    if os.environ.get("SUPABASE_AUTH_ENABLED", "false").lower() == "true":
        try:
            auth_key = os.environ.get("SUPABASE_ANON_KEY")
            if not auth_key:
                return error_response("SUPABASE_ANON_KEY es obligatorio para Supabase Auth", 503)
            auth_client = create_client(os.environ["SUPABASE_URL"], auth_key)
            auth_result = auth_client.auth.sign_in_with_password({"email": username, "password": password})
            user_id = str(auth_result.user.id)
            profile = get_supabase().table("perfiles").select("rol,nombre").eq("id", user_id).single().execute().data or {}
            session.clear()
            session["admin"] = True
            session["admin_authenticated"] = True
            session["user_id"] = user_id
            session["role"] = profile.get("rol", "solo_lectura")
            session["csrf_token"] = secrets.token_urlsafe(32)
            return jsonify({"success": True, "role": session["role"]}), 200
        except Exception:
            return error_response("Credenciales de Supabase no válidas", 401)
    expected_user = os.environ.get("ADMIN_USERNAME")
    expected_hash = os.environ.get("ADMIN_PASSWORD_HASH")
    if not expected_user or not expected_hash:
        return error_response("Autenticación no configurada en el servidor", 503)
    if not secrets.compare_digest(username, expected_user) or not check_password_hash(expected_hash, password):
        return error_response("Usuario o contraseña incorrectos", 401)
    session.clear()
    session["admin"] = True
    session["admin_authenticated"] = True
    session["role"] = "administrador"
    session["csrf_token"] = secrets.token_urlsafe(32)
    return jsonify({"success": True}), 200


@app.post("/api/logout")
@app.get("/api/logout")
def logout():
    session.clear()
    return jsonify({"success": True}), 200


@app.get("/api/auth/session")
def auth_session():
    authenticated = session.get("admin") is True or session.get("admin_authenticated") is True
    return jsonify({"success": authenticated}), 200


@app.get("/api/auth/csrf")
@require_admin
def csrf():
    token = session.get("csrf_token") or secrets.token_urlsafe(32)
    session["csrf_token"] = token
    return jsonify({"token": token})


@app.get("/api/admin/dashboard")
@require_admin
def dashboard():
    try:
        client = get_supabase()
        orders = client.table("citas").select("*").order("fecha").order("hora").execute().data or []
        products_data = [with_image_url(product) for product in (client.table("productos").select("*").order("id", desc=True).execute().data or [])]
        inventory = client.table("insumos").select("*").order("stock_actual").execute().data or []
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
                "monthly_cashflow": [sum(float(order.get("abono") or 0) for order in orders if str(order.get("created_at", "")).startswith(f"{year}-{month:02d}")) for month in range(1, 13)],
                "payment_distribution": {payment: sum(1 for order in orders if order.get("tipo_pago") == payment) for payment in ALLOWED_PAYMENTS},
            },
            "inventory": inventory,
        })
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


@app.post("/api/admin/orders")
@require_admin
def admin_create_order():
    try:
        fields = _order_payload(request.get_json(silent=True) or {})
        if fields.get("items"):
            fields["items"], fields["precio"] = _resolve_order_items(get_supabase(), fields["items"])
            if fields.get("abono", 0) > fields["precio"]:
                raise ValueError("El abono no puede superar el precio calculado")
        fields["estado"] = "Pendiente"
        result = get_supabase().table("citas").insert(fields).execute()
        return jsonify({"data": result.data[0]}), 201
    except ValueError as error:
        return error_response(str(error))
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


@app.put("/api/pedidos/<int:order_id>")
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
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


@app.delete("/api/admin/orders/<int:order_id>")
@require_admin
def admin_delete_order(order_id):
    try:
        get_supabase().table("citas").delete().eq("id", order_id).execute()
        return ("", 204)
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


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
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


@app.put("/api/productos/<int:product_id>")
@app.patch("/api/admin/products/<int:product_id>")
@require_admin
def admin_update_product(product_id):
    try:
        fields = _product_payload(request.get_json(silent=True) or {})
        result = get_supabase().table("productos").update(fields).eq("id", product_id).execute()
        return jsonify({"data": result.data[0] if result.data else None})
    except ValueError as error:
        return error_response(str(error))
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


@app.delete("/api/admin/products/<int:product_id>")
@require_admin
def admin_delete_product(product_id):
    try:
        client = get_supabase()
        product = client.table("productos").select("imagen").eq("id", product_id).single().execute().data
        if product and product.get("imagen") and not str(product["imagen"]).startswith(("http://", "https://")):
            client.storage.from_("productos").remove([product["imagen"]])
        client.table("productos").delete().eq("id", product_id).execute()
        return ("", 204)
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


@app.get("/api/admin/inventory")
@require_admin
def admin_inventory():
    try:
        result = get_supabase().table("insumos").select("*").order("stock_actual").execute()
        return jsonify({"data": result.data or []})
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


@app.get("/api/insumos")
@require_admin
def get_inventory():
    try:
        result = get_supabase().table("insumos").select("*").order("ingrediente").execute()
        return jsonify({"data": result.data or []})
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


@app.post("/api/insumos")
@require_admin
def save_inventory():
    try:
        payload = _inventory_payload(request.get_json(silent=True) or {})
        client = get_supabase()
        if payload.get("id"):
            result = client.table("insumos").update(payload).eq("id", payload["id"]).execute()
        else:
            result = client.table("insumos").upsert(payload, on_conflict="ingrediente").execute()
        return jsonify({"data": result.data[0] if result.data else None}), 201
    except (KeyError, TypeError, ValueError) as error:
        return error_response(str(error))
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


@app.post("/api/admin/messages/proximity")
@require_admin
def send_proximity_messages():
    provider = os.environ.get("MESSAGING_PROVIDER", "generic")
    webhook = os.environ.get("MESSAGING_WEBHOOK_URL")
    if not webhook:
        return error_response("Configura MESSAGING_WEBHOOK_URL para activar la mensajería", 503)
    try:
        orders = get_supabase().table("citas").select("*").neq("estado", "Entregado").execute().data or []
        upcoming = [order for order in orders if 0 <= (date.fromisoformat(str(order["fecha"])) - date.today()).days <= 2]
        body = json.dumps({"provider": provider, "orders": upcoming}, separators=(",", ":"), ensure_ascii=False).encode()
        webhook_secret = os.environ.get("MESSAGING_WEBHOOK_SECRET")
        if not webhook_secret:
            return error_response("Configura MESSAGING_WEBHOOK_SECRET para firmar la mensajería", 503)
        signature = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        response = httpx.post(webhook, content=body, headers={"Content-Type": "application/json", "X-Webhook-Signature": f"sha256={signature}"}, timeout=10)
        response.raise_for_status()
        return jsonify({"sent": len(upcoming), "provider": provider})
    except (APIError, RuntimeError, httpx.HTTPError, ValueError) as error:
        return database_error(error)


@app.get("/api/admin/orders/<int:order_id>/receipt.pdf")
@require_admin
def order_receipt(order_id):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        order = get_supabase().table("citas").select("*").eq("id", order_id).single().execute().data
        if not order:
            return error_response("Pedido no encontrado", 404)
        buffer = io.BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
        styles = getSampleStyleSheet()
        items = order.get("items") or [{"nombre": order.get("descripcion", "Pedido artesanal"), "cantidad": 1, "precio": order.get("precio", 0)}]
        rows = [["Producto", "Cantidad", "Importe"]] + [[str(item.get("nombre")), str(item.get("cantidad", 1)), f"${float(item.get('precio', 0)) * int(item.get('cantidad', 1)):,.0f}"] for item in items]
        story = [Paragraph("ISAURA CERPA", styles["Title"]), Paragraph("Repostería artesanal · Comprobante de pedido", styles["Normal"]), Spacer(1, 12)]
        story.append(Paragraph(f"Cliente: {order['nombre_cliente']}<br/>Contacto: {order['contacto']}<br/>Entrega: {order['fecha']} · {order['hora']}<br/>Estado: {order['estado']} · Pago: {order['tipo_pago']}", styles["BodyText"]))
        story += [Spacer(1, 14), Table(rows, colWidths=[110 * mm, 25 * mm, 35 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#27352f")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9ddd5")), ("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)])), Spacer(1, 12), Paragraph(f"Abono: ${float(order.get('abono', 0)):,.0f}<br/><b>Total: ${float(order.get('precio', 0)):,.0f}</b>", styles["BodyText"])]
        document.build(story)
        buffer.seek(0)
        return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=f"recibo-isaura-{order_id}.pdf")
    except (APIError, RuntimeError, httpx.HTTPError) as error:
        return database_error(error)


from .erp import register_erp_routes

register_erp_routes(app, get_supabase, require_admin, role_required)









