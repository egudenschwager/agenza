# main.py
import requests
from fastapi import FastAPI, Request, HTTPException
import json
import os
from datetime import datetime, date
from typing import Dict, Any

# Funciones de la BD
from db_service import consultar_disponibilidad, reservar_cita, buscar_citas_pendientes, cancelar_cita

app = FastAPI()

# --- CONFIGURACIÓN ---
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "AGZ_TOKEN_DE_PRUEBA_123")
MEDICO_PILOTO_ID = 1
user_sessions: Dict[str, Any] = {}


# ============================================================
# ✅ FUNCIÓN FINAL DE ENVÍO A WATI (TU TENANT → usa "message")
# ============================================================
def send_whatsapp_message(recipient_number, message_text):

    WATI_BASE_ENDPOINT = os.getenv("WATI_ENDPOINT_BASE")          # https://live-mt-server.wati.io
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN")            # Bearer xxx
    WATI_ACCOUNT_ID = os.getenv("WATI_ACCOUNT_ID")                # 1043548

    if not WATI_BASE_ENDPOINT or not WATI_ACCESS_TOKEN or not WATI_ACCOUNT_ID:
        print("ERROR: Credenciales WATI no configuradas.")
        return

    wa_id = recipient_number.replace("+", "")
    url = f"{WATI_BASE_ENDPOINT}/{WATI_ACCOUNT_ID}/api/v1/sendSessionMessage/{wa_id}"

    headers = {
        "Authorization": WATI_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    # ✅ FIX: Tu tenant NO usa messageText → usa message
    payload = {
        "message": message_text
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        print("\n--- DEBUG ENVÍO WATI (v1) ---")
        print("URL:", url)
        print("TO:", wa_id)
        print("TEXT:", message_text)
        print("------------------------------")
        print("STATUS:", response.status_code)
        print("BODY:", response.text)
        print("✅ MENSAJE ENVIADO A WATI\n")

        response.raise_for_status()

    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR enviando mensaje a WATI: {e}")


# ============================================================
# ✅ EXTRACCIÓN DEL MENSAJE DESDE EL JSON RAW DE WATI
# ============================================================
def extract_message_info(data):

    # ✅ Tu tenant envía siempre este formato:
    #    {"text": "...", "type": "text", "waId": "569..."}

    if data.get("type") == "text" and "text" in data:
        return {
            "sender": "+" + data.get("waId", ""),
            "text": data.get("text", "").strip()
        }

    return None


# ============================================================
# ✅ VERIFICACIÓN DEL WEBHOOK
# ============================================================
@app.get("/webhook")
def verify_webhook(request: Request):
    try:
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("✅ WEBHOOK VERIFICADO")
            return int(challenge)

        raise HTTPException(status_code=403, detail="Token inválido")

    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================
# ✅ LÓGICA DEL CHATBOT
# ============================================================
@app.post("/webhook")
async def handle_whatsapp_messages(request: Request):
    try:
        data = await request.json()

        print("\n==== RAW WEBHOOK ====")
        print(data)
        print("=====================\n")

        message_info = extract_message_info(data)

        if not message_info:
            return {"status": "ignored"}

        sender_number = message_info["sender"]
        text = message_info["text"].lower()

        current_state = user_sessions.get(sender_number, {"state": "INICIO"})
        state = current_state["state"]

        response_text = ""

        # -----------------------
        # ✅ Estado inicial
        # -----------------------
        if state == "INICIO":
            if "agendar" in text:
                response_text = "Perfecto 👍 ¿Qué fecha deseas? (Ej: 2025-11-06)"
                user_sessions[sender_number] = {"state": "PREGUNTANDO_FECHA"}

            elif "cancelar" in text:
                response_text = "Para cancelar tu cita, indícame tu RUT/RUN/DNI."
                user_sessions[sender_number] = {"state": "PREGUNTANDO_CANCELAR_RUT"}

            else:
                response_text = "Bienvenido a Agenza. Escribe 'agendar' o 'cancelar' para comenzar."

        # ✅ Más estados se agregan aquí…

        # -----------------------
        # ✅ Enviar mensaje
        # -----------------------
        if response_text:
            print(f">>> RESPUESTA: {response_text}")
            send_whatsapp_message(sender_number, response_text)

        return {"status": "ok"}

    except Exception as e:
        print("❌ ERROR WEBHOOK:", e)
        send_whatsapp_message(sender_number, "Lo siento, ocurrió un error. Escribe 'agendar' para comenzar.")
        return {"status": "error"}

