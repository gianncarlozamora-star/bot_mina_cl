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
- perforacion    → reporte de avance de perforación, metros perforados, turno
- sgs            → logueo, muestreo, RQD, fotografía o densidad
- certimin       → envío o confirmación de batch de laboratorio
- modelado       → modelamiento o estimación de un DDH
- consulta_ddh   → pregunta por el estado de un DDH específico
- consulta_tajo  → pregunta por sondajes de un tajo (T-XXX)
- consulta_objetivo → pregunta por sondajes de un cuerpo/objetivo (OB1, etc.)
- resumen        → pide resumen general, KPIs, totales
- descarga       → quiere descargar Excel o reporte
- menu           → saludo, ayuda, menú, inicio, hola, opciones
- desconocido    → no encaja en ninguna categoría anterior
- consulta_foto  → quiere ver una foto registrada de un sondaje

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


def generar_mensaje_estandarizado(datos: dict) -> str:
    """
    Genera el mensaje estandarizado de reporte de turno AGRUPADO POR EMPRESA
    para que el perforista pueda copiarlo y enviarlo a su grupo de WhatsApp.
    No incluye costos ni retorno de fluido.
    """
    # Determinar empresa para el encabezado
    maquina  = datos.get("maquina_cod", "—")
    turno    = datos.get("turno", "—")
    fecha    = datos.get("fecha", "—")
    bhid     = datos.get("bhid", "—")
    nivel    = datos.get("sondaje_nivel", "—")
    labor    = datos.get("sondaje_labor", "—")
    desde    = datos.get("prof_inicio", 0)
    hasta    = datos.get("prof_final", 0)
    avance   = datos.get("avance", 0)
    obs      = datos.get("observaciones", "") or "Sin novedades."
    diametro = datos.get("diametro", "—")
    prog     = datos.get("prog_m", "—")

    # Formato fecha legible
    try:
        from datetime import datetime
        fecha_fmt = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        fecha_fmt = fecha

    system = """Eres el asistente de operaciones mineras de Cerro Lindo.
Genera un reporte de turno de perforación profesional en español para WhatsApp.
El reporte NO debe incluir costos, valorización ni retorno de fluido.
Usa formato limpio con emojis moderados, similar a los reportes de Explomin y Explodrilling.
Agrupa la información claramente. Solo el reporte, sin texto adicional."""

    prompt = f"""Genera el reporte de turno con estos datos:
- Máquina: {maquina}
- Fecha: {fecha_fmt}
- Turno: {turno}
- Ubicación: Nivel {nivel} | {labor}
- Sondaje: {bhid}
- Línea: {diametro}
- Programación: {prog} m
- Prof. inicio: {desde:.2f} m
- Prof. final: {hasta:.2f} m
- Avance: {avance:.2f} m
- Observaciones: {obs}

IMPORTANTE: No incluyas costos, valorización ni retorno de fluido."""

    try:
        cliente = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = cliente.messages.create(
            model=MODELO_IA,
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"[IA] Error generando reporte: {e}")
        # Fallback manual sin IA
        return (
            f"📋 *Reporte {maquina} — Turno {turno}*\n"
            f"📅 Fecha: {fecha_fmt}\n"
            f"📍 Ubicación: Nv.{nivel} {labor}\n"
            f"🔖 Sondaje: {bhid}\n"
            f"💧 Línea: {diametro} | Prog: {prog} m\n"
            f"📏 Desde: {desde:.2f} m\n"
            f"📏 Hasta: {hasta:.2f} m\n"
            f"➡️ Avance: *{avance:.2f} m*\n"
            f"📝 Obs: {obs}"
        )


def generar_reporte_empresa(reportes: list, empresa: str, fecha: str) -> str:
    """
    Genera reporte consolidado de TODAS las máquinas de una empresa en un turno.
    reportes: lista de dicts con datos de cada máquina.
    """
    try:
        from datetime import datetime
        fecha_fmt = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        fecha_fmt = fecha

    total_avance = sum(r.get("avance", 0) for r in reportes)

    system = """Eres el asistente de operaciones mineras de Cerro Lindo.
Genera un reporte consolidado de turno para todas las máquinas de una empresa.
Formato WhatsApp, profesional, sin costos ni valorización.
Incluye un resumen al final con el avance total."""

    prompt = f"""Genera el reporte consolidado de {empresa} para el {fecha_fmt}.
Total avance del turno: {total_avance:.2f} m

Datos por máquina:
{json.dumps(reportes, ensure_ascii=False, default=str, indent=2)}

Sin costos. Sin retorno de fluido. Solo operaciones."""

    try:
        cliente = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = cliente.messages.create(
            model=MODELO_IA,
            max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"[IA] Error generando reporte empresa: {e}")
        # Fallback manual
        lineas = [f"📋 *Reporte {empresa} — {fecha_fmt}*\n"]
        for r in reportes:
            lineas.append(
                f"🚜 *{r.get('maquina_cod','—')}* | {r.get('bhid','—')}\n"
                f"   Turno {r.get('turno','—')} | "
                f"{r.get('prof_inicio',0):.1f}→{r.get('prof_final',0):.1f} m | "
                f"Avance: *{r.get('avance',0):.1f} m*\n"
                f"   📝 {r.get('observaciones','Sin novedades') or 'Sin novedades'}\n"
            )
        lineas.append(f"\n➡️ *Avance total: {total_avance:.2f} m*")
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
