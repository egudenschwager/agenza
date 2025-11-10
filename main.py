# main.py
import requests
from fastapi import FastAPI, Request, HTTPException
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
# ✅ FUNCIÓN PARA ENVIAR PLANTILLA WATI V1 (CORRECTA)
# ======================================================
def send_template_message(recipient_number: str, template_name: str, parameters: List[Dict[str, str]]):
    """
    Envía una plantilla aprobada usando WATI V1 /broadcast/scheduleBroadcast
    """
    # Variables EXACTAS definidas en Railway
    WATI_BASE_ENDPOINT = os.getenv("WATI_ENDPOINT_BASE")
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN")
    WATI_ACCOUNT_ID = os.getenv("WATI_ACCOUNT_ID")

    if not WATI_BASE_ENDPOINT or not WATI_ACCESS_TOKEN or not WATI_ACCOUNT_ID:
        print("❌ ERROR: Variables WATI no configuradas.")
        print("WATI_ENDPOINT_BASE:", WATI_BASE_ENDPOINT)
        print("WATI_ACCESS_TOKEN:", WATI_ACCESS_TOKEN)
        print("WATI_ACCOUNT_ID:", WATI_ACCOUNT_ID)
        return

    # Endpoint correcto
    url = f"{WATI_BASE_ENDPOINT}/{WATI_ACCOUNT_ID}/api/v1/broadcast/scheduleBroadcast"

    headers = {
        "Authorization": WATI_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    # Payload con nombres en PascalCase — WATI requiere este formato exacto
    payload = {
        "TemplateName": template_name,
        "BroadcastName": f"AGENZA_BOT_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "Parameters": parameters,
        "Receivers": [
            {"WhatsAppNumber": recipient_number.replace("+", "")}
        ],
        "ScheduleTime": "now"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)

        print("=== DEBUG TEMPLATE SEND ===")
        print("URL:", url)
        print("STATUS:", response.status_code)
        print("BODY:", response.text)
        print("===========================")

        response.raise_for_status()
        print("✅ Plantilla enviada correctamente.")

    except Exception as e:
        print(f"❌ ERROR enviando plantilla: {e}")


# ======================================================
# ✅ EXTRAER MENSAJE DESDE WATI
# ======================================================
def extract_message_info(data):
    """
    Extrae la información del JSON de WATI (compatible con webhook actual)
    """
    if "type" in data and data.get("type") == "text":
        return {
            "sender": "+" + data.get("waId", ""),
            "text": data.get("text", "").strip()
        }
    return None


# ======================================================
# ✅ ENDPOINT GET – VERIFICACIÓN WEBHOOK
# ======================================================
@app.get("/webhook")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ WEBHOOK VERIFICADO")
        return int(challenge)

    raise HTTPException(status_code=403, detail="Token incorrecto")


# ======================================================
# ✅ ENDPOINT POST – LÓGICA DEL BOT
# ======================================================
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
    text = info["text"].lower().strip()

    state = user_sessions.get(sender, {"state": "INICIO"})["state"]

    # Para pruebas: nombre fijo
    nombre_paciente = "Erick"

    # ===========================================
    # ✅ ESTADO: INICIO
    # ===========================================
    if state == "INICIO":

        template_params = [
            {"name": "1", "value": nombre_paciente}
        ]

        # Si dice agendar
        if "agendar" in text or "hora" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_FECHA"}
            send_template_message(sender, "agenza_inicio", template_params)
            return {"status": "agendar_iniciado"}

        # Si dice cancelar
        if "cancelar" in text or "anular" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_CANCELAR_RUT"}
            send_template_message(sender, "agenza_inicio", template_params)
            return {"status": "cancelar_iniciado"}

        # Respuesta por defecto
        send_template_message(sender, "agenza_inicio", template_params)
        return {"status": "bienvenida"}

    # ===========================================
    # ✅ ESTADO: PREGUNTANDO_FECHA
    # ===========================================
    if state == "PREGUNTANDO_FECHA":
        # Aquí irá la validación de fecha + consulta a BD
        send_template_message(sender, "agenza_inicio", [
            {"name": "1", "value": nombre_paciente}
        ])
        return {"status": "fecha_ok"}

    return {"status": "ok"}
