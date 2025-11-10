# main.py
import requests 
from fastapi import FastAPI, Request, HTTPException
import json
import os
from datetime import datetime, date 
from typing import Dict, Any, List

# --- Importar funciones de base de datos (se asume db_service está en la carpeta) ---
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
    WATI_BASE_ENDPOINT = os.getenv("WATI_ENDPOINT_BASE") # https://live-mt-server.wati.io
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN")
    WATI_ACCOUNT_ID = os.getenv("WATI_ACCOUNT_ID")

    if not WATI_BASE_ENDPOINT or not WATI_ACCESS_TOKEN or not WATI_ACCOUNT_ID:
        print("❌ ERROR: Variables WATI no configuradas. Abortando envío.")
        return

    # Endpoint V1/Broadcast correcto: BASE / ACCOUNT_ID / api/v1 / broadcast / scheduleBroadcast
    url = f"{WATI_BASE_ENDPOINT}/{WATI_ACCOUNT_ID}/api/v1/broadcast/scheduleBroadcast"

    headers = {
        "Authorization": WATI_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    # El payload debe usar 'receivers' para enviar a un solo número
    payload = {
        "template_name": template_name,
        "broadcast_name": f"AGENZA_BOT_RESPUESTA_{datetime.now().strftime('%Y%m%d%H%M')}",
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
        print("✅ ÉXITO WATI: Plantilla enviada correctamente.")
        
    except Exception as e:
        print(f"❌ ERROR CRÍTICO enviando plantilla: {e}")


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
    info = extract_message_info(data)
    
    # Si el mensaje no es texto o es ignorado
    if not info:
        return {"status": "ignored"}

    sender = info["sender"]
    text = info["text"].lower().strip()
    state = user_sessions.get(sender, {"state": "INICIO"})["state"]
    
    # 🚨 NOTA: Para el piloto, usaremos un nombre fijo para el saludo
    nombre_paciente_temp = "Erick" 

    # ===========================================
    # ✅ LÓGICA DE ESTADOS - INICIO
    # ===========================================
    if state == "INICIO":
        
        # 1. Preparar la plantilla de bienvenida para la respuesta inmediata
        template_params = [{"name": "1", "value": nombre_paciente_temp}] # Si tu plantilla usa {{1}}
        
        if "agendar" in text or "hora" in text:
            # Si el usuario quiere agendar, enviamos la plantilla y pasamos al siguiente estado
            user_sessions[sender] = {"state": "PREGUNTANDO_FECHA"}
            
            # --- ENVÍO DE PLANTILLA (Responde al mensaje entrante) ---
            send_template_message(sender, "agenza_bienvenida", template_params)
            return {"status": "iniciado_agendamiento"}
        
        # 2. Si el usuario quiere cancelar
        if "cancelar" in text or "anular" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_CANCELAR_RUT"}
            send_template_message(sender, "agenza_bienvenida", template_params)
            return {"status": "iniciado_cancelacion"}

        # 3. Si el usuario solo saluda (respuesta por defecto)
        send_template_message(sender, "agenza_bienvenida", template_params)
        return {"status": "template_sent_bienvenida"}

    # ===========================================
    # ✅ ESTADO: PREGUNTANDO_FECHA (Continuación del flujo)
    # ===========================================
    if state == "PREGUNTANDO_FECHA":
        # ... (Aquí iría la lógica de validación de fecha, consulta a la BD, y respuesta con opciones)
        
        # Al no poder enviar mensajes libres, asumiremos que si la fecha es inválida o no hay horas,
        # debemos usar otra plantilla (ej. una plantilla de "No hay horas") o re-enviar la bienvenida.
        send_template_message(sender, "agenza_bienvenida", [{"name": "1", "value": nombre_paciente_temp}])
        return {"status": "ok_date_received"}


    # NOTA: Los otros estados de la Máquina (PREGUNTANDO_HORA, CANCELAR_RUT, etc.) 
    # deberían ser actualizados para usar send_template_message con plantillas específicas para cada paso.

    return {"status": "ok"}