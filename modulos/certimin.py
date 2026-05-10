"""
FLUJO CERTIMIN — Confirmación de batch enviado/analizado
Para rol CERTIMIN.

Flujo:
  iniciar → muestra lista de batches pendientes automáticamente
  → usuario escribe número de batch (de la lista o manual)
  → Paso 1: confirmar RECEPCIÓN
  → Paso 2: confirmar RESULTADOS (requiere recepción previa)

Ambos pasos son independientes (pueden hacerse en días distintos).
"""
from db.sesiones import actualizar_sesion, cerrar_sesion
from db.conexion import ejecutar
from config import fecha_hora_str, hora_peru

FLUJO = "CERTIMIN"


# ══════════════════════════════════════════════════════════════
# INICIO — muestra batches pendientes automáticamente
# ══════════════════════════════════════════════════════════════

def iniciar(usuario: dict, sesion_id: int) -> str:
    actualizar_sesion(sesion_id, "numero_batch", {})
    lista = _lista_batches_pendientes()
    return (
        f"🧪 *REPORTE CERTIMIN*\n"
        f"📅 {fecha_hora_str()}\n"
        f"{'─'*28}\n"
        f"{lista}\n"
        f"{'─'*28}\n"
        f"Escribe el *número de batch* a confirmar:\n"
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
    if paso == "numero_batch":
        datos["numero_batch"] = msg.upper().strip()

        row = ejecutar(
            """SELECT id, numero_batch, cant_muestras, fecha_envio,
                      confirmado_recepcion, resultados_disponibles,
                      COALESCE(destino, 'LOCAL') as destino
               FROM laboratorio_certimin WHERE numero_batch = %s""",
            (datos["numero_batch"],), fetchone=True
        )

        if row:
            datos["batch_id"]      = row[0]
            datos["cant_muestras"] = row[2]
            datos["fecha_envio"]   = str(row[3])
            datos["destino"]       = row[6]
            tiene_recepcion  = row[4]
            tiene_resultados = row[5]

            # Ambos ya confirmados
            if tiene_recepcion and tiene_resultados:
                cerrar_sesion(usuario["id"])
                return (
                    f"ℹ️ Batch *{datos['numero_batch']}* ya tiene todo confirmado:\n"
                    f"  ✅ Recepción\n"
                    f"  ✅ Resultados analizados\n\n"
                    f"Si hay un error contacta al administrador."
                )

            actualizar_sesion(sid, "confirmacion_tipo", datos)
            return _menu_confirmacion(datos, tiene_recepcion, tiene_resultados)

        else:
            # Batch no existe — el geólogo debe registrarlo primero
            cerrar_sesion(usuario["id"])
            return (
                f"⚠️ Batch *{datos['numero_batch']}* no está registrado.\n\n"
                f"El geólogo debe registrarlo primero desde su menú.\n"
                f"Escribe *hola* para reiniciar."
            )

    # ── Tipo de confirmación ──────────────────────────────────
    elif paso == "confirmacion_tipo":
        # Releer estado actual desde BD
        row = ejecutar(
            "SELECT confirmado_recepcion, resultados_disponibles "
            "FROM laboratorio_certimin WHERE id = %s",
            (datos["batch_id"],), fetchone=True
        )
        tiene_recepcion  = row[0] if row else False
        tiene_resultados = row[1] if row else False

        if msg in ("1", "recepcion", "recepción"):
            if tiene_recepcion:
                return (
                    f"ℹ️ La recepción del batch *{datos['numero_batch']}* "
                    f"ya fue confirmada.\n\n"
                    + _menu_confirmacion(datos, tiene_recepcion, tiene_resultados)
                )
            datos["tipo_confirmacion"] = "RECEPCION"
            actualizar_sesion(sid, "confirmar", datos)
            return (
                f"📦 *Confirmar RECEPCIÓN*\n"
                f"🧪 Batch:    *{datos['numero_batch']}*\n"
                f"📊 Muestras: {datos.get('cant_muestras', '—')}\n"
                f"📍 Destino:  {_destino_label(datos.get('destino','LOCAL'))}\n\n"
                f"¿Confirmas? (*sí* / *no*)\n"
            )

        elif msg in ("2", "resultados"):
            if not tiene_recepcion:
                return (
                    f"⚠️ Primero debes confirmar la *recepción* del batch.\n\n"
                    + _menu_confirmacion(datos, tiene_recepcion, tiene_resultados)
                )
            if tiene_resultados:
                return (
                    f"ℹ️ Los resultados del batch *{datos['numero_batch']}* "
                    f"ya fueron confirmados.\n\n"
                    f"Si hay un error contacta al administrador."
                )
            datos["tipo_confirmacion"] = "RESULTADOS"
            actualizar_sesion(sid, "nombre_archivo", datos)
            return (
                f"📊 *Confirmar RESULTADOS ANALIZADOS*\n"
                f"🧪 Batch: *{datos['numero_batch']}*\n\n"
                f"¿Nombre del archivo Excel con resultados?\n"
                f"Ejemplo: Resultados_7094_Certimin.xlsx\n"
                f"O escribe *omitir* para saltar.\n"
            )

        else:
            return (
                f"❓ Responde *1* o *2*.\n\n"
                + _menu_confirmacion(datos, tiene_recepcion, tiene_resultados)
            )

    # ── Nombre de archivo de resultados ───────────────────────
    elif paso == "nombre_archivo":
        datos["archivo_resultados"] = (
            None if msg.lower() in ("no sé", "no se", "omitir", "-")
            else msg.strip()
        )
        actualizar_sesion(sid, "confirmar", datos)
        archivo_label = datos.get("archivo_resultados") or "_(sin archivo)_"
        return (
            f"📊 *Confirmar RESULTADOS ANALIZADOS*\n"
            f"🧪 Batch: *{datos['numero_batch']}*\n"
            f"📄 Archivo: {archivo_label}\n\n"
            f"¿Confirmas que las leyes ya están disponibles? (*sí* / *no*)\n"
        )

    # ── Confirmación final ────────────────────────────────────
    elif paso == "confirmar":
        if msg.lower() in ("no", "cancelar"):
            cerrar_sesion(usuario["id"])
            return "❌ Confirmación cancelada."
        if msg.lower() not in ("sí", "si", "ok", "yes", "s"):
            return "¿Confirmas? *sí* o *no*."

        try:
            tipo     = datos.get("tipo_confirmacion")
            batch_id = datos.get("batch_id")
            hoy      = hora_peru().strftime("%Y-%m-%d")

            if tipo == "RECEPCION":
                ejecutar(
                    """UPDATE laboratorio_certimin
                       SET confirmado_recepcion = TRUE,
                           fecha_confirmacion   = %s,
                           confirmado_por       = %s,
                           actualizado_en       = NOW()
                       WHERE id = %s""",
                    (hoy, usuario["id"], batch_id)
                )
                cerrar_sesion(usuario["id"])
                return (
                    f"✅ *Recepción confirmada*\n"
                    f"🧪 Batch:    *{datos['numero_batch']}*\n"
                    f"📦 Muestras: {datos.get('cant_muestras', '—')}\n"
                    f"📍 Destino:  {_destino_label(datos.get('destino','LOCAL'))}\n"
                    f"📅 {fecha_hora_str()}\n"
                    f"👤 {usuario['nombre']}\n\n"
                    f"_(Cuando tengas los resultados, reporta con el mismo número de batch)_"
                )

            else:  # RESULTADOS
                ejecutar(
                    """UPDATE laboratorio_certimin
                       SET resultados_disponibles = TRUE,
                           fecha_resultados       = %s,
                           archivo_resultados     = %s,
                           actualizado_en         = NOW()
                       WHERE id = %s""",
                    (hoy, datos.get("archivo_resultados"), batch_id)
                )
                ejecutar(
                    """UPDATE sondajes s
                       SET estado_laboratorio = 'COMPLETADO'
                       FROM batch_sondajes bs
                       WHERE bs.batch_id = %s AND bs.sondaje_id = s.id""",
                    (batch_id,)
                )
                row_count = ejecutar(
                    "SELECT COUNT(*) FROM batch_sondajes WHERE batch_id = %s",
                    (batch_id,), fetchone=True
                )
                n_sondajes = row_count[0] if row_count else 0

                cerrar_sesion(usuario["id"])
                return (
                    f"✅ *Resultados confirmados*\n"
                    f"🧪 Batch:    *{datos['numero_batch']}*\n"
                    f"📊 Leyes disponibles en sistema\n"
                    f"🔖 Sondajes actualizados: {n_sondajes}\n"
                    f"📄 Archivo: {datos.get('archivo_resultados') or '—'}\n"
                    f"📅 {fecha_hora_str()}\n"
                    f"👤 {usuario['nombre']}\n"
                )

        except Exception as e:
            print(f"[CERTIMIN] Error: {e}")
            return "⚠️ Error al confirmar. Intenta de nuevo."

    return "❓ Escribe *hola* para reiniciar."


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _lista_batches_pendientes() -> str:
    """
    Muestra batches pendientes separados por estado y destino.
    Pendiente recepción → aún no llegaron a Certimin.
    Pendiente resultados → llegaron pero aún no analizaron.
    """
    rows_rec = ejecutar(
        """SELECT numero_batch, cant_muestras, fecha_envio,
                  COALESCE(destino, 'LOCAL') as destino
           FROM laboratorio_certimin
           WHERE confirmado_recepcion = FALSE
           ORDER BY fecha_envio DESC
           LIMIT 8""",
        fetchall=True
    ) or []

    rows_res = ejecutar(
        """SELECT numero_batch, cant_muestras, fecha_confirmacion,
                  COALESCE(destino, 'LOCAL') as destino
           FROM laboratorio_certimin
           WHERE confirmado_recepcion = TRUE
             AND COALESCE(resultados_disponibles, FALSE) = FALSE
           ORDER BY fecha_confirmacion DESC
           LIMIT 8""",
        fetchall=True
    ) or []

    lineas = []

    if rows_rec:
        lineas.append("📦 *Pendientes de RECEPCIÓN:*")
        for r in rows_rec:
            icono = "🏭" if r[3] == "LOCAL" else "✈️"
            lineas.append(
                f"  • *{r[0]}* — {r[1] or '?'} muestras "
                f"| {icono} {r[3]} | {_fmt_fecha(str(r[2]))}"
            )
    else:
        lineas.append("📦 *Pendientes de RECEPCIÓN:* ninguno ✅")

    lineas.append("")

    if rows_res:
        lineas.append("📊 *Pendientes de RESULTADOS:*")
        for r in rows_res:
            icono = "🏭" if r[3] == "LOCAL" else "✈️"
            lineas.append(
                f"  • *{r[0]}* — {r[1] or '?'} muestras "
                f"| {icono} {r[3]} | recibido {_fmt_fecha(str(r[2]))}"
            )
    else:
        lineas.append("📊 *Pendientes de RESULTADOS:* ninguno ✅")

    return "\n".join(lineas)


def _menu_confirmacion(datos: dict,
                        tiene_recepcion: bool,
                        tiene_resultados: bool) -> str:
    rec_label = "✅ Ya confirmada"  if tiene_recepcion  else "⏳ Pendiente"
    res_label = "✅ Ya confirmados" if tiene_resultados else "⏳ Pendiente"

    return (
        f"📋 Batch *{datos['numero_batch']}*\n"
        f"   Muestras: {datos.get('cant_muestras', '—')} | "
        f"Enviado: {_fmt_fecha(datos.get('fecha_envio',''))} | "
        f"{_destino_label(datos.get('destino','LOCAL'))}\n\n"
        f"¿Qué deseas confirmar?\n"
        f"  *1* — 📦 Recepción       {rec_label}\n"
        f"  *2* — 📊 Resultados      {res_label}\n"
    )


def _destino_label(destino: str) -> str:
    return "🏭 Local (Ica)" if destino == "LOCAL" else "✈️ Lima"


def _fmt_fecha(fecha: str) -> str:
    try:
        from datetime import datetime
        return datetime.strptime(fecha[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return str(fecha)[:10] if fecha else "—"
