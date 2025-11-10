# main.py
import requests
from fastapi import FastAPI, Request, HTTPException
import os
from datetime import datetime
from typing import Dict, Any, List

# Funciones BD
from db_service import (
    consultar_disponibilidad,
    reservar_cita,
    buscar_citas_pendientes,
    cancelar_cita
)

app = FastAPI()

# =======================================
# CONFIG
# =======================================
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "AGZ_TOKEN_DE_PRUEBA_123")
MEDICO_PILOTO_ID = 1

# Sesiones
user_sessions: Dict[str, Any] = {}

# =======================================
# ✅ FUNCIÓN PARA ENVIAR PLANTILLA (V1)
# =======================================

def send_template_message(recipient_number: str, template_name: str, parameters: List[Dict[str, str]]):
    """
    Envía una plantilla aprobada usando API V1 sendTemplateMessage.
    Funciona perfecto para bots que responden mensajes entrantes.
    """

    WATI_BASE_URL = os.getenv("WATI_ENDPOINT_BASE")     # https://live-mt-server.wati.io
    WATI_ACCOUNT_ID = os.getenv("WATI_ACCOUNT_ID")      # 1043548
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN")  # Bearer xxx

    if not WATI_BASE_URL or not WATI_ACCOUNT_ID or not WATI_ACCESS_TOKEN:
        print("❌ ERROR: Variables WATI no configuradas.")
        return

    url = f"{WATI_BASE_URL}/{WATI_ACCOUNT_ID}/api/v1/sendTemplateMessage"

    headers = {
        "Authorization": WATI_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    # ✅ CORRECCIÓN: eliminar "+" ANTES de enviar
    clean_number = recipient_number.replace("+", "")

    payload = {
        "template_name": template_name,
        "parameters": parameters,
        "receivers": [
            {"whatsappNumber": clean_number}
        ]
    }

    r = requests.post(url, headers=headers, json=payload)

    print("=== DEBUG WATI SEND TEMPLATE ===")
    print("URL:", url)
    print("STATUS:", r.status_code)
    print("BODY:", r.text)
    print("PAYLOAD:", payload)
    print("=================================")

    try:
        r.raise_for_status()
        print("✅ WATI: Plantilla enviada correctamente.")
    except Exception as e:
        print("❌ ERROR enviando plantilla:", e)


# =======================================
# ✅ EXTRACCIÓN DEL MENSAJE ENTRANTE
# =======================================

def extract_message_info(data):
    if data.get("type") == "text":
        return {
            "sender": "+" + data.get("waId", ""),
            "text": data.get("text", "").strip()
        }
    return None


# =======================================
# ✅ VERIFICACIÓN DEL WEBHOOK
# =======================================

@app.get("/webhook")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ WEBHOOK VERIFICADO")
        return int(challenge)

    raise HTTPException(status_code=403, detail="Token incorrecto")


# =======================================
# ✅ LÓGICA DEL BOT
# =======================================

@app.post("/webhook")
async def handle_whatsapp_messages(request: Request):
    data = await request.json()

    print("==== RAW WEBHOOK ====")
    print(data)
    print("=====================")

    info = extract_message_info(data)

    if not info:
        return {"status": "ignored"}

    sender = info["sender"]
    text = info["text"].lower()
    state = user_sessions.get(sender, {"state": "INICIO"})["state"]

    # Nombre temporal (en el futuro se obtiene desde BD o WATI)
    nombre = "Erick"

    # ---------------------------------------
    # ✅ ESTADO INICIO
    # ---------------------------------------
    if state == "INICIO":

        # Parámetros de la plantilla (según tu planilla aprobada)
        params = [
            {"name": "1", "value": nombre}
        ]

        # 1. Usuario quiere agendar
        if "agendar" in text or "hora" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_FECHA"}

            send_template_message(
                recipient_number=sender,
                template_name="agenza_inicio",
                parameters=params
            )

            return {"status": "inicio_agendar"}

        # 2. Usuario quiere cancelar
        if "cancelar" in text or "anular" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_CANCELAR_RUT"}

            send_template_message(
                recipient_number=sender,
                template_name="agenza_inicio",
                parameters=params
            )

            return {"status": "inicio_cancelar"}

        # 3. Usuario solo saluda
        send_template_message(
            recipient_number=sender,
            template_name="agenza_inicio",
            parameters=params
        )

        return {"status": "inicio"}

    # ---------------------------------------
    # ✅ OTRO ESTADO: PREGUNTANDO_FECHA
    # ---------------------------------------
    if state == "PREGUNTANDO_FECHA":
        send_template_message(
            recipient_number=sender,
            template_name="agenza_inicio",
            parameters=[{"name": "1", "value": nombre}]
        )
        return {"status": "fecha_recibida"}

    return {"status": "ok"}
