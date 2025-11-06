# test_db.py
import os
from datetime import date
from db_service import consultar_disponibilidad

# --- PARÁMETROS DE PRUEBA ---
MEDICO_ID_PRUEBA = 1
# La fecha de uno de los slots disponibles que insertaste: 2025-11-06
FECHA_PRUEBA = date(2025, 11, 6) 

print("--- Iniciando prueba de conexión a Supabase ---")

# 1. Verificar la URI
uri = os.getenv("SUPABASE_URI")
if not uri:
    print("ERROR: La variable SUPABASE_URI no está definida. Por favor, define la variable de entorno primero.")
    exit()
print(f"URI cargada.")

# 2. Llamar a la función crítica
print(f"Buscando disponibilidad para Médico {MEDICO_ID_PRUEBA} en {FECHA_PRUEBA}...")

horas_disponibles = consultar_disponibilidad(MEDICO_ID_PRUEBA, FECHA_PRUEBA)

# 3. Mostrar el resultado
if horas_disponibles:
    print("\n✅ ÉXITO: Horas encontradas en Supabase:")
    for hora in horas_disponibles:
        print(f"  - Bloque {hora['id_bloque']} a las {hora['hora_inicio_str']}")
else:
    print("\n❌ FALLO EN LA CONEXIÓN/CONSULTA. Revisa la contraseña o los datos de prueba.")

print("\n--- Prueba de conexión finalizada ---")