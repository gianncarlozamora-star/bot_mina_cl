"""
ROUTER PRINCIPAL DEL BOT
Recibe mensaje, detecta intención y deriva al módulo correcto.
Usa mensajes interactivos (botones/listas) cuando es posible.
"""
from db.usuarios import obtener_usuario, actualizar_ultimo_acceso
from db.sesiones import obtener_sesion, crear_sesion, cerrar_sesion
from ia.interprete import interpretar_mensaje
from config import fecha_hora_str, FLUJOS
from whatsapp_interactivo import (
    menu_principal_rol, menu_maquinas, botones_turno,
    botones_confirmar, botones_si_no, botones_si_no_fin,
    menu_tipo_sondaje, menu_diametro, menu_etapas_sgs,
    menu_fotos, menu_descarga, botones, lista
)

import modulos.matricula    as mod_matricula
import modulos.perforacion  as mod_perforacion
import modulos.sgs          as mod_sgs
import modulos.certimin     as mod_certimin
import modulos.gerencia     as mod_gerencia

ROLES_MATRICULA   = {"GEOLOGO", "ADMIN"}
ROLES_PERFORACION = {"PERFORISTA", "ADMIN"}
ROLES_SGS         = {"SGS", "ADMIN"}
ROLES_CERTIMIN    = {"CERTIMIN", "ADMIN"}


def procesar(mensaje: str, remitente: str, foto_url: str = None) -> str:
    usuario = obtener_usuario(remitente)
    if not usuario:
        return (
            "⛔ Tu número no está registrado en el sistema Cerro Lindo.\n\n"
            "Contacta al administrador para que te registre."
        )

    actualizar_ultimo_acceso(usuario["id"])

    msg_limpio = mensaje.strip()

    # ── Comandos globales ─────────────────────────────────────
    if msg_limpio.lower() in ("cancelar", "cancel", "salir", "exit",
                               "menu", "menú", "hola", "inicio",
                               "start", "hi", "ayuda", "help", "opciones"):
        cerrar_sesion(usuario["id"])
        menu_principal_rol(remitente, usuario)
        return {"tipo": "interactivo"}

    # ── Sesión activa → continuar flujo ───────────────────────
    sesion = obtener_sesion(usuario["id"])
    if sesion:
        return _continuar_flujo(msg_limpio, remitente, usuario,
                                sesion, foto_url)

    # ── Sin sesión → interpretar con IA ──────────────────────
    intent = interpretar_mensaje(msg_limpio, usuario)
    accion = intent.get("intencion", "desconocido")

    return _despachar_intencion(accion, intent, msg_limpio, remitente, usuario)


def _despachar_intencion(accion, intent, mensaje, remitente, usuario):
    rol = usuario["rol"]

    if accion == "menu":
        menu_principal_rol(remitente, usuario)
        return {"tipo": "interactivo"}

    if accion == "matricula":
        if rol not in ROLES_MATRICULA:
            return "⛔ Solo los geólogos de Nexa pueden matricular sondajes."
        sid = crear_sesion(usuario["id"], FLUJOS["MATRICULA"])
        menu_tipo_sondaje(remitente)
        from db.sondajes import obtener_subcategorias_activas
        subcat = obtener_subcategorias_activas()
        from db.sesiones import actualizar_sesion
        actualizar_sesion(sid, "tipo_sondaje",
                          {"subcat_opciones": [s["codigo"] for s in subcat],
                           "subcat_ids":      [s["id"]     for s in subcat],
                           "subcat_nombres":  [s["nombre"] for s in subcat]})
        return {"tipo": "interactivo"}

    if accion == "anular":
        if rol not in ROLES_MATRICULA:
            return "⛔ Solo geólogos y admin pueden anular sondajes."
        sid = crear_sesion(usuario["id"], FLUJOS["MATRICULA"])
        return mod_matricula.iniciar_anulacion(usuario, sid)

    if accion == "perforacion":
        if rol not in ROLES_PERFORACION:
            return "⛔ Este flujo es solo para perforistas."
        sid = crear_sesion(usuario["id"], FLUJOS["PERFORACION"])
        from db.usuarios import obtener_maquinas_activas
        maquinas = obtener_maquinas_activas()
        menu_maquinas(remitente, maquinas)
        from db.sesiones import actualizar_sesion
        actualizar_sesion(sid, "maquina",
                          {"maquina_opciones": [(m["id"], m["codigo"],
                                                 m["empresa"]) for m in maquinas]})
        return {"tipo": "interactivo"}

    if accion == "sgs":
        if rol not in ROLES_SGS:
            return "⛔ Este flujo es solo para técnicos SGS."
        sid = crear_sesion(usuario["id"], FLUJOS["SGS"])
        menu_etapas_sgs(remitente)
        from db.sesiones import actualizar_sesion
        actualizar_sesion(sid, "tipo_etapa", {})
        return {"tipo": "interactivo"}

    if accion == "certimin":
        if rol not in ROLES_CERTIMIN:
            return "⛔ Este flujo es solo para Certimin."
        sid = crear_sesion(usuario["id"], FLUJOS["CERTIMIN"])
        return mod_certimin.iniciar(usuario, sid)

    if accion == "consulta_ddh":
        bhid = intent.get("bhid") or mensaje
        return mod_gerencia.consultar_ddh(bhid, usuario)

    if accion == "consulta_tajo":
        tajo = intent.get("tajo") or mensaje
        return mod_gerencia.consultar_tajo(tajo, usuario)

    if accion == "consulta_objetivo":
        objetivo = intent.get("objetivo") or mensaje
        return mod_gerencia.consultar_objetivo(objetivo, usuario)

    if accion == "consulta_foto":
        bhid = intent.get("bhid") or mensaje
        resultado = mod_gerencia.consultar_foto(bhid, usuario)
        if isinstance(resultado, dict) and resultado.get("tipo") == "lista_fotos":
            menu_fotos(remitente, resultado["fotos"], resultado["bhid"])
            return {"tipo": "interactivo"}
        return resultado

    if accion == "resumen":
        if rol not in {"GERENCIA", "GEOLOGO", "ADMIN"}:
            return "⛔ El resumen es solo para gerencia y geólogos."
        return mod_gerencia.resumen_general(usuario)

    if accion == "anular_sondaje" or (accion == "desconocido" and
            any(w in mensaje.lower() for w in ("anular","eliminar","borrar","cancelar sondaje"))):
        if rol not in ROLES_MATRICULA:
            return "⛔ Solo geólogos y admin pueden anular sondajes."
        sid = crear_sesion(usuario["id"], FLUJOS["MATRICULA"])
        return mod_matricula.iniciar_anulacion(usuario, sid)

    if accion == "descarga":
        if rol not in {"GERENCIA", "GEOLOGO", "ADMIN"}:
            return "⛔ La descarga es solo para gerencia y geólogos."
        menu_descarga(remitente)
        sid = crear_sesion(usuario["id"], FLUJOS["DESCARGA_EXCEL"])
        from db.sesiones import actualizar_sesion
        actualizar_sesion(sid, "tipo_reporte", {})
        return {"tipo": "interactivo"}

    respuesta_libre = intent.get("respuesta_libre", "")
    if respuesta_libre:
        return respuesta_libre

    menu_principal_rol(remitente, usuario)
    return {"tipo": "interactivo"}


def _continuar_flujo(mensaje, remitente, usuario, sesion, foto_url=None):
    flujo = sesion.get("flujo")
    paso  = sesion.get("paso")
    datos = sesion.get("datos", {})
    sid   = sesion["id"]

    # Manejar IDs especiales de máquinas desde lista interactiva
    if mensaje.startswith("__maq_id_"):
        try:
            maq_id = int(mensaje.replace("__maq_id_", ""))
            opciones = datos.get("maquina_opciones", [])
            for i, op in enumerate(opciones):
                if op[0] == maq_id:
                    mensaje = str(i + 1)
                    break
        except:
            pass

    if flujo == FLUJOS["MATRICULA"]:
        # Inyectar botones interactivos en pasos clave
        resultado = mod_matricula.procesar(mensaje, usuario, sesion)
        return _enriquecer_matricula(resultado, paso, sesion, remitente, sid)

    if flujo == FLUJOS["PERFORACION"]:
        resultado = mod_perforacion.procesar(mensaje, usuario, sesion, foto_url)
        return _enriquecer_perforacion(resultado, paso, sesion, remitente, sid)

    if flujo == FLUJOS["SGS"]:
        return mod_sgs.procesar(mensaje, usuario, sesion)

    if flujo == FLUJOS["CERTIMIN"]:
        resultado = mod_certimin.procesar(mensaje, usuario, sesion)
        return _enriquecer_certimin(resultado, paso, remitente)

    if flujo == FLUJOS["DESCARGA_EXCEL"]:
        return _procesar_descarga(mensaje, usuario, sesion)

    if flujo == "9":  # Selección de foto
        resultado = mod_gerencia.consultar_foto(mensaje, usuario, sesion)
        return resultado

    cerrar_sesion(usuario["id"])
    menu_principal_rol(remitente, usuario)
    return {"tipo": "interactivo"}


def _enriquecer_matricula(resultado, paso, sesion, remitente, sid):
    from db.conexion import ejecutar as _ej
    row = _ej("SELECT paso_actual FROM sesiones_bot WHERE id = %s",
               (sid,), fetchone=True)
    paso_nuevo = row[0] if row else paso

    # Pasos de anulación — no interceptar, dejar pasar directo
    if paso in ("anular_buscar", "anular_confirmar"):
        return resultado

    if resultado is None:
        return {"tipo": "interactivo"}
    # Después de confirmar labor → botones diámetro
    if paso_nuevo == "diametro":
        if resultado:
            from main import enviar_mensaje
            try:
                enviar_mensaje(remitente, resultado)
            except:
                pass
        menu_diametro(remitente)
        return {"tipo": "interactivo"}

    # Después de elegir diámetro → lista máquinas
    if paso_nuevo == "maquina":
        if resultado:
            from main import enviar_mensaje
            try:
                enviar_mensaje(remitente, resultado)
            except:
                pass
        from db.usuarios import obtener_maquinas_activas
        maquinas = obtener_maquinas_activas()
        menu_maquinas(remitente, maquinas,
                      "¿Qué máquina perfora este sondaje?")
        return {"tipo": "interactivo"}

    # Resumen final → botones confirmar
    if paso_nuevo == "confirmacion" and isinstance(resultado, str) and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}

    # Reutilizar BHID anulado → botones sí/no
    if paso_nuevo == "reutilizar_bhid":
        botones_si_no(remitente, resultado)
        return {"tipo": "interactivo"}

    # Confirmar anulación → botones sí/no
    if paso_nuevo == "anular_confirmar" and isinstance(resultado, str):
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}

    return resultado


def _enriquecer_perforacion(resultado, paso, sesion, remitente, sid):
    """Reemplaza respuestas de texto con interactivos donde aplica."""
    from db.sesiones import obtener_sesion as _get
    sesion_actual = _get(sesion["id"]) or sesion
    paso_nuevo = sesion_actual.get("paso", paso)

    if paso_nuevo == "turno":
        botones_turno(remitente)
        return {"tipo": "interactivo"}
    if paso_nuevo == "foto":
        botones(remitente,
                "📸 ¿Adjuntar foto de la última caja o tramo?\n"
                "Envía la foto ahora o presiona No.",
                ["No"])
        return {"tipo": "interactivo"}
    if paso_nuevo == "confirmacion" and isinstance(resultado, str) and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
    if paso_nuevo == "reporte_empresa" and isinstance(resultado, str):
        botones_si_no_fin(remitente,
                          "¿Generar reporte consolidado de tu empresa?")
        return {"tipo": "interactivo"}
    if paso_nuevo == "post_consolidado":
        botones_si_no(remitente, "¿Registrar otra máquina?")
        return {"tipo": "interactivo"}
    if paso_nuevo == "maquina":
        from db.usuarios import obtener_maquinas_activas
        maquinas = obtener_maquinas_activas()
        menu_maquinas(remitente, maquinas)
        return {"tipo": "interactivo"}
    return resultado


def _enriquecer_certimin(resultado, paso, remitente):
    if isinstance(resultado, str) and "¿Confirmas?" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
    if isinstance(resultado, str) and "¿Qué quieres confirmar?" in resultado:
        botones(remitente, resultado,
                ["📦 Recepción", "📊 Resultados"])
        return {"tipo": "interactivo"}
    return resultado


def _procesar_descarga(mensaje, usuario, sesion):
    from db.sesiones import actualizar_sesion
    from reportes.exportar import generar_avance_diario, generar_estado_sondajes
    from config import hora_peru as _hora

    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    if paso == "tipo_reporte":
        if msg == "1":
            datos_excel = generar_avance_diario()
            cerrar_sesion(usuario["id"])
            if datos_excel:
                return _entregar_excel(datos_excel,
                    f"Avance_{_hora().strftime('%m%Y')}.xlsx", usuario)
            return "⚠️ Error generando Excel."
        elif msg == "2":
            datos_excel = generar_estado_sondajes()
            cerrar_sesion(usuario["id"])
            if datos_excel:
                return _entregar_excel(datos_excel, "Estado_Sondajes.xlsx", usuario)
            return "⚠️ Error generando Excel."
        elif msg == "3":
            actualizar_sesion(sid, "mes_especifico", datos)
            return "¿Qué mes? (número 1-12)\nEjemplo: *5* para mayo"
        return "❓ Opción no válida."

    elif paso == "mes_especifico":
        try:
            mes = int(msg)
            if mes < 1 or mes > 12:
                raise ValueError
        except:
            return "❓ Número del 1 al 12."
        anio = _hora().year
        datos_excel = generar_avance_diario(mes, anio)
        cerrar_sesion(usuario["id"])
        if datos_excel:
            return _entregar_excel(datos_excel, f"Avance_{mes:02d}{anio}.xlsx", usuario)
        return "⚠️ Error generando Excel."

    cerrar_sesion(usuario["id"])
    return "❓ Opción no válida."


def _entregar_excel(datos_bytes, nombre, usuario):
    try:
        with open(f"/tmp/{nombre}", "wb") as f:
            f.write(datos_bytes)
        return (
            f"✅ *Excel generado*\n\n"
            f"📄 {nombre}\n\n"
            f"Descárgalo en:\n"
            f"https://botminacl-production.up.railway.app/descargar/{nombre}\n\n"
            f"_(Disponible por 1 hora)_"
        )
    except Exception as e:
        print(f"[DESCARGA] Error: {e}")
        return "⚠️ Error generando el archivo."
