# main.py
import requests
from fastapi import FastAPI, Request, HTTPException
import os
from typing import Dict, Any
from datetime import datetime

# --- Importar servicios de base de datos ---
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
# ✅ SANITIZADOR DE MENSAJES PARA PLANTILLAS WATI
# ======================================================
def sanitize_message(text: str) -> str:
    if not text:
        return ""
    text = text.replace("*", "")
    text = text.replace("_", "")
    text = text.replace("~", "")
    text = text.replace("`", "")
    return text.strip()


# ======================================================
# ✅ FUNCIÓN PARA ENVIAR PLANTILLAS DE WATI (V1)
# ======================================================
def send_template_message(recipient_number: str, template_name: str, param_value="Hola"):
    WATI_BASE = os.getenv("WATI_ENDPOINT_BASE")  # https://live-mt-server.wati.io
    WATI_TOKEN = os.getenv("WATI_ACCESS_TOKEN")
    WATI_ID = os.getenv("WATI_ACCOUNT_ID")  # 1043548

    if not WATI_BASE or not WATI_TOKEN or not WATI_ID:
        print("❌ ERROR: Variables de entorno WATI no configuradas.")
        return

    # Limpiar número (+569 -> 569)
    wa = recipient_number.replace("+", "")

    url = f"{WATI_BASE}/{WATI_ID}/api/v1/sendTemplateMessage"

    headers = {
        "Authorization": WATI_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "template_name": template_name,
        "broadcast_name": template_name,
        "parameters": [
            {"name": "1", "value": param_value}
        ],
        "receivers": [
            {"whatsappNumber": wa}
        ]
    }

    print("=== DEBUG TEMPLATE SEND ===")
    print("URL:", url)
    print("Payload:", payload)
    print("===========================")

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        print("STATUS:", r.status_code)
        print("BODY:", r.text)
    except Exception as e:
        print("❌ ERROR enviando plantilla:", e)


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
# ✅ ENDPOINT POST – RECEPCIÓN DE MENSAJES
# ======================================================
@app.post("/webhook")
async def handle_whatsapp_messages(request: Request):
    data = await request.json()

    print("\n==== RAW WEBHOOK ====")
    print(data)
    print("=====================")

    info = extract_message_info(data)
    if not info:
        return {"status": "ignored"}

    sender = info["sender"]
    text = info["text"].lower().strip()

    # Estado actual del usuario
    state = user_sessions.get(sender, {"state": "INICIO"})["state"]

    # ===========================================
    # ✅ LÓGICA DE ESTADOS - INICIO
    # ===========================================
    if state == "INICIO":

        # Usuario quiere agendar
        if "agendar" in text or "hora" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_FECHA"}
            send_template_message(sender, "agenza_bienvenida")  
            return {"status": "ok"}

        # Usuario quiere cancelar
        if "cancelar" in text or "anular" in text:
            user_sessions[sender] = {"state": "PREGUNTANDO_CANCELAR_RUT"}
            send_template_message(sender, "agenza_bienvenida")
            return {"status": "ok"}

        # ✅ Si el usuario dice "hola", mandar PLANTILLA
        send_template_message(sender, "agenza_bienvenida")
        return {"status": "template_sent"}

    # ===========================================
    # ✅ ESTADO: PREGUNTANDO_FECHA
    # ===========================================
    if state == "PREGUNTANDO_FECHA":
        try:
            fecha = datetime.strptime(text, "%Y-%m-%d").date()
            disponibilidad = consultar_disponibilidad(MEDICO_PILOTO_ID, fecha)

            if not disponibilidad:
                send_template_message(sender, "agenza_bienvenida")  
                return {"status": "ok"}

            horas = ", ".join([d["hora"] for d in disponibilidad])
            message = f"✅ Disponibilidad para {fecha}:\n{horas}\n\nElige una hora."

            send_template_message(sender, "agenza_bienvenida")
            user_sessions[sender] = {"state": "PREGUNTANDO_HORA", "fecha": str(fecha)}
            return {"status": "ok"}
        except:
            send_template_message(sender, "agenza_bienvenida")
            return {"status": "ok"}

    # ===========================================
    # ✅ ESTADO: PREGUNTANDO_HORA
    # ===========================================
    if state == "PREGUNTANDO_HORA":
        hora = text
        fecha = user_sessions[sender].get("fecha")

        if not fecha:
            send_template_message(sender, "agenza_bienvenida")
            return {"status": "ok"}

        ok = reservar_cita(MEDICO_PILOTO_ID, fecha, hora, sender)

        if ok:
            send_template_message(sender, "agenza_bienvenida")
        else:
            send_template_message(sender, "agenza_bienvenida")

        user_sessions[sender] = {"state": "INICIO"}
        return {"status": "ok"}

    # ===========================================
    # ✅ ESTADO: PREGUNTANDO_CANCELAR_RUT
    # ===========================================
    if state == "PREGUNTANDO_CANCELAR_RUT":
        rut = text
        citas = buscar_citas_pendientes(rut)

        if not citas:
            send_template_message(sender, "agenza_bienvenida")
            return {"status": "ok"}

        cancelar_cita(rut)
        send_template_message(sender, "agenza_bienvenida")
        user_sessions[sender] = {"state": "INICIO"}
        return {"status": "ok"}

    return {"status": "ok"}
