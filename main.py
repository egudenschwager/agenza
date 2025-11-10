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

user_sessions: Dict[str, Any] = {}

# ======================================================
# ✅ FUNCIÓN PARA ENVIAR PLANTILLAS DE WATI (USANDO TUS VARIABLES)
# ======================================================
def send_template_message(recipient_number: str, template_name: str, parameters: List[Dict[str, str]]):
    
    # ✅ Ahora sí usamos EXACTAMENTE los nombres que tienes en Railway
    WATI_BASE_ENDPOINT = os.getenv("WATI_ENDPOINT_BASE")   # <-- corregido
    WATI_ACCESS_TOKEN  = os.getenv("WATI_ACCESS_TOKEN")
    WATI_ACCOUNT_ID    = os.getenv("WATI_ACCOUNT_ID")

    if not WATI_BASE_ENDPOINT or not WATI_ACCESS_TOKEN or not WATI_ACCOUNT_ID:
        print("❌ ERROR: Variables WATI no configuradas.")
        print("BASE:", WATI_BASE_ENDPOINT)
        print("TOKEN:", WATI_ACCESS_TOKEN)
        print("ACCOUNT:", WATI_ACCOUNT_ID)
        return

    url = f"{WATI_BASE_ENDPOINT}/{WATI_ACCOUNT_ID}/api/v1/broadcast/scheduleBroadcast"

    headers = {
        "Authorization": WATI_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "template_name": template_name,
        "broadcast_name": f"AGENZA_BOT_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "parameters": parameters,
        "receivers": [
            {"whatsappNumber": recipient_number.replace("+", "")}
        ],
        "scheduleTime": "now"
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)

        print("=== DEBUG TEMPLATE SEND ===")
        print("URL:", url)
        print("STATUS:", r.status_code)
        print("BODY:", r.text)
        print("===========================")

        r.raise_for_status()
        print("✅ Plantilla enviada correctamente.")

    except Exception as e:
        print(f"❌ ERROR enviando plantilla: {e}")

# ======================================================
# ✅ EXTRAER MENSAJE DE WATI
# ======================================================
def extract_message_info(data):
    if "type" in data and data.get("type") == "text":
        return {
            "sender": "+" + data.get("waId", ""),
            "text": data.get("text", "").strip()
        }
    return None

# ======================================================
# ✅ WEBHOOK VERIFICATION (GET)
# ======================================================
@app.get("/webhook")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verificado")
        return int(challenge)

    raise HTTPException(status_code=403, detail="Token inválido")

# ======================================================
# ✅ WEBHOOK RECEPTOR (POST)
# ======================================================
@app.post("/webhook")
async def handle_whatsapp_messages(request: Request):
    data = await request.json()
    info = extract_message_info(data)

    if not info:
        return {"status": "ignored"}

    sender = info["sender"]
    text   = info["text"].lower().strip()

    state = user_sessions.get(sender, {"state": "INICIO"})["state"]

    nombre_temp = "Paciente"

    # --- ESTADO INICIO ---
    if state == "INICIO":

        template_params = [{"name": "1", "value": nombre_temp}]

        if "agendar" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_FECHA"}
            send_template_message(sender, "agenza_bienvenida", template_params)
            return {"status": "agendar_start"}

        if "cancelar" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_CANCELAR_RUT"}
            send_template_message(sender, "agenza_bienvenida", template_params)
            return {"status": "cancel_start"}

        # Respuesta por defecto
        send_template_message(sender, "agenza_bienvenida", template_params)
        return {"status": "bienvenida_default"}

    # --- OTROS ESTADOS SE PUEDEN AGREGAR LUEGO ---
    send_template_message(sender, "agenza_bienvenida", [{"name": "1", "value": nombre_temp}])
    return {"status": "fallback"}