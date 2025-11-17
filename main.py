# main.py → Chatbot WhatsApp Citas Médicas 2025 (YCloud + Railway)

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
import os
import hmac
import hashlib
from loguru import logger
import requests
from datetime import datetime
from db_service import obtener_lista_medicos, consultar_disponibilidad, reservar_cita
from dateutil import parser
import pytz

app = FastAPI(title="Chatbot Citas Médicas WhatsApp")

# ==============================================================
# CONFIGURACIÓN YCLOUD
# ==============================================================

YCLOUD_API_KEY = os.getenv("YCLOUD_API_KEY")
YCLOUD_PHONE_ID = os.getenv("YCLOUD_PHONE_ID")  # ej: 113452XXXXXX
WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "mi_token_secreto_2025")

CHILE_TZ = pytz.timezone("America/Santiago")

# ==============================================================
# WEBHOOK VERIFICACIÓN (GET)
# ==============================================================

@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == WEBHOOK_VERIFY_TOKEN:
        logger.info("Webhook verificado correctamente")
        return PlainTextResponse(content=challenge)
    raise HTTPException(status_code=403, detail="Forbidden")

# ==============================================================
# WEBHOOK RECEPCIÓN MENSAJES (POST)
# ==============================================================

@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    
    # Verificar firma (seguridad YCloud)
    signature = request.headers.get("X-YCloud-Signature")
    if signature:
        expected = hmac.new(YCLOUD_API_KEY.encode(), await request.body(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401)

    # Procesar mensajes
    if "messages" in body:
        for message in body["messages"]:
            from_number = message["from"]
            text = message.get("text", {}).get("body", "").strip().lower()

            # Aquí va tu lógica de conversación (estado en DB o Redis)
            # Por ahora, ejemplo simple de saludo + menú
            if any(saludo in text for saludo in ["hola", "buenas", "hi"]):
                await enviar_mensaje_texto(from_number, 
                    "¡Hola! 👋 Bienvenido(a) a Clínica Sonrisas Perfectas\n\n¿Qué deseas hacer?\n1️⃣ Agendar cita\n2️⃣ Ver mis citas\n3️⃣ Cancelar cita")
    
    return JSONResponse({"status": "ok"})

# ==============================================================
# ENVIAR MENSAJE WHATSAPP (función reutilizable)
# ==============================================================

async def enviar_mensaje_texto(to: str, texto: str):
    url = f"https://api.ycloud.com/v2/api/whatsapp/{YCLOUD_PHONE_ID}/messages"
    payload = {
        "to": to,
        "type": "text",
        "text": {"body": texto}
    }
    headers = {
        "Authorization": f"Bearer {YCLOUD_API_KEY}",
        "Content-Type": "application/json"
    }
    try:
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        logger.error(f"Error enviando mensaje a {to}: {e}")

# ==============================================================
# HEALTH CHECK
# ==============================================================

@app.get("/")
async def root():
    return {"status": "Chatbot citas médicas activo 24/7", "hora_chile": datetime.now(CHILE_TZ).strftime("%Y-%m-%d %H:%M")}