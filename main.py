# main.py → YCLOUD 100% FUNCIONAL NOVIEMBRE 2025

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
import os
import requests
from datetime import datetime
import pytz
from loguru import logger

app = FastAPI()

# Variables YCloud
API_KEY = os.getenv("YCLOUD_API_KEY")
PHONE_ID = os.getenv("YCLOUD_PHONE_ID")
VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "clinica2025")

tz = pytz.timezone("America/Santiago")

@app.get("/")
async def home():
    return {
        "status": "Bot activo con YCloud",
        "hora_chile": datetime.now(tz).strftime("%d-%m-%Y %H:%M"),
        "provider": "YCloud"
    }

# Verificación del webhook
@app.get("/webhook")
async def verify(request: Request):
    if (request.query_params.get("hub.mode") == "subscribe" and
        request.query_params.get("hub.verify_token") == VERIFY_TOKEN):
        return PlainTextResponse(request.query_params.get("hub.challenge"))
    raise HTTPException(status_code=403)

# Recepción de mensajes
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if "messages" in data:
        for msg in data["messages"]:
            telefono = msg["from"]
            texto = msg.get("text", {}).get("body", "").lower()

            # Respuesta automática de prueba
            await enviar_mensaje(telefono,
                "¡Hola! Bienvenido(a)\n\nTu bot de citas médicas/odontológicas ya está funcionando 100% con YCloud\n\nEn breve tendrás el menú completo para agendar 24/7")

    return {"status": "ok"}

# Función para enviar mensajes
async def enviar_mensaje(to: str, texto: str):
    url = f"https://api.ycloud.com/v2/api/whatsapp/{PHONE_ID}/messages"
    payload = {
        "to": to,
        "type": "text",
        "text": {"body": texto}
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    try:
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        logger.error(f"Error enviando mensaje: {e}")