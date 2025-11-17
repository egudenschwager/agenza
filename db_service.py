# db_service.py → VERSIÓN 2025 PRODUCCIÓN (FastAPI + Supabase + Railway)

import os
from psycopg_pool import ConnectionPool
from contextlib import contextmanager
from datetime import date
from typing import List, Dict, Any

# ============================================
# CONEXIÓN CON POOL MODERNO (psycopg 3)
# ============================================

DATABASE_URL = os.getenv("SUPABASE_URI")  # o DATABASE_URL, como prefieras

if not DATABASE_URL:
    raise ValueError("Falta SUPABASE_URI en variables de entorno")

# Pool global (psycopg 3 – el estándar actual)
pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=2,
    max_size=20,
    timeout=30.0,
    kwargs={
        "connect_timeout": 10,
        "options": "-c statement_timeout=20000"
    }
)

@contextmanager
def get_db():
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


# ============================================
# 1. LISTAR MÉDICOS
# ============================================

def obtener_lista_medicos() -> List[Dict[str, Any]]:
    try:
        with get_db() as conn:
            with conn.cursor(row_factory=dict_row) as cur:  # dict_row viene de psycopg
                cur.execute("""
                    SELECT id_medico, nombre, especialidad 
                    FROM medicos 
                    ORDER BY especialidad, nombre;
                """)
                return cur.fetchall()
    except Exception as e:
        print("Error obtener_lista_medicos:", e)
        return []


# ============================================
# 2. CONSULTAR DISPONIBILIDAD
# ============================================

def consultar_disponibilidad(id_medico: int, fecha: date) -> List[Dict[str, Any]]:
    try:
        with get_db() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT id_bloque, TO_CHAR(hora_inicio, 'HH24:MI') AS hora_str 
                    FROM bloques_disponibles 
                    WHERE medico_id = %s AND fecha = %s AND estado = 'DISPONIBLE'
                    ORDER BY hora_inicio;
                """, (id_medico, fecha))
                return cur.fetchall()
    except Exception as e:
        print("Error consultar_disponibilidad:", e)
        return []


# ============================================
# 3. RESERVAR CITA (TRANSACCIÓN SEGURA)
# ============================================

from psycopg.rows import dict_row  # ← IMPORTANTE: agregar esta línea al inicio

def reservar_cita(id_bloque: int, rut: str, nombre_completo: str, telefono: str, id_medico: int) -> bool:
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # 1. Paciente (upsert)
                cur.execute("""
                    INSERT INTO pacientes (rut, nombre_completo, telefono_wsp)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (rut) DO UPDATE SET
                        nombre_completo = EXCLUDED.nombre_completo,
                        telefono_wsp = EXCLUDED.telefono_wsp
                    RETURNING id_paciente;
                """, (rut, nombre_completo, telefono))
                paciente_id = cur.fetchone()[0]

                # 2. Reservar bloque (solo si sigue disponible)
                cur.execute("""
                    UPDATE bloques_disponibles
                    SET estado = 'RESERVADO', paciente_id = %s
                    WHERE id_bloque = %s AND estado = 'DISPONIBLE';
                """, (paciente_id, id_bloque))

                if cur.rowcount == 0:
                    conn.rollback()
                    return False

                # 3. Registrar cita
                cur.execute("""
                    INSERT INTO citas_agendadas (bloque_id, paciente_id, medico_id, estado_cita)
                    VALUES (%s, %s, %s, 'CONFIRMADA');
                """, (id_bloque, paciente_id, id_medico))

                conn.commit()
                return True

    except Exception as e:
        print("Error reservar_cita:", e)
        if 'conn' in locals():
            conn.rollback()
        return False