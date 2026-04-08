import requests
from sqlalchemy.orm import Session
from models import Cita
from datetime import datetime

def agendar_cita(db: Session, nombre: str, telefono: str, especialidad: str, fecha: str, hora: str):
    """
    Recibe la conexión a la base de datos y guarda la cita de forma persistente.
    """
    try:
        # Convertimos los textos a formatos nativos de Fecha y Hora para la DB
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
        hora_obj = datetime.strptime(hora, "%H:%M").time()
        
        # Preparamos el registro
        nueva_cita = Cita(
            nombre=nombre,
            telefono=telefono,
            especialidad=especialidad,
            fecha=fecha_obj,
            hora=hora_obj,
            estado="agendada"
        )
        
        # Insertamos y guardamos (Commit)
        db.add(nueva_cita)
        db.commit()
        db.refresh(nueva_cita) # Refrescamos para obtener el ID autogenerado
        
        print(f"🗄️ [DB SUCCESS] Cita {nueva_cita.id} guardada en base de datos.")
        return f"✅ ¡Listo {nombre}! Tu cita de {especialidad} quedó agendada para el {fecha} a las {hora}."
        
    except Exception as e:
        db.rollback() # Si algo falla, deshacemos los cambios
        print(f"❌ [DB ERROR] Falló el guardado: {e}")
        return "⚠️ Hubo un problema interno guardando tu cita. Por favor, intenta de nuevo."


def enviar_respuesta(telefono: str, texto: str):
    """
    Envía la respuesta a nuestro puente local de Node.js (bridge.js)
    """
    print(f"📡 Enviando a Puente Local -> {telefono}: {texto}")
    
    # 🎯 Le pegamos a nuestro propio archivo bridge.js en el puerto 3000
    url = "http://127.0.0.1:3000/send"
    
    payload = {
        "number": telefono,
        "text": texto
    }
    
    try:
        respuesta = requests.post(url, json=payload)
        respuesta.raise_for_status() 
        print("✅ Mensaje entregado al Puente con éxito")
        return True
    except Exception as e:
        print(f"❌ Error conectando con el Puente: {e}")
        return False
