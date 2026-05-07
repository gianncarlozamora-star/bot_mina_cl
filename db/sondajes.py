from db.conexion import ejecutar, ejecutar_dict
from config import hora_peru

# ── BÚSQUEDA ──────────────────────────────────────────────────

def buscar_sondaje(texto: str) -> dict | None:
    texto = texto.strip().upper().replace(" ", "")
    
    # Extraer últimos 4 dígitos
    digitos = ''.join(filter(str.isdigit, texto))
    ultimos4 = digitos[-4:] if len(digitos) >= 4 else digitos

    # Buscar en tabla directa, no en vista
    row = ejecutar(
        """SELECT s.bhid, sc.nombre, s.tajo_objetivo, s.cuerpo_objetivo,
                  s.campana, m.codigo, e.codigo,
                  s.profundidad_prog, s.profundidad_final,
                  CASE WHEN s.profundidad_prog > 0 
                       THEN ROUND((COALESCE(s.profundidad_final,0) / s.profundidad_prog * 100)::numeric, 1)
                       ELSE 0 END,
                  s.diametro, s.nivel_prog, s.labor,
                  s.estado_logueo, s.estado_muestreo, s.estado_rqd,
                  s.estado_fotografia, s.estado_densidad,
                  s.estado_laboratorio, s.estado_modelado,
                  s.fecha_inicio_perf, s.fecha_fin_perf, s.id
           FROM sondajes s
           JOIN cat_subcategorias sc ON s.subcategoria_id = sc.id
           JOIN cat_maquinas m ON s.maquina_id = m.id
           JOIN cat_empresas e ON s.empresa_id = e.id
           WHERE s.bhid LIKE %s
           LIMIT 1""",
        (f"%{ultimos4}",), fetchone=True
    )
    if not row:
        return None
    
    cols = ["bhid","subcategoria","tajo_objetivo","cuerpo_objetivo",
            "campana","maquina","empresa","prog_m","final_m","avance_pct",
            "diametro","nivel","labor","estado_logueo","estado_muestreo",
            "estado_rqd","estado_fotografia","estado_densidad",
            "estado_laboratorio","estado_modelado",
            "fecha_inicio_perf","fecha_fin_perf","id"]
    return dict(zip(cols, row))

def _row_to_dict(row) -> dict:
    cols = [
        "bhid", "subcategoria", "tajo_objetivo", "cuerpo_objetivo",
        "campana", "maquina", "empresa", "prog_m", "final_m",
        "avance_pct", "diametro", "nivel", "labor",
        "estado_logueo", "estado_muestreo", "estado_rqd",
        "estado_fotografia", "estado_densidad", "estado_laboratorio",
        "estado_modelado", "fecha_inicio_perf", "fecha_fin_perf"
    ]
    return dict(zip(cols, row))

def obtener_sondaje_completo(bhid: str) -> dict | None:
    row = ejecutar_dict(
        "SELECT * FROM sondajes WHERE bhid = %s", (bhid,), fetchone=True
    )
    return row

def sondajes_por_tajo(tajo: str) -> list:
    rows = ejecutar(
        """SELECT bhid, prog_m, final_m, avance_pct,
                  estado_logueo, estado_laboratorio, estado_modelado,
                  maquina, empresa
           FROM v_estado_sondajes
           WHERE UPPER(tajo_objetivo) = UPPER(%s)
           ORDER BY bhid""",
        (tajo,), fetchall=True
    )
    return rows

def sondajes_por_objetivo(objetivo: str) -> list:
    """Para gerencia: cuántos DDH se han perforado al objetivo X."""
    rows = ejecutar(
        """SELECT bhid, subcategoria, prog_m, final_m, avance_pct,
                  estado_logueo, estado_laboratorio, estado_modelado,
                  maquina, empresa, tajo_objetivo, cuerpo_objetivo
           FROM v_estado_sondajes
           WHERE UPPER(tajo_objetivo)  LIKE UPPER(%s)
              OR UPPER(cuerpo_objetivo) LIKE UPPER(%s)
           ORDER BY bhid""",
        (f"%{objetivo}%", f"%{objetivo}%"), fetchall=True
    )
    return rows

def resumen_campana(campana: str = None) -> dict:
    filtro = "WHERE s.campana = %s" if campana else ""
    params = (campana,) if campana else ()
    row = ejecutar(
        f"""SELECT
               COUNT(*)                                                    AS total,
               COUNT(*) FILTER (WHERE s.profundidad_final IS NOT NULL)    AS perforados,
               COALESCE(SUM(s.profundidad_final), 0)                      AS metros_perforados,
               COALESCE(SUM(s.profundidad_prog), 0)                       AS metros_prog,
               COUNT(*) FILTER (WHERE s.estado_logueo     = 'COMPLETADO') AS logueados,
               COUNT(*) FILTER (WHERE s.estado_muestreo   = 'COMPLETADO') AS muestreados,
               COUNT(*) FILTER (WHERE s.estado_laboratorio= 'COMPLETADO') AS con_leyes,
               COUNT(*) FILTER (WHERE s.estado_modelado   = 'COMPLETADO') AS modelados
           FROM sondajes s
           JOIN cat_subcategorias sc ON s.subcategoria_id = sc.id
           WHERE sc.fase_activa = TRUE {('AND s.campana = %s' if campana else '')}""",
        params, fetchone=True
    )
    if not row:
        return {}
    cols = ["total","perforados","metros_perforados","metros_prog",
            "logueados","muestreados","con_leyes","modelados"]
    return dict(zip(cols, row))

# ── MATRICULACIÓN ─────────────────────────────────────────────

def matricular_sondaje(datos: dict, usuario_id: int) -> str:
    """
    Inserta un nuevo sondaje. Retorna el BHID generado.
    datos debe contener todos los campos requeridos.
    """
    row = ejecutar(
        """INSERT INTO sondajes (
               bhid, es_provisional,
               categoria_id, subcategoria_id, campana,
               tajo_objetivo, cuerpo_objetivo, profundidad_prog,
               azimut_prog, dip_prog, nivel_prog, labor, diametro,
               empresa_id, maquina_id, matriculado_por
           ) VALUES (
               %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
           )
           ON CONFLICT (bhid) DO NOTHING
           RETURNING bhid""",
        (
            datos["bhid"], datos.get("es_provisional", False),
            datos["categoria_id"], datos["subcategoria_id"],
            datos.get("campana"),
            datos.get("tajo_objetivo"), datos.get("cuerpo_objetivo"),
            datos["profundidad_prog"],
            datos.get("azimut_prog"), datos.get("dip_prog"),
            datos.get("nivel_prog"), datos.get("labor"),
            datos.get("diametro", "NQ"),
            datos["empresa_id"], datos["maquina_id"],
            usuario_id,
        ),
        fetchone=True
    )
    return row[0] if row else None

def vincular_provisional(bhid_provisional: str, bhid_definitivo: str) -> bool:
    """Vincula un BHID provisional con el código definitivo asignado."""
    rows = ejecutar(
        """UPDATE sondajes
           SET bhid = %s, es_provisional = FALSE, bhid_definitivo = %s
           WHERE bhid = %s""",
        (bhid_definitivo, bhid_definitivo, bhid_provisional)
    )
    return rows > 0

def siguiente_bhid(prefijo: str = "PECLD") -> str:
    """Sugiere el siguiente código DDH basado en el máximo existente."""
    row = ejecutar(
        """SELECT MAX(CAST(SUBSTRING(bhid FROM '[0-9]+$') AS INTEGER))
           FROM sondajes WHERE bhid LIKE %s""",
        (f"{prefijo}%",), fetchone=True
    )
    siguiente = (row[0] or 0) + 1
    return f"{prefijo}{siguiente:05d}"

# ── ACTUALIZACIÓN DE ETAPAS ───────────────────────────────────

MAPA_ETAPAS = {
    "logueo":      "estado_logueo",
    "muestreo":    "estado_muestreo",
    "rqd":         "estado_rqd",
    "fotografia":  "estado_fotografia",
    "densidad":    "estado_densidad",
    "laboratorio": "estado_laboratorio",
    "modelado":    "estado_modelado",
}

def actualizar_estado_etapa(bhid: str, etapa: str, estado: str) -> bool:
    campo = MAPA_ETAPAS.get(etapa.lower())
    if not campo:
        return False
    rows = ejecutar(
        f"UPDATE sondajes SET {campo} = %s WHERE bhid = %s",
        (estado.upper(), bhid)
    )
    return rows > 0

# ── CATÁLOGOS PARA FORMULARIOS ────────────────────────────────

def obtener_subcategorias_activas() -> list:
    rows = ejecutar(
        """SELECT sc.id, sc.codigo, sc.nombre, sc.clasificacion_ddh
           FROM cat_subcategorias sc
           JOIN cat_categorias c ON sc.categoria_id = c.id
           WHERE sc.fase_activa = TRUE AND c.codigo = 'OPE'
           ORDER BY sc.id""",
        fetchall=True
    )
    return [{"id": r[0], "codigo": r[1], "nombre": r[2], "clasificacion": r[3]}
            for r in rows]

def obtener_maquinas_con_empresa() -> list:
    rows = ejecutar(
        """SELECT m.id, m.codigo, e.codigo AS empresa, e.id AS empresa_id
           FROM cat_maquinas m
           JOIN cat_empresas e ON m.empresa_id = e.id
           WHERE m.activo = TRUE
           ORDER BY e.codigo, m.codigo""",
        fetchall=True
    )
    return [{"id": r[0], "codigo": r[1], "empresa": r[2], "empresa_id": r[3]}
            for r in rows]

def obtener_tarifa(diametro: str, metros: float, sufijo: str) -> float | None:
    row = ejecutar(
        "SELECT fn_get_tarifa(%s, %s, %s)",
        (diametro, metros, sufijo), fetchone=True
    )
    return float(row[0]) if row and row[0] else None

def calcular_valor_turno(diametro: str, prof_inicio: float,
                          prof_final: float, sufijo: str) -> float:
    """
    Calcula el valor USD de un turno considerando que puede cruzar tramos.
    Divide los metros por tramo tarifario y suma el costo total.
    """
    total = 0.0
    metro_actual = prof_inicio

    while metro_actual < prof_final:
        tarifa_row = ejecutar(
            """SELECT precio_usd, tramo_hasta
               FROM cat_tarifas
               WHERE diametro = %s AND sufijo = %s
                 AND %s >= tramo_desde AND %s < tramo_hasta
                 AND fase_activa = TRUE
               LIMIT 1""",
            (diametro, sufijo, int(metro_actual), int(metro_actual)), fetchone=True
        )
        if not tarifa_row:
            break
        precio, tramo_hasta = float(tarifa_row[0]), float(tarifa_row[1])
        metros_en_tramo = min(prof_final, tramo_hasta) - metro_actual
        total += metros_en_tramo * precio
        metro_actual = tramo_hasta

    metro_actual = float(tramo_hasta)
