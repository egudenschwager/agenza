# main.py
import requests
from fastapi import FastAPI, Request, HTTPException
import json
import os
from datetime import datetime, date 
from typing import Dict, Any, List

# --- Importar funciones de base de datos (asume db_service está en la carpeta) ---
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
def send_template_message(recipient_number: str, template_name: str, param_value: str = "Estimado/a cliente"):
    """
    FUNCIÓN FINAL: Envía la Plantilla Aprobada de WATI (requerido para el tenant V1).
    """
    WATI_BASE = os.getenv("WATI_ENDPOINT_BASE")
    WATI_TOKEN = os.getenv("WATI_ACCESS_TOKEN")
    WATI_ID = os.getenv("WATI_ACCOUNT_ID")

    if not WATI_BASE or not WATI_TOKEN or not WATI_ID:
        print("❌ ERROR: Variables de entorno WATI no configuradas.")
        return

    # Endpoint V1/Broadcast: BASE / ACCOUNT_ID / api/v1 / broadcast / scheduleBroadcast
    url = f"{WATI_BASE}/{WATI_ID}/api/v1/broadcast/scheduleBroadcast"

    headers = {
        "Authorization": WATI_TOKEN,
        "Content-Type": "application/json"
    }

    # 🚨 SOLUCIÓN DE PAYLOAD: Usamos el nombre de plantilla aprobada con su parámetro.
    payload = {
        "template_name": "agenza_bienvenida", # Nombre aprobado en WATI
        "broadcast_name": f"Agenza_Saludo_{datetime.now().strftime('%H%M%S')}",
        "parameters": [
            {"name": "1", "value": param_value} # Parámetro para {{1}} (el nombre)
        ],
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
    
    # Imprimir el cuerpo del webhook entrante para diagnóstico (no lo haremos aquí para no saturar)
    # print(data)

    info = extract_message_info(data)
    if not info:
        return {"status": "ignored"}

    sender = info["sender"]
    text = info["text"].lower().strip()

    # Estado actual del usuario
    state = user_sessions.get(sender, {"state": "INICIO"})["state"]
    
    # 🚨 El nombre del paciente para la plantilla (asumimos un valor por defecto si no lo tenemos)
    nombre_paciente_temp = "Erick" 

    # ===========================================
    # ✅ LÓGICA DE ESTADOS - INICIO
    # ===========================================
    if state == "INICIO":
        
        # 1. Si el usuario quiere agendar
        if "agendar" in text or "hora" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_FECHA"}
            # Enviamos la plantilla de bienvenida para dar el primer paso
            send_template_message(sender, "agenza_bienvenida", nombre_paciente_temp)
            return {"status": "ok"}

        # 2. Si el usuario quiere cancelar
        if "cancelar" in text or "anular" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_CANCELAR_RUT"}
            send_template_message(sender, "agenza_bienvenida", nombre_paciente_temp)
            return {"status": "ok"}

        # 3. Respuesta por defecto o Saludo (Siempre con plantilla)
        send_template_message(sender, "agenza_bienvenida", nombre_paciente_temp)
        return {"status": "template_sent_bienvenida"}

    # ===========================================
    # ✅ LÓGICA DE ESTADOS RESTANTE (Resumida, pero asume las funciones de BD)
    # ===========================================
    
    # NOTA: Los otros estados de la Máquina (PREGUNTANDO_FECHA, CANCELAR_RUT, etc.) 
    # deben ser actualizados para usar send_template_message con plantillas específicas para cada paso.

    return {"status": "ok"}