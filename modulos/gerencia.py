"""
FLUJO DE CONSULTAS — Gerencia y cualquier rol
Consultas de estado DDH, tajo, objetivo, resumen general,
ficha completa, costos, períodos, pendientes y ranking.
"""
from db.sondajes import (buscar_sondaje, sondajes_por_tajo,
                          sondajes_por_objetivo, resumen_campana)
from db.conexion import ejecutar
from ia.interprete import responder_consulta_gerencia
from config import fecha_hora_str, hora_peru

ICONOS = {
    "COMPLETADO":   "✅",
    "EN_PROCESO":   "🔄",
    "PENDIENTE":    "⏳",
    "NO_APLICA":    "➖",
    "OK":           "✅",
    "NP":           "➖",
    "GYRO":         "✅",
    "NO_REALIZADO": "❌",
}

ROLES_CON_COSTOS = {"GERENCIA", "ADMIN"}


def icono(estado: str) -> str:
    return ICONOS.get(str(estado).upper(), "⏳")


# ══════════════════════════════════════════════════════════════
# FICHA COMPLETA DDH — historia resumida
# ══════════════════════════════════════════════════════════════

def consultar_ddh_completo(texto: str, usuario: dict) -> str:
    """
    Ficha completa con toda la historia del sondaje:
    perforación → SGS → batch/laboratorio → modelamiento
    """
    sondaje = buscar_sondaje(texto)
    if not sondaje:
        return (
            f"❌ No encontré el sondaje *{texto}*.\n"
            f"Verifica el código o los últimos 4 dígitos.\n"
        )

    s    = sondaje
    bhid = s["bhid"]
    rol  = usuario.get("rol", "")

    # ── Datos básicos ─────────────────────────────────────────
    avance_pct = f"{float(s.get('avance_pct') or 0):.1f}%"
    final_m    = float(s.get("final_m") or 0)
    prog_m     = float(s.get("prog_m") or 0)
    objetivo   = s.get("tajo_objetivo") or s.get("cuerpo_objetivo") or "—"

    # Estado perforación
    if s.get("estado_perforacion") == "FINALIZADO":
        perf_str = f"✅ {final_m:.1f}/{prog_m:.1f} m ({avance_pct}) — Finalizado"
    elif s.get("estado_perforacion") == "EN_CURSO":
        perf_str = f"🔄 {final_m:.1f}/{prog_m:.1f} m ({avance_pct}) — En curso"
    else:
        perf_str = f"⏳ {final_m:.1f}/{prog_m:.1f} m — Planificado"

    # ── Último reporte de perforación ────────────────────────
    ult_perf = ejecutar(
        """SELECT ap.fecha, ap.turno, ap.prof_inicio, ap.prof_final,
                  m.codigo as maquina
           FROM avance_perforacion ap
           JOIN cat_maquinas m ON ap.maquina_id = m.id
           JOIN sondajes s ON ap.sondaje_id = s.id
           WHERE s.bhid = %s AND ap.estado = 'ACTIVO'
           ORDER BY ap.id DESC LIMIT 1""",
        (bhid,), fetchone=True
    )
    perf_detalle = ""
    if ult_perf:
        perf_detalle = (
            f"\n     {ult_perf[4]} | {ult_perf[1]} | "
            f"{_fmt_fecha(str(ult_perf[0]))} | "
            f"{float(ult_perf[2] or 0):.1f}→{float(ult_perf[3] or 0):.1f}m"
        )

    # ── Etapas SGS ────────────────────────────────────────────
    etapas_sgs = ejecutar(
        """SELECT etapa, desde_m, hasta_m, fecha, tecnico,
                  cant_muestras, COALESCE(estado, 'ACTIVO') as estado
           FROM etapas_sgs e
           JOIN sondajes s ON e.sondaje_id = s.id
           WHERE s.bhid = %s AND COALESCE(e.estado,'ACTIVO') != 'ANULADO'
           ORDER BY etapa, e.id DESC""",
        (bhid,), fetchall=True
    ) or []

    # Agrupar por etapa (solo el más reciente)
    etapas_dict = {}
    for e in etapas_sgs:
        etapa = e[0]
        if etapa not in etapas_dict:
            etapas_dict[etapa] = e

    def _etapa_str(clave, nombre):
        e = etapas_dict.get(clave)
        if not e:
            return f"⏳ {nombre}      Pendiente"
        desde = float(e[1] or 0)
        hasta = float(e[2] or 0)
        fecha = _fmt_fecha(str(e[3])) if e[3] else "—"
        extra = f"{desde:.1f}→{hasta:.1f}m | {fecha}"
        if clave == "MUESTREO" and e[5]:
            extra += f" | {e[5]} muestras"
        return f"✅ {nombre}      {extra}"

    # ── Batch y laboratorio ───────────────────────────────────
    batch_row = ejecutar(
        """SELECT lc.numero_batch, lc.cant_muestras, lc.fecha_envio,
                  lc.confirmado_recepcion, lc.resultados_disponibles,
                  lc.fecha_resultados, lc.archivo_resultados,
                  COALESCE(lc.destino, 'LOCAL') as destino
           FROM laboratorio_certimin lc
           JOIN batch_sondajes bs ON bs.batch_id = lc.id
           JOIN sondajes s ON bs.sondaje_id = s.id
           WHERE s.bhid = %s
           ORDER BY lc.id DESC LIMIT 1""",
        (bhid,), fetchone=True
    )

    if batch_row:
        b_num     = batch_row[0]
        b_mues    = batch_row[1] or "?"
        b_envio   = _fmt_fecha(str(batch_row[2])) if batch_row[2] else "—"
        b_recep   = "✅ Recibido" if batch_row[3] else "⏳ En tránsito"
        b_result  = "✅ Analizadas" if batch_row[4] else "⏳ Pendiente"
        b_destino = "🏭 Local" if batch_row[7] == "LOCAL" else "✈️ Lima"
        b_fecha_r = _fmt_fecha(str(batch_row[5])) if batch_row[5] else "—"
        batch_str = (
            f"📦 Batch *{b_num}* | {b_mues} muestras | {b_destino}\n"
            f"   Envío: {b_envio} | {b_recep}\n"
            f"   Leyes: {b_result}"
            + (f" ({b_fecha_r})" if batch_row[4] else "")
        )
        lab_icono = "✅" if batch_row[4] else ("🔄" if batch_row[3] else "⏳")
    else:
        batch_str = "_(Sin batch registrado)_"
        lab_icono = "⏳"

    # ── Modelamiento y estimación ─────────────────────────────
    est_estado = s.get("estado_estimacion", "PENDIENTE") or "PENDIENTE"
    mod_estado = s.get("estado_modelado", "PENDIENTE") or "PENDIENTE"
    modelo_cp  = s.get("modelo_cp") or "—"

    mod_str = f"{icono(mod_estado)} Modelamiento"
    est_str = (
        f"{icono(est_estado)} Estimación"
        + (f"   Modelo: *{modelo_cp}*" if est_estado == "COMPLETADO" else "")
    )

    # ── Costo (solo GERENCIA y ADMIN) ────────────────────────
    costo_str = ""
    if rol in ROLES_CON_COSTOS and final_m > 0:
        costo = _calcular_costo_sondaje(bhid)
        if costo:
            costo_str = f"\n💰 Costo estimado: *${costo:,.2f} USD*"

    # ── Armar mensaje final ───────────────────────────────────
    return (
        f"🔍 *{bhid}*\n"
        f"{'─'*30}\n"
        f"📂 {s.get('subcategoria','—')} | 🎯 {objetivo}\n"
        f"🏔️ Nv.{s.get('nivel','—')} | {s.get('labor','—')}\n"
        f"🚜 {s.get('maquina','—')} ({s.get('empresa','—')}) | {s.get('diametro','—')}\n"
        f"{'─'*30}\n"
        f"⛏️ *Perforación*\n"
        f"   {perf_str}{perf_detalle}\n"
        f"{'─'*30}\n"
        f"*SGS:*\n"
        f"   {_etapa_str('LOGUEO',     '📝 Logueo    ')}\n"
        f"   {_etapa_str('MUESTREO',   '🧪 Muestreo  ')}\n"
        f"   {_etapa_str('RQD',        '📐 RQD       ')}\n"
        f"   {_etapa_str('FOTOGRAFIA', '📸 Fotografía')}\n"
        f"   {_etapa_str('DENSIDAD',   '⚖️ Densidad  ')}\n"
        f"{'─'*30}\n"
        f"*Laboratorio:*\n"
        f"   {batch_str}\n"
        f"{'─'*30}\n"
        f"*Modelamiento:*\n"
        f"   {mod_str}\n"
        f"   {est_str}\n"
        f"{'─'*30}"
        f"{costo_str}\n"
        f"📅 {fecha_hora_str()}"
    )


# ══════════════════════════════════════════════════════════════
# CONSULTA DDH SIMPLE (mantener compatibilidad)
# ══════════════════════════════════════════════════════════════

def consultar_ddh(texto: str, usuario: dict) -> str:
    """Ficha completa — redirige a consultar_ddh_completo."""
    return consultar_ddh_completo(texto, usuario)


# ══════════════════════════════════════════════════════════════
# CONSULTA BATCH
# ══════════════════════════════════════════════════════════════

def consultar_batch(numero_batch: str, usuario: dict) -> str:
    row = ejecutar(
        """SELECT lc.numero_batch, lc.cant_muestras, lc.fecha_envio,
                  lc.confirmado_recepcion, lc.fecha_confirmacion,
                  lc.resultados_disponibles, lc.fecha_resultados,
                  lc.archivo_resultados, COALESCE(lc.destino,'LOCAL') as destino,
                  u.nombre as creado_por
           FROM laboratorio_certimin lc
           LEFT JOIN usuarios_bot u ON lc.creado_por = u.id
           WHERE lc.numero_batch = %s""",
        (numero_batch.strip(),), fetchone=True
    )
    if not row:
        return f"❌ Batch *{numero_batch}* no encontrado en el sistema."

    # Sondajes vinculados
    sondajes = ejecutar(
        """SELECT s.bhid FROM sondajes s
           JOIN batch_sondajes bs ON bs.sondaje_id = s.id
           JOIN laboratorio_certimin lc ON bs.batch_id = lc.id
           WHERE lc.numero_batch = %s""",
        (numero_batch.strip(),), fetchall=True
    ) or []
    sondajes_str = ", ".join(f"*{r[0]}*" for r in sondajes) or "—"

    destino_label = "🏭 Local (Ica)" if row[8] == "LOCAL" else "✈️ Lima"
    recep_str  = f"✅ {_fmt_fecha(str(row[4]))}" if row[3] else "⏳ Pendiente"
    result_str = f"✅ {_fmt_fecha(str(row[6]))}" if row[5] else "⏳ Pendiente"
    archivo    = row[7] or "—"

    return (
        f"📦 *Batch {row[0]}*\n"
        f"{'─'*28}\n"
        f"🔖 Sondajes:  {sondajes_str}\n"
        f"🧪 Muestras:  {row[1] or '—'}\n"
        f"📅 Enviado:   {_fmt_fecha(str(row[2])) if row[2] else '—'}\n"
        f"📍 Destino:   {destino_label}\n"
        f"👤 Registró:  {row[9] or '—'}\n"
        f"{'─'*28}\n"
        f"📦 Recepción: {recep_str}\n"
        f"📊 Resultados:{result_str}\n"
        f"📄 Archivo:   {archivo}\n"
        f"{'─'*28}\n"
        f"📅 {fecha_hora_str()}"
    )


# ══════════════════════════════════════════════════════════════
# CONSULTAS DE PERÍODO — semana / mes
# ══════════════════════════════════════════════════════════════

def consultar_metros_semana(usuario: dict) -> str:
    """Metros perforados en los últimos 7 días por empresa y máquina."""
    rol = usuario.get("rol", "")
    rows = ejecutar(
        """SELECT m.codigo, e.nombre as empresa, m.sufijo_tarifa,
                  SUM(ap.prof_final - ap.prof_inicio) as metros,
                  COUNT(DISTINCT ap.fecha) as dias,
                  COUNT(*) as reportes,
                  s.diametro
           FROM avance_perforacion ap
           JOIN cat_maquinas m ON ap.maquina_id = m.id
           JOIN cat_empresas e ON m.empresa_id = e.id
           JOIN sondajes s ON ap.sondaje_id = s.id
           WHERE ap.fecha >= CURRENT_DATE - INTERVAL '7 days'
             AND ap.estado = 'ACTIVO'
           GROUP BY m.codigo, e.nombre, m.sufijo_tarifa, s.diametro
           ORDER BY e.nombre, metros DESC""",
        fetchall=True
    ) or []

    if not rows:
        return "📋 Sin reportes de perforación en los últimos 7 días."

    total_metros = sum(float(r[3] or 0) for r in rows)
    hoy          = hora_peru()
    desde        = (hoy.date().__str__())

    # Agrupar por empresa
    empresas = {}
    for r in rows:
        maq, emp, sufijo, metros, dias, reportes, diam = r
        metros = float(metros or 0)
        if emp not in empresas:
            empresas[emp] = {"metros": 0, "maquinas": [], "sufijo": sufijo}
        empresas[emp]["metros"] += metros
        empresas[emp]["maquinas"].append((maq, metros, dias, sufijo, diam))

    lineas = [
        f"📊 *PERFORACIÓN — ÚLTIMOS 7 DÍAS*\n"
        f"{'─'*28}"
    ]

    costo_total = 0.0
    for emp, data in empresas.items():
        lineas.append(f"\n🏢 *{emp}* — {data['metros']:,.1f} m")
        for maq, metros, dias, sufijo, diam in data["maquinas"]:
            costo_maq = 0.0
            if rol in ROLES_CON_COSTOS:
                costo_maq = _calcular_costo_periodo(maq, sufijo, diam, metros)
                costo_total += costo_maq
                costo_str = f" | 💰 ${costo_maq:,.0f}"
            else:
                costo_str = ""
            lineas.append(f"   🚜 {maq}: {metros:,.1f} m ({dias}d){costo_str}")

    lineas.append(f"\n{'─'*28}")
    lineas.append(f"📏 *Total: {total_metros:,.1f} m*")
    if rol in ROLES_CON_COSTOS and costo_total > 0:
        lineas.append(f"💰 *Costo total: ${costo_total:,.0f} USD*")
    lineas.append(f"📅 {fecha_hora_str()}")

    return "\n".join(lineas)


def consultar_metros_mes(usuario: dict, mes: int = None, anio: int = None) -> str:
    """Metros perforados en el mes actual (o el indicado) por empresa."""
    rol  = usuario.get("rol", "")
    hoy  = hora_peru()
    mes  = mes  or hoy.month
    anio = anio or hoy.year

    rows = ejecutar(
        """SELECT m.codigo, e.nombre as empresa, m.sufijo_tarifa,
                  SUM(ap.prof_final - ap.prof_inicio) as metros,
                  COUNT(DISTINCT ap.fecha) as dias_activos,
                  s.diametro
           FROM avance_perforacion ap
           JOIN cat_maquinas m ON ap.maquina_id = m.id
           JOIN cat_empresas e ON m.empresa_id = e.id
           JOIN sondajes s ON ap.sondaje_id = s.id
           WHERE EXTRACT(MONTH FROM ap.fecha) = %s
             AND EXTRACT(YEAR  FROM ap.fecha) = %s
             AND ap.estado = 'ACTIVO'
           GROUP BY m.codigo, e.nombre, m.sufijo_tarifa, s.diametro
           ORDER BY e.nombre, metros DESC""",
        (mes, anio), fetchall=True
    ) or []

    if not rows:
        return f"📋 Sin reportes para {mes:02d}/{anio}."

    total_metros = sum(float(r[3] or 0) for r in rows)
    nombre_mes   = _nombre_mes(mes)

    empresas = {}
    for r in rows:
        maq, emp, sufijo, metros, dias, diam = r
        metros = float(metros or 0)
        if emp not in empresas:
            empresas[emp] = {"metros": 0, "maquinas": []}
        empresas[emp]["metros"] += metros
        empresas[emp]["maquinas"].append((maq, metros, dias, sufijo, diam))

    lineas = [
        f"📊 *PERFORACIÓN — {nombre_mes.upper()} {anio}*\n"
        f"{'─'*28}"
    ]

    costo_total = 0.0
    for emp, data in empresas.items():
        lineas.append(f"\n🏢 *{emp}* — {data['metros']:,.1f} m")
        for maq, metros, dias, sufijo, diam in data["maquinas"]:
            costo_str = ""
            if rol in ROLES_CON_COSTOS:
                costo_maq = _calcular_costo_periodo(maq, sufijo, diam, metros)
                costo_total += costo_maq
                costo_str = f" | 💰 ${costo_maq:,.0f}"
            lineas.append(f"   🚜 {maq}: {metros:,.1f} m ({dias} días){costo_str}")

    lineas.append(f"\n{'─'*28}")
    lineas.append(f"📏 *Total: {total_metros:,.1f} m*")
    if rol in ROLES_CON_COSTOS and costo_total > 0:
        lineas.append(f"💰 *Costo total: ${costo_total:,.0f} USD*")
    lineas.append(f"📅 {fecha_hora_str()}")

    return "\n".join(lineas)


# ══════════════════════════════════════════════════════════════
# RANKING DE MÁQUINAS
# ══════════════════════════════════════════════════════════════

def ranking_maquinas(usuario: dict, dias: int = 30) -> str:
    """Ranking de productividad por máquina en los últimos N días."""
    rol  = usuario.get("rol", "")
    rows = ejecutar(
        """SELECT m.codigo, e.nombre,
                  SUM(ap.prof_final - ap.prof_inicio) as metros,
                  COUNT(DISTINCT ap.fecha) as dias_activos,
                  COUNT(DISTINCT ap.turno || ap.fecha::text) as turnos,
                  m.sufijo_tarifa,
                  MAX(s.diametro) as diametro
           FROM avance_perforacion ap
           JOIN cat_maquinas m ON ap.maquina_id = m.id
           JOIN cat_empresas e ON m.empresa_id = e.id
           JOIN sondajes s ON ap.sondaje_id = s.id
           WHERE ap.fecha >= CURRENT_DATE - INTERVAL '%s days'
             AND ap.estado = 'ACTIVO'
           GROUP BY m.codigo, e.nombre, m.sufijo_tarifa
           ORDER BY metros DESC""",
        (dias,), fetchall=True
    ) or []

    if not rows:
        return f"📋 Sin datos de los últimos {dias} días."

    lineas = [
        f"🏆 *RANKING MÁQUINAS — {dias} días*\n"
        f"{'─'*28}"
    ]

    for i, r in enumerate(rows, 1):
        maq, emp, metros, dias_act, turnos, sufijo, diam = r
        metros = float(metros or 0)
        m_turno = metros / turnos if turnos else 0
        costo_str = ""
        if rol in ROLES_CON_COSTOS:
            costo = _calcular_costo_periodo(maq, sufijo, diam, metros)
            costo_str = f" | 💰 ${costo:,.0f}"
        medalla = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        lineas.append(
            f"{medalla} *{maq}* ({emp})\n"
            f"   {metros:,.1f} m | {m_turno:.1f} m/turno | {dias_act} días{costo_str}"
        )

    lineas.append(f"\n📅 {fecha_hora_str()}")
    return "\n".join(lineas)


# ══════════════════════════════════════════════════════════════
# PENDIENTES POR ETAPA
# ══════════════════════════════════════════════════════════════

def consultar_pendientes(etapa: str = None, usuario: dict = None) -> str:
    """
    Sondajes con etapas pendientes.
    Si se especifica etapa: LOGUEO, MUESTREO, MODELADO, ESTIMACION, LABORATORIO
    Si no: resumen general de brechas.
    """
    if etapa:
        etapa = etapa.upper()

    if etapa in (None, "GENERAL"):
        return _pendientes_resumen()
    elif etapa == "LOGUEO":
        return _pendientes_etapa_sgs("LOGUEO", "📝 Logueo")
    elif etapa == "MUESTREO":
        return _pendientes_etapa_sgs("MUESTREO", "🧪 Muestreo")
    elif etapa in ("MODELADO", "MODELAMIENTO"):
        return _pendientes_modelado()
    elif etapa == "ESTIMACION":
        return _pendientes_estimacion()
    elif etapa == "LABORATORIO":
        return _pendientes_laboratorio()
    else:
        return _pendientes_resumen()


def _pendientes_resumen() -> str:
    """Resumen de brechas por etapa."""
    rows = ejecutar(
        """SELECT
               SUM(CASE WHEN COALESCE(estado_logueo,'PENDIENTE') != 'COMPLETADO'
                        AND profundidad_final > 0 THEN 1 ELSE 0 END) as sin_logueo,
               SUM(CASE WHEN COALESCE(estado_muestreo,'PENDIENTE') != 'COMPLETADO'
                        AND profundidad_final > 0 THEN 1 ELSE 0 END) as sin_muestreo,
               SUM(CASE WHEN COALESCE(estado_laboratorio,'PENDIENTE') != 'COMPLETADO'
                        AND profundidad_final > 0 THEN 1 ELSE 0 END) as sin_leyes,
               SUM(CASE WHEN COALESCE(estado_modelado,'PENDIENTE') != 'COMPLETADO'
                        AND estado_laboratorio = 'COMPLETADO' THEN 1 ELSE 0 END) as sin_modelar,
               SUM(CASE WHEN COALESCE(estado_estimacion,'PENDIENTE') != 'COMPLETADO'
                        AND COALESCE(estado_modelado,'PENDIENTE') = 'COMPLETADO'
                        THEN 1 ELSE 0 END) as sin_estimar
           FROM sondajes
           WHERE profundidad_final > 0""",
        fetchone=True
    )

    if not rows:
        return "⚠️ Sin datos."

    sin_log, sin_mues, sin_leyes, sin_mod, sin_est = rows

    return (
        f"⚠️ *PENDIENTES POR ETAPA*\n"
        f"{'─'*28}\n"
        f"📝 Sin loguear:    *{sin_log or 0}* sondajes\n"
        f"🧪 Sin muestrear:  *{sin_mues or 0}* sondajes\n"
        f"🧪 Sin leyes:      *{sin_leyes or 0}* sondajes\n"
        f"🗂️ Sin modelar:    *{sin_mod or 0}* sondajes\n"
        f"📐 Sin estimar:    *{sin_est or 0}* sondajes\n"
        f"{'─'*28}\n"
        f"Pregunta por etapa: *'qué falta loguear'*\n"
        f"📅 {fecha_hora_str()}"
    )


def _pendientes_etapa_sgs(etapa: str, nombre: str) -> str:
    rows = ejecutar(
        """SELECT s.bhid, sc.nombre as subcat,
                  s.tajo_objetivo, s.cuerpo_objetivo,
                  s.profundidad_final
           FROM sondajes s
           LEFT JOIN cat_subcategorias sc ON s.subcategoria_id = sc.id
           WHERE s.profundidad_final > 0
             AND NOT EXISTS (
                 SELECT 1 FROM etapas_sgs e
                 WHERE e.sondaje_id = s.id
                   AND e.etapa = %s
                   AND COALESCE(e.estado,'ACTIVO') != 'ANULADO'
             )
           ORDER BY s.bhid
           LIMIT 15""",
        (etapa,), fetchall=True
    ) or []

    if not rows:
        return f"✅ No hay sondajes pendientes de *{nombre}*."

    lineas = [f"{nombre} — *{len(rows)} pendientes*\n{'─'*28}"]
    for r in rows:
        bhid, subcat, tajo, cuerpo, final = r
        obj = tajo or cuerpo or "—"
        lineas.append(f"  • *{bhid}* — {subcat or '—'} | {obj} | {float(final or 0):.1f}m")
    if len(rows) == 15:
        lineas.append("  _...ver más consultando por tajo_")
    lineas.append(f"\n📅 {fecha_hora_str()}")
    return "\n".join(lineas)


def _pendientes_modelado() -> str:
    rows = ejecutar(
        """SELECT s.bhid, sc.nombre, s.tajo_objetivo, s.cuerpo_objetivo
           FROM sondajes s
           LEFT JOIN cat_subcategorias sc ON s.subcategoria_id = sc.id
           WHERE s.estado_laboratorio = 'COMPLETADO'
             AND COALESCE(s.estado_modelado, 'PENDIENTE') != 'COMPLETADO'
           ORDER BY s.bhid LIMIT 15""",
        fetchall=True
    ) or []

    if not rows:
        return "✅ No hay sondajes pendientes de modelamiento."

    lineas = [f"🗂️ *Pendientes de MODELAR* — {len(rows)}\n{'─'*28}"]
    for r in rows:
        obj = r[2] or r[3] or "—"
        lineas.append(f"  • *{r[0]}* — {r[1] or '—'} | {obj}")
    lineas.append(f"\n📅 {fecha_hora_str()}")
    return "\n".join(lineas)


def _pendientes_estimacion() -> str:
    rows = ejecutar(
        """SELECT s.bhid, sc.nombre, s.tajo_objetivo, s.cuerpo_objetivo,
                  COALESCE(s.modelo_cp, '—')
           FROM sondajes s
           LEFT JOIN cat_subcategorias sc ON s.subcategoria_id = sc.id
           WHERE COALESCE(s.estado_modelado,'PENDIENTE') = 'COMPLETADO'
             AND COALESCE(s.estado_estimacion,'PENDIENTE') != 'COMPLETADO'
           ORDER BY s.bhid LIMIT 15""",
        fetchall=True
    ) or []

    if not rows:
        return "✅ No hay sondajes pendientes de estimación."

    lineas = [f"📐 *Pendientes de ESTIMAR* — {len(rows)}\n{'─'*28}"]
    for r in rows:
        obj = r[2] or r[3] or "—"
        lineas.append(f"  • *{r[0]}* — {r[1] or '—'} | {obj}")
    lineas.append(f"\n📅 {fecha_hora_str()}")
    return "\n".join(lineas)


def _pendientes_laboratorio() -> str:
    rows = ejecutar(
        """SELECT s.bhid, sc.nombre, s.tajo_objetivo, s.cuerpo_objetivo,
                  lc.numero_batch, lc.confirmado_recepcion
           FROM sondajes s
           LEFT JOIN cat_subcategorias sc ON s.subcategoria_id = sc.id
           LEFT JOIN batch_sondajes bs ON bs.sondaje_id = s.id
           LEFT JOIN laboratorio_certimin lc ON bs.batch_id = lc.id
           WHERE COALESCE(s.estado_laboratorio,'PENDIENTE') != 'COMPLETADO'
             AND s.profundidad_final > 0
           ORDER BY s.bhid LIMIT 15""",
        fetchall=True
    ) or []

    if not rows:
        return "✅ No hay sondajes pendientes de laboratorio."

    lineas = [f"🧪 *Pendientes de LABORATORIO* — {len(rows)}\n{'─'*28}"]
    for r in rows:
        bhid, subcat, tajo, cuerpo, batch, recepcion = r
        obj = tajo or cuerpo or "—"
        estado_lab = "🔄 En tránsito" if batch and not recepcion else \
                     "🔄 En análisis" if batch and recepcion else \
                     "⏳ Sin batch"
        batch_str = f"Batch {batch}" if batch else "sin batch"
        lineas.append(f"  • *{bhid}* — {obj} | {estado_lab} ({batch_str})")
    lineas.append(f"\n📅 {fecha_hora_str()}")
    return "\n".join(lineas)


# ══════════════════════════════════════════════════════════════
# CONSULTA POR TAJO
# ══════════════════════════════════════════════════════════════

def consultar_tajo(tajo: str, usuario: dict) -> str:
    rows = sondajes_por_tajo(tajo)
    if not rows:
        return f"❌ No encontré sondajes para el tajo *{tajo}*."

    total      = len(rows)
    perforados = sum(1 for r in rows if r[2] and float(r[2]) > 0)
    logueados  = sum(1 for r in rows if r[4] == "COMPLETADO")
    con_leyes  = sum(1 for r in rows if r[5] == "COMPLETADO")
    modelados  = sum(1 for r in rows if r[6] == "COMPLETADO")
    metros_tot = sum(float(r[2] or 0) for r in rows)

    detalle = ""
    for r in rows[:15]:
        bhid, prog, final, avpct, log, lab, mod, maq, emp = r
        bar = f"{float(avpct or 0):.0f}%"
        detalle += f"  • *{bhid}* {bar} {icono(log)}{icono(lab)}{icono(mod)}\n"
    if total > 15:
        detalle += f"  _...y {total-15} más_\n"

    return (
        f"📋 *Tajo {tajo}* — {total} sondajes\n"
        f"{'─'*30}\n"
        f"⛏️ Perforados:  {perforados}/{total}\n"
        f"📏 Metros:      {metros_tot:,.1f} m\n"
        f"✅ Logueados:   {logueados}/{total}\n"
        f"🧪 Con leyes:   {con_leyes}/{total}\n"
        f"🗂️ Modelados:   {modelados}/{total}\n"
        f"{'─'*30}\n"
        f"{detalle}"
        f"📅 {fecha_hora_str()}"
    )


# ══════════════════════════════════════════════════════════════
# CONSULTA POR OBJETIVO
# ══════════════════════════════════════════════════════════════

def consultar_objetivo(objetivo: str, usuario: dict) -> str:
    rows = sondajes_por_objetivo(objetivo)
    if not rows:
        return f"❌ No encontré sondajes para el objetivo *{objetivo}*."

    total     = len(rows)
    metros    = sum(float(r[3] or 0) for r in rows)
    con_leyes = sum(1 for r in rows if r[6] == "COMPLETADO")
    modelados = sum(1 for r in rows if r[7] == "COMPLETADO")

    detalle = ""
    for r in rows[:15]:
        bhid, subcat, prog, final, avpct, log, lab, mod, maq, emp, tajo, cuerpo = r
        bar = f"{float(avpct or 0):.0f}%"
        obj = tajo or cuerpo or "—"
        detalle += f"  • *{bhid}* → {obj} {bar}\n"
    if total > 15:
        detalle += f"  _...y {total-15} más_\n"

    return (
        f"🎯 *Objetivo: {objetivo}* — {total} sondajes\n"
        f"{'─'*30}\n"
        f"📏 Metros perforados: {metros:,.1f} m\n"
        f"🧪 Con leyes:         {con_leyes}/{total}\n"
        f"🗂️ Modelados:         {modelados}/{total}\n"
        f"{'─'*30}\n"
        f"{detalle}"
        f"📅 {fecha_hora_str()}"
    )


# ══════════════════════════════════════════════════════════════
# RESUMEN GENERAL
# ══════════════════════════════════════════════════════════════

def resumen_general(usuario: dict) -> str:
    datos = resumen_campana()
    if not datos:
        return "⚠️ Sin datos disponibles."

    total  = datos.get("total", 0)
    perf   = datos.get("perforados", 0)
    metros = float(datos.get("metros_perforados", 0))
    mprog  = float(datos.get("metros_prog", 0))
    avpct  = (metros / mprog * 100) if mprog > 0 else 0
    log    = datos.get("logueados", 0)
    mues   = datos.get("muestreados", 0)
    leyes  = datos.get("con_leyes", 0)
    mod    = datos.get("modelados", 0)

    campanas = ejecutar(
        """SELECT campana, COUNT(*), SUM(profundidad_final)
           FROM sondajes WHERE campana IS NOT NULL
           GROUP BY campana ORDER BY campana DESC LIMIT 3""",
        fetchall=True
    )
    camp_str = ""
    if campanas:
        for c in campanas:
            camp_str += f"  📅 {c[0]}: {c[1]} DDH | {float(c[2] or 0):,.1f} m\n"

    return (
        f"📊 *RESUMEN CERRO LINDO*\n"
        f"📅 {fecha_hora_str()}\n"
        f"{'─'*30}\n"
        f"🔢 Total DDH:        {total}\n"
        f"⛏️ Perforados:       {perf}/{total}\n"
        f"📏 Metros:           {metros:,.1f} / {mprog:,.1f} m ({avpct:.1f}%)\n"
        f"{'─'*30}\n"
        f"✅ Logueados:        {log}/{total}\n"
        f"🔬 Muestreados:      {mues}/{total}\n"
        f"🧪 Con leyes:        {leyes}/{total}\n"
        f"🗂️ Modelados:        {mod}/{total}\n"
        f"{'─'*30}\n"
        f"*Por campaña:*\n{camp_str}"
    )


# ══════════════════════════════════════════════════════════════
# SONDAJES EN CURSO
# ══════════════════════════════════════════════════════════════

def sondajes_en_curso(usuario: dict) -> str:
    rows = ejecutar(
        """SELECT bhid, maquina, empresa, nivel, labor,
                  prog_m, final_m, avance_pct, diametro,
                  tajo_objetivo, cuerpo_objetivo, ultimo_reporte
           FROM v_sondajes_en_curso
           ORDER BY empresa, maquina""",
        fetchall=True
    )
    if not rows:
        return "📋 No hay sondajes en perforación actualmente."

    total      = len(rows)
    metros_tot = sum(float(r[6] or 0) for r in rows)

    detalle        = ""
    empresa_actual = ""
    for r in rows:
        bhid, maq, emp, nivel, labor, prog, final, avpct, diam, tajo, cuerpo, ult_rep = r
        if emp != empresa_actual:
            empresa_actual = emp
            detalle += f"\n*{emp}:*\n"
        objetivo = tajo or cuerpo or "—"
        pct      = f"{float(avpct or 0):.0f}%"
        ult      = str(ult_rep)[:10] if ult_rep else "sin reporte"
        detalle += (
            f"  🔖 *{bhid}* → {objetivo}\n"
            f"     {maq} | Nv.{nivel} | {diam}\n"
            f"     {float(final or 0):.1f}/{float(prog or 0):.1f} m ({pct}) | {ult}\n"
        )

    return (
        f"⛏️ *SONDAJES EN PERFORACIÓN*\n"
        f"{'─'*30}\n"
        f"Total activos: *{total}*\n"
        f"Metros acumulados: *{metros_tot:,.1f} m*\n"
        f"{'─'*30}\n"
        f"{detalle}\n"
        f"📅 {fecha_hora_str()}"
    )


# ══════════════════════════════════════════════════════════════
# CONSULTA DE FOTOS
# ══════════════════════════════════════════════════════════════

def consultar_foto(texto: str, usuario: dict, sesion=None,
                   filtro_origen: str = None) -> str:
    """
    filtro_origen: None=todas, 'PERFORACION'=solo perf, 'SGS'=solo sgs/logueo
    """
    from db.sesiones import crear_sesion, actualizar_sesion, cerrar_sesion as _cerrar

    # Selección desde sesión activa
    if sesion and sesion.get("flujo") == "9" \
            and sesion.get("paso") == "seleccion_foto":
        fotos = sesion["datos"].get("fotos", [])
        try:
            idx = int(texto.strip()) - 1
            if idx < 0 or idx >= len(fotos):
                return f"❓ Responde con un número del 1 al {len(fotos)}."
            foto = fotos[idx]
            _cerrar(usuario["id"])
            return {
                "tipo":    "imagen",
                "url":     foto[0],
                "caption": f"📸 {foto[5]} | {foto[3]} | Tramo {foto[1]} | {foto[2]}"
            }
        except Exception as e:
            print(f"[GERENCIA] Error selección foto: {e}")
            return "❓ Responde con un número válido."

    sondaje = buscar_sondaje(texto)
    if not sondaje:
        return "❌ No encontré el sondaje. Ejemplo: *foto del 9999*"

    bhid = sondaje["bhid"]

    rows_perf = []
    rows_sgs  = []

    if filtro_origen in (None, "PERFORACION"):
        rows_perf = ejecutar(
            """SELECT ap.foto_url,
                      COALESCE(ap.foto_tramo, '—'),
                      ap.fecha::text,
                      CONCAT('Perf. ', ap.turno, ' | ', m.codigo),
                      m.codigo, s.bhid, 'PERFORACION', ap.id
               FROM avance_perforacion ap
               JOIN sondajes s ON ap.sondaje_id = s.id
               JOIN cat_maquinas m ON ap.maquina_id = m.id
               WHERE s.bhid = %s AND ap.foto_url IS NOT NULL
               ORDER BY ap.id DESC""",
            (bhid,), fetchall=True
        ) or []

    if filtro_origen in (None, "SGS"):
        rows_sgs = ejecutar(
            """SELECT e.foto_url,
                      CONCAT(ROUND(e.desde_m::numeric,1)::text,'-',
                             ROUND(e.hasta_m::numeric,1)::text,'m'),
                      e.fecha::text,
                      CONCAT(e.etapa,' | ',COALESCE(e.tecnico,'—')),
                      COALESCE(e.tecnico,'SGS'),
                      s.bhid, e.etapa, e.id
               FROM etapas_sgs e
               JOIN sondajes s ON e.sondaje_id = s.id
               WHERE s.bhid = %s AND e.foto_url IS NOT NULL
               ORDER BY e.id DESC""",
            (bhid,), fetchall=True
        ) or []

    todas = sorted(
        list(rows_perf) + list(rows_sgs),
        key=lambda r: r[7], reverse=True
    )[:10]

    if not todas:
        tipo_str = {
            "PERFORACION": "de perforación",
            "SGS": "de SGS/logueo"
        }.get(filtro_origen, "")
        return f"📸 No hay fotos {tipo_str} registradas para *{bhid}*."

    fotos = [[r[0], r[1], r[2], r[3], r[4], r[5], r[6]] for r in todas]

    if len(fotos) == 1:
        f = fotos[0]
        return {
            "tipo":    "imagen",
            "url":     f[0],
            "caption": f"📸 {f[5]} | {f[3]} | Tramo {f[1]} | {f[2]}"
        }

    sid = crear_sesion(usuario["id"], "9")
    actualizar_sesion(sid, "seleccion_foto", {"fotos": fotos, "bhid": bhid})
    fotos_menu = [(f[0], f[1], f[2], f[3], f[4]) for f in fotos]

    return {
        "tipo":  "lista_fotos",
        "fotos": fotos_menu,
        "bhid":  bhid,
    }


# ══════════════════════════════════════════════════════════════
# CONSULTA LIBRE IA
# ══════════════════════════════════════════════════════════════

def consulta_libre_gerencia(pregunta: str, usuario: dict) -> str:
    datos = {"resumen_general": resumen_campana()}
    return responder_consulta_gerencia(pregunta, datos)


# ══════════════════════════════════════════════════════════════
# HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════

def _calcular_costo_sondaje(bhid: str) -> float | None:
    """Calcula el costo total de un sondaje usando cat_tarifas."""
    rows = ejecutar(
        """SELECT ap.prof_inicio, ap.prof_final, s.diametro, m.sufijo_tarifa
           FROM avance_perforacion ap
           JOIN sondajes s ON ap.sondaje_id = s.id
           JOIN cat_maquinas m ON ap.maquina_id = m.id
           WHERE s.bhid = %s AND ap.estado = 'ACTIVO'
           ORDER BY ap.id""",
        (bhid,), fetchall=True
    ) or []

    if not rows:
        return None

    total = 0.0
    for r in rows:
        prof_ini, prof_fin, diam, sufijo = r
        metros = float(prof_fin or 0) - float(prof_ini or 0)
        if metros <= 0:
            continue
        tarifa = _obtener_tarifa(diam, sufijo, float(prof_ini or 0), float(prof_fin or 0))
        total += tarifa * metros

    return total if total > 0 else None


def _calcular_costo_periodo(maq: str, sufijo: str, diam: str, metros: float) -> float:
    """Estimación simplificada de costo para un período dado."""
    if not sufijo or not diam or metros <= 0:
        return 0.0
    # Tarifa promedio aproximada para el período (usa tramo 0-100 como base)
    tarifa = _obtener_tarifa(diam, sufijo, 0, metros)
    return tarifa * metros


def _obtener_tarifa(diametro: str, sufijo: str, desde: float, hasta: float) -> float:
    """Obtiene la tarifa USD/m según diámetro, sufijo y tramo de profundidad."""
    # pg8000 requiere int para columnas int4 — castear explícitamente
    punto_medio = int((desde + hasta) / 2)
    row = ejecutar(
        """SELECT precio_usd FROM cat_tarifas
           WHERE diametro = %s
             AND sufijo = %s
             AND tramo_desde <= %s
             AND tramo_hasta > %s
             AND fase_activa = TRUE
           ORDER BY tramo_desde DESC
           LIMIT 1""",
        (diametro, sufijo, punto_medio, punto_medio),
        fetchone=True
    )
    if row:
        return float(row[0])
    # Fallback: tarifa más alta del diámetro/sufijo
    row2 = ejecutar(
        """SELECT precio_usd FROM cat_tarifas
           WHERE diametro = %s AND sufijo = %s AND fase_activa = TRUE
           ORDER BY precio_usd DESC LIMIT 1""",
        (diametro, sufijo), fetchone=True
    )
    return float(row2[0]) if row2 else 0.0


def _fmt_fecha(fecha: str) -> str:
    try:
        from datetime import datetime
        return datetime.strptime(fecha[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return str(fecha)[:10] if fecha else "—"


def _nombre_mes(mes: int) -> str:
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return meses[mes - 1] if 1 <= mes <= 12 else str(mes)
