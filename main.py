# main.py
import requests
from fastapi import FastAPI, Request, HTTPException
import os
from typing import Dict, Any
from datetime import datetime

# Importaciones de tu servicio de BD
from db_service import consultar_disponibilidad, reservar_cita, buscar_citas_pendientes, cancelar_cita

app = FastAPI()

# Config global
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "AGZ_TOKEN_DE_PRUEBA_123")
MEDICO_PILOTO_ID = 1
user_sessions: Dict[str, Any] = {}


# ---------------------------------------------------------
# ✅ FUNCIÓN DE ENVÍO A WATI (BLINDADA Y FINAL)
# ---------------------------------------------------------
def send_whatsapp_message(recipient_number: str, message_text: str):

    # ▶ Variables desde Railway
    WATI_BASE = os.getenv("WATI_ENDPOINT_BASE")          # https://live-mt-server.wati.io
    WATI_TOKEN = os.getenv("WATI_ACCESS_TOKEN")          # Bearer eyJ...
    WATI_TENANT = os.getenv("WATI_ACCOUNT_ID")           # 1043548

    if not WATI_BASE or not WATI_TOKEN or not WATI_TENANT:
        print("❌ ERROR: Variables de entorno WATI incompletas.")
        return

    # ▶ Normalizar número
    wa_number = recipient_number.replace("+", "").strip()

    # ▶ URL oficial final ✅
    url = f"{WATI_BASE}/{WATI_TENANT}/api/v1/sendSessionMessage/{wa_number}"

    # ▶ Evitar errores por cadena vacía
    if not message_text or not message_text.strip():
        print(f"⚠ No se envió mensaje: message_text vacío para {recipient_number}")
        return

    headers = {
        "Authorization": WATI_TOKEN,  # El valor en Railway DEBE incluir "Bearer "
        "Content-Type": "application/json"
    }

    payload = {"messageText": message_text}

    # ▶ DEBUG limpio
    print("\n--- DEBUG ENVÍO WATI (v1) ---")
    print("URL:", url)
    print("TO:", wa_number)
    print("TEXT:", message_text)
    print("------------------------------")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        print("STATUS:", response.status_code)
        print("BODY:", response.text)
        response.raise_for_status()
        print("✅ MENSAJE ENVIADO A WATI\n")

    except Exception as e:
        print("❌ ERROR AL ENVIAR A WATI:", e)


# ---------------------------------------------------------
# ✅ EXTRAER DATOS DEL MENSAJE ENTRANTE
# ---------------------------------------------------------
def extract_message_info(data):
    """
    WATI v1 entrega un JSON plano con:
    type = 'text'
    waId = '569xxxxxxx'
    text = 'mensaje'
    """
    try:
        if data.get("type") == "text":
            return {
                "sender": "+" + data.get("waId", ""),
                "text": data.get("text", "").strip()
            }
    except:
        pass

    return None


# ---------------------------------------------------------
# ✅ WEBHOOK GET (verificación)
# ---------------------------------------------------------
@app.get("/webhook")
def verify_webhook(request: Request):
    try:
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("✅ WEBHOOK VERIFICADO POR WATI")
            return int(challenge)
        else:
            raise HTTPException(status_code=403, detail="Token inválido")

    except:
        raise HTTPException(status_code=500, detail="Error interno")


# ---------------------------------------------------------
# ✅ WEBHOOK POST (LÓGICA DE AGENZA)
# ---------------------------------------------------------
@app.post("/webhook")
async def handle_whatsapp_messages(request: Request):
    try:
        data = await request.json()

        # ▶ Debug entrada
        print("\n==== RAW WEBHOOK ====")
        print(data)
        print("=====================")

        message_info = extract_message_info(data)

        if not message_info:
            print("⚠ Webhook ignorado (no es texto)")
            return {"status": "ignored"}

        sender_number = message_info["sender"]
        text = message_info["text"].lower().strip()

        current_state = user_sessions.get(sender_number, {"state": "INICIO"})
        state = current_state["state"]

        response_text = ""

        # -----------------------------------------------------
        # ✅ ESTADO INICIO
        # -----------------------------------------------------
        if state == "INICIO":
            if "agendar" in text or "hora" in text:
                response_text = "¡Hola! Indica la fecha (ej. 2025-11-06) para buscar disponibilidad."
                user_sessions[sender_number] = {"state": "PREGUNTANDO_FECHA"}

            elif "cancelar" in text or "anular" in text:
                response_text = "Para cancelar tu cita, por favor ingresa tu RUT/RUN/DNI."
                user_sessions[sender_number] = {"state": "PREGUNTANDO_CANCELAR_RUT"}

            else:
                response_text = "Bienvenido a Agenza. Escribe 'agendar' o 'cancelar' para comenzar."

        # -----------------------------------------------------
        # ✅ (INCOMPLETO) — Agregar aquí tu lógica completa
        # -----------------------------------------------------
        # Ejemplo:
        # if state == "PREGUNTANDO_FECHA":
        #    ...

        # -----------------------------------------------------
        # ✅ Enviar respuesta final
        # -----------------------------------------------------
        if response_text.strip():
            print(">>> RESPUESTA:", response_text)
            send_whatsapp_message(sender_number, response_text)
        else:
            print("⚠ No se envió mensaje porque response_text era vacío.")

        return {"status": "ok"}

    except Exception as e:
        print("❌ ERROR en webhook:", e)
        user_sessions[sender_number] = {"state": "INICIO"}

        send_whatsapp_message(
            sender_number,
            "Lo siento, ocurrió un error. Escribe 'agendar' o 'cancelar' para volver a empezar."
        )

        return {"status": "error"}, 200
