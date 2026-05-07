"""
FLUJO DE REPORTE DE AVANCE DE PERFORACIÓN
Para roles PERFORISTA.
Pasos: maquina → sondaje → turno → profundidades →
       observaciones → foto → confirmacion → reporte_empresa → post_consolidado
"""
from db.sesiones import actualizar_sesion, cerrar_sesion
from db.sondajes import buscar_sondaje, calcular_valor_turno
from db.conexion import ejecutar
from db.usuarios import obtener_maquinas_activas
from ia.interprete import generar_mensaje_estandarizado, generar_reporte_empresa
from config import fecha_hora_str
from config import hora_peru as _hora

FLUJO = "PERFORACION"

def iniciar(usuario: dict, sesion_id: int) -> str:
    if usuario.get("maquina"):
        actualizar_sesion(sesion_id, "sondaje",
                          {"maquina_id":  usuario["maquina_id"],
                           "maquina_cod": usuario["maquina"],
                           "empresa_id":  usuario["empresa_id"],
                           "sufijo":      usuario.get("sufijo_tarifa", "")})
        return (
            f"⛏️ *REPORTE DE PERFORACIÓN*\n"
            f"🚜 Máquina: *{usuario['maquina']}*\n\n"
            f"¿Cuál es el *código del sondaje*?\n"
            f"Ejemplo: 8422, PECLD08422\n"
        )
    maquinas = obtener_maquinas_activas()
    menu = "\n".join([f"  *{i+1}* — {m['codigo']} ({m['empresa']})"
                      for i, m in enumerate(maquinas)])
    actualizar_sesion(sesion_id, "maquina",
                      {"maquina_opciones": [(m["id"], m["codigo"],
                                             m["empresa"]) for m in maquinas]})
    return (
        f"⛏️ *REPORTE DE PERFORACIÓN*\n"
        f"📅 {fecha_hora_str()}\n\n"
        f"¿Con qué *máquina* trabajas hoy?\n\n"
        f"{menu}\n\n"
        f"Responde con el número.\n"
    )


def procesar(mensaje: str, usuario: dict, sesion: dict,
             foto_url: str = None) -> str:
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    # Si viene foto en paso foto, procesarla directamente
    if foto_url and paso == "foto":
        datos["foto_url"]   = foto_url
        datos["foto_tramo"] = (
            f"{datos.get('prof_inicio', 0):.1f}-"
            f"{datos.get('prof_final', 0):.1f}m"
        )
        actualizar_sesion(sid, "confirmacion", datos)
        return _mostrar_resumen(datos)

    # ── Selección de máquina ──────────────────────────────────
    if paso == "maquina":
        opciones = datos.get("maquina_opciones", [])
        if not msg.isdigit() or int(msg) < 1 or int(msg) > len(opciones):
            return f"❓ Responde con un número del 1 al {len(opciones)}."
        idx = int(msg) - 1
        maq_id, maq_cod, empresa = opciones[idx]
        row = ejecutar(
            "SELECT empresa_id, sufijo_tarifa FROM cat_maquinas WHERE id = %s",
            (maq_id,), fetchone=True
        )
        datos.update({
            "maquina_id":  maq_id,
            "maquina_cod": maq_cod,
            "empresa_id":  row[0] if row else 1,
            "sufijo":      row[1] if row else "",
        })
        actualizar_sesion(sid, "sondaje", datos)
        return (
            f"✅ Máquina: *{maq_cod}*\n\n"
            f"¿Cuál es el *código del sondaje*?\n"
            f"Ejemplo: 8422, PECLD08422\n"
        )

    # ── Sondaje ───────────────────────────────────────────────
    elif paso == "sondaje":
        if msg.lower() == "provisional":
            ts = _hora().strftime("%d%m-%H%M")
            bhid_temp = f"TEMP-{datos.get('maquina_cod','X').replace('-','')}-{ts}"
            datos["bhid"]           = bhid_temp
            datos["es_provisional"] = True
            datos["diametro"]       = "NQ"
            datos["prog_m"]         = 0
            datos["final_m_actual"] = 0
            actualizar_sesion(sid, "turno", datos)
            return (
                f"⚠️ Registrando como *provisional* ({bhid_temp})\n\n"
                f"¿Qué turno reportas?\n"
                f"  *1* — Día\n  *2* — Noche\n"
            )
        sondaje = buscar_sondaje(msg)
        if not sondaje:
            return (
                f"❌ No encontré *{msg}*.\n\n"
                f"Verifica el código o escribe *provisional*.\n"
            )
        datos["bhid"]           = sondaje["bhid"]
        datos["sondaje_nivel"]  = sondaje.get("nivel", "—")
        datos["sondaje_labor"]  = sondaje.get("labor", "—")
        datos["diametro"]       = sondaje.get("diametro", "NQ")
        datos["prog_m"]         = sondaje.get("prog_m", 0)
        datos["final_m_actual"] = sondaje.get("final_m") or 0
        actualizar_sesion(sid, "turno", datos, sondaje_context=sondaje["bhid"])
        return (
            f"✅ Sondaje: *{sondaje['bhid']}*\n"
            f"   Nv.{sondaje.get('nivel','—')} | {sondaje.get('labor','—')}\n"
            f"   Prog: {sondaje.get('prog_m','—')} m | "
            f"Actual: {sondaje.get('final_m') or 0:.1f} m\n\n"
            f"¿Qué turno reportas?\n"
            f"  *1* — Día\n  *2* — Noche\n"
        )

    # ── Turno ─────────────────────────────────────────────────
    elif paso == "turno":
        turnos = {"1": "DIA", "2": "NOCHE", "dia": "DIA", "día": "DIA",
                  "noche": "NOCHE", "d": "DIA", "n": "NOCHE"}
        turno = turnos.get(msg.lower())
        if not turno:
            return "❓ Responde *1* (Día) o *2* (Noche)."
        datos["turno"] = turno
        datos["fecha"] = _hora().strftime("%Y-%m-%d")
        actualizar_sesion(sid, "prof_inicio", datos)
        return (
            f"✅ Turno: *{turno}* | 📅 {_hora().strftime('%d/%m/%Y')}\n\n"
            f"¿*Profundidad inicio* del turno (metros)?\n"
            f"Ejemplo: 182.50\n"
        )

    # ── Profundidad inicio ────────────────────────────────────
    elif paso == "prof_inicio":
        try:
            prof_ini = float(msg.replace(",", "."))
            if prof_ini < 0:
                raise ValueError
            datos["prof_inicio"] = prof_ini
        except ValueError:
            return "❓ Número válido. Ejemplo: 182.50"
        actualizar_sesion(sid, "prof_final", datos)
        return (
            f"✅ Inicio: *{prof_ini:.2f} m*\n\n"
            f"¿*Profundidad final* del turno?\n"
        )

    # ── Profundidad final ─────────────────────────────────────
    elif paso == "prof_final":
        try:
            prof_fin = float(msg.replace(",", "."))
            if prof_fin <= datos.get("prof_inicio", 0):
                return f"❓ Debe ser mayor a {datos['prof_inicio']:.2f} m."
            datos["prof_final"] = prof_fin
        except ValueError:
            return "❓ Número válido."

        avance = prof_fin - datos["prof_inicio"]
        datos["avance"]         = round(avance, 2)
        datos["retorno_fluido"] = "100%"
        sufijo = datos.get("sufijo", "")
        diam   = datos.get("diametro", "NQ")
        datos["valor_usd"] = calcular_valor_turno(
            diam, datos["prof_inicio"], prof_fin, sufijo)

        actualizar_sesion(sid, "observaciones", datos)
        return (
            f"✅ Final: *{prof_fin:.2f} m* | Avance: *{avance:.2f} m*\n\n"
            f"¿*Observaciones* del turno?\n"
            f"Escribe las novedades o *ninguna*.\n"
        )

    # ── Observaciones ─────────────────────────────────────────
    elif paso == "observaciones":
        datos["observaciones"] = "" if msg.lower() == "ninguna" else msg
        actualizar_sesion(sid, "foto", datos)
        return (
            f"📸 ¿Adjuntar foto de la última caja o tramo?\n"
            f"Envía la foto o escribe *no*.\n"
        )

    # ── Foto ──────────────────────────────────────────────────
    elif paso == "foto":
        if msg.lower() in ("no", "n", "omitir", "skip"):
            datos["foto_url"] = None
        actualizar_sesion(sid, "confirmacion", datos)
        return _mostrar_resumen(datos)

    # ── Confirmación ──────────────────────────────────────────
    elif paso == "confirmacion":
        if msg.lower() in ("no", "cancelar"):
            cerrar_sesion(usuario["id"])
            return "❌ Reporte cancelado."
        if msg.lower() not in ("sí", "si", "yes", "ok", "confirma"):
            return "¿Confirmas? *sí* o *no*."

        try:
            sondaje_id = _obtener_sondaje_id(datos["bhid"])
            if not sondaje_id:
                cerrar_sesion(usuario["id"])
                return "⚠️ Sondaje no encontrado en BD."

            ejecutar(
                """INSERT INTO avance_perforacion (
                       sondaje_id, maquina_id, fecha, turno,
                       prof_inicio, prof_final, valor_usd,
                       retorno_fluido, observaciones,
                       foto_url, foto_tramo,
                       reportado_por, fuente, mensaje_original
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'BOT',%s)""",
                (
                    sondaje_id, datos["maquina_id"],
                    datos["fecha"], datos["turno"],
                    datos["prof_inicio"], datos["prof_final"],
                    datos.get("valor_usd"),
                    datos.get("retorno_fluido", "100%"),
                    datos.get("observaciones"),
                    datos.get("foto_url"),
                    datos.get("foto_tramo"),
                    usuario["id"], str(datos)
                )
            )
            ejecutar(
                """UPDATE sondajes SET profundidad_final = %s,
                   fecha_inicio_perf = COALESCE(fecha_inicio_perf, %s)
                   WHERE bhid = %s""",
                (datos["prof_final"], datos["fecha"], datos["bhid"])
            )

            msg_individual = generar_mensaje_estandarizado(datos)
            empresa_nombre = _obtener_empresa(datos)
            datos["msg_individual"] = msg_individual
            actualizar_sesion(sid, "reporte_empresa", datos)

            return (
                f"✅ *Reporte registrado*\n"
                f"📅 {fecha_hora_str()}\n\n"
                f"─────────────────────\n"
                f"📋 *TU REPORTE — {datos.get('maquina_cod','—')}:*\n"
                f"_(Copia y reenvía a tu grupo)_\n\n"
                f"{msg_individual}\n"
                f"─────────────────────\n\n"
                f"¿Generar reporte consolidado de *{empresa_nombre}* "
                f"para este turno?\n"
                f"  *sí* — Generar consolidado\n"
                f"  *no* — Registrar otra máquina\n"
                f"  *fin* — Terminar\n"
            )

        except Exception as e:
            print(f"[PERFORACION] Error: {e}")
            return "⚠️ Error al guardar. Intenta de nuevo."

    # ── Reporte consolidado por empresa ───────────────────────
    elif paso == "reporte_empresa":
        if msg.lower() == "fin":
            cerrar_sesion(usuario["id"])
            return "✅ Sesión cerrada. Escribe *hola* cuando necesites."

        if msg.lower() in ("no", "n", "otra"):
            return _menu_siguiente_maquina(sid, datos)

        if msg.lower() not in ("sí", "si", "yes", "ok"):
            return (
                f"Responde:\n"
                f"  *sí* — Generar consolidado\n"
                f"  *no* — Registrar otra máquina\n"
                f"  *fin* — Terminar\n"
            )

        try:
            empresa_id = datos.get("empresa_id", 1)
            fecha      = datos.get("fecha")
            turno      = datos.get("turno")

            rows = ejecutar(
                """SELECT ap.prof_inicio, ap.prof_final, ap.metros_avance,
                          ap.observaciones, m.codigo, s.bhid,
                          s.nivel_prog, s.labor, s.diametro, s.profundidad_prog
                   FROM avance_perforacion ap
                   JOIN sondajes     s ON ap.sondaje_id = s.id
                   JOIN cat_maquinas m ON ap.maquina_id = m.id
                   WHERE m.empresa_id = %s
                     AND ap.fecha     = %s
                     AND ap.turno     = %s
                     AND ap.estado    = 'ACTIVO'
                   ORDER BY m.codigo""",
                (empresa_id, fecha, turno), fetchall=True
            )

            if not rows:
                actualizar_sesion(sid, "reporte_empresa", datos)
                return (
                    f"⚠️ Aún no hay reportes de otras máquinas para este turno.\n\n"
                    f"  *no* — Registrar otra máquina\n"
                    f"  *fin* — Terminar\n"
                )

            reportes = [{
                "prof_inicio":   float(r[0] or 0),
                "prof_final":    float(r[1] or 0),
                "avance":        float(r[2] or 0),
                "observaciones": r[3] or "Sin novedades",
                "maquina_cod":   r[4],
                "bhid":          r[5],
                "sondaje_nivel": r[6],
                "sondaje_labor": r[7],
                "diametro":      r[8],
                "prog_m":        r[9],
                "turno":         turno,
                "fecha":         fecha,
            } for r in rows]

            emp_row = ejecutar(
                "SELECT nombre FROM cat_empresas WHERE id = %s",
                (empresa_id,), fetchone=True
            )
            empresa_nombre = emp_row[0] if emp_row else "Empresa"
            consolidado    = generar_reporte_empresa(reportes, empresa_nombre, fecha)

            # Pasar a post_consolidado para preguntar si registra otra máquina
            actualizar_sesion(sid, "post_consolidado", datos)
            return (
                f"─────────────────────\n"
                f"🏢 *REPORTE {empresa_nombre.upper()} — TURNO {turno}*\n"
                f"_(Copia y reenvía al grupo de tu empresa)_\n\n"
                f"{consolidado}\n"
                f"─────────────────────\n\n"
                f"¿Registrar otra máquina?\n"
                f"  *sí* — Continuar\n"
                f"  *no* — Terminar\n"
            )

        except Exception as e:
            print(f"[PERFORACION] Error consolidado: {e}")
            cerrar_sesion(usuario["id"])
            return "⚠️ Error generando consolidado. Tu reporte individual ya fue guardado."

    # ── Post consolidado: ¿otra máquina? ─────────────────────
    elif paso == "post_consolidado":
        if msg.lower() in ("no", "n", "fin", "terminar"):
            cerrar_sesion(usuario["id"])
            return "✅ Listo. Escribe *hola* cuando necesites."

        if msg.lower() in ("sí", "si", "yes", "ok"):
            return _menu_siguiente_maquina(sid, datos)

        return "*sí* para registrar otra máquina o *no* para terminar."

    return "❓ Escribe *hola* para reiniciar."


# ── HELPERS ───────────────────────────────────────────────────

def _menu_siguiente_maquina(sid: int, datos: dict) -> str:
    """Prepara el menú para registrar la siguiente máquina del mismo turno."""
    maquinas = obtener_maquinas_activas()
    menu = "\n".join([f"  *{i+1}* — {m['codigo']} ({m['empresa']})"
                      for i, m in enumerate(maquinas)])
    datos_nueva = {
        "empresa_id":      datos.get("empresa_id"),
        "turno":           datos.get("turno"),
        "fecha":           datos.get("fecha"),
        "maquina_opciones": [(m["id"], m["codigo"],
                               m["empresa"]) for m in maquinas],
    }
    actualizar_sesion(sid, "maquina", datos_nueva)
    return (
        f"⛏️ *SIGUIENTE MÁQUINA*\n"
        f"Turno: *{datos.get('turno','—')}* | "
        f"📅 {datos.get('fecha','—')}\n\n"
        f"¿Qué máquina reportas ahora?\n\n"
        f"{menu}\n\n"
        f"Responde con el número.\n"
    )

def _mostrar_resumen(datos: dict) -> str:
    return (
        f"📋 *RESUMEN DEL REPORTE*\n"
        f"{'─'*30}\n"
        f"🔖 Sondaje:  *{datos.get('bhid','—')}*\n"
        f"🚜 Máquina:  {datos.get('maquina_cod','—')}\n"
        f"⏱️ Turno:    {datos.get('turno','—')} | {datos.get('fecha','—')}\n"
        f"📏 Desde:    {datos.get('prof_inicio',0):.2f} m\n"
        f"📏 Hasta:    {datos.get('prof_final',0):.2f} m\n"
        f"➡️ Avance:   *{datos.get('avance',0):.2f} m*\n"
        f"📝 Obs:      {datos.get('observaciones','Ninguna') or 'Ninguna'}\n"
        f"📸 Foto:     {'✅ Adjunta' if datos.get('foto_url') else 'No'}\n"
        f"{'─'*30}\n\n"
        f"¿Confirmas? (*sí* / *no*)\n"
    )

def _obtener_sondaje_id(bhid: str) -> int | None:
    row = ejecutar(
        "SELECT id FROM sondajes WHERE bhid = %s", (bhid,), fetchone=True
    )
    return row[0] if row else None

def _obtener_empresa(datos: dict) -> str:
    row = ejecutar(
        "SELECT codigo FROM cat_empresas WHERE id = %s",
        (datos.get("empresa_id", 1),), fetchone=True
    )
    return row[0] if row else "tu empresa"
