from fastapi import FastAPI, Depends
import re
from sqlalchemy.orm import Session
from tools import agendar_cita, enviar_respuesta
from db import engine, Base, get_db
import models

# 🔥 Magia pura: Esto crea la base de datos (agenza.db) y las tablas automáticamente
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Memoria temporal de usuarios (FSM)
usuarios = {}

@app.post("/webhook")
def webhook(data: dict, db: Session = Depends(get_db)):
    try:
        # 1. Validación exclusiva para el puente local
        if data.get("type") != "whatsapp":
            return {"status": "ignored"}

        # 2. Extracción directa del JSON limpio que manda bridge.js
        texto = data.get("text", "").strip().lower()
        telefono = data.get("from", "")
        nombre = data.get("name", "Paciente")

        if not telefono or not texto:
            return {"status": "ignored"}

        print(f"\n📩 {nombre} ({telefono}): {texto}")

        # 3. Máquina de Estados (FSM)
        estado = usuarios.get(telefono, {"estado": "inicio"})

        # =========================
        # 🟢 INICIO
        # =========================
        if "hola" in texto or estado["estado"] == "inicio":
            usuarios[telefono] = {"estado": "esperando_especialidad"}
            enviar_respuesta(
                telefono, 
                f"Hola {nombre} 👋\n¿Qué especialidad necesitas?"
            )
            return {"status": "ok"}

        # =========================
        # 🟡 ESPECIALIDAD
        # =========================
        if estado["estado"] == "esperando_especialidad":
            usuarios[telefono] = {"estado": "esperando_fecha", "especialidad": texto}
            enviar_respuesta(telefono, "Perfecto 👍\nIndica la fecha (YYYY-MM-DD)")
            return {"status": "ok"}

        # =========================
        # 🔵 FECHA
        # =========================
        if estado["estado"] == "esperando_fecha":
            # Validar formato con Regex
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", texto):
                enviar_respuesta(telefono, "⚠️ Formato incorrecto. Ingresa: YYYY-MM-DD")
                return {"status": "ok"}
            usuarios[telefono]["estado"] = "esperando_hora"
            usuarios[telefono]["fecha"] = texto
            enviar_respuesta(telefono, "Ahora indica la hora (HH:MM)")
            return {"status": "ok"}

        # =========================
        # 🟣 HORA (AGENDAR)
        # =========================
        if estado["estado"] == "esperando_hora":
            # Llamada a tu herramienta para guardar en BD
            resultado = agendar_cita(
                db=db,
                nombre=nombre,
                telefono=telefono,
                especialidad=estado["especialidad"],
                fecha=estado["fecha"],
                hora=texto
            )

            enviar_respuesta(telefono, resultado)
            
            # Resetear flujo para el próximo chat
            usuarios[telefono] = {"estado": "inicio"}
            return {"status": "ok"}

        return {"status": "ok"}

    except Exception as e:
        print(f"❌ Error en el webhook: {e}")
        return {"status": "error"}
