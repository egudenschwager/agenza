# main.py
import requests
from fastapi import FastAPI, Request, HTTPException
import json
import os
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Any, List

# --- Importar funciones de base de datos ---
from db_service import (
    consultar_disponibilidad,
    reservar_cita,
    buscar_citas_pendientes,
    cancelar_cita
)

# ================================
# CONFIG GLOBAL
# ================================
app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "AGZ_TOKEN_DE_PRUEBA_123")
MEDICO_PILOTO_ID = 1

# Sesiones por usuario
user_sessions: Dict[str, Any] = {}


# ======================================================
# ✅ FUNCIÓN PARA ENVIAR PLANTILLAS DE WATI (V1 /broadcast)
# ======================================================
def send_template_message(recipient_number: str, template_name: str, parameters: List[Dict[str, str]]):

    # Variables EXACTAS configuradas en Railway
    WATI_BASE_ENDPOINT = os.getenv("WATI_ENDPOINT_BASE")  # https://live-mt-server.wati.io
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN")
    WATI_ACCOUNT_ID = os.getenv("WATI_ACCOUNT_ID")

    if not WATI_BASE_ENDPOINT or not WATI_ACCESS_TOKEN or not WATI_ACCOUNT_ID:
        print("❌ ERROR: Variables WATI no configuradas.")
        return

    # Endpoint requerido por WATI
    url = f"{WATI_BASE_ENDPOINT}/{WATI_ACCOUNT_ID}/api/v1/broadcast/scheduleBroadcast"

    headers = {
        "Authorization": WATI_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    # ✅ Programar el envío 10 segundos en el futuro
    schedule_time = (datetime.now(timezone.utc) + timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "TemplateName": template_name,
        "BroadcastName": f"AGENZA_BOT_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "Parameters": parameters,
        "Receivers": [
            {"WhatsAppNumber": recipient_number.replace("+", "")}
        ],
        "ScheduleTime": schedule_time
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)

        print("=== DEBUG TEMPLATE SEND ===")
        print("URL:", url)
        print("STATUS:", r.status_code)
        print("BODY:", r.text)
        print("PAYLOAD:", payload)
        print("===========================")

        r.raise_for_status()
        print("✅ Plantilla enviada correctamente.")

    except Exception as e:
        print(f"❌ ERROR enviando plantilla: {e}")


# ======================================================
# ✅ EXTRAER MENSAJE DESDE WATI
# ======================================================
def extract_message_info(data):
    """Extrae la información del mensaje entrante del JSON de WATI."""
    if "type" in data and data.get("type") == "text":
        return {
            "sender": "+" + data.get("waId", ""),
            "text": data.get("text", "").strip(),
            "sender_name": data.get("senderName", "Paciente")
        }
    return None


# ======================================================
# ✅ ENDPOINT GET – VERIFICACIÓN DE WEBHOOK
# ======================================================
@app.get("/webhook")
def verify_webhook(request: Request):
    try:
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("✅ WEBHOOK VERIFICADO")
            return int(challenge)

        raise HTTPException(status_code=403, detail="Token incorrecto")

    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


# ======================================================
# ✅ ENDPOINT POST – RECEPCIÓN DE MENSAJES (MÁQUINA DE ESTADOS)
# ======================================================
@app.post("/webhook")
async def handle_whatsapp_messages(request: Request):
    data = await request.json()

    print("==== RAW WEBHOOK ====")
    print(data)
    print("=====================")

    info = extract_message_info(data)

    # Si el mensaje no es texto o no se puede leer
    if not info:
        return {"status": "ignored"}

    sender = info["sender"]
    sender_name = info["sender_name"] or "Paciente"
    text = info["text"].lower().strip()

    # Obtener estado actual
    state = user_sessions.get(sender, {"state": "INICIO"})["state"]

    # ===========================================
    # ✅ LÓGICA DE ESTADOS - INICIO
    # ===========================================
    if state == "INICIO":

        # Parámetros para la plantilla (solo un parámetro {{1}})
        template_params = [
            {"name": "1", "value": sender_name}
        ]

        # ---- Usuario quiere agendar ----
        if "agendar" in text or "hora" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_FECHA"}
            send_template_message(sender, "agenza_inicio", template_params)
            return {"status": "iniciado_agendamiento"}

        # ---- Usuario quiere cancelar ----
        if "cancelar" in text or "anular" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_CANCELAR_RUT"}
            send_template_message(sender, "agenza_inicio", template_params)
            return {"status": "iniciado_cancelacion"}

        # ---- Saludo genérico ----
        send_template_message(sender, "agenza_inicio", template_params)
        return {"status": "template_sent_bienvenida"}

    # ===========================================
    # ✅ ESTADO: PREGUNTANDO_FECHA (simplificado por ahora)
    # ===========================================
    if state == "PREGUNTANDO_FECHA":
        send_template_message(sender, "agenza_inicio", [
            {"name": "1", "value": sender_name}
        ])
        return {"status": "ok_date_received"}

    return {"status": "ok"}
