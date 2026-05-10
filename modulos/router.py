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
import modulos.anular_sgs    as mod_anular_sgs
import modulos.batch_geologo as mod_batch_geologo

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
 
    # ── Cambio de módulo desde interactivo (aunque haya sesión) ──
    # Cuando el usuario toca un botón de menú que cambia de módulo,
    # cerrar la sesión activa y abrir la nueva.
    if msg_limpio.lower() in ("anular sgs", "anular_sgs"):
        cerrar_sesion(usuario["id"])
        sid = crear_sesion(usuario["id"], FLUJOS["ANULAR_SGS"])
        return mod_anular_sgs.iniciar(usuario, sid)
 
    if msg_limpio.lower() in ("registrar batch", "batch"):
        cerrar_sesion(usuario["id"])
        rol = usuario["rol"]
        if rol not in {"GEOLOGO", "ADMIN"}:
            return "⛔ Solo los geólogos pueden registrar batches."
        sid = crear_sesion(usuario["id"], FLUJOS["BATCH_GEOLOGO"])
        return mod_batch_geologo.iniciar(usuario, sid)

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

    if accion == "matricula" or mensaje.lower() in ("matricular", "matricula"):
        if rol not in ROLES_MATRICULA:
            return "⛔ Solo los geólogos de Nexa pueden matricular sondajes."
        sid = crear_sesion(usuario["id"], FLUJOS["MATRICULA"])
        from db.sondajes import obtener_subcategorias_activas
        from db.sesiones import actualizar_sesion
        subcat = obtener_subcategorias_activas()
        actualizar_sesion(sid, "tipo_sondaje",
                          {"subcat_opciones": [s["codigo"] for s in subcat],
                           "subcat_ids":      [s["id"]     for s in subcat],
                           "subcat_nombres":  [s["nombre"] for s in subcat]})
        menu_tipo_sondaje(remitente)
        return {"tipo": "interactivo"}

    if accion == "anular_reporte" or any(w in mensaje.lower()
            for w in ("anular reporte", "borrar reporte", "eliminar reporte",
                      "borrar mi reporte", "anular mi reporte")):
        return _iniciar_anulacion_reporte(usuario)
    
    if (accion == "anular" and accion != "anular_reporte") or any(w in mensaje.lower()
            for w in ("eliminar sondaje", "borrar sondaje")):
        if rol not in ROLES_MATRICULA:
            return "⛔ Solo geólogos y admin pueden anular sondajes."
        sid = crear_sesion(usuario["id"], FLUJOS["MATRICULA"])
        return mod_matricula.iniciar_anulacion(usuario, sid)

    if accion == "anular_sgs" or any(w in mensaje.lower() for w in (
            "borrar logueo", "anular logueo", "borrar muestreo",
            "anular muestreo", "borrar registro sgs",
            "corregir reporte sgs", "eliminar registro sgs")):
        sid = crear_sesion(usuario["id"], FLUJOS["ANULAR_SGS"])
        return mod_anular_sgs.iniciar(usuario, sid)
 
    
    if accion == "batch" or any(w in mensaje.lower() for w in (
            "registrar batch", "nuevo batch", "crear batch",
            "batch fusion", "envío laboratorio", "envio laboratorio")):
        if rol not in {"GEOLOGO", "ADMIN"}:
            return "⛔ Solo los geólogos pueden registrar batches."
        sid = crear_sesion(usuario["id"], FLUJOS["BATCH_GEOLOGO"])
        return mod_batch_geologo.iniciar(usuario, sid)

    if accion == "perforacion" or mensaje.lower() == "perforacion":
        if rol not in ROLES_PERFORACION:
            return "⛔ Este flujo es solo para perforistas."
        sid = crear_sesion(usuario["id"], FLUJOS["PERFORACION"])
        from db.usuarios import obtener_maquinas_activas
        from db.sesiones import actualizar_sesion
        maquinas = obtener_maquinas_activas()
        actualizar_sesion(sid, "maquina",
                          {"maquina_opciones": [(m["id"], m["codigo"],
                                                 m["empresa"]) for m in maquinas]})
        menu_maquinas(remitente, maquinas)
        return {"tipo": "interactivo"}

    if accion == "sgs" or mensaje.lower() in ("sgs", "logueo", "muestreo", "rqd"):
        if rol not in ROLES_SGS:
            return "⛔ Este flujo es solo para técnicos SGS."
        sid = crear_sesion(usuario["id"], FLUJOS["SGS"])
        from db.sesiones import actualizar_sesion
        actualizar_sesion(sid, "tipo_etapa", {})
        menu_etapas_sgs(remitente)
        return {"tipo": "interactivo"}

    if accion == "certimin" or mensaje.lower() == "certimin":
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

    if accion == "consulta_activos":
        return mod_gerencia.sondajes_en_curso(usuario)

    if accion in ("consulta_logueo_activos", "sgs_activos"):
        return mod_sgs.consultar_sondajes_activos_sgs()
 
    if accion in ("consulta_finalizados", "sgs_finalizados"):
        return mod_sgs.consultar_finalizados_mes()
 
    if accion in ("consulta_pendiente_logueo", "sgs_pendientes"):
        return mod_sgs.consultar_pendientes_logueo()
  
    if accion == "resumen":
        if rol not in {"GERENCIA", "GEOLOGO", "ADMIN"}:
            return "⛔ El resumen es solo para gerencia y geólogos."
        return mod_gerencia.resumen_general(usuario)

    if accion == "descarga":
        if rol not in {"GERENCIA", "GEOLOGO", "ADMIN"}:
            return "⛔ La descarga es solo para gerencia y geólogos."
        sid = crear_sesion(usuario["id"], FLUJOS["DESCARGA_EXCEL"])
        from db.sesiones import actualizar_sesion
        actualizar_sesion(sid, "tipo_reporte", {})
        menu_descarga(remitente)
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

    # Normalizar IDs de máquinas desde lista interactiva
    if mensaje.startswith("__maq_id_"):
        try:
            maq_id   = int(mensaje.replace("__maq_id_", ""))
            from db.usuarios import obtener_maquinas_activas
            maquinas = obtener_maquinas_activas()
            for i, m in enumerate(maquinas):
                if m["id"] == maq_id:
                    mensaje = str(i + 1)
                    break
        except:
            pass

    if flujo == FLUJOS["MATRICULA"]:
        resultado = mod_matricula.procesar(mensaje, usuario, sesion)
        return _enriquecer_matricula(resultado, paso, sid, remitente)

    if flujo == FLUJOS["PERFORACION"]:
        resultado = mod_perforacion.procesar(mensaje, usuario, sesion, foto_url)
        return _enriquecer_perforacion(resultado, paso, sid, remitente)

    if flujo == FLUJOS["SGS"]:
        resultado = mod_sgs.procesar(mensaje, usuario, sesion, foto_url)
        return _enriquecer_sgs(resultado, paso, sid, remitente)

    if flujo == FLUJOS["CERTIMIN"]:
        resultado = mod_certimin.procesar(mensaje, usuario, sesion)
        return _enriquecer_certimin(resultado, paso, remitente)
        
    if flujo == FLUJOS["ANULAR_SGS"]:
        return mod_anular_sgs.procesar(mensaje, usuario, sesion)

    if flujo == FLUJOS["BATCH_GEOLOGO"]:
        resultado = mod_batch_geologo.procesar(mensaje, usuario, sesion)
        return _enriquecer_batch(resultado, paso, sid, remitente)
    
   
    if flujo == FLUJOS["DESCARGA_EXCEL"]:
        return _procesar_descarga(mensaje, usuario, sesion)

    if flujo == "9":  # Selección de foto
        return mod_gerencia.consultar_foto(mensaje, usuario, sesion)

    cerrar_sesion(usuario["id"])
    menu_principal_rol(remitente, usuario)
    return {"tipo": "interactivo"}


# ── ENRICHERS ─────────────────────────────────────────────────
# Leen el paso NUEVO de BD (después de que el módulo lo actualizó)
# y envían el interactivo correspondiente.

def _enriquecer_matricula(resultado, paso_anterior, sesion_id, remitente):
    from db.conexion import ejecutar as _ej
    row = _ej("SELECT paso_actual FROM sesiones_bot WHERE id = %s",
               (sesion_id,), fetchone=True)
    paso_nuevo = row[0] if row else paso_anterior

    # Pasos de anulación — pasar directo sin interceptar
    if paso_anterior in ("anular_buscar", "anular_confirmar") or \
       paso_nuevo    in ("anular_buscar", "anular_confirmar"):
        return resultado

    # Menú ya enviado por el router
    if resultado is None:
        return {"tipo": "interactivo"}

    # labor completado → mostrar botones de diámetro
    if paso_nuevo == "diametro":
        _enviar_texto(remitente, resultado)
        menu_diametro(remitente)
        return {"tipo": "interactivo"}

    # diámetro completado → mostrar lista de máquinas
    if paso_nuevo == "maquina":
        _enviar_texto(remitente, resultado)
        from db.usuarios import obtener_maquinas_activas
        maquinas = obtener_maquinas_activas()
        menu_maquinas(remitente, maquinas, "¿Qué máquina perfora este sondaje?")
        return {"tipo": "interactivo"}

    # máquina completada → código DDH (texto libre, no interceptar)
    if paso_nuevo == "codigo_ddh":
        return resultado

    # confirmación → botones confirmar/cancelar
    if paso_nuevo == "confirmacion" and isinstance(resultado, str) and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}

    # reutilizar BHID anulado → botones sí/no
    if paso_nuevo == "reutilizar_bhid":
        botones_si_no(remitente, resultado)
        return {"tipo": "interactivo"}

    return resultado


def _enriquecer_perforacion(resultado, paso_anterior, sesion_id, remitente):
    from db.conexion import ejecutar as _ej
    row = _ej("SELECT paso_actual FROM sesiones_bot WHERE id = %s",
               (sesion_id,), fetchone=True)
    paso_nuevo = row[0] if row else paso_anterior

    if paso_nuevo == "sondaje":
        return resultado
    if paso_nuevo == "turno" and paso_anterior != "turno":
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
    if paso_nuevo == "reporte_empresa" and paso_anterior != "reporte_empresa":
        botones_si_no_fin(remitente, "¿Generar reporte consolidado de tu empresa?")
        return {"tipo": "interactivo"}
    if paso_nuevo == "post_consolidado" and paso_anterior != "post_consolidado":
        if isinstance(resultado, str) and resultado.strip():
            _enviar_texto(remitente, resultado)
        botones_si_no(remitente, "¿Registrar otra máquina?")
        return {"tipo": "interactivo"}
        
    if paso_nuevo == "maquina":
        from db.usuarios import obtener_maquinas_activas
        maquinas = obtener_maquinas_activas()
        menu_maquinas(remitente, maquinas)
        return {"tipo": "interactivo"}
    return resultado

def _enriquecer_sgs(resultado, paso_anterior, sesion_id, remitente):
    from db.conexion import ejecutar as _ej
    row = _ej("SELECT paso_actual FROM sesiones_bot WHERE id = %s",
               (sesion_id,), fetchone=True)
    paso_nuevo = row[0] if row else paso_anterior
 
    # ── LOGUEO ────────────────────────────────────────────────
    if paso_nuevo == "foto_logueo":
        botones(remitente,
                "📸 ¿Adjuntar foto del tramo logueado?\\n"
                "Envía la imagen ahora o presiona No.",
                ["No"])
        return {"tipo": "interactivo"}
 
    if paso_nuevo == "confirmacion_logueo" and isinstance(resultado, str) \
            and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
 
    if paso_nuevo == "confirmar_fin_logueo":
        botones_si_no(remitente, resultado)
        return {"tipo": "interactivo"}
 
    # ── MUESTREO ──────────────────────────────────────────────
    if paso_nuevo == "confirmacion_muestreo" and isinstance(resultado, str) \
            and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
 
    # ── DENSIDAD ──────────────────────────────────────────────
    if paso_nuevo == "confirmacion_densidad" and isinstance(resultado, str) \
            and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
 
    # ── GENÉRICO (RQD, Fotografía) ────────────────────────────
    if paso_nuevo == "foto_opcional":
        botones(remitente,
                "📸 ¿Adjuntar foto del tramo?\\n"
                "Envía la imagen o presiona No.",
                ["No"])
        return {"tipo": "interactivo"}
 
    if paso_nuevo == "confirmacion_generica" and isinstance(resultado, str) \
            and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
 
    # Texto libre en todos los demás pasos
    return resultado

def _enriquecer_batch(resultado, paso_anterior, sesion_id, remitente):
    from db.conexion import ejecutar as _ej
    row = _ej("SELECT paso_actual FROM sesiones_bot WHERE id = %s",
               (sesion_id,), fetchone=True)
    paso_nuevo = row[0] if row else paso_anterior
 
    if paso_nuevo == "batch_confirmacion" and isinstance(resultado, str) \
            and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
 
    return resultado





def _enriquecer_certimin(resultado, paso, remitente):
    if isinstance(resultado, str) and "¿Confirmas?" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
    if isinstance(resultado, str) and "¿Qué quieres confirmar?" in resultado:
        botones(remitente, resultado, ["📦 Recepción", "📊 Resultados"])
        return {"tipo": "interactivo"}
    return resultado


# ── DESCARGA ──────────────────────────────────────────────────

def _procesar_descarga(mensaje, usuario, sesion):
    from db.sesiones import actualizar_sesion
    from reportes.exportar import generar_avance_diario, generar_estado_sondajes
    from config import hora_peru as _hora

    paso = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    if paso == "tipo_reporte":
        if msg == "1":
            datos_excel = generar_avance_diario()
            cerrar_sesion(usuario["id"])
            return _entregar_excel(datos_excel,
                f"Avance_{_hora().strftime('%m%Y')}.xlsx") if datos_excel \
                else "⚠️ Error generando Excel."
        elif msg == "2":
            datos_excel = generar_estado_sondajes()
            cerrar_sesion(usuario["id"])
            return _entregar_excel(datos_excel, "Estado_Sondajes.xlsx") if datos_excel \
                else "⚠️ Error generando Excel."
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
        anio        = _hora().year
        datos_excel = generar_avance_diario(mes, anio)
        cerrar_sesion(usuario["id"])
        return _entregar_excel(datos_excel, f"Avance_{mes:02d}{anio}.xlsx") if datos_excel \
            else "⚠️ Error generando Excel."

    cerrar_sesion(usuario["id"])
    return "❓ Opción no válida."


def _entregar_excel(datos_bytes, nombre):
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


def _enviar_texto(remitente, texto):
    """Envía un mensaje de texto simple (helper interno)."""
    if not texto:
        return
    try:
        from main import enviar_mensaje
        enviar_mensaje(remitente, texto)
    except Exception as e:
        print(f"[ROUTER] Error enviando texto: {e}")


def _iniciar_anulacion_reporte(usuario: dict) -> str:
    """Inicia el flujo de anulación del último reporte de perforación."""
    from db.conexion import ejecutar as _ej
    from db.sesiones import crear_sesion, actualizar_sesion
    rol = usuario["rol"]

    if rol == "PERFORISTA":
        # Solo puede anular su propio último reporte
        row = _ej(
            """SELECT ap.id, s.bhid, ap.fecha, ap.turno,
                      ap.prof_inicio, ap.prof_final
               FROM avance_perforacion ap
               JOIN sondajes s ON ap.sondaje_id = s.id
               JOIN cat_maquinas m ON ap.maquina_id = m.id
               WHERE ap.reportado_por = %s AND ap.estado = \'ACTIVO\'
               ORDER BY ap.id DESC LIMIT 1""",
            (usuario["id"],), fetchone=True
        )
    else:
        # ADMIN y GEOLOGO ven el último reporte global
        row = _ej(
            """SELECT ap.id, s.bhid, ap.fecha, ap.turno,
                      ap.prof_inicio, ap.prof_final
               FROM avance_perforacion ap
               JOIN sondajes s ON ap.sondaje_id = s.id
               WHERE ap.estado = \'ACTIVO\'
               ORDER BY ap.id DESC LIMIT 1""",
            fetchone=True
        )

    if not row:
        return "⚠️ No encontré ningún reporte activo para anular."

    ap_id, bhid, fecha, turno, prof_ini, prof_fin = row
    try:
        from datetime import datetime
        fecha_fmt = datetime.strptime(str(fecha), "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        fecha_fmt = str(fecha)

    sid = crear_sesion(usuario["id"], FLUJOS["PERFORACION"])
    actualizar_sesion(sid, "anular_reporte", {
        "reporte_id":  ap_id,
        "bhid":        bhid,
        "turno":       turno,
        "fecha_fmt":   fecha_fmt,
        "prof_inicio": float(prof_ini or 0),
        "prof_final":  float(prof_fin or 0),
    })
    avance = float(prof_fin or 0) - float(prof_ini or 0)
    return (
        f"🗑️ *ANULAR REPORTE*\n\n"
        f"🔖 {bhid} | {turno} {fecha_fmt}\n"
        f"📏 {float(prof_ini or 0):.2f} → {float(prof_fin or 0):.2f} m "
        f"| +{avance:.2f} m\n\n"
        f"⚠️ Esta acción no se puede deshacer.\n"
        f"¿Confirmas? (*sí* / *no*)\n"
    )
