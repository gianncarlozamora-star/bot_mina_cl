"""
MÓDULO BATCH GEÓLOGO
El geólogo registra el número de batch generado en Fusion
para hacer seguimiento y vincularlo con muestreo SGS.

Flujo:
  numero_batch → verificar duplicado →
  sondaje_batch → [segundo sondaje opcional] →
  cant_muestras (pre-cargado de muestreo o manual) →
  fecha_envio → destino (LOCAL/LIMA) → confirmacion_batch

Tabla que escribe:
  - laboratorio_certimin (batch cabecera, incluye campo destino)
  - batch_sondajes       (vinculación 1..2 sondajes)
"""
from db.sesiones import actualizar_sesion, cerrar_sesion
from db.sondajes import buscar_sondaje
from db.conexion import ejecutar
from config import fecha_hora_str, hora_peru

FLUJO = "BATCH_GEOLOGO"


# ══════════════════════════════════════════════════════════════
# INICIO
# ══════════════════════════════════════════════════════════════

def iniciar(usuario: dict, sesion_id: int) -> str:
    actualizar_sesion(sesion_id, "batch_numero", {})
    return (
        f"📦 *REGISTRAR BATCH*\n"
        f"📅 {fecha_hora_str()}\n\n"
        f"¿Cuál es el *número de batch* generado en Fusion?\n"
        f"Ejemplo: 7094\n"
    )


# ══════════════════════════════════════════════════════════════
# PROCESADOR PRINCIPAL
# ══════════════════════════════════════════════════════════════

def procesar(mensaje: str, usuario: dict, sesion: dict) -> str:
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    # ── Número de batch ───────────────────────────────────────
    if paso == "batch_numero":
        if not msg.isdigit():
            return "❓ El número de batch es numérico. Ejemplo: 7094"

        numero = msg.strip()

        row = ejecutar(
            "SELECT id, numero_batch FROM laboratorio_certimin WHERE numero_batch = %s",
            (numero,), fetchone=True
        )
        if row:
            cerrar_sesion(usuario["id"])
            return (
                f"⚠️ El batch *{numero}* ya está registrado en el sistema.\n"
                f"Si necesitas vincularlo a otro sondaje, contacta al administrador.\n"
            )

        datos["numero_batch"] = numero
        actualizar_sesion(sid, "batch_sondaje1", datos)
        return (
            f"✅ Batch: *{numero}*\n\n"
            f"¿*Código del sondaje* principal de este batch?\n"
            f"Ejemplo: 8422, PECLD08422\n"
        )

    # ── Sondaje 1 ─────────────────────────────────────────────
    elif paso == "batch_sondaje1":
        sondaje = buscar_sondaje(msg)
        if not sondaje:
            return f"❌ No encontré *{msg}*. Verifica el código."

        bhid = sondaje["bhid"]
        muestreo = _muestreo_del_sondaje(bhid)
        datos["sondaje1_id"]   = sondaje.get("id") or _obtener_id(bhid)
        datos["sondaje1_bhid"] = bhid
        datos["sondajes"]      = [{"id": datos["sondaje1_id"], "bhid": bhid}]

        if muestreo:
            datos["cant_muestras_auto"] = muestreo["total"]
            datos["cant_muestras"]      = muestreo["total"]
            aviso = (
                f"✅ Sondaje: *{bhid}*\n"
                f"🧪 Muestreo registrado: *{muestreo['total']}* muestras "
                f"({muestreo['desde']:.1f}→{muestreo['hasta']:.1f}m, "
                f"{muestreo['fecha']})\n"
            )
        else:
            datos["cant_muestras_auto"] = None
            aviso = (
                f"✅ Sondaje: *{bhid}*\n"
                f"⚠️ Sin muestreo SGS registrado aún.\n"
            )

        actualizar_sesion(sid, "batch_sondaje2", datos)
        return (
            aviso +
            f"\n¿Hay un *segundo sondaje* en este batch?\n"
            f"Escribe el código o *no* para continuar.\n"
        )

    # ── Sondaje 2 (opcional) ──────────────────────────────────
    elif paso == "batch_sondaje2":
        if msg.lower() in ("no", "n", "ninguno"):
            datos["sondaje2_id"]   = None
            datos["sondaje2_bhid"] = None
            actualizar_sesion(sid, "batch_cant_muestras", datos)
            return _preguntar_cant_muestras(datos)

        sondaje = buscar_sondaje(msg)
        if not sondaje:
            return f"❌ No encontré *{msg}*. Verifica el código o escribe *no*."

        bhid2 = sondaje["bhid"]
        if bhid2 == datos["sondaje1_bhid"]:
            return "❓ Es el mismo sondaje que el primero. Escribe otro o *no*."

        muestreo2 = _muestreo_del_sondaje(bhid2)
        datos["sondaje2_id"]   = sondaje.get("id") or _obtener_id(bhid2)
        datos["sondaje2_bhid"] = bhid2
        datos["sondajes"].append({"id": datos["sondaje2_id"], "bhid": bhid2})

        if muestreo2 and datos.get("cant_muestras_auto"):
            total_auto = datos["cant_muestras_auto"] + muestreo2["total"]
            datos["cant_muestras_auto"] = total_auto
            datos["cant_muestras"]      = total_auto
            aviso2 = (
                f"✅ Segundo sondaje: *{bhid2}*\n"
                f"🧪 Muestreo: *{muestreo2['total']}* muestras\n"
                f"📊 Total combinado: *{total_auto}* muestras\n"
            )
        else:
            datos["cant_muestras_auto"] = None
            aviso2 = f"✅ Segundo sondaje: *{bhid2}*\n"

        actualizar_sesion(sid, "batch_cant_muestras", datos)
        return aviso2 + "\n" + _preguntar_cant_muestras(datos)

    # ── Cantidad de muestras ──────────────────────────────────
    elif paso == "batch_cant_muestras":
        if msg.lower() in ("ok", "confirma", "si", "sí", "yes") \
                and datos.get("cant_muestras_auto"):
            pass  # ya está en datos["cant_muestras"]
        else:
            try:
                n = int(msg.strip())
                if n <= 0:
                    raise ValueError
                datos["cant_muestras"] = n
            except ValueError:
                return "❓ Número entero positivo. Ejemplo: 54"

        actualizar_sesion(sid, "batch_fecha", datos)
        return (
            f"✅ Muestras: *{datos['cant_muestras']}*\n\n"
            f"¿*Fecha de envío* del batch a Certimin?\n"
            f"  *hoy* — Hoy\n"
            f"  DD/MM — Fecha específica\n"
        )

    # ── Fecha de envío ────────────────────────────────────────
    elif paso == "batch_fecha":
        fecha = _parsear_fecha(msg)
        if not fecha:
            return "❓ Formato: *hoy* o DD/MM (ej: 09/05)."
        datos["fecha_envio"] = fecha
        # ── NUEVO: preguntar destino ──────────────────────────
        actualizar_sesion(sid, "batch_destino", datos)
        return (
            f"✅ Fecha: *{_fmt_fecha(fecha)}*\n\n"
            f"¿A qué laboratorio Certimin se envía este batch?\n"
            f"  *1* — 🏭 Certimin *Local* (Ica ~24h)\n"
            f"  *2* — ✈️  Certimin *Lima* (demora varios días)\n"
        )

    # ── Destino ───────────────────────────────────────────────
    elif paso == "batch_destino":
        if msg in ("1", "local", "ica"):
            datos["destino"] = "LOCAL"
        elif msg in ("2", "lima"):
            datos["destino"] = "LIMA"
        else:
            return (
                f"❓ Responde *1* (Local) o *2* (Lima).\n"
            )
        actualizar_sesion(sid, "batch_confirmacion", datos)
        return _resumen_batch(datos)

    # ── Confirmación ──────────────────────────────────────────
    elif paso == "batch_confirmacion":
        if msg.lower() in ("no", "cancelar", "n"):
            cerrar_sesion(usuario["id"])
            return "❌ Batch cancelado."
        if msg.lower() not in ("sí", "si", "ok", "confirma", "yes"):
            return "¿Confirmas? *sí* o *no*."

        try:
            row = ejecutar(
                """INSERT INTO laboratorio_certimin
                       (numero_batch, cant_muestras, fecha_envio,
                        creado_por, fuente, destino)
                   VALUES (%s, %s, %s, %s, 'BOT', %s)
                   RETURNING id""",
                (
                    datos["numero_batch"],
                    datos["cant_muestras"],
                    datos["fecha_envio"],
                    usuario["id"],
                    datos.get("destino", "LOCAL"),
                ),
                fetchone=True
            )
            batch_id = row[0] if row else None

            if not batch_id:
                return "⚠️ Error creando el batch. Intenta de nuevo."

            for s in datos.get("sondajes", []):
                ejecutar(
                    """INSERT INTO batch_sondajes
                           (batch_id, sondaje_id, numero_envio)
                       VALUES (%s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (batch_id, s["id"], datos["numero_batch"])
                )

            for s in datos.get("sondajes", []):
                ejecutar(
                    """UPDATE sondajes SET estado_laboratorio = 'EN_PROCESO'
                       WHERE id = %s AND estado_laboratorio = 'PENDIENTE'""",
                    (s["id"],)
                )

            cerrar_sesion(usuario["id"])

            sondajes_str = " | ".join(s["bhid"] for s in datos.get("sondajes", []))
            destino_label = "🏭 Local (Ica)" if datos.get("destino") == "LOCAL" else "✈️ Lima"
            return (
                f"✅ *Batch registrado*\n"
                f"{'─'*28}\n"
                f"📦 Batch:    *{datos['numero_batch']}*\n"
                f"🔖 Sondaje:  {sondajes_str}\n"
                f"🧪 Muestras: {datos['cant_muestras']}\n"
                f"📅 Envío:    {_fmt_fecha(datos['fecha_envio'])}\n"
                f"📍 Destino:  {destino_label}\n"
                f"👤 {usuario['nombre']}\n"
                f"{'─'*28}\n"
                f"📌 Certimin confirmará la recepción cuando llegue."
            )

        except Exception as e:
            print(f"[BATCH_GEOLOGO] Error: {e}")
            return "⚠️ Error al guardar. Intenta de nuevo."

    return "❓ Escribe *hola* para reiniciar."


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _muestreo_del_sondaje(bhid: str) -> dict | None:
    row = ejecutar(
        """SELECT e.cant_muestras, e.desde_m, e.hasta_m, e.fecha
           FROM etapas_sgs e
           JOIN sondajes s ON e.sondaje_id = s.id
           WHERE s.bhid = %s AND e.etapa = 'MUESTREO'
             AND COALESCE(e.estado, 'ACTIVO') != 'ANULADO'
           ORDER BY e.id DESC LIMIT 1""",
        (bhid,), fetchone=True
    )
    if not row:
        return None
    try:
        fecha_str = row[3].strftime("%d/%m") if row[3] else "—"
    except:
        fecha_str = str(row[3])[:5]
    return {
        "total":  int(row[0] or 0),
        "desde":  float(row[1] or 0),
        "hasta":  float(row[2] or 0),
        "fecha":  fecha_str,
    }


def _preguntar_cant_muestras(datos: dict) -> str:
    cant_auto = datos.get("cant_muestras_auto")
    if cant_auto:
        return (
            f"¿*Cantidad de muestras* del batch?\n"
            f"SGS registró *{cant_auto}* muestras — escribe *ok* para usar ese valor\n"
            f"o escribe el número correcto si difiere.\n"
        )
    return (
        f"¿*Cantidad total de muestras* en el batch?\n"
        f"Ejemplo: 54\n"
    )


def _parsear_fecha(msg: str) -> str | None:
    if msg.lower() in ("hoy", "today"):
        return hora_peru().strftime("%Y-%m-%d")
    try:
        from datetime import datetime
        parsed = datetime.strptime(msg.replace("-", "/"), "%d/%m")
        return parsed.replace(year=hora_peru().year).strftime("%Y-%m-%d")
    except:
        return None


def _fmt_fecha(fecha: str) -> str:
    try:
        from datetime import datetime
        return datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return fecha


def _obtener_id(bhid: str) -> int | None:
    row = ejecutar("SELECT id FROM sondajes WHERE bhid=%s", (bhid,), fetchone=True)
    return row[0] if row else None


def _resumen_batch(datos: dict) -> str:
    sondajes_str = "\n".join(
        f"  🔖 {s['bhid']}" for s in datos.get("sondajes", [])
    )
    destino_label = "🏭 Local (Ica)" if datos.get("destino") == "LOCAL" else "✈️ Lima"
    return (
        f"📋 *RESUMEN BATCH*\n{'─'*28}\n"
        f"📦 Número:   *{datos.get('numero_batch','—')}*\n"
        f"{'─'*28}\n"
        f"{sondajes_str}\n"
        f"{'─'*28}\n"
        f"🧪 Muestras: *{datos.get('cant_muestras','—')}*\n"
        f"📅 Envío:    {_fmt_fecha(datos.get('fecha_envio',''))}\n"
        f"📍 Destino:  {destino_label}\n"
        f"{'─'*28}\n"
        f"¿Confirmas? (*sí* / *no*)\n"
    )
