"""
FLUJO DE MATRICULACIÓN DE SONDAJES
Solo para roles GEOLOGO y ADMIN.
Incluye anulación y reutilización de BHID.
Pasos: tipo → objetivo → profundidad → azimut → inclinacion →
       nivel → labor → maquina → diametro → codigo_ddh → confirmacion
"""
from db.sesiones import actualizar_sesion, cerrar_sesion
from db.sondajes import (matricular_sondaje, obtener_subcategorias_activas,
                          obtener_maquinas_con_empresa, siguiente_bhid,
                          buscar_sondaje)
from db.conexion import ejecutar
from config import fecha_hora_str
from config import hora_peru as _hora

FLUJO = "MATRICULA"


def iniciar(usuario: dict, sesion_id: int) -> str:
    """Llamado desde router — el menú interactivo ya fue enviado."""
    subcat = obtener_subcategorias_activas()
    actualizar_sesion(sesion_id, "tipo_sondaje",
                      {"subcat_opciones": [s["codigo"] for s in subcat],
                       "subcat_ids":      [s["id"]     for s in subcat],
                       "subcat_nombres":  [s["nombre"] for s in subcat]})
    return None  # router ya envió el menú interactivo


def iniciar_anulacion(usuario: dict, sesion_id: int) -> str:
    actualizar_sesion(sesion_id, "anular_buscar", {})
    return (
        "🗑️ *ANULAR SONDAJE*\n\n"
        "¿Cuál es el código del sondaje a anular?\n"
        "Ejemplo: 8422, PECLD08422\n"
    )


def procesar(mensaje: str, usuario: dict, sesion: dict) -> str:
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    # ══ FLUJO DE ANULACIÓN ════════════════════════════════════

    if paso == "anular_buscar":
        sondaje = buscar_sondaje(msg)
        if not sondaje:
            return f"❌ No encontré *{msg}*. Verifica el código."

        # Verificar si ya está anulado
        row = ejecutar(
            "SELECT estado_logueo FROM sondajes WHERE bhid = %s",
            (sondaje["bhid"],), fetchone=True
        )
        datos["bhid_anular"] = sondaje["bhid"]
        datos["sondaje_info"] = sondaje

        # Contar registros asociados
        avances = ejecutar(
            """SELECT COUNT(*) FROM avance_perforacion ap
               JOIN sondajes s ON ap.sondaje_id = s.id
               WHERE s.bhid = %s AND ap.estado = 'ACTIVO'""",
            (sondaje["bhid"],), fetchone=True
        )
        etapas = ejecutar(
            """SELECT COUNT(*) FROM etapas_sgs e
               JOIN sondajes s ON e.sondaje_id = s.id
               WHERE s.bhid = %s""",
            (sondaje["bhid"],), fetchone=True
        )
        cnt_avances = avances[0] if avances else 0
        cnt_etapas  = etapas[0]  if etapas  else 0
        datos["cnt_avances"] = cnt_avances
        datos["cnt_etapas"]  = cnt_etapas

        actualizar_sesion(sid, "anular_confirmar", datos)
        objetivo = sondaje.get("tajo_objetivo") or sondaje.get("cuerpo_objetivo","—")
        return (
            f"⚠️ *CONFIRMAR ANULACIÓN*\n"
            f"{'─'*30}\n"
            f"🔖 Sondaje:   *{sondaje['bhid']}*\n"
            f"📂 Tipo:      {sondaje.get('subcategoria','—')}\n"
            f"🎯 Objetivo:  {objetivo}\n"
            f"🚜 Máquina:   {sondaje.get('maquina','—')}\n"
            f"{'─'*30}\n"
            f"⛏️ Avances registrados:    {cnt_avances}\n"
            f"🔬 Etapas SGS registradas: {cnt_etapas}\n"
            f"{'─'*30}\n\n"
            f"⚠️ *Todo el historial será anulado.*\n\n"
            f"¿Confirmas la anulación? (*sí* / *no*)\n"
        )

    elif paso == "anular_confirmar":
        if msg.lower() in ("no", "cancelar", "n"):
            cerrar_sesion(usuario["id"])
            return "❌ Anulación cancelada."
        if msg.lower() not in ("sí", "si", "yes", "ok"):
            return "¿Confirmas? *sí* o *no*."

        bhid = datos["bhid_anular"]
        try:
            # Anular avances de perforación
            ejecutar(
                """UPDATE avance_perforacion SET estado = 'ANULADO'
                   WHERE sondaje_id = (SELECT id FROM sondajes WHERE bhid = %s)""",
                (bhid,)
            )
            # Anular batches vinculados
            ejecutar(
                """UPDATE batch_sondajes SET numero_envio = -1
                   WHERE sondaje_id = (SELECT id FROM sondajes WHERE bhid = %s)""",
                (bhid,)
            )
            # Anular sondaje principal
            ejecutar(
                """UPDATE sondajes SET
                       estado_logueo      = 'NO_APLICA',
                       estado_muestreo    = 'NO_APLICA',
                       estado_rqd         = 'NO_APLICA',
                       estado_fotografia  = 'NO_APLICA',
                       estado_densidad    = 'NO_APLICA',
                       estado_laboratorio = 'NO_APLICA',
                       estado_modelado    = 'NO_APLICA',
                       campana            = CONCAT('ANULADO_', COALESCE(campana, '')),
                       actualizado_en     = NOW()
                   WHERE bhid = %s""",
                (bhid,)
            )
            cerrar_sesion(usuario["id"])
            return (
                f"✅ *Sondaje anulado*\n\n"
                f"🔖 {bhid}\n"
                f"⛏️ {datos['cnt_avances']} avances anulados\n"
                f"🔬 {datos['cnt_etapas']} etapas SGS anuladas\n"
                f"📅 {fecha_hora_str()}\n"
                f"👤 {usuario['nombre']}\n\n"
                f"El BHID queda disponible para reutilización."
            )
        except Exception as e:
            print(f"[MATRICULA] Error anulando: {e}")
            return "⚠️ Error al anular. Contacta al administrador."

    # ══ FLUJO DE MATRICULACIÓN ════════════════════════════════

    elif paso == "tipo_sondaje":
        opciones = datos.get("subcat_opciones", [])
        ids      = datos.get("subcat_ids", [])
        nombres  = datos.get("subcat_nombres", [])

        # Acepta número o código directo (desde botón interactivo)
        if msg.isdigit() and 1 <= int(msg) <= len(opciones):
            idx = int(msg) - 1
        elif msg.upper() in opciones:
            idx = opciones.index(msg.upper())
        else:
            return f"❓ Responde con un número del 1 al {len(opciones)}."

        datos["subcategoria_codigo"]  = opciones[idx]
        datos["subcategoria_id"]      = ids[idx]
        datos["subcategoria_nombre"]  = nombres[idx]

        if opciones[idx] == "INFILL":
            actualizar_sesion(sid, "infill_nivel", datos)
            return (
                f"✅ Tipo: *INFILL*\n\n"
                f"¿*Nivel base* del tajo (metros)?\n"
                f"Ejemplo: 1710, 1850, 1940\n"
            )
        else:
            actualizar_sesion(sid, "objetivo_recategorizacion", datos)
            return (
                f"✅ Tipo: *{nombres[idx]}*\n\n"
                f"¿Cuál es el *cuerpo / objetivo*?\n"
                f"Ejemplo: OB1, EXT-OB1, OB1_01, OB6\n"
            )

    elif paso == "infill_nivel":
        try:
            nivel_tajo = int(msg.strip())
            datos["infill_nivel"] = nivel_tajo
        except ValueError:
            return "❓ Número entero. Ejemplo: 1710"
        actualizar_sesion(sid, "infill_cuerpo", datos)
        return (
            f"✅ Nivel base: *{nivel_tajo}*\n\n"
            f"¿*Cuerpo / objetivo*?\n"
            f"Ejemplo: OB5B, OB1, EXT-OB1\n"
        )

    elif paso == "infill_cuerpo":
        datos["infill_cuerpo"] = msg.strip().upper()
        actualizar_sesion(sid, "infill_tajo", datos)
        return (
            f"✅ Cuerpo: *{datos['infill_cuerpo']}*\n\n"
            f"¿*Número de tajo*?\n"
            f"Ejemplo: T-002, T-021\n"
        )

    elif paso == "infill_tajo":
        tajo_num = msg.strip().upper()
        if not tajo_num.startswith("T-"):
            tajo_num = f"T-{tajo_num.lstrip('0') or tajo_num}"
        tajo_num = tajo_num.upper()
        nivel    = datos.get("infill_nivel", "")
        cuerpo   = datos.get("infill_cuerpo", "")
        nombre_tajo = f"{nivel}_{cuerpo}_{tajo_num}"
        datos["tajo_objetivo"] = nombre_tajo
        datos["tajo_num"]      = tajo_num
        datos["infill_nombre"] = nombre_tajo

        # Buscar o crear tajo en BD
        tajo_row = ejecutar(
            "SELECT id, dxf_url, dxf_fecha FROM tajos "
            "WHERE nivel = %s AND cuerpo = %s AND tajo = %s LIMIT 1",
            (nivel, cuerpo, tajo_num), fetchone=True
        )
        if tajo_row:
            datos["tajo_id"]  = tajo_row[0]
            datos["dxf_url"]  = tajo_row[1]
            datos["dxf_fecha"] = str(tajo_row[2]) if tajo_row[2] else None
        else:
            # Crear registro de tajo
            nuevo = ejecutar(
                "INSERT INTO tajos (nivel, cuerpo, tajo) "
                "VALUES (%s, %s, %s) RETURNING id",
                (nivel, cuerpo, tajo_num), fetchone=True
            )
            datos["tajo_id"] = nuevo[0] if nuevo else None
            datos["dxf_url"] = None

        actualizar_sesion(sid, "infill_dxf", datos)

        if datos.get("dxf_url"):
            return (
                f"✅ Tajo: *{nombre_tajo}*\n"
                f"📎 Ya tiene DXF subido ({datos['dxf_fecha']})\n\n"
                f"¿Reemplazar el DXF o mantener el actual?\n"
                f"  *mantener* — Usar el existente\n"
                f"  *reemplazar* — Subir nuevo archivo\n"
            )
        return (
            f"✅ Tajo: *{nombre_tajo}*\n\n"
            f"📎 ¿Adjuntas el sólido DXF?\n"
            f"  Adjunta el archivo ahora\n"
            f"  *no tengo* — Continuar sin DXF\n"
            f"  *regularizar* — Marcar pendiente\n"
        )

    elif paso == "objetivo_infill":
        # Fallback legacy
        datos["tajo_objetivo"] = msg.upper()
        actualizar_sesion(sid, "profundidad", datos)
        return (
            f"✅ Tajo objetivo: *{datos['tajo_objetivo']}*\n\n"
            f"¿*Profundidad programada* (metros)?\n"
            f"Ejemplo: 150, 295, 320.50\n"
        )

    elif paso == "infill_dxf":
        # Puede venir como texto o como archivo (foto_url en datos)
        dxf_url = datos.get("dxf_archivo_url")  # seteado por main.py si adjunta

        if dxf_url:
            # Archivo recibido — guardar en tajos
            tajo_id = datos.get("tajo_id")
            if tajo_id:
                ejecutar(
                    "UPDATE tajos SET dxf_url = %s, dxf_fecha = %s WHERE id = %s",
                    (dxf_url, _hora().strftime("%Y-%m-%d"), tajo_id)
                )
            datos["dxf_url"]      = dxf_url
            datos["estado_dxf"]   = "SUBIDO"
            actualizar_sesion(sid, "profundidad", datos)
            return (
                f"✅ DXF registrado para *{datos.get('infill_nombre','—')}*\n\n"
                f"¿*Profundidad programada* (metros)?\n"
                f"Ejemplo: 150, 295, 320.50\n"
            )

        if msg.lower() == "mantener":
            datos["estado_dxf"] = "SUBIDO"
            actualizar_sesion(sid, "profundidad", datos)
            return (
                f"✅ DXF existente mantenido.\n\n"
                f"¿*Profundidad programada* (metros)?\n"
            )

        if msg.lower() in ("reemplazar",):
            datos["esperando_dxf"] = True
            actualizar_sesion(sid, "infill_dxf", datos)
            return "📎 Adjunta el nuevo archivo DXF:\n"

        if msg.lower() in ("no tengo", "no", "sin dxf"):
            datos["estado_dxf"] = "SIN_DXF"
            actualizar_sesion(sid, "profundidad", datos)
            return (
                f"⚠️ Sin DXF — puedes regularizarlo después.\n\n"
                f"¿*Profundidad programada* (metros)?\n"
            )

        if msg.lower() in ("regularizar", "pendiente"):
            tajo_id = datos.get("tajo_id")
            if tajo_id:
                ejecutar(
                    "UPDATE tajos SET estado_infill = 'DXF_PENDIENTE' WHERE id = %s",
                    (tajo_id,)
                )
            datos["estado_dxf"] = "PENDIENTE"
            actualizar_sesion(sid, "profundidad", datos)
            return (
                f"📌 DXF marcado como *pendiente* para regularizar.\n\n"
                f"¿*Profundidad programada* (metros)?\n"
            )

        return (
            f"📎 ¿Adjuntas el sólido DXF?\n"
            f"  Adjunta el archivo\n"
            f"  *no tengo* — Continuar sin DXF\n"
            f"  *regularizar* — Marcar pendiente\n"
        )

    elif paso == "objetivo_recategorizacion":
        datos["cuerpo_objetivo"] = msg.upper()
        actualizar_sesion(sid, "profundidad", datos)
        return (
            f"✅ Objetivo: *{datos['cuerpo_objetivo']}*\n\n"
            f"¿*Profundidad programada* (metros)?\n"
            f"Ejemplo: 150, 295, 320.50\n"
        )

    elif paso == "profundidad":
        try:
            prof = float(msg.replace(",", "."))
            if prof <= 0:
                raise ValueError
            datos["profundidad_prog"] = prof
        except ValueError:
            return "❓ Número válido. Ejemplo: 295 o 320.50"
        actualizar_sesion(sid, "azimut", datos)
        return (
            f"✅ Profundidad: *{prof:.1f} m*\n\n"
            f"¿*Azimut* programado (°)?\n"
            f"Ejemplo: 39, 285, 346\n"
        )

    elif paso == "azimut":
        try:
            az = float(msg.replace("°", "").strip())
            if az < 0 or az > 360:
                raise ValueError
            datos["azimut_prog"] = az
        except ValueError:
            return "❓ Azimut entre 0 y 360. Ejemplo: 39"
        actualizar_sesion(sid, "inclinacion", datos)
        return (
            f"✅ Azimut: *{az:.1f}°*\n\n"
            f"¿*Inclinación* programada (°)?\n"
            f"Negativo = hacia abajo. Ejemplo: -17, -42, +8\n"
        )

    elif paso == "inclinacion":
        try:
            dip = float(msg.replace("°", "").strip())
            datos["dip_prog"] = dip
        except ValueError:
            return "❓ Ejemplo: -17 o +8"
        actualizar_sesion(sid, "nivel", datos)
        return (
            f"✅ Inclinación: *{dip:.1f}°*\n\n"
            f"¿En qué *nivel* se ubica?\n"
            f"Ejemplo: 1710, 1850, 1940\n"
        )

    elif paso == "nivel":
        try:
            nivel = int(msg.strip())
            datos["nivel_prog"] = nivel
        except ValueError:
            return "❓ Número entero. Ejemplo: 1940"
        actualizar_sesion(sid, "labor", datos)
        return (
            f"✅ Nivel: *{nivel}*\n\n"
            f"¿*Labor* de la boca del sondaje?\n"
            f"Ejemplo: Cx.010, Bp.650, Ga.714\n"
        )

    elif paso == "labor":
        datos["labor"] = msg.strip()
        actualizar_sesion(sid, "diametro", datos)
        # El router enviará botones de diámetro
        return f"✅ Labor: *{datos['labor']}*"

    elif paso == "diametro":
        diams = {"1": "BQ", "2": "NQ", "3": "HQ", "4": "PQ",
                 "bq": "BQ", "nq": "NQ", "hq": "HQ", "pq": "PQ"}
        diam = diams.get(msg.lower())
        if not diam:
            return "❓ Responde BQ, NQ, HQ o PQ."
        datos["diametro"] = diam
        actualizar_sesion(sid, "maquina", datos)
        # El router enviará lista de máquinas
        return f"✅ Diámetro: *{diam}*"

    elif paso == "maquina":
        maquinas = obtener_maquinas_con_empresa()
        nueva_idx = len(maquinas) + 1

        # Puede venir como número o como __maq_id_X__
        if msg.startswith("__maq_id_"):
            try:
                maq_id = int(msg.replace("__maq_id_", ""))
                for m in maquinas:
                    if m["id"] == maq_id:
                        datos["maquina_id"]  = m["id"]
                        datos["maquina_cod"] = m["codigo"]
                        datos["empresa_id"]  = m["empresa_id"]
                        actualizar_sesion(sid, "codigo_ddh", datos)
                        return _sugerir_bhid(datos, sid)
            except:
                pass

        if msg.isdigit():
            n = int(msg)
            if n == nueva_idx:
                actualizar_sesion(sid, "nueva_maquina", datos)
                return (
                    "🆕 *Nueva máquina*\n\n"
                    "Escribe el código.\n"
                    "Ejemplo: DCAT-15, FB100-03\n"
                )
            if 1 <= n <= len(maquinas):
                m = maquinas[n - 1]
                datos["maquina_id"]  = m["id"]
                datos["maquina_cod"] = m["codigo"]
                datos["empresa_id"]  = m["empresa_id"]
                actualizar_sesion(sid, "codigo_ddh", datos)
                return _sugerir_bhid(datos, sid)

        return f"❓ Responde con un número del 1 al {nueva_idx}."

    elif paso == "nueva_maquina":
        nuevo_cod = msg.strip().upper()
        row = ejecutar(
            """INSERT INTO cat_maquinas (codigo, empresa_id, sufijo_tarifa, activo)
               VALUES (%s, 1, '', TRUE)
               ON CONFLICT (codigo) DO UPDATE SET activo=TRUE
               RETURNING id""",
            (nuevo_cod,), fetchone=True
        )
        if row:
            datos["maquina_id"]  = row[0]
            datos["maquina_cod"] = nuevo_cod
            datos["empresa_id"]  = 1
        actualizar_sesion(sid, "codigo_ddh", datos)
        return _sugerir_bhid(datos, sid)

    elif paso == "codigo_ddh":
        msg_low = msg.lower()
        if msg_low in ("confirma", "si", "sí", "ok", "yes"):
            bhid = datos["bhid_sugerido"]
        elif msg_low == "provisional":
            ts = _hora().strftime("%d%m-%H%M")
            bhid = f"TEMP-{datos.get('maquina_cod','X').replace('-','')}-{ts}"
            datos["es_provisional"] = True
        else:
            bhid = msg.strip().upper().replace("-", "").replace(" ", "")
            if not bhid.startswith("PECLD"):
                digitos = ''.join(filter(str.isdigit, bhid))
                bhid = f"PECLD{digitos.zfill(5)}"

        # Verificar si existe
        row = ejecutar(
            "SELECT campana FROM sondajes WHERE bhid = %s",
            (bhid,), fetchone=True
        )
        if row:
            campana = row[0] or ""
            if campana.startswith("ANULADO"):
                # BHID anulado — ofrecer reutilizar
                datos["bhid"]           = bhid
                datos["bhid_anulado"]   = True
                actualizar_sesion(sid, "reutilizar_bhid", datos)
                return (
                    f"⚠️ *{bhid}* existe pero está *anulado*.\n\n"
                    f"¿Deseas reutilizar este código con los nuevos datos?\n"
                    f"  *sí* — Reutilizar\n"
                    f"  *no* — Elegir otro código\n"
                )
            else:
                return (
                    f"⚠️ *{bhid}* ya existe y está activo.\n"
                    f"Elige otro código o escribe *provisional*.\n"
                )

        datos["bhid"] = bhid
        datos["categoria_id"] = _obtener_cat_id()
        actualizar_sesion(sid, "confirmacion", datos)
        return _resumen_matricula(datos)

    elif paso == "reutilizar_bhid":
        if msg.lower() in ("no", "n"):
            actualizar_sesion(sid, "codigo_ddh", datos)
            return (
                f"¿Cuál es el nuevo código DDH?\n"
                f"Siguiente disponible: *{siguiente_bhid()}*\n"
            )
        if msg.lower() not in ("sí", "si", "yes", "ok"):
            return "¿Reutilizar? *sí* o *no*."

        datos["categoria_id"]  = _obtener_cat_id()
        datos["reutilizando"]  = True
        actualizar_sesion(sid, "confirmacion", datos)
        return (
            f"✅ Reutilizando *{datos['bhid']}*\n\n"
            + _resumen_matricula(datos)
        )

    elif paso == "confirmacion":
        if msg.lower() in ("no", "cancelar", "n"):
            cerrar_sesion(usuario["id"])
            return "❌ Matriculación cancelada."
        if msg.lower() not in ("sí", "si", "yes", "ok", "confirma"):
            return "¿Confirmas? *sí* o *no*."

        try:
            if datos.get("reutilizando"):
                # Actualizar registro existente
                ejecutar(
                    """UPDATE sondajes SET
                           categoria_id       = %s,
                           subcategoria_id    = %s,
                           campana            = NULL,
                           tajo_objetivo      = %s,
                           cuerpo_objetivo    = %s,
                           profundidad_prog   = %s,
                           azimut_prog        = %s,
                           dip_prog           = %s,
                           nivel_prog         = %s,
                           labor              = %s,
                           diametro           = %s,
                           empresa_id         = %s,
                           maquina_id         = %s,
                           profundidad_final  = NULL,
                           estado_logueo      = 'PENDIENTE',
                           estado_muestreo    = 'PENDIENTE',
                           estado_rqd         = 'PENDIENTE',
                           estado_fotografia  = 'PENDIENTE',
                           estado_densidad    = 'PENDIENTE',
                           estado_laboratorio = 'PENDIENTE',
                           estado_modelado    = 'PENDIENTE',
                           fecha_inicio_perf  = NULL,
                           fecha_fin_perf     = NULL,
                           matriculado_por    = %s,
                           actualizado_en     = NOW()
                       WHERE bhid = %s""",
                    (
                        datos["categoria_id"], datos["subcategoria_id"],
                        datos.get("tajo_objetivo"), datos.get("cuerpo_objetivo"),
                        datos["profundidad_prog"],
                        datos.get("azimut_prog"), datos.get("dip_prog"),
                        datos.get("nivel_prog"), datos.get("labor"),
                        datos.get("diametro", "NQ"),
                        datos["empresa_id"], datos["maquina_id"],
                        usuario["id"], datos["bhid"]
                    )
                )
                bhid = datos["bhid"]
            else:
                bhid = matricular_sondaje(datos, usuario["id"])

            cerrar_sesion(usuario["id"])
            if bhid:
                return (
                    f"✅ *Sondaje matriculado*\n\n"
                    f"🔖 Código: *{bhid}*\n"
                    f"📅 {fecha_hora_str()}\n"
                    f"👤 {usuario['nombre']}\n\n"
                    f"Ya disponible para perforistas y SGS."
                )
            return "⚠️ Error al registrar. El código ya existe o hay un problema en BD."

        except Exception as e:
            print(f"[MATRICULA] Error: {e}")
            return "⚠️ Error al guardar. Contacta al administrador."

    return "❓ Escribe *hola* para reiniciar."


# ── HELPERS ───────────────────────────────────────────────────

def _sugerir_bhid(datos: dict, sid: int) -> str:
    bhid_sugerido = siguiente_bhid()
    datos["bhid_sugerido"] = bhid_sugerido
    actualizar_sesion(sid, "codigo_ddh", datos)
    return (
        f"✅ Máquina: *{datos['maquina_cod']}*\n\n"
        f"¿Cuál es el *código DDH*?\n"
        f"Siguiente disponible: *{bhid_sugerido}*\n\n"
        f"Escribe el código, *confirma* para usar el sugerido,\n"
        f"o *provisional* si aún no tiene código.\n"
    )

def _resumen_matricula(datos: dict) -> str:
    objetivo = datos.get("tajo_objetivo") or datos.get("cuerpo_objetivo", "—")
    prov = " *(PROVISIONAL)*" if datos.get("es_provisional") else ""
    return (
        f"📋 *RESUMEN DEL SONDAJE*{prov}\n"
        f"{'─'*30}\n"
        f"🔖 Código:      *{datos.get('bhid','—')}*\n"
        f"📂 Tipo:        {datos.get('subcategoria_nombre','—')}\n"
        f"🎯 Objetivo:    {objetivo}\n"
        f"📏 Prog:        {datos.get('profundidad_prog','—')} m\n"
        f"🧭 Azimut:      {datos.get('azimut_prog','—')}°\n"
        f"📐 Inclinación: {datos.get('dip_prog','—')}°\n"
        f"🏔️ Nivel:       {datos.get('nivel_prog','—')}\n"
        f"⛏️ Labor:       {datos.get('labor','—')}\n"
        f"🚜 Máquina:     {datos.get('maquina_cod','—')}\n"
        f"💧 Diámetro:    {datos.get('diametro','—')}\n"
        f"{'─'*30}\n\n"
        f"¿Confirmas el registro? (*sí* / *no*)\n"
    )

def _obtener_cat_id() -> int:
    row = ejecutar(
        "SELECT id FROM cat_categorias WHERE codigo='OPE'",
        fetchone=True
    )
    return row[0] if row else 1

def _sondaje_activo_en_maquina_mat(maquina_id: int) -> dict | None:
    """Retorna el sondaje EN_CURSO de una máquina (para matriculación)."""
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
