"""
FLUJO CERTIMIN — Confirmación de batch enviado/analizado
Para rol CERTIMIN.
"""
from db.sesiones import actualizar_sesion, cerrar_sesion
from db.conexion import ejecutar
from config import fecha_hora_str, hora_peru

FLUJO = "CERTIMIN"

def iniciar(usuario: dict, sesion_id: int) -> str:
    actualizar_sesion(sesion_id, "numero_batch", {})
    return (
        f"🧪 *REPORTE CERTIMIN*\n"
        f"📅 {fecha_hora_str()}\n\n"
        f"¿Cuál es el *número de batch* que confirmas?\n"
        f"Ejemplo: 7094, 7095\n"
    )

def procesar(mensaje: str, usuario: dict, sesion: dict) -> str:
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    # ── Número de batch ───────────────────────────────────────
    if paso == "numero_batch":
        datos["numero_batch"] = msg.upper().strip()

        # Verificar si el batch existe en BD
        row = ejecutar(
            """SELECT id, numero_batch, cant_muestras, fecha_envio,
                      confirmado_recepcion
               FROM laboratorio_certimin WHERE numero_batch = %s""",
            (datos["numero_batch"],), fetchone=True
        )
        if row:
            datos["batch_id"]   = row[0]
            datos["cant_muestras"] = row[2]
            datos["fecha_envio"]   = str(row[3])
            ya_confirmado = row[4]
            if ya_confirmado:
                cerrar_sesion(usuario["id"])
                return (
                    f"ℹ️ El batch *{datos['numero_batch']}* ya fue confirmado.\n"
                    f"Si hay un error, contacta al administrador."
                )
            actualizar_sesion(sid, "confirmacion_tipo", datos)
            return (
                f"✅ Batch encontrado: *{datos['numero_batch']}*\n"
                f"   Muestras: {row[2] or '—'} | Enviado: {row[3] or '—'}\n\n"
                f"¿Qué quieres confirmar?\n"
                f"  *1* — Recepción del batch (llegó a Certimin)\n"
                f"  *2* — Resultados disponibles (leyes analizadas)\n"
            )
        else:
            # Batch no existe, crear nuevo
            actualizar_sesion(sid, "batch_nuevo_muestras", datos)
            return (
                f"⚠️ Batch *{datos['numero_batch']}* no está registrado.\n\n"
                f"¿Cuántas muestras tiene el batch?\n"
            )

    # ── Batch nuevo: cantidad de muestras ─────────────────────
    elif paso == "batch_nuevo_muestras":
        try:
            datos["cant_muestras"] = int(msg)
        except:
            return "❓ Ingresa un número entero. Ejemplo: 42"
        actualizar_sesion(sid, "batch_nuevo_fecha", datos)
        return (
            f"✅ Muestras: *{datos['cant_muestras']}*\n\n"
            f"¿*Fecha de envío* desde SGS? (DD/MM o *hoy*)\n"
        )

    elif paso == "batch_nuevo_fecha":
        if msg.lower() == "hoy":
            datos["fecha_envio"] = hora_peru().strftime("%Y-%m-%d")
        else:
            try:
                from datetime import datetime
                parsed = datetime.strptime(msg.replace("-","/"), "%d/%m")
                datos["fecha_envio"] = parsed.replace(
                    year=hora_peru().year).strftime("%Y-%m-%d")
            except:
                return "❓ Formato: DD/MM o *hoy*."

        # Crear el batch en BD
        row = ejecutar(
            """INSERT INTO laboratorio_certimin
                   (numero_batch, cant_muestras, fecha_envio)
               VALUES (%s, %s, %s) RETURNING id""",
            (datos["numero_batch"], datos["cant_muestras"], datos["fecha_envio"]),
            fetchone=True
        )
        datos["batch_id"] = row[0] if row else None
        actualizar_sesion(sid, "confirmacion_tipo", datos)
        return (
            f"✅ Batch *{datos['numero_batch']}* creado.\n\n"
            f"¿Qué quieres confirmar?\n"
            f"  *1* — Recepción del batch\n"
            f"  *2* — Resultados disponibles\n"
        )

    # ── Tipo de confirmación ──────────────────────────────────
    elif paso == "confirmacion_tipo":
        if msg == "1":
            datos["tipo_confirmacion"] = "RECEPCION"
            actualizar_sesion(sid, "confirmar", datos)
            return (
                f"📦 Confirmando *recepción* del batch *{datos['numero_batch']}*\n\n"
                f"¿Confirmas? (*sí* / *no*)\n"
            )
        elif msg == "2":
            datos["tipo_confirmacion"] = "RESULTADOS"
            actualizar_sesion(sid, "nombre_archivo", datos)
            return (
                f"📊 Confirmando *resultados disponibles* del batch *{datos['numero_batch']}*\n\n"
                f"¿Nombre del archivo Excel enviado por correo?\n"
                f"Ejemplo: Resultados_7094_Certimin.xlsx\n"
                f"O escribe *no sé* para omitir.\n"
            )
        else:
            return "❓ Responde *1* o *2*."

    # ── Nombre de archivo de resultados ───────────────────────
    elif paso == "nombre_archivo":
        datos["archivo_resultados"] = None if msg.lower() in ("no sé","no se","omitir") else msg.strip()
        actualizar_sesion(sid, "confirmar", datos)
        return (
            f"✅ Archivo: *{datos.get('archivo_resultados','—')}*\n\n"
            f"¿Confirmas que los resultados del batch "
            f"*{datos['numero_batch']}* ya están disponibles? (*sí* / *no*)\n"
        )

    # ── Confirmación final ────────────────────────────────────
    elif paso == "confirmar":
        if msg.lower() in ("no", "cancelar"):
            cerrar_sesion(usuario["id"])
            return "❌ Confirmación cancelada."
        if msg.lower() not in ("sí", "si", "ok", "yes"):
            return "¿Confirmas? *sí* o *no*."

        try:
            tipo = datos.get("tipo_confirmacion")
            batch_id = datos.get("batch_id")
            hoy = hora_peru().strftime("%Y-%m-%d")

            if tipo == "RECEPCION":
                ejecutar(
                    """UPDATE laboratorio_certimin
                       SET confirmado_recepcion=TRUE, fecha_confirmacion=%s,
                           confirmado_por=%s, actualizado_en=NOW()
                       WHERE id=%s""",
                    (hoy, usuario["id"], batch_id)
                )
                msg_ok = (
                    f"✅ *Recepción confirmada*\n"
                    f"🧪 Batch: *{datos['numero_batch']}*\n"
                    f"📅 {fecha_hora_str()}\n"
                    f"👤 {usuario['nombre']}\n"
                )
            else:  # RESULTADOS
                ejecutar(
                    """UPDATE laboratorio_certimin
                       SET resultados_disponibles=TRUE, fecha_resultados=%s,
                           archivo_resultados=%s, actualizado_en=NOW()
                       WHERE id=%s""",
                    (hoy, datos.get("archivo_resultados"), batch_id)
                )
                # Actualizar estado laboratorio de sondajes vinculados
                ejecutar(
                    """UPDATE sondajes s
                       SET estado_laboratorio = 'COMPLETADO'
                       FROM batch_sondajes bs
                       WHERE bs.batch_id = %s AND bs.sondaje_id = s.id""",
                    (batch_id,)
                )
                msg_ok = (
                    f"✅ *Resultados confirmados*\n"
                    f"🧪 Batch: *{datos['numero_batch']}*\n"
                    f"📊 Leyes ya disponibles en sistema.\n"
                    f"📅 {fecha_hora_str()}\n"
                    f"👤 {usuario['nombre']}\n"
                )

            cerrar_sesion(usuario["id"])
            return msg_ok

        except Exception as e:
            print(f"[CERTIMIN] Error: {e}")
            return "⚠️ Error al confirmar. Intenta de nuevo."

    return "❓ Paso no reconocido. Escribe *hola* para reiniciar."
