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


# --- FUNCIÓN DE ENVÍO REAL A LA API DE WATI (CON CORRECCIÓN DE ENDPOINT Y DEBUGGING) ---
def send_whatsapp_message(recipient_number, message_text):
    """
    FUNCIÓN REAL: Envía el mensaje al usuario a través de la API de WATI.
    Utiliza el endpoint exacto para evitar errores 404/Autenticación.
    """
    # 🚨 NOTA: Se debe usar WATI_ENDPOINT_BASE para la URL sin la ruta /api/v1/
    WATI_BASE_ENDPOINT = os.getenv("WATI_ENDPOINT_BASE") 
    WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN") 
    
    if not WATI_BASE_ENDPOINT or not WATI_ACCESS_TOKEN:
        print("ERROR: Credenciales WATI no configuradas. Abortando envío.")
        return

    # Construye la URL correcta con el path /api/v1/
    send_message_url = f"{WATI_BASE_ENDPOINT}/api/v1/sendSessionMessage"
    
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
        
        # --- LÍNEAS DE DEBUGGING CRÍTICAS ---
        print("--- DEBUG WATI START (DIAGNÓSTICO AUTENTICACIÓN) ---")
        print(f"URL FINAL ENVIADA: {send_message_url}")
        print(f"Status WATI: {response.status_code}") 
        print(f"Respuesta WATI (CUERPO): {response.text}") 
        print("--- DEBUG WATI END ---")
        
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
    """Procesa mensajes POST y maneja la Máquina de Estados de Agenza."""
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
        
        # print(f"Mensaje de {sender_number} en estado {state_name}: {text}") # Línea de diagnóstico de estado
        
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

        # --- ESTADOS DE AGENDAMIENTO ---
        elif state_name == "PREGUNTANDO_FECHA":
            try:
                fecha_busqueda = datetime.strptime(text, '%Y-%m-%d').date()
                horas = consultar_disponibilidad(MEDICO_PILOTO_ID, fecha_busqueda)
                if horas:
                    opciones = {}
                    display_list = []
                    for h in horas:
                        opciones[str(h['id_bloque'])] = h 
                        display_list.append(f"*{h['id_bloque']}*: {h['hora_inicio_str']}")
                    response_text = f"Horas disponibles el {text}:\n\n" + "\n".join(display_list) + "\n\nResponde con el *ID de bloque* que deseas reservar."
                    user_sessions[sender_number] = {"state": "PREGUNTANDO_BLOQUE", "opciones": opciones}
                else:
                    response_text = "No hay horas disponibles para esa fecha. ¿Puedes intentar con otra?"
            except ValueError:
                response_text = "El formato de la fecha es incorrecto. Usa AAAA-MM-DD (ej. 2025-11-06)."

        elif state_name == "PREGUNTANDO_BLOQUE":
            opciones_validas = current_state.get('opciones', {})
            if text in opciones_validas:
                bloque_seleccionado = opciones_validas[text]
                user_sessions[sender_number] = {"state": "PREGUNTANDO_RUT", "bloque_id": bloque_seleccionado['id_bloque']}
                response_text = f"Has seleccionado la hora {bloque_seleccionado['hora_inicio_str']}. Por favor, envíame tu **RUT/RUN/DNI**."
            else:
                response_text = "Opción inválida. Envía el *ID del bloque* que deseas."

        elif state_name == "PREGUNTANDO_RUT":
            if len(text) >= 9 and "-" in text:
                rut = text.upper()
                user_sessions[sender_number]['rut'] = rut
                user_sessions[sender_number]['state'] = "PREGUNTANDO_NOMBRE"
                response_text = "Gracias. Ahora, por favor, escribe tu **Nombre Completo**."
            else:
                response_text = "Formato de RUT/DNI incorrecto. Intenta nuevamente (ej. 12345678-9)."
                
        elif state_name == "PREGUNTANDO_NOMBRE":
            if len(text) > 5 and ' ' in text: 
                nombre = text
                bloque_id = current_state['bloque_id']
                rut = current_state['rut']
                telefono_wsp = sender_number 
                
                if reservar_cita(bloque_id, rut, nombre, telefono_wsp, MEDICO_PILOTO_ID):
                    response_text = f"✅ ¡Listo, {nombre}! Tu cita ha sido confirmada. ¡Gracias por usar Agenza!"
                else:
                    response_text = "❌ ¡Oh no! Alguien reservó ese horario justo ahora. Por favor, escribe 'agendar' para buscar otra hora."
                    
                user_sessions[sender_number] = {"state": "INICIO"} 

            else:
                response_text = "Por favor, escribe tu nombre y apellido completo."

        # --- ESTADOS DE CANCELACIÓN ---
        elif state_name == "PREGUNTANDO_CANCELAR_RUT":
            if len(text) >= 9 and "-" in text:
                rut = text.upper()
                citas_pendientes = buscar_citas_pendientes(rut)
                
                if citas_pendientes:
                    opciones_citas = {}
                    display_list = ["Citas encontradas:\n"]
                    for cita in citas_pendientes:
                        opciones_citas[str(cita['id_cita'])] = cita
                        display_list.append(f"*{cita['id_cita']}*: Dr. {cita['medico']} el {cita['fecha']} a las {cita['hora_inicio']}")

                    response_text = "\n".join(display_list) + "\n\nResponde con el *ID de Cita* que deseas **CANCELAR**."
                    user_sessions[sender_number] = {"state": "PREGUNTANDO_CANCELAR_CITA", "citas": opciones_citas}
                else:
                    response_text = "No encontramos citas confirmadas a tu nombre. Escribe 'agendar' para reservar."
                    user_sessions[sender_number] = {"state": "INICIO"}

            else:
                response_text = "Formato de RUT/DNI incorrecto. Ingresa el RUT nuevamente."


        elif state_name == "PREGUNTANDO_CANCELAR_CITA":
            cita_id_str = text
            opciones_citas = current_state.get('citas', {})
            
            if cita_id_str in opciones_citas:
                cita_seleccionada = opciones_citas[cita_id_str]
                
                cita_id_int = int(cita_id_str)
                bloque_id_int = cita_seleccionada['id_bloque']
                
                if cancelar_cita(cita_id_int, bloque_id_int):
                    response_text = f"✅ Tu cita con el Dr. {cita_seleccionada['medico']} ha sido **CANCELADA** y el horario liberado. ¡Gracias!"
                else:
                    response_text = "❌ No pudimos completar la cancelación. Por favor, contacta a la clínica."
                    
                user_sessions[sender_number] = {"state": "INICIO"}
            else:
                response_text = "Opción inválida. Responde con el ID de Cita correcto."


        # --- Envío de Respuesta Final ---
        if response_text:
            send_whatsapp_message(sender_number, response_text)

        return {"status": "ok"}
    
    except Exception as e:
        print(f"Error procesando el mensaje: {e}")
        user_sessions[sender_number] = {"state": "INICIO"}
        send_whatsapp_message(sender_number, "Lo siento, hubo un fallo. Escribe 'agendar' o 'cancelar' para empezar de nuevo.")
        return {"status": "error"}, 200