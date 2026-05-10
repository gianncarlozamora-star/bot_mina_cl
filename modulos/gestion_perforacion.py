"""
MÓDULO GESTIÓN PERFORACIÓN DIAMANTINA
Consultas y consolidado bajo demanda para geólogo, admin y perforista.

Submenú:
  1 — Consolidado del turno (por empresa)
  2 — Sondajes activos
  3 — Métricas del turno

Sin sesión — todas las consultas son directas.
"""
from db.conexion import ejecutar
from ia.interprete import generar_reporte_empresa
from config import fecha_hora_str, hora_peru

# ══════════════════════════════════════════════════════════════
# ENTRADA PRINCIPAL — sin sesión, responde directo
# ══════════════════════════════════════════════════════════════

def consolidado_turno(empresa_id: int = None,
                      turno: str = None,
                      fecha: str = None) -> str:
    """
    Reporte consolidado de todas las empresas (o una específica)
    para el turno y fecha dados.
    Default: turno actual inferido por hora Perú, fecha hoy.
    """
    hoy   = hora_peru()
    fecha = fecha or hoy.strftime("%Y-%m-%d")
    if not turno:
        turno = "NOCHE" if hoy.hour < 10 or hoy.hour >= 20 else "DIA"

    # Obtener empresas activas
    if empresa_id:
        empresas = ejecutar(
            "SELECT id, nombre, codigo FROM cat_empresas WHERE id = %s",
            (empresa_id,), fetchall=True
        ) or []
    else:
        empresas = ejecutar(
            """SELECT id, nombre, codigo FROM cat_empresas
               WHERE tipo = 'CONTRATISTA' ORDER BY codigo""",
            fetchall=True
        ) or []

    if not empresas:
        return "⚠️ No hay empresas contratistas registradas."

    bloques = []
    total_metros = 0.0
    total_maquinas = 0
    total_reportaron = 0

    for emp in empresas:
        eid, enombre, ecodigo = emp

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
            (eid, fecha, turno), fetchall=True
        ) or []

        maquinas_empresa = ejecutar(
            """SELECT codigo FROM cat_maquinas
               WHERE empresa_id = %s AND activo = TRUE""",
            (eid,), fetchall=True
        ) or []

        n_total = len(maquinas_empresa)
        total_maquinas += n_total

        if not rows and not maquinas_empresa:
            continue

        reportes = [{
            "prof_inicio":   float(r[0] or 0),
            "prof_final":    float(r[1] or 0),
            "avance":        float(r[2] or 0),
            "observaciones": r[3] or "",
            "maquina_cod":   r[4],
            "bhid":          r[5],
            "sondaje_nivel": r[6],
            "sondaje_labor": r[7],
            "diametro":      r[8],
            "prog_m":        r[9],
            "turno":         turno,
            "fecha":         fecha,
        } for r in rows]

        maquinas_reportaron = {r["maquina_cod"] for r in reportes}
        sin_reporte = [
            m[0] for m in maquinas_empresa
            if m[0] not in maquinas_reportaron
        ]

        metros_emp = sum(r["avance"] for r in reportes)
        total_metros    += metros_emp
        total_reportaron += len(reportes)

        consolidado = generar_reporte_empresa(
            reportes, enombre, fecha,
            maquinas_sin_reporte=sin_reporte
        )
        bloques.append(consolidado)

    if not bloques:
        return (
            f"📭 Sin reportes de perforación para el turno *{turno}* "
            f"del *{_fmt_fecha(fecha)}*.\n\n"
            f"Usa *Gestión Perforación* → Consolidado después de registrar."
        )

    encabezado = (
        f"💎 *CONSOLIDADO PERFORACIÓN DIAMANTINA*\n"
        f"⏱️ Turno: *{turno}* | 📅 {_fmt_fecha(fecha)}\n"
        f"{'━'*30}\n"
    )
    pie = (
        f"\n{'━'*30}\n"
        f"🏁 *RESUMEN GENERAL*\n"
        f"   ➡️ Total: *{total_metros:.2f} m*\n"
        f"   🚜 Máquinas: {total_reportaron}/{total_maquinas}\n"
        f"📅 {fecha_hora_str()}"
    )

    return encabezado + "\n\n".join(bloques) + pie


def sondajes_activos_perf() -> str:
    """Lista de sondajes EN_CURSO con último reporte registrado."""
    rows = ejecutar(
        """SELECT s.bhid,
                  m.codigo        AS maquina,
                  e.codigo        AS empresa,
                  COALESCE(s.tajo_objetivo, s.cuerpo_objetivo, '—') AS objetivo,
                  s.profundidad_prog                                  AS prog_m,
                  COALESCE(s.profundidad_final, 0)                    AS final_m,
                  s.diametro,
                  s.nivel_prog,
                  s.labor,
                  MAX(ap.fecha)   AS ultimo_reporte
           FROM sondajes s
           JOIN cat_maquinas m ON s.maquina_id = m.id
           JOIN cat_empresas e ON s.empresa_id = e.id
           LEFT JOIN avance_perforacion ap
                  ON ap.sondaje_id = s.id AND ap.estado = 'ACTIVO'
           WHERE s.estado_perforacion = 'EN_CURSO'
           GROUP BY s.bhid, m.codigo, e.codigo, s.tajo_objetivo,
                    s.cuerpo_objetivo, s.profundidad_prog,
                    s.profundidad_final, s.diametro,
                    s.nivel_prog, s.labor
           ORDER BY e.codigo, m.codigo""",
        fetchall=True
    ) or []

    if not rows:
        return "📭 No hay sondajes en perforación actualmente."

    total      = len(rows)
    metros_tot = sum(float(r[5] or 0) for r in rows)
    empresa_actual = ""
    lineas = [
        f"💎 *SONDAJES EN PERFORACIÓN*\n{'━'*30}",
        f"Total activos: *{total}* | Metros acum: *{metros_tot:,.1f} m*",
        f"{'━'*30}",
    ]

    for r in rows:
        bhid, maq, emp, obj, prog, final, diam, nivel, labor, ult_rep = r
        if emp != empresa_actual:
            empresa_actual = emp
            lineas.append(f"\n🏢 *{emp}*")

        prog_f  = float(prog  or 0)
        final_f = float(final or 0)
        pct     = f"{final_f/prog_f*100:.0f}%" if prog_f > 0 else "—"

        try:
            from datetime import datetime
            ult_str = ult_rep.strftime("%d/%m") if ult_rep else "sin reporte"
        except:
            ult_str = str(ult_rep)[:5] if ult_rep else "sin reporte"

        lineas.append(
            f"  🔖 *{bhid}* → {obj}\n"
            f"     {maq} | Nv.{nivel or '—'} {labor or '—'} | {diam or '—'}\n"
            f"     {final_f:.1f}/{prog_f:.0f}m ({pct}) | {ult_str}"
        )

    lineas.append(f"\n{'━'*30}\n📅 {fecha_hora_str()}")
    return "\n".join(lineas)


def metricas_turno(turno: str = None, fecha: str = None) -> str:
    """
    Métricas del turno actual: metros por empresa
    y comparativo con el turno anterior.
    """
    hoy   = hora_peru()
    fecha = fecha or hoy.strftime("%Y-%m-%d")
    if not turno:
        turno = "NOCHE" if hoy.hour < 10 or hoy.hour >= 20 else "DIA"

    turno_ant = "NOCHE" if turno == "DIA" else "DIA"

    rows = ejecutar(
        """SELECT e.codigo, e.nombre,
                  COUNT(ap.id)              AS n_maquinas,
                  SUM(ap.prof_final - ap.prof_inicio) AS metros
           FROM avance_perforacion ap
           JOIN cat_maquinas m ON ap.maquina_id = m.id
           JOIN cat_empresas e ON m.empresa_id  = e.id
           WHERE ap.fecha = %s AND ap.turno = %s
             AND ap.estado = 'ACTIVO'
           GROUP BY e.codigo, e.nombre
           ORDER BY e.codigo""",
        (fecha, turno), fetchall=True
    ) or []

    rows_ant = ejecutar(
        """SELECT e.codigo,
                  SUM(ap.prof_final - ap.prof_inicio) AS metros
           FROM avance_perforacion ap
           JOIN cat_maquinas m ON ap.maquina_id = m.id
           JOIN cat_empresas e ON m.empresa_id  = e.id
           WHERE ap.fecha = %s AND ap.turno = %s
             AND ap.estado = 'ACTIVO'
           GROUP BY e.codigo""",
        (fecha, turno_ant), fetchall=True
    ) or []

    ant_dict = {r[0]: float(r[1] or 0) for r in rows_ant}

    if not rows:
        return (
            f"📭 Sin reportes para turno *{turno}* del *{_fmt_fecha(fecha)}*."
        )

    total_actual = sum(float(r[3] or 0) for r in rows)
    total_ant    = sum(ant_dict.values())

    lineas = [
        f"💎 *MÉTRICAS — TURNO {turno}*",
        f"📅 {_fmt_fecha(fecha)}",
        f"{'━'*30}",
    ]

    for r in rows:
        ecodigo, enombre, n_maq, metros = r
        metros_f = float(metros or 0)
        metros_a = ant_dict.get(ecodigo, 0)
        diff     = metros_f - metros_a
        diff_str = f"+{diff:.1f}m vs {turno_ant}" if diff >= 0 \
                   else f"{diff:.1f}m vs {turno_ant}"
        lineas.append(
            f"\n🏢 *{enombre}*\n"
            f"   ➡️ +{metros_f:.2f} m | 🚜 {n_maq} máquina(s)\n"
            f"   📊 {diff_str}"
        )

    diff_total = total_actual - total_ant
    diff_total_str = f"+{diff_total:.1f}m" if diff_total >= 0 \
                     else f"{diff_total:.1f}m"

    lineas.append(f"\n{'━'*30}")
    lineas.append(
        f"🏁 *TOTAL: +{total_actual:.2f} m*\n"
        f"   vs turno {turno_ant}: {diff_total_str}\n"
        f"📅 {fecha_hora_str()}"
    )
    return "\n".join(lineas)


# ══════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════

def _fmt_fecha(fecha: str) -> str:
    try:
        from datetime import datetime
        return datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return fecha
