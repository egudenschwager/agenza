# db_service.py
import psycopg2
from psycopg2 import extras
from psycopg2 import pooling # Se mantiene pooling si se usa
import os
from datetime import date, timedelta
from typing import List, Dict, Any

# ============================================
# ✅ CONEXIÓN GLOBAL A POSTGRESQL (SUPABASE)
# ============================================

# La URI se lee directamente de la variable de entorno de Railway/Supabase
SUPABASE_URI = os.getenv("SUPABASE_URI")

# Nota: En entornos como Railway, a menudo es mejor usar psycopg2.connect(SUPABASE_URI) 
# directamente dentro de cada función, ya que el pooling lo maneja el proveedor cloud.
# Mantenemos la lógica de conexión directa por la URL para evitar problemas de configuración.


def get_connection():
    """Obtiene una nueva conexión de PostgreSQL usando la URI de Supabase."""
    if not SUPABASE_URI:
        raise ValueError("SUPABASE_URI no está configurada.")
    return psycopg2.connect(SUPABASE_URI)


# ============================================
# ✅ 1. LISTAR MÉDICOS (Multi-Médico)
# ============================================

def obtener_lista_medicos() -> List[Dict[str, Any]]:
    """
    Obtiene la lista de médicos disponibles para el menú inicial.
    """
    conn = None
    try:
        conn = get_connection()
        # Usamos DictCursor para obtener resultados como diccionarios (similar a dictionary=True en MySQL)
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)

        query = """
        SELECT 
            id_medico, 
            nombre, 
            especialidad 
        FROM 
            medicos
        ORDER BY 
            especialidad, nombre;
        """
        cursor.execute(query)
        return cursor.fetchall()

    except Exception as e:
        print("❌ Error en obtener_lista_medicos:", e)
        return []

    finally:
        if conn:
            cursor.close()
            conn.close()


# ============================================
# ✅ 2. CONSULTAR DISPONIBILIDAD
# ============================================

def consultar_disponibilidad(id_medico: int, fecha: date) -> List[Dict[str, Any]]:
    """
    Retorna una lista de bloques de horas DISPONIBLES para un médico en una fecha.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)

        query = """
        SELECT 
            id_bloque, 
            TO_CHAR(hora_inicio, 'HH24:MI') AS hora_str 
        FROM 
            bloques_disponibles 
        WHERE 
            medico_id = %s 
            AND fecha = %s 
            AND estado = 'DISPONIBLE'
        ORDER BY 
            hora_inicio ASC;
        """
        cursor.execute(query, (id_medico, fecha))
        return cursor.fetchall()

    except Exception as e:
        print("❌ Error en consultar_disponibilidad:", e)
        return []

    finally:
        if conn:
            cursor.close()
            conn.close()


# ============================================
# ✅ 3. RESERVAR UNA CITA (TRANSACCIÓN ATÓMICA)
# ============================================

def reservar_cita(id_bloque: int, rut: str, nombre_completo: str, telefono: str, id_medico: int) -> bool:
    """
    Ejecuta una transacción ATÓMICA: 1. Inserta/Actualiza Paciente. 
    2. Reserva el bloque (solo si está 'DISPONIBLE'). 3. Registra la cita.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1. Insertar/Actualizar Paciente (ON CONFLICT DO UPDATE)
        # Esto es crucial para manejar pacientes recurrentes
        cursor.execute("""
            INSERT INTO pacientes (rut, nombre_completo, telefono_wsp)
            VALUES (%s, %s, %s)
            ON CONFLICT (rut) DO UPDATE
            SET nombre_completo = EXCLUDED.nombre_completo, telefono_wsp = EXCLUDED.telefono_wsp
            RETURNING id_paciente;
        """, (rut, nombre_completo, telefono))
        paciente_id = cursor.fetchone()[0]

        # 2. Intentar reservar el Bloque (Bloqueo Optimista: solo si es DISPONIBLE)
        cursor.execute("""
            UPDATE bloques_disponibles
            SET estado = 'RESERVADO', paciente_id = %s
            WHERE id_bloque = %s AND estado = 'DISPONIBLE';
        """, (paciente_id, id_bloque))

        if cursor.rowcount == 0:
            conn.rollback()  # Bloque ya fue tomado, revertir paso 1
            return False

        # 3. Registrar la Cita en el historial
        cursor.execute("""
            INSERT INTO citas_agendadas (bloque_id, paciente_id, medico_id, estado_cita)
            VALUES (%s, %s, %s, 'CONFIRMADA');
        """, (id_bloque, paciente_id, id_medico))

        conn.commit()
        return True

    except Exception as e:
        print("❌ Error en reservar_cita:", e)
        if conn:
            conn.rollback()
        return False

    finally:
        if conn:
            cursor.close()
            conn.close()

# --- NOTA: Las funciones de cancelación (4 y 5) también deben ser actualizadas 
# para usar el esquema bloques_disponibles/citas_agendadas de PostgreSQL.