# db_service.py
import psycopg2
from psycopg2 import extras
import os
from datetime import date, timedelta # <-- Importación de timedelta
from typing import List, Dict, Any

# La URI se lee de la variable de entorno (Pooler de Supabase)
SUPABASE_URI = os.getenv("SUPABASE_URI")

# --- FUNCIÓN 1: CONSULTAR DISPONIBILIDAD ---
def consultar_disponibilidad(medico_id: int, fecha_busqueda: date) -> List[Dict[str, Any]]:
    """Consulta los slots DISPONIBLES para un médico en una fecha específica."""
    if not SUPABASE_URI:
        print("ERROR: SUPABASE_URI no está configurada.")
        return []

    query = """
    SELECT 
        id_bloque, 
        TO_CHAR(hora_inicio, 'HH24:MI') AS hora_inicio_str 
    FROM 
        bloques_disponibles
    WHERE 
        medico_id = %s 
    AND 
        fecha = %s 
    AND 
        estado = 'DISPONIBLE'
    ORDER BY 
        hora_inicio;
    """
    conn = None
    horas_disponibles = []
    
    try:
        conn = psycopg2.connect(SUPABASE_URI)
        cur = conn.cursor(cursor_factory=extras.RealDictCursor) 
        cur.execute(query, (medico_id, fecha_busqueda))
        horas_disponibles = cur.fetchall()
        cur.close()
    except Exception as error:
        print(f"Error al conectar o consultar la BD: {error}")
    finally:
        if conn is not None:
            conn.close()
    
    return horas_disponibles

# --- FUNCIÓN 2: RESERVAR CITA (TRANSACCIÓN ATÓMICA) ---
def reservar_cita(bloque_id: int, rut: str, nombre_completo: str, telefono_wsp: str, medico_id: int) -> bool:
    """Ejecuta una transacción atómica para insertar/obtener paciente y reservar el bloque."""
    if not SUPABASE_URI:
        return False

    conn = None
    try:
        conn = psycopg2.connect(SUPABASE_URI)
        cur = conn.cursor()
        
        # PASO A: Insertar o actualizar el paciente y obtener su ID
        cur.execute("""
            INSERT INTO pacientes (rut, nombre_completo, telefono_wsp)
            VALUES (%s, %s, %s)
            ON CONFLICT (rut) DO UPDATE
            SET nombre_completo = EXCLUDED.nombre_completo, telefono_wsp = EXCLUDED.telefono_wsp
            RETURNING id_paciente;
        """, (rut, nombre_completo, telefono_wsp))
        paciente_id = cur.fetchone()[0]
        
        # PASO B: Intentar reservar el bloque (CRÍTICO: Solo si está DISPONIBLE)
        cur.execute("""
            UPDATE bloques_disponibles
            SET estado = 'RESERVADO', paciente_id = %s
            WHERE id_bloque = %s AND estado = 'DISPONIBLE'
            RETURNING id_bloque;
        """, (paciente_id, bloque_id))
        
        if cur.rowcount == 0:
            conn.rollback() 
            return False 

        # PASO C: Registrar la cita agendada
        cur.execute("""
            INSERT INTO citas_agendadas (bloque_id, paciente_id, medico_id)
            VALUES (%s, %s, %s);
        """, (bloque_id, paciente_id, medico_id))

        # ÉXITO: Confirmar todos los cambios
        conn.commit()
        return True

    except Exception as error:
        if conn:
            conn.rollback() 
        print(f"Error fatal durante la reserva. Transacción revertida: {error}")
        return False

    finally:
        if conn is not None:
            conn.close()

# --- FUNCIÓN 3: BUSCAR CITAS PENDIENTES ---
def buscar_citas_pendientes(rut: str) -> List[Dict[str, Any]]:
    """Busca todas las citas CONFIRMADAS y FUTURAS asociadas a un RUT para la cancelación."""
    if not SUPABASE_URI:
        return []

    query = """
    SELECT 
        CA.id_cita, 
        M.nombre AS medico, 
        BD.fecha, 
        TO_CHAR(BD.hora_inicio, 'HH24:MI') AS hora_inicio,
        BD.id_bloque 
    FROM 
        citas_agendadas CA
    JOIN 
        pacientes P ON CA.paciente_id = P.id_paciente
    JOIN
        medicos M ON CA.medico_id = M.id_medico
    JOIN
        bloques_disponibles BD ON CA.bloque_id = BD.id_bloque
    WHERE 
        P.rut = %s
    AND 
        BD.fecha >= CURRENT_DATE 
    AND
        CA.estado_cita = 'CONFIRMADA'
    ORDER BY
        BD.fecha, BD.hora_inicio;
    """
    conn = None
    citas = []
    
    try:
        conn = psycopg2.connect(SUPABASE_URI)
        cur = conn.cursor(cursor_factory=extras.RealDictCursor) 
        cur.execute(query, (rut,))
        citas = cur.fetchall()
        cur.close()
    except Exception as error:
        print(f"Error al buscar citas: {error}")
    finally:
        if conn is not None:
            conn.close()
            
    return citas

# --- FUNCIÓN 4: CANCELAR CITA (TRANSACCIÓN ATÓMICA DE REVERSIÓN) ---
def cancelar_cita(cita_id: int, bloque_id: int) -> bool:
    """Ejecuta una transacción atómica para cancelar la cita y liberar el bloque."""
    if not SUPABASE_URI:
        return False

    conn = None
    try:
        conn = psycopg2.connect(SUPABASE_URI)
        cur = conn.cursor()
        
        # PASO A: Actualizar el estado en la tabla de citas (Registro Histórico)
        cur.execute("""
            UPDATE citas_agendadas
            SET estado_cita = 'CANCELADA'
            WHERE id_cita = %s AND estado_cita = 'CONFIRMADA';
        """, (cita_id,))
        
        if cur.rowcount == 0:
            conn.rollback() 
            return False
            
        # PASO B: Liberar el bloque de tiempo (Inventario): Volver a DISPONIBLE y NULL paciente_id
        cur.execute("""
            UPDATE bloques_disponibles
            SET estado = 'DISPONIBLE', paciente_id = NULL
            WHERE id_bloque = %s AND estado = 'RESERVADO';
        """, (bloque_id,))
        
        # ÉXITO: Confirmar todos los cambios
        conn.commit()
        return True

    except Exception as error:
        if conn:
            conn.rollback() 
        print(f"Error grave durante la cancelación. Transacción revertida: {error}")
        return False

    finally:
        if conn is not None:
            conn.close()

# --- FUNCIÓN 5: OBTENER CITAS PARA MAÑANA (RECORDATORIOS) ---
def obtener_citas_manana() -> List[Dict[str, Any]]:
    """Busca todas las citas CONFIRMADAS para el día de mañana."""
    if not SUPABASE_URI:
        print("ERROR: SUPABASE_URI no está configurada.")
        return []

    # Calcular la fecha de mañana
    manana = date.today() + timedelta(days=1)

    query = """
    SELECT 
        P.nombre_completo, 
        P.telefono_wsp,
        M.nombre AS medico, 
        TO_CHAR(BD.hora_inicio, 'HH24:MI') AS hora_inicio,
        BD.fecha
    FROM 
        citas_agendadas CA
    JOIN 
        pacientes P ON CA.paciente_id = P.id_paciente
    JOIN
        medicos M ON CA.medico_id = M.id_medico
    JOIN
        bloques_disponibles BD ON CA.bloque_id = BD.id_bloque
    WHERE 
        BD.fecha = %s
    AND 
        CA.estado_cita = 'CONFIRMADA';
    """
    conn = None
    citas = []
    
    try:
        conn = psycopg2.connect(SUPABASE_URI)
        cur = conn.cursor(cursor_factory=extras.RealDictCursor) 
        cur.execute(query, (manana,))
        citas = cur.fetchall()
        cur.close()
    except Exception as error:
        print(f"Error al buscar citas para mañana: {error}")
    finally:
        if conn is not None:
            conn.close()
            
    return citas