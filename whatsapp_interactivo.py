"""
MENSAJES INTERACTIVOS DE WHATSAPP
Botones (hasta 3) y Listas (hasta 10 opciones).
"""
import requests
from config import ACCESS_TOKEN, WA_API_URL


def enviar_interactivo(telefono: str, payload: dict):
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type":  "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to":   telefono,
        "type": "interactive",
        **payload
    }
    try:
        r = requests.post(WA_API_URL, json=data, headers=headers, timeout=10)
        print(f"   WA interactivo: {r.status_code}")
        if r.status_code != 200:
            print(f"   WA error: {r.text}")
        return r.status_code == 200
    except Exception as e:
        print(f"❌ Error enviando interactivo: {e}")
        return False


def botones(telefono: str, cuerpo: str, opciones: list,
            encabezado: str = None, pie: str = None):
    opciones = opciones[:3]
    buttons  = [
        {"type": "reply", "reply": {
            "id":    f"btn_{i}_{op.lower()[:20].replace(' ','_')}",
            "title": op[:20]
        }}
        for i, op in enumerate(opciones)
    ]
    payload = {
        "interactive": {
            "type": "button",
            "body": {"text": cuerpo[:1024]},
            "action": {"buttons": buttons}
        }
    }
    if encabezado:
        payload["interactive"]["header"] = {
            "type": "text", "text": encabezado[:60]
        }
    if pie:
        payload["interactive"]["footer"] = {"text": pie[:60]}
    return enviar_interactivo(telefono, payload)


def lista(telefono: str, cuerpo: str, secciones: list,
          boton_texto: str = "Ver opciones",
          encabezado: str = None, pie: str = None):
    rows_total = sum(len(s.get("items", [])) for s in secciones)
    assert rows_total <= 10, "Máximo 10 items en lista"

    sections = []
    for sec in secciones:
        rows = [
            {
                "id":          item["id"][:200],
                "title":       item["titulo"][:24],
                "description": item.get("desc", "")[:72]
            }
            for item in sec.get("items", [])
        ]
        section = {"rows": rows}
        if sec.get("titulo"):
            section["title"] = sec["titulo"][:24]
        sections.append(section)

    payload = {
        "interactive": {
            "type": "list",
            "body": {"text": cuerpo[:1024]},
            "action": {
                "button":   boton_texto[:20],
                "sections": sections
            }
        }
    }
    if encabezado:
        payload["interactive"]["header"] = {
            "type": "text", "text": encabezado[:60]
        }
    if pie:
        payload["interactive"]["footer"] = {"text": pie[:60]}
    return enviar_interactivo(telefono, payload)


# ── HELPERS ESPECÍFICOS DEL SISTEMA ──────────────────────────

def menu_principal_rol(telefono: str, usuario: dict):
    """Menú principal según el rol del usuario."""
    rol    = usuario["rol"]
    nombre = usuario["nombre"]

    menus = {
        "GEOLOGO": {
            "cuerpo": f"Hola *{nombre}* 👷\n¿Qué deseas hacer?",
            "opciones_lista": [
                {"id": "matricula",   "titulo": "📋 Matricular DDH",    "desc": "Registrar nuevo sondaje"},
                {"id": "anular",      "titulo": "🗑️ Anular sondaje",    "desc": "Anular matricula DDH"},
                {"id": "perforacion", "titulo": "Perforacion Diamantina","desc": "Registrar avance turno"},
                {"id": "gestion_perf","titulo": "Gestion Perforacion",  "desc": "Consolidado y activos"},
                {"id": "sgs",         "titulo": "🔬 Reporte SGS",        "desc": "Logueo, muestreo, RQD"},
                {"id": "resumen",     "titulo": "📊 Resumen general",    "desc": "KPIs y avances"},
                {"id": "descarga",    "titulo": "📥 Descargar Excel",    "desc": "Exportar reportes"},
            ]
        },
        "PERFORISTA": {
            "cuerpo": f"Hola *{nombre}* ⛏️\n¿Qué deseas hacer?",
            "opciones_lista": [
                {"id": "perforacion", "titulo": "Perforacion Diamantina","desc": "Registrar avance"},
                {"id": "gestion_perf","titulo": "Ver consolidado",       "desc": "Estado del turno"},
                {"id": "consulta",    "titulo": "🔍 Consultar sondaje",  "desc": "Estado de un DDH"},
            ]
        },
        "SGS": {
            "cuerpo": f"Hola *{nombre}* 🔬\n¿Qué actividad reportas?",
            "opciones_lista": [
                {"id": "sgs_logueo",     "titulo": "📝 Logueo",          "desc": "Registro geológico"},
                {"id": "sgs_muestreo",   "titulo": "🧪 Muestreo",        "desc": "Toma de muestras"},
                {"id": "sgs_rqd",        "titulo": "📐 RQD",             "desc": "Calidad de roca"},
                {"id": "sgs_fotografia", "titulo": "📸 Fotografía",      "desc": "Fotos de testigos"},
                {"id": "sgs_densidad",   "titulo": "⚖️ Densidad",        "desc": "Control de densidad"},
                {"id": "anular_sgs",     "titulo": "🗑️ Anular registro", "desc": "Corregir un reporte SGS"},
            ]
        },
        "CERTIMIN": {
            "cuerpo": f"Hola *{nombre}* 🧪\n¿Qué deseas confirmar?",
            "opciones_lista": [
                {"id": "certimin", "titulo": "📦 Confirmar batch", "desc": "Recepción o resultados"},
            ]
        },
        "ADMIN": {
            "cuerpo": f"Hola *{nombre}* 🔧\n¿Qué deseas hacer?",
            "opciones_lista": [
                {"id": "matricula",   "titulo": "📋 Matricular DDH",    "desc": "Nuevo sondaje"},
                {"id": "anular",      "titulo": "🗑️ Anular sondaje",    "desc": "Anular matricula DDH"},
                {"id": "perforacion", "titulo": "Perforacion Diamantina","desc": "Registrar avance"},
                {"id": "gestion_perf","titulo": "Gestion Perforacion",  "desc": "Consolidado y activos"},
                {"id": "sgs",         "titulo": "🔬 Reporte SGS",        "desc": "Logueo, muestreo"},
                {"id": "certimin",    "titulo": "🧪 Certimin",           "desc": "Confirmar batch"},
                {"id": "resumen",     "titulo": "📊 Resumen general",    "desc": "KPIs y avances"},
                {"id": "descarga",    "titulo": "📥 Descargar Excel",    "desc": "Exportar reportes"},
            ]
        },
        "GERENCIA": {
            "cuerpo": f"Hola *{nombre}* 📊\n¿Qué deseas consultar?",
            "opciones_lista": [
                {"id": "resumen",   "titulo": "📊 Resumen general",  "desc": "KPIs y métricas"},
                {"id": "tajo",      "titulo": "🎯 Consultar tajo",   "desc": "DDH por tajo"},
                {"id": "objetivo",  "titulo": "🏔️ Consultar cuerpo", "desc": "DDH por objetivo"},
                {"id": "descarga",  "titulo": "📥 Descargar Excel",  "desc": "Exportar reportes"},
            ]
        },
    }

    cfg = menus.get(rol, menus["GERENCIA"])
    items = cfg["opciones_lista"]

    if len(items) <= 3:
        return botones(telefono, cfg["cuerpo"],
                       [i["titulo"] for i in items])
    else:
        return lista(telefono, cfg["cuerpo"],
                     [{"items": items}],
                     boton_texto="Ver opciones")


def menu_maquinas(telefono: str, maquinas: list,
                  texto: str = "¿Con qué máquina trabajas?"):
    from main import enviar_mensaje
    lineas = [f"*{texto}*\n"]
    for i, m in enumerate(maquinas):
        lineas.append(f"  *{i+1}* — {m['codigo']} ({m['empresa']})")
    lineas.append(f"\nResponde con el número.")
    enviar_mensaje(telefono, "\n".join(lineas))


def botones_turno(telefono: str, texto: str = "¿Qué turno reportas?"):
    return botones(telefono, texto, ["☀️ Día", "🌙 Noche"])


def botones_confirmar(telefono: str, texto: str, pie: str = None):
    from main import enviar_mensaje
    enviar_mensaje(telefono,
                   texto + "\n\n✅ Responde *sí* para confirmar o *no* para cancelar.")


def botones_si_no(telefono: str, texto: str):
    from main import enviar_mensaje
    enviar_mensaje(telefono, texto + "\n\nResponde *sí* o *no*.")


def botones_si_no_fin(telefono: str, texto: str):
    from main import enviar_mensaje
    enviar_mensaje(telefono,
                   texto + "\n\n  *sí* — Generar\n  *no* — Otra máquina\n  *fin* — Terminar")


def menu_tipo_sondaje(telefono: str):
    return lista(
        telefono,
        "¿Qué tipo de sondaje vas a registrar?",
        [{"items": [
            {"id": "tipo_INFILL",  "titulo": "INFILL",
             "desc": "Sondaje de relleno en tajo"},
            {"id": "tipo_IND_MED", "titulo": "INDICADO A MEDIDO",
             "desc": "Conversión de categoría"},
            {"id": "tipo_INF_IND", "titulo": "INFERIDO A INDICADO",
             "desc": "Conversión de categoría"},
            {"id": "tipo_POT_INF", "titulo": "POTENCIAL A INFERIDO",
             "desc": "Conversión de categoría"},
        ]}],
        boton_texto="Seleccionar tipo"
    )


def menu_diametro(telefono: str):
    return botones(telefono, "¿Qué diámetro de perforación?",
                   ["BQ", "NQ", "HQ"])


def menu_etapas_sgs(telefono: str):
    """
    Menú SGS con 7 opciones:
    - 5 etapas de reporte
    - Anular registro SGS
    - Registrar batch (para geólogos que usan SGS también)
    """
    return lista(
        telefono,
        "¿Qué actividad vas a reportar?",
        [
            {
                "titulo": "Reportar",
                "items": [
                    {"id": "sgs_LOGUEO",     "titulo": "📝 Logueo",
                     "desc": "Registro geológico"},
                    {"id": "sgs_MUESTREO",   "titulo": "🧪 Muestreo",
                     "desc": "Toma de muestras"},
                    {"id": "sgs_RQD",        "titulo": "📐 RQD",
                     "desc": "Calidad de roca"},
                    {"id": "sgs_FOTOGRAFIA", "titulo": "📸 Fotografía",
                     "desc": "Fotos de testigos"},
                    {"id": "sgs_DENSIDAD",   "titulo": "⚖️ Densidad",
                     "desc": "Control de densidad"},
                ]
            },
            {
                "titulo": "Gestión",
                "items": [
                    {"id": "anular_sgs",   "titulo": "🗑️ Anular registro",
                     "desc": "Corregir un reporte SGS"},
                    {"id": "batch",        "titulo": "📦 Registrar batch",
                     "desc": "Batch Fusion → laboratorio"},
                    {"id": "reporte_sgs",  "titulo": "📋 Reporte diario",
                     "desc": "Consolidado SGS del día"},
                ]
            }
        ],
        boton_texto="Seleccionar"
    )



def menu_gestion_perforacion(telefono: str):
    """Submenu de gestion de perforacion diamantina."""
    return lista(
        telefono,
        "Gestion Perforacion Diamantina",
        [{"items": [
            {"id": "gp_consolidado", "titulo": "Consolidado turno",
             "desc": "Reporte por empresa"},
            {"id": "gp_activos",    "titulo": "Sondajes activos",
             "desc": "En perforacion ahora"},
            {"id": "gp_metricas",   "titulo": "Metricas del turno",
             "desc": "Metros y comparativo"},
        ]}],
        boton_texto="Ver opciones"
    )


def menu_fotos(telefono: str, fotos: list, bhid: str):
    items = [
        {
            "id":     f"foto_{i}",
            "titulo": f"{r[3]} {str(r[2])[-5:]}",
            "desc":   f"{r[4]} | tramo {r[1]}"
        }
        for i, r in enumerate(fotos[:10])
    ]
    return lista(
        telefono,
        f"📸 *{bhid}* — {len(fotos)} foto(s) registradas\n¿Cuál quieres ver?",
        [{"items": items}],
        boton_texto="Ver fotos"
    )


def menu_descarga(telefono: str):
    return lista(
        telefono,
        "¿Qué reporte necesitas descargar?",
        [{"items": [
            {"id": "desc_avance", "titulo": "📊 Avance diario",
             "desc": "Mes actual en Excel"},
            {"id": "desc_estado", "titulo": "📋 Estado sondajes",
             "desc": "Todos los DDH"},
            {"id": "desc_mes",    "titulo": "📅 Mes específico",
             "desc": "Elige el mes"},
        ]}],
        boton_texto="Seleccionar reporte"
    )
