# main.py
import requests 
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


# --- FUNCIÓN DE ENVÍO REAL A LA API DE WATI (CON CORRECCIÓN DE ENDPOINT) ---
def send_whatsapp_message(recipient_number, message_text):
    """
    FUNCIÓN REAL: Envía el mensaje al usuario a través de la API de WATI.
    Utiliza el endpoint FINAL CORREGIDO para evitar el error 404.
    """
    # 🚨 NOTA: Se usan WATI_ENDPOINT_BASE y WATI_ACCOUNT_ID
    WATI_BASE_ENDPOINT = os.getenv("WATI_ENDPOINT_BASE") 
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN") 
    WATI_ACCOUNT_ID = os.getenv("WATI_ACCOUNT_ID") # <-- SE NECESITA ESTA VARIABLE
    
    if not WATI_BASE_ENDPOINT or not WATI_ACCESS_TOKEN or not WATI_ACCOUNT_ID:
        print("ERROR: Credenciales WATI no configuradas correctamente. Abortando envío.")
        return

    # CONSTRUCCIÓN FINAL: BASE / ACCOUNT_ID / api/v1 / sendSessionMessage
    send_message_url = f"{WATI_BASE_ENDPOINT}/{WATI_ACCOUNT_ID}/api/v1/sendSessionMessage" 
    
    headers = {
        "Authorization": WATI_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }
    
    payload = {
        "whatsappNumber": recipient_number.replace('+', ''), 
        "messageText": message_text
    }
    
    try:
        response = requests.post(send_message_url, headers=headers, json=payload, timeout=10)
        
        # --- DEBUGGING CRÍTICO ---
        print("--- DEBUG WATI START (DIAGNÓSTICO AUTENTICACIÓN) ---")
        print(f"URL FINAL ENVIADA: {send_message_url}")
        print(f"Status WATI: {response.status_code}") 
        print(f"Respuesta WATI (CUERPO): {response.text}") 
        print("--- DEBUG WATI END ---")
        
        response.raise_for_status() 
        print(f"ÉXITO API WATI: Mensaje enviado.")
        
    except requests.exceptions.RequestException as e:
        print(f"FALLO DE API WATI: No se pudo enviar la respuesta, error: {e}")


# --- FUNCIÓN AUXILIAR DE EXTRACCIÓN DEL MENSAJE (CORRECCIÓN CRÍTICA PARA WATI) ---
def extract_message_info(data):
    """Extrae la información del mensaje entrante del JSON de WATI."""
    # Este es el formato directo que WATI envía
    if 'type' in data and data.get('type') == 'text' and 'text' in data:
        return {
            'sender': '+' + data.get('waId', ''),
            'text': data.get('text', '').strip()
        }
    elif 'entry' in data:
        return None # Ignorar estados y otros eventos de Meta
    return None


# --- ENDPOINT GET: Verificación del Webhook ---
@app.get("/webhook")
def verify_webhook(request: Request):
    """Responde al GET de WATI para verificar la URL y el Token."""
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
        
        response_text = ""
        
        # --- Lógica de la Máquina de Estados ---
        
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

        # [El resto de la lógica de Agendamiento y Cancelación (omitido por espacio)]
        
        # --- Envío de Respuesta Final ---
        if response_text:
            send_whatsapp_message(sender_number, response_text)

        return {"status": "ok"}
    
    except Exception as e:
        print(f"Error procesando el mensaje: {e}")
        user_sessions[sender_number] = {"state": "INICIO"}
        send_whatsapp_message(sender_number, "Lo siento, hubo un fallo. Escribe 'agendar' o 'cancelar' para empezar de nuevo.")
        return {"status": "error"}, 200
