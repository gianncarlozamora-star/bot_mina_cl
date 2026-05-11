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

import modulos.matricula           as mod_matricula
import modulos.perforacion         as mod_perforacion
import modulos.sgs                 as mod_sgs
import modulos.certimin            as mod_certimin
import modulos.gerencia            as mod_gerencia
import modulos.anular_sgs          as mod_anular_sgs
import modulos.batch_geologo       as mod_batch_geologo
import modulos.reporte_sgs         as mod_reporte_sgs
import modulos.gestion_perforacion as mod_gestion_perf
import modulos.consolidado_perf    as mod_consolidado_perf
import modulos.modelamiento        as mod_modelamiento
import modulos.plan_tajos          as mod_plan_tajos    # ← NUEVO

ROLES_MATRICULA    = {"GEOLOGO", "ADMIN"}
ROLES_PERFORACION  = {"PERFORISTA", "ADMIN"}
ROLES_SGS          = {"SGS", "ADMIN"}
ROLES_CERTIMIN     = {"CERTIMIN", "ADMIN"}
ROLES_MODELAMIENTO = {"GEOLOGO", "ADMIN"}
ROLES_CONSULTA     = {"GEOLOGO", "ADMIN", "GERENCIA", "PERFORISTA"}
ROLES_PLAN_TAJOS   = {"GEOLOGO", "ADMIN"}                    # ← NUEVO


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

    # ── SGS directo desde menú principal rol SGS ─────────────
    _etapas_sgs_map = {"1": "LOGUEO", "2": "MUESTREO", "3": "RQD",
                       "4": "FOTOGRAFIA", "5": "DENSIDAD"}
    if usuario["rol"] in ROLES_SGS and msg_limpio in _etapas_sgs_map \
            and not obtener_sesion(usuario["id"]):
        _etapa = _etapas_sgs_map[msg_limpio]
        cerrar_sesion(usuario["id"])
        sid = crear_sesion(usuario["id"], FLUJOS["SGS"])
        from db.sesiones import actualizar_sesion as _act
        _act(sid, "sondaje_sgs", {"etapa": _etapa})
        return f"✅ Etapa: *{_etapa}*\n\n¿Código del sondaje?\nEjemplo: 8422, PECLD08422\n"

    
    # ── Accesos directos desde menú interactivo ───────────────
    # ── Plan de tajos — acceso directo ──────────────────────
    if msg_limpio.lower() in ("cargar plan tajos", "plan tajos",
                               "cargar plan", "subir plan tajos",
                               "nuevo plan tajos"):
        cerrar_sesion(usuario["id"])
        if usuario["rol"] not in ROLES_PLAN_TAJOS:
            return "⛔ Solo los geólogos pueden cargar el plan de tajos."
        sid = crear_sesion(usuario["id"], FLUJOS["PLAN_TAJOS"])
        return mod_plan_tajos.iniciar(usuario, sid)

    # ── CSV recibido — continuar flujo plan_tajos ─────────
    if msg_limpio.startswith("[csv:") and obtener_sesion(usuario["id"]):
        sesion_csv = obtener_sesion(usuario["id"])
        if sesion_csv and sesion_csv.get("flujo") == FLUJOS["PLAN_TAJOS"]:
            ruta = sesion_csv.get("datos", {}).get("csv_ruta_local")
            resultado = mod_plan_tajos.procesar(
                msg_limpio, usuario, sesion_csv,
                archivo_local=ruta
            )
            if ruta:
                try:
                    import os as _os
                    _os.remove(ruta)
                except:
                    pass
            return resultado

    if msg_limpio.lower() in ("anular sgs", "anular_sgs"):
        cerrar_sesion(usuario["id"])
        sid = crear_sesion(usuario["id"], FLUJOS["ANULAR_SGS"])
        return mod_anular_sgs.iniciar(usuario, sid)

    if msg_limpio.lower() in ("reporte sgs", "reporte diario sgs",
                               "generar reporte sgs"):
        cerrar_sesion(usuario["id"])
        if usuario["rol"] not in {"GEOLOGO", "ADMIN"}:
            return "⛔ Solo los geólogos pueden generar el reporte SGS."
        sid = crear_sesion(usuario["id"], FLUJOS["REPORTE_SGS"])
        return mod_reporte_sgs.iniciar(usuario, sid)

    if msg_limpio.lower() in ("modelamiento", "modelar", "estimar",
                               "estimacion", "estimación",
                               "modelamiento y estimacion"):
        cerrar_sesion(usuario["id"])
        if usuario["rol"] not in ROLES_MODELAMIENTO:
            return "⛔ Solo los geólogos pueden registrar modelamiento."
        sid = crear_sesion(usuario["id"], FLUJOS["MODELAMIENTO"])
        return mod_modelamiento.iniciar(usuario, sid)

    if msg_limpio.lower() in ("registrar batch", "batch"):
        cerrar_sesion(usuario["id"])
        if usuario["rol"] not in {"GEOLOGO", "ADMIN"}:
            return "⛔ Solo los geólogos pueden registrar batches."
        sid = crear_sesion(usuario["id"], FLUJOS["BATCH_GEOLOGO"])
        return mod_batch_geologo.iniciar(usuario, sid)

    # ── Historia tajo — acceso directo ────────────────────────
    if msg_limpio.lower() in ("historia tajo", "historia del tajo",
                               "reporte tajo", "excel tajo",
                               "historia por tajo"):
        cerrar_sesion(usuario["id"])
        return _iniciar_historia_tajo(remitente, usuario)

    # Viene de la lista interactiva (tajo__T-008)
    if msg_limpio.startswith("tajo__"):
        tajo_nombre = msg_limpio[6:].strip()
        return _generar_y_entregar_tajo(tajo_nombre, usuario)

    # ── Submenú gestión perforación ───────────────────────────
    if msg_limpio.lower() in ("gestion perforacion", "gestión perforación"):
        cerrar_sesion(usuario["id"])
        from whatsapp_interactivo import menu_gestion_perforacion
        menu_gestion_perforacion(remitente)
        return {"tipo": "interactivo"}

    if msg_limpio.lower() == "consolidado turno":
        from whatsapp_interactivo import menu_empresa_perforacion
        menu_empresa_perforacion(remitente)
        return {"tipo": "interactivo"}

    if msg_limpio.lower().startswith("consolidado_emp_"):
        codigo = msg_limpio.replace("consolidado_emp_", "")
        cerrar_sesion(usuario["id"])
        sid = crear_sesion(usuario["id"], FLUJOS["CONSOLIDADO_PERF"])
        from db.sesiones import actualizar_sesion as _act
        _act(sid, "cons_turno", {
            "empresa_id":     None if codigo == "todas" else _get_empresa_id(codigo),
            "empresa_nombre": codigo.upper(),
        })
        botones_turno(remitente, f"Empresa: {codigo.upper()} | Qué turno?")
        return {"tipo": "interactivo"}

    if msg_limpio.lower() == "sondajes activos":
        return mod_gestion_perf.sondajes_activos_perf()

    if msg_limpio.lower() == "metricas turno":
        return mod_gestion_perf.metricas_turno()

    # ── Consultas de pendientes — acceso directo pre-IA ───────
    _pendientes_frases = (
        "qué falta", "que falta", "falta modelar", "falta loguear",
        "falta muestrear", "falta estimar", "pendientes de",
        "sin modelar", "sin loguear", "sin muestrear", "sin estimar",
        "sin leyes", "qué está atrasado", "que esta atrasado",
        "atraso en", "brechas"
    )
    if any(f in msg_limpio.lower() for f in _pendientes_frases):
        etapa = None
        if any(w in msg_limpio.lower() for w in ("loguear", "logueo")):
            etapa = "LOGUEO"
        elif any(w in msg_limpio.lower() for w in ("muestrear", "muestreo")):
            etapa = "MUESTREO"
        elif any(w in msg_limpio.lower() for w in ("modelar", "modelado", "modelamiento")):
            etapa = "MODELADO"
        elif any(w in msg_limpio.lower() for w in ("estimar", "estimacion", "estimación")):
            etapa = "ESTIMACION"
        elif any(w in msg_limpio.lower() for w in ("laboratorio", "leyes", "analizar")):
            etapa = "LABORATORIO"
        return mod_gerencia.consultar_pendientes(etapa, usuario)

    # ── Sesión activa → continuar flujo ───────────────────────
    sesion = obtener_sesion(usuario["id"])
    if sesion:
        return _continuar_flujo(msg_limpio, remitente, usuario, sesion, foto_url)

    # ── Sin sesión → interpretar con IA ──────────────────────
    intent = interpretar_mensaje(msg_limpio, usuario)
    accion = intent.get("intencion", "desconocido")
    return _despachar_intencion(accion, intent, msg_limpio, remitente, usuario)


def _despachar_intencion(accion, intent, mensaje, remitente, usuario):
    rol = usuario["rol"]

    if accion == "menu":
        menu_principal_rol(remitente, usuario)
        return {"tipo": "interactivo"}

    # ── Matrícula ─────────────────────────────────────────────
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

    # ── Anulaciones ───────────────────────────────────────────
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

    # ── Batch ─────────────────────────────────────────────────
    if accion == "batch" or any(w in mensaje.lower() for w in (
            "registrar batch", "nuevo batch", "crear batch",
            "batch fusion", "envío laboratorio", "envio laboratorio")):
        if rol not in {"GEOLOGO", "ADMIN"}:
            return "⛔ Solo los geólogos pueden registrar batches."
        sid = crear_sesion(usuario["id"], FLUJOS["BATCH_GEOLOGO"])
        return mod_batch_geologo.iniciar(usuario, sid)

    # ── Perforación ───────────────────────────────────────────
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

    # ── SGS ───────────────────────────────────────────────────
    if accion == "sgs" or mensaje.lower() in ("sgs", "logueo", "muestreo", "rqd"):
        if rol not in ROLES_SGS:
            return "⛔ Este flujo es solo para técnicos SGS."
        sid = crear_sesion(usuario["id"], FLUJOS["SGS"])
        from db.sesiones import actualizar_sesion
        actualizar_sesion(sid, "tipo_etapa", {})
        menu_etapas_sgs(remitente)
        return {"tipo": "interactivo"}

    # ── Certimin ──────────────────────────────────────────────
    if accion == "certimin" or mensaje.lower() == "certimin":
        if rol not in ROLES_CERTIMIN:
            return "⛔ Este flujo es solo para Certimin."
        sid = crear_sesion(usuario["id"], FLUJOS["CERTIMIN"])
        return mod_certimin.iniciar(usuario, sid)

    # ── Modelamiento ──────────────────────────────────────────
    _es_consulta_pendiente = any(w in mensaje.lower() for w in (
        "qué falta", "que falta", "falta modelar", "sin modelar",
        "pendiente", "atrasado", "brecha"
    ))
    if not _es_consulta_pendiente and (
            accion == "modelamiento" or any(w in mensaje.lower() for w in (
            "modelamiento", "modelar", "estimacion", "estimación",
            "modelo corto plazo", "modelamiento y estimacion"))):
        if rol not in ROLES_MODELAMIENTO:
            return "⛔ Solo los geólogos pueden registrar modelamiento."
        sid = crear_sesion(usuario["id"], FLUJOS["MODELAMIENTO"])
        return mod_modelamiento.iniciar(usuario, sid)

    # ── Reporte SGS ───────────────────────────────────────────
    # ── Plan de tajos ─────────────────────────────────────────
    if accion == "plan_tajos" or any(w in mensaje.lower() for w in (
            "cargar plan tajos", "plan tajos", "subir plan",
            "cargar plan", "nuevo plan tajos")):
        if rol not in ROLES_PLAN_TAJOS:
            return "⛔ Solo los geólogos pueden cargar el plan de tajos."
        sid = crear_sesion(usuario["id"], FLUJOS["PLAN_TAJOS"])
        return mod_plan_tajos.iniciar(usuario, sid)

    if accion == "consulta_tajos_riesgo" or any(w in mensaje.lower() for w in (
            "tajos de alto riesgo", "tajos alto riesgo",
            "tajos criticos", "tajos críticos",
            "tajos de riesgo", "alto riesgo sin perforar")):
        return mod_plan_tajos.consultar_tajos_riesgo(None, usuario)

    if accion == "plan_mes" or any(w in mensaje.lower() for w in (
            "plan de mayo", "plan del mes", "plan de junio",
            "plan mensual", "resumen del plan")):
        mes = intent.get("mes")
        return mod_plan_tajos.consultar_plan_mes(mes=mes, usuario=usuario)

    if accion == "tajos_criticos" or any(w in mensaje.lower() for w in (
            "tajos sin perforar", "criticos sin perforar",
            "críticos sin perforar", "tajos urgentes")):
        return mod_plan_tajos.tajos_criticos_sin_perforar(usuario)

    if accion == "reporte_sgs" or any(w in mensaje.lower() for w in (
            "reporte sgs", "generar reporte sgs", "reporte diario sgs",
            "reporte geologia", "consolidado sgs")):
        if rol not in {"GEOLOGO", "ADMIN"}:
            return "⛔ Solo los geólogos pueden generar el reporte SGS."
        sid = crear_sesion(usuario["id"], FLUJOS["REPORTE_SGS"])
        return mod_reporte_sgs.iniciar(usuario, sid)

    # ══════════════════════════════════════════════════════════
    # CONSULTAS
    # ══════════════════════════════════════════════════════════

    if accion == "consulta_ddh":
        bhid = intent.get("bhid") or mensaje
        return mod_gerencia.consultar_ddh_completo(bhid, usuario)

    if accion == "consulta_batch":
        numero_batch = intent.get("numero_batch") or mensaje
        return mod_gerencia.consultar_batch(numero_batch, usuario)

    if accion == "consulta_tajo":
        tajo = intent.get("tajo") or mensaje
        return mod_gerencia.consultar_tajo(tajo, usuario)

    if accion == "consulta_objetivo":
        objetivo = intent.get("objetivo") or mensaje
        return mod_gerencia.consultar_objetivo(objetivo, usuario)

    if accion == "consulta_foto":
        bhid        = intent.get("bhid") or mensaje
        filtro_foto = intent.get("filtro_foto")
        resultado   = mod_gerencia.consultar_foto(bhid, usuario,
                                                   filtro_origen=filtro_foto)
        if isinstance(resultado, dict) and resultado.get("tipo") == "lista_fotos":
            menu_fotos(remitente, resultado["fotos"], resultado["bhid"])
            return {"tipo": "interactivo"}
        return resultado

    if accion == "consulta_activos" or any(w in mensaje.lower() for w in (
            "sondajes activos", "qué máquinas perforan", "que maquinas perforan",
            "en curso perforación", "activos perforacion")):
        return mod_gerencia.sondajes_en_curso(usuario)

    if accion == "consulta_semana" or any(w in mensaje.lower() for w in (
            "esta semana", "últimos 7 días", "ultimos 7 dias",
            "metros semana", "costo semana", "rendimiento semana")):
        return mod_gerencia.consultar_metros_semana(usuario)

    if accion == "consulta_mes" or any(w in mensaje.lower() for w in (
            "este mes", "del mes", "metros mes", "costo mes",
            "avance mensual", "lo que va del mes")):
        mes = intent.get("mes")
        return mod_gerencia.consultar_metros_mes(usuario, mes=mes)

    if accion == "ranking_maquinas" or any(w in mensaje.lower() for w in (
            "ranking", "máquina más productiva", "maquina mas productiva",
            "cuál máquina", "cual maquina", "mejor máquina",
            "comparar máquinas")):
        return mod_gerencia.ranking_maquinas(usuario)

    if accion == "consulta_pendientes" or any(w in mensaje.lower() for w in (
            "qué falta", "que falta", "pendientes", "atraso",
            "sin loguear", "sin muestrear", "sin modelar",
            "sin estimar", "qué está atrasado", "brechas")):
        etapa = intent.get("etapa_pendiente")
        return mod_gerencia.consultar_pendientes(etapa, usuario)

    if accion in ("consulta_logueo_activos", "sgs_activos"):
        return mod_sgs.consultar_sondajes_activos_sgs()

    if accion in ("consulta_finalizados", "sgs_finalizados"):
        return mod_sgs.consultar_finalizados_mes()

    if accion in ("consulta_pendiente_logueo", "sgs_pendientes"):
        return mod_sgs.consultar_pendientes_logueo()

    if accion == "gestion_perforacion" or any(w in mensaje.lower() for w in (
            "gestión perforación", "gestion perforacion",
            "consolidado perforación", "ver consolidado")):
        return _menu_gestion_perf(remitente)

    if accion == "consolidado_turno" or any(w in mensaje.lower() for w in (
            "consolidado turno", "reporte consolidado",
            "consolidado dia", "consolidado noche")):
        turno = "NOCHE" if "noche" in mensaje.lower() else None
        return mod_gestion_perf.consolidado_turno(turno=turno)

    if accion == "metricas_turno" or any(w in mensaje.lower() for w in (
            "métricas turno", "metricas turno", "metros del turno",
            "cuánto se perforó hoy", "cuanto se perforo")):
        return mod_gestion_perf.metricas_turno()

    # ── Historia tajo desde IA ────────────────────────────────
    if accion == "historia_tajo" or any(w in mensaje.lower() for w in (
            "historia tajo", "historia del tajo", "reporte tajo",
            "excel tajo", "historia por tajo", "descargar tajo")):
        if rol not in {"GERENCIA", "GEOLOGO", "ADMIN"}:
            return "⛔ Solo geólogos, gerencia y admin pueden descargar este reporte."
        # Si la IA extrajo el tajo directamente, generar sin preguntar
        tajo_directo = intent.get("tajo")
        if tajo_directo:
            return _generar_y_entregar_tajo(tajo_directo, usuario)
        return _iniciar_historia_tajo(remitente, usuario)

    # ── Resumen general ───────────────────────────────────────
    if accion == "resumen":
        if rol not in {"GERENCIA", "GEOLOGO", "ADMIN"}:
            return "⛔ El resumen es solo para gerencia y geólogos."
        return mod_gerencia.resumen_general(usuario)

    # ── Descarga Excel ────────────────────────────────────────
    if accion == "descarga":
        if rol not in {"GERENCIA", "GEOLOGO", "ADMIN"}:
            return "⛔ La descarga es solo para gerencia y geólogos."
        sid = crear_sesion(usuario["id"], FLUJOS["DESCARGA_EXCEL"])
        from db.sesiones import actualizar_sesion
        actualizar_sesion(sid, "tipo_reporte", {})
        menu_descarga(remitente)
        return {"tipo": "interactivo"}

    # ── Fallback ──────────────────────────────────────────────
    respuesta_libre = intent.get("respuesta_libre", "")
    if respuesta_libre:
        return respuesta_libre

    menu_principal_rol(remitente, usuario)
    return {"tipo": "interactivo"}


def _continuar_flujo(mensaje, remitente, usuario, sesion, foto_url=None):
    flujo = sesion.get("flujo")
    paso  = sesion.get("paso")
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

    if flujo == FLUJOS["CONSOLIDADO_PERF"]:
        resultado = mod_consolidado_perf.procesar(mensaje, usuario, sesion)
        return _enriquecer_consolidado(resultado, paso, sid, remitente)

    if flujo == FLUJOS["ANULAR_SGS"]:
        return mod_anular_sgs.procesar(mensaje, usuario, sesion)

    if flujo == FLUJOS["BATCH_GEOLOGO"]:
        resultado = mod_batch_geologo.procesar(mensaje, usuario, sesion)
        return _enriquecer_batch(resultado, paso, sid, remitente)

    if flujo == FLUJOS["REPORTE_SGS"]:
        return mod_reporte_sgs.procesar(mensaje, usuario, sesion)

    if flujo == FLUJOS["DESCARGA_EXCEL"]:
        return _procesar_descarga(mensaje, usuario, sesion)

    if flujo == FLUJOS["PLAN_TAJOS"]:
        ruta_csv = datos.get("csv_ruta_local")
        resultado = mod_plan_tajos.procesar(
            mensaje, usuario, sesion,
            archivo_local=ruta_csv if paso == "pt_csv" else None
        )
        return resultado

    if flujo == FLUJOS["MODELAMIENTO"]:
        resultado = mod_modelamiento.procesar(mensaje, usuario, sesion)
        return _enriquecer_modelamiento(resultado, paso, sid, remitente)

    if flujo == FLUJOS["HISTORIA_TAJO"]:
        return _procesar_historia_tajo(mensaje, usuario, sesion, remitente)

    if flujo == "9":  # Selección de foto
        return mod_gerencia.consultar_foto(mensaje, usuario, sesion)

    cerrar_sesion(usuario["id"])
    menu_principal_rol(remitente, usuario)
    return {"tipo": "interactivo"}


# ══════════════════════════════════════════════════════════════
# ENRICHERS
# ══════════════════════════════════════════════════════════════

def _enriquecer_matricula(resultado, paso_anterior, sesion_id, remitente):
    from db.conexion import ejecutar as _ej
    row = _ej("SELECT paso_actual FROM sesiones_bot WHERE id = %s",
               (sesion_id,), fetchone=True)
    paso_nuevo = row[0] if row else paso_anterior

    if paso_anterior in ("anular_buscar", "anular_confirmar") or \
       paso_nuevo    in ("anular_buscar", "anular_confirmar"):
        return resultado
    if resultado is None:
        return {"tipo": "interactivo"}
    if paso_nuevo == "diametro":
        _enviar_texto(remitente, resultado)
        menu_diametro(remitente)
        return {"tipo": "interactivo"}
    if paso_nuevo == "maquina":
        _enviar_texto(remitente, resultado)
        from db.usuarios import obtener_maquinas_activas
        maquinas = obtener_maquinas_activas()
        menu_maquinas(remitente, maquinas, "¿Qué máquina perfora este sondaje?")
        return {"tipo": "interactivo"}
    if paso_nuevo == "codigo_ddh":
        return resultado
    if paso_nuevo == "confirmacion" and isinstance(resultado, str) and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
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
                "Envía la foto ahora o presiona No.", ["No"])
        return {"tipo": "interactivo"}
    if paso_nuevo == "confirmacion" and isinstance(resultado, str) and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
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

    if paso_nuevo == "foto_logueo":
        botones(remitente,
                "📸 ¿Adjuntar foto del tramo logueado?\n"
                "Envía la imagen ahora o presiona No.", ["No"])
        return {"tipo": "interactivo"}
    if paso_nuevo == "confirmacion_logueo" and isinstance(resultado, str) \
            and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
    if paso_nuevo == "confirmar_fin_logueo":
        botones_si_no(remitente, resultado)
        return {"tipo": "interactivo"}
    if paso_nuevo == "confirmacion_muestreo" and isinstance(resultado, str) \
            and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
    if paso_nuevo == "confirmacion_densidad" and isinstance(resultado, str) \
            and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
    if paso_nuevo == "foto_opcional":
        botones(remitente,
                "📸 ¿Adjuntar foto del tramo?\n"
                "Envía la imagen o presiona No.", ["No"])
        return {"tipo": "interactivo"}
    if paso_nuevo == "confirmacion_generica" and isinstance(resultado, str) \
            and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
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


def _enriquecer_modelamiento(resultado, paso_anterior, sesion_id, remitente):
    from db.conexion import ejecutar as _ej
    row = _ej("SELECT paso_actual FROM sesiones_bot WHERE id = %s",
               (sesion_id,), fetchone=True)
    paso_nuevo = row[0] if row else paso_anterior

    if paso_nuevo == "mod_confirmacion" and isinstance(resultado, str) \
            and "RESUMEN" in resultado:
        botones_confirmar(remitente, resultado)
        return {"tipo": "interactivo"}
    return resultado


def _enriquecer_consolidado(resultado, paso_anterior, sesion_id, remitente):
    from db.conexion import ejecutar as _ej
    row = _ej("SELECT paso_actual FROM sesiones_bot WHERE id = %s",
               (sesion_id,), fetchone=True)
    paso_nuevo = row[0] if row else paso_anterior

    if paso_nuevo == "cons_turno":
        botones_turno(remitente)
        return {"tipo": "interactivo"}
    if paso_nuevo == "cons_fecha":
        return resultado
    return resultado


# ══════════════════════════════════════════════════════════════
# HISTORIA TAJO — helpers
# ══════════════════════════════════════════════════════════════

def _iniciar_historia_tajo(remitente: str, usuario: dict):
    """Muestra la lista de tajos disponibles o pide que escriba el nombre."""
    from reportes.exportar import listar_tajos_disponibles
    from db.sesiones import actualizar_sesion

    rol = usuario["rol"]
    if rol not in {"GERENCIA", "GEOLOGO", "ADMIN"}:
        return "⛔ Solo geólogos, gerencia y admin pueden descargar este reporte."

    tajos = listar_tajos_disponibles()
    if not tajos:
        return "⚠️ No hay tajos con sondajes activos en este momento."

    sid = crear_sesion(usuario["id"], FLUJOS["HISTORIA_TAJO"])
    actualizar_sesion(sid, "esperando_tajo",
                      {"tajos_disponibles": [t["tajo"] for t in tajos]})

    _menu_seleccion_tajo_wa(remitente, tajos)
    return {"tipo": "interactivo"}


def _menu_seleccion_tajo_wa(remitente: str, tajos: list):
    """Envía lista interactiva de tajos (máx 10)."""
    items = [
        {
            "id":    f"tajo_{t['tajo'].replace(' ', '_')[:30]}",
            "titulo": t["tajo"][:24],
            "desc":  f"{t['total']} DDH | {t['metros']:,.0f} m perf."
        }
        for t in tajos[:10]
    ]
    lista(
        remitente,
        "📋 *Historia por Tajo*\n\n"
        "Selecciona el tajo de la lista o escribe su nombre directamente:",
        [{"titulo": "Tajos activos", "items": items}],
        boton_texto="Ver tajos"
    )


def _procesar_historia_tajo(mensaje: str, usuario: dict,
                             sesion: dict, remitente: str):
    """Maneja la sesión HISTORIA_TAJO: recibe el nombre y genera el Excel."""
    from reportes.exportar import listar_tajos_disponibles

    paso  = sesion["paso"]
    datos = sesion["datos"]

    if paso == "esperando_tajo":
        tajo_input = mensaje.strip()
        tajos_disponibles = datos.get("tajos_disponibles", [])

        # Buscar coincidencia parcial (case-insensitive)
        match = next(
            (t for t in tajos_disponibles
             if tajo_input.upper() in t.upper() or t.upper() in tajo_input.upper()),
            None
        )

        if not match:
            # Si no hay match sugerir similares por primera letra
            sugerencias = [t for t in tajos_disponibles
                           if tajo_input and tajo_input[0].upper() == t[0].upper()][:3]
            sug_str = "\n".join(f"  • {s}" for s in sugerencias)
            return (
                f"❓ No encontré el tajo *{tajo_input}*.\n\n"
                + (f"Quizás quisiste decir:\n{sug_str}\n\n" if sug_str else "")
                + "Escribe el nombre exacto o toca *hola* para ver la lista."
            )

        cerrar_sesion(usuario["id"])
        return _generar_y_entregar_tajo(match, usuario)

    cerrar_sesion(usuario["id"])
    return "❓ Paso no reconocido. Escribe *hola* para reiniciar."


def _generar_y_entregar_tajo(tajo: str, usuario: dict) -> str:
    """Genera el Excel de historia del tajo y retorna el link de descarga."""
    from reportes.exportar import generar_historia_tajo
    from config import hora_peru

    datos_excel = generar_historia_tajo(tajo)
    if not datos_excel:
        return (
            f"⚠️ No encontré sondajes para el tajo *{tajo}*.\n"
            f"Verifica el nombre e intenta de nuevo."
        )

    nombre = (
        f"Historia_Tajo_{tajo.replace(' ', '_').replace('/', '-')}"
        f"_{hora_peru().strftime('%d%m%Y')}.xlsx"
    )
    return _entregar_excel(datos_excel, nombre)


# ══════════════════════════════════════════════════════════════
# HELPERS GENERALES
# ══════════════════════════════════════════════════════════════

def _get_empresa_id(codigo: str):
    from db.conexion import ejecutar as _ej
    row = _ej("SELECT id FROM cat_empresas WHERE LOWER(codigo) = %s",
              (codigo.lower(),), fetchone=True)
    return row[0] if row else None


def _menu_gestion_perf(remitente: str):
    from whatsapp_interactivo import menu_gestion_perforacion
    menu_gestion_perforacion(remitente)
    return {"tipo": "interactivo"}


def _enviar_texto(remitente, texto):
    if not texto:
        return
    try:
        from main import enviar_mensaje
        enviar_mensaje(remitente, texto)
    except Exception as e:
        print(f"[ROUTER] Error enviando texto: {e}")


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
        return _entregar_excel(datos_excel,
            f"Avance_{mes:02d}{anio}.xlsx") if datos_excel \
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


def _iniciar_anulacion_reporte(usuario: dict) -> str:
    from db.conexion import ejecutar as _ej
    from db.sesiones import crear_sesion, actualizar_sesion
    rol = usuario["rol"]

    if rol == "PERFORISTA":
        row = _ej(
            """SELECT ap.id, s.bhid, ap.fecha, ap.turno,
                      ap.prof_inicio, ap.prof_final
               FROM avance_perforacion ap
               JOIN sondajes s ON ap.sondaje_id = s.id
               WHERE ap.reportado_por = %s AND ap.estado = 'ACTIVO'
               ORDER BY ap.id DESC LIMIT 1""",
            (usuario["id"],), fetchone=True
        )
    else:
        row = _ej(
            """SELECT ap.id, s.bhid, ap.fecha, ap.turno,
                      ap.prof_inicio, ap.prof_final
               FROM avance_perforacion ap
               JOIN sondajes s ON ap.sondaje_id = s.id
               WHERE ap.estado = 'ACTIVO'
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
