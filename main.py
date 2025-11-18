# main.py → FLUJO COMPLETO NEON 2025 (YCloud + Railway + Neon DB)

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
import os
import requests
from datetime import datetime, date
import pytz
from loguru import logger
from db_service import obtener_lista_medicos, consultar_disponibilidad, reservar_cita

app = FastAPI()

# ====================== CONFIG YCLOUD ======================
API_KEY = os.getenv("YCLOUD_API_KEY")
PHONE_ID = os.getenv("YCLOUD_PHONE_ID")
VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "clinica2025")
CHILE_TZ = pytz.timezone("America/Santiago")

# ====================== ESTADO EN MEMORIA ======================
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

# ====================== GET/SET ESTADO ======================
async def get_estado(telefono: str):
    return conversaciones.get(telefono, {"estado": "inicio"})

async def set_estado(telefono: str, datos: dict):
    conversaciones[telefono] = datos

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

        estado = await get_estado(telefono)

        # FLUJO COMPLETO CON NEON DB
        if estado["estado"] == "inicio":
            await enviar_mensaje(telefono, "¡Hola! Bienvenido(a) a *Clínica Sonrisas*\n\n¿Qué deseas?\n1️⃣ Agendar cita\n2️⃣ Ver mis citas\n3️⃣ Cancelar cita")
            await set_estado(telefono, {"estado": "menu"})

        elif estado["estado"] == "menu":
            if "1" in texto:
                medicos = obtener_lista_medicos()
                if not medicos:
                    await enviar_mensaje(telefono, "Lo siento, no hay médicos disponibles ahora.")
                    return
                respuesta = "Elige tu médico:\n\n"
                for i, m in enumerate(medicos, 1):
                    respuesta += f"{i}️⃣ Dr(a). {m['nombre']} - {m['especialidad']}\n"
                respuesta += "\nEscribe solo el número 👆"
                await enviar_mensaje(telefono, respuesta)
                await set_estado(telefono, {"estado": "elegir_medico", "medicos": medicos})
            elif "2" in texto:
                await enviar_mensaje(telefono, "Para ver citas, envía tu RUT (ej: 12.345.678-9)")
                await set_estado(telefono, {"estado": "ver_citas"})
            else:
                await enviar_mensaje(telefono, "Opción no válida. Escribe 1 para agendar.")

        elif estado["estado"] == "elegir_medico":
            try:
                idx = int(texto) - 1
                medico = estado["medicos"][idx]
                await enviar_mensaje(telefono, f"Perfecto, Dr(a). {medico['nombre']}\n\n¿Para qué fecha? (ej: 20-11-2025)")
                await set_estado(telefono, {"estado": "elegir_fecha", "medico_id": medico["id_medico"], "medico_nombre": medico["nombre"]})
            except:
                await enviar_mensaje(telefono, "Número inválido. Escribe solo el número del médico.")

        elif estado["estado"] == "elegir_fecha":
            try:
                fecha = datetime.strptime(texto, "%d-%m-%Y").date()
                if fecha < date.today():
                    await enviar_mensaje(telefono, "Fecha inválida. Elige una fecha futura.")
                    return
                bloques = consultar_disponibilidad(estado["medico_id"], fecha)
                if not bloques:
                    await enviar_mensaje(telefono, "No hay horarios disponibles esa fecha. Elige otra.")
                    return
                respuesta = f"Horarios disponibles {texto}:\n\n"
                for i, b in enumerate(bloques, 1):
                    respuesta += f"{i}️⃣ {b['hora_str']}\n"
                respuesta += "\nEscribe solo el número del horario"
                await enviar_mensaje(telefono, respuesta)
                await set_estado(telefono, {**estado, "estado": "elegir_hora", "fecha": fecha, "bloques": bloques})
            except:
                await enviar_mensaje(telefono, "Formato inválido. Usa DD-MM-YYYY")

        elif estado["estado"] == "elegir_hora":
            try:
                idx = int(texto) - 1
                bloque = estado["bloques"][idx]
                await enviar_mensaje(telefono, "Perfecto. Ahora dime:\n\n• Nombre completo\n• RUT (ej: 12.345.678-9)")
                await set_estado(telefono, {**estado, "estado": "datos_paciente", "bloque_id": bloque["id_bloque"]})
            except:
                await enviar_mensaje(telefono, "Número inválido.")

        elif estado["estado"] == "datos_paciente":
            lineas = [l.strip() for l in texto.split("\n") if l.strip()]
            if len(lineas) < 2:
                await enviar_mensaje(telefono, "Faltan datos. Nombre y RUT por favor.")
                return
            nombre = lineas[0]
            rut = lineas[1].replace(".", "").replace("-", "").lower()
            if not rut[:-1].isdigit() or len(rut) < 8:
                await enviar_mensaje(telefono, "RUT inválido. Ejemplo: 12345678-9")
                return

            exito = reservar_cita(
                id_bloque=estado["bloque_id"],
                rut=rut,
                nombre_completo=nombre,
                telefono=telefono,
                id_medico=estado["medico_id"]
            )
            if exito:
                await enviar_mensaje(telefono, f"¡CITA CONFIRMADA! 🎉\n\nDr(a). {estado['medico_nombre']}\nFecha: {estado['fecha'].strftime('%d-%m-%Y')}\nHora: {estado['bloques'][idx]['hora_str']}\nPaciente: {nombre}\n\n¡Te esperamos! 😊\nDirección: Av. Siempre Viva 123, Santiago")
            else:
                await enviar_mensaje(telefono, "Lo siento, ese horario ya fue tomado. Elige otro.")
            await set_estado(telefono, {"estado": "inicio"})

        elif estado["estado"] == "ver_citas":
            # Aquí puedes agregar consulta real a Neon
            await enviar_mensaje(telefono, "Para ver citas, envía tu RUT (ej: 12.345.678-9)")
            await set_estado(telefono, {"estado": "menu"})

    return {"status": "ok"}

@app.get("/")
async def root():
    return {"status": "Bot citas 24/7 activo", "hora_chile": datetime.now(CHILE_TZ).strftime("%d-%m-%Y %H:%M")}