"""
FLUJO DE REPORTE DE AVANCE DE PERFORACIÓN v2
Incluye:
- Validación máquina vs sondaje matriculado
- Estado de perforación (PLANIFICADO/EN_CURSO/FINALIZADO)
- Cambio de línea con metro exacto
- Detección automática de sondaje finalizado
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
        f"{menu}\n\nResponde con el número.\n"
    )


def procesar(mensaje: str, usuario: dict, sesion: dict,
             foto_url: str = None) -> str:
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    # Foto en paso foto
    if foto_url and paso == "foto":
        datos["foto_url"]   = foto_url
        datos["foto_tramo"] = (
            f"{datos.get('prof_inicio',0):.1f}-"
            f"{datos.get('prof_final',0):.1f}m"
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
            datos.update({
                "bhid": bhid_temp, "es_provisional": True,
                "diametro": "NQ", "prog_m": 0, "final_m_actual": 0
            })
            actualizar_sesion(sid, "turno", datos)
            return (
                f"⚠️ Provisional: *{bhid_temp}*\n\n"
                f"¿Qué turno reportas?\n  *1* — Día\n  *2* — Noche\n"
            )

        sondaje = buscar_sondaje(msg)
        if not sondaje:
            return f"❌ No encontré *{msg}*. Verifica o escribe *provisional*.\n"

        # Validar estado de perforación
        estado_perf = _obtener_estado_perforacion(sondaje["bhid"])
        if estado_perf == "FINALIZADO":
            return (
                f"⛔ *{sondaje['bhid']}* está marcado como *FINALIZADO*.\n\n"
                f"Si hay un error, contacta al geólogo para reactivarlo.\n"
            )
        if estado_perf == "SUSPENDIDO":
            return (
                f"⚠️ *{sondaje['bhid']}* está *SUSPENDIDO*.\n\n"
                f"¿Deseas reportar avance de todas formas? (*sí* / *no*)\n"
            )

        # Validar máquina vs sondaje matriculado
        maq_matriculada = _obtener_maquina_sondaje(sondaje["bhid"])
        maq_actual      = datos.get("maquina_cod", "")
        if maq_matriculada and maq_matriculada != maq_actual:
            datos["bhid"]              = sondaje["bhid"]
            datos["maquina_matriculada"] = maq_matriculada
            datos["sondaje_nivel"]     = sondaje.get("nivel", "—")
            datos["sondaje_labor"]     = sondaje.get("labor", "—")
            datos["diametro"]          = sondaje.get("diametro", "NQ")
            datos["prog_m"]            = sondaje.get("prog_m", 0)
            datos["final_m_actual"]    = sondaje.get("final_m") or 0
            actualizar_sesion(sid, "confirmar_maquina", datos)
            return (
                f"⚠️ *Atención — Máquina no coincide*\n\n"
                f"Sondaje *{sondaje['bhid']}* está matriculado para "
                f"*{maq_matriculada}*\nbut estás reportando con *{maq_actual}*.\n\n"
                f"¿Confirmas que es correcto? (*sí* / *no*)\n"
            )

        datos.update({
            "bhid":           sondaje["bhid"],
            "sondaje_nivel":  sondaje.get("nivel", "—"),
            "sondaje_labor":  sondaje.get("labor", "—"),
            "diametro":       sondaje.get("diametro", "NQ"),
            "prog_m":         sondaje.get("prog_m", 0),
            "final_m_actual": sondaje.get("final_m") or 0,
        })
        actualizar_sesion(sid, "turno", datos, sondaje_context=sondaje["bhid"])
        return _msg_sondaje_ok(sondaje)

    # ── Confirmar máquina incorrecta ──────────────────────────
    elif paso == "confirmar_maquina":
        if msg.lower() in ("no", "n"):
            cerrar_sesion(usuario["id"])
            return "❌ Reporte cancelado. Verifica el sondaje correcto."
        if msg.lower() not in ("sí", "si", "yes", "ok"):
            return "¿Confirmas? *sí* o *no*."
        # Continuar con advertencia registrada
        actualizar_sesion(sid, "turno", datos, sondaje_context=datos["bhid"])
        sondaje = buscar_sondaje(datos["bhid"])
        return _msg_sondaje_ok(sondaje)

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
        return f"✅ Inicio: *{prof_ini:.2f} m*\n\n¿*Profundidad final* del turno?\n"

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

        # Detectar si alcanzó profundidad programada
        prog_m = float(datos.get("prog_m") or 0)
        if prog_m > 0 and prof_fin >= prog_m * 0.98:
            datos["posible_fin"] = True

        actualizar_sesion(sid, "cambio_linea", datos)
        return (
            f"✅ Final: *{prof_fin:.2f} m* | Avance: *{avance:.2f} m*\n\n"
            f"¿Hubo *cambio de línea* en este turno?\n"
            f"  *sí* — Registrar cambio\n"
            f"  *no* — Continuar\n"
        )

    # ── Cambio de línea ───────────────────────────────────────
    elif paso == "cambio_linea":
        if msg.lower() in ("no", "n"):
            datos["hubo_cambio_linea"] = False
            # Calcular costo sin cambio
            sufijo = datos.get("sufijo", "")
            diam   = datos.get("diametro", "NQ")
            datos["valor_usd"] = calcular_valor_turno(
                diam, datos["prof_inicio"], datos["prof_final"], sufijo)
            actualizar_sesion(sid, "observaciones", datos)
            return (
                f"¿*Observaciones* del turno?\n"
                f"Escribe las novedades o *ninguna*.\n"
            )
        if msg.lower() in ("sí", "si", "yes", "ok"):
            datos["hubo_cambio_linea"] = True
            datos["linea_anterior"]    = datos.get("diametro", "NQ")
            actualizar_sesion(sid, "linea_nueva", datos)
            return (
                f"📏 Línea actual: *{datos.get('diametro','NQ')}*\n\n"
                f"¿A qué línea cambiaste?\n"
                f"  *1* — BQ\n  *2* — NQ\n  *3* — HQ\n  *4* — PQ\n"
            )
        return "Responde *sí* o *no*."

    # ── Línea nueva ───────────────────────────────────────────
    elif paso == "linea_nueva":
        diams = {"1": "BQ", "2": "NQ", "3": "HQ", "4": "PQ",
                 "bq": "BQ", "nq": "NQ", "hq": "HQ", "pq": "PQ"}
        linea_nueva = diams.get(msg.lower())
        if not linea_nueva:
            return "❓ Responde 1 (BQ), 2 (NQ), 3 (HQ) o 4 (PQ)."
        datos["linea_nueva"] = linea_nueva
        actualizar_sesion(sid, "metro_cambio", datos)
        return (
            f"✅ Nueva línea: *{linea_nueva}*\n\n"
            f"¿En qué *metro exacto* fue el cambio?\n"
            f"Ejemplo: 125.50\n"
        )

    # ── Metro del cambio ──────────────────────────────────────
    elif paso == "metro_cambio":
        try:
            metro = float(msg.replace(",", "."))
            prof_ini = datos.get("prof_inicio", 0)
            prof_fin = datos.get("prof_final", 0)
            if metro < prof_ini or metro > prof_fin:
                return f"❓ Debe estar entre {prof_ini:.2f} y {prof_fin:.2f} m."
            datos["metro_cambio_linea"] = metro
        except ValueError:
            return "❓ Número válido. Ejemplo: 125.50"

        # Calcular costo dividido por tramo
        sufijo        = datos.get("sufijo", "")
        linea_ant     = datos.get("linea_anterior", "NQ")
        linea_nueva   = datos.get("linea_nueva", "BQ")
        prof_ini      = datos["prof_inicio"]
        prof_fin      = datos["prof_final"]

        costo_tramo1  = calcular_valor_turno(linea_ant,   prof_ini, metro,    sufijo)
        costo_tramo2  = calcular_valor_turno(linea_nueva, metro,    prof_fin, sufijo)
        datos["valor_usd"] = costo_tramo1 + costo_tramo2

        # Actualizar diámetro del sondaje al nuevo
        ejecutar(
            "UPDATE sondajes SET diametro = %s WHERE bhid = %s",
            (linea_nueva, datos["bhid"])
        )
        datos["diametro"] = linea_nueva

        actualizar_sesion(sid, "observaciones", datos)
        return (
            f"✅ Cambio de línea registrado:\n"
            f"   {linea_ant} → {linea_nueva} en metro *{metro:.2f} m*\n\n"
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
                       hubo_cambio_linea, linea_anterior,
                       linea_nueva, metro_cambio_linea,
                       reportado_por, fuente, mensaje_original
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'BOT',%s)""",
                (
                    sondaje_id, datos["maquina_id"],
                    datos["fecha"], datos["turno"],
                    datos["prof_inicio"], datos["prof_final"],
                    datos.get("valor_usd"),
                    datos.get("retorno_fluido", "100%"),
                    datos.get("observaciones"),
                    datos.get("foto_url"),
                    datos.get("foto_tramo"),
                    datos.get("hubo_cambio_linea", False),
                    datos.get("linea_anterior"),
                    datos.get("linea_nueva"),
                    datos.get("metro_cambio_linea"),
                    usuario["id"], str(datos)
                )
            )

            # Actualizar profundidad final y estado EN_CURSO
            ejecutar(
                """UPDATE sondajes SET
                       profundidad_final  = %s,
                       estado_perforacion = CASE
                           WHEN estado_perforacion = 'PLANIFICADO' THEN 'EN_CURSO'
                           ELSE estado_perforacion END,
                       fecha_inicio_perf  = COALESCE(fecha_inicio_perf, %s)
                   WHERE bhid = %s""",
                (datos["prof_final"], datos["fecha"], datos["bhid"])
            )

            msg_individual = generar_mensaje_estandarizado(datos)
            empresa_nombre = _obtener_empresa(datos)
            datos["msg_individual"] = msg_individual

            # Verificar si sondaje llegó a profundidad programada
            if datos.get("posible_fin"):
                datos["empresa_nombre"] = empresa_nombre
                actualizar_sesion(sid, "confirmar_fin_sondaje", datos)
                return (
                    f"✅ *Reporte registrado*\n📅 {fecha_hora_str()}\n\n"
                    f"─────────────────────\n"
                    f"📋 *TU REPORTE:*\n_(Copia y reenvía)_\n\n"
                    f"{msg_individual}\n"
                    f"─────────────────────\n\n"
                    f"🎯 *La profundidad final alcanzó el programa.*\n"
                    f"¿El sondaje *{datos['bhid']}* ha finalizado?\n"
                    f"  *sí* — Marcar como FINALIZADO\n"
                    f"  *no* — Continúa perforando\n"
                )

            actualizar_sesion(sid, "reporte_empresa", datos)
            return (
                f"✅ *Reporte registrado*\n📅 {fecha_hora_str()}\n\n"
                f"─────────────────────\n"
                f"📋 *TU REPORTE — {datos.get('maquina_cod','—')}:*\n"
                f"_(Copia y reenvía)_\n\n"
                f"{msg_individual}\n"
                f"─────────────────────\n\n"
                f"¿Generar reporte consolidado de *{empresa_nombre}*?\n"
                f"  *sí* — Generar\n  *no* — Otra máquina\n  *fin* — Terminar\n"
            )

        except Exception as e:
            print(f"[PERFORACION] Error: {e}")
            return "⚠️ Error al guardar. Intenta de nuevo."

    # ── Confirmar fin de sondaje ──────────────────────────────
    elif paso == "confirmar_fin_sondaje":
        if msg.lower() in ("sí", "si", "yes", "ok"):
            ejecutar(
                """UPDATE sondajes SET
                       estado_perforacion = 'FINALIZADO',
                       fecha_fin_perf     = %s
                   WHERE bhid = %s""",
                (datos.get("fecha"), datos["bhid"])
            )
            empresa_nombre = datos.get("empresa_nombre", "tu empresa")
            actualizar_sesion(sid, "reporte_empresa", datos)
            return (
                f"✅ *{datos['bhid']}* marcado como *FINALIZADO* 🎉\n\n"
                f"¿Generar reporte consolidado de *{empresa_nombre}*?\n"
                f"  *sí* — Generar\n  *no* — Otra máquina\n  *fin* — Terminar\n"
            )
        else:
            empresa_nombre = datos.get("empresa_nombre", "tu empresa")
            actualizar_sesion(sid, "reporte_empresa", datos)
            return (
                f"✅ Sondaje continúa en curso.\n\n"
                f"¿Generar reporte consolidado de *{empresa_nombre}*?\n"
                f"  *sí* — Generar\n  *no* — Otra máquina\n  *fin* — Terminar\n"
            )

    # ── Reporte consolidado por empresa ───────────────────────
    elif paso == "reporte_empresa":
        if msg.lower() == "fin":
            cerrar_sesion(usuario["id"])
            return "✅ Sesión cerrada. Escribe *hola* cuando necesites."
        if msg.lower() in ("no", "n", "otra"):
            return _menu_siguiente_maquina(sid, datos)
        if msg.lower() not in ("sí", "si", "yes", "ok"):
            return "  *sí* — Generar\n  *no* — Otra máquina\n  *fin* — Terminar"

        try:
            empresa_id = datos.get("empresa_id", 1)
            fecha      = datos.get("fecha")
            turno      = datos.get("turno")
            rows = ejecutar(
                """SELECT ap.prof_inicio, ap.prof_final, ap.metros_avance,
                          ap.observaciones, m.codigo, s.bhid,
                          s.nivel_prog, s.labor, s.diametro, s.profundidad_prog
                   FROM avance_perforacion ap
                   JOIN sondajes s     ON ap.sondaje_id = s.id
                   JOIN cat_maquinas m ON ap.maquina_id = m.id
                   WHERE m.empresa_id = %s AND ap.fecha = %s
                     AND ap.turno = %s AND ap.estado = 'ACTIVO'
                   ORDER BY m.codigo""",
                (empresa_id, fecha, turno), fetchall=True
            )
            if not rows:
                actualizar_sesion(sid, "reporte_empresa", datos)
                return "⚠️ Aún no hay reportes de otras máquinas.\n\n  *no* — Otra máquina\n  *fin* — Terminar"

            reportes = [{
                "prof_inicio": float(r[0] or 0), "prof_final": float(r[1] or 0),
                "avance": float(r[2] or 0), "observaciones": r[3] or "Sin novedades",
                "maquina_cod": r[4], "bhid": r[5], "sondaje_nivel": r[6],
                "sondaje_labor": r[7], "diametro": r[8], "prog_m": r[9],
                "turno": turno, "fecha": fecha,
            } for r in rows]

            emp_row = ejecutar("SELECT nombre FROM cat_empresas WHERE id = %s",
                               (empresa_id,), fetchone=True)
            empresa_nombre = emp_row[0] if emp_row else "Empresa"
            consolidado    = generar_reporte_empresa(reportes, empresa_nombre, fecha)
            actualizar_sesion(sid, "post_consolidado", datos)
            return (
                f"─────────────────────\n"
                f"🏢 *{empresa_nombre.upper()} — TURNO {turno}*\n"
                f"_(Copia y reenvía)_\n\n{consolidado}\n"
                f"─────────────────────\n\n"
                f"¿Registrar otra máquina?\n  *sí* — Continuar\n  *no* — Terminar\n"
            )
        except Exception as e:
            print(f"[PERFORACION] Error consolidado: {e}")
            cerrar_sesion(usuario["id"])
            return "⚠️ Error generando consolidado."

    # ── Post consolidado ──────────────────────────────────────
    elif paso == "post_consolidado":
        if msg.lower() in ("no", "n", "fin", "terminar"):
            cerrar_sesion(usuario["id"])
            return "✅ Listo. Escribe *hola* cuando necesites."
        if msg.lower() in ("sí", "si", "yes", "ok"):
            return _menu_siguiente_maquina(sid, datos)
        return "*sí* para continuar o *no* para terminar."

    return "❓ Escribe *hola* para reiniciar."


# ── HELPERS ───────────────────────────────────────────────────

def _msg_sondaje_ok(sondaje: dict) -> str:
    estado = sondaje.get("estado_perforacion", "")
    estado_str = ""
    if estado == "PLANIFICADO":
        estado_str = "\n   🔵 Estado: PLANIFICADO (primer avance)"
    elif estado == "EN_CURSO":
        estado_str = "\n   🟢 Estado: EN CURSO"
    return (
        f"✅ Sondaje: *{sondaje['bhid']}*\n"
        f"   Nv.{sondaje.get('nivel','—')} | {sondaje.get('labor','—')}"
        f"{estado_str}\n"
        f"   Prog: {sondaje.get('prog_m','—')} m | "
        f"Actual: {sondaje.get('final_m') or 0:.1f} m\n\n"
        f"¿Qué turno reportas?\n  *1* — Día\n  *2* — Noche\n"
    )

def _menu_siguiente_maquina(sid: int, datos: dict) -> str:
    maquinas = obtener_maquinas_activas()
    menu = "\n".join([f"  *{i+1}* — {m['codigo']} ({m['empresa']})"
                      for i, m in enumerate(maquinas)])
    datos_nueva = {
        "empresa_id": datos.get("empresa_id"),
        "turno":      datos.get("turno"),
        "fecha":      datos.get("fecha"),
        "maquina_opciones": [(m["id"], m["codigo"],
                               m["empresa"]) for m in maquinas],
    }
    actualizar_sesion(sid, "maquina", datos_nueva)
    return (
        f"⛏️ *SIGUIENTE MÁQUINA*\n"
        f"Turno: *{datos.get('turno','—')}* | {datos.get('fecha','—')}\n\n"
        f"{menu}\n\nResponde con el número.\n"
    )

def _mostrar_resumen(datos: dict) -> str:
    cambio_str = ""
    if datos.get("hubo_cambio_linea"):
        cambio_str = (
            f"\n🔄 Cambio línea: {datos.get('linea_anterior','—')} → "
            f"{datos.get('linea_nueva','—')} "
            f"en {datos.get('metro_cambio_linea',0):.1f} m"
        )
    return (
        f"📋 *RESUMEN DEL REPORTE*\n{'─'*30}\n"
        f"🔖 Sondaje:  *{datos.get('bhid','—')}*\n"
        f"🚜 Máquina:  {datos.get('maquina_cod','—')}\n"
        f"⏱️ Turno:    {datos.get('turno','—')} | {datos.get('fecha','—')}\n"
        f"📏 Desde:    {datos.get('prof_inicio',0):.2f} m\n"
        f"📏 Hasta:    {datos.get('prof_final',0):.2f} m\n"
        f"➡️ Avance:   *{datos.get('avance',0):.2f} m*"
        f"{cambio_str}\n"
        f"📝 Obs:      {datos.get('observaciones','Ninguna') or 'Ninguna'}\n"
        f"📸 Foto:     {'✅' if datos.get('foto_url') else 'No'}\n"
        f"{'─'*30}\n\n¿Confirmas? (*sí* / *no*)\n"
    )

def _obtener_sondaje_id(bhid: str) -> int | None:
    row = ejecutar("SELECT id FROM sondajes WHERE bhid = %s",
                   (bhid,), fetchone=True)
    return row[0] if row else None

def _obtener_empresa(datos: dict) -> str:
    row = ejecutar("SELECT codigo FROM cat_empresas WHERE id = %s",
                   (datos.get("empresa_id", 1),), fetchone=True)
    return row[0] if row else "tu empresa"

def _obtener_estado_perforacion(bhid: str) -> str:
    row = ejecutar("SELECT estado_perforacion FROM sondajes WHERE bhid = %s",
                   (bhid,), fetchone=True)
    return row[0] if row else "PLANIFICADO"

def _obtener_maquina_sondaje(bhid: str) -> str | None:
    row = ejecutar(
        """SELECT m.codigo FROM sondajes s
           JOIN cat_maquinas m ON s.maquina_id = m.id
           WHERE s.bhid = %s""",
        (bhid,), fetchone=True
    )
    return row[0] if row else None
