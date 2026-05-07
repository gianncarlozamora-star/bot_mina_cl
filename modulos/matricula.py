"""
FLUJO DE MATRICULACIÓN DE SONDAJES
Solo para rol GEOLOGO.
Pasos: tipo → objetivo → profundidad → orientación → ubicación →
       máquina → diámetro → confirmación → registro
"""
from db.sesiones import crear_sesion, actualizar_sesion, cerrar_sesion
from db.sondajes import (matricular_sondaje, obtener_subcategorias_activas,
                          obtener_maquinas_con_empresa, siguiente_bhid,
                          buscar_sondaje)
from config import fecha_hora_str

FLUJO = "MATRICULA"

# ── MENÚ INICIAL ──────────────────────────────────────────────

def iniciar(usuario: dict, sesion_id: int) -> str:
    subcat = obtener_subcategorias_activas()
    menu = "\n".join([f"  *{i+1}* — {s['nombre']}" for i, s in enumerate(subcat)])
    actualizar_sesion(sesion_id, "tipo_sondaje",
                      {"subcat_opciones": [s["codigo"] for s in subcat],
                       "subcat_ids": [s["id"] for s in subcat]})
    return (
        f"📋 *MATRICULACIÓN DE SONDAJE*\n"
        f"📅 {fecha_hora_str()}\n\n"
        f"¿Qué tipo de sondaje vas a registrar?\n\n"
        f"{menu}\n\n"
        f"Responde con el número."
    )

# ── PROCESADOR PRINCIPAL ──────────────────────────────────────

def procesar(mensaje: str, usuario: dict, sesion: dict) -> str:
    paso  = sesion["paso"]
    datos = sesion["datos"]
    sid   = sesion["id"]
    msg   = mensaje.strip()

    # ── PASO 1: Tipo de sondaje ───────────────────────────────
    if paso == "tipo_sondaje":
        opciones = datos.get("subcat_opciones", [])
        ids      = datos.get("subcat_ids", [])
        if not msg.isdigit() or int(msg) < 1 or int(msg) > len(opciones):
            return f"❓ Responde con un número del 1 al {len(opciones)}."
        idx = int(msg) - 1
        datos["subcategoria_codigo"] = opciones[idx]
        datos["subcategoria_id"]     = ids[idx]
        datos["subcategoria_nombre"] = opciones[idx].replace("_", " A ")

        # Si es INFILL → pide tajo. Si es recategorización → pide cuerpo.
        if opciones[idx] == "INFILL":
            actualizar_sesion(sid, "objetivo_infill", datos)
            return (
                f"✅ Tipo: *INFILL*\n\n"
                f"¿Cuál es el *tajo objetivo*?\n"
                f"Ejemplo: T-021, Tj.001, T-695\n"
            )
        else:
            actualizar_sesion(sid, "objetivo_recategorizacion", datos)
            return (
                f"✅ Tipo: *{datos['subcategoria_nombre']}*\n\n"
                f"¿Cuál es el *cuerpo / objetivo*?\n"
                f"Ejemplo: OB1, EXT-OB1, OB1_01, OB6\n"
            )

    # ── PASO 2a: Objetivo INFILL (tajo) ───────────────────────
    elif paso == "objetivo_infill":
        datos["tajo_objetivo"] = msg.upper()
        actualizar_sesion(sid, "profundidad", datos)
        return (
            f"✅ Tajo objetivo: *{datos['tajo_objetivo']}*\n\n"
            f"¿Cuál es la *profundidad programada* (metros)?\n"
            f"Ejemplo: 150, 295, 320.50\n"
        )

    # ── PASO 2b: Objetivo recategorización (cuerpo) ───────────
    elif paso == "objetivo_recategorizacion":
        datos["cuerpo_objetivo"] = msg.upper()
        actualizar_sesion(sid, "profundidad", datos)
        return (
            f"✅ Objetivo: *{datos['cuerpo_objetivo']}*\n\n"
            f"¿Cuál es la *profundidad programada* (metros)?\n"
            f"Ejemplo: 150, 295, 320.50\n"
        )

    # ── PASO 3: Profundidad programada ────────────────────────
    elif paso == "profundidad":
        try:
            prof = float(msg.replace(",", "."))
            if prof <= 0:
                raise ValueError
            datos["profundidad_prog"] = prof
        except ValueError:
            return "❓ Ingresa un número válido. Ejemplo: 295 o 320.50"
        actualizar_sesion(sid, "orientacion", datos)
        return (
            f"✅ Profundidad programada: *{prof:.1f} m*\n\n"
            f"¿Cuál es el *azimut* programado (°)?\n"
            f"Ejemplo: 39, 285, 346\n"
        )

    # ── PASO 4: Azimut ────────────────────────────────────────
    elif paso == "orientacion":
        try:
            az = float(msg.replace("°", "").strip())
            if az < 0 or az > 360:
                raise ValueError
            datos["azimut_prog"] = az
        except ValueError:
            return "❓ Ingresa el azimut entre 0 y 360. Ejemplo: 39"
        actualizar_sesion(sid, "inclinacion", datos)
        return (
            f"✅ Azimut: *{az:.1f}°*\n\n"
            f"¿Cuál es la *inclinación* programada (°)?\n"
            f"Usa negativo para inclinación hacia abajo.\n"
            f"Ejemplo: -17, -42, +8\n"
        )

    # ── PASO 5: Inclinación ───────────────────────────────────
    elif paso == "inclinacion":
        try:
            dip = float(msg.replace("°", "").strip())
            datos["dip_prog"] = dip
        except ValueError:
            return "❓ Ingresa la inclinación. Ejemplo: -17 o +8"
        actualizar_sesion(sid, "nivel", datos)
        return (
            f"✅ Inclinación: *{dip:.1f}°*\n\n"
            f"¿En qué *nivel* se ubica el sondaje?\n"
            f"Ejemplo: 1710, 1850, 1940\n"
        )

    # ── PASO 6: Nivel ─────────────────────────────────────────
    elif paso == "nivel":
        try:
            nivel = int(msg.strip())
            datos["nivel_prog"] = nivel
        except ValueError:
            return "❓ Ingresa el nivel como número. Ejemplo: 1940"
        actualizar_sesion(sid, "labor", datos)
        return (
            f"✅ Nivel: *{nivel}*\n\n"
            f"¿Cuál es la *labor* de la boca del sondaje?\n"
            f"Ejemplo: Cx.010, Bp.650, Ga.714, CX 845\n"
        )

    # ── PASO 7: Labor ─────────────────────────────────────────
    elif paso == "labor":
        datos["labor"] = msg.strip()
        # Mostrar máquinas disponibles
        maquinas = obtener_maquinas_con_empresa()
        menu = "\n".join([f"  *{i+1}* — {m['codigo']} ({m['empresa']})"
                          for i, m in enumerate(maquinas)])
        menu += f"\n  *{len(maquinas)+1}* — Nueva máquina"
        datos["maquina_opciones"] = [(m["id"], m["codigo"], m["empresa_id"])
                                      for m in maquinas]
        actualizar_sesion(sid, "maquina", datos)
        return (
            f"✅ Labor: *{datos['labor']}*\n\n"
            f"¿Qué *máquina* perfora este sondaje?\n\n"
            f"{menu}\n\n"
            f"Responde con el número.\n"
        )

    # ── PASO 8: Máquina ───────────────────────────────────────
    elif paso == "maquina":
        opciones = datos.get("maquina_opciones", [])
        nueva_idx = len(opciones) + 1
        if msg.isdigit() and int(msg) == nueva_idx:
            actualizar_sesion(sid, "nueva_maquina", datos)
            return (
                "🆕 *Nueva máquina*\n\n"
                "Escribe el código de la nueva máquina.\n"
                "Ejemplo: DCAT-15, FB100-03\n"
            )
        if not msg.isdigit() or int(msg) < 1 or int(msg) > len(opciones):
            return f"❓ Responde con un número del 1 al {nueva_idx}."
        idx = int(msg) - 1
        maq_id, maq_cod, emp_id = opciones[idx]
        datos["maquina_id"]  = maq_id
        datos["maquina_cod"] = maq_cod
        datos["empresa_id"]  = emp_id
        actualizar_sesion(sid, "diametro", datos)
        return (
            f"✅ Máquina: *{maq_cod}*\n\n"
            f"¿Qué *diámetro* de perforación?\n\n"
            f"  *1* — BQ\n  *2* — NQ\n  *3* — HQ\n  *4* — PQ\n\n"
            f"Responde con el número.\n"
        )

    # ── PASO 8b: Nueva máquina ────────────────────────────────
    elif paso == "nueva_maquina":
        nuevo_cod = msg.strip().upper()
        # Registrar en catálogo como inactiva para revisión
        from db.conexion import ejecutar
        row = ejecutar(
            """INSERT INTO cat_maquinas (codigo, empresa_id, sufijo_tarifa, activo)
               VALUES (%s, 1, '', TRUE) ON CONFLICT (codigo) DO NOTHING RETURNING id""",
            (nuevo_cod,), fetchone=True
        )
        if row:
            datos["maquina_id"]  = row[0]
            datos["maquina_cod"] = nuevo_cod
            datos["empresa_id"]  = 1
        actualizar_sesion(sid, "diametro", datos)
        return (
            f"✅ Máquina *{nuevo_cod}* agregada.\n\n"
            f"¿Qué *diámetro* de perforación?\n\n"
            f"  *1* — BQ\n  *2* — NQ\n  *3* — HQ\n  *4* — PQ\n\n"
            f"Responde con el número.\n"
        )

    # ── PASO 9: Diámetro ──────────────────────────────────────
    elif paso == "diametro":
        diams = ["BQ", "NQ", "HQ", "PQ"]
        if not msg.isdigit() or int(msg) < 1 or int(msg) > 4:
            return "❓ Responde 1 (BQ), 2 (NQ), 3 (HQ) o 4 (PQ)."
        datos["diametro"] = diams[int(msg) - 1]

        # Sugerir siguiente BHID
        bhid_sugerido = siguiente_bhid()
        datos["bhid_sugerido"] = bhid_sugerido

        actualizar_sesion(sid, "codigo_ddh", datos)
        return (
            f"✅ Diámetro: *{datos['diametro']}*\n\n"
            f"¿Cuál es el *código DDH* asignado?\n"
            f"Siguiente disponible: *{bhid_sugerido}*\n\n"
            f"Escribe el código o *confirma* para usar el sugerido.\n"
            f"Si aún no tiene código, escribe *provisional*.\n"
        )

    # ── PASO 10: Código DDH ───────────────────────────────────
    elif paso == "codigo_ddh":
        msg_low = msg.lower()
        if msg_low in ("confirma", "si", "sí", "ok", "yes"):
            bhid = datos["bhid_sugerido"]
        elif msg_low == "provisional":
            from config import hora_peru
            ts = hora_peru().strftime("%d%m-%H%M")
            bhid = f"TEMP-{datos['maquina_cod'].replace('-','')}-{ts}"
            datos["es_provisional"] = True
        else:
            bhid = msg.strip().upper().replace("-", "").replace(" ", "")
            if not bhid.startswith("PECLD"):
                bhid = "PECLD" + bhid.lstrip("0").zfill(5)

        # Verificar que no exista
        existe = buscar_sondaje(bhid)
        if existe:
            return f"⚠️ El sondaje *{bhid}* ya existe en la BD.\n¿Deseas usar otro código?"

        datos["bhid"] = bhid

        # Obtener categoria_id de OPERACIONES
        from db.conexion import ejecutar as _ej
        cat_row = _ej("SELECT id FROM cat_categorias WHERE codigo='OPE'",
                      fetchone=True)
        datos["categoria_id"] = cat_row[0] if cat_row else 1

        actualizar_sesion(sid, "confirmacion", datos)

        # Resumen para confirmar
        prov_aviso = " *(PROVISIONAL)*" if datos.get("es_provisional") else ""
        objetivo = datos.get("tajo_objetivo") or datos.get("cuerpo_objetivo", "—")
        return (
            f"📋 *RESUMEN DEL SONDAJE*{prov_aviso}\n"
            f"{'─'*30}\n"
            f"🔖 Código:      *{bhid}*\n"
            f"📂 Tipo:        {datos.get('subcategoria_nombre','')}\n"
            f"🎯 Objetivo:    {objetivo}\n"
            f"📏 Prog:        {datos['profundidad_prog']:.1f} m\n"
            f"🧭 Azimut:      {datos.get('azimut_prog','—')}°\n"
            f"📐 Inclinación: {datos.get('dip_prog','—')}°\n"
            f"🏔️ Nivel:       {datos.get('nivel_prog','—')}\n"
            f"⛏️ Labor:       {datos.get('labor','—')}\n"
            f"🚜 Máquina:     {datos.get('maquina_cod','—')}\n"
            f"💧 Diámetro:    {datos.get('diametro','—')}\n"
            f"{'─'*30}\n\n"
            f"¿Confirmas el registro? (*sí* / *no*)\n"
        )

    # ── PASO 11: Confirmación final ───────────────────────────
    elif paso == "confirmacion":
        if msg.lower() in ("no", "cancelar", "cancel"):
            cerrar_sesion(usuario["id"])
            return "❌ Matriculación cancelada. Escribe *hola* para volver al menú."

        if msg.lower() not in ("sí", "si", "yes", "confirma", "ok"):
            return "¿Confirmas? Responde *sí* o *no*."

        # Insertar en BD
        try:
            bhid = matricular_sondaje(datos, usuario["id"])
            cerrar_sesion(usuario["id"])
            if bhid:
                return (
                    f"✅ *Sondaje matriculado exitosamente*\n\n"
                    f"🔖 Código: *{bhid}*\n"
                    f"📅 {fecha_hora_str()}\n"
                    f"👤 Registrado por: {usuario['nombre']}\n\n"
                    f"El sondaje ya está disponible para las contratistas y SGS."
                )
            else:
                return "⚠️ Error al registrar. El código ya existe o hay un problema en BD."
        except Exception as e:
            print(f"[MATRICULA] Error: {e}")
            return "⚠️ Error al guardar. Contacta al administrador."

    return "❓ Paso no reconocido. Escribe *hola* para reiniciar."
