import csv
import io
from datetime import date, datetime, timezone
from functools import wraps

from flask import jsonify, request, send_file, session

from .notifications import send_order_message


ROLES = {"administrador", "produccion", "ventas", "solo_lectura"}
ORDER_STATES = {"Pendiente", "Confirmado", "En producción", "Listo", "Entregado", "Cancelado"}


def _missing_table(error, table_name):
    return table_name in str(error) and "PGRST205" in str(error)


def register_erp_routes(app, get_supabase, require_admin, role_required):
    @app.get("/api/track/<uuid:tracking_token>")
    def track_order(tracking_token):
        try:
            result = get_supabase().table("citas").select("id,fecha,hora,estado,descripcion,created_at,updated_at").eq("tracking_token", str(tracking_token)).single().execute()
            if not result.data:
                return jsonify({"error": "Pedido no encontrado"}), 404
            return jsonify({"data": result.data})
        except Exception as error:
            app.logger.exception("Error consultando tracking", exc_info=error)
            return jsonify({"error": "No se pudo consultar el pedido"}), 503

    @app.get("/api/catalog/options")
    def catalog_options():
        client = get_supabase()
        variants = client.table("variantes_producto").select("*").eq("disponible", True).execute().data or []
        extras = client.table("adicionales").select("*").eq("disponible", True).execute().data or []
        return jsonify({"data": {"variantes": variants, "adicionales": extras}})

    @app.get("/api/auth/profile")
    @require_admin
    def profile():
        return jsonify({"data": {"id": session.get("user_id"), "rol": session.get("role", "administrador")}})

    @app.get("/api/admin/orders/<int:order_id>/history")
    @role_required("administrador", "ventas", "produccion", "solo_lectura")
    def order_history(order_id):
        result = get_supabase().table("pedido_historial").select("*").eq("pedido_id", order_id).order("created_at", desc=True).execute()
        return jsonify({"data": result.data or []})

    @app.patch("/api/admin/orders/<int:order_id>/lifecycle")
    @role_required("administrador", "ventas", "produccion")
    def update_lifecycle(order_id):
        payload = request.get_json(silent=True) or {}
        state = str(payload.get("estado", "")).strip()
        if state not in ORDER_STATES:
            return jsonify({"error": "Estado de pedido no válido"}), 400
        fields = {"estado": state}
        if "fecha" in payload:
            fields["fecha"] = str(payload["fecha"])
        if "hora" in payload:
            fields["hora"] = str(payload["hora"])
        if "notas_internas" in payload:
            fields["notas_internas"] = str(payload["notas_internas"])[:2000]
        result = get_supabase().table("citas").update(fields).eq("id", order_id).execute()
        if state in {"Confirmado", "En producción", "Listo", "Entregado"} and result.data:
            message_record = {"pedido_id": order_id, "canal": "whatsapp", "plantilla": "pedido_actualizacion", "estado": "fallido"}
            try:
                provider_id = send_order_message(result.data[0])
                message_record.update({"proveedor_id": provider_id, "estado": "enviado", "enviado_at": datetime.now(timezone.utc).isoformat()})
            except Exception as error:
                app.logger.warning("No se pudo enviar actualización de pedido: %s", error)
                message_record["error"] = str(error)[:500]
            try:
                get_supabase().table("pedido_mensajes").insert(message_record).execute()
            except Exception as error:
                if not _missing_table(error, "pedido_mensajes"):
                    raise
        return jsonify({"data": result.data[0] if result.data else None})

    @app.get("/api/admin/production/today")
    @role_required("administrador", "produccion", "solo_lectura")
    def production_today():
        result = get_supabase().table("citas").select("*").eq("fecha", date.today().isoformat()).in_("estado", ["Confirmado", "En producción", "Listo"]).order("hora").execute()
        return jsonify({"data": result.data or []})

    @app.post("/api/admin/inventory/movements")
    @role_required("administrador", "produccion")
    def inventory_movement():
        payload = request.get_json(silent=True) or {}
        try:
            insumo_id = int(payload["insumo_id"])
            quantity = float(payload["cantidad"])
            movement_type = str(payload["tipo"])
            reason = str(payload.get("motivo", ""))[:240]
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "insumo_id, cantidad y tipo son obligatorios"}), 400
        if quantity <= 0 or movement_type not in {"entrada", "salida", "ajuste"}:
            return jsonify({"error": "Movimiento de inventario no válido"}), 400
        client = get_supabase()
        current = client.table("insumos").select("stock_actual").eq("id", insumo_id).single().execute().data
        if not current:
            return jsonify({"error": "Insumo no encontrado"}), 404
        current_stock = float(current.get("stock_actual") or 0)
        new_stock = quantity if movement_type == "ajuste" else current_stock + quantity if movement_type == "entrada" else current_stock - quantity
        if new_stock < 0:
            return jsonify({"error": "El movimiento dejaría el stock en negativo"}), 400
        client.table("insumos").update({"stock_actual": new_stock}).eq("id", insumo_id).execute()
        result = client.table("movimientos_inventario").insert({"insumo_id": insumo_id, "tipo": movement_type, "cantidad": quantity, "motivo": reason}).execute()
        return jsonify({"data": result.data[0] if result.data else None, "stock_actual": new_stock}), 201

    @app.get("/api/admin/expenses")
    @role_required("administrador", "solo_lectura")
    def expenses():
        try:
            result = get_supabase().table("gastos").select("*").order("fecha", desc=True).execute()
        except Exception as error:
            if _missing_table(error, "gastos"):
                return jsonify({"data": []})
            raise
        return jsonify({"data": result.data or []})

    @app.post("/api/admin/expenses")
    @role_required("administrador")
    def create_expense():
        payload = request.get_json(silent=True) or {}
        try:
            fields = {"concepto": str(payload["concepto"]).strip()[:160], "categoria": str(payload.get("categoria", "operativo"))[:60], "monto": float(payload["monto"]), "fecha": str(payload.get("fecha", date.today().isoformat())), "notas": str(payload.get("notas", ""))[:1000]}
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "concepto y monto son obligatorios"}), 400
        if not fields["concepto"] or fields["monto"] < 0:
            return jsonify({"error": "Gasto no válido"}), 400
        result = get_supabase().table("gastos").insert(fields).execute()
        return jsonify({"data": result.data[0] if result.data else None}), 201

    @app.get("/api/admin/reports/summary")
    @role_required("administrador", "solo_lectura")
    def report_summary():
        client = get_supabase()
        orders = client.table("citas").select("precio,abono,fecha,estado,created_at").execute().data or []
        try:
            expenses_data = client.table("gastos").select("monto,fecha").execute().data or []
        except Exception as error:
            if _missing_table(error, "gastos"):
                expenses_data = []
            else:
                raise
        sales = sum(float(order.get("precio") or 0) for order in orders if order.get("estado") != "Cancelado")
        deposits = sum(float(order.get("abono") or 0) for order in orders if order.get("estado") != "Cancelado")
        expenses_total = sum(float(item.get("monto") or 0) for item in expenses_data)
        receivable = max(0, sales - deposits)
        return jsonify({"data": {"ventas": sales, "abonos": deposits, "por_cobrar": receivable, "gastos": expenses_total, "utilidad_neta": deposits - expenses_total, "pedidos": len(orders)}})

    @app.get("/api/admin/reports/orders.csv")
    @role_required("administrador", "ventas", "solo_lectura")
    def orders_csv():
        rows = get_supabase().table("citas").select("*").order("fecha", desc=True).execute().data or []
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=sorted(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        else:
            output.write("id\n")
        buffer = io.BytesIO(output.getvalue().encode("utf-8-sig"))
        return send_file(buffer, mimetype="text/csv", as_attachment=True, download_name="pedidos-isaura.csv")

    @app.get("/api/admin/orders/<int:order_id>/label")
    @role_required("administrador", "produccion", "solo_lectura")
    def order_label(order_id):
        order = get_supabase().table("citas").select("*").eq("id", order_id).single().execute().data
        if not order:
            return jsonify({"error": "Pedido no encontrado"}), 404
        description = str(order.get("descripcion", "")).replace("\n", "<br>")
        html = f"<!doctype html><html lang='es'><meta charset='utf-8'><title>Etiqueta {order_id}</title><style>body{{font:20px sans-serif;width:320px;padding:20px}}h1{{font-size:26px}}@media print{{button{{display:none}}}}</style><h1>Isaura Cerpa</h1><p><b>Cliente:</b> {order.get('nombre_cliente','')}</p><p><b>Entrega:</b> {order.get('fecha','')} {order.get('hora','')}</p><p><b>Pedido:</b><br>{description}</p><button onclick='print()'>Imprimir</button>"
        return html