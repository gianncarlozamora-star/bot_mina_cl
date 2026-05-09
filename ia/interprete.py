import json
import anthropic
from config import ANTHROPIC_KEY, MODELO_IA


def interpretar_mensaje(mensaje: str, usuario: dict) -> dict:
    """
    Interpreta el mensaje en lenguaje natural y retorna un dict con:
    - intencion, bhid, tajo, objetivo, etapa_sgs, respuesta_libre
    """
    system = f"""Eres el asistente de gestión minera de Cerro Lindo (Perú).
Analiza el mensaje y devuelve SOLO un JSON con esta estructura:
{{
  "intencion": "<ver opciones abajo>",
  "bhid": "<código DDH normalizado, ej: PECLD08422>",
  "tajo": "<código tajo, ej: T-008 o Tj.001>",
  "objetivo": "<cuerpo/objetivo, ej: OB1, EXT-OB1, OB1_01>",
  "etapa_sgs": "<logueo|muestreo|rqd|fotografia|densidad>",
  "respuesta_libre": "<respuesta corta en español solo si intencion=desconocido>"
}}

INTENCIONES VÁLIDAS:
- matricula      → quiere registrar/crear/matricular un nuevo sondaje DDH
- anular         → quiere anular, eliminar o borrar un sondaje
- perforacion    → reporte de avance de perforación, metros perforados, turno
- sgs            → logueo, muestreo, RQD, fotografía o densidad
- certimin       → envío o confirmación de batch de laboratorio
- modelado       → modelamiento o estimación de un DDH
- consulta_ddh   → pregunta por el estado de un DDH específico
- consulta_tajo  → pregunta por sondajes de un tajo (T-XXX)
- consulta_objetivo → pregunta por sondajes de un cuerpo/objetivo (OB1, etc.)
- consulta_foto  → quiere ver una foto registrada de un sondaje
- consulta_activos → pregunta por sondajes activos, en perforación, en curso, qué máquinas están perforando, objetivos en perforación, avance actual por máquina
- resumen          → pide resumen general, KPIs, totales de toda la campaña
- descarga       → quiere descargar Excel o reporte
- menu           → saludo, ayuda, menú, inicio, hola, opciones
- desconocido    → no encaja en ninguna categoría anterior

REGLAS DE NORMALIZACIÓN DE BHID:
- "8422", "el 8422", "pecld8422", "PECLD-08422" → "PECLD08422"
- Los últimos 4 dígitos son siempre confiables
- Si solo hay 4 dígitos, agregar prefijo PECLD0 → "PECLD08422"
- Errores de prefijo como "PELD", "PKCLD", "PECLDD" → corregir a "PECLD"

REGLAS DE NORMALIZACIÓN DE TAJO:
- "T008", "tajo 8", "t-008", "el T008" → "T-008"
- "tajo 695", "T695" → "T-695"

Usuario actual: {usuario.get('nombre','?')} | Rol: {usuario.get('rol','?')}

Devuelve SOLO el JSON sin texto adicional, sin backticks, sin explicaciones."""

    try:
        cliente = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = cliente.messages.create(
            model=MODELO_IA,
            max_tokens=300,
            system=system,
            messages=[{"role": "user", "content": mensaje}]
        )
        texto = resp.content[0].text.strip()
        texto = texto.replace("```json", "").replace("```", "").strip()
        return json.loads(texto)
    except Exception as e:
        print(f"[IA] Error interpretando: {e}")
        return {"intencion": "desconocido", "respuesta_libre": "No entendí el mensaje."}


def _fmt_fecha(fecha: str) -> str:
    """Convierte 2026-05-08 → 08/05/26"""
    try:
        from datetime import datetime
        return datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%y")
    except:
        return fecha


def _obs_relevante(obs: str) -> str | None:
    """Retorna None si la observación no es relevante."""
    if not obs:
        return None
    ignorar = ("ninguna", "nada", "sin novedad", "sin novedades",
               "ninguna novedad", "sin observacion", "sin observaciones",
               "ningua", "nada relevante", "todo bien", "normal",
               "sin nada", "ok", "bien")
    if obs.lower().strip() in ignorar:
        return None
    return obs.strip()


def generar_mensaje_estandarizado(datos: dict) -> str:
    """
    Genera reporte individual compacto para WhatsApp.
    Formato aprobado: sin costos, sin retorno de fluido,
    observaciones solo si son relevantes.
    """
    maquina  = datos.get("maquina_cod", "—")
    turno    = datos.get("turno", "—")
    fecha    = _fmt_fecha(datos.get("fecha", "—"))
    bhid     = datos.get("bhid", "—")
    nivel    = datos.get("sondaje_nivel", "—")
    labor    = datos.get("sondaje_labor", "—")
    desde    = float(datos.get("prof_inicio") or 0)
    hasta    = float(datos.get("prof_final") or 0)
    avance   = float(datos.get("avance") or 0)
    diametro = datos.get("diametro", "—")
    prog     = datos.get("prog_m", "—")
    objetivo = datos.get("tajo_objetivo") or datos.get("cuerpo_objetivo") or "—"
    obs      = _obs_relevante(datos.get("observaciones", ""))

    # Calcular porcentaje de avance total
    try:
        prog_f = float(prog)
        pct    = f" ({hasta/prog_f*100:.0f}%)" if prog_f > 0 else ""
    except:
        pct = ""

    # Cambio de línea
    cambio_str = ""
    if datos.get("hubo_cambio_linea"):
        cambio_str = (
            f"\n🔄 {datos.get('linea_anterior','—')} → "
            f"{datos.get('linea_nueva','—')} "
            f"en {datos.get('metro_cambio_linea',0):.1f}m"
        )

    # ¿Finalizó?
    fin_str = " ✅ FIN" if datos.get("posible_fin") else ""

    lineas = [
        f"⛏️ {maquina} | TURNO {turno} | {fecha}",
        f"📍 Nv.{nivel} {labor}",
        f"🔖 {bhid} → {objetivo} | {diametro} | Prog: {prog}m",
        f"📏 {desde:.2f} → {hasta:.2f} m | +{avance:.2f} m{pct}{fin_str}{cambio_str}",
    ]
    if obs:
        lineas.append(f"⚠️ {obs}")

    return "\n".join(lineas)


def generar_reporte_empresa(reportes: list, empresa: str, fecha: str,
                             maquinas_sin_reporte: list = None) -> str:
    """
    Genera reporte consolidado compacto por empresa.
    Formato aprobado: una línea por máquina con info esencial.
    """
    fecha_fmt    = _fmt_fecha(fecha)
    total_avance = sum(float(r.get("avance") or 0) for r in reportes)
    turno        = reportes[0].get("turno", "—") if reportes else "—"

    lineas = [
        f"🏢 {empresa.upper()} | {turno} | {fecha_fmt}",
        "─────────────────────",
    ]

    for r in reportes:
        maq      = r.get("maquina_cod", "—")
        bhid     = r.get("bhid", "—")
        nivel    = r.get("sondaje_nivel", "—")
        labor    = r.get("sondaje_labor", "—")
        diametro = r.get("diametro", "—")
        prog     = r.get("prog_m")
        desde    = float(r.get("prof_inicio") or 0)
        hasta    = float(r.get("prof_final") or 0)
        avance   = float(r.get("avance") or 0)
        obs      = _obs_relevante(r.get("observaciones", ""))
        fin_str  = " ✅ FIN" if r.get("es_fin") else ""

        # Porcentaje sobre programa
        try:
            pct = f" ({hasta/float(prog)*100:.0f}%)" if prog and float(prog) > 0 else ""
        except:
            pct = ""

        lineas.append(f"\n🚜 {maq} | {bhid}")
        lineas.append(f"   Nv.{nivel} {labor} | {diametro} | Prog: {prog}m")
        lineas.append(f"   {desde:.2f} → {hasta:.2f} m | +{avance:.2f} m{pct}{fin_str}")
        if obs:
            lineas.append(f"   ⚠️ {obs}")

    # Máquinas sin reporte
    if maquinas_sin_reporte:
        for maq in maquinas_sin_reporte:
            lineas.append(f"\n🚜 {maq} | sin reporte ⏳")

    lineas.append("\n─────────────────────")
    n_reportaron = len(reportes)
    n_total      = n_reportaron + len(maquinas_sin_reporte or [])
    lineas.append(
        f"➡️ TOTAL: {total_avance:.2f} m | "
        f"{n_reportaron}/{n_total} máquinas"
    )

    return "\n".join(lineas)


def responder_consulta_gerencia(pregunta: str, datos: dict) -> str:
    """Genera respuesta en lenguaje natural para consultas de gerencia."""
    system = """Eres el asistente de inteligencia de negocios de Cerro Lindo.
Responde en español de forma clara, concisa y profesional.
Usa los datos proporcionados para responder la pregunta del gerente.
Formatea los números con separadores de miles. Sin texto innecesario."""

    prompt = f"""Pregunta del gerente: {pregunta}

Datos disponibles:
{json.dumps(datos, ensure_ascii=False, default=str, indent=2)}

Responde de forma ejecutiva y directa."""

    try:
        cliente = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = cliente.messages.create(
            model=MODELO_IA,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"[IA] Error en consulta gerencia: {e}")
        return "Error procesando la consulta."
