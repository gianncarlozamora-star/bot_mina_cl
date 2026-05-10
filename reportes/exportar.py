"""
EXPORTACIÓN A EXCEL — Historia por Tajo
Agrega la función generar_historia_tajo() al exportar.py existente.
Pega este bloque al final de reportes/exportar.py (antes del EOF).
"""

# ══════════════════════════════════════════════════════════════
# NUEVA FUNCIÓN — pegar al final de reportes/exportar.py
# ══════════════════════════════════════════════════════════════

def listar_tajos_disponibles() -> list[dict]:
    """
    Retorna todos los tajos/cuerpos que tienen sondajes activos.
    Usado para el menú interactivo de selección.
    Formato: [{"tajo": "T-008", "total": 5, "metros": 1234.5}, ...]
    """
    rows = ejecutar(
        """SELECT
               COALESCE(s.tajo_objetivo, s.cuerpo_objetivo, 'SIN TAJO') AS tajo,
               COUNT(*)                                                  AS total,
               COALESCE(SUM(s.profundidad_final), 0)                    AS metros
           FROM sondajes s
           JOIN cat_subcategorias sc ON s.subcategoria_id = sc.id
           WHERE sc.fase_activa = TRUE
             AND COALESCE(s.tajo_objetivo, s.cuerpo_objetivo) IS NOT NULL
           GROUP BY 1
           ORDER BY 1""",
        fetchall=True
    )
    return [
        {"tajo": r[0], "total": r[1], "metros": float(r[2] or 0)}
        for r in (rows or [])
    ]


def generar_historia_tajo(tajo: str) -> bytes | None:
    """
    Genera Excel con una fila por sondaje del tajo indicado.

    Columnas:
        BHID | SUBCATEGORÍA | TAJO/CUERPO | NIVEL | LABOR | MÁQUINA | E.E.
        DIÁMETRO | PROG (m) | PERFORADO (m) | % AV
        PERFORACIÓN | LOGUEO | MUESTREO | RQD | FOTOGRAFÍA | DENSIDAD
        LABORATORIO | MODELADO | ESTIMACIÓN
        BATCH | Nº ENVÍO

    Colores semáforo por estado:
        COMPLETADO → verde   (#C6EFCE / #375623 texto)
        EN_PROCESO → amarillo (#FFEB9C / #7D6608 texto)
        PENDIENTE  → rojo    (#FFCCCC / #9C0006 texto)
        NO_APLICA  → gris    (#D9D9D9)
    """
    if not OPENPYXL_OK:
        return None

    # ── QUERY PRINCIPAL ───────────────────────────────────────
    rows = ejecutar(
        """SELECT
               s.bhid,
               sc.nombre                                              AS subcategoria,
               COALESCE(s.tajo_objetivo, s.cuerpo_objetivo, '—')     AS tajo_cuerpo,
               COALESCE(s.nivel_prog, '—')                           AS nivel,
               COALESCE(s.labor, '—')                                AS labor,
               COALESCE(m.codigo, '—')                               AS maquina,
               COALESCE(e.codigo, '—')                               AS empresa,
               COALESCE(s.diametro, '—')                             AS diametro,
               COALESCE(s.profundidad_prog,  0)                      AS prog_m,
               COALESCE(s.profundidad_final, 0)                      AS final_m,
               CASE
                   WHEN COALESCE(s.profundidad_prog, 0) > 0
                   THEN ROUND(
                       (COALESCE(s.profundidad_final,0) /
                        s.profundidad_prog * 100)::numeric, 1)
                   ELSE 0
               END                                                    AS avance_pct,
               COALESCE(s.estado_perforacion, 'PENDIENTE')           AS est_perf,
               COALESCE(s.estado_logueo,      'PENDIENTE')           AS est_log,
               COALESCE(s.estado_muestreo,    'PENDIENTE')           AS est_mues,
               COALESCE(s.estado_rqd,         'PENDIENTE')           AS est_rqd,
               COALESCE(s.estado_fotografia,  'PENDIENTE')           AS est_foto,
               COALESCE(s.estado_densidad,    'PENDIENTE')           AS est_dens,
               COALESCE(s.estado_laboratorio, 'PENDIENTE')           AS est_lab,
               COALESCE(s.estado_modelado,    'PENDIENTE')           AS est_mod,
               COALESCE(s.estado_estimacion,  'PENDIENTE')           AS est_est,
               -- Batch más reciente vinculado
               (SELECT lc.numero_batch
                FROM batch_sondajes bs
                JOIN laboratorio_certimin lc ON bs.batch_id = lc.id
                WHERE bs.sondaje_id = s.id
                ORDER BY bs.id DESC LIMIT 1)                         AS batch,
               (SELECT bs2.numero_envio
                FROM batch_sondajes bs2
                WHERE bs2.sondaje_id = s.id
                ORDER BY bs2.id DESC LIMIT 1)                        AS num_envio
           FROM sondajes s
           JOIN cat_subcategorias sc ON s.subcategoria_id = sc.id
           LEFT JOIN cat_maquinas  m  ON s.maquina_id     = m.id
           LEFT JOIN cat_empresas  e  ON m.empresa_id     = e.id
           WHERE sc.fase_activa = TRUE
             AND (
                 UPPER(s.tajo_objetivo)  ILIKE %s
              OR UPPER(s.cuerpo_objetivo) ILIKE %s
             )
           ORDER BY s.bhid""",
        (f"%{tajo.upper()}%", f"%{tajo.upper()}%"),
        fetchall=True
    )

    if not rows:
        return None  # sin datos — el router avisa al usuario

    # ── WORKBOOK ──────────────────────────────────────────────
    wb = Workbook()
    ws = wb.active
    ws.title = f"Tajo_{tajo[:20]}"

    # Estilos base
    header_font  = Font(bold=True, color="FFFFFF", size=10)
    header_fill  = PatternFill("solid", start_color="1F4E79")
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    right_align  = Alignment(horizontal="right",  vertical="center")
    thin_border  = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"),  bottom=Side(style="thin")
    )

    # Semáforo — (fondo, texto)
    SEMAFORO = {
        "COMPLETADO": ("C6EFCE", "375623"),
        "EN_PROCESO": ("FFEB9C", "7D6608"),
        "PENDIENTE":  ("FFCCCC", "9C0006"),
        "NO_APLICA":  ("D9D9D9", "595959"),
        "GYRO":       ("C6EFCE", "375623"),
        "OK":         ("C6EFCE", "375623"),
        "NO_REALIZADO":("FFCCCC","9C0006"),
    }

    # Etiquetas legibles
    ETIQUETA = {
        "COMPLETADO":  "✔ OK",
        "EN_PROCESO":  "▶ En curso",
        "PENDIENTE":   "✘ Pendiente",
        "NO_APLICA":   "— N/A",
        "GYRO":        "✔ GYRO",
        "OK":          "✔ OK",
        "NO_REALIZADO":"✘ No realiz.",
    }

    # ── FILA TÍTULO ───────────────────────────────────────────
    ws.merge_cells("A1:V1")
    titulo_cell = ws.cell(1, 1,
        f"HISTORIA TAJO / CUERPO: {tajo.upper()}  —  "
        f"Generado: {hora_peru().strftime('%d/%m/%Y %H:%M')} (hora Perú)")
    titulo_cell.font      = Font(bold=True, size=12, color="FFFFFF")
    titulo_cell.fill      = PatternFill("solid", start_color="1F4E79")
    titulo_cell.alignment = center_align
    ws.row_dimensions[1].height = 22

    # ── ENCABEZADOS (fila 2) ──────────────────────────────────
    HEADERS = [
        # Identificación
        "BHID", "SUBCATEGORÍA", "TAJO / CUERPO", "NIVEL", "LABOR",
        "MÁQUINA", "E.E.", "DIÁMETRO",
        # Perforación
        "PROG (m)", "PERFORADO (m)", "AVANCE %",
        # Estados (semáforo)
        "PERFORACIÓN", "LOGUEO", "MUESTREO", "RQD",
        "FOTOGRAFÍA", "DENSIDAD", "LABORATORIO", "MODELADO", "ESTIMACIÓN",
        # Batch
        "BATCH", "Nº ENVÍO",
    ]

    # Anchos de columna (en caracteres)
    COL_WIDTHS = [
        12, 18, 16, 10, 14,
        12, 14, 10,
        10, 13, 10,
        13, 12, 12, 10,
        12, 11, 13, 12, 13,
        12, 10,
    ]

    for col_num, (h, w) in enumerate(zip(HEADERS, COL_WIDTHS), 1):
        cell = ws.cell(2, col_num, h)
        cell.font      = header_font
        cell.fill      = header_fill
        cell.alignment = center_align
        cell.border    = thin_border
        ws.column_dimensions[get_column_letter(col_num)].width = w
    ws.row_dimensions[2].height = 30

    # Índices de columnas de estado (1-based, fila de datos)
    # Columnas 12-20 son los 9 estados
    COL_ESTADOS_START = 12  # PERFORACIÓN
    COL_ESTADOS_END   = 20  # ESTIMACIÓN

    # ── DATOS (desde fila 3) ──────────────────────────────────
    fill_par   = PatternFill("solid", start_color="EBF3FB")
    fill_impar = PatternFill("solid", start_color="FFFFFF")

    for row_num, row in enumerate(rows, 3):
        (bhid, subcat, tajo_c, nivel, labor, maquina, empresa, diametro,
         prog, final, avpct,
         est_perf, est_log, est_mues, est_rqd, est_foto, est_dens,
         est_lab, est_mod, est_est,
         batch, num_envio) = row

        fill_base = fill_par if row_num % 2 == 0 else fill_impar

        estados = [est_perf, est_log, est_mues, est_rqd, est_foto,
                   est_dens, est_lab, est_mod, est_est]

        ws_row = [
            bhid, subcat, tajo_c, nivel, labor,
            maquina, empresa, diametro,
            float(prog or 0), float(final or 0), float(avpct or 0),
        ] + [ETIQUETA.get(str(e or "PENDIENTE"), str(e or "—")) for e in estados] + [
            batch or "—",
            int(num_envio) if num_envio else "—",
        ]

        ws.append(ws_row)
        ws.row_dimensions[row_num].height = 18

        for col_num in range(1, len(ws_row) + 1):
            cell = ws.cell(row_num, col_num)
            cell.border = thin_border

            # Columnas de estado → semáforo
            if COL_ESTADOS_START <= col_num <= COL_ESTADOS_END:
                estado_raw = str(estados[col_num - COL_ESTADOS_START] or "PENDIENTE")
                fondo, texto = SEMAFORO.get(estado_raw, ("FFFFFF", "000000"))
                cell.fill      = PatternFill("solid", start_color=fondo)
                cell.font      = Font(bold=True, color=texto, size=9)
                cell.alignment = center_align

            # Columnas numéricas
            elif col_num in (9, 10):   # prog, final
                cell.number_format = "#,##0.00"
                cell.alignment     = right_align
                cell.fill          = fill_base
            elif col_num == 11:        # avance %
                cell.number_format = "#,##0.0"
                cell.alignment     = right_align
                cell.fill          = fill_base
                # Colorear % avance: verde > 80, amarillo 40-80, rojo < 40
                pct = float(avpct or 0)
                if pct >= 80:
                    cell.fill = PatternFill("solid", start_color="C6EFCE")
                elif pct >= 40:
                    cell.fill = PatternFill("solid", start_color="FFEB9C")
                else:
                    cell.fill = PatternFill("solid", start_color="FFCCCC")
            else:
                cell.fill      = fill_base
                cell.alignment = center_align

    # ── FILA TOTALES ──────────────────────────────────────────
    total_row = ws.max_row + 1
    total_font = Font(bold=True, size=10)

    ws.cell(total_row, 1, f"TOTAL: {len(rows)} sondajes").font = total_font
    ws.cell(total_row, 1).fill = PatternFill("solid", start_color="D6E4F0")

    for col in (9, 10):   # PROG y PERFORADO
        col_l = get_column_letter(col)
        cell  = ws.cell(total_row, col,
                        f"=SUM({col_l}3:{col_l}{total_row-1})")
        cell.font          = total_font
        cell.number_format = "#,##0.00"
        cell.fill          = PatternFill("solid", start_color="D6E4F0")
        cell.border        = thin_border

    # Avance % promedio
    col_av = get_column_letter(11)
    cell_av = ws.cell(total_row, 11,
                      f"=AVERAGE({col_av}3:{col_av}{total_row-1})")
    cell_av.font          = total_font
    cell_av.number_format = "#,##0.0"
    cell_av.fill          = PatternFill("solid", start_color="D6E4F0")
    cell_av.border        = thin_border

    # Contar COMPLETADO por columna de estado
    for idx, col_num in enumerate(range(COL_ESTADOS_START, COL_ESTADOS_END + 1)):
        completados = sum(
            1 for row in rows
            if str(row[11 + idx] or "PENDIENTE") == "COMPLETADO"
        )
        cell = ws.cell(total_row, col_num,
                       f"{completados}/{len(rows)}")
        cell.font      = total_font
        cell.fill      = PatternFill("solid", start_color="D6E4F0")
        cell.alignment = Alignment(horizontal="center")
        cell.border    = thin_border

    # ── CONGELAR CABECERAS ────────────────────────────────────
    ws.freeze_panes = "A3"

    # ── AUTOFILTER ────────────────────────────────────────────
    ws.auto_filter.ref = f"A2:{get_column_letter(len(HEADERS))}2"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
