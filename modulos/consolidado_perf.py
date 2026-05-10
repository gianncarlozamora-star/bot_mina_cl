"""
FLUJO CONSOLIDADO PERFORACIÓN
Sesión corta: empresa → turno → fecha → genera reporte.
"""
from db.sesiones import actualizar_sesion, cerrar_sesion
from db.conexion import ejecutar
from config import hora_peru

FLUJO = "CONSOLIDADO_PERF"


def iniciar(usuario: dict, sesion_id: int) -> str:
    """Router ya envió menu_empresa_perforacion() — solo inicializa paso."""
    actualizar_sesion(sesion_id, "cons_empresa", {})
    return None


def procesar(mensaje: str, usuario: dict, sesion: dict) -> str:
    from modulos.gestion_perforacion import consolidado_turno
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip().lower()

    # ── Empresa ───────────────────────────────────────────────
    if paso == "cons_empresa":
        empresas_map = {
            "explomin":      ("EXPLOMIN",      None),
            "explodrilling": ("EXPLODRILLING", None),
            "todas":         ("Todas",         None),
        }
        # Viene normalizado desde main.py como "explomin", "explodrilling", "todas"
        match = empresas_map.get(msg)
        if not match:
            return "❓ Selecciona una empresa de la lista."

        nombre_emp, _ = match
        if nombre_emp == "Todas":
            datos["empresa_id"]     = None
            datos["empresa_nombre"] = "Todas"
        else:
            row = ejecutar(
                "SELECT id FROM cat_empresas WHERE codigo = %s",
                (nombre_emp,), fetchone=True
            )
            datos["empresa_id"]     = row[0] if row else None
            datos["empresa_nombre"] = nombre_emp

        actualizar_sesion(sid, "cons_turno", datos)
        return None  # router envía botones_turno

    # ── Turno ─────────────────────────────────────────────────
    elif paso == "cons_turno":
        turnos = {
            "1": "DIA", "dia": "DIA", "día": "DIA",
            "2": "NOCHE", "noche": "NOCHE",
            "☀️ día": "DIA", "☀️ dia": "DIA",
            "🌙 noche": "NOCHE",
        }
        turno = turnos.get(msg)
        if not turno:
            return "❓ Responde *1* (Día) o *2* (Noche)."
        datos["turno"] = turno
        actualizar_sesion(sid, "cons_fecha", datos)
        return (
            f"✅ Turno: *{turno}*\n\n"
            f"¿Qué *fecha*?\n"
            f"  *hoy* — {hora_peru().strftime('%d/%m/%Y')}\n"
            f"  *ayer* — fecha anterior\n"
            f"  DD/MM — fecha específica\n"
        )

    # ── Fecha ─────────────────────────────────────────────────
    elif paso == "cons_fecha":
        fecha = _parsear_fecha(msg)
        if not fecha:
            return "❓ Escribe *hoy*, *ayer* o DD/MM (ej: 09/05)."
        datos["fecha"] = fecha
        cerrar_sesion(usuario["id"])
        return consolidado_turno(
            empresa_id=datos.get("empresa_id"),
            turno=datos["turno"],
            fecha=fecha,
        )

    return "❓ Escribe *hola* para reiniciar."


# ── HELPER ────────────────────────────────────────────────────

def _parsear_fecha(msg: str) -> str | None:
    from datetime import datetime, timedelta
    hoy = hora_peru().date()
    if msg in ("hoy", "today"):
        return hoy.strftime("%Y-%m-%d")
    if msg in ("ayer", "yesterday"):
        return (hoy - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        parsed = datetime.strptime(msg.replace("-", "/"), "%d/%m")
        return parsed.replace(year=hoy.year).strftime("%Y-%m-%d")
    except:
        return None
