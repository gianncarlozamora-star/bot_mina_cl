import json
import anthropic
from config import ANTHROPIC_KEY, MODELO_IA


def interpretar_mensaje(mensaje: str, usuario: dict) -> dict:
    """
    Interpreta el mensaje en lenguaje natural y retorna un dict con:
    intencion, bhid, tajo, objetivo, etapa_sgs, periodo,
    numero_batch, etapa_pendiente, filtro_foto, respuesta_libre
    """
    system = f"""Eres el asistente de gestión minera de Cerro Lindo (Perú).
Analiza el mensaje y devuelve SOLO un JSON con esta estructura:
{{
  "intencion": "<ver opciones abajo>",
  "bhid": "<código DDH normalizado, ej: PECLD08422>",
  "tajo": "<código tajo, ej: T-008>",
  "objetivo": "<cuerpo/objetivo, ej: OB1, EXT-OB1>",
  "etapa_sgs": "<logueo|muestreo|rqd|fotografia|densidad>",
  "periodo": "<semana|mes|hoy|null>",
  "mes": <número 1-12 o null>,
  "numero_batch": "<número batch si mencionan uno, ej: 7094>",
  "etapa_pendiente": "<logueo|muestreo|modelado|estimacion|laboratorio|null>",
  "filtro_foto": "<perforacion|sgs|null>",
  "respuesta_libre": "<respuesta corta en español solo si intencion=desconocido>"
}}

INTENCIONES VÁLIDAS:
- matricula           → registrar/crear/matricular nuevo sondaje DDH
- anular              → anular/eliminar/borrar un SONDAJE (la matrícula del DDH)
- anular_sgs          → borrar o corregir registro SGS (logueo, muestreo, rqd, foto, densidad)
                        Frases: "borrar mi logueo", "anular muestreo", "corregir reporte sgs"
- anular_reporte      → anular último reporte de PERFORACIÓN (avance de metros)
- batch               → registrar nuevo batch Fusion para envío a laboratorio
- certimin            → Certimin confirma recepción o resultados de un batch
- perforacion         → reporte de avance de perforación, metros perforados, turno
- sgs                 → logueo, muestreo, RQD, fotografía o densidad
- modelamiento        → registrar modelamiento o estimación de sondajes
- reporte_sgs         → generar reporte consolidado diario SGS
                        Frases: "reporte sgs", "reporte diario", "consolidado sgs"

- consulta_ddh        → estado/historia completa de un DDH específico
                        Frases: "cómo está el 8422", "estado del 8422",
                        "historia del 8422", "qué pasó con el 8422",
                        "el 8422 ya fue logueado?", "a qué batch pertenece el 8422"
- consulta_tajo       → sondajes de un tajo (T-XXX)
- consulta_objetivo   → sondajes de un cuerpo/objetivo (OB1, EXT-OB1)
- consulta_foto       → ver foto de un sondaje
                        Frases: "foto del 8422", "foto de perforación del 8422",
                        "foto de logueo del 8422", "última foto del 8422"
                        → si dice "perforación" poner filtro_foto=perforacion
                        → si dice "logueo" o "sgs" poner filtro_foto=sgs
- consulta_batch      → estado de un batch específico
                        Frases: "estado del batch 7094", "el batch 7094 fue analizado",
                        "qué pasó con el batch 7094"
- consulta_activos    → sondajes activos en perforación, qué máquinas perforan
- consulta_semana     → metros perforados esta semana, avance semanal, costo semanal
                        Frases: "cuánto se perforó esta semana", "metros de la semana",
                        "costo de esta semana", "rendimiento semanal"
- consulta_mes        → metros perforados este mes o un mes específico
                        Frases: "cuánto se perforó este mes", "metros de mayo",
                        "costo del mes", "avance mensual", "cuánto va el mes"
                        → si menciona un mes específico poner campo mes (1-12)
- ranking_maquinas    → ranking productividad por máquina, cuál máquina perfora más,
                        máquina más productiva, comparar máquinas
                        Frases: "cuál máquina perfora más", "ranking de máquinas",
                        "qué máquina es la mejor"
- consulta_pendientes → qué falta, pendientes por etapa, atrasos, brechas
                        Frases: "qué falta loguear", "qué sondajes faltan modelar",
                        "qué está atrasado", "pendientes de muestreo",
                        "qué falta para completar", "cuánto falta"
                        → poner etapa_pendiente si se especifica una etapa
- consulta_logueo_activos  → sondajes con logueo en curso o pendiente de loguear
- consulta_finalizados     → sondajes finalizados este mes
- consulta_pendiente_logueo → sondajes sin completar el logueo
- resumen             → resumen general, KPIs, totales de campaña
- descarga            → descargar Excel o reporte
- gestion_perforacion → submenú gestión perforación (consolidado, activos, métricas)
- consolidado_turno   → consolidado de turno por empresa
- metricas_turno      → métricas del turno actual
- menu                → saludo, ayuda, menú, inicio, hola, opciones
- desconocido         → no encaja en ninguna categoría anterior

REGLAS DE NORMALIZACIÓN DE BHID:
- "8422", "el 8422", "pecld8422", "PECLD-08422" → "PECLD08422"
- Los últimos 4 dígitos son siempre confiables
- Si solo hay 4 dígitos, agregar prefijo PECLD0 → "PECLD08422"
- Errores de prefijo: "PELD", "PKCLD", "PECLDD" → corregir a "PECLD"
- Si el código tiene más de 4 dígitos al final usar los últimos 5

REGLAS DE NORMALIZACIÓN DE TAJO:
- "T008", "tajo 8", "t-008", "el T008" → "T-008"
- "tajo 695", "T695" → "T-695"

REGLAS DE PERÍODO:
- "esta semana", "semana", "últimos 7 días" → periodo=semana
- "este mes", "el mes", "lo que va del mes" → periodo=mes, mes=null
- "en mayo", "del mes de mayo", "mayo" → periodo=mes, mes=5
- "hoy", "de hoy" → periodo=hoy

REGLAS ESPECIALES:
- Si preguntan por historia/trazabilidad completa de un DDH → consulta_ddh
- Si preguntan por batch de un sondaje → consulta_ddh (bhid presente)
- Si preguntan por estado de un batch específico → consulta_batch (numero_batch presente)
- Si preguntan por fotos → consulta_foto, detectar filtro_foto
- Si preguntan qué falta/pendiente con etapa específica → consulta_pendientes + etapa_pendiente
- "modelamiento" o "estimar" sin DDH específico → modelamiento (flujo de registro)
- "modelamiento" o "estimación" con DDH → consulta_ddh

Usuario actual: {usuario.get('nombre','?')} | Rol: {usuario.get('rol','?')}

Devuelve SOLO el JSON sin texto adicional, sin backticks, sin explicaciones."""

    try:
        cliente = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = cliente.messages.create(
            model=MODELO_IA,
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": mensaje}]
        )
        texto = resp.content[0].text.strip()
        texto = texto.replace("```json", "").replace("```", "").strip()
        return json.loads(texto)
    except Exception as e:
        print(f"[IA] Error interpretando: {e}")
        return {"intencion": "desconocido",
                "respuesta_libre": "No entendí el mensaje."}


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

    try:
        prog_f = float(prog)
        pct    = f" ({hasta/prog_f*100:.0f}%)" if prog_f > 0 else ""
    except:
        pct = ""

    cambio_str = ""
    if datos.get("hubo_cambio_linea"):
        cambio_str = (
            f"\n🔄 {datos.get('linea_anterior','—')} → "
            f"{datos.get('linea_nueva','—')} "
            f"en {datos.get('metro_cambio_linea',0):.1f}m"
        )

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

        try:
            pct = f" ({hasta/float(prog)*100:.0f}%)" if prog and float(prog) > 0 else ""
        except:
            pct = ""

        lineas.append(f"\n🚜 {maq} | {bhid}")
        lineas.append(f"   Nv.{nivel} {labor} | {diametro} | Prog: {prog}m")
        lineas.append(f"   {desde:.2f} → {hasta:.2f} m | +{avance:.2f} m{pct}{fin_str}")
        if obs:
            lineas.append(f"   ⚠️ {obs}")

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
    """Genera respuesta en lenguaje natural para consultas complejas."""
    system = """Eres el asistente de inteligencia de negocios de Cerro Lindo.
Responde en español de forma clara, concisa y profesional.
Usa los datos proporcionados para responder la pregunta.
Formatea los números con separadores de miles. Sin texto innecesario."""

    prompt = f"""Pregunta: {pregunta}

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
