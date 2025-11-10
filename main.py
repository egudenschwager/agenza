# main.py
import requests
from fastapi import FastAPI, Request, HTTPException
import json
import os
from datetime import datetime
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
# ✅ FUNCIÓN CORRECTA PARA ENVIAR PLANTILLAS DE WATI (API v2)
# ======================================================
def send_template_message(recipient_number: str, template_name: str, parameters: List[Dict[str, str]]):
    """
    Envía una plantilla aprobada utilizando la API correcta de WATI (v2).
    """

    WATI_BASE_ENDPOINT = os.getenv("WATI_BASE_ENDPOINT")     # https://live-mt-server.wati.io
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN")       # Debe incluir 'Bearer ...'
    WATI_ACCOUNT_ID = os.getenv("WATI_ACCOUNT_ID")

    if not WATI_BASE_ENDPOINT or not WATI_ACCESS_TOKEN or not WATI_ACCOUNT_ID:
        print("❌ ERROR: Variables WATI no configuradas.")
        return

    url = f"{WATI_BASE_ENDPOINT}/{WATI_ACCOUNT_ID}/api/v2/sendTemplateMessage"

    headers = {
        "Authorization": WATI_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "template_name": template_name,
        "broadcast_name": f"agenza_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "to": recipient_number.replace("+", ""),
        "parameters": parameters
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)

        print("\n=== DEBUG TEMPLATE SEND (REAL API v2) ===")
        print("URL:", url)
        print("PAYLOAD:", json.dumps(payload, indent=2, ensure_ascii=False))
        print("STATUS:", r.status_code)
        print("BODY:", r.text)
        print("========================================\n")

        r.raise_for_status()
        print("✅ Plantilla enviada correctamente a WATI.\n")

    except Exception as e:
        print(f"❌ ERROR enviando plantilla: {e}")


# ======================================================
# ✅ EXTRAER MENSAJE DESDE WATI
# ======================================================
def extract_message_info(data):
    if "type" in data and data.get("type") == "text":
        return {
            "sender": "+" + data.get("waId", ""),
            "text": data.get("text", "").strip()
        }
    return None


# ======================================================
# ✅ VERIFICACIÓN WEBHOOK
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
# ✅ POST /webhook — Máquina de Estados
# ======================================================
@app.post("/webhook")
async def handle_whatsapp_messages(request: Request):
    data = await request.json()

    info = extract_message_info(data)
    if not info:
        return {"status": "ignored"}

    sender = info["sender"]
    text = info["text"].lower().strip()

    state = user_sessions.get(sender, {"state": "INICIO"})["state"]

    # Para el piloto: nombre fijo
    nombre_paciente = "Erick"

    # ===========================
    # ✅ INICIO
    # ===========================
    if state == "INICIO":

        params = [{"name": "1", "value": nombre_paciente}]

        # Usuario quiere agendar
        if "agendar" in text or "hora" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_FECHA"}
            send_template_message(sender, "agenza_bienvenida", params)
            return {"status": "agendando"}

        # Usuario quiere cancelar
        if "cancelar" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_CANCELAR_RUT"}
            send_template_message(sender, "agenza_bienvenida", params)
            return {"status": "cancelando"}

        # Saludo por defecto
        send_template_message(sender, "agenza_bienvenida", params)
        return {"status": "template_sent_bienvenida"}

    # ===========================
    # ✅ PREGUNTANDO_FECHA
    # ===========================
    if state == "PREGUNTANDO_FECHA":
        send_template_message(sender, "agenza_bienvenida", [{"name": "1", "value": nombre_paciente}])
        return {"status": "fecha_recibida"}

    return {"status": "ok"}

