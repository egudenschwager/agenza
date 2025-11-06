# cron_reminders.py
import os
# ¡Añadir 'datetime' a las importaciones de la librería 'datetime'!
from datetime import date, timedelta, datetime 
from db_service import obtener_citas_manana

# --- FUNCIÓN DE SIMULACIÓN DE ENVÍO ---
def send_whatsapp_reminder(recipient_number, message_text):
    """
    Función que simula el envío real del recordatorio.
    En un entorno de producción, esta función llamaría a la API de tu BSP.
    """
    print(f"--- [RECORDATORIO ENVIADO] ---")
    print(f"A: {recipient_number}")
    print(f"Mensaje: {message_text}\n")
    # Aquí iría el código real para la API de WhatsApp/BSP (ej. 360Dialog)

# --- FUNCIÓN PRINCIPAL DEL CRON JOB ---
# cron_reminders.py (Fragmento corregido)
# ...

# --- FUNCIÓN PRINCIPAL DEL CRON JOB ---
def run_reminder_job():
    """Ejecuta la tarea de buscar citas y enviar recordatorios."""
    # datetime.now() ya no dará error
    print(f"--- INICIANDO TRABAJO DE RECORDATORIO: {datetime.now()} ---") 
    
       # 1. Obtener la fecha de mañana
    manana = date.today() + timedelta(days=1)
    
    print(f"Buscando citas CONFIRMADAS para la fecha: {manana.strftime('%Y-%m-%d')}")
    
    # 2. Obtener citas de la BD
    citas_manana = obtener_citas_manana()
    
    if not citas_manana:
        print("No se encontraron citas para mañana. Finalizando.")
        return

    print(f"Se encontraron {len(citas_manana)} citas. Enviando recordatorios.")
    
    # 3. Enviar recordatorios
    for cita in citas_manana:
        nombre = cita['nombre_completo']
        telefono = cita['telefono_wsp']
        medico = cita['medico']
        hora = cita['hora_inicio']
        
        # Construir el mensaje
        mensaje = (
            f"¡Hola {nombre}! 👋\n"
            f"Te recordamos tu cita con el Dr. {medico} mañana {manana.strftime('%d-%m-%Y')} "
            f"a las {hora}. Por favor, sé puntual. ¡Te esperamos!"
        )
        
        send_whatsapp_reminder(telefono, mensaje)
        
    print("--- TRABAJO DE RECORDATORIO FINALIZADO ---")

if __name__ == "__main__":
    # Ejecutar el script
    run_reminder_job()