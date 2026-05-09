"""
FLUJO SGS — Logueo, Muestreo, RQD, Fotografía, Densidad
Para rol SGS y ADMIN.

v4 — Muestreo y Densidad con columnas correctas:

MUESTREO (columnas nuevas):
  mues_ordinarias, mues_std_alta, mues_std_baja,
  dup_gemela, dup_grueso, dup_fino, muestras_blanco
  cant_muestras = total general
  cod_muestra_ini / cod_muestra_fin = rango correlativo

DENSIDAD (columnas existentes):
  std_densidad  = cantidad de estándares
  dup_densidad  = cantidad de duplicados
  originales    = cantidad de originales
  cant_muestras = total (std + dup + originales)

ANTES DE DESPLEGAR — correr en BD:
  ALTER TABLE etapas_sgs
    ADD COLUMN IF NOT EXISTS mues_ordinarias  INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mues_std_alta    INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mues_std_baja    INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dup_gemela       INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dup_grueso       INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dup_fino         INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS muestras_blanco  INT DEFAULT 0;
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
    """Router ya envió menu_etapas_sgs() — solo inicializa el paso."""
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

    # ── Foto en logueo ────────────────────────────────────────
    if foto_url and paso == "foto_logueo":
        datos["foto_url"] = foto_url
        datos["foto_descripcion"] = (
            f"Logueo tramo {datos.get('desde_m', 0):.1f}"
            f"-{datos.get('hasta_m', 0):.1f}m"
        )
        actualizar_sesion(sid, "confirmacion_logueo", datos)
        return _resumen_logueo(datos)

    # ── Foto en RQD / Fotografía ──────────────────────────────
    if foto_url and paso == "foto_opcional":
        datos["foto_url"] = foto_url
        datos["foto_descripcion"] = (
            f"Tramo {datos.get('desde_m', 0):.1f}"
            f"-{datos.get('hasta_m', 0):.1f}m"
        )
        actualizar_sesion(sid, "confirmacion_generica", datos)
        return _resumen_generico(datos)

    # ── Selección de etapa ────────────────────────────────────
    if paso == "tipo_etapa":
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

    # ── Búsqueda de sondaje ───────────────────────────────────
    elif paso == "sondaje_sgs":
        sondaje = buscar_sondaje(msg)
        if not sondaje:
            return f"❌ No encontré *{msg}*. Verifica el código."

        etapa = datos.get("etapa", "")
        datos["bhid"]       = sondaje["bhid"]
        datos["sondaje_id"] = sondaje.get("id") or _obtener_id(sondaje["bhid"])
        datos["diametro"]   = sondaje.get("diametro", "NQ")

        if etapa == "LOGUEO":
            logueado_hasta = _ultimo_metro_logueado(sondaje["bhid"])
            prof_final     = float(sondaje.get("final_m") or 0)
            prog_m         = float(sondaje.get("prog_m") or 0)
            estado_perf    = (sondaje.get("estado_perforacion") or
                              _estado_perforacion(sondaje["bhid"]))
            estado_logueo  = sondaje.get("estado_logueo", "PENDIENTE")
            datos.update({
                "logueado_hasta": logueado_hasta,
                "prof_final":     prof_final,
                "prog_m":         prog_m,
                "desde_m":        logueado_hasta,
            })
            actualizar_sesion(sid, "fecha_logueo", datos,
                              sondaje_context=sondaje["bhid"])
            return _ficha_logueo(sondaje, logueado_hasta,
                                 prof_final, prog_m,
                                 estado_perf, estado_logueo)

        elif etapa == "MUESTREO":
            prof_final = float(sondaje.get("final_m") or 0)
            prog_m     = float(sondaje.get("prog_m") or 0)
            datos.update({"prof_final": prof_final, "prog_m": prog_m})
            aviso = _aviso_muestreo_previo(sondaje["bhid"])
            actualizar_sesion(sid, "fecha_muestreo", datos,
                              sondaje_context=sondaje["bhid"])
            return _ficha_muestreo(sondaje, prof_final, prog_m) + aviso

        elif etapa == "DENSIDAD":
            prof_final = float(sondaje.get("final_m") or 0)
            prog_m     = float(sondaje.get("prog_m") or 0)
            datos.update({"prof_final": prof_final, "prog_m": prog_m})
            aviso = _aviso_densidad_previa(sondaje["bhid"])
            actualizar_sesion(sid, "fecha_densidad", datos,
                              sondaje_context=sondaje["bhid"])
            return _ficha_densidad(sondaje, prof_final, prog_m) + aviso

        else:
            # RQD, FOTOGRAFIA
            actualizar_sesion(sid, "fecha_trabajo", datos,
                              sondaje_context=sondaje["bhid"])
            return (
                f"✅ Sondaje: *{sondaje['bhid']}*\n"
                f"   Prog: {sondaje.get('prog_m','—')} m | "
                f"Final: {float(sondaje.get('final_m') or 0):.1f} m\n\n"
                f"¿*Fecha* del trabajo? (DD/MM o *hoy*)\n"
            )

    # ══════════════════════════════════════════════════════════
    # FLUJO LOGUEO
    # ══════════════════════════════════════════════════════════

    elif paso == "fecha_logueo":
        fecha = _parsear_fecha(msg)
        if not fecha:
            return "❓ Formato: DD/MM (ej: 06/05) o escribe *hoy*."
        datos["fecha"] = fecha
        desde_pre = datos.get("desde_m", 0)
        actualizar_sesion(sid, "tramo_desde_logueo", datos)
        if desde_pre > 0:
            return (
                f"✅ Fecha: *{fecha}*\n\n"
                f"📏 Último metro logueado: *{desde_pre:.2f} m*\n"
                f"¿*Desde* qué metro retomas?\n"
                f"Escribe *{desde_pre:.0f}* para continuar o el metro correcto.\n"
            )
        return (
            f"✅ Fecha: *{fecha}*\n\n"
            f"¿*Desde* qué metro trabajaste?\n"
            f"Ejemplo: 0, 50.5\n"
        )

    elif paso == "tramo_desde_logueo":
        try:
            desde = float(msg.replace(",", "."))
            if desde < 0:
                raise ValueError
            datos["desde_m"] = desde
        except ValueError:
            return "❓ Número válido. Ejemplo: 120.5"
        actualizar_sesion(sid, "tramo_hasta_logueo", datos)
        return (
            f"✅ Desde: *{desde:.2f} m*\n\n"
            f"¿*Hasta* qué metro logueaste?\n"
            f"Perforado hasta: {datos.get('prof_final', 0):.2f} m\n"
        )

    elif paso == "tramo_hasta_logueo":
        try:
            hasta = float(msg.replace(",", "."))
            desde = datos.get("desde_m", 0)
            if hasta <= desde:
                return f"❓ Debe ser mayor a {desde:.2f} m."
            datos["hasta_m"] = hasta
        except ValueError:
            return "❓ Número válido."
        metros     = hasta - datos["desde_m"]
        prof_final = float(datos.get("prof_final") or 0)
        if prof_final > 0 and hasta >= prof_final * 0.98:
            datos["posible_fin_logueo"] = True
        actualizar_sesion(sid, "comentario_logueo", datos)
        return (
            f"✅ Tramo: *{datos['desde_m']:.2f} → {hasta:.2f} m* "
            f"({metros:.2f} m)\n\n"
            f"¿*Comentario* del tramo?\n"
            f"Escribe las observaciones o *no* para omitir.\n"
        )

    elif paso == "comentario_logueo":
        datos["comentario"] = (
            None if msg.lower() in ("no", "n", "ninguno", "ninguna", "omitir")
            else msg.strip()
        )
        actualizar_sesion(sid, "foto_logueo", datos)
        return "📸 ¿Adjuntar foto del tramo?\nEnvía la imagen o escribe *no*.\n"

    elif paso == "foto_logueo":
        if msg.lower() in ("no", "n", "omitir", "skip"):
            datos["foto_url"] = None
            datos["foto_descripcion"] = None
        actualizar_sesion(sid, "confirmacion_logueo", datos)
        return _resumen_logueo(datos)

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
                    datos["sondaje_id"], datos.get("fecha"),
                    datos.get("desde_m"), datos.get("hasta_m"),
                    usuario["nombre"],
                    datos.get("foto_url"), datos.get("foto_descripcion"),
                    datos.get("comentario"), usuario["id"],
                )
            )
            if datos.get("posible_fin_logueo"):
                actualizar_sesion(sid, "confirmar_fin_logueo", datos)
                return (
                    f"✅ *Logueo registrado*\n"
                    f"🔬 LOGUEO | *{datos['bhid']}*\n"
                    f"📏 {datos['desde_m']:.2f} → {datos['hasta_m']:.2f} m\n"
                    f"👤 {usuario['nombre']}\n\n"
                    f"─────────────────────\n"
                    f"🎯 El tramo cubre todo lo perforado.\n"
                    f"¿El logueo de *{datos['bhid']}* está *completo*?\n"
                    f"  *sí* — Marcar COMPLETADO\n"
                    f"  *no* — Hay más por loguear\n"
                )
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

    elif paso == "confirmar_fin_logueo":
        if msg.lower() in ("sí", "si", "yes", "ok"):
            actualizar_estado_etapa(datos["bhid"], "logueo", "COMPLETADO")
            cerrar_sesion(usuario["id"])
            return (
                f"✅ *Logueo COMPLETADO* 🎉\n"
                f"🔖 {datos['bhid']} marcado como completo.\n"
                f"📅 {fecha_hora_str()}\n"
            )
        actualizar_estado_etapa(datos["bhid"], "logueo", "EN_PROCESO")
        cerrar_sesion(usuario["id"])
        return "✅ Logueo registrado. Sondaje continúa *EN PROCESO*.\n"

    # ══════════════════════════════════════════════════════════
    # FLUJO MUESTREO
    # ══════════════════════════════════════════════════════════

    elif paso == "fecha_muestreo":
        fecha = _parsear_fecha(msg)
        if not fecha:
            return "❓ Formato: DD/MM (ej: 06/05) o escribe *hoy*."
        datos["fecha"] = fecha
        actualizar_sesion(sid, "tramo_desde_muestreo", datos)
        return (
            f"✅ Fecha: *{fecha}*\n\n"
            f"¿*Desde* qué metro se tomaron las muestras?\n"
        )

    elif paso == "tramo_desde_muestreo":
        try:
            desde = float(msg.replace(",", "."))
            if desde < 0: raise ValueError
            datos["desde_m"] = desde
        except ValueError:
            return "❓ Número válido. Ejemplo: 50.5"
        actualizar_sesion(sid, "tramo_hasta_muestreo", datos)
        return (
            f"✅ Desde: *{desde:.2f} m*\n\n"
            f"¿*Hasta* qué metro?\n"
            f"Perforado hasta: {datos.get('prof_final', 0):.2f} m\n"
        )

    elif paso == "tramo_hasta_muestreo":
        try:
            hasta = float(msg.replace(",", "."))
            desde = datos.get("desde_m", 0)
            if hasta <= desde:
                return f"❓ Debe ser mayor a {desde:.2f} m."
            datos["hasta_m"] = hasta
        except ValueError:
            return "❓ Número válido."
        metros = hasta - datos["desde_m"]
        actualizar_sesion(sid, "muestreo_tecnico", datos)
        return (
            f"✅ Tramo: *{datos['desde_m']:.2f} → {hasta:.2f} m* "
            f"({metros:.2f} m)\n\n"
            f"¿Nombre del *técnico* muestrero?\n"
        )

    elif paso == "muestreo_tecnico":
        datos["tecnico"] = msg.strip()
        actualizar_sesion(sid, "mues_cod_ini", datos)
        return (
            f"✅ Técnico: *{datos['tecnico']}*\n\n"
            f"¿*Código de muestra inicial*? (número correlativo)\n"
            f"Ejemplo: 1561667\n"
        )

    elif paso == "mues_cod_ini":
        cod = msg.strip()
        if not cod.isdigit():
            return "❓ Solo números. Ejemplo: 1561667"
        datos["cod_muestra_ini"] = cod
        actualizar_sesion(sid, "mues_cod_fin", datos)
        return f"✅ Código inicial: *{cod}*\n\n¿*Código de muestra final*?\n"

    elif paso == "mues_cod_fin":
        cod = msg.strip()
        if not cod.isdigit():
            return "❓ Solo números."
        ini = int(datos["cod_muestra_ini"])
        fin = int(cod)
        if fin < ini:
            return f"❓ Debe ser mayor o igual a {ini}."
        datos["cod_muestra_fin"] = cod
        datos["total_rango"]     = fin - ini + 1
        actualizar_sesion(sid, "mues_ordinarias", datos)
        return (
            f"✅ Rango: *{ini}* → *{fin}* ({fin - ini + 1} muestras)\n\n"
            f"─── DESGLOSE ───\n"
            f"¿Cuántas *ordinarias*?\n"
        )

    elif paso == "mues_ordinarias":
        try:
            n = int(msg.strip())
            if n < 0: raise ValueError
            datos["mues_ordinarias"] = n
        except ValueError:
            return "❓ Número entero positivo."
        actualizar_sesion(sid, "mues_std_alta", datos)
        return (
            f"✅ Ordinarias: *{n}*\n\n"
            f"QAQC — ¿Cuántos *estándares alta ley*?\n"
            f"_(0 si no aplica)_\n"
        )

    elif paso == "mues_std_alta":
        try:
            n = int(msg.strip())
            if n < 0: raise ValueError
            datos["mues_std_alta"] = n
        except ValueError:
            return "❓ Número entero (0 si no aplica)."
        actualizar_sesion(sid, "mues_std_baja", datos)
        return (
            f"✅ STD alta: *{n}*\n\n"
            f"¿Cuántos *estándares baja ley*?\n"
            f"_(0 si no aplica)_\n"
        )

    elif paso == "mues_std_baja":
        try:
            n = int(msg.strip())
            if n < 0: raise ValueError
            datos["mues_std_baja"] = n
        except ValueError:
            return "❓ Número entero (0 si no aplica)."
        actualizar_sesion(sid, "mues_dup_gemela", datos)
        return (
            f"✅ STD baja: *{n}*\n\n"
            f"¿Cuántos *duplicados gemela*?\n"
            f"_(0 si BQ o no aplica)_\n"
        )

    elif paso == "mues_dup_gemela":
        try:
            n = int(msg.strip())
            if n < 0: raise ValueError
            datos["dup_gemela"] = n
        except ValueError:
            return "❓ Número entero (0 si no aplica)."
        actualizar_sesion(sid, "mues_dup_grueso", datos)
        return (
            f"✅ Dup. gemela: *{n}*\n\n"
            f"¿Cuántos *duplicados grueso*?\n"
            f"_(0 si no aplica)_\n"
        )

    elif paso == "mues_dup_grueso":
        try:
            n = int(msg.strip())
            if n < 0: raise ValueError
            datos["dup_grueso"] = n
        except ValueError:
            return "❓ Número entero (0 si no aplica)."
        actualizar_sesion(sid, "mues_dup_fino", datos)
        return (
            f"✅ Dup. grueso: *{n}*\n\n"
            f"¿Cuántos *duplicados fino*?\n"
            f"_(0 si no aplica)_\n"
        )

    elif paso == "mues_dup_fino":
        try:
            n = int(msg.strip())
            if n < 0: raise ValueError
            datos["dup_fino"] = n
        except ValueError:
            return "❓ Número entero (0 si no aplica)."
        actualizar_sesion(sid, "mues_blancos", datos)
        return (
            f"✅ Dup. fino: *{n}*\n\n"
            f"¿Cuántas *muestras blanco*?\n"
            f"_(0 si no aplica)_\n"
        )

    elif paso == "mues_blancos":
        try:
            n = int(msg.strip())
            if n < 0: raise ValueError
            datos["muestras_blanco"] = n
        except ValueError:
            return "❓ Número entero (0 si no aplica)."

        # Cálculo y verificación
        ord_n    = datos.get("mues_ordinarias", 0)
        std_alta = datos.get("mues_std_alta", 0)
        std_baja = datos.get("mues_std_baja", 0)
        gemela   = datos.get("dup_gemela", 0)
        grueso   = datos.get("dup_grueso", 0)
        fino     = datos.get("dup_fino", 0)
        blancos  = n
        rango    = datos.get("total_rango", 0)
        qaqc     = std_alta + std_baja + gemela + grueso + fino + blancos
        total    = ord_n + qaqc
        datos["qaqc_total"]    = qaqc
        datos["cant_muestras"] = total

        aviso = ""
        if rango > 0 and total != rango:
            aviso = (
                f"\n⚠️ *Verificar:* el rango tiene *{rango}* muestras "
                f"pero la suma da *{total}*.\n"
                f"Confirma igual si es correcto o escribe *no* para corregir.\n"
            )
        actualizar_sesion(sid, "confirmacion_muestreo", datos)
        return _resumen_muestreo(datos) + aviso

    elif paso == "confirmacion_muestreo":
        if msg.lower() in ("no", "cancelar", "n"):
            cerrar_sesion(usuario["id"])
            return "❌ Reporte cancelado."
        if msg.lower() not in ("sí", "si", "ok", "confirma", "yes"):
            return "¿Confirmas? Responde *sí* o *no*."
        try:
            ejecutar(
                """INSERT INTO etapas_sgs (
                       sondaje_id, etapa, fecha, desde_m, hasta_m,
                       tecnico, cod_muestra_ini, cod_muestra_fin, cant_muestras,
                       mues_ordinarias, mues_std_alta, mues_std_baja,
                       dup_gemela, dup_grueso, dup_fino, muestras_blanco,
                       reportado_por, fuente
                   ) VALUES (
                       %s,'MUESTREO',%s,%s,%s,
                       %s,%s,%s,%s,
                       %s,%s,%s,
                       %s,%s,%s,%s,
                       %s,'BOT'
                   )""",
                (
                    datos["sondaje_id"],
                    datos.get("fecha"),
                    datos.get("desde_m"), datos.get("hasta_m"),
                    datos.get("tecnico"),
                    datos.get("cod_muestra_ini"), datos.get("cod_muestra_fin"),
                    datos.get("cant_muestras"),
                    datos.get("mues_ordinarias", 0),
                    datos.get("mues_std_alta", 0),
                    datos.get("mues_std_baja", 0),
                    datos.get("dup_gemela", 0),
                    datos.get("dup_grueso", 0),
                    datos.get("dup_fino", 0),
                    datos.get("muestras_blanco", 0),
                    usuario["id"],
                )
            )
            actualizar_estado_etapa(datos["bhid"], "muestreo", "EN_PROCESO")
            cerrar_sesion(usuario["id"])
            return (
                f"✅ *Muestreo registrado*\n"
                f"🧪 MUESTREO | *{datos['bhid']}*\n"
                f"📏 {datos['desde_m']:.2f} → {datos['hasta_m']:.2f} m\n"
                f"🔢 Total: *{datos['cant_muestras']}* muestras "
                f"({datos.get('mues_ordinarias',0)} ord. + "
                f"{datos.get('qaqc_total',0)} QAQC)\n"
                f"👤 {datos.get('tecnico','—')}\n"
                f"📅 {fecha_hora_str()}\n\n"
                f"📌 El geólogo deberá crear el *batch* para envío a laboratorio."
            )
        except Exception as e:
            print(f"[SGS-MUESTREO] Error: {e}")
            return "⚠️ Error al guardar. Intenta de nuevo."

    # ══════════════════════════════════════════════════════════
    # FLUJO DENSIDAD
    # ══════════════════════════════════════════════════════════

    elif paso == "fecha_densidad":
        fecha = _parsear_fecha(msg)
        if not fecha:
            return "❓ Formato: DD/MM (ej: 06/05) o escribe *hoy*."
        datos["fecha"] = fecha
        actualizar_sesion(sid, "tramo_desde_densidad", datos)
        return (
            f"✅ Fecha: *{fecha}*\n\n"
            f"¿*Desde* qué metro trabajaste?\n"
        )

    elif paso == "tramo_desde_densidad":
        try:
            desde = float(msg.replace(",", "."))
            if desde < 0: raise ValueError
            datos["desde_m"] = desde
        except ValueError:
            return "❓ Número válido. Ejemplo: 50.5"
        actualizar_sesion(sid, "tramo_hasta_densidad", datos)
        return (
            f"✅ Desde: *{desde:.2f} m*\n\n"
            f"¿*Hasta* qué metro?\n"
            f"Perforado hasta: {datos.get('prof_final', 0):.2f} m\n"
        )

    elif paso == "tramo_hasta_densidad":
        try:
            hasta = float(msg.replace(",", "."))
            desde = datos.get("desde_m", 0)
            if hasta <= desde:
                return f"❓ Debe ser mayor a {desde:.2f} m."
            datos["hasta_m"] = hasta
        except ValueError:
            return "❓ Número válido."
        metros = hasta - datos["desde_m"]
        actualizar_sesion(sid, "densidad_tecnico", datos)
        return (
            f"✅ Tramo: *{datos['desde_m']:.2f} → {hasta:.2f} m* "
            f"({metros:.2f} m)\n\n"
            f"¿Nombre del *técnico* responsable?\n"
        )

    elif paso == "densidad_tecnico":
        datos["tecnico"] = msg.strip()
        actualizar_sesion(sid, "dens_originales", datos)
        return (
            f"✅ Técnico: *{datos['tecnico']}*\n\n"
            f"¿Cuántas *muestras originales*?\n"
            f"Ejemplo: 45\n"
        )

    elif paso == "dens_originales":
        try:
            n = int(msg.strip())
            if n < 0: raise ValueError
            datos["originales"] = n
        except ValueError:
            return "❓ Número entero positivo."
        actualizar_sesion(sid, "dens_std", datos)
        return (
            f"✅ Originales: *{n}*\n\n"
            f"¿Cuántos *estándares*?\n"
            f"_(0 si no aplica)_\n"
        )

    elif paso == "dens_std":
        try:
            n = int(msg.strip())
            if n < 0: raise ValueError
            datos["std_densidad"] = n
        except ValueError:
            return "❓ Número entero (0 si no aplica)."
        actualizar_sesion(sid, "dens_dup", datos)
        return (
            f"✅ Estándares: *{n}*\n\n"
            f"¿Cuántos *duplicados*?\n"
            f"_(0 si no aplica)_\n"
        )

    elif paso == "dens_dup":
        try:
            n = int(msg.strip())
            if n < 0: raise ValueError
            datos["dup_densidad"] = n
        except ValueError:
            return "❓ Número entero (0 si no aplica)."

        total = (datos.get("originales", 0) +
                 datos.get("std_densidad", 0) + n)
        datos["cant_muestras"] = total
        actualizar_sesion(sid, "confirmacion_densidad", datos)
        return _resumen_densidad(datos)

    elif paso == "confirmacion_densidad":
        if msg.lower() in ("no", "cancelar", "n"):
            cerrar_sesion(usuario["id"])
            return "❌ Reporte cancelado."
        if msg.lower() not in ("sí", "si", "ok", "confirma", "yes"):
            return "¿Confirmas? Responde *sí* o *no*."
        try:
            ejecutar(
                """INSERT INTO etapas_sgs (
                       sondaje_id, etapa, fecha, desde_m, hasta_m,
                       tecnico, originales, std_densidad, dup_densidad,
                       cant_muestras, reportado_por, fuente
                   ) VALUES (
                       %s,'DENSIDAD',%s,%s,%s,
                       %s,%s,%s,%s,%s,
                       %s,'BOT'
                   )""",
                (
                    datos["sondaje_id"],
                    datos.get("fecha"),
                    datos.get("desde_m"), datos.get("hasta_m"),
                    datos.get("tecnico"),
                    datos.get("originales", 0),
                    datos.get("std_densidad", 0),
                    datos.get("dup_densidad", 0),
                    datos.get("cant_muestras", 0),
                    usuario["id"],
                )
            )
            actualizar_estado_etapa(datos["bhid"], "densidad", "EN_PROCESO")
            cerrar_sesion(usuario["id"])
            return (
                f"✅ *Densidad registrada*\n"
                f"⚖️ DENSIDAD | *{datos['bhid']}*\n"
                f"📏 {datos['desde_m']:.2f} → {datos['hasta_m']:.2f} m\n"
                f"📊 Orig: {datos.get('originales',0)} | "
                f"STD: {datos.get('std_densidad',0)} | "
                f"DUP: {datos.get('dup_densidad',0)} | "
                f"Total: *{datos.get('cant_muestras',0)}*\n"
                f"👤 {datos.get('tecnico','—')}\n"
                f"📅 {fecha_hora_str()}\n"
            )
        except Exception as e:
            print(f"[SGS-DENSIDAD] Error: {e}")
            return "⚠️ Error al guardar. Intenta de nuevo."

    # ══════════════════════════════════════════════════════════
    # FLUJO GENÉRICO (RQD, Fotografía)
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
            f"Ejemplo: 0, 50.5\n"
        )

    elif paso == "tramo_desde":
        try:
            datos["desde_m"] = float(msg.replace(",", "."))
        except:
            return "❓ Número válido. Ejemplo: 50.5"
        actualizar_sesion(sid, "tramo_hasta", datos)
        return "¿*Hasta* qué metro?\n"

    elif paso == "tramo_hasta":
        try:
            hasta = float(msg.replace(",", "."))
            if hasta <= datos.get("desde_m", 0):
                return f"❓ Debe ser mayor a {datos['desde_m']:.2f} m."
            datos["hasta_m"] = hasta
        except:
            return "❓ Número válido."
        metros = datos["hasta_m"] - datos["desde_m"]
        actualizar_sesion(sid, "tecnico_generico", datos)
        return (
            f"✅ Tramo: *{datos['desde_m']:.2f} — {datos['hasta_m']:.2f} m* "
            f"({metros:.2f} m)\n\n"
            f"¿Nombre del *técnico* responsable?\n"
        )

    elif paso == "tecnico_generico":
        datos["tecnico"] = msg.strip()
        actualizar_sesion(sid, "foto_opcional", datos)
        return (
            f"✅ Técnico: *{datos['tecnico']}*\n\n"
            f"📸 ¿Adjuntar foto?\n"
            f"Envía la foto o escribe *no*.\n"
        )

    elif paso == "foto_opcional":
        if msg.lower() in ("no", "n", "omitir"):
            datos["foto_url"] = None
        actualizar_sesion(sid, "confirmacion_generica", datos)
        return _resumen_generico(datos)

    elif paso == "confirmacion_generica":
        if msg.lower() in ("no", "cancelar"):
            cerrar_sesion(usuario["id"])
            return "❌ Reporte cancelado."
        if msg.lower() not in ("sí", "si", "ok", "confirma", "yes"):
            return "¿Confirmas? Responde *sí* o *no*."
        try:
            ejecutar(
                """INSERT INTO etapas_sgs (
                       sondaje_id, etapa, fecha, desde_m, hasta_m,
                       tecnico, foto_url, foto_descripcion,
                       reportado_por, fuente
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'BOT')""",
                (
                    datos.get("sondaje_id"), datos.get("etapa"),
                    datos.get("fecha"), datos.get("desde_m"), datos.get("hasta_m"),
                    datos.get("tecnico"),
                    datos.get("foto_url"), datos.get("foto_descripcion"),
                    usuario["id"]
                )
            )
            etapa_key = datos["etapa"].lower()
            actualizar_estado_etapa(datos["bhid"], etapa_key, "EN_PROCESO")
            cerrar_sesion(usuario["id"])
            return (
                f"✅ *{datos['etapa']} registrado*\n"
                f"🔬 {datos['etapa']} | *{datos['bhid']}*\n"
                f"📏 {datos['desde_m']:.2f} — {datos['hasta_m']:.2f} m\n"
                f"📅 {fecha_hora_str()}\n"
                f"👤 {datos.get('tecnico','—')}\n"
            )
        except Exception as e:
            print(f"[SGS-{datos.get('etapa','')}] Error: {e}")
            return "⚠️ Error al guardar. Intenta de nuevo."

    return "❓ Paso no reconocido. Escribe *hola* para reiniciar."


# ══════════════════════════════════════════════════════════════
# CONSULTAS SIN SESIÓN
# ══════════════════════════════════════════════════════════════

def consultar_sondajes_activos_sgs() -> str:
    rows = ejecutar(
        """SELECT s.bhid, m.codigo, e.codigo,
                  COALESCE(s.tajo_objetivo, s.cuerpo_objetivo, '—'),
                  s.profundidad_prog, COALESCE(s.profundidad_final, 0),
                  s.estado_logueo,
                  COALESCE((
                      SELECT MAX(eg.hasta_m) FROM etapas_sgs eg
                      JOIN sondajes ss ON eg.sondaje_id = ss.id
                      WHERE ss.bhid = s.bhid AND eg.etapa = 'LOGUEO'
                  ), 0)
           FROM sondajes s
           JOIN cat_maquinas m ON s.maquina_id = m.id
           JOIN cat_empresas e ON s.empresa_id = e.id
           WHERE s.estado_perforacion = 'EN_CURSO'
             AND s.estado_logueo IN ('PENDIENTE', 'EN_PROCESO')
           ORDER BY s.bhid""",
        fetchall=True
    )
    if not rows:
        return "✅ No hay sondajes activos con logueo pendiente."
    lineas = ["🔬 *SONDAJES ACTIVOS — LOGUEO PENDIENTE*", "─" * 32]
    for r in rows:
        bhid, maq, emp, obj, prog, final, est_log, log_hasta = r
        prog_f  = float(prog or 0)
        final_f = float(final or 0)
        log_f   = float(log_hasta or 0)
        pend    = final_f - log_f
        pct     = f"{final_f/prog_f*100:.0f}%" if prog_f > 0 else "—"
        icono   = "🟡" if est_log == "EN_PROCESO" else "🔴"
        lineas.append(
            f"\n{icono} *{bhid}* | {maq} ({emp})\n"
            f"   🎯 {obj} | Prog: {prog_f:.0f}m\n"
            f"   ⛏️ Perforado: {final_f:.1f}m ({pct})\n"
            f"   📝 Logueado hasta: {log_f:.1f}m"
            + (f" | ⚠️ Pendiente: {pend:.1f}m" if pend > 0.5 else "")
        )
    lineas.append(f"\n{'─'*32}\nTotal: *{len(rows)}* sondaje(s)")
    return "\n".join(lineas)


def consultar_finalizados_mes(mes: int = None, anio: int = None) -> str:
    hoy  = hora_peru().date()
    mes  = mes or hoy.month
    anio = anio or hoy.year
    rows = ejecutar(
        """SELECT s.bhid, m.codigo,
                  COALESCE(s.tajo_objetivo, s.cuerpo_objetivo, '—'),
                  s.profundidad_prog, COALESCE(s.profundidad_final, 0),
                  s.estado_logueo, s.fecha_fin_perf
           FROM sondajes s JOIN cat_maquinas m ON s.maquina_id = m.id
           WHERE s.estado_perforacion = 'FINALIZADO'
             AND EXTRACT(MONTH FROM s.fecha_fin_perf) = %s
             AND EXTRACT(YEAR  FROM s.fecha_fin_perf) = %s
           ORDER BY s.fecha_fin_perf DESC""",
        (mes, anio), fetchall=True
    )
    meses_es = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
                7:"Jul",8:"Ago",9:"Set",10:"Oct",11:"Nov",12:"Dic"}
    mes_str = f"{meses_es.get(mes, mes)}/{anio}"
    if not rows:
        return f"📭 No hay sondajes finalizados en *{mes_str}*."
    lineas = [f"✅ *FINALIZADOS — {mes_str}*", "─" * 32]
    for r in rows:
        bhid, maq, obj, prog, final, est_log, fecha_fin = r
        log_icon = {"COMPLETADO":"✅","EN_PROCESO":"🟡",
                    "PENDIENTE":"🔴"}.get(est_log, "⬜")
        try: fstr = fecha_fin.strftime("%d/%m") if fecha_fin else "—"
        except: fstr = str(fecha_fin)[:5]
        lineas.append(
            f"\n🔖 *{bhid}* | {maq}\n"
            f"   🎯 {obj}\n"
            f"   📏 {float(final or 0):.1f}/{float(prog or 0):.0f}m | Fin: {fstr}\n"
            f"   📝 Logueo: {log_icon} {est_log}"
        )
    lineas.append(f"\n{'─'*32}\nTotal: *{len(rows)}* finalizados en {mes_str}")
    return "\n".join(lineas)


def consultar_pendientes_logueo() -> str:
    rows = ejecutar(
        """SELECT s.bhid, s.estado_perforacion, m.codigo,
                  COALESCE(s.tajo_objetivo, s.cuerpo_objetivo, '—'),
                  COALESCE(s.profundidad_final, 0), s.estado_logueo,
                  COALESCE((
                      SELECT MAX(eg.hasta_m) FROM etapas_sgs eg
                      JOIN sondajes ss ON eg.sondaje_id = ss.id
                      WHERE ss.bhid = s.bhid AND eg.etapa = 'LOGUEO'
                  ), 0)
           FROM sondajes s JOIN cat_maquinas m ON s.maquina_id = m.id
           WHERE s.estado_logueo IN ('PENDIENTE', 'EN_PROCESO')
             AND s.estado_perforacion IN ('EN_CURSO', 'FINALIZADO')
           ORDER BY
               CASE s.estado_perforacion WHEN 'FINALIZADO' THEN 1 ELSE 2 END,
               s.bhid""",
        fetchall=True
    )
    if not rows:
        return "✅ Todos los sondajes tienen logueo al día."
    lineas = ["📋 *SONDAJES CON LOGUEO PENDIENTE*", "─" * 32]
    fin_count = en_curso_count = 0
    for r in rows:
        bhid, est_perf, maq, obj, final, est_log, log_hasta = r
        final_f = float(final or 0)
        log_f   = float(log_hasta or 0)
        pend    = final_f - log_f
        if est_perf == "FINALIZADO":
            fin_count += 1; icono = "🚨"; label = "FINALIZADO"
        else:
            en_curso_count += 1; icono = "⏳"; label = "EN CURSO"
        lineas.append(
            f"\n{icono} *{bhid}* | {label}\n"
            f"   🚜 {maq} | 🎯 {obj}\n"
            f"   📝 Logueado: {log_f:.1f}m / Perforado: {final_f:.1f}m"
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
    if msg in ETAPAS_SGS:
        return ETAPAS_SGS[msg]
    if msg.upper() in {"LOGUEO", "MUESTREO", "RQD", "FOTOGRAFIA", "DENSIDAD"}:
        return msg.upper()
    return None


def _ultimo_metro_logueado(bhid: str) -> float:
    row = ejecutar(
        """SELECT COALESCE(MAX(e.hasta_m), 0)
           FROM etapas_sgs e JOIN sondajes s ON e.sondaje_id = s.id
           WHERE s.bhid = %s AND e.etapa = 'LOGUEO'""",
        (bhid,), fetchone=True
    )
    return float(row[0]) if row else 0.0


def _aviso_muestreo_previo(bhid: str) -> str:
    rows = ejecutar(
        """SELECT e.fecha, e.desde_m, e.hasta_m, e.cant_muestras, e.tecnico
           FROM etapas_sgs e JOIN sondajes s ON e.sondaje_id = s.id
           WHERE s.bhid = %s AND e.etapa = 'MUESTREO'
           ORDER BY e.id DESC LIMIT 3""",
        (bhid,), fetchall=True
    )
    if not rows:
        return "\n¿*Fecha* del muestreo? (DD/MM o *hoy*)\n"
    lineas = ["\n⚠️ *Muestreo(s) previo(s) registrado(s):*"]
    for r in rows:
        fecha, desde, hasta, cant, tec = r
        try: fstr = fecha.strftime("%d/%m/%y") if fecha else "—"
        except: fstr = str(fecha)[:8]
        lineas.append(
            f"  📋 {fstr} | "
            f"{float(desde or 0):.1f}→{float(hasta or 0):.1f}m | "
            f"{cant or '?'} muestras | {tec or '—'}"
        )
    lineas.append(
        "\nSi es un *nuevo tramo*, continúa normalmente.\n"
        "Si hay un *error*, escribe *cancelar* y anula el reporte anterior.\n\n"
        "¿*Fecha* del muestreo? (DD/MM o *hoy*)\n"
    )
    return "\n".join(lineas)


def _aviso_densidad_previa(bhid: str) -> str:
    rows = ejecutar(
        """SELECT e.fecha, e.desde_m, e.hasta_m, e.cant_muestras, e.tecnico
           FROM etapas_sgs e JOIN sondajes s ON e.sondaje_id = s.id
           WHERE s.bhid = %s AND e.etapa = 'DENSIDAD'
           ORDER BY e.id DESC LIMIT 2""",
        (bhid,), fetchall=True
    )
    if not rows:
        return "\n¿*Fecha* del trabajo? (DD/MM o *hoy*)\n"
    lineas = ["\n⚠️ *Densidad previa registrada:*"]
    for r in rows:
        fecha, desde, hasta, cant, tec = r
        try: fstr = fecha.strftime("%d/%m/%y") if fecha else "—"
        except: fstr = str(fecha)[:8]
        lineas.append(
            f"  📋 {fstr} | "
            f"{float(desde or 0):.1f}→{float(hasta or 0):.1f}m | "
            f"{cant or '?'} muestras | {tec or '—'}"
        )
    lineas.append(
        "\nSi es un *nuevo tramo*, continúa normalmente.\n"
        "Si hay *error*, escribe *cancelar*.\n\n"
        "¿*Fecha* del trabajo? (DD/MM o *hoy*)\n"
    )
    return "\n".join(lineas)


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


def _ficha_logueo(sondaje: dict, logueado_hasta: float, prof_final: float,
                  prog_m: float, estado_perf: str, estado_logueo: str) -> str:
    bhid     = sondaje.get("bhid", "—")
    maquina  = sondaje.get("maquina", "—")
    empresa  = sondaje.get("empresa", "—")
    subcat   = sondaje.get("subcategoria", "—")
    objetivo = sondaje.get("tajo_objetivo") or sondaje.get("cuerpo_objetivo") or "—"
    nivel    = sondaje.get("nivel", "—")
    labor    = sondaje.get("labor", "—")
    diametro = sondaje.get("diametro", "—")
    perf_icon = {"EN_CURSO":"🟢","FINALIZADO":"✅","PLANIFICADO":"🔵"}.get(estado_perf,"⬜")
    pct_perf  = f"{prof_final/prog_m*100:.0f}%" if prog_m > 0 else "—"
    pend_m    = max(0.0, prof_final - logueado_hasta)
    if logueado_hasta == 0:
        log_str = "   📝 Sin logueo — empieza desde 0.0 m"
    elif pend_m <= 0.5:
        log_str = "   📝 ✅ Logueo al día"
    else:
        log_str = (
            f"   📝 Logueado hasta: *{logueado_hasta:.2f} m*\n"
            f"   ⚠️ Pendiente: *{pend_m:.2f} m* "
            f"({logueado_hasta:.1f} → {prof_final:.1f} m)"
        )
    return (
        f"✅ *{bhid}*\n{'─'*30}\n"
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


def _ficha_muestreo(sondaje: dict, prof_final: float, prog_m: float) -> str:
    bhid      = sondaje.get("bhid", "—")
    maquina   = sondaje.get("maquina", "—")
    empresa   = sondaje.get("empresa", "—")
    objetivo  = sondaje.get("tajo_objetivo") or sondaje.get("cuerpo_objetivo") or "—"
    diametro  = sondaje.get("diametro", "—")
    pct_perf  = f"{prof_final/prog_m*100:.0f}%" if prog_m > 0 else "—"
    est_mues  = sondaje.get("estado_muestreo", "PENDIENTE")
    mues_icon = {"COMPLETADO":"✅","EN_PROCESO":"🟡","PENDIENTE":"🔴"}.get(est_mues,"⬜")
    return (
        f"✅ *{bhid}*\n{'─'*30}\n"
        f"🚜 {maquina} ({empresa}) | {diametro}\n"
        f"🎯 {objetivo}\n"
        f"📏 Perforado: *{prof_final:.1f}/{prog_m:.0f} m* ({pct_perf})\n"
        f"🧪 Muestreo: {mues_icon} {est_mues}\n"
        f"{'─'*30}\n"
    )


def _ficha_densidad(sondaje: dict, prof_final: float, prog_m: float) -> str:
    bhid      = sondaje.get("bhid", "—")
    maquina   = sondaje.get("maquina", "—")
    empresa   = sondaje.get("empresa", "—")
    objetivo  = sondaje.get("tajo_objetivo") or sondaje.get("cuerpo_objetivo") or "—"
    diametro  = sondaje.get("diametro", "—")
    pct_perf  = f"{prof_final/prog_m*100:.0f}%" if prog_m > 0 else "—"
    est_dens  = sondaje.get("estado_densidad", "PENDIENTE")
    dens_icon = {"COMPLETADO":"✅","EN_PROCESO":"🟡","PENDIENTE":"🔴"}.get(est_dens,"⬜")
    return (
        f"✅ *{bhid}*\n{'─'*30}\n"
        f"🚜 {maquina} ({empresa}) | {diametro}\n"
        f"🎯 {objetivo}\n"
        f"📏 Perforado: *{prof_final:.1f}/{prog_m:.0f} m* ({pct_perf})\n"
        f"⚖️ Densidad: {dens_icon} {est_dens}\n"
        f"{'─'*30}\n"
    )


def _resumen_muestreo(datos: dict) -> str:
    ini       = datos.get("cod_muestra_ini", "—")
    fin       = datos.get("cod_muestra_fin", "—")
    total     = datos.get("cant_muestras", 0)
    ordinarias = datos.get("mues_ordinarias", 0)
    std_alta  = datos.get("mues_std_alta", 0)
    std_baja  = datos.get("mues_std_baja", 0)
    gemela    = datos.get("dup_gemela", 0)
    grueso    = datos.get("dup_grueso", 0)
    fino      = datos.get("dup_fino", 0)
    blancos   = datos.get("muestras_blanco", 0)
    qaqc      = datos.get("qaqc_total", 0)
    return (
        f"📋 *RESUMEN MUESTREO*\n{'─'*28}\n"
        f"🔖 Sondaje:  *{datos.get('bhid','—')}*\n"
        f"📏 Tramo:    {datos.get('desde_m',0):.2f} → {datos.get('hasta_m',0):.2f} m\n"
        f"📅 Fecha:    {datos.get('fecha','—')}\n"
        f"👤 Técnico:  {datos.get('tecnico','—')}\n"
        f"{'─'*28}\n"
        f"🔢 Rango:    *{ini}* → *{fin}*\n"
        f"{'─'*28}\n"
        f"  Ordinarias:      {ordinarias}\n"
        f"  STD alta ley:    {std_alta}\n"
        f"  STD baja ley:    {std_baja}\n"
        f"  Dup. gemela:     {gemela}\n"
        f"  Dup. grueso:     {grueso}\n"
        f"  Dup. fino:       {fino}\n"
        f"  Blancos:         {blancos}\n"
        f"{'─'*28}\n"
        f"  QAQC total:      {qaqc}\n"
        f"  *TOTAL:          {total}*\n"
        f"{'─'*28}\n"
        f"¿Confirmas? (*sí* / *no*)\n"
    )


def _resumen_densidad(datos: dict) -> str:
    orig  = datos.get("originales", 0)
    std   = datos.get("std_densidad", 0)
    dup   = datos.get("dup_densidad", 0)
    total = datos.get("cant_muestras", 0)
    return (
        f"📋 *RESUMEN DENSIDAD*\n{'─'*28}\n"
        f"🔖 Sondaje:  *{datos.get('bhid','—')}*\n"
        f"📏 Tramo:    {datos.get('desde_m',0):.2f} → {datos.get('hasta_m',0):.2f} m\n"
        f"📅 Fecha:    {datos.get('fecha','—')}\n"
        f"👤 Técnico:  {datos.get('tecnico','—')}\n"
        f"{'─'*28}\n"
        f"  Originales:  {orig}\n"
        f"  Estándar:    {std}\n"
        f"  Duplicado:   {dup}\n"
        f"{'─'*28}\n"
        f"  *TOTAL:      {total}*\n"
        f"{'─'*28}\n"
        f"¿Confirmas? (*sí* / *no*)\n"
    )


def _resumen_logueo(datos: dict) -> str:
    desde = datos.get("desde_m", 0)
    hasta = datos.get("hasta_m", 0)
    return (
        f"📋 *RESUMEN LOGUEO*\n{'─'*28}\n"
        f"🔖 Sondaje: *{datos.get('bhid','—')}*\n"
        f"📏 Tramo:   {desde:.2f} → {hasta:.2f} m ({hasta - desde:.2f} m)\n"
        f"📅 Fecha:   {datos.get('fecha','—')}\n"
        f"👤 Técnico: {datos.get('tecnico', datos.get('_nombre_usuario','—'))}\n"
        + (f"💬 Obs:     {datos['comentario']}\n" if datos.get("comentario") else "")
        + f"📸 Foto:    {'✅' if datos.get('foto_url') else 'No'}\n"
        f"{'─'*28}\n"
        f"¿Confirmas? (*sí* / *no*)\n"
    )


def _resumen_generico(datos: dict) -> str:
    etapa = datos.get("etapa", "—")
    return (
        f"📋 *RESUMEN {etapa}*\n{'─'*28}\n"
        f"🔖 Sondaje: *{datos.get('bhid','—')}*\n"
        f"📏 Tramo:   {datos.get('desde_m',0):.2f} — {datos.get('hasta_m',0):.2f} m\n"
        f"📅 Fecha:   {datos.get('fecha','—')}\n"
        f"👤 Técnico: {datos.get('tecnico','—')}\n"
        f"📸 Foto:    {'Sí' if datos.get('foto_url') else 'No'}\n"
        f"{'─'*28}\n"
        f"¿Confirmas? (*sí* / *no*)\n"
    )
