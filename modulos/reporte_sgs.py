"""
MÓDULO REPORTE CONSOLIDADO SGS
Genera el reporte diario SGS para envío al área de geología.

Flujo:
  geólogo escribe "reporte sgs" →
  bot genera preview del día →
  confirma → texto formateado listo para copiar y pegar

Protocolo QAQC Cerro Lindo:
  % inserción = control / (control + ordinarias) × 100
  🚨 < 12% — por debajo del protocolo
  ✅ 12-14% — dentro del protocolo
  ⚠️ > 14% — por encima del protocolo
"""
from db.sesiones import actualizar_sesion, cerrar_sesion
from db.conexion import ejecutar
from config import fecha_hora_str, hora_peru

FLUJO = "REPORTE_SGS"

QAQC_MIN = 12.0
QAQC_MAX = 14.0


# ══════════════════════════════════════════════════════════════
# INICIO
# ══════════════════════════════════════════════════════════════

def iniciar(usuario: dict, sesion_id: int) -> str:
    """Genera preview del día y pide confirmación."""
    fecha_hoy = hora_peru().strftime("%Y-%m-%d")
    datos     = {"fecha": fecha_hoy}

    preview = _generar_reporte(fecha_hoy)
    if not preview["tiene_datos"]:
        cerrar_sesion(usuario["id"])
        return (
            f"📭 No hay registros SGS del día de hoy "
            f"*{hora_peru().strftime('%d/%m/%Y')}*.\n\n"
            f"Escribe *hola* para volver al menú."
        )

    actualizar_sesion(sesion_id, "confirmar_reporte", datos)
    return (
        f"{preview['texto']}\n\n"
        f"{'─'*30}\n"
        f"¿Confirmas y generas el reporte para enviar?\n"
        f"*sí* — Generar | *no* — Cancelar\n"
    )


# ══════════════════════════════════════════════════════════════
# PROCESADOR
# ══════════════════════════════════════════════════════════════

def procesar(mensaje: str, usuario: dict, sesion: dict) -> str:
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip().lower()

    if paso == "confirmar_reporte":
        if msg in ("no", "cancelar", "n"):
            cerrar_sesion(usuario["id"])
            return "❌ Reporte cancelado."
        if msg not in ("sí", "si", "ok", "confirma", "yes"):
            return "¿Confirmas? *sí* o *no*."

        fecha   = datos.get("fecha", hora_peru().strftime("%Y-%m-%d"))
        preview = _generar_reporte(fecha)
        cerrar_sesion(usuario["id"])
        return (
            f"{preview['texto']}\n\n"
            f"{'─'*30}\n"
            f"✅ *Reporte generado* — copia y envía al grupo.\n"
            f"📅 {fecha_hora_str()} | 👤 {usuario['nombre']}\n"
        )

    return "❓ Escribe *hola* para reiniciar."


# ══════════════════════════════════════════════════════════════
# GENERADOR DEL REPORTE
# ══════════════════════════════════════════════════════════════

def _generar_reporte(fecha: str) -> dict:
    """
    Genera el texto completo del reporte SGS para una fecha.
    Retorna dict con 'texto' y 'tiene_datos'.
    """
    try:
        fecha_fmt = _fmt_fecha(fecha)
        lineas    = [f"*REPORTE SGS — {fecha_fmt}*"]

        tiene_datos = False

        # ── 1-3. Etapas de metraje (Logueo, RQD, Fotografía) ─
        etapas_metraje = [
            ("LOGUEO",     "1. LOGUEO GEOLÓGICO"),
            ("RQD",        "2. RQD"),
            ("FOTOGRAFIA", "3. FOTOGRAFÍA"),
        ]
        for etapa, titulo in etapas_metraje:
            rows = _registros_etapa_metraje(etapa, fecha)
            if rows:
                tiene_datos = True
                lineas.append(f"\n*{titulo}*")
                for r in rows:
                    bhid, desde, hasta, est_perf, est_etapa = r
                    estado_str = _estado_str(est_perf, est_etapa)
                    lineas.append(
                        f"- {bhid} = {float(desde or 0):.2f} → "
                        f"{float(hasta or 0):.2f} {estado_str}"
                    )

        # ── 4. Densidad ───────────────────────────────────────
        rows_dens = _registros_densidad(fecha)
        if rows_dens:
            tiene_datos = True
            lineas.append("\n*4. DENSIDAD*")
            for r in rows_dens:
                bhid, cant, est_perf, est_etapa = r
                estado_str = _estado_str(est_perf, est_etapa)
                lineas.append(
                    f"- {bhid} = {int(cant or 0)} muestras {estado_str}"
                )

        # ── 5. Muestreo ───────────────────────────────────────
        rows_mues = _registros_muestreo(fecha)
        if rows_mues:
            tiene_datos = True
            lineas.append("\n*5. MUESTREO*")
            for r in rows_mues:
                bhid, cant, est_perf, est_etapa = r
                estado_str = _estado_str(est_perf, est_etapa)
                lineas.append(
                    f"- {bhid} = {int(cant or 0)} muestras {estado_str}"
                )

        if not tiene_datos:
            return {"texto": "", "tiene_datos": False}

        # ── QAQC ──────────────────────────────────────────────
        qaqc = _calcular_qaqc(fecha)
        if qaqc["total"] > 0:
            pct       = qaqc["pct_insercion"]
            pct_icon  = _icono_qaqc(pct)
            pct_str   = f"{pct:.1f}%"
            rango_msg = (
                "✅ dentro del protocolo (12-14%)"
                if QAQC_MIN <= pct <= QAQC_MAX
                else (
                    f"🚨 por debajo del protocolo (mín {QAQC_MIN}%)"
                    if pct < QAQC_MIN
                    else f"⚠️ por encima del protocolo (máx {QAQC_MAX}%)"
                )
            )
            lineas.append(f"\n{'━'*25}")
            lineas.append("*📊 CONTROL QAQC*")
            lineas.append(f"Total muestras hoy:    {qaqc['total']}")
            lineas.append(
                f"Ordinarias:            "
                f"{qaqc['ordinarias']} "
                f"({qaqc['pct_ordinarias']:.1f}%)"
            )
            lineas.append(
                f"Control (inserción):   "
                f"{qaqc['control']} ({pct_str}) {pct_icon}"
            )
            lineas.append(f"  _{rango_msg}_")
            if qaqc["std_alta"]:
                lineas.append(f"  STD alta ley:    {qaqc['std_alta']}")
            if qaqc["std_baja"]:
                lineas.append(f"  STD baja ley:    {qaqc['std_baja']}")
            if qaqc["dup_grueso"]:
                lineas.append(f"  Dup. grueso:     {qaqc['dup_grueso']}")
            if qaqc["dup_fino"]:
                lineas.append(f"  Dup. fino:       {qaqc['dup_fino']}")
            if qaqc["dup_gemela"]:
                lineas.append(f"  Dup. gemela:     {qaqc['dup_gemela']}")
            if qaqc["blancos"]:
                lineas.append(f"  Blancos:         {qaqc['blancos']}")

        # ── Envío a laboratorio ───────────────────────────────
        batches_hoy    = _batches_del_dia(fecha)
        pendientes_env = _muestras_sin_batch()

        lineas.append(f"\n{'━'*25}")
        lineas.append("*📦 ENVÍO A LABORATORIO*")

        if batches_hoy:
            lineas.append("Enviados hoy:")
            total_env = 0
            for b in batches_hoy:
                bhids_str, cant, numero = b
                total_env += int(cant or 0)
                lineas.append(
                    f"- {bhids_str} = {int(cant or 0)} muestras "
                    f"(Batch {numero})"
                )
            lineas.append(f"Total enviado hoy: *{total_env} muestras*")
        else:
            lineas.append("Sin envíos registrados hoy.")

        if pendientes_env:
            lineas.append("\nPendientes de envío:")
            total_pend = 0
            for p in pendientes_env:
                bhid, cant = p
                total_pend += int(cant or 0)
                lineas.append(
                    f"- {bhid} = {int(cant or 0)} muestras ⏳"
                )
            lineas.append(f"Total pendiente: *{total_pend} muestras*")
        else:
            lineas.append("✅ Sin muestras pendientes de envío.")

        return {"texto": "\n".join(lineas), "tiene_datos": True}

    except Exception as e:
        print(f"[REPORTE_SGS] Error generando: {e}")
        return {"texto": "⚠️ Error generando el reporte.", "tiene_datos": True}


# ══════════════════════════════════════════════════════════════
# QUERIES
# ══════════════════════════════════════════════════════════════

def _registros_etapa_metraje(etapa: str, fecha: str) -> list:
    """Logueo, RQD, Fotografía — agrupa por sondaje sumando tramos."""
    return ejecutar(
        """SELECT s.bhid,
                  MIN(e.desde_m)          AS desde,
                  MAX(e.hasta_m)          AS hasta,
                  s.estado_perforacion,
                  MAX(s.estado_logueo)    FILTER (WHERE e.etapa='LOGUEO')
                      OVER (PARTITION BY s.bhid)
           FROM etapas_sgs e
           JOIN sondajes s ON e.sondaje_id = s.id
           WHERE e.etapa = %s
             AND e.fecha = %s
             AND COALESCE(e.estado, 'ACTIVO') != 'ANULADO'
           GROUP BY s.bhid, s.estado_perforacion,
                    s.estado_logueo, s.estado_rqd, s.estado_fotografia
           ORDER BY s.bhid""",
        (etapa, fecha), fetchall=True
    ) or []


def _registros_etapa_metraje(etapa: str, fecha: str) -> list:
    """Logueo, RQD, Fotografía — agrupa por sondaje."""
    col_estado = {
        "LOGUEO":     "s.estado_logueo",
        "RQD":        "s.estado_rqd",
        "FOTOGRAFIA": "s.estado_fotografia",
    }.get(etapa, "s.estado_logueo")

    return ejecutar(
        f"""SELECT s.bhid,
                  MIN(e.desde_m)   AS desde,
                  MAX(e.hasta_m)   AS hasta,
                  s.estado_perforacion,
                  {col_estado}     AS estado_etapa
           FROM etapas_sgs e
           JOIN sondajes s ON e.sondaje_id = s.id
           WHERE e.etapa = %s
             AND e.fecha  = %s
             AND COALESCE(e.estado, 'ACTIVO') != 'ANULADO'
           GROUP BY s.bhid, s.estado_perforacion, {col_estado}
           ORDER BY s.bhid""",
        (etapa, fecha), fetchall=True
    ) or []


def _registros_densidad(fecha: str) -> list:
    """Densidad — suma originales + std + dup por sondaje."""
    return ejecutar(
        """SELECT s.bhid,
                  SUM(e.originales + e.std_densidad + e.dup_densidad) AS cant,
                  s.estado_perforacion,
                  s.estado_densidad
           FROM etapas_sgs e
           JOIN sondajes s ON e.sondaje_id = s.id
           WHERE e.etapa = 'DENSIDAD'
             AND e.fecha  = %s
             AND COALESCE(e.estado, 'ACTIVO') != 'ANULADO'
           GROUP BY s.bhid, s.estado_perforacion, s.estado_densidad
           ORDER BY s.bhid""",
        (fecha,), fetchall=True
    ) or []


def _registros_muestreo(fecha: str) -> list:
    """Muestreo — suma cant_muestras por sondaje."""
    return ejecutar(
        """SELECT s.bhid,
                  SUM(e.cant_muestras) AS cant,
                  s.estado_perforacion,
                  s.estado_muestreo
           FROM etapas_sgs e
           JOIN sondajes s ON e.sondaje_id = s.id
           WHERE e.etapa = 'MUESTREO'
             AND e.fecha  = %s
             AND COALESCE(e.estado, 'ACTIVO') != 'ANULADO'
           GROUP BY s.bhid, s.estado_perforacion, s.estado_muestreo
           ORDER BY s.bhid""",
        (fecha,), fetchall=True
    ) or []


def _calcular_qaqc(fecha: str) -> dict:
    """Suma todos los QAQC del día para calcular % inserción."""
    row = ejecutar(
        """SELECT
               COALESCE(SUM(e.mues_ordinarias), 0)  AS ordinarias,
               COALESCE(SUM(e.mues_std_alta), 0)    AS std_alta,
               COALESCE(SUM(e.mues_std_baja), 0)    AS std_baja,
               COALESCE(SUM(e.dup_gemela), 0)       AS dup_gemela,
               COALESCE(SUM(e.dup_grueso), 0)       AS dup_grueso,
               COALESCE(SUM(e.dup_fino), 0)         AS dup_fino,
               COALESCE(SUM(e.muestras_blanco), 0)  AS blancos
           FROM etapas_sgs e
           WHERE e.etapa = 'MUESTREO'
             AND e.fecha  = %s
             AND COALESCE(e.estado, 'ACTIVO') != 'ANULADO'""",
        (fecha,), fetchone=True
    )
    if not row:
        return {"total": 0}

    ordinarias = int(row[0])
    std_alta   = int(row[1])
    std_baja   = int(row[2])
    dup_gemela = int(row[3])
    dup_grueso = int(row[4])
    dup_fino   = int(row[5])
    blancos    = int(row[6])

    control = std_alta + std_baja + dup_gemela + dup_grueso + dup_fino + blancos
    total   = ordinarias + control
    pct_insercion  = (control / total * 100) if total > 0 else 0
    pct_ordinarias = (ordinarias / total * 100) if total > 0 else 0

    return {
        "total":           total,
        "ordinarias":      ordinarias,
        "control":         control,
        "std_alta":        std_alta,
        "std_baja":        std_baja,
        "dup_gemela":      dup_gemela,
        "dup_grueso":      dup_grueso,
        "dup_fino":        dup_fino,
        "blancos":         blancos,
        "pct_insercion":   round(pct_insercion, 1),
        "pct_ordinarias":  round(pct_ordinarias, 1),
    }


def _batches_del_dia(fecha: str) -> list:
    """Batches enviados en la fecha indicada."""
    return ejecutar(
        """SELECT
               STRING_AGG(DISTINCT s.bhid, ', ' ORDER BY s.bhid) AS bhids,
               lc.cant_muestras,
               lc.numero_batch
           FROM laboratorio_certimin lc
           JOIN batch_sondajes bs ON bs.batch_id = lc.id
           JOIN sondajes s        ON bs.sondaje_id = s.id
           WHERE lc.fecha_envio = %s
           GROUP BY lc.id, lc.cant_muestras, lc.numero_batch
           ORDER BY lc.numero_batch""",
        (fecha,), fetchall=True
    ) or []


def _muestras_sin_batch() -> list:
    """
    Sondajes con muestreo registrado pero sin batch asociado.
    Pendientes de envío a laboratorio.
    """
    return ejecutar(
        """SELECT s.bhid,
                  SUM(e.cant_muestras) AS cant
           FROM etapas_sgs e
           JOIN sondajes s ON e.sondaje_id = s.id
           WHERE e.etapa = 'MUESTREO'
             AND COALESCE(e.estado, 'ACTIVO') != 'ANULADO'
             AND s.id NOT IN (
                 SELECT DISTINCT bs.sondaje_id
                 FROM batch_sondajes bs
                 JOIN laboratorio_certimin lc ON bs.batch_id = lc.id
             )
           GROUP BY s.bhid
           ORDER BY s.bhid""",
        fetchall=True
    ) or []


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _estado_str(estado_perf: str, estado_etapa: str) -> str:
    """Retorna 'FIN' o 'continúa' según el estado."""
    if estado_perf == "FINALIZADO" or estado_etapa in ("COMPLETADO", "FIN"):
        return "✅ FIN"
    return "🔄 continúa"


def _icono_qaqc(pct: float) -> str:
    if pct < QAQC_MIN:
        return "🚨"
    if pct <= QAQC_MAX:
        return "✅"
    return "⚠️"


def _fmt_fecha(fecha: str) -> str:
    try:
        from datetime import datetime
        return datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return fecha
