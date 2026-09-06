import os

from werkzeug.security import generate_password_hash

os.environ.setdefault("ADMIN_SESSION_SECRET", "test-secret-with-at-least-32-bytes-123456")
os.environ.setdefault("ADMIN_USERNAME", "test@example.com")
os.environ.setdefault("ADMIN_PASSWORD_HASH", generate_password_hash("test-password"))
os.environ.setdefault("SUPABASE_AUTH_ENABLED", "false")
os.environ.setdefault("RATELIMIT_STORAGE_URI", "memory://")

from api.index import app


def test_health_and_authentication():
    client = app.test_client()
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/insumos").status_code == 401
    assert client.post("/api/login", json={"username": "test@example.com", "password": "test-password"}).status_code == 200
    assert client.get("/api/auth/csrf").status_code == 200


def test_order_item_price_is_server_owned():
    from api.index import _resolve_order_items

    class Result:
        data = [{"id": 1, "nombre": "Torta", "precio": 25000}]

    class Table:
        def select(self, *_): return self
        def in_(self, *_): return self
        def execute(self): return Result()

    class Client:
        def table(self, *_): return Table()

    items, total = _resolve_order_items(Client(), [{"id": 1, "cantidad": 2}])
    assert total == 50000
    assert items[0]["nombre"] == "Torta"
    assert items[0]["precio"] == 25000


def test_order_payload_accepts_supabase_time_with_seconds():
    from api.index import _order_payload

    payload = {
        "nombre_cliente": "Cliente",
        "contacto": "3000000000",
        "fecha": "2026-09-05",
        "hora": "10:00:00",
        "descripcion": "Torta de prueba",
        "tipo_pago": "Pendiente de Pago",
        "precio": 0,
        "abono": 0,
    }

    assert _order_payload(payload)["hora"] == "10:00:00"
