"""
ROUTER PRINCIPAL DEL BOT
Recibe el mensaje, detecta intención y deriva al módulo correcto.
Gestiona sesiones activas y menús por rol.
"""
from db.usuarios import obtener_usuario, actualizar_ultimo_acceso
from db.sesiones import obtener_sesion, crear_sesion, cerrar_sesion
from ia.interprete import interpretar_mensaje
from config import fecha_hora_str, FLUJOS

import modulos.matricula    as mod_matricula
import modulos.perforacion  as mod_perforacion
import modulos.sgs          as mod_sgs
import modulos.certimin     as mod_certimin
import modulos.gerencia     as mod_gerencia

# Roles que pueden matricular sondajes
ROLES_MATRICULA   = {"GEOLOGO", "ADMIN"}
# Roles que reportan perforación
ROLES_PERFORACION = {"PERFORISTA", "ADMIN"}
# Roles SGS
ROLES_SGS         = {"SGS", "ADMIN"}
# Roles Certimin
ROLES_CERTIMIN    = {"CERTIMIN", "ADMIN"}
# Roles modelamiento
ROLES_MODELADO    = {"MODELADOR", "GEOLOGO", "ADMIN"}
# Todos pueden consultar
ROLES_CONSULTA    = {"GEOLOGO","PERFORISTA","SGS","CERTIMIN",
                      "MODELADOR","GERENCIA","ADMIN"}


def procesar(mensaje: str, remitente: str, foto_url: str = None) -> str:
    """
    Punto de entrada principal del bot.
    Retorna el texto de respuesta para WhatsApp.
    """
    # ── 1. Identificar usuario ────────────────────────────────
    usuario = obtener_usuario(remitente)
    if not usuario:
        return (
            "⛔ Tu número no está registrado en el sistema Cerro Lindo.\n\n"
            "Contacta al administrador para que te registre."
        )

    actualizar_ultimo_acceso(usuario["id"])

    # Si viene foto, convertirla en mensaje especial
    if foto_url:
        mensaje = f"FOTO:{foto_url}"

    msg_limpio = mensaje.strip()

    # ── 2. Comandos globales siempre disponibles ──────────────
    if msg_limpio.lower() in ("cancelar", "cancel", "salir", "exit", "menu", "menú"):
        cerrar_sesion(usuario["id"])
        return _menu_rol(usuario)

    if msg_limpio.lower() in ("hola", "inicio", "start", "hi", "ayuda", "help", "opciones"):
        cerrar_sesion(usuario["id"])
        return _menu_rol(usuario)

    # ── 3. Sesión activa → continuar flujo ───────────────────
    sesion = obtener_sesion(usuario["id"])
    if sesion:
        return _continuar_flujo(msg_limpio, usuario, sesion, foto_url)

    # ── 4. Sin sesión → interpretar con IA ───────────────────
    intent = interpretar_mensaje(msg_limpio, usuario)
    accion = intent.get("intencion", "desconocido")

    return _despachar_intencion(accion, intent, msg_limpio, usuario)


def _despachar_intencion(accion: str, intent: dict,
                          mensaje: str, usuario: dict) -> str:
    rol = usuario["rol"]

    # ── MENÚ ─────────────────────────────────────────────────
    if accion == "menu":
        return _menu_rol(usuario)

    # ── MATRICULA ────────────────────────────────────────────
    if accion == "matricula":
        if rol not in ROLES_MATRICULA:
            return "⛔ Solo los geólogos de Nexa pueden matricular sondajes."
        sid = crear_sesion(usuario["id"], FLUJOS["MATRICULA"])
        return mod_matricula.iniciar(usuario, sid)

    # ── PERFORACIÓN ──────────────────────────────────────────
    if accion == "perforacion":
        if rol not in ROLES_PERFORACION:
            return "⛔ Este flujo es solo para perforistas."
        sid = crear_sesion(usuario["id"], FLUJOS["PERFORACION"])
        return mod_perforacion.iniciar(usuario, sid)

    # ── SGS ───────────────────────────────────────────────────
    if accion == "sgs":
        if rol not in ROLES_SGS:
            return "⛔ Este flujo es solo para técnicos SGS."
        sid = crear_sesion(usuario["id"], FLUJOS["SGS"])
        return mod_sgs.iniciar(usuario, sid)

    # ── CERTIMIN ─────────────────────────────────────────────
    if accion == "certimin":
        if rol not in ROLES_CERTIMIN:
            return "⛔ Este flujo es solo para Certimin."
        sid = crear_sesion(usuario["id"], FLUJOS["CERTIMIN"])
        return mod_certimin.iniciar(usuario, sid)

    # ── CONSULTA DDH ─────────────────────────────────────────
    if accion == "consulta_ddh":
        bhid = intent.get("bhid") or mensaje
        return mod_gerencia.consultar_ddh(bhid, usuario)

    # ── CONSULTA TAJO ────────────────────────────────────────
    if accion == "consulta_tajo":
        tajo = intent.get("tajo") or mensaje
        if rol not in {"GERENCIA", "GEOLOGO", "ADMIN"}:
            return "⛔ Consulta de tajos disponible solo para gerencia y geólogos."
        return mod_gerencia.consultar_tajo(tajo, usuario)

    # ── CONSULTA OBJETIVO ────────────────────────────────────
    if accion == "consulta_objetivo":
        objetivo = intent.get("objetivo") or intent.get("tajo") or mensaje
        return mod_gerencia.consultar_objetivo(objetivo, usuario)

    # ── RESUMEN GENERAL ──────────────────────────────────────
    if accion == "resumen":
        if rol not in {"GERENCIA", "GEOLOGO", "ADMIN"}:
            return "⛔ El resumen general es solo para gerencia y geólogos."
        return mod_gerencia.resumen_general(usuario)

    # ── DESCARGA EXCEL ───────────────────────────────────────
    if accion == "descarga":
        if rol not in {"GERENCIA", "GEOLOGO", "ADMIN"}:
            return "⛔ La descarga de reportes es solo para gerencia y geólogos."
        return _menu_descarga(usuario)


    if accion == "consulta_foto":
        bhid = intent.get("bhid") or mensaje
        return mod_gerencia.consultar_foto(bhid, usuario)

                            
    # ── DESCONOCIDO → IA libre ────────────────────────────────
    respuesta_libre = intent.get("respuesta_libre", "")
    if respuesta_libre:
        return respuesta_libre

    return (
        "🤔 No entendí tu mensaje.\n\n"
        "Escribe *hola* para ver el menú de opciones."
    )

def _continuar_flujo(mensaje: str, usuario: dict, sesion: dict,
                     foto_url: str = None) -> str:
    flujo = sesion.get("flujo")

    if flujo == FLUJOS["MATRICULA"]:
        return mod_matricula.procesar(mensaje, usuario, sesion)

    if flujo == FLUJOS["PERFORACION"]:
        return mod_perforacion.procesar(mensaje, usuario, sesion, foto_url)

    if flujo == FLUJOS["SGS"]:
        return mod_sgs.procesar(mensaje, usuario, sesion)

    if flujo == FLUJOS["CERTIMIN"]:
        return mod_certimin.procesar(mensaje, usuario, sesion)

    if flujo == FLUJOS["DESCARGA_EXCEL"]:
        return _procesar_descarga(mensaje, usuario, sesion)

    if flujo == "9":  # Selección de foto
        return mod_gerencia.consultar_foto(mensaje, usuario, sesion)

    cerrar_sesion(usuario["id"])
    return _menu_rol(usuario)


def _menu_rol(usuario: dict) -> str:
    nombre = usuario["nombre"]
    rol    = usuario["rol"]
    hora   = fecha_hora_str()

    menus = {
        "GEOLOGO": (
            f"👋 Hola *{nombre}*\n📅 {hora}\n\n"
            f"*Panel Geólogo:*\n\n"
            f"1️⃣ *matricular* → Nuevo sondaje DDH\n"
            f"2️⃣ *perforación* → Reporte de avance\n"
            f"3️⃣ *logueo* → Reporte SGS\n"
            f"🔍 *estado 8422* → Estado de un DDH\n"
            f"📊 *resumen* → KPIs generales\n"
            f"📥 *descargar* → Exportar Excel\n"
        ),
        "PERFORISTA": (
            f"👋 Hola *{nombre}*\n📅 {hora}\n\n"
            f"*Panel Perforista:*\n\n"
            f"2️⃣ *perforación* → Reportar avance de turno\n"
            f"🔍 *estado 8422* → Consultar estado de un DDH\n\n"
            f"Escribe el número o la palabra clave."
        ),
        "SGS": (
            f"👋 Hola *{nombre}* (SGS)\n📅 {hora}\n\n"
            f"*Panel SGS:*\n\n"
            f"3️⃣ *logueo* → Reporte de logueo\n"
            f"3️⃣ *muestreo* → Reporte de muestreo\n"
            f"3️⃣ *RQD* → Reporte de RQD\n"
            f"3️⃣ *foto* → Reporte de fotografía\n"
            f"3️⃣ *densidad* → Reporte de densidad\n"
            f"🔍 *estado 8422* → Consultar DDH\n"
        ),
        "CERTIMIN": (
            f"👋 Hola *{nombre}* (Certimin)\n📅 {hora}\n\n"
            f"*Panel Certimin:*\n\n"
            f"4️⃣ *certimin* → Confirmar batch\n"
            f"🔍 *estado batch 7094* → Consultar batch\n"
        ),
        "GERENCIA": (
            f"👋 Hola *{nombre}*\n📅 {hora}\n\n"
            f"*Panel Gerencia:*\n\n"
            f"📊 *resumen* → KPIs generales\n"
            f"🔍 *tajo T-021* → Sondajes de un tajo\n"
            f"🔍 *estado 8422* → Estado de un DDH\n"
            f"🎯 *objetivo OB1* → DDH por cuerpo\n"
            f"📥 *descargar* → Exportar Excel\n\n"
            f"También puedes preguntar en lenguaje natural:\n"
            f"_¿Cuántos DDH se han perforado para el T-021?_"
        ),
        "MODELADOR": (
            f"👋 Hola *{nombre}*\n📅 {hora}\n\n"
            f"*Panel Modelador:*\n\n"
            f"🔍 *estado 8422* → Estado de un DDH\n"
            f"📊 *resumen* → KPIs generales\n"
        ),
        "ADMIN": (
            f"👋 Hola *{nombre}* (Admin)\n📅 {hora}\n\n"
            f"*Acceso completo:*\n\n"
            f"1️⃣ matricular | 2️⃣ perforación\n"
            f"3️⃣ SGS | 4️⃣ certimin\n"
            f"📊 resumen | 🔍 estado [DDH]\n"
            f"📥 descargar | 🎯 objetivo [X]\n"
        ),
    }
    return menus.get(rol, menus["GERENCIA"])


def _menu_descarga(usuario: dict) -> str:
    from db.sesiones import crear_sesion
    sid = crear_sesion(usuario["id"], FLUJOS["DESCARGA_EXCEL"])
    from db.sesiones import actualizar_sesion
    actualizar_sesion(sid, "tipo_reporte", {})
    return (
        f"📥 *DESCARGA DE REPORTES*\n\n"
        f"¿Qué reporte necesitas?\n\n"
        f"  *1* — Avance diario (mes actual)\n"
        f"  *2* — Estado de todos los sondajes\n"
        f"  *3* — Avance de un mes específico\n"
    )


def _procesar_descarga(mensaje: str, usuario: dict, sesion: dict) -> str:
    from db.sesiones import actualizar_sesion
    from reportes.exportar import generar_avance_diario, generar_estado_sondajes

    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    if paso == "tipo_reporte":
        if msg == "1":
            datos_excel = generar_avance_diario()
            cerrar_sesion(usuario["id"])
            if datos_excel:
                # Guardar temporalmente y dar URL de descarga
                return _entregar_excel(datos_excel,
                    f"Avance_Diario_{fecha_hora_str().replace('/','').replace(':','').replace(' ','_')}.xlsx",
                    usuario)
            return "⚠️ Error generando el Excel."

        elif msg == "2":
            datos_excel = generar_estado_sondajes()
            cerrar_sesion(usuario["id"])
            if datos_excel:
                return _entregar_excel(datos_excel, "Estado_Sondajes.xlsx", usuario)
            return "⚠️ Error generando el Excel."

        elif msg == "3":
            actualizar_sesion(sid, "mes_especifico", datos)
            return (
                "¿Qué mes? (número 1-12)\n"
                "Ejemplo: *5* para mayo\n"
            )
        else:
            return "❓ Responde *1*, *2* o *3*."

    elif paso == "mes_especifico":
        try:
            mes = int(msg)
            if mes < 1 or mes > 12:
                raise ValueError
        except:
            return "❓ Ingresa un número del 1 al 12."
        from config import hora_peru
        anio = hora_peru().year
        datos_excel = generar_avance_diario(mes, anio)
        cerrar_sesion(usuario["id"])
        if datos_excel:
            return _entregar_excel(datos_excel,
                f"Avance_Mes{mes:02d}_{anio}.xlsx", usuario)
        return "⚠️ Error generando el Excel."

    cerrar_sesion(usuario["id"])
    return "❓ Opción no válida."


def _entregar_excel(datos_bytes: bytes, nombre: str, usuario: dict) -> str:
    """
    Guarda el Excel en disco y retorna mensaje con instrucciones.
    En producción esto se puede conectar a un servicio de storage
    (S3, Google Drive) y enviar el link directo.
    """
    import os, base64
    try:
        ruta = f"/tmp/{nombre}"
        with open(ruta, "wb") as f:
            f.write(datos_bytes)
        # En Railway, el archivo se sirve via endpoint /descargar/<nombre>
        return (
            f"✅ *Excel generado*\n\n"
            f"📄 {nombre}\n\n"
            f"Descárgalo en:\n"
            f"https://TU_DOMINIO_RAILWAY.up.railway.app/descargar/{nombre}\n\n"
            f"_(El archivo estará disponible por 1 hora)_"
        )
    except Exception as e:
        print(f"[DESCARGA] Error: {e}")
        return "⚠️ Error generando el archivo."
