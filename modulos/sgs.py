"""
FLUJO SGS — Logueo, Muestreo, RQD, Fotografía, Densidad
Para rol SGS y ADMIN.

v2 — LOGUEO mejorado:
  - Ficha completa del sondaje al buscarlo
  - Pre-carga el último metro logueado como "desde_m"
  - Técnico = usuario WhatsApp (nombre + id)
  - Comentario opcional por tramo
  - Foto opcional (Cloudinary, cualquier imagen)
  - Finalización: marca estado_logueo = COMPLETADO
  - Consultas sin sesión: activos, finalizados mes, pendientes logueo
"""
from db.sesiones import actualizar_sesion, cerrar_sesion
from db.sondajes import buscar_sondaje, actualizar_estado_etapa
from db.conexion import ejecutar
from config import fecha_hora_str, hora_peru, ETAPAS_SGS

FLUJO = "SGS"


# ══════════════════════════════════════════════════════════════
# INICIO
# ══════════════════════════════════════════════════════════════

def iniciar(usuario: dict, sesion_id: int) -> None:
    """
    Router ya envió menu_etapas_sgs() — solo inicializa el paso.
    Retorna None para que router no envíe texto duplicado.
    """
    actualizar_sesion(sesion_id, "tipo_etapa", {})
    return None


# ══════════════════════════════════════════════════════════════
# PROCESADOR PRINCIPAL
# ══════════════════════════════════════════════════════════════

def procesar(mensaje: str, usuario: dict, sesion: dict,
             foto_url: str = None) -> str:
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    # ── Foto recibida en paso foto_logueo ─────────────────────
    if foto_url and paso == "foto_logueo":
        datos["foto_url"] = foto_url
        datos["foto_descripcion"] = (
            f"Logueo tramo {datos.get('desde_m', 0):.1f}"
            f"-{datos.get('hasta_m', 0):.1f}m"
        )
        actualizar_sesion(sid, "confirmacion_logueo", datos)
        return _resumen_logueo(datos)

    # ── Foto recibida en paso foto_opcional (otras etapas) ────
    if foto_url and paso == "foto_opcional":
        datos["foto_url"] = foto_url
        datos["foto_descripcion"] = (
            f"Tramo {datos.get('desde_m', 0):.1f}"
            f"-{datos.get('hasta_m', 0):.1f}m"
        )
        actualizar_sesion(sid, "confirmacion", datos)
        return _resumen_sgs(datos)

    # ── Selección de etapa ────────────────────────────────────
    if paso == "tipo_etapa":
        # Acepta número ("1") o código normalizado desde interactivo ("LOGUEO")
        etapa = _resolver_etapa(msg)
        if not etapa:
            return f"❓ Responde con un número del 1 al {len(ETAPAS_SGS)}."
        datos["etapa"] = etapa
        actualizar_sesion(sid, "sondaje_sgs", datos)
        return (
            f"✅ Etapa: *{etapa}*\n\n"
            f"¿Código del sondaje?\n"
            f"Ejemplo: 8422, PECLD08422\n"
        )

    # ══════════════════════════════════════════════════════════
    # FLUJO LOGUEO
    # ══════════════════════════════════════════════════════════

    elif paso == "sondaje_sgs":
        sondaje = buscar_sondaje(msg)
        if not sondaje:
            return f"❌ No encontré *{msg}*. Verifica el código."

        etapa = datos.get("etapa", "")

        # Guardar datos base del sondaje
        datos["bhid"]       = sondaje["bhid"]
        datos["sondaje_id"] = sondaje.get("id") or _obtener_id(sondaje["bhid"])

        if etapa == "LOGUEO":
            # Calcular metros ya logueados
            logueado_hasta = _ultimo_metro_logueado(sondaje["bhid"])
            prof_final     = float(sondaje.get("final_m") or 0)
            prog_m         = float(sondaje.get("prog_m") or 0)
            estado_perf    = sondaje.get("estado_perforacion", "") or \
                             _estado_perforacion(sondaje["bhid"])
            estado_logueo  = sondaje.get("estado_logueo", "PENDIENTE")

            datos["logueado_hasta"] = logueado_hasta
            datos["prof_final"]     = prof_final
            datos["prog_m"]         = prog_m
            datos["desde_m"]        = logueado_hasta   # pre-cargado

            actualizar_sesion(sid, "fecha_logueo", datos,
                              sondaje_context=sondaje["bhid"])
            return _ficha_sondaje_logueo(sondaje, logueado_hasta,
                                         prof_final, prog_m,
                                         estado_perf, estado_logueo)
        else:
            # Otras etapas → flujo original
            actualizar_sesion(sid, "fecha_trabajo", datos,
                              sondaje_context=sondaje["bhid"])
            return (
                f"✅ Sondaje: *{sondaje['bhid']}*\n"
                f"   Prog: {sondaje.get('prog_m','—')} m | "
                f"Final: {float(sondaje.get('final_m') or 0):.1f} m\n\n"
                f"¿*Fecha* del trabajo? (DD/MM o *hoy*)\n"
            )

    # ── Fecha del logueo ──────────────────────────────────────
    elif paso == "fecha_logueo":
        fecha = _parsear_fecha(msg)
        if not fecha:
            return "❓ Formato: DD/MM (ej: 06/05) o escribe *hoy*."
        datos["fecha"] = fecha
        # desde_m ya pre-cargado; confirmar o ajustar
        desde_pre = datos.get("desde_m", 0)
        actualizar_sesion(sid, "tramo_desde_logueo", datos)
        if desde_pre > 0:
            return (
                f"✅ Fecha: *{fecha}*\n\n"
                f"📏 Último metro logueado: *{desde_pre:.2f} m*\n"
                f"¿*Desde* qué metro retomas hoy?\n"
                f"Escribe *{desde_pre:.0f}* para continuar desde ahí "
                f"o el metro que corresponda.\n"
            )
        return (
            f"✅ Fecha: *{fecha}*\n\n"
            f"¿*Desde* qué metro trabajaste?\n"
            f"Ejemplo: 0, 50.5\n"
        )

    # ── Tramo desde (logueo) ──────────────────────────────────
    elif paso == "tramo_desde_logueo":
        try:
            desde = float(msg.replace(",", "."))
            if desde < 0:
                raise ValueError
            datos["desde_m"] = desde
        except ValueError:
            return "❓ Ingresa un número válido. Ejemplo: 120.5"
        actualizar_sesion(sid, "tramo_hasta_logueo", datos)
        prof_final = datos.get("prof_final", 0)
        return (
            f"✅ Desde: *{desde:.2f} m*\n\n"
            f"¿*Hasta* qué metro logueaste?\n"
            f"Perforado hasta: {prof_final:.2f} m\n"
        )

    # ── Tramo hasta (logueo) ──────────────────────────────────
    elif paso == "tramo_hasta_logueo":
        try:
            hasta = float(msg.replace(",", "."))
            desde = datos.get("desde_m", 0)
            if hasta <= desde:
                return f"❓ Debe ser mayor a {desde:.2f} m."
            datos["hasta_m"] = hasta
        except ValueError:
            return "❓ Ingresa un número válido."

        metros = hasta - datos["desde_m"]
        prof_final = float(datos.get("prof_final") or 0)

        # Detectar si cubre todo lo perforado
        if prof_final > 0 and hasta >= prof_final * 0.98:
            datos["posible_fin_logueo"] = True

        actualizar_sesion(sid, "comentario_logueo", datos)
        return (
            f"✅ Tramo: *{datos['desde_m']:.2f} → {hasta:.2f} m* "
            f"({metros:.2f} m)\n\n"
            f"¿Algún *comentario* del tramo?\n"
            f"Escribe las observaciones o *no* para omitir.\n"
        )

    # ── Comentario (logueo) ───────────────────────────────────
    elif paso == "comentario_logueo":
        if msg.lower() in ("no", "n", "ninguno", "ninguna", "omitir"):
            datos["comentario"] = None
        else:
            datos["comentario"] = msg.strip()
        actualizar_sesion(sid, "foto_logueo", datos)
        return (
            f"📸 ¿Adjuntar foto del tramo?\n"
            f"Envía la imagen o escribe *no*.\n"
        )

    # ── Foto (logueo) ─────────────────────────────────────────
    elif paso == "foto_logueo":
        if msg.lower() in ("no", "n", "omitir", "skip"):
            datos["foto_url"]         = None
            datos["foto_descripcion"] = None
        # Si vino foto_url la manejamos arriba (bloque inicial)
        actualizar_sesion(sid, "confirmacion_logueo", datos)
        return _resumen_logueo(datos)

    # ── Confirmación (logueo) ─────────────────────────────────
    elif paso == "confirmacion_logueo":
        if msg.lower() in ("no", "cancelar", "n"):
            cerrar_sesion(usuario["id"])
            return "❌ Reporte cancelado."
        if msg.lower() not in ("sí", "si", "ok", "confirma", "yes"):
            return "¿Confirmas? Responde *sí* o *no*."

        try:
            ejecutar(
                """INSERT INTO etapas_sgs (
                       sondaje_id, etapa, fecha, desde_m, hasta_m,
                       tecnico, foto_url, foto_descripcion,
                       observaciones, reportado_por, fuente
                   ) VALUES (%s, 'LOGUEO', %s, %s, %s, %s, %s, %s, %s, %s, 'BOT')""",
                (
                    datos["sondaje_id"],
                    datos.get("fecha"),
                    datos.get("desde_m"),
                    datos.get("hasta_m"),
                    usuario["nombre"],          # técnico = usuario WhatsApp
                    datos.get("foto_url"),
                    datos.get("foto_descripcion"),
                    datos.get("comentario"),
                    usuario["id"],
                )
            )

            # Actualizar estado en sondaje maestro
            if datos.get("posible_fin_logueo"):
                actualizar_sesion(sid, "confirmar_fin_logueo", datos)
                return (
                    f"✅ *Logueo registrado*\n"
                    f"🔬 LOGUEO | *{datos['bhid']}*\n"
                    f"📏 {datos['desde_m']:.2f} → {datos['hasta_m']:.2f} m\n"
                    f"👤 {usuario['nombre']}\n\n"
                    f"─────────────────────\n"
                    f"🎯 El tramo logueado cubre todo lo perforado.\n"
                    f"¿El logueo del sondaje *{datos['bhid']}* está *completo*?\n"
                    f"  *sí* — Marcar COMPLETADO\n"
                    f"  *no* — Hay más por loguear\n"
                )
            else:
                actualizar_estado_etapa(datos["bhid"], "logueo", "EN_PROCESO")
                cerrar_sesion(usuario["id"])
                pendiente = max(0, datos.get("prof_final", 0) - datos["hasta_m"])
                return (
                    f"✅ *Logueo registrado*\n"
                    f"🔬 LOGUEO | *{datos['bhid']}*\n"
                    f"📏 {datos['desde_m']:.2f} → {datos['hasta_m']:.2f} m\n"
                    f"👤 {usuario['nombre']}\n"
                    f"📅 {fecha_hora_str()}\n"
                    + (f"\n⏳ Pendiente: *{pendiente:.2f} m* por loguear."
                       if pendiente > 0.5 else "")
                )

        except Exception as e:
            print(f"[SGS-LOGUEO] Error: {e}")
            return "⚠️ Error al guardar. Intenta de nuevo."

    # ── Confirmar fin de logueo ───────────────────────────────
    elif paso == "confirmar_fin_logueo":
        if msg.lower() in ("sí", "si", "yes", "ok"):
            actualizar_estado_etapa(datos["bhid"], "logueo", "COMPLETADO")
            cerrar_sesion(usuario["id"])
            return (
                f"✅ *Logueo COMPLETADO* 🎉\n"
                f"🔖 {datos['bhid']} marcado como logueo completo.\n"
                f"📅 {fecha_hora_str()}\n"
            )
        else:
            actualizar_estado_etapa(datos["bhid"], "logueo", "EN_PROCESO")
            cerrar_sesion(usuario["id"])
            return (
                f"✅ Logueo registrado. Sondaje continúa *EN PROCESO*.\n"
                f"Cuando termines escribe *logueo* para continuar.\n"
            )

    # ══════════════════════════════════════════════════════════
    # FLUJO GENÉRICO (Muestreo, RQD, Fotografía, Densidad)
    # ══════════════════════════════════════════════════════════

    elif paso == "fecha_trabajo":
        fecha = _parsear_fecha(msg)
        if not fecha:
            return "❓ Formato: DD/MM (ej: 06/05) o escribe *hoy*."
        datos["fecha"] = fecha
        actualizar_sesion(sid, "tramo_desde", datos)
        return (
            f"✅ Fecha: *{fecha}*\n\n"
            f"¿*Desde* qué metro trabajaste?\n"
            f"Ejemplo: 0, 50.5, 269.30\n"
        )

    elif paso == "tramo_desde":
        try:
            datos["desde_m"] = float(msg.replace(",", "."))
        except:
            return "❓ Ingresa un número. Ejemplo: 50.5"
        actualizar_sesion(sid, "tramo_hasta", datos)
        return "¿*Hasta* qué metro?\n"

    elif paso == "tramo_hasta":
        try:
            hasta = float(msg.replace(",", "."))
            if hasta <= datos.get("desde_m", 0):
                return f"❓ Debe ser mayor a {datos['desde_m']:.2f} m."
            datos["hasta_m"] = hasta
        except:
            return "❓ Ingresa un número válido."
        metros = datos["hasta_m"] - datos["desde_m"]
        actualizar_sesion(sid, "tecnico", datos)
        return (
            f"✅ Tramo: *{datos['desde_m']:.2f} — {datos['hasta_m']:.2f} m* "
            f"({metros:.2f} m)\n\n"
            f"¿Nombre del *técnico* responsable?\n"
        )

    elif paso == "tecnico":
        datos["tecnico"] = msg.strip()
        etapa = datos.get("etapa", "")
        if etapa == "MUESTREO":
            actualizar_sesion(sid, "cod_muestra_ini", datos)
            return (
                f"✅ Técnico: *{datos['tecnico']}*\n\n"
                f"¿*Código de muestra inicial*?\n"
                f"Ejemplo: 1561667\n"
            )
        elif etapa == "DENSIDAD":
            actualizar_sesion(sid, "densidad_datos", datos)
            return (
                f"✅ Técnico: *{datos['tecnico']}*\n\n"
                f"Ingresa: *STD DUP ORIGINALES*\n"
                f"Ejemplo: 2 3 45\n"
            )
        else:
            actualizar_sesion(sid, "foto_opcional", datos)
            return (
                f"✅ Técnico: *{datos['tecnico']}*\n\n"
                f"📸 ¿Deseas adjuntar una foto de este tramo?\n"
                f"Envía la foto o escribe *no*.\n"
            )

    elif paso == "cod_muestra_ini":
        datos["cod_muestra_ini"] = msg.strip()
        actualizar_sesion(sid, "cod_muestra_fin", datos)
        return "¿*Código de muestra final*?\n"

    elif paso == "cod_muestra_fin":
        datos["cod_muestra_fin"] = msg.strip()
        try:
            cant = int(datos["cod_muestra_fin"]) - int(datos["cod_muestra_ini"]) + 1
            datos["cant_muestras"] = cant
        except:
            datos["cant_muestras"] = None
        actualizar_sesion(sid, "foto_opcional", datos)
        cant_str = (f" ({datos['cant_muestras']} muestras)"
                    if datos.get("cant_muestras") else "")
        return (
            f"✅ Muestras: *{datos['cod_muestra_ini']}* → "
            f"*{datos['cod_muestra_fin']}*{cant_str}\n\n"
            f"📸 ¿Adjuntar foto? Envía o escribe *no*.\n"
        )

    elif paso == "densidad_datos":
        partes = msg.strip().split()
        if len(partes) < 3:
            return "❓ Ingresa 3 valores: STD DUP ORIGINALES\nEjemplo: 2 3 45"
        try:
            datos["std_densidad"] = int(partes[0])
            datos["dup_densidad"] = int(partes[1])
            datos["originales"]   = int(partes[2])
        except:
            return "❓ Los valores deben ser números enteros."
        actualizar_sesion(sid, "foto_opcional", datos)
        return (
            f"✅ STD: {datos['std_densidad']} | "
            f"DUP: {datos['dup_densidad']} | "
            f"Originales: {datos['originales']}\n\n"
            f"📸 ¿Adjuntar foto? Envía o escribe *no*.\n"
        )

    elif paso == "foto_opcional":
        if msg.lower() in ("no", "n", "omitir"):
            datos["foto_url"] = None
        # foto_url real viene por el bloque inicial arriba
        actualizar_sesion(sid, "confirmacion", datos)
        return _resumen_sgs(datos)

    elif paso == "confirmacion":
        if msg.lower() in ("no", "cancelar"):
            cerrar_sesion(usuario["id"])
            return "❌ Reporte cancelado."
        if msg.lower() not in ("sí", "si", "ok", "confirma", "yes"):
            return "¿Confirmas? Responde *sí* o *no*."
        try:
            ejecutar(
                """INSERT INTO etapas_sgs (
                       sondaje_id, etapa, fecha, desde_m, hasta_m,
                       tecnico, cod_muestra_ini, cod_muestra_fin, cant_muestras,
                       std_densidad, dup_densidad, originales,
                       foto_url, foto_descripcion,
                       reportado_por, fuente
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'BOT')""",
                (
                    datos.get("sondaje_id"), datos.get("etapa"),
                    datos.get("fecha"), datos.get("desde_m"), datos.get("hasta_m"),
                    datos.get("tecnico"),
                    datos.get("cod_muestra_ini"), datos.get("cod_muestra_fin"),
                    datos.get("cant_muestras"),
                    datos.get("std_densidad"), datos.get("dup_densidad"),
                    datos.get("originales"),
                    datos.get("foto_url"), datos.get("foto_descripcion"),
                    usuario["id"]
                )
            )
            etapa_key = datos["etapa"].lower()
            actualizar_estado_etapa(datos["bhid"], etapa_key, "EN_PROCESO")
            cerrar_sesion(usuario["id"])
            return (
                f"✅ *Reporte SGS registrado*\n"
                f"🔬 {datos['etapa']} | *{datos['bhid']}*\n"
                f"📏 {datos['desde_m']:.2f} — {datos['hasta_m']:.2f} m\n"
                f"📅 {fecha_hora_str()}\n"
                f"👤 {datos.get('tecnico','—')}\n"
            )
        except Exception as e:
            print(f"[SGS] Error: {e}")
            return "⚠️ Error al guardar. Intenta de nuevo."

    return "❓ Paso no reconocido. Escribe *hola* para reiniciar."


# ══════════════════════════════════════════════════════════════
# CONSULTAS SIN SESIÓN (llamadas desde router/gerencia)
# ══════════════════════════════════════════════════════════════

def consultar_sondajes_activos_sgs() -> str:
    """
    Sondajes EN_CURSO con logueo pendiente o en proceso.
    Para técnicos SGS que preguntan qué tienen por hacer.
    """
    rows = ejecutar(
        """SELECT s.bhid,
                  m.codigo           AS maquina,
                  e.codigo           AS empresa,
                  COALESCE(s.tajo_objetivo, s.cuerpo_objetivo, '—') AS objetivo,
                  s.profundidad_prog AS prog_m,
                  COALESCE(s.profundidad_final, 0)                  AS final_m,
                  s.estado_logueo,
                  COALESCE(
                      (SELECT MAX(eg.hasta_m)
                       FROM etapas_sgs eg
                       JOIN sondajes ss ON eg.sondaje_id = ss.id
                       WHERE ss.bhid = s.bhid AND eg.etapa = 'LOGUEO'),
                      0
                  ) AS logueado_hasta
           FROM sondajes s
           JOIN cat_maquinas m ON s.maquina_id  = m.id
           JOIN cat_empresas e ON s.empresa_id  = e.id
           WHERE s.estado_perforacion = 'EN_CURSO'
             AND s.estado_logueo IN ('PENDIENTE', 'EN_PROCESO')
           ORDER BY s.bhid""",
        fetchall=True
    )
    if not rows:
        return "✅ No hay sondajes activos con logueo pendiente."

    lineas = [f"🔬 *SONDAJES ACTIVOS — LOGUEO PENDIENTE*",
              f"{'─'*32}"]
    for r in rows:
        bhid, maq, emp, obj, prog, final, est_log, log_hasta = r
        prog_f  = float(prog  or 0)
        final_f = float(final or 0)
        log_f   = float(log_hasta or 0)
        pend    = final_f - log_f
        pct_perf = f"{final_f/prog_f*100:.0f}%" if prog_f > 0 else "—"
        estado_icon = "🟡" if est_log == "EN_PROCESO" else "🔴"
        lineas.append(
            f"\n{estado_icon} *{bhid}* | {maq} ({emp})\n"
            f"   🎯 {obj} | Prog: {prog_f:.0f}m\n"
            f"   ⛏️ Perforado: {final_f:.1f}m ({pct_perf})\n"
            f"   📝 Logueado hasta: {log_f:.1f}m"
            + (f" | ⚠️ Pendiente: {pend:.1f}m" if pend > 0.5 else "")
        )
    lineas.append(f"\n{'─'*32}")
    lineas.append(f"Total: *{len(rows)} sondaje(s)* con logueo pendiente")
    return "\n".join(lineas)


def consultar_finalizados_mes(mes: int = None, anio: int = None) -> str:
    """
    Sondajes finalizados en el mes indicado (default: mes actual).
    """
    from datetime import date
    hoy  = hora_peru().date()
    mes  = mes  or hoy.month
    anio = anio or hoy.year

    rows = ejecutar(
        """SELECT s.bhid,
                  m.codigo AS maquina,
                  COALESCE(s.tajo_objetivo, s.cuerpo_objetivo, '—') AS objetivo,
                  s.profundidad_prog  AS prog_m,
                  COALESCE(s.profundidad_final, 0)                  AS final_m,
                  s.estado_logueo,
                  s.fecha_fin_perf
           FROM sondajes s
           JOIN cat_maquinas m ON s.maquina_id = m.id
           WHERE s.estado_perforacion = 'FINALIZADO'
             AND EXTRACT(MONTH FROM s.fecha_fin_perf) = %s
             AND EXTRACT(YEAR  FROM s.fecha_fin_perf) = %s
           ORDER BY s.fecha_fin_perf DESC""",
        (mes, anio), fetchall=True
    )

    meses_es = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",
                6:"Junio",7:"Julio",8:"Agosto",9:"Septiembre",
                10:"Octubre",11:"Noviembre",12:"Diciembre"}
    mes_str = f"{meses_es.get(mes, mes)}/{anio}"

    if not rows:
        return f"📭 No hay sondajes finalizados en *{mes_str}*."

    lineas = [f"✅ *FINALIZADOS — {mes_str}*", f"{'─'*32}"]
    for r in rows:
        bhid, maq, obj, prog, final, est_log, fecha_fin = r
        log_icon = {"COMPLETADO": "✅", "EN_PROCESO": "🟡",
                    "PENDIENTE": "🔴"}.get(est_log, "⬜")
        try:
            fecha_str = fecha_fin.strftime("%d/%m") if fecha_fin else "—"
        except:
            fecha_str = str(fecha_fin)[:5]
        lineas.append(
            f"\n🔖 *{bhid}* | {maq}\n"
            f"   🎯 {obj}\n"
            f"   📏 {float(final or 0):.1f}/{float(prog or 0):.0f}m"
            f" | Fin: {fecha_str}\n"
            f"   📝 Logueo: {log_icon} {est_log}"
        )
    lineas.append(f"\n{'─'*32}")
    lineas.append(f"Total: *{len(rows)} sondaje(s)* finalizados en {mes_str}")
    return "\n".join(lineas)


def consultar_pendientes_logueo() -> str:
    """
    Todos los sondajes (EN_CURSO o FINALIZADO) con logueo incompleto.
    Vista priorizada: finalizados primero (más urgente), luego en curso.
    """
    rows = ejecutar(
        """SELECT s.bhid,
                  s.estado_perforacion,
                  m.codigo AS maquina,
                  COALESCE(s.tajo_objetivo, s.cuerpo_objetivo, '—') AS objetivo,
                  COALESCE(s.profundidad_final, 0)  AS final_m,
                  s.estado_logueo,
                  COALESCE(
                      (SELECT MAX(eg.hasta_m)
                       FROM etapas_sgs eg
                       JOIN sondajes ss ON eg.sondaje_id = ss.id
                       WHERE ss.bhid = s.bhid AND eg.etapa = 'LOGUEO'),
                      0
                  ) AS logueado_hasta
           FROM sondajes s
           JOIN cat_maquinas m ON s.maquina_id = m.id
           WHERE s.estado_logueo IN ('PENDIENTE', 'EN_PROCESO')
             AND s.estado_perforacion IN ('EN_CURSO', 'FINALIZADO')
           ORDER BY
               CASE s.estado_perforacion
                   WHEN 'FINALIZADO' THEN 1
                   ELSE 2 END,
               s.bhid""",
        fetchall=True
    )
    if not rows:
        return "✅ Todos los sondajes activos tienen logueo al día."

    lineas = [f"📋 *SONDAJES CON LOGUEO PENDIENTE*", f"{'─'*32}"]
    fin_count = en_curso_count = 0
    for r in rows:
        bhid, est_perf, maq, obj, final, est_log, log_hasta = r
        final_f = float(final   or 0)
        log_f   = float(log_hasta or 0)
        pend    = final_f - log_f
        if est_perf == "FINALIZADO":
            fin_count += 1
            icono = "🚨"
            label = "FINALIZADO"
        else:
            en_curso_count += 1
            icono = "⏳"
            label = "EN CURSO"
        lineas.append(
            f"\n{icono} *{bhid}* | {label}\n"
            f"   🚜 {maq} | 🎯 {obj}\n"
            f"   📝 Logueado: {log_f:.1f}m / "
            f"Perforado: {final_f:.1f}m"
            + (f" | Faltan: *{pend:.1f}m*" if pend > 0.5 else "")
        )
    lineas.append(f"\n{'─'*32}")
    if fin_count:
        lineas.append(f"🚨 *{fin_count}* finalizado(s) sin logueo completo")
    if en_curso_count:
        lineas.append(f"⏳ *{en_curso_count}* en curso con logueo pendiente")
    return "\n".join(lineas)


# ══════════════════════════════════════════════════════════════
# HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════

def _resolver_etapa(msg: str) -> str | None:
    """Acepta número o nombre de etapa (desde interactivo o texto)."""
    # Por número
    if msg in ETAPAS_SGS:
        return ETAPAS_SGS[msg]
    # Por nombre directo (interactivo normalizado)
    nombres_validos = {"LOGUEO", "MUESTREO", "RQD", "FOTOGRAFIA", "DENSIDAD"}
    if msg.upper() in nombres_validos:
        return msg.upper()
    return None


def _ultimo_metro_logueado(bhid: str) -> float:
    """Retorna el MAX(hasta_m) de registros LOGUEO del sondaje."""
    row = ejecutar(
        """SELECT COALESCE(MAX(e.hasta_m), 0)
           FROM etapas_sgs e
           JOIN sondajes s ON e.sondaje_id = s.id
           WHERE s.bhid = %s AND e.etapa = 'LOGUEO'""",
        (bhid,), fetchone=True
    )
    return float(row[0]) if row else 0.0


def _estado_perforacion(bhid: str) -> str:
    row = ejecutar(
        "SELECT estado_perforacion FROM sondajes WHERE bhid = %s",
        (bhid,), fetchone=True
    )
    return row[0] if row else "PLANIFICADO"


def _parsear_fecha(msg: str) -> str | None:
    if msg.lower() == "hoy":
        return hora_peru().strftime("%Y-%m-%d")
    try:
        from datetime import datetime
        parsed = datetime.strptime(msg.replace("-", "/"), "%d/%m")
        return parsed.replace(year=hora_peru().year).strftime("%Y-%m-%d")
    except:
        return None


def _obtener_id(bhid: str) -> int | None:
    row = ejecutar("SELECT id FROM sondajes WHERE bhid=%s", (bhid,), fetchone=True)
    return row[0] if row else None


def _ficha_sondaje_logueo(sondaje: dict, logueado_hasta: float,
                           prof_final: float, prog_m: float,
                           estado_perf: str, estado_logueo: str) -> str:
    """Ficha completa del sondaje para el técnico de logueo."""
    bhid     = sondaje.get("bhid", "—")
    maquina  = sondaje.get("maquina", "—")
    empresa  = sondaje.get("empresa", "—")
    subcat   = sondaje.get("subcategoria", "—")
    objetivo = sondaje.get("tajo_objetivo") or sondaje.get("cuerpo_objetivo") or "—"
    nivel    = sondaje.get("nivel", "—")
    labor    = sondaje.get("labor", "—")
    diametro = sondaje.get("diametro", "—")

    # Estado perforación
    perf_icons = {"EN_CURSO": "🟢", "FINALIZADO": "✅", "PLANIFICADO": "🔵"}
    perf_icon  = perf_icons.get(estado_perf, "⬜")
    pct_perf   = f"{prof_final/prog_m*100:.0f}%" if prog_m > 0 else "—"

    # Estado logueo
    pend_m = max(0.0, prof_final - logueado_hasta)
    if logueado_hasta == 0:
        log_str = "   📝 Sin logueo registrado — empieza desde 0.0 m"
    elif pend_m <= 0.5:
        log_str = "   📝 ✅ Logueo al día"
    else:
        log_str = (
            f"   📝 Logueado hasta: *{logueado_hasta:.2f} m*\n"
            f"   ⚠️ Pendiente: *{pend_m:.2f} m* "
            f"({logueado_hasta:.1f} → {prof_final:.1f} m)"
        )

    return (
        f"✅ *{bhid}*\n"
        f"{'─'*30}\n"
        f"🚜 {maquina} ({empresa})\n"
        f"📂 {subcat} | 🎯 {objetivo}\n"
        f"📍 Nv.{nivel} {labor} | {diametro}\n"
        f"{'─'*30}\n"
        f"   {perf_icon} {estado_perf} — "
        f"Perforado: *{prof_final:.1f}/{prog_m:.0f} m* ({pct_perf})\n"
        f"{log_str}\n"
        f"{'─'*30}\n\n"
        f"¿*Fecha* del logueo? (DD/MM o *hoy*)\n"
    )


def _resumen_logueo(datos: dict) -> str:
    desde = datos.get("desde_m", 0)
    hasta = datos.get("hasta_m", 0)
    return (
        f"📋 *RESUMEN LOGUEO*\n"
        f"{'─'*28}\n"
        f"🔖 Sondaje: *{datos.get('bhid','—')}*\n"
        f"📏 Tramo:   {desde:.2f} → {hasta:.2f} m "
        f"({hasta - desde:.2f} m)\n"
        f"📅 Fecha:   {datos.get('fecha','—')}\n"
        f"👤 Técnico: {datos.get('_nombre_usuario', datos.get('tecnico','—'))}\n"
        + (f"💬 Comentario: {datos['comentario']}\n"
           if datos.get("comentario") else "")
        + f"📸 Foto: {'✅' if datos.get('foto_url') else 'No'}\n"
        f"{'─'*28}\n"
        f"¿Confirmas? (*sí* / *no*)\n"
    )


def _resumen_sgs(datos: dict) -> str:
    etapa = datos.get("etapa", "—")
    lineas = [
        f"📋 *RESUMEN {etapa}*",
        f"{'─'*28}",
        f"🔖 Sondaje: *{datos.get('bhid','—')}*",
        f"📏 Tramo:   {datos.get('desde_m',0):.2f} — {datos.get('hasta_m',0):.2f} m",
        f"📅 Fecha:   {datos.get('fecha','—')}",
        f"👤 Técnico: {datos.get('tecnico','—')}",
    ]
    if etapa == "MUESTREO":
        lineas.append(
            f"🔢 Muestras: {datos.get('cod_muestra_ini','—')} → "
            f"{datos.get('cod_muestra_fin','—')}"
        )
        if datos.get("cant_muestras"):
            lineas.append(f"   Total: {datos['cant_muestras']} muestras")
    if etapa == "DENSIDAD":
        lineas.append(
            f"📊 STD: {datos.get('std_densidad','—')} | "
            f"DUP: {datos.get('dup_densidad','—')} | "
            f"Orig: {datos.get('originales','—')}"
        )
    lineas.append(f"📸 Foto: {'Sí' if datos.get('foto_url') else 'No'}")
    lineas.append(f"{'─'*28}")
    lineas.append("¿Confirmas? (*sí* / *no*)")
    return "\n".join(lineas)
