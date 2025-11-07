# main.py
import requests
from fastapi import FastAPI, Request, HTTPException
import json
import os
from typing import Dict, Any

from db_service import consultar_disponibilidad, reservar_cita, buscar_citas_pendientes, cancelar_cita

app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "AGZ_TOKEN_DE_PRUEBA_123")
MEDICO_PILOTO_ID = 1
user_sessions: Dict[str, Any] = {}


# ✅ Sanitizador para WATI
def sanitize_text(text: str) -> str:
    if not text:
        return ""
    return text.replace("'", "\\'").replace('"', '\\"')


# ✅ Envío REAL a WATI con messageText (correcto para tu tenant)
def send_whatsapp_message(recipient_number, message_text):

    WATI_BASE_ENDPOINT = os.getenv("WATI_ENDPOINT_BASE")
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN")
    WATI_ACCOUNT_ID = os.getenv("WATI_ACCOUNT_ID")

    if not WATI_BASE_ENDPOINT or not WATI_ACCESS_TOKEN or not WATI_ACCOUNT_ID:
        print("ERROR: Credenciales WATI no configuradas.")
        return

    wa_id = recipient_number.replace("+", "")
    url = f"{WATI_BASE_ENDPOINT}/{WATI_ACCOUNT_ID}/api/v1/sendSessionMessage/{wa_id}"

    headers = {
        "Authorization": WATI_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "messageText": sanitize_text(message_text)
    }

    response = requests.post(url, headers=headers, json=payload, timeout=10)

    print("\n--- DEBUG WATI (V1) ---")
    print("URL:", url)
    print("TO:", wa_id)
    print("MESSAGE (raw):", message_text)
    print("MESSAGE (sanitized):", payload["messageText"])
    print("STATUS:", response.status_code)
    print("BODY:", response.text)
    print("------------------------\n")

    response.raise_for_status()


# ✅ Extractor WATI
def extract_message_info(data):
    if data.get("type") == "text" and "text" in data:
        return {
            "sender": "+" + data.get("waId", ""),
            "text": data.get("text", "").strip()
        }
    return None


# ✅ Verificación webhook
@app.get("/webhook")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)

    raise HTTPException(status_code=403, detail="Token inválido")


# ✅ Endpoint principal
@app.post("/webhook")
async def handle_whatsapp_messages(request: Request):
    data = await request.json()

    print("\n==== RAW WEBHOOK ====")
    print(data)
    print("=====================\n")

    message_info = extract_message_info(data)
    if not message_info:
        return {"status": "ignored"}

    sender = message_info["sender"]
    text = message_info["text"].lower()

    state = user_sessions.get(sender, {"state": "INICIO"})["state"]

    response_text = ""

    if state == "INICIO":
        if "agendar" in text:
            response_text = "Perfecto 👍 ¿Qué fecha deseas? (Ej: 2025-11-06)"
            user_sessions[sender] = {"state": "PREGUNTANDO_FECHA"}
        elif "cancelar" in text:
            response_text = "Para cancelar tu cita, indícame tu RUT/RUN/DNI."
            user_sessions[sender] = {"state": "PREGUNTANDO_CANCELAR_RUT"}
        else:
            response_text = "Bienvenido a Agenza. Escribe agendar o cancelar para comenzar."

    if response_text:
        send_whatsapp_message(sender, response_text)

    return {"status": "ok"}
