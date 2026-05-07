"""
FLUJO SGS — Logueo, Muestreo, RQD, Fotografía, Densidad
Para rol SGS.
"""
from db.sesiones import actualizar_sesion, cerrar_sesion
from db.sondajes import buscar_sondaje, actualizar_estado_etapa
from db.conexion import ejecutar
from config import fecha_hora_str, hora_peru, ETAPAS_SGS

FLUJO = "SGS"

def iniciar(usuario: dict, sesion_id: int) -> str:
    menu = "\n".join([f"  *{k}* — {v.capitalize()}"
                      for k, v in ETAPAS_SGS.items()])
    actualizar_sesion(sesion_id, "tipo_etapa", {})
    return (
        f"🔬 *REPORTE SGS*\n"
        f"📅 {fecha_hora_str()}\n\n"
        f"¿Qué actividad vas a reportar?\n\n"
        f"{menu}\n\n"
        f"Responde con el número.\n"
    )

def procesar(mensaje: str, usuario: dict, sesion: dict) -> str:
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    # ── Tipo de etapa ─────────────────────────────────────────
    if paso == "tipo_etapa":
        if msg not in ETAPAS_SGS:
            return f"❓ Responde con un número del 1 al {len(ETAPAS_SGS)}."
        datos["etapa"] = ETAPAS_SGS[msg]
        actualizar_sesion(sid, "sondaje", datos)
        return (
            f"✅ Etapa: *{datos['etapa']}*\n\n"
            f"¿Código del sondaje?\n"
            f"Ejemplo: 8422, PECLD08422\n"
        )

    # ── Sondaje ───────────────────────────────────────────────
    elif paso == "sondaje":
        sondaje = buscar_sondaje(msg)
        if not sondaje:
            return f"❌ No encontré *{msg}*. Verifica el código."
        datos["bhid"]      = sondaje["bhid"]
        datos["sondaje_id"] = _obtener_id(sondaje["bhid"])
        actualizar_sesion(sid, "fecha_trabajo", datos,
                          sondaje_context=sondaje["bhid"])
        return (
            f"✅ Sondaje: *{sondaje['bhid']}*\n"
            f"   Prog: {sondaje.get('prog_m','—')} m | "
            f"Final: {sondaje.get('final_m',0):.1f} m\n\n"
            f"¿*Fecha* del trabajo? (DD/MM o *hoy*)\n"
        )

    # ── Fecha ─────────────────────────────────────────────────
    elif paso == "fecha_trabajo":
        if msg.lower() == "hoy":
            datos["fecha"] = hora_peru().strftime("%Y-%m-%d")
        else:
            try:
                from datetime import datetime
                parsed = datetime.strptime(msg.replace("-","/"), "%d/%m")
                datos["fecha"] = parsed.replace(year=hora_peru().year).strftime("%Y-%m-%d")
            except:
                return "❓ Formato: DD/MM (ej: 06/05) o escribe *hoy*."
        actualizar_sesion(sid, "tramo_desde", datos)
        return (
            f"✅ Fecha: *{datos['fecha']}*\n\n"
            f"¿*Desde* qué metro trabajaste hoy?\n"
            f"Ejemplo: 0, 50.5, 269.30\n"
        )

    # ── Tramo desde ───────────────────────────────────────────
    elif paso == "tramo_desde":
        try:
            datos["desde_m"] = float(msg.replace(",", "."))
        except:
            return "❓ Ingresa un número. Ejemplo: 50.5"
        actualizar_sesion(sid, "tramo_hasta", datos)
        return f"¿*Hasta* qué metro?\n"

    # ── Tramo hasta ───────────────────────────────────────────
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

    # ── Técnico ───────────────────────────────────────────────
    elif paso == "tecnico":
        datos["tecnico"] = msg.strip()
        etapa = datos.get("etapa", "")

        # Campos adicionales por etapa
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
            # LOGUEO, RQD, FOTOGRAFIA → ir a foto
            actualizar_sesion(sid, "foto_opcional", datos)
            return (
                f"✅ Técnico: *{datos['tecnico']}*\n\n"
                f"📸 ¿Deseas adjuntar una foto de este tramo?\n"
                f"Envía la foto o escribe *no*.\n"
            )

    # ── Muestreo: código inicial ──────────────────────────────
    elif paso == "cod_muestra_ini":
        datos["cod_muestra_ini"] = msg.strip()
        actualizar_sesion(sid, "cod_muestra_fin", datos)
        return f"¿*Código de muestra final*?\n"

    elif paso == "cod_muestra_fin":
        datos["cod_muestra_fin"] = msg.strip()
        # Calcular cantidad si son numéricos
        try:
            cant = int(datos["cod_muestra_fin"]) - int(datos["cod_muestra_ini"]) + 1
            datos["cant_muestras"] = cant
        except:
            datos["cant_muestras"] = None
        actualizar_sesion(sid, "foto_opcional", datos)
        cant_str = f" ({datos['cant_muestras']} muestras)" if datos.get("cant_muestras") else ""
        return (
            f"✅ Muestras: *{datos['cod_muestra_ini']}* → *{datos['cod_muestra_fin']}*{cant_str}\n\n"
            f"📸 ¿Adjuntar foto? Envía o escribe *no*.\n"
        )

    # ── Densidad ──────────────────────────────────────────────
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

    # ── Foto opcional ─────────────────────────────────────────
    elif paso == "foto_opcional":
        if msg.lower() in ("no", "n", "omitir"):
            datos["foto_url"] = None
        elif msg.startswith("FOTO:"):
            datos["foto_url"]          = msg.replace("FOTO:", "").strip()
            datos["foto_descripcion"]  = f"Tramo {datos.get('desde_m',0):.1f}-{datos.get('hasta_m',0):.1f}m"
        actualizar_sesion(sid, "confirmacion", datos)
        return _resumen_sgs(datos)

    # ── Confirmación ──────────────────────────────────────────
    elif paso == "confirmacion":
        if msg.lower() in ("no", "cancelar"):
            cerrar_sesion(usuario["id"])
            return "❌ Reporte cancelado."
        if msg.lower() not in ("sí", "si", "ok", "confirma"):
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
            # Actualizar estado en sondaje maestro
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
        lineas.append(f"🔢 Muestras: {datos.get('cod_muestra_ini','—')} → {datos.get('cod_muestra_fin','—')}")
        if datos.get("cant_muestras"):
            lineas.append(f"   Total: {datos['cant_muestras']} muestras")
    if etapa == "DENSIDAD":
        lineas.append(f"📊 STD: {datos.get('std_densidad','—')} | DUP: {datos.get('dup_densidad','—')} | Orig: {datos.get('originales','—')}")
    lineas.append(f"📸 Foto: {'Sí' if datos.get('foto_url') else 'No'}")
    lineas.append(f"{'─'*28}")
    lineas.append("¿Confirmas? (*sí* / *no*)")
    return "\n".join(lineas)

def _obtener_id(bhid: str) -> int | None:
    row = ejecutar("SELECT id FROM sondajes WHERE bhid=%s", (bhid,), fetchone=True)
    return row[0] if row else None
