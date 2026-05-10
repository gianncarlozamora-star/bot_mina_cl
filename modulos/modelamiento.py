"""
MÓDULO MODELAMIENTO Y ESTIMACIÓN
El geólogo registra cuando completa el modelamiento y/o estimación
de uno o varios sondajes en paralelo.

Flujo:
  iniciar → muestra sondajes listos para modelar y estimar
  → elige acción (1=Modelamiento / 2=Estimación)
  → ingresa códigos de sondajes (separados por coma)
  → ESTIMACIÓN: pregunta modelo CP (ej: CP-MAY26)
  → resumen → confirmar

Tablas que escribe:
  - sondajes: estado_modelado, estado_estimacion, modelo_cp
"""
from db.sesiones import actualizar_sesion, cerrar_sesion
from db.conexion import ejecutar
from db.sondajes import buscar_sondaje
from config import fecha_hora_str, hora_peru

FLUJO = "MODELAMIENTO"


# ══════════════════════════════════════════════════════════════
# INICIO
# ══════════════════════════════════════════════════════════════

def iniciar(usuario: dict, sesion_id: int) -> str:
    actualizar_sesion(sesion_id, "mod_accion", {})
    panel = _panel_sondajes()
    return (
        f"🗂️ *MODELAMIENTO Y ESTIMACIÓN*\n"
        f"📅 {fecha_hora_str()}\n"
        f"{'─'*28}\n"
        f"{panel}\n"
        f"{'─'*28}\n"
        f"¿Qué deseas registrar?\n"
        f"  *1* — 🗂️ Modelamiento completado\n"
        f"  *2* — 📐 Estimación completada\n"
    )


# ══════════════════════════════════════════════════════════════
# PROCESADOR PRINCIPAL
# ══════════════════════════════════════════════════════════════

def procesar(mensaje: str, usuario: dict, sesion: dict) -> str:
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    # ── Elegir acción ─────────────────────────────────────────
    if paso == "mod_accion":
        if msg == "1":
            datos["accion"] = "MODELAMIENTO"
            actualizar_sesion(sid, "mod_sondajes", datos)
            # Mostrar helper de pendientes de modelar
            helper = _helper_pendientes_modelar()
            return (
                f"🗂️ *MODELAMIENTO*\n\n"
                f"{helper}\n"
                f"{'─'*28}\n"
                f"¿Qué sondajes modelaste?\n"
                f"Escribe los códigos separados por coma:\n"
                f"Ejemplo: 8422, 8401, 8399\n"
            )
        elif msg == "2":
            datos["accion"] = "ESTIMACION"
            actualizar_sesion(sid, "mod_sondajes", datos)
            # Mostrar helper de listos para estimar
            helper = _helper_listos_estimar()
            return (
                f"📐 *ESTIMACIÓN*\n\n"
                f"{helper}\n"
                f"{'─'*28}\n"
                f"¿Qué sondajes estimaste?\n"
                f"Escribe los códigos separados por coma:\n"
                f"Ejemplo: 8422, 8401\n"
            )
        else:
            return "❓ Responde *1* (Modelamiento) o *2* (Estimación)."

    # ── Ingresar códigos de sondajes ──────────────────────────
    elif paso == "mod_sondajes":
        codigos = [c.strip() for c in msg.replace(";", ",").split(",") if c.strip()]
        if not codigos:
            return "❓ Ingresa al menos un código. Ejemplo: 8422, 8401"

        encontrados = []
        no_encontrados = []
        advertencias = []

        for cod in codigos:
            sondaje = buscar_sondaje(cod)
            if not sondaje:
                no_encontrados.append(cod)
                continue

            # Validaciones según acción
            if datos["accion"] == "MODELAMIENTO":
                if sondaje.get("estado_laboratorio") != "COMPLETADO":
                    advertencias.append(
                        f"⚠️ *{sondaje['bhid']}* aún no tiene leyes confirmadas."
                    )
                if sondaje.get("estado_modelado") == "COMPLETADO":
                    advertencias.append(
                        f"ℹ️ *{sondaje['bhid']}* ya fue modelado anteriormente."
                    )

            elif datos["accion"] == "ESTIMACION":
                if sondaje.get("estado_modelado") != "COMPLETADO":
                    advertencias.append(
                        f"⚠️ *{sondaje['bhid']}* aún no está modelado."
                    )
                if sondaje.get("estado_estimacion") == "COMPLETADO":
                    advertencias.append(
                        f"ℹ️ *{sondaje['bhid']}* ya fue estimado anteriormente."
                    )

            encontrados.append({
                "id":   sondaje.get("id") or _obtener_id(sondaje["bhid"]),
                "bhid": sondaje["bhid"],
                "tipo": sondaje.get("subcategoria", "—"),
                "obj":  sondaje.get("tajo_objetivo") or sondaje.get("cuerpo_objetivo") or "—",
            })

        if no_encontrados:
            return (
                f"❌ No encontré: *{', '.join(no_encontrados)}*\n"
                f"Verifica los códigos e intenta de nuevo."
            )

        if not encontrados:
            return "❌ Ningún sondaje válido encontrado. Revisa los códigos."

        datos["sondajes"] = encontrados
        datos["advertencias"] = advertencias

        # Si es estimación → pedir modelo CP
        if datos["accion"] == "ESTIMACION":
            actualizar_sesion(sid, "mod_modelo_cp", datos)
            aviso = "\n".join(advertencias) + "\n\n" if advertencias else ""
            sondajes_str = "\n".join(
                f"  🔖 {s['bhid']} — {s['tipo']} | {s['obj']}"
                for s in encontrados
            )
            return (
                f"{aviso}"
                f"✅ Sondajes a estimar:\n{sondajes_str}\n\n"
                f"¿En qué *modelo de corto plazo* se incluyen?\n"
                f"Ejemplo: CP-MAY26, CP-JUN26\n"
            )

        # Si es modelamiento → ir directo a confirmación
        actualizar_sesion(sid, "mod_confirmacion", datos)
        return _resumen(datos)

    # ── Modelo CP (solo estimación) ───────────────────────────
    elif paso == "mod_modelo_cp":
        modelo = msg.upper().strip()
        if len(modelo) < 4:
            return "❓ Ingresa el código del modelo. Ejemplo: CP-MAY26"

        # Normalizar formato CP-MMMAA
        if not modelo.startswith("CP-"):
            modelo = f"CP-{modelo}"

        datos["modelo_cp"] = modelo
        actualizar_sesion(sid, "mod_confirmacion", datos)
        return _resumen(datos)

    # ── Confirmación final ────────────────────────────────────
    elif paso == "mod_confirmacion":
        if msg.lower() in ("no", "cancelar"):
            cerrar_sesion(usuario["id"])
            return "❌ Registro cancelado."
        if msg.lower() not in ("sí", "si", "ok", "yes", "s"):
            return "¿Confirmas? *sí* o *no*."

        try:
            accion    = datos["accion"]
            sondajes  = datos["sondajes"]
            modelo_cp = datos.get("modelo_cp")
            hoy       = hora_peru().strftime("%Y-%m-%d")
            n         = len(sondajes)

            if accion == "MODELAMIENTO":
                for s in sondajes:
                    ejecutar(
                        """UPDATE sondajes
                           SET estado_modelado = 'COMPLETADO',
                               actualizado_en  = NOW()
                           WHERE id = %s""",
                        (s["id"],)
                    )
                cerrar_sesion(usuario["id"])
                bhids = ", ".join(s["bhid"] for s in sondajes)
                return (
                    f"✅ *Modelamiento registrado*\n"
                    f"{'─'*28}\n"
                    f"🗂️ Sondajes: {n}\n"
                    f"🔖 {bhids}\n"
                    f"📅 {fecha_hora_str()}\n"
                    f"👤 {usuario['nombre']}\n"
                    f"{'─'*28}\n"
                    f"_(Listos para estimación cuando corresponda)_"
                )

            else:  # ESTIMACION
                for s in sondajes:
                    ejecutar(
                        """UPDATE sondajes
                           SET estado_estimacion = 'COMPLETADO',
                               modelo_cp         = %s,
                               actualizado_en    = NOW()
                           WHERE id = %s""",
                        (modelo_cp, s["id"])
                    )
                cerrar_sesion(usuario["id"])
                bhids = ", ".join(s["bhid"] for s in sondajes)
                return (
                    f"✅ *Estimación registrada*\n"
                    f"{'─'*28}\n"
                    f"📐 Sondajes: {n}\n"
                    f"🔖 {bhids}\n"
                    f"📊 Modelo CP: *{modelo_cp}*\n"
                    f"📅 {fecha_hora_str()}\n"
                    f"👤 {usuario['nombre']}\n"
                )

        except Exception as e:
            print(f"[MODELAMIENTO] Error: {e}")
            return "⚠️ Error al guardar. Intenta de nuevo."

    return "❓ Escribe *hola* para reiniciar."


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _panel_sondajes() -> str:
    """Panel inicial: muestra listos para modelar y listos para estimar."""

    # Listos para modelar: laboratorio COMPLETADO, modelado PENDIENTE
    rows_mod = ejecutar(
        """SELECT s.bhid, sc.nombre, s.tajo_objetivo, s.cuerpo_objetivo
           FROM sondajes s
           LEFT JOIN cat_subcategorias sc ON s.subcategoria_id = sc.id
           WHERE s.estado_laboratorio = 'COMPLETADO'
             AND COALESCE(s.estado_modelado, 'PENDIENTE') != 'COMPLETADO'
           ORDER BY s.bhid
           LIMIT 10""",
        fetchall=True
    ) or []

    # Listos para estimar: modelado COMPLETADO, estimacion PENDIENTE
    rows_est = ejecutar(
        """SELECT s.bhid, sc.nombre, s.tajo_objetivo, s.cuerpo_objetivo,
                  COALESCE(s.modelo_cp, '—')
           FROM sondajes s
           LEFT JOIN cat_subcategorias sc ON s.subcategoria_id = sc.id
           WHERE COALESCE(s.estado_modelado, 'PENDIENTE') = 'COMPLETADO'
             AND COALESCE(s.estado_estimacion, 'PENDIENTE') != 'COMPLETADO'
           ORDER BY s.bhid
           LIMIT 10""",
        fetchall=True
    ) or []

    lineas = []

    if rows_mod:
        lineas.append(f"🗂️ *Listos para MODELAR ({len(rows_mod)}):*")
        for r in rows_mod:
            obj = r[2] or r[3] or "—"
            lineas.append(f"  • *{r[0]}* — {r[1] or '—'} | {obj}")
    else:
        lineas.append("🗂️ *Listos para MODELAR:* ninguno ✅")

    lineas.append("")

    if rows_est:
        lineas.append(f"📐 *Listos para ESTIMAR ({len(rows_est)}):*")
        for r in rows_est:
            obj = r[2] or r[3] or "—"
            lineas.append(f"  • *{r[0]}* — {r[1] or '—'} | {obj}")
    else:
        lineas.append("📐 *Listos para ESTIMAR:* ninguno ✅")

    return "\n".join(lineas)


def _helper_pendientes_modelar() -> str:
    """Lista compacta de sondajes pendientes de modelar."""
    rows = ejecutar(
        """SELECT s.bhid, sc.nombre, s.tajo_objetivo, s.cuerpo_objetivo
           FROM sondajes s
           LEFT JOIN cat_subcategorias sc ON s.subcategoria_id = sc.id
           WHERE s.estado_laboratorio = 'COMPLETADO'
             AND COALESCE(s.estado_modelado, 'PENDIENTE') != 'COMPLETADO'
           ORDER BY s.bhid
           LIMIT 10""",
        fetchall=True
    ) or []

    if not rows:
        return "_(No hay sondajes pendientes de modelar)_"

    lineas = [f"📋 *Pendientes de modelar ({len(rows)}):*"]
    for r in rows:
        obj = r[2] or r[3] or "—"
        lineas.append(f"  • *{r[0]}* — {r[1] or '—'} | {obj}")
    return "\n".join(lineas)


def _helper_listos_estimar() -> str:
    """Lista compacta de sondajes modelados pendientes de estimar."""
    rows = ejecutar(
        """SELECT s.bhid, sc.nombre, s.tajo_objetivo, s.cuerpo_objetivo
           FROM sondajes s
           LEFT JOIN cat_subcategorias sc ON s.subcategoria_id = sc.id
           WHERE COALESCE(s.estado_modelado, 'PENDIENTE') = 'COMPLETADO'
             AND COALESCE(s.estado_estimacion, 'PENDIENTE') != 'COMPLETADO'
           ORDER BY s.bhid
           LIMIT 10""",
        fetchall=True
    ) or []

    if not rows:
        return "_(No hay sondajes modelados pendientes de estimar)_"

    lineas = [f"📋 *Modelados, listos para estimar ({len(rows)}):*"]
    for r in rows:
        obj = r[2] or r[3] or "—"
        lineas.append(f"  • *{r[0]}* — {r[1] or '—'} | {obj}")
    return "\n".join(lineas)


def _resumen(datos: dict) -> str:
    accion   = datos["accion"]
    sondajes = datos["sondajes"]
    advertencias = datos.get("advertencias", [])

    sondajes_str = "\n".join(
        f"  🔖 {s['bhid']} — {s['tipo']} | {s['obj']}"
        for s in sondajes
    )
    aviso_str = ("\n" + "\n".join(advertencias) + "\n") if advertencias else ""

    if accion == "MODELAMIENTO":
        return (
            f"📋 *RESUMEN MODELAMIENTO*\n"
            f"{'─'*28}\n"
            f"{sondajes_str}\n"
            f"{'─'*28}\n"
            f"🗂️ Total: *{len(sondajes)}* sondajes\n"
            f"{aviso_str}"
            f"{'─'*28}\n"
            f"¿Confirmas? (*sí* / *no*)\n"
        )
    else:
        return (
            f"📋 *RESUMEN ESTIMACIÓN*\n"
            f"{'─'*28}\n"
            f"{sondajes_str}\n"
            f"{'─'*28}\n"
            f"📐 Total:    *{len(sondajes)}* sondajes\n"
            f"📊 Modelo CP: *{datos.get('modelo_cp', '—')}*\n"
            f"{aviso_str}"
            f"{'─'*28}\n"
            f"¿Confirmas? (*sí* / *no*)\n"
        )


def _obtener_id(bhid: str) -> int | None:
    row = ejecutar("SELECT id FROM sondajes WHERE bhid = %s", (bhid,), fetchone=True)
    return row[0] if row else None


# ══════════════════════════════════════════════════════════════
# CONSULTA PÚBLICA — para gerencia.py y reporte
# ══════════════════════════════════════════════════════════════

def estado_modelamiento() -> str:
    """Resumen de estado de modelamiento y estimación por campaña."""
    rows = ejecutar(
        """SELECT
               COALESCE(campana, 'Sin campaña') as campana,
               COUNT(*) as total,
               SUM(CASE WHEN estado_laboratorio = 'COMPLETADO' THEN 1 ELSE 0 END) as con_leyes,
               SUM(CASE WHEN COALESCE(estado_modelado,'PENDIENTE') = 'COMPLETADO' THEN 1 ELSE 0 END) as modelados,
               SUM(CASE WHEN COALESCE(estado_estimacion,'PENDIENTE') = 'COMPLETADO' THEN 1 ELSE 0 END) as estimados
           FROM sondajes
           GROUP BY campana
           ORDER BY campana DESC
           LIMIT 5""",
        fetchall=True
    ) or []

    if not rows:
        return "⚠️ Sin datos de modelamiento."

    lineas = [
        f"🗂️ *ESTADO MODELAMIENTO*\n"
        f"{'─'*28}"
    ]
    for r in rows:
        campana, total, leyes, mod, est = r
        lineas.append(
            f"📅 *{campana}*\n"
            f"   Leyes:     {leyes}/{total}\n"
            f"   Modelados: {mod}/{total}\n"
            f"   Estimados: {est}/{total}\n"
        )

    return "\n".join(lineas) + f"\n📅 {fecha_hora_str()}"
