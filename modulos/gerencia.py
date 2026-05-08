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

def consultar_foto(texto: str, usuario: dict, sesion=None) -> str:
    from db.sondajes import buscar_sondaje
    from db.sesiones import crear_sesion, actualizar_sesion, cerrar_sesion

    # Si hay sesión activa de selección de foto
    if sesion and sesion.get("flujo") == "9" and sesion.get("paso") == "seleccion_foto":
        fotos = sesion["datos"].get("fotos", [])
        try:
            idx = int(texto.strip()) - 1
            if idx < 0 or idx >= len(fotos):
                return f"❓ Responde con un número del 1 al {len(fotos)}."
            url, tramo, fecha, turno, maq, bhid = fotos[idx]
            cerrar_sesion(usuario["id"])
            return {
                "tipo":    "imagen",
                "url":     url,
                "caption": f"📸 {bhid} | {maq} | Tramo {tramo} | {turno} {fecha}"
            }
        except:
            return "❓ Responde con un número válido."

    # Buscar sondaje
    sondaje = buscar_sondaje(texto)
    if not sondaje:
        return "❌ No encontré el sondaje. Ejemplo: *foto del 9999*"

    bhid = sondaje["bhid"]
    rows = ejecutar(
        """SELECT ap.foto_url, ap.foto_tramo, ap.fecha, ap.turno, m.codigo, s.bhid
           FROM avance_perforacion ap
           JOIN cat_maquinas m ON ap.maquina_id = m.id
           JOIN sondajes s ON ap.sondaje_id = s.id
           WHERE s.bhid = %s AND ap.foto_url IS NOT NULL
           ORDER BY ap.creado_en DESC""",
        (bhid,), fetchall=True
    )
    if not rows:
        return f"📸 No hay fotos registradas para *{bhid}*."

    if len(rows) == 1:
        url, tramo, fecha, turno, maq, bhid2 = rows[0]
        return {
            "tipo":    "imagen",
            "url":     url,
            "caption": f"📸 {bhid} | {maq} | Tramo {tramo} | {turno} {fecha}"
        }

    # Múltiples fotos — crear sesión para selección
    sid = crear_sesion(usuario["id"], "9")
    actualizar_sesion(sid, "seleccion_foto", {
        "fotos": [list(r) for r in rows[:5]]
    })

    lista = "\n".join([
        f"  {i+1}. {r[3]} {r[2]} — {r[4]} tramo {r[1]}"
        for i, r in enumerate(rows[:5])
    ])
    return (
        f"📸 *Fotos de {bhid}* ({len(rows)} registradas)\n\n"
        f"{lista}\n\n"
        f"¿Cuál quieres ver? Responde con el número."
    )
