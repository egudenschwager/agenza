# main.py
import requests 
from fastapi import FastAPI, Request, HTTPException
import json
import os
from datetime import datetime, date 
from typing import Dict, Any, List

# Importar funciones de base de datos (usaremos las funciones de PostgreSQL)
from db_service import (
    obtener_lista_medicos,
    consultar_disponibilidad,
    reservar_cita,
    # Las funciones de cancelación también deberían actualizarse, pero omitimos por enfoque
)

# ================================
# CONFIG GLOBAL
# ================================
app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "AGZ_TOKEN_DE_PRUEBA_123") 
# MEDICO_PILOTO_ID ya no es fijo, se define en el estado.
user_sessions: Dict[str, Any] = {} 

# --- FUNCIÓN AUXILIAR DE ENVÍO DE PLANTILLA (SIMPLIFICADA) ---
# Esta función debe ser actualizada para usar el API Key de Ycloud.
def send_template_message(recipient_number: str, template_name: str, parameters: List[Dict[str, str]] = []):
    """
    Simulación de envío de Plantilla de WATI/Ycloud. 
    Aquí iría el código real de la API de Ycloud/Twilio/360Dialog.
    """
    print(f"\n>>>> ENVIANDO PLANTILLA: {template_name} a {recipient_number}")
    print(f"PAYLOAD: {parameters}")
    # Nota: En producción, usarías aquí la Clave API de Ycloud para el envío real.
    # El código debe ser ajustado al formato JSON exacto de Ycloud.

# --- FUNCIÓN AUXILIAR DE EXTRACCIÓN DEL MENSAJE (Sin cambios) ---
def extract_message_info(data):
    # Función que extrae el mensaje de entrada (waId, text)
    if "type" in data and data.get("type") == "text":
        return {
            "sender": "+" + data.get("waId", ""),
            "text": data.get("text", "").strip()
        }
    return None

# [Código de verificación GET omitido por espacio]

# ======================================================
# ✅ ENDPOINT POST – RECEPCIÓN DE MENSAJES (MÁQUINA DE ESTADOS MULTI-MÉDICO)
# ======================================================
@app.post("/webhook")
async def handle_whatsapp_messages(request: Request):
    data = await request.json()
    info = extract_message_info(data)
    
    if not info:
        return {"status": "ignored"}

    sender = info["sender"]
    text = info["text"].lower().strip()
    state = user_sessions.get(sender, {"state": "INICIO"})["state"]
    
    # Asumimos un nombre temporal para la plantilla de bienvenida.
    nombre_paciente_temp = "Estimado cliente"
    
    # ===========================================
    # ✅ LÓGICA DE ESTADOS
    # ===========================================

    # --- ESTADO INICIO ---
    if state == "INICIO":
        # Llamamos a la BD para obtener la lista de médicos (Nuevo paso)
        medicos = obtener_lista_medicos()
        
        if not medicos:
            response_text = "Lo sentimos, no hay médicos disponibles en este momento."
            send_template_message(sender, "agenza_bienvenida", [{"name": "1", "value": response_text}])
            return {"status": "no_medicos"}

        # Construir el mensaje de selección (ejemplo de lista)
        opciones_medicos = "\n".join([f"*{m['id_medico']}*: {m['nombre']} ({m['especialidad']})" for m in medicos])
        
        menu_text = f"¡Hola {nombre_paciente_temp}! Soy Agenza. Por favor, selecciona el ID del médico con el que deseas agendar:\n\n{opciones_medicos}"
        
        # Almacenar la lista de médicos en la sesión y pasar al nuevo estado
        user_sessions[sender] = {"state": "ESPERANDO_SELECCION_MEDICO", "medicos": {str(m['id_medico']): m for m in medicos}}

        # Enviamos la plantilla de bienvenida con el menú
        send_template_message(sender, "agenza_bienvenida", [{"name": "1", "value": menu_text}])
        return {"status": "menu_medicos_enviado"}

    # --- NUEVO ESTADO: ESPERANDO SELECCIÓN DE MÉDICO ---
    elif state == "ESPERANDO_SELECCION_MEDICO":
        medicos_disponibles = user_sessions[sender].get("medicos", {})
        
        # Verificar si la entrada del usuario es un ID de médico válido
        if text in medicos_disponibles:
            medico_seleccionado = medicos_disponibles[text]
            
            # Guardamos el ID del médico y pasamos a preguntar la fecha
            user_sessions[sender]['medico_id'] = medico_seleccionado['id_medico']
            user_sessions[sender]['medico_nombre'] = medico_seleccionado['nombre']
            user_sessions[sender]['state'] = "PREGUNTANDO_FECHA"
            
            response_text = f"Has seleccionado a {medico_seleccionado['nombre']}. Por favor, indica la fecha (AAAA-MM-DD) para buscar su disponibilidad."
            send_template_message(sender, "agenza_bienvenida", [{"name": "1", "value": response_text}])
            return {"status": "medico_seleccionado"}
        
        # Si la selección es inválida
        response_text = "ID de médico inválido. Por favor, envía solo el número del médico que deseas (ej. 101)."
        send_template_message(sender, "agenza_bienvenida", [{"name": "1", "value": response_text}])
        return {"status": "seleccion_invalida"}


    # --- RESTO DE LOS ESTADOS (PREGUNTANDO_FECHA, etc.) ---
    # Los estados PREGUNTANDO_FECHA y siguientes ahora deben usar user_sessions[sender]['medico_id']
    # en lugar de MEDICO_PILOTO_ID. Por ejemplo:
    elif state == "PREGUNTANDO_FECHA":
        medico_id = user_sessions[sender].get('medico_id')
        # Lógica de fecha...
        # Llamada a la BD: consultar_disponibilidad(medico_id, fecha_busqueda)
        pass # Continúa la lógica del agendamiento...

    return {"status": "ok"}