"""
FLUJO DE CONSULTAS — Gerencia y cualquier rol
Consultas de estado DDH, tajo, objetivo, resumen general.
"""
from db.sondajes import (buscar_sondaje, sondajes_por_tajo,
                          sondajes_por_objetivo, resumen_campana)
from db.conexion import ejecutar
from ia.interprete import responder_consulta_gerencia
from config import fecha_hora_str

ICONOS = {
    "COMPLETADO":  "✅",
    "EN_PROCESO":  "🔄",
    "PENDIENTE":   "⏳",
    "NO_APLICA":   "➖",
    "OK":          "✅",
    "NP":          "➖",
    "GYRO":        "✅",
    "NO_REALIZADO":"❌",
}

def icono(estado: str) -> str:
    return ICONOS.get(str(estado).upper(), "❓")

# ── CONSULTA DDH INDIVIDUAL ───────────────────────────────────

def consultar_ddh(texto: str, usuario: dict) -> str:
    sondaje = buscar_sondaje(texto)
    if not sondaje:
        return (
            f"❌ No encontré el sondaje *{texto}*.\n\n"
            f"Verifica el código o los últimos 4 dígitos.\n"
        )
    s = sondaje
    avance_str = f"{s.get('avance_pct', 0):.1f}%" if s.get("avance_pct") else "—"
    return (
        f"🔍 *{s['bhid']}*\n"
        f"{'─'*30}\n"
        f"📂 {s.get('subcategoria','—')}\n"
        f"🎯 Objetivo: {s.get('tajo_objetivo') or s.get('cuerpo_objetivo','—')}\n"
        f"🏔️ Nivel: {s.get('nivel','—')} | Labor: {s.get('labor','—')}\n"
        f"🚜 {s.get('maquina','—')} ({s.get('empresa','—')})\n"
        f"📏 Prog: {s.get('prog_m','—')} m | Final: {s.get('final_m',0):.1f} m | {avance_str}\n"
        f"{'─'*30}\n"
        f"{icono(s['estado_logueo'])} Logueo\n"
        f"{icono(s['estado_muestreo'])} Muestreo\n"
        f"{icono(s['estado_rqd'])} RQD\n"
        f"{icono(s['estado_fotografia'])} Fotografía\n"
        f"{icono(s['estado_densidad'])} Densidad\n"
        f"{icono(s['estado_laboratorio'])} Laboratorio\n"
        f"{icono(s['estado_modelado'])} Modelado\n"
        f"{'─'*30}\n"
        f"📅 {fecha_hora_str()}"
    )

# ── CONSULTA POR TAJO ─────────────────────────────────────────

def consultar_tajo(tajo: str, usuario: dict) -> str:
    rows = sondajes_por_tajo(tajo)
    if not rows:
        return f"❌ No encontré sondajes para el tajo *{tajo}*."

    total       = len(rows)
    perforados  = sum(1 for r in rows if r[2] and float(r[2]) > 0)
    logueados   = sum(1 for r in rows if r[4] == "COMPLETADO")
    con_leyes   = sum(1 for r in rows if r[5] == "COMPLETADO")
    modelados   = sum(1 for r in rows if r[6] == "COMPLETADO")
    metros_tot  = sum(float(r[2] or 0) for r in rows)

    # Detalle de cada DDH
    detalle = ""
    for r in rows[:15]:  # máximo 15 en el mensaje
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

# ── CONSULTA POR OBJETIVO / CUERPO ────────────────────────────

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
        bar  = f"{float(avpct or 0):.0f}%"
        obj  = tajo or cuerpo or "—"
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

# ── RESUMEN GENERAL ───────────────────────────────────────────

def resumen_general(usuario: dict) -> str:
    datos = resumen_campana()
    if not datos:
        return "⚠️ Sin datos disponibles."

    total   = datos.get("total", 0)
    perf    = datos.get("perforados", 0)
    metros  = float(datos.get("metros_perforados", 0))
    mprog   = float(datos.get("metros_prog", 0))
    avpct   = (metros / mprog * 100) if mprog > 0 else 0
    log     = datos.get("logueados", 0)
    mues    = datos.get("muestreados", 0)
    leyes   = datos.get("con_leyes", 0)
    mod     = datos.get("modelados", 0)

    # Avance por campana
    campanas = ejecutar(
        """SELECT campana, COUNT(*), SUM(profundidad_final)
           FROM sondajes
           WHERE campana IS NOT NULL
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

# ── CONSULTA LIBRE (lenguaje natural via IA) ──────────────────

def consulta_libre_gerencia(pregunta: str, usuario: dict) -> str:
    """Para preguntas complejas que no encajan en los patrones anteriores."""
    datos = {
        "resumen_general": resumen_campana(),
    }
    return responder_consulta_gerencia(pregunta, datos)

# ── AGREGAR AL FINAL DE modulos/gerencia.py ──────────────────

def sondajes_en_curso(usuario: dict) -> str:
    """Lista de sondajes actualmente en perforación."""
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

def consultar_foto(texto: str, usuario: dict, sesion=None) -> str:
    from db.sondajes import buscar_sondaje
    from db.sesiones import crear_sesion, actualizar_sesion, cerrar_sesion

    # ── Selección de foto desde sesión activa ─────────────────
    if sesion and sesion.get("flujo") == "9" \
            and sesion.get("paso") == "seleccion_foto":
        fotos = sesion["datos"].get("fotos", [])
        try:
            idx = int(texto.strip()) - 1
            if idx < 0 or idx >= len(fotos):
                return f"❓ Responde con un número del 1 al {len(fotos)}."
            # fotos[i] = [url, tramo, fecha, fuente_label, tecnico, bhid, origen]
            foto         = fotos[idx]
            url          = foto[0]
            tramo        = foto[1]
            fecha        = foto[2]
            fuente_label = foto[3]
            tecnico      = foto[4]
            bhid         = foto[5]
            cerrar_sesion(usuario["id"])
            return {
                "tipo":    "imagen",
                "url":     url,
                "caption": (
                    f"📸 {bhid} | {fuente_label} | "
                    f"Tramo {tramo} | {fecha} | {tecnico}"
                )
            }
        except Exception as e:
            print(f"[GERENCIA] Error selección foto: {e}")
            return "❓ Responde con un número válido."

    # ── Buscar sondaje ────────────────────────────────────────
    sondaje = buscar_sondaje(texto)
    if not sondaje:
        return "❌ No encontré el sondaje. Ejemplo: *foto del 9999*"

    bhid = sondaje["bhid"]

    # ── Consulta unificada: perforación + SGS ─────────────────
    # 7 columnas: url, tramo, fecha, fuente_label, tecnico, bhid, origen
    rows = ejecutar(
        """
        SELECT
            ap.foto_url,
            COALESCE(ap.foto_tramo, '—'),
            ap.fecha::text,
            CONCAT('Perf. ', ap.turno, ' | ', m.codigo),
            COALESCE(u.nombre, 'Perforista'),
            s.bhid,
            'PERFORACION',
            ap.id
        FROM avance_perforacion ap
        JOIN sondajes      s ON ap.sondaje_id   = s.id
        JOIN cat_maquinas  m ON ap.maquina_id   = m.id
        LEFT JOIN usuarios_bot ub ON ap.reportado_por = ub.id
        WHERE s.bhid = %s AND ap.foto_url IS NOT NULL

        UNION ALL

        SELECT
            e.foto_url,
            CONCAT(
                ROUND(e.desde_m::numeric, 2)::text, '-',
                ROUND(e.hasta_m::numeric, 2)::text, 'm'
            ),
            e.fecha::text,
            CONCAT(e.etapa, ' | ', COALESCE(e.tecnico, '—')),
            COALESCE(ub.nombre, e.tecnico, 'SGS'),
            s.bhid,
            e.etapa,
            e.id
        FROM etapas_sgs    e
        JOIN sondajes      s  ON e.sondaje_id    = s.id
        LEFT JOIN usuarios_bot ub ON e.reportado_por = ub.id
        WHERE s.bhid = %s AND e.foto_url IS NOT NULL

        ORDER BY 8 DESC
        """,
        (bhid, bhid), fetchall=True
    )

    if not rows:
        return (
            f"📸 No hay fotos registradas para *{bhid}*.\n"
            f"_(Incluye fotos de perforación y SGS)_"
        )

    # Normalizar a lista serializable [url, tramo, fecha, fuente, tecnico, bhid, origen]
    fotos = [
        [r[0], r[1], r[2], r[3], r[4], r[5], r[6]]
        for r in rows[:10]
    ]

    # ── Una sola foto → enviar directo ────────────────────────
    if len(fotos) == 1:
        f = fotos[0]
        return {
            "tipo":    "imagen",
            "url":     f[0],
            "caption": f"📸 {f[5]} | {f[3]} | Tramo {f[1]} | {f[2]}"
        }

    # ── Varias fotos → menú interactivo ──────────────────────
    sid = crear_sesion(usuario["id"], "9")
    actualizar_sesion(sid, "seleccion_foto", {"fotos": fotos, "bhid": bhid})

    # menu_fotos espera: [(url, tramo, fecha, fuente_label, tecnico), ...]
    fotos_menu = [(f[0], f[1], f[2], f[3], f[4]) for f in fotos]

    return {
        "tipo":  "lista_fotos",
        "fotos": fotos_menu,
        "bhid":  bhid,
    }
