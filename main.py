# main.py → VERSIÓN BÁSICA FUNCIONANDO (YCloud + Railway – sin DB)

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
import os
import requests
from datetime import datetime
import pytz
from loguru import logger

app = FastAPI()

# ====================== CONFIG YCLOUD ======================
API_KEY = os.getenv("YCLOUD_API_KEY")
PHONE_ID = os.getenv("YCLOUD_PHONE_ID")
VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "clinica2025")
CHILE_TZ = pytz.timezone("America/Santiago")

# ====================== ESTADO SIMPLE (en memoria, sin DB) ======================
conversaciones = {}

# ====================== ENVIAR MENSAJE ======================
async def enviar_mensaje(to: str, texto: str):
    url = f"https://api.ycloud.com/v2/api/whatsapp/{PHONE_ID}/messages"
    payload = {"to": to, "type": "text", "text": {"body": texto}}
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    try:
        requests.post(url, json=payload, headers=headers, timeout=10)
        logger.success(f"Enviado a {to}")
    except Exception as e:
        logger.error(f"Error enviando: {e}")

# ====================== WEBHOOK ======================
@app.get("/webhook")
async def verify(request: Request):
    if request.query_params.get("hub.mode") == "subscribe" and request.query_params.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(request.query_params.get("hub.challenge"))
    raise HTTPException(403)

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    if "messages" not in data:
        return {"status": "ok"}

    for msg in data["messages"]:
        telefono = msg["from"]
        texto = msg.get("text", {}).get("body", "").strip().lower()

        # Estado simple en memoria
        estado = conversaciones.get(telefono, {"estado": "inicio"})

        # FLUJO BÁSICO (sin DB – responde siempre)
        if estado["estado"] == "inicio":
            await enviar_mensaje(telefono, "¡Hola! 👋 Bienvenido(a) a *Clínica Sonrisas*\n\n¿Qué deseas?\n1️⃣ Agendar cita\n2️⃣ Ver horarios\n3️⃣ Contacto")
            conversaciones[telefono] = {"estado": "menu"}

        elif estado["estado"] == "menu":
            if "1" in texto:
                await enviar_mensaje(telefono, "Para agendar:\n• Elige médico: Dr. Pérez (Odontología) o Dra. López (Ortodoncia)\n• Fecha: DD-MM-YYYY\n• Hora: 9:00, 10:00, etc.\n\nEjemplo: 'Dr. Pérez 20-11-2025 10:00'")
                conversaciones[telefono] = {"estado": "agendar"}
            else:
                await enviar_mensaje(telefono, "Opción no válida. Escribe 1 para agendar.")
                conversaciones[telefono] = {"estado": "inicio"}

        elif estado["estado"] == "agendar":
            # Simula reserva (sin DB – responde confirmación)
            await enviar_mensaje(telefono, f"¡Cita agendada! {texto}\n\nTe esperamos. 😊\nDirección: Av. Ejemplo 123, Santiago")
            conversaciones[telefono] = {"estado": "inicio"}

        else:
            await enviar_mensaje(telefono, "¡Hola! Escribe '1' para agendar cita.")
            conversaciones[telefono] = {"estado": "inicio"}

    return {"status": "ok"}

@app.get("/")
async def root():
    return {"status": "Bot citas 24/7 activo", "hora_chile": datetime.now(CHILE_TZ).strftime("%d-%m-%Y %H:%M")}