"""
MÓDULO ANULAR SGS
Permite anular registros de etapas_sgs (logueo, muestreo, rqd, fotografia, densidad).

Reglas:
- Técnico SGS: solo sus propios registros, máximo 7 días atrás
- GEOLOGO / ADMIN: cualquier registro, sin límite de tiempo
- No borra físicamente — marca estado = 'ANULADO' en etapas_sgs
- Si era el único registro activo de esa etapa → revierte estado en sondajes a PENDIENTE

Flujo:
  elegir_etapa → elegir_fecha → seleccionar_registro → confirmacion_anular
"""
from db.sesiones import actualizar_sesion, cerrar_sesion
from db.sondajes import actualizar_estado_etapa
from db.conexion import ejecutar
from config import fecha_hora_str, hora_peru

FLUJO = "ANULAR_SGS"

ETAPAS_LABEL = {
    "LOGUEO":     "📝 Logueo",
    "MUESTREO":   "🧪 Muestreo",
    "RQD":        "📐 RQD",
    "FOTOGRAFIA": "📸 Fotografía",
    "DENSIDAD":   "⚖️ Densidad",
}

ROLES_ADMIN = {"GEOLOGO", "ADMIN"}


# ══════════════════════════════════════════════════════════════
# INICIO
# ══════════════════════════════════════════════════════════════

def iniciar(usuario: dict, sesion_id: int) -> str:
    """
    Router llama aquí. Muestra menú de etapas disponibles.
    El router debe enviar menu_etapas_anular() después si quiere interactivo,
    o dejar que este texto lo maneje directamente.
    """
    actualizar_sesion(sesion_id, "anular_elegir_etapa",
                      {"es_admin": usuario["rol"] in ROLES_ADMIN})
    return (
        f"🗑️ *ANULAR REGISTRO SGS*\n\n"
        f"¿Qué tipo de registro quieres anular?\n\n"
        f"  *1* — 📝 Logueo\n"
        f"  *2* — 🧪 Muestreo\n"
        f"  *3* — 📐 RQD\n"
        f"  *4* — 📸 Fotografía\n"
        f"  *5* — ⚖️ Densidad\n\n"
        f"Responde con el número.\n"
    )


# ══════════════════════════════════════════════════════════════
# PROCESADOR PRINCIPAL
# ══════════════════════════════════════════════════════════════

def procesar(mensaje: str, usuario: dict, sesion: dict) -> str:
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    # ── Elegir etapa ──────────────────────────────────────────
    if paso == "anular_elegir_etapa":
        mapa = {
            "1": "LOGUEO", "2": "MUESTREO", "3": "RQD",
            "4": "FOTOGRAFIA", "5": "DENSIDAD",
        }
        # También acepta nombre directo
        etapa = mapa.get(msg) or (
            msg.upper() if msg.upper() in ETAPAS_LABEL else None
        )
        if not etapa:
            return "❓ Responde con un número del 1 al 5."

        datos["etapa"] = etapa
        actualizar_sesion(sid, "anular_elegir_fecha", datos)
        return (
            f"✅ Etapa: *{ETAPAS_LABEL[etapa]}*\n\n"
            f"¿De qué *fecha* es el registro?\n"
            f"  *hoy* — Registros de hoy\n"
            f"  *ayer* — Registros de ayer\n"
            f"  DD/MM — Fecha específica\n"
        )

    # ── Elegir fecha ──────────────────────────────────────────
    elif paso == "anular_elegir_fecha":
        fecha = _parsear_fecha_anular(msg)
        if not fecha:
            return "❓ Formato: *hoy*, *ayer* o DD/MM (ej: 08/05)."

        # Verificar límite de 7 días para no-admin
        es_admin = datos.get("es_admin", False)
        if not es_admin:
            from datetime import date, timedelta
            limite = hora_peru().date() - timedelta(days=7)
            from datetime import datetime
            fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
            if fecha_dt < limite:
                return (
                    f"⛔ Solo puedes anular registros de los últimos 7 días.\n"
                    f"Para fechas anteriores, contacta al geólogo.\n"
                )

        datos["fecha_anular"] = fecha
        registros = _listar_registros(
            etapa=datos["etapa"],
            fecha=fecha,
            usuario_id=usuario["id"],
            es_admin=es_admin,
        )
        if not registros:
            return (
                f"📭 No encontré registros de *{ETAPAS_LABEL[datos['etapa']]}* "
                f"del *{_fmt_fecha(fecha)}* "
                + ("" if es_admin else "registrados por ti")
                + ".\n\nEscribe *hola* para volver al menú."
            )

        datos["registros"] = registros
        actualizar_sesion(sid, "anular_seleccionar", datos)
        return _menu_registros(registros, datos["etapa"], fecha)

    # ── Seleccionar registro ──────────────────────────────────
    elif paso == "anular_seleccionar":
        registros = datos.get("registros", [])
        if not msg.isdigit() or int(msg) < 1 or int(msg) > len(registros):
            return f"❓ Responde con un número del 1 al {len(registros)}."

        idx = int(msg) - 1
        reg = registros[idx]
        datos["registro_id"]       = reg["id"]
        datos["registro_bhid"]     = reg["bhid"]
        datos["registro_resumen"]  = reg["resumen"]
        datos["registro_etapa"]    = datos["etapa"]

        actualizar_sesion(sid, "anular_confirmar", datos)
        return (
            f"⚠️ *CONFIRMAR ANULACIÓN*\n"
            f"{'─'*28}\n"
            f"🔬 {ETAPAS_LABEL[datos['etapa']]}\n"
            f"🔖 Sondaje: *{reg['bhid']}*\n"
            f"📅 Fecha:   {_fmt_fecha(datos['fecha_anular'])}\n"
            f"📝 {reg['resumen']}\n"
            f"{'─'*28}\n\n"
            f"¿Confirmas la anulación? (*sí* / *no*)\n"
        )

    # ── Confirmación ──────────────────────────────────────────
    elif paso == "anular_confirmar":
        if msg.lower() in ("no", "cancelar", "n"):
            cerrar_sesion(usuario["id"])
            return "❌ Anulación cancelada."
        if msg.lower() not in ("sí", "si", "ok", "yes", "confirma"):
            return "¿Confirmas? *sí* o *no*."

        reg_id  = datos["registro_id"]
        bhid    = datos["registro_bhid"]
        etapa   = datos["registro_etapa"]

        try:
            # Marcar como ANULADO (no borrar físicamente)
            ejecutar(
                """UPDATE etapas_sgs
                   SET estado = 'ANULADO', actualizado_en = NOW()
                   WHERE id = %s""",
                (reg_id,)
            )

            # Verificar si quedan registros activos de esa etapa
            row = ejecutar(
                """SELECT COUNT(*) FROM etapas_sgs e
                   JOIN sondajes s ON e.sondaje_id = s.id
                   WHERE s.bhid = %s AND e.etapa = %s
                     AND COALESCE(e.estado, 'ACTIVO') != 'ANULADO'""",
                (bhid, etapa), fetchone=True
            )
            quedan = int(row[0]) if row else 0

            # Si no quedan registros activos → revertir estado en sondaje
            if quedan == 0:
                etapa_key = etapa.lower()
                actualizar_estado_etapa(bhid, etapa_key, "PENDIENTE")
                revertido = f"\n↩️ Estado {ETAPAS_LABEL[etapa]} revertido a *PENDIENTE*."
            else:
                revertido = ""

            cerrar_sesion(usuario["id"])
            return (
                f"✅ *Registro anulado*\n"
                f"🗑️ {ETAPAS_LABEL[etapa]} | *{bhid}*\n"
                f"📅 {fecha_hora_str()}\n"
                f"👤 {usuario['nombre']}"
                f"{revertido}\n"
            )

        except Exception as e:
            print(f"[ANULAR_SGS] Error: {e}")
            return "⚠️ Error al anular. Intenta de nuevo."

    return "❓ Escribe *hola* para reiniciar."


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _listar_registros(etapa: str, fecha: str,
                       usuario_id: int, es_admin: bool) -> list:
    """
    Retorna lista de registros activos de la etapa/fecha.
    Admin ve todos; técnico solo los suyos.
    """
    filtro_usuario = "" if es_admin else "AND e.reportado_por = %s"
    params_base    = [etapa, fecha]
    if not es_admin:
        params_base.append(usuario_id)

    rows = ejecutar(
        f"""SELECT e.id,
                   s.bhid,
                   e.desde_m, e.hasta_m,
                   e.tecnico,
                   e.cant_muestras,
                   e.cod_muestra_ini, e.cod_muestra_fin,
                   e.observaciones,
                   ub.nombre AS reportado_nombre
            FROM etapas_sgs e
            JOIN sondajes s ON e.sondaje_id = s.id
            LEFT JOIN usuarios_bot ub ON e.reportado_por = ub.id
            WHERE e.etapa = %s
              AND e.fecha  = %s
              AND COALESCE(e.estado, 'ACTIVO') != 'ANULADO'
              {filtro_usuario}
            ORDER BY e.id DESC
            LIMIT 10""",
        tuple(params_base), fetchall=True
    )
    if not rows:
        return []

    resultado = []
    for r in rows:
        (reg_id, bhid, desde, hasta, tecnico, cant,
         cod_ini, cod_fin, obs, reportado) = r

        # Construir resumen según etapa
        if etapa == "MUESTREO":
            resumen = (
                f"{float(desde or 0):.1f}→{float(hasta or 0):.1f}m | "
                f"{cod_ini or '?'}→{cod_fin or '?'} | "
                f"{cant or '?'} muestras"
            )
        elif etapa in ("LOGUEO", "RQD", "FOTOGRAFIA"):
            resumen = (
                f"{float(desde or 0):.1f}→{float(hasta or 0):.1f}m"
                + (f" | {obs[:40]}" if obs else "")
            )
        elif etapa == "DENSIDAD":
            resumen = (
                f"{float(desde or 0):.1f}→{float(hasta or 0):.1f}m | "
                f"{cant or '?'} muestras"
            )
        else:
            resumen = f"{float(desde or 0):.1f}→{float(hasta or 0):.1f}m"

        if reportado:
            resumen += f" | 👤 {reportado}"

        resultado.append({
            "id":      reg_id,
            "bhid":    bhid,
            "resumen": resumen,
        })
    return resultado


def _menu_registros(registros: list, etapa: str, fecha: str) -> str:
    """Muestra lista numerada de registros para seleccionar."""
    lineas = [
        f"📋 *{ETAPAS_LABEL[etapa]} — {_fmt_fecha(fecha)}*",
        f"{'─'*28}",
    ]
    for i, r in enumerate(registros):
        lineas.append(f"  *{i+1}* — {r['bhid']} | {r['resumen']}")
    lineas.append(f"{'─'*28}")
    lineas.append("¿Cuál quieres anular? Responde con el número.")
    return "\n".join(lineas)


def _parsear_fecha_anular(msg: str) -> str | None:
    msg_low = msg.lower().strip()
    hoy = hora_peru().date()
    if msg_low in ("hoy", "today"):
        return hoy.strftime("%Y-%m-%d")
    if msg_low in ("ayer", "yesterday"):
        from datetime import timedelta
        return (hoy - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        from datetime import datetime
        parsed = datetime.strptime(msg.replace("-", "/"), "%d/%m")
        return parsed.replace(year=hoy.year).strftime("%Y-%m-%d")
    except:
        return None


def _fmt_fecha(fecha: str) -> str:
    try:
        from datetime import datetime
        return datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return fecha
