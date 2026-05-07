import json
import anthropic
from config import ANTHROPIC_KEY, MODELO_IA

cliente = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def interpretar_mensaje(mensaje: str, usuario: dict) -> dict:
    """
    Interpreta el mensaje en lenguaje natural y retorna un dict con:
    - intencion: matricula | perforacion | sgs | certimin | modelado |
                 consulta_ddh | consulta_tajo | consulta_objetivo |
                 resumen | descarga | menu | desconocido
    - bhid: código DDH detectado (normalizado)
    - tajo: código de tajo (T-XXX)
    - objetivo: cuerpo/objetivo (OB1, EXT-OB1, etc.)
    - etapa_sgs: logueo | muestreo | rqd | fotografia | densidad
    - respuesta_libre: texto si intencion=desconocido
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

def generar_mensaje_estandarizado(datos_turno: dict) -> str:
    """
    Genera el mensaje estandarizado de reporte de turno para que
    el perforista pueda copiarlo y enviarlo a su grupo de WhatsApp.
    """
    system = """Eres un asistente de operaciones mineras.
Con los datos proporcionados, genera un reporte de turno de perforación
profesional y estandarizado en español, listo para enviar por WhatsApp.
Usa el mismo formato que usan las empresas contratistas en Cerro Lindo.
Incluye todos los campos. Sin texto adicional, solo el reporte."""

    prompt = f"Genera el reporte de turno con estos datos: {json.dumps(datos_turno, ensure_ascii=False, default=str)}"

    try:
        resp = cliente.messages.create(
            model=MODELO_IA,
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"[IA] Error generando reporte: {e}")
        return None

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
