import os
from urllib.parse import quote

import httpx


def order_message(order):
    return (
        f"Hola {order.get('nombre_cliente', 'cliente')}, tu pedido Isaura Cerpa está "
        f"{order.get('estado', 'Pendiente')}. Entrega: {order.get('fecha', '')} a las {order.get('hora', '')}."
    )


def send_order_message(order):
    provider = os.environ.get("MESSAGING_PROVIDER", "webhook").lower()
    message = order_message(order)
    phone = str(order.get("contacto", "")).replace("+", "").replace(" ", "")
    if provider == "twilio":
        account_sid = os.environ["TWILIO_ACCOUNT_SID"]
        auth_token = os.environ["TWILIO_AUTH_TOKEN"]
        sender = os.environ["TWILIO_WHATSAPP_FROM"]
        response = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
            data={"From": sender, "To": f"whatsapp:+{phone}", "Body": message},
            auth=(account_sid, auth_token),
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("sid", "")
    if provider == "meta":
        token = os.environ["META_ACCESS_TOKEN"]
        phone_id = os.environ["META_PHONE_NUMBER_ID"]
        template = os.environ.get("META_TEMPLATE_NAME", "pedido_actualizacion")
        response = httpx.post(
            f"https://graph.facebook.com/v22.0/{quote(phone_id, safe='')}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"messaging_product": "whatsapp", "to": phone, "type": "template", "template": {"name": template, "language": {"code": "es_CO"}, "components": [{"type": "body", "parameters": [{"type": "text", "text": order.get("estado", "Pendiente")}, {"type": "text", "text": str(order.get("fecha", ""))}]}]}},
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("messages", [{}])[0].get("id", "")
    return ""
