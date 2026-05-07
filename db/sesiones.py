import json
from db.conexion import ejecutar
from config import hora_peru, SESION_TIMEOUT_MIN

def obtener_sesion(usuario_id: int) -> dict | None:
    row = ejecutar(
        """SELECT id, flujo_activo, paso_actual, datos_parciales, sondaje_context
           FROM sesiones_bot
           WHERE usuario_id = %s AND activa = TRUE
           ORDER BY iniciada_en DESC LIMIT 1""",
        (usuario_id,), fetchone=True
    )
    if not row:
        return None
    datos = row[3]
    if isinstance(datos, str):
        import json
        datos = json.loads(datos)
    return {
        "id":              row[0],
        "flujo":           row[1],
        "paso":            row[2],
        "datos":           datos or {},
        "sondaje_context": row[4],
    }

def crear_sesion(usuario_id: int, flujo: str, paso: str = "inicio") -> int:
    """Cierra sesión anterior y crea una nueva. Retorna el id."""
    cerrar_sesion(usuario_id)
    from datetime import timedelta
    expira = hora_peru() + timedelta(minutes=SESION_TIMEOUT_MIN)
    row = ejecutar(
        """INSERT INTO sesiones_bot (usuario_id, flujo_activo, paso_actual,
               datos_parciales, activa, expirada_en)
           VALUES (%s, %s, %s, '{}', TRUE, %s)
           RETURNING id""",
        (usuario_id, flujo, paso, expira), fetchone=True
    )
    return row[0] if row else None

def actualizar_sesion(sesion_id: int, paso: str,
                       datos: dict, sondaje_context: str = None):
    """Actualiza el paso y datos acumulados de una sesión."""
    ejecutar(
        """UPDATE sesiones_bot
           SET paso_actual = %s, datos_parciales = %s,
               sondaje_context = COALESCE(%s, sondaje_context),
               actualizada_en = %s
           WHERE id = %s""",
        (paso, json.dumps(datos, ensure_ascii=False, default=str),
         sondaje_context, hora_peru(), sesion_id)
    )

def cerrar_sesion(usuario_id: int):
    """Marca todas las sesiones activas del usuario como inactivas."""
    ejecutar(
        "UPDATE sesiones_bot SET activa=FALSE WHERE usuario_id=%s AND activa=TRUE",
        (usuario_id,)
    )

def renovar_sesion(sesion_id: int):
    """Renueva el tiempo de expiración."""
    from datetime import timedelta
    expira = hora_peru() + timedelta(minutes=SESION_TIMEOUT_MIN)
    ejecutar(
        "UPDATE sesiones_bot SET expirada_en=%s WHERE id=%s",
        (expira, sesion_id)
    )
