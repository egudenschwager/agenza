# main.py
import requests # <--- NECESARIO para hacer la llamada POST a WATI
from fastapi import FastAPI, Request, HTTPException
import json
import os
from datetime import datetime, date 
from typing import Dict, Any

# Importaciones de las funciones de la BD (asume que db_service está actualizado)
from db_service import consultar_disponibilidad, reservar_cita, buscar_citas_pendientes, cancelar_cita 

app = FastAPI()

# --- CONFIGURACIÓN PARA EL PILOTO ---
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "AGZ_TOKEN_DE_PRUEBA_123") 
MEDICO_PILOTO_ID = 1 
user_sessions: Dict[str, Any] = {} 


# --- FUNCIÓN DE ENVÍO REAL A LA API DE WATI (CON DEBUGGING) ---
def send_whatsapp_message(recipient_number, message_text):
    """
    FUNCIÓN REAL: Envía el mensaje al usuario a través de la API de WATI.
    Incluye logging detallado para diagnosticar fallos de Token/Endpoint.
    """
    WATI_BASE_ENDPOINT = os.getenv("WATI_ENDPOINT") # e.g., https://live-mt-server.wati.io/1043548
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN") # e.g., Bearer eyJhbGciOiJIUzI1NiI...
    
    if not WATI_BASE_ENDPOINT or not WATI_ACCESS_TOKEN:
        print("ERROR: Credenciales WATI no configuradas. Abortando envío.")
        return

    # Endpoint para mensajes de sesión (conversaciones iniciadas por el usuario)
    send_message_url = f"{WATI_BASE_ENDPOINT}/api/v1/sendSessionMessage"
    
    headers = {
        "Authorization": WATI_ACCESS_TOKEN, # Incluye el Bearer Token
        "Content-Type": "application/json"
    }
    
    payload = {
        # WATI prefiere el número sin el '+'
        "whatsappNumber": recipient_number.replace('+', ''), 
        "messageText": message_text
    }
    
    try:
        response = requests.post(send_message_url, headers=headers, json=payload, timeout=10)
        
        # --- LÍNEAS DE DEBUGGING CRÍTICAS ---
        print("--- DEBUG WATI START (Error en API de Envío) ---")
        print(f"URL Enviada: {send_message_url}")
        print(f"Status WATI: {response.status_code}") # Código de respuesta de la API de WATI
        print(f"Respuesta WATI (CUERPO): {response.text}") # JSON de error de WATI (Mensaje CLAVE)
        print("--- DEBUG WATI END ---")
        
        # Esto lanzará una excepción si WATI devuelve un error 4xx o 5xx (ej. 401 Unauthorized)
        response.raise_for_status() 
        
        print(f"ÉXITO API WATI: Mensaje enviado.")
        
    except requests.exceptions.RequestException as e:
        print(f"FALLO DE API WATI: No se pudo enviar la respuesta, error: {e}")
        # La aplicación devuelve 200 OK al webhook, pero el mensaje no se envía.


# --- FUNCIÓN AUXILIAR DE EXTRACCIÓN DEL MENSAJE (Sin cambios) ---
def extract_message_info(data):
    """Intenta extraer el número del remitente y el texto del mensaje entrante de la data de WATI/Meta."""
    try:
        if 'entry' in data and data['entry'][0].get('changes'):
            value = data['entry'][0]['changes'][0]['value']
            if 'messages' in value and value['messages']:
                message = value['messages'][0]
                if message.get('type') == 'text' and 'text' in message:
                    return {
                        'sender': message.get('from'),
                        'text': message['text'].get('body', '').strip() 
                    }
    except Exception as e:
        print(f"ERROR EN EXTRACCIÓN DE MENSAJE: {e}")
        return None
    return None


# --- ENDPOINT GET: Verificación del Webhook ---
@app.get("/webhook")
def verify_webhook(request: Request):
    try:
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("WEBHOOK VERIFICADO")
            return int(challenge)
        else:
            raise HTTPException(status_code=403, detail="Verification failed: Token mismatch")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# --- ENDPOINT POST: Recepción de Mensajes y Lógica de Diálogo ---
@app.post("/webhook")
async def handle_whatsapp_messages(request: Request):
    try:
        data = await request.json()
        message_info = extract_message_info(data)
        
        if not message_info:
            return {"status": "ignored"}

        sender_number = message_info['sender']
        text = message_info['text'].strip().lower()
        
        # --- Obtener y Estandarizar el Estado ---
        current_state = user_sessions.get(sender_number, {"state": "INICIO"}) 
        state_name = current_state.get("state")
        
        print(f"Mensaje de {sender_number} en estado {state_name}: {text}")
        
        response_text = ""
        
        # --- Lógica de la Máquina de Estados (Agendamiento y Cancelación) ---
        
        # ESTADO INICIO
        if state_name == "INICIO":
            if "agendar" in text or "hora" in text:
                response_text = "¡Hola! Por favor, indica la fecha (ej. 2025-11-06) para buscar disponibilidad:"
                user_sessions[sender_number] = {"state": "PREGUNTANDO_FECHA"} 
            elif "cancelar" in text or "anular" in text:
                response_text = "Para cancelar tu cita, por favor ingresa tu **RUT/RUN/DNI**."
                user_sessions[sender_number] = {"state": "PREGUNTANDO_CANCELAR_RUT"} 
            else:
                response_text = "Bienvenido a Agenza. Escribe 'agendar' o 'cancelar' para comenzar."

        # [El resto de la lógica de estados de Agendamiento y Cancelación se mantiene sin cambios]
        
        # --- Envío de Respuesta Final ---
        if response_text:
            send_whatsapp_message(sender_number, response_text)

        return {"status": "ok"}
    
    except Exception as e:
        print(f"Error procesando el mensaje: {e}")
        user_sessions[sender_number] = {"state": "INICIO"}
        # Usamos la función de envío real para informar del fallo al usuario
        send_whatsapp_message(sender_number, "Lo siento, hubo un fallo. Escribe 'agendar' o 'cancelar' para empezar de nuevo.")
        return {"status": "error"}, 200