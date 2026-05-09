"""
FLUJO DE REPORTE DE AVANCE DE PERFORACIÓN v3
Fixes:
1. Validación máquina: muestra sondaje activo de esa máquina
2. Flujo post-consolidado corregido
3. Advertencia en sondaje provisional si máquina tiene activo
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
            # Mostrar sondaje activo en esta máquina
            activo = _sondaje_activo_en_maquina(datos.get("maquina_id"))
            if activo:
                return (
                    f"❌ No encontré *{msg}*.\n\n"
                    f"La máquina *{datos.get('maquina_cod','—')}* "
                    f"tiene activo:\n"
                    f"  🔖 *{activo['bhid']}* | {activo['objetivo']}\n"
                    f"  📏 {activo['final_m']:.1f}/{activo['prog_m']:.1f} m\n\n"
                    f"¿Era ese? Escríbelo de nuevo o usa *{activo['bhid'][-4:]}*\n"
                )
            return f"❌ No encontré *{msg}*. Verifica el código o escribe *provisional*.\n"

        # Validar estado
        estado_perf = sondaje.get("estado_perforacion") or \
                      _obtener_estado_perforacion(sondaje["bhid"])
        if estado_perf == "FINALIZADO":
            return (
                f"⛔ *{sondaje['bhid']}* está *FINALIZADO*.\n\n"
                f"Contacta al geólogo si hay un error.\n"
            )

        # Validar máquina vs sondaje matriculado
        maq_matriculada = _obtener_maquina_sondaje(sondaje["bhid"])
        maq_actual      = datos.get("maquina_cod", "")
        if maq_matriculada and maq_matriculada != maq_actual:
            # Mostrar también qué sondaje corresponde a esta máquina
            activo = _sondaje_activo_en_maquina(datos.get("maquina_id"))
            aviso_activo = ""
            if activo:
                aviso_activo = (
                    f"\n\n📌 El sondaje activo de *{maq_actual}* es:\n"
                    f"  🔖 *{activo['bhid']}* | {activo['objetivo']}\n"
                    f"  📏 {activo['final_m']:.1f}/{activo['prog_m']:.1f} m"
                )
            datos.update({
                "bhid":               sondaje["bhid"],
                "maquina_matriculada": maq_matriculada,
                "sondaje_nivel":      sondaje.get("nivel", "—"),
                "sondaje_labor":      sondaje.get("labor", "—"),
                "diametro":           sondaje.get("diametro", "NQ"),
                "prog_m":             sondaje.get("prog_m", 0),
                "final_m_actual":     sondaje.get("final_m") or 0,
            })
            actualizar_sesion(sid, "confirmar_maquina", datos)
            return (
                f"⚠️ *{sondaje['bhid']}* está matriculado para "
                f"*{maq_matriculada}*, no para *{maq_actual}*."
                f"{aviso_activo}\n\n"
                f"¿Confirmas igualmente? (*sí* / *no*)\n"
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
            # Mostrar sondaje correcto de esta máquina
            activo = _sondaje_activo_en_maquina(datos.get("maquina_id"))
            if activo:
                actualizar_sesion(sid, "sondaje", datos)
                return (
                    f"El sondaje activo de *{datos.get('maquina_cod','—')}* es:\n"
                    f"  🔖 *{activo['bhid']}* | {activo['objetivo']}\n"
                    f"  📏 {activo['final_m']:.1f}/{activo['prog_m']:.1f} m\n\n"
                    f"Escribe el código correcto:\n"
                )
            actualizar_sesion(sid, "sondaje", datos)
            return "❌ Cancelado. Escribe el código correcto del sondaje:\n"
        if msg.lower() not in ("sí", "si", "yes", "ok"):
            return "¿Confirmas? *sí* o *no*."
        actualizar_sesion(sid, "turno", datos, sondaje_context=datos["bhid"])
        sondaje = buscar_sondaje(datos["bhid"])
        return _msg_sondaje_ok(sondaje)

    # ── Turno ─────────────────────────────────────────────────
    elif paso == "turno":
        turnos = {"1": "DIA", "2": "NOCHE", "dia": "DIA", "día": "DIA",
          "noche": "NOCHE", "d": "DIA", "n": "NOCHE",
          "☀️ día": "DIA", "☀️ dia": "DIA", "🌙 noche": "NOCHE",
          "día": "DIA", "dia": "DIA"}
        turno = turnos.get(msg.lower())
        if not turno:
            return "❓ Responde *1* (Día) o *2* (Noche)."
        datos["turno"] = turno

        # Fix fecha turno NOCHE: si reportan entre 00:00 y 10:00am
        # el turno corresponde al día anterior
        hora_actual = _hora()
        if turno == "NOCHE" and hora_actual.hour < 10:
            from datetime import timedelta
            fecha_reporte = (hora_actual - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            fecha_reporte = hora_actual.strftime("%Y-%m-%d")
        datos["fecha"] = fecha_reporte

        # Validar turno duplicado
        duplicado = _verificar_turno_duplicado(
            datos.get("bhid"), fecha_reporte, turno
        )
        if duplicado:
            cerrar_sesion(usuario["id"])
            return (
                f"⚠️ *Ya existe un reporte {turno} del {duplicado['fecha_fmt']}*\n"
                f"para *{datos.get('bhid','—')}*:\n"
                f"  📏 {duplicado['prof_inicio']:.2f} → {duplicado['prof_final']:.2f} m "
                f"| +{duplicado['avance']:.2f} m\n"
                f"  🚜 {duplicado['maquina']} | 👤 {duplicado['reportado_por']}\n\n"
                f"Si hubo un error, escribe *anular reporte* para eliminarlo\n"
                f"y luego vuelve a reportar.\n"
            )

        # Cargar último avance registrado para pre-llenar prof_inicio
        ultimo = _ultimo_avance_sondaje(datos.get("bhid"))
        if ultimo:
            datos["ultimo_avance_id"]        = ultimo["id"]
            datos["ultimo_prof_inicio"]      = ultimo["prof_inicio"]
            datos["ultimo_prof_final"]       = ultimo["prof_final"]
            datos["prof_inicio_sugerido"]    = ultimo["prof_final"]
            actualizar_sesion(sid, "prof_inicio", datos)
            return (
                f"✅ Turno: *{turno}* | 📅 {hora_actual.strftime('%d/%m/%Y')}\n\n"
                f"📏 Último metraje registrado: *{ultimo['prof_final']:.2f} m*\n"
                f"¿Confirmas que inicias desde ahí?\n"
                f"  *sí* — Usar {ultimo['prof_final']:.2f} m\n"
                f"  *no* — Ingresar valor correcto\n"
            )

        actualizar_sesion(sid, "prof_inicio", datos)
        return (
            f"✅ Turno: *{turno}* | 📅 {hora_actual.strftime('%d/%m/%Y')}\n\n"
            f"¿*Profundidad inicio* del turno (metros)?\n"
        )

    # ── Turno duplicado ──────────────────────────────────────
    elif paso == "turno_duplicado":
        if msg.lower() in ("cancelar", "no", "n"):
            cerrar_sesion(usuario["id"])
            return "❌ Reporte cancelado. Escribe *hola* cuando necesites."
        if msg.lower() not in ("corregir", "si", "sí", "ok"):
            return (
                f"¿Qué deseas hacer?\n"
                f"  *corregir* — Reemplazar el reporte existente\n"
                f"  *cancelar* — Salir sin cambios\n"
            )
        # Anular el avance duplicado y continuar
        dup_id = datos.get("duplicado_id")
        if dup_id:
            ejecutar(
                "UPDATE avance_perforacion SET estado = 'ANULADO' WHERE id = %s",
                (dup_id,)
            )
        # Continuar con prof_inicio usando el último avance anterior al anulado
        ultimo = _ultimo_avance_sondaje(datos.get("bhid"))
        if ultimo:
            datos["ultimo_avance_id"]     = ultimo["id"]
            datos["ultimo_prof_inicio"]   = ultimo["prof_inicio"]
            datos["ultimo_prof_final"]    = ultimo["prof_final"]
            datos["prof_inicio_sugerido"] = ultimo["prof_final"]
            actualizar_sesion(sid, "prof_inicio", datos)
            return (
                f"✅ Reporte anterior anulado. Ingresa los datos correctos.\n\n"
                f"📏 Último metraje registrado: *{ultimo['prof_final']:.2f} m*\n"
                f"¿Confirmas que inicias desde ahí?\n"
                f"  *sí* — Usar {ultimo['prof_final']:.2f} m\n"
                f"  *no* — Ingresar valor correcto\n"
            )
        actualizar_sesion(sid, "prof_inicio", datos)
        return "✅ Reporte anterior anulado.\n\n¿*Profundidad inicio* del turno (metros)?\n"

    # ── Profundidad inicio ────────────────────────────────────
    elif paso == "prof_inicio":
        sugerido        = datos.get("prof_inicio_sugerido")
        ultimo_ini      = datos.get("ultimo_prof_inicio", 0)
        ultimo_avance_id = datos.get("ultimo_avance_id")

        # Tiene metraje previo → espera sí/no o valor corregido
        if sugerido is not None:
            if msg.lower() in ("sí", "si", "yes", "ok", "s"):
                # Confirma el valor sugerido
                datos["prof_inicio"] = float(sugerido)
                datos.pop("prof_inicio_sugerido", None)
                actualizar_sesion(sid, "prof_final", datos)
                return f"✅ Inicio confirmado: *{float(sugerido):.2f} m*\n\n¿*Profundidad final* del turno?\n"

            if msg.lower() in ("no", "n"):
                # Pide el valor correcto
                actualizar_sesion(sid, "prof_inicio", datos)
                return (
                    f"📏 Ingresa el metraje correcto de inicio:\n"
                    f"   (Debe ser mayor a {float(ultimo_ini):.2f} m, "
                    f"que fue el inicio del turno anterior)\n"
                )

            # Intentar parsear como número (valor corregido)
            try:
                prof_ini = float(msg.replace(",", "."))
                if prof_ini < float(ultimo_ini):
                    return (
                        f"❌ El valor no puede ser menor a *{float(ultimo_ini):.2f} m*\n"
                        f"   (inicio del turno anterior — los metrajes se cruzarían)\n"
                        f"Ingresa un valor mayor a {float(ultimo_ini):.2f} m:\n"
                    )
                # Valor válido — actualizar prof_final del turno anterior
                if ultimo_avance_id and prof_ini != float(sugerido):
                    ejecutar(
                        "UPDATE avance_perforacion SET prof_final = %s WHERE id = %s",
                        (prof_ini, ultimo_avance_id)
                    )
                    ejecutar(
                        "UPDATE sondajes SET profundidad_final = %s WHERE bhid = %s",
                        (prof_ini, datos.get("bhid"))
                    )
                    aviso_correccion = f"⚠️ Metraje anterior corregido: {float(sugerido):.2f} → *{prof_ini:.2f} m*\n\n"
                else:
                    aviso_correccion = ""
                datos["prof_inicio"] = prof_ini
                datos.pop("prof_inicio_sugerido", None)
                actualizar_sesion(sid, "prof_final", datos)
                return f"{aviso_correccion}✅ Inicio: *{prof_ini:.2f} m*\n\n¿*Profundidad final* del turno?\n"
            except ValueError:
                return (
                    f"❓ Responde *sí* para confirmar {float(sugerido):.2f} m, "
                    f"*no* para ingresar otro valor, o escribe el número directamente.\n"
                )

        # Sin metraje previo → flujo normal
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
            if prof_fin < datos.get("prof_inicio", 0):
                return f"❓ Debe ser mayor o igual a {datos['prof_inicio']:.2f} m."
            datos["prof_final"] = prof_fin
        except ValueError:
            return "❓ Número válido."

        avance = prof_fin - datos["prof_inicio"]
        datos["avance"]         = round(avance, 2)
        datos["retorno_fluido"] = "100%"

        prog_m = float(datos.get("prog_m") or 0)
        if prog_m > 0 and prof_fin >= prog_m * 0.98:
            datos["posible_fin"] = True

        actualizar_sesion(sid, "fin_sondaje_manual", datos)
        return (
            f"✅ Final: *{prof_fin:.2f} m* | Avance: *{avance:.2f} m*\n\n"
            f"¿El sondaje *{datos.get('bhid','—')}* ha *finalizado*?\n"
            f"  *sí* — Marcar FINALIZADO\n"
            f"  *no* — Continúa perforando\n"
        )

    # ── Fin sondaje manual (siempre se pregunta) ──────────────
    elif paso == "fin_sondaje_manual":
        if msg.lower() in ("sí", "si", "yes", "ok"):
            datos["fin_manual"] = True
        elif msg.lower() in ("no", "n"):
            datos["fin_manual"] = False
        else:
            return (
                f"¿El sondaje *{datos.get('bhid','—')}* ha finalizado?\n"
                f"  *sí* — Marcar FINALIZADO\n"
                f"  *no* — Continúa perforando\n"
            )
        actualizar_sesion(sid, "cambio_linea", datos)
        return (
            f"¿Hubo *cambio de línea* en este turno?\n"
            f"  *sí* — Registrar cambio\n"
            f"  *no* — Continuar\n"
        )

    # ── Cambio de línea ───────────────────────────────────────
    elif paso == "cambio_linea":
        if msg.lower() in ("no", "n"):
            datos["hubo_cambio_linea"] = False
            sufijo = datos.get("sufijo", "")
            diam   = datos.get("diametro", "NQ")
            datos["valor_usd"] = calcular_valor_turno(
                diam, datos["prof_inicio"], datos["prof_final"], sufijo)
            actualizar_sesion(sid, "observaciones", datos)
            return "¿*Observaciones* del turno?\nEscribe las novedades o *ninguna*.\n"
        if msg.lower() in ("sí", "si", "yes", "ok"):
            datos["hubo_cambio_linea"] = True
            datos["linea_anterior"]    = datos.get("diametro", "NQ")
            diam_actual = datos.get("diametro", "NQ")

            # Secuencia de reducción: PQ→HQ→NQ→BQ
            opciones_reduccion = {
                "PQ": [("1","HQ"), ("2","NQ"), ("3","BQ")],
                "HQ": [("1","NQ"), ("2","BQ")],
                "NQ": [("1","BQ")],
                "BQ": [],
            }
            opciones = opciones_reduccion.get(diam_actual, [])

            if not opciones:
                datos["hubo_cambio_linea"] = False
                actualizar_sesion(sid, "observaciones", datos)
                return (
                    f"⛔ *BQ* es el diámetro mínimo, no hay reducción posible.\n\n"
                    f"¿*Observaciones* del turno?\nEscribe las novedades o *ninguna*.\n"
                )

            menu_lineas = "\n".join([f"  *{n}* — {d}" for n, d in opciones])
            datos["lineas_opciones"] = opciones
            actualizar_sesion(sid, "linea_nueva", datos)
            return (
                f"📏 Línea actual: *{diam_actual}*\n\n"
                f"¿A qué línea cambiaste?\n{menu_lineas}\n"
            )
        return "Responde *sí* o *no*."

    # ── Línea nueva ───────────────────────────────────────────
    elif paso == "linea_nueva":
        opciones = datos.get("lineas_opciones", [])
        # Construir mapa dinámico con las opciones permitidas
        mapa = {n: d for n, d in opciones}
        # También aceptar el nombre directo
        for _, d in opciones:
            mapa[d.lower()] = d
        linea_nueva = mapa.get(msg.lower()) or mapa.get(msg.upper())
        if not linea_nueva:
            menu_lineas = "\n".join([f"  *{n}* — {d}" for n, d in opciones])
            return f"❓ Opción no válida. Elige:\n{menu_lineas}\n"
        datos["linea_nueva"] = linea_nueva
        actualizar_sesion(sid, "metro_cambio", datos)
        return f"✅ Nueva línea: *{linea_nueva}*\n\n¿En qué *metro exacto* fue el cambio?\nEjemplo: 125.50\n"

    # ── Metro del cambio ──────────────────────────────────────
    elif paso == "metro_cambio":
        try:
            metro    = float(msg.replace(",", "."))
            prof_ini = datos.get("prof_inicio", 0)
            prof_fin = datos.get("prof_final", 0)
            if metro < prof_ini or metro > prof_fin:
                return f"❓ Debe estar entre {prof_ini:.2f} y {prof_fin:.2f} m."
            datos["metro_cambio_linea"] = metro
        except ValueError:
            return "❓ Número válido. Ejemplo: 125.50"

        sufijo      = datos.get("sufijo", "")
        linea_ant   = datos.get("linea_anterior", "NQ")
        linea_nueva = datos.get("linea_nueva", "BQ")
        costo1      = calcular_valor_turno(linea_ant,   datos["prof_inicio"], metro,              sufijo)
        costo2      = calcular_valor_turno(linea_nueva, metro,                datos["prof_final"], sufijo)
        datos["valor_usd"] = costo1 + costo2

        ejecutar("UPDATE sondajes SET diametro = %s WHERE bhid = %s",
                 (linea_nueva, datos["bhid"]))
        datos["diametro"] = linea_nueva

        actualizar_sesion(sid, "observaciones", datos)
        return (
            f"✅ Cambio registrado: {linea_ant} → {linea_nueva} en *{metro:.2f} m*\n\n"
            f"¿*Observaciones* del turno?\nEscribe las novedades o *ninguna*.\n"
        )

    # ── Observaciones ─────────────────────────────────────────
    elif paso == "observaciones":
        datos["observaciones"] = "" if msg.lower() == "ninguna" else msg
        actualizar_sesion(sid, "foto", datos)
        return "📸 ¿Adjuntar foto?\nEnvía la foto o escribe *no*.\n"

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
                    datos.get("retorno_fluido","100%"),
                    datos.get("observaciones"),
                    datos.get("foto_url"), datos.get("foto_tramo"),
                    datos.get("hubo_cambio_linea", False),
                    datos.get("linea_anterior"), datos.get("linea_nueva"),
                    datos.get("metro_cambio_linea"),
                    usuario["id"], str(datos)
                )
            )
            ejecutar(
                """UPDATE sondajes SET
                       profundidad_final  = %s,
                       estado_perforacion = CASE
                           WHEN estado_perforacion = 'PLANIFICADO' THEN 'EN_CURSO'
                           ELSE estado_perforacion END,
                       fecha_inicio_perf = COALESCE(fecha_inicio_perf, %s)
                   WHERE bhid = %s""",
                (datos["prof_final"], datos["fecha"], datos["bhid"])
            )

            msg_individual = generar_mensaje_estandarizado(datos)
            empresa_nombre = _obtener_empresa(datos)
            datos["msg_individual"]  = msg_individual
            datos["empresa_nombre"]  = empresa_nombre

            reporte_base = (
                f"✅ *Reporte registrado*\n📅 {fecha_hora_str()}\n\n"
                f"─────────────────────\n"
                f"📋 *TU REPORTE — {datos.get('maquina_cod','—')}:*\n"
                f"_(Copia y reenvía)_\n\n"
                f"{msg_individual}\n"
                f"─────────────────────\n\n"
            )

            # Sondaje marcado como finalizado por el perforista
            if datos.get("fin_manual"):
                ejecutar(
                    "UPDATE sondajes SET estado_perforacion='FINALIZADO', fecha_fin_perf=%s WHERE bhid=%s",
                    (datos.get("fecha"), datos["bhid"])
                )
                datos["es_fin"] = True
                reporte_base += f"🎉 *{datos['bhid']}* marcado como *FINALIZADO*\n\n"

            actualizar_sesion(sid, "reporte_empresa", datos)
            return (
                reporte_base +
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
                "UPDATE sondajes SET estado_perforacion='FINALIZADO', fecha_fin_perf=%s WHERE bhid=%s",
                (datos.get("fecha"), datos["bhid"])
            )
            datos["es_fin"] = True
            msg_extra = f"✅ *{datos['bhid']}* marcado como *FINALIZADO* 🎉\n\n"
        else:
            msg_extra = "✅ Sondaje continúa en curso.\n\n"

        empresa_nombre = datos.get("empresa_nombre", "tu empresa")
        actualizar_sesion(sid, "reporte_empresa", datos)
        return (
            msg_extra +
            f"¿Generar reporte consolidado de *{empresa_nombre}*?\n"
            f"  *sí* — Generar\n  *no* — Otra máquina\n  *fin* — Terminar\n"
        )

    # ── Reporte consolidado ───────────────────────────────────
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
                """SELECT ap.prof_inicio, ap.prof_final,
                          (ap.prof_final - ap.prof_inicio) AS avance,
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
                # No hay más reportes — terminar directamente
                cerrar_sesion(usuario["id"])
                return (
                    f"⚠️ Solo hay un reporte registrado para este turno.\n"
                    f"El reporte individual ya fue enviado. ✅\n\n"
                    f"Escribe *hola* cuando necesites."
                )

            reportes = [{
                "prof_inicio": float(r[0] or 0), "prof_final": float(r[1] or 0),
                "avance": float(r[2] or 0), "observaciones": r[3] or "",
                "maquina_cod": r[4], "bhid": r[5], "sondaje_nivel": r[6],
                "sondaje_labor": r[7], "diametro": r[8], "prog_m": r[9],
                "turno": turno, "fecha": fecha,
            } for r in rows]

            # Detectar máquinas de la empresa que NO reportaron
            maquinas_empresa = ejecutar(
                """SELECT codigo FROM cat_maquinas
                   WHERE empresa_id = %s AND activo = TRUE""",
                (empresa_id,), fetchall=True
            )
            maquinas_reportaron = {r["maquina_cod"] for r in reportes}
            sin_reporte = [
                m[0] for m in (maquinas_empresa or [])
                if m[0] not in maquinas_reportaron
            ]

            emp_row = ejecutar("SELECT nombre FROM cat_empresas WHERE id=%s",
                               (empresa_id,), fetchone=True)
            empresa_nombre = emp_row[0] if emp_row else "Empresa"
            consolidado    = generar_reporte_empresa(
                reportes, empresa_nombre, fecha,
                maquinas_sin_reporte=sin_reporte
            )

            # Después del consolidado → terminar o registrar otra máquina
            actualizar_sesion(sid, "post_consolidado", datos)
            return (
                f"─────────────────────\n"
                f"🏢 *{empresa_nombre.upper()} — TURNO {turno}*\n"
                f"_(Copia y reenvía)_\n\n{consolidado}\n"
                f"─────────────────────\n\n"
                f"¿Registrar otra máquina?\n"
                f"  *sí* — Continuar\n  *no* — Terminar\n"
            )
        except Exception as e:
            print(f"[PERFORACION] Error consolidado: {e}")
            cerrar_sesion(usuario["id"])
            return "⚠️ Error generando consolidado. Tu reporte ya fue guardado."

    # ── Post consolidado ──────────────────────────────────────
    elif paso == "post_consolidado":
        if msg.lower() in ("no", "n", "fin", "terminar"):
            cerrar_sesion(usuario["id"])
            return "✅ Listo. Escribe *hola* cuando necesites."
        if msg.lower() in ("sí", "si", "yes", "ok"):
            return _menu_siguiente_maquina(sid, datos)
        return "*sí* para otra máquina o *no* para terminar."

    # ── Anular último reporte ─────────────────────────────────
    elif paso == "anular_reporte":
        if msg.lower() in ("no", "cancelar", "n"):
            cerrar_sesion(usuario["id"])
            return "❌ Cancelado. El reporte sigue activo."
        if msg.lower() not in ("sí", "si", "yes", "ok", "confirma"):
            return "¿Confirmas la anulación? *sí* o *no*."

        reporte_id = datos.get("reporte_id")
        if not reporte_id:
            cerrar_sesion(usuario["id"])
            return "⚠️ No se encontró el reporte. Intenta de nuevo."

        row = ejecutar(
            "SELECT estado FROM avance_perforacion WHERE id = %s",
            (reporte_id,), fetchone=True
        )
        if not row or row[0] != "ACTIVO":
            cerrar_sesion(usuario["id"])
            return "⚠️ El reporte ya no está activo."

        ejecutar(
            "UPDATE avance_perforacion SET estado = \'ANULADO\' WHERE id = %s",
            (reporte_id,)
        )

        bhid = datos.get("bhid")
        anterior = ejecutar(
            "SELECT prof_final FROM avance_perforacion "
            "WHERE sondaje_id = (SELECT id FROM sondajes WHERE bhid = %s) "
            "AND estado = \'ACTIVO\' ORDER BY id DESC LIMIT 1",
            (bhid,), fetchone=True
        )
        nueva_prof = float(anterior[0]) if anterior else None
        if nueva_prof is not None:
            ejecutar(
                "UPDATE sondajes SET profundidad_final = %s WHERE bhid = %s",
                (nueva_prof, bhid)
            )

        cerrar_sesion(usuario["id"])
        cerrar_sesion(usuario["id"])
        bhid_r  = datos.get("bhid", "—")
        turno_r = datos.get("turno", "—")
        fecha_r = datos.get("fecha_fmt", "—")
        pi_r    = float(datos.get("prof_inicio", 0))
        pf_r    = float(datos.get("prof_final", 0))
        return (
            f"✅ *Reporte anulado*\n\n"
            f"🔖 {bhid_r} | {turno_r} {fecha_r}\n"
            f"📏 {pi_r:.2f} → {pf_r:.2f} m\n\n"
            f"Ya puedes volver a reportar este turno.\n"
            f"Escribe *perforación* para continuar."
        )

    return "❓ Escribe *hola* para reiniciar."


# ── HELPERS ───────────────────────────────────────────────────

def _sondaje_activo_en_maquina(maquina_id: int) -> dict | None:
    """Retorna el sondaje EN_CURSO de una máquina específica."""
    if not maquina_id:
        return None
    row = ejecutar(
        """SELECT s.bhid, s.profundidad_prog, s.profundidad_final,
                  s.tajo_objetivo, s.cuerpo_objetivo
           FROM sondajes s
           WHERE s.maquina_id = %s
             AND s.estado_perforacion = 'EN_CURSO'
           ORDER BY s.fecha_inicio_perf DESC LIMIT 1""",
        (maquina_id,), fetchone=True
    )
    if not row:
        return None
    return {
        "bhid":     row[0],
        "prog_m":   float(row[1] or 0),
        "final_m":  float(row[2] or 0),
        "objetivo": row[3] or row[4] or "—",
    }

def _msg_sondaje_ok(sondaje: dict) -> str:
    estado = sondaje.get("estado_perforacion", "") if sondaje else ""
    estado_str = ""
    if estado == "PLANIFICADO":
        estado_str = "\n   🔵 Primer avance — iniciará EN CURSO"
    elif estado == "EN_CURSO":
        estado_str = "\n   🟢 EN CURSO"
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
        "empresa_id":      datos.get("empresa_id"),
        "turno":           datos.get("turno"),
        "fecha":           datos.get("fecha"),
        "maquina_opciones":[(m["id"], m["codigo"],
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
    row = ejecutar("SELECT id FROM sondajes WHERE bhid=%s", (bhid,), fetchone=True)
    return row[0] if row else None

def _obtener_empresa(datos: dict) -> str:
    row = ejecutar("SELECT codigo FROM cat_empresas WHERE id=%s",
                   (datos.get("empresa_id",1),), fetchone=True)
    return row[0] if row else "tu empresa"

def _obtener_estado_perforacion(bhid: str) -> str:
    row = ejecutar("SELECT estado_perforacion FROM sondajes WHERE bhid=%s",
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

def _verificar_turno_duplicado(bhid: str, fecha: str, turno: str) -> dict | None:
    """Verifica si ya existe un reporte activo para ese sondaje+fecha+turno."""
    if not bhid or not fecha or not turno:
        return None
    row = ejecutar(
        """SELECT ap.id, ap.prof_inicio, ap.prof_final,
                  ap.fecha, m.codigo, u.nombre
           FROM avance_perforacion ap
           JOIN sondajes s      ON ap.sondaje_id = s.id
           JOIN cat_maquinas m  ON ap.maquina_id = m.id
           LEFT JOIN usuarios_bot u ON ap.reportado_por = u.id
           WHERE s.bhid = %s AND ap.fecha = %s
             AND ap.turno = %s AND ap.estado = 'ACTIVO'
           ORDER BY ap.id DESC LIMIT 1""",
        (bhid, fecha, turno), fetchone=True
    )
    if not row:
        return None
    prof_ini = float(row[1] or 0)
    prof_fin = float(row[2] or 0)
    try:
        from datetime import datetime
        fecha_fmt = datetime.strptime(str(row[3]), "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        fecha_fmt = str(row[3])
    return {
        "id":            row[0],
        "prof_inicio":   prof_ini,
        "prof_final":    prof_fin,
        "avance":        round(prof_fin - prof_ini, 2),
        "fecha_fmt":     fecha_fmt,
        "maquina":       row[4] or "—",
        "reportado_por": row[5] or "—",
    }

def _ultimo_avance_sondaje(bhid: str) -> dict | None:
    """Retorna el último avance registrado de un sondaje con id, prof_inicio y prof_final."""
    if not bhid:
        return None
    row = ejecutar(
        """SELECT ap.id, ap.prof_inicio, ap.prof_final
           FROM avance_perforacion ap
           JOIN sondajes s ON ap.sondaje_id = s.id
           WHERE s.bhid = %s AND ap.estado = 'ACTIVO'
           ORDER BY ap.fecha DESC, ap.id DESC
           LIMIT 1""",
        (bhid,), fetchone=True
    )
    if not row:
        return None
    return {
        "id":          row[0],
        "prof_inicio": float(row[1] or 0),
        "prof_final":  float(row[2] or 0),
    }
