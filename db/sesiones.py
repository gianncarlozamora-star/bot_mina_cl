import json
from db.conexion import ejecutar
from config import hora_peru, SESION_TIMEOUT_MIN

def obtener_sesion(usuario_id: int) -> dict | None:
    row = ejecutar(
        """SELECT id, flujo_activo, paso_actual,
                  datos_parciales::text, sondaje_context
           FROM sesiones_bot
           WHERE usuario_id = %s AND activa = TRUE
           ORDER BY iniciada_en DESC LIMIT 1""",
        (usuario_id,), fetchone=True
    )
    print(f"[SESION] Buscando usuario={usuario_id} resultado={row}")
    if not row:
        return None
    try:
        datos = json.loads(row[3]) if row[3] else {}
    except:
        datos = {}
    return {
        "id":    row[0],
        "flujo": row[1],
        "paso":  row[2],
        "datos": datos,
        "sondaje_context": row[4],
    }

def crear_sesion(usuario_id: int, flujo: str, paso: str = "inicio") -> int:
    cerrar_sesion(usuario_id)
    row = ejecutar(
        """INSERT INTO sesiones_bot 
               (usuario_id, flujo_activo, paso_actual, datos_parciales, activa)
           VALUES (%s, %s, %s, '{}'::jsonb, TRUE)
           RETURNING id""",
        (usuario_id, flujo, paso), fetchone=True
    )
    print(f"[SESION] Creada: usuario={usuario_id} flujo={flujo} row={row}")
    return row[0] if row else None

def actualizar_sesion(sesion_id: int, paso: str,
                       datos: dict, sondaje_context: str = None):
    ejecutar(
        """UPDATE sesiones_bot
           SET paso_actual = %s,
               datos_parciales = %s::jsonb,
               sondaje_context = COALESCE(%s, sondaje_context),
               actualizada_en = NOW()
           WHERE id = %s""",
        (paso, json.dumps(datos, ensure_ascii=False, default=str),
         sondaje_context, sesion_id)
    )

def cerrar_sesion(usuario_id: int):
    ejecutar(
        "UPDATE sesiones_bot SET activa=FALSE WHERE usuario_id=%s AND activa=TRUE",
        (usuario_id,)
    )

def renovar_sesion(sesion_id: int):
    ejecutar(
        "UPDATE sesiones_bot SET actualizada_en=NOW() WHERE id=%s",
        (sesion_id,)
    )
