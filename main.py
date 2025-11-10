# main.py
import requests
from fastapi import FastAPI, Request, HTTPException
import json
import os
from datetime import datetime, timedelta, timezone
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
# ✅ FUNCIÓN PARA ENVIAR PLANTILLAS DE WATI (V1 LEGACY)
# ======================================================
def send_template_message(recipient_number: str, template_name: str, parameters: List[Dict[str, str]]):
    """
    Envía una Plantilla Aprobada de WATI (requerido para tu tipo de tenant).
    """

    WATI_BASE_URL = os.getenv("WATI_ENDPOINT_BASE")
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN")
    WATI_ACCOUNT_ID = os.getenv("WATI_ACCOUNT_ID")

    if not WATI_BASE_URL or not WATI_ACCESS_TOKEN or not WATI_ACCOUNT_ID:
        print("❌ ERROR: Variables WATI no configuradas.")
        return

    url = f"{WATI_BASE_URL}/{WATI_ACCOUNT_ID}/api/v1/broadcast/scheduleBroadcast"

    headers = {
        "Authorization": WATI_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    # ✅ WATI exige tiempo futuro y segundos = 00
    now_utc = datetime.now(timezone.utc)
    scheduled = now_utc + timedelta(seconds=70)  # +70s mínimo para evitar timezone issues
    scheduled = scheduled.replace(second=0, microsecond=0)  # segundos = 00 exacto
    schedule_time_str = scheduled.strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "TemplateName": template_name,
        "BroadcastName": f"AGENZA_BOT_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "Parameters": parameters,
        "Receivers": [
            {"WhatsAppNumber": recipient_number.replace("+", "")}
        ],
        "ScheduleTime": schedule_time_str
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)

        # --- LOG COMPLETO ---
        print("=== DEBUG TEMPLATE SEND ===")
        print("URL:", url)
        print("STATUS:", r.status_code)
        print("BODY:", r.text)
        print("PAYLOAD:", payload)
        print("===========================")

        r.raise_for_status()
        print("✅ ÉXITO WATI: Plantilla enviada correctamente.")

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
            "text": data.get("text", "").strip()
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

    if not info:
        return {"status": "ignored"}

    sender = info["sender"]
    text = info["text"].lower().strip()

    state = user_sessions.get(sender, {"state": "INICIO"})["state"]

    # Paciente del piloto
    nombre_paciente_temp = "Erick"

    template_params = [{"name": "1", "value": nombre_paciente_temp}]

    # ===========================================
    # ✅ ESTADO: INICIO
    # ===========================================
    if state == "INICIO":

        if "agendar" in text or "hora" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_FECHA"}

            send_template_message(sender, "agenza_inicio", template_params)
            return {"status": "iniciado_agendamiento"}

        if "cancelar" in text or "anular" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_CANCELAR_RUT"}

            send_template_message(sender, "agenza_inicio", template_params)
            return {"status": "iniciado_cancelacion"}

        # Saludo normal
        send_template_message(sender, "agenza_inicio", template_params)
        return {"status": "template_sent_solo_saludo"}

    # ===========================================
    # ✅ ESTADO: PREGUNTANDO_FECHA
    # ===========================================
    if state == "PREGUNTANDO_FECHA":
        send_template_message(sender, "agenza_inicio", template_params)
        return {"status": "ok_date_received"}

    return {"status": "ok"}
