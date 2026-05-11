"""
MÓDULO PLAN TAJOS
Carga el CSV de recursos por tajo, pondera leyes por TONNES,
y permite asignar riesgo (ALTO/MEDIO/BAJO) por conversación.

Flujo:
  iniciar → pide mes/año → pide tipo (PRELIMINAR/ADICIONAL)
  → pide CSV por WhatsApp → procesa → resumen
  → pregunta tajos ALTO riesgo → pregunta MEDIO → resto = BAJO
  → confirmación final

Tabla que escribe:
  - plan_tajos (una fila por tajo por mes/tipo)

CSV esperado (columnas mínimas):
  LAYERS, CLASS, TONNES, ZN, PB, CU, AGOZ, NSR25RES
  LAYERS formato: NIVEL_OREBODY_TAJO ej: 1550_OB1_T-021
"""
from db.sesiones import actualizar_sesion, cerrar_sesion
from db.conexion import ejecutar
from config import fecha_hora_str, hora_peru

FLUJO = "PLAN_TAJOS"

# CLASS a ignorar en el cálculo — ninguno, incluimos todo
CLASS_IGNORAR = set()  # incluimos 0, 5 y todos

MESES = {
    1:"enero", 2:"febrero", 3:"marzo", 4:"abril",
    5:"mayo", 6:"junio", 7:"julio", 8:"agosto",
    9:"septiembre", 10:"octubre", 11:"noviembre", 12:"diciembre"
}


# ══════════════════════════════════════════════════════════════
# INICIO
# ══════════════════════════════════════════════════════════════

def iniciar(usuario: dict, sesion_id: int) -> str:
    actualizar_sesion(sesion_id, "pt_mes", {})
    hoy = hora_peru()
    return (
        f"📊 *CARGAR PLAN DE TAJOS*\n"
        f"📅 {fecha_hora_str()}\n\n"
        f"¿Para qué *mes y año* es este plan?\n"
        f"Ejemplo: *mayo 2026* o *5 2026*\n"
        f"_(Mes actual: {MESES[hoy.month]} {hoy.year})_\n"
    )


# ══════════════════════════════════════════════════════════════
# PROCESADOR PRINCIPAL
# ══════════════════════════════════════════════════════════════

def procesar(mensaje: str, usuario: dict, sesion: dict,
             archivo_url: str = None, archivo_local: str = None) -> str:
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    # ── Mes y año ─────────────────────────────────────────────
    if paso == "pt_mes":
        resultado = _parsear_mes_anio(msg)
        if not resultado:
            return (
                "❓ No entendí el mes. Ejemplos:\n"
                "  *mayo 2026*\n  *5 2026*\n  *05/2026*\n"
            )
        datos["mes"], datos["anio"] = resultado
        actualizar_sesion(sid, "pt_tipo", datos)
        return (
            f"✅ Plan: *{MESES[datos['mes']].capitalize()} {datos['anio']}*\n\n"
            f"¿Qué tipo de envío es?\n"
            f"  *1* — 📋 PRELIMINAR (envío inicial del mes)\n"
            f"  *2* — ➕ ADICIONAL (actualización fuera de fecha)\n"
        )

    # ── Tipo de envío ─────────────────────────────────────────
    elif paso == "pt_tipo":
        if msg in ("1", "preliminar", "PRELIMINAR"):
            datos["tipo_envio"] = "PRELIMINAR"
        elif msg in ("2", "adicional", "ADICIONAL"):
            datos["tipo_envio"] = "ADICIONAL"
        else:
            return "❓ Responde *1* (Preliminar) o *2* (Adicional)."
        actualizar_sesion(sid, "pt_csv", datos)
        return (
            f"✅ Tipo: *{datos['tipo_envio']}*\n\n"
            f"📎 Ahora envía el archivo *CSV* del reporte de tajos.\n"
            f"_(El archivo debe tener columnas: LAYERS, CLASS, TONNES, ZN, PB, CU, AGOZ, NSR25RES)_\n"
        )

    # ── Recepción del CSV ─────────────────────────────────────
    elif paso == "pt_csv":
        if not archivo_local:
            return (
                "📎 Aún no recibí el archivo CSV.\n"
                "Envíalo como documento adjunto desde WhatsApp."
            )
        # Procesar el CSV
        return _procesar_csv(archivo_local, datos, sid, usuario)

    # ── Tajos de riesgo ALTO ──────────────────────────────────
    elif paso == "pt_riesgo_alto":
        tajos_procesados = datos.get("tajos_procesados", [])
        tajos_validos    = [t["tajo"] for t in tajos_procesados]

        if msg.lower() in ("no", "n", "ninguno", "ninguna"):
            datos["tajos_alto"] = []
        else:
            ingresados = [t.strip().upper() for t in msg.replace(";", ",").split(",") if t.strip()]
            # Validar que existan en el plan
            no_encontrados = [t for t in ingresados if t not in tajos_validos]
            if no_encontrados:
                return (
                    f"❌ No encontré en el plan: *{', '.join(no_encontrados)}*\n"
                    f"Verifica los códigos o escribe *no* para continuar.\n"
                )
            datos["tajos_alto"] = ingresados

        actualizar_sesion(sid, "pt_riesgo_medio", datos)

        # Mostrar los que quedan (no son alto)
        restantes = [t for t in tajos_validos if t not in datos["tajos_alto"]]
        alto_str  = ", ".join(datos["tajos_alto"]) if datos["tajos_alto"] else "ninguno"
        return (
            f"✅ *ALTO riesgo:* {alto_str}\n\n"
            f"¿Hay tajos de riesgo *MEDIO*?\n"
            f"Escribe los códigos separados por coma o *no*\n"
            f"_(Restantes: {len(restantes)} tajos)_\n"
        )

    # ── Tajos de riesgo MEDIO ─────────────────────────────────
    elif paso == "pt_riesgo_medio":
        tajos_procesados = datos.get("tajos_procesados", [])
        tajos_validos    = [t["tajo"] for t in tajos_procesados]
        tajos_alto       = datos.get("tajos_alto", [])
        disponibles      = [t for t in tajos_validos if t not in tajos_alto]

        if msg.lower() in ("no", "n", "ninguno", "ninguna"):
            datos["tajos_medio"] = []
        else:
            ingresados = [t.strip().upper() for t in msg.replace(";", ",").split(",") if t.strip()]
            no_encontrados = [t for t in ingresados if t not in disponibles]
            if no_encontrados:
                return (
                    f"❌ No encontré o ya son ALTO: *{', '.join(no_encontrados)}*\n"
                    f"Verifica los códigos o escribe *no*.\n"
                )
            datos["tajos_medio"] = ingresados

        # Resto = BAJO automáticamente
        tajos_bajo = [
            t for t in tajos_validos
            if t not in tajos_alto and t not in datos["tajos_medio"]
        ]
        datos["tajos_bajo"] = tajos_bajo
        actualizar_sesion(sid, "pt_confirmar", datos)

        # Calcular TMH por grupo
        tmh_alto  = _tmh_grupo(tajos_procesados, datos["tajos_alto"])
        tmh_medio = _tmh_grupo(tajos_procesados, datos["tajos_medio"])
        tmh_bajo  = _tmh_grupo(tajos_procesados, tajos_bajo)
        tmh_total = tmh_alto + tmh_medio + tmh_bajo

        medio_str = ", ".join(datos["tajos_medio"]) if datos["tajos_medio"] else "ninguno"

        return (
            f"✅ *MEDIO riesgo:* {medio_str}\n"
            f"✅ *BAJO riesgo:* {len(tajos_bajo)} tajos (por descarte)\n\n"
            f"📋 *RESUMEN FINAL*\n"
            f"{'─'*28}\n"
            f"📅 {MESES[datos['mes']].capitalize()} {datos['anio']} — {datos['tipo_envio']}\n"
            f"{'─'*28}\n"
            f"🔴 ALTO:  {len(datos['tajos_alto']):>3} tajos | {tmh_alto:>10,.0f} t\n"
            f"🟡 MEDIO: {len(datos['tajos_medio']):>3} tajos | {tmh_medio:>10,.0f} t\n"
            f"🟢 BAJO:  {len(tajos_bajo):>3} tajos | {tmh_bajo:>10,.0f} t\n"
            f"{'─'*28}\n"
            f"📦 TOTAL: {len(tajos_validos):>3} tajos | {tmh_total:>10,.0f} t\n"
            f"{'─'*28}\n"
            f"¿Confirmas? (*sí* / *no*)\n"
        )

    # ── Confirmación final ────────────────────────────────────
    elif paso == "pt_confirmar":
        if msg.lower() in ("no", "cancelar"):
            cerrar_sesion(usuario["id"])
            return "❌ Carga cancelada. Los datos no fueron guardados."
        if msg.lower() not in ("sí", "si", "ok", "yes", "s"):
            return "¿Confirmas? *sí* o *no*."

        return _guardar_plan(datos, usuario, sid)

    return "❓ Escribe *hola* para reiniciar."


# ══════════════════════════════════════════════════════════════
# PROCESAMIENTO CSV
# ══════════════════════════════════════════════════════════════

def _procesar_csv(ruta_local: str, datos: dict, sid: int, usuario: dict) -> str:
    """Lee el CSV, agrupa por tajo, pondera leyes por TONNES."""
    try:
        import csv
        from collections import defaultdict

        tajos_raw = defaultdict(lambda: {
            "tonnes": 0.0, "zn": 0.0, "pb": 0.0,
            "cu": 0.0, "ag": 0.0, "nsr": 0.0,
            "nivel": ""
        })

        with open(ruta_local, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            # Verificar columnas mínimas
            cols = [c.strip().upper() for c in (reader.fieldnames or [])]
            requeridas = {"LAYERS", "TONNES", "ZN", "PB", "CU", "AGOZ", "NSR25RES"}
            faltantes  = requeridas - set(cols)
            if faltantes:
                return (
                    f"❌ El CSV no tiene las columnas requeridas:\n"
                    f"Faltan: *{', '.join(faltantes)}*\n\n"
                    f"Columnas encontradas: {', '.join(cols[:8])}...\n"
                    f"Envía un CSV con el formato correcto."
                )

            filas_procesadas = 0
            filas_error      = 0

            for row in reader:
                try:
                    layers = row.get("LAYERS", "").strip()
                    if not layers:
                        continue

                    # Extraer tajo y nivel de LAYERS
                    # Formato: NIVEL_OREBODY_TAJO ej: 1550_OB1_T-021
                    tajo, nivel = _extraer_tajo_nivel(layers)
                    if not tajo:
                        continue

                    tonnes = float(row.get("TONNES", 0) or 0)
                    if tonnes <= 0:
                        continue

                    zn  = float(row.get("ZN",       0) or 0)
                    pb  = float(row.get("PB",       0) or 0)
                    cu  = float(row.get("CU",       0) or 0)
                    ag  = float(row.get("AGOZ",     0) or 0)
                    nsr = float(row.get("NSR25RES", 0) or 0)

                    # Acumular ponderado por TONNES
                    t = tajos_raw[tajo]
                    t["zn"]     += zn  * tonnes
                    t["pb"]     += pb  * tonnes
                    t["cu"]     += cu  * tonnes
                    t["ag"]     += ag  * tonnes
                    t["nsr"]    += nsr * tonnes
                    t["tonnes"] += tonnes
                    if not t["nivel"]:
                        t["nivel"] = nivel

                    filas_procesadas += 1

                except (ValueError, TypeError):
                    filas_error += 1
                    continue

        if not tajos_raw:
            return (
                "❌ No se encontraron datos válidos en el CSV.\n"
                "Verifica que el archivo tenga filas con TONNES > 0."
            )

        # Calcular leyes ponderadas finales
        tajos_procesados = []
        for tajo, t in sorted(tajos_raw.items()):
            tonnes = t["tonnes"]
            if tonnes <= 0:
                continue
            tajos_procesados.append({
                "tajo":   tajo,
                "nivel":  t["nivel"],
                "tmh":    tonnes / 1000,  # toneladas métricas
                "zn_pct": t["zn"]  / tonnes,
                "pb_pct": t["pb"]  / tonnes,
                "cu_pct": t["cu"]  / tonnes,
                "ag_oz":  t["ag"]  / tonnes,
                "nsr":    t["nsr"] / tonnes,
            })

        datos["tajos_procesados"] = tajos_procesados
        datos["filas_procesadas"] = filas_procesadas
        actualizar_sesion(sid, "pt_riesgo_alto", datos)

        # Resumen de tajos encontrados
        total_tmh = sum(t["tmh"] for t in tajos_procesados)
        n_tajos   = len(tajos_procesados)

        # Listar los primeros 15
        lista_tajos = ""
        for t in tajos_procesados[:15]:
            lista_tajos += (
                f"  • *{t['tajo']}* | {t['tmh']:,.0f} t | "
                f"Zn:{t['zn_pct']:.2f}% | NSR:{t['nsr']:.0f}\n"
            )
        if n_tajos > 15:
            lista_tajos += f"  _...y {n_tajos-15} más_\n"

        return (
            f"✅ *CSV procesado correctamente*\n"
            f"{'─'*28}\n"
            f"📊 Tajos encontrados: *{n_tajos}*\n"
            f"⚖️ TMH total: *{total_tmh:,.0f} t*\n"
            f"📋 Filas procesadas: {filas_procesadas}\n"
            f"{'─'*28}\n"
            f"{lista_tajos}"
            f"{'─'*28}\n"
            f"¿Hay tajos de riesgo *ALTO*?\n"
            f"Escribe los códigos separados por coma:\n"
            f"Ejemplo: T-015, T-007, T-570\n"
            f"O escribe *no* si ninguno es alto.\n"
        )

    except Exception as e:
        print(f"[PLAN_TAJOS] Error procesando CSV: {e}")
        import traceback
        traceback.print_exc()
        return f"⚠️ Error procesando el CSV: {str(e)[:100]}\nVerifica el formato del archivo."


def _extraer_tajo_nivel(layers: str) -> tuple:
    """
    Extrae tajo y nivel de LAYERS.
    Formato: NIVEL_OREBODY_TAJO  ej: 1550_OB1_T-021
    El tajo es la parte después del segundo guión bajo que empieza con T-
    """
    partes = layers.split("_")
    nivel  = partes[0] if partes else ""

    # Buscar la parte que empieza con T- o T
    tajo = None
    for i, p in enumerate(partes):
        if p.upper().startswith("T-") or (p.upper().startswith("T") and len(p) > 1):
            # Reconstruir el tajo completo (puede tener _ internos como T-081_2)
            tajo = "_".join(partes[i:])
            break

    return tajo, nivel


# ══════════════════════════════════════════════════════════════
# GUARDAR EN BD
# ══════════════════════════════════════════════════════════════

def _guardar_plan(datos: dict, usuario: dict, sid: int) -> str:
    """Guarda el plan en BD con los riesgos asignados."""
    try:
        mes          = datos["mes"]
        anio         = datos["anio"]
        tipo_envio   = datos["tipo_envio"]
        tajos_proc   = datos["tajos_procesados"]
        tajos_alto   = set(datos.get("tajos_alto", []))
        tajos_medio  = set(datos.get("tajos_medio", []))

        # Marcar anteriores del mismo mes/tipo como inactivos
        ejecutar(
            """UPDATE plan_tajos SET activo = FALSE
               WHERE mes = %s AND anio = %s AND tipo_envio = %s""",
            (mes, anio, tipo_envio)
        )

        # Insertar nuevos
        insertados = 0
        for t in tajos_proc:
            tajo = t["tajo"]
            if tajo in tajos_alto:
                riesgo = "ALTO"
            elif tajo in tajos_medio:
                riesgo = "MEDIO"
            else:
                riesgo = "BAJO"

            ejecutar(
                """INSERT INTO plan_tajos
                       (tajo, nivel, mes, anio, tipo_envio,
                        tmh, zn_pct, pb_pct, cu_pct, ag_oz, nsr,
                        riesgo, activo, creado_por)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s)""",
                (
                    tajo, t["nivel"], mes, anio, tipo_envio,
                    round(t["tmh"], 2),
                    round(t["zn_pct"], 4),
                    round(t["pb_pct"], 4),
                    round(t["cu_pct"], 4),
                    round(t["ag_oz"],  4),
                    round(t["nsr"],    2),
                    riesgo,
                    usuario["id"],
                )
            )
            insertados += 1

        cerrar_sesion(usuario["id"])

        alto_n  = len(tajos_alto)
        medio_n = len(tajos_medio)
        bajo_n  = insertados - alto_n - medio_n

        return (
            f"✅ *Plan de tajos guardado*\n"
            f"{'─'*28}\n"
            f"📅 {MESES[mes].capitalize()} {anio} — {tipo_envio}\n"
            f"📦 Total: *{insertados}* tajos\n"
            f"{'─'*28}\n"
            f"🔴 ALTO:  {alto_n} tajos\n"
            f"🟡 MEDIO: {medio_n} tajos\n"
            f"🟢 BAJO:  {bajo_n} tajos\n"
            f"{'─'*28}\n"
            f"👤 {usuario['nombre']}\n"
            f"📅 {fecha_hora_str()}\n\n"
            f"_(Consulta con: 'tajos de alto riesgo' o 'plan de mayo')_"
        )

    except Exception as e:
        print(f"[PLAN_TAJOS] Error guardando: {e}")
        import traceback
        traceback.print_exc()
        return f"⚠️ Error guardando el plan: {str(e)[:100]}"


# ══════════════════════════════════════════════════════════════
# CONSULTAS PÚBLICAS
# ══════════════════════════════════════════════════════════════

def consultar_tajos_riesgo(riesgo: str = None, usuario: dict = None) -> str:
    """
    Tajos de alto/medio riesgo del plan activo
    cruzados con sondajes matriculados.
    Si riesgo=None → muestra ALTO y MEDIO.
    """
    hoy  = hora_peru()
    mes  = hoy.month
    anio = hoy.year

    where_riesgo = ""
    params       = [mes, anio]
    if riesgo:
        where_riesgo = "AND pt.riesgo = %s"
        params.append(riesgo.upper())
    else:
        where_riesgo = "AND pt.riesgo IN ('ALTO','MEDIO')"

    rows = ejecutar(
        f"""SELECT pt.tajo, pt.riesgo, pt.tmh, pt.zn_pct, pt.nsr,
                   COUNT(s.id) as n_sondajes,
                   SUM(CASE WHEN s.estado_perforacion = 'EN_CURSO' THEN 1 ELSE 0 END) as en_perf,
                   SUM(CASE WHEN s.estado_perforacion = 'FINALIZADO' THEN 1 ELSE 0 END) as finalizados
            FROM plan_tajos pt
            LEFT JOIN sondajes s ON s.tajo_objetivo = pt.tajo
            WHERE pt.mes = %s AND pt.anio = %s AND pt.activo = TRUE
            {where_riesgo}
            GROUP BY pt.tajo, pt.riesgo, pt.tmh, pt.zn_pct, pt.nsr
            ORDER BY
                CASE pt.riesgo WHEN 'ALTO' THEN 1 WHEN 'MEDIO' THEN 2 ELSE 3 END,
                pt.nsr DESC""",
        params, fetchall=True
    ) or []

    if not rows:
        titulo = f"riesgo {riesgo}" if riesgo else "alto/medio riesgo"
        return (
            f"📋 No hay tajos de {titulo} en el plan activo "
            f"({MESES[mes]} {anio}).\n"
            f"¿Ya se cargó el plan? Escribe *cargar plan tajos*."
        )

    nombre_mes = MESES[mes].capitalize()
    lineas     = [f"⚠️ *TAJOS {('DE ' + riesgo) if riesgo else 'ALTO/MEDIO RIESGO'}*"]
    lineas.append(f"📅 {nombre_mes} {anio}\n{'─'*28}")

    icono_r = {"ALTO": "🔴", "MEDIO": "🟡", "BAJO": "🟢"}

    for r in rows:
        tajo, riesgo_t, tmh, zn, nsr, n_s, en_perf, finalizados = r
        icono  = icono_r.get(riesgo_t, "⬜")
        tmh_f  = float(tmh or 0)
        zn_f   = float(zn or 0)
        nsr_f  = float(nsr or 0)
        n_s    = int(n_s or 0)
        ep     = int(en_perf or 0)
        fin    = int(finalizados or 0)

        if n_s == 0:
            estado_ddh = "⛔ Sin DDH"
        elif ep > 0:
            estado_ddh = f"🔄 {ep} en perf."
        elif fin > 0:
            estado_ddh = f"✅ {fin} finalizado(s)"
        else:
            estado_ddh = f"📋 {n_s} matriculado(s)"

        lineas.append(
            f"\n{icono} *{tajo}* — {riesgo_t}\n"
            f"   TMH: {tmh_f:,.0f} t | Zn: {zn_f:.2f}% | NSR: {nsr_f:.0f}\n"
            f"   DDH: {estado_ddh}"
        )

    lineas.append(f"\n{'─'*28}\n📅 {fecha_hora_str()}")
    return "\n".join(lineas)


def consultar_plan_mes(mes: int = None, anio: int = None,
                       usuario: dict = None) -> str:
    """Resumen del plan activo del mes."""
    hoy  = hora_peru()
    mes  = mes  or hoy.month
    anio = anio or hoy.year

    rows = ejecutar(
        """SELECT riesgo, COUNT(*), SUM(tmh), AVG(zn_pct), AVG(nsr)
           FROM plan_tajos
           WHERE mes = %s AND anio = %s AND activo = TRUE
           GROUP BY riesgo
           ORDER BY CASE riesgo WHEN 'ALTO' THEN 1 WHEN 'MEDIO' THEN 2 ELSE 3 END""",
        (mes, anio), fetchall=True
    ) or []

    if not rows:
        return (
            f"📋 No hay plan cargado para *{MESES[mes]} {anio}*.\n"
            f"El geólogo puede cargarlo con: *cargar plan tajos*"
        )

    total_tajos = sum(int(r[1] or 0) for r in rows)
    total_tmh   = sum(float(r[2] or 0) for r in rows)
    nombre_mes  = MESES[mes].capitalize()
    icono_r     = {"ALTO": "🔴", "MEDIO": "🟡", "BAJO": "🟢"}

    lineas = [
        f"📊 *PLAN TAJOS — {nombre_mes.upper()} {anio}*\n"
        f"{'─'*28}"
    ]
    for r in rows:
        riesgo_t, n, tmh, zn_avg, nsr_avg = r
        pct = float(tmh or 0) / total_tmh * 100 if total_tmh > 0 else 0
        lineas.append(
            f"{icono_r.get(riesgo_t,'⬜')} *{riesgo_t}*: "
            f"{int(n or 0)} tajos | {float(tmh or 0):,.0f} t ({pct:.0f}%)\n"
            f"   Zn prom: {float(zn_avg or 0):.2f}% | NSR prom: {float(nsr_avg or 0):.0f}"
        )

    lineas.append(
        f"\n{'─'*28}\n"
        f"📦 Total: *{total_tajos}* tajos | *{total_tmh:,.0f} t*\n"
        f"📅 {fecha_hora_str()}"
    )
    return "\n".join(lineas)


def consultar_leyes_tajo(tajo: str, usuario: dict = None) -> str:
    """Ficha de leyes de un tajo específico del plan activo."""
    hoy  = hora_peru()

    row = ejecutar(
        """SELECT pt.tajo, pt.nivel, pt.mes, pt.anio, pt.tipo_envio,
                  pt.tmh, pt.zn_pct, pt.pb_pct, pt.cu_pct, pt.ag_oz,
                  pt.nsr, pt.riesgo,
                  COUNT(s.id) as n_sondajes,
                  SUM(CASE WHEN s.estado_perforacion='EN_CURSO' THEN 1 ELSE 0 END) as en_perf,
                  SUM(CASE WHEN s.estado_perforacion='FINALIZADO' THEN 1 ELSE 0 END) as finalizados,
                  SUM(COALESCE(s.profundidad_final,0)) as metros_tot
           FROM plan_tajos pt
           LEFT JOIN sondajes s ON UPPER(s.tajo_objetivo) = UPPER(pt.tajo)
           WHERE UPPER(pt.tajo) = UPPER(%s) AND pt.activo = TRUE
           GROUP BY pt.tajo, pt.nivel, pt.mes, pt.anio, pt.tipo_envio,
                    pt.tmh, pt.zn_pct, pt.pb_pct, pt.cu_pct, pt.ag_oz,
                    pt.nsr, pt.riesgo
           ORDER BY pt.anio DESC, pt.mes DESC
           LIMIT 1""",
        (tajo,), fetchone=True
    )

    if not row:
        return (
            f"❌ No encontré el tajo *{tajo}* en el plan activo.\n"
            f"Verifica el código o carga el plan primero."
        )

    (tajo_n, nivel, mes, anio, tipo, tmh, zn, pb, cu, ag, nsr,
     riesgo_t, n_s, en_perf, finalizados, metros_tot) = row

    icono_r = {"ALTO": "🔴", "MEDIO": "🟡", "BAJO": "🟢"}
    nombre_mes = MESES[int(mes)].capitalize() if mes else "—"

    # Sondajes vinculados
    sondajes_rows = ejecutar(
        """SELECT s.bhid, s.estado_perforacion,
                  COALESCE(s.profundidad_final,0) as final,
                  COALESCE(s.profundidad_prog,0) as prog
           FROM sondajes s
           WHERE UPPER(s.tajo_objetivo) = UPPER(%s)
           ORDER BY s.bhid
           LIMIT 10""",
        (tajo_n,), fetchall=True
    ) or []

    ddh_str = ""
    if sondajes_rows:
        for s in sondajes_rows:
            bhid, estado, final, prog = s
            pct = f"{float(final)/float(prog)*100:.0f}%" if float(prog) > 0 else "—"
            est_icon = {"EN_CURSO": "🔄", "FINALIZADO": "✅", "PLANIFICADO": "⏳"}.get(
                str(estado), "⏳")
            ddh_str += f"  {est_icon} *{bhid}* | {float(final):.1f}/{float(prog):.1f}m ({pct})\n"
    else:
        ddh_str = "  _(Sin sondajes matriculados)_\n"

    return (
        f"🎯 *Tajo {tajo_n}* — Nv.{nivel}\n"
        f"{'─'*30}\n"
        f"📅 Plan: {nombre_mes} {anio} | {tipo}\n"
        f"{icono_r.get(riesgo_t,'⬜')} Riesgo: *{riesgo_t}*\n"
        f"{'─'*30}\n"
        f"⚖️ *Recursos:*\n"
        f"   TMH:    {float(tmh or 0):>10,.0f} t\n"
        f"   Zn(%):  {float(zn  or 0):>10.3f}\n"
        f"   Pb(%):  {float(pb  or 0):>10.3f}\n"
        f"   Cu(%):  {float(cu  or 0):>10.3f}\n"
        f"   Ag(oz): {float(ag  or 0):>10.3f}\n"
        f"   NSR($): {float(nsr or 0):>10.0f}\n"
        f"{'─'*30}\n"
        f"⛏️ *Sondajes DDH ({int(n_s or 0)}):*\n"
        f"{ddh_str}"
        f"{'─'*30}\n"
        f"📅 {fecha_hora_str()}"
    )


def tajos_criticos_sin_perforar(usuario: dict = None) -> str:
    """Tajos ALTO riesgo sin ningún sondaje activo en perforación."""
    hoy  = hora_peru()
    mes  = hoy.month
    anio = hoy.year

    rows = ejecutar(
        """SELECT pt.tajo, pt.tmh, pt.zn_pct, pt.nsr,
                  COUNT(s.id) as total_ddh,
                  SUM(CASE WHEN s.estado_perforacion='EN_CURSO' THEN 1 ELSE 0 END) as en_perf
           FROM plan_tajos pt
           LEFT JOIN sondajes s ON UPPER(s.tajo_objetivo) = UPPER(pt.tajo)
           WHERE pt.mes = %s AND pt.anio = %s
             AND pt.activo = TRUE AND pt.riesgo = 'ALTO'
           GROUP BY pt.tajo, pt.tmh, pt.zn_pct, pt.nsr
           HAVING SUM(CASE WHEN s.estado_perforacion='EN_CURSO' THEN 1 ELSE 0 END) = 0
           ORDER BY pt.nsr DESC""",
        (mes, anio), fetchall=True
    ) or []

    if not rows:
        return (
            f"✅ No hay tajos ALTO riesgo sin perforación activa\n"
            f"para {MESES[mes]} {anio}."
        )

    nombre_mes = MESES[mes].capitalize()
    lineas     = [
        f"🚨 *TAJOS CRÍTICOS SIN PERFORAR*\n"
        f"📅 {nombre_mes} {anio}\n{'─'*28}"
    ]

    for r in rows:
        tajo, tmh, zn, nsr, total_ddh, _ = r
        ddh_str = f"⛔ Sin DDH" if int(total_ddh or 0) == 0 else f"📋 {int(total_ddh)} matriculado(s)"
        lineas.append(
            f"\n🔴 *{tajo}*\n"
            f"   TMH: {float(tmh or 0):,.0f} t | Zn: {float(zn or 0):.2f}% | NSR: {float(nsr or 0):.0f}\n"
            f"   {ddh_str}"
        )

    lineas.append(f"\n{'─'*28}\n📅 {fecha_hora_str()}")
    return "\n".join(lineas)


# ══════════════════════════════════════════════════════════════
# HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════

def _parsear_mes_anio(msg: str) -> tuple | None:
    """Parsea 'mayo 2026', '5 2026', '05/2026' → (5, 2026)."""
    import re
    msg = msg.strip().lower()

    nombres_mes = {
        "enero":1,"febrero":2,"marzo":3,"abril":4,
        "mayo":5,"junio":6,"julio":7,"agosto":8,
        "septiembre":9,"octubre":10,"noviembre":11,"diciembre":12
    }

    # Buscar nombre de mes
    for nombre, num in nombres_mes.items():
        if nombre in msg:
            anio_match = re.search(r"\d{4}", msg)
            anio = int(anio_match.group()) if anio_match else hora_peru().year
            return (num, anio)

    # Formato numérico: "5 2026" o "05/2026" o "5/2026"
    match = re.search(r"(\d{1,2})[/\s\-](\d{4})", msg)
    if match:
        mes  = int(match.group(1))
        anio = int(match.group(2))
        if 1 <= mes <= 12:
            return (mes, anio)

    # Solo número 1-12 (asume año actual)
    match2 = re.match(r"^(\d{1,2})$", msg)
    if match2:
        mes = int(match2.group(1))
        if 1 <= mes <= 12:
            return (mes, hora_peru().year)

    return None


def _tmh_grupo(tajos_procesados: list, tajos_grupo: list) -> float:
    """Suma TMH de los tajos del grupo."""
    grupo_set = set(tajos_grupo)
    return sum(
        t["tmh"] for t in tajos_procesados
        if t["tajo"] in grupo_set
    )
