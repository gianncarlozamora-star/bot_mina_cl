import os
import requests
import psycopg2
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

# ─── CONFIGURACIÓN (desde variables de entorno de Railway) ───────────────────
VERIFY_TOKEN   = os.environ.get("VERIFY_TOKEN", "Mina_Giann_2026")
ACCESS_TOKEN   = os.environ.get("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
DATABASE_URL   = os.environ.get("DATABASE_URL")

# ─── HORA PERÚ ───────────────────────────────────────────────────────────────
def hora_peru():
    return datetime.utcnow() - timedelta(hours=5)

# ─── CONEXIÓN A POSTGRESQL ───────────────────────────────────────────────────
def get_db():
    return psycopg2.connect(DATABASE_URL)

# ─── CREAR TABLAS AL INICIAR (datos ficticios de ejemplo) ────────────────────
def inicializar_db():
    conn = get_db()
    cur = conn.cursor()

    # Tabla de tajos
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tajos (
            id VARCHAR(50) PRIMARY KEY,
            nivel INTEGER,
            cuerpo VARCHAR(20),
            tajo VARCHAR(30),
            mes_plan VARCHAR(30),
            tonelaje NUMERIC(15,3),
            zn_pct NUMERIC(6,4),
            pb_pct NUMERIC(6,4),
            cu_pct NUMERIC(6,4),
            ag_pct NUMERIC(6,4),
            riesgo_inicial VARCHAR(30),
            riesgo_final VARCHAR(30),
            estado_infill VARCHAR(30),
            observaciones TEXT,
            creado_en TIMESTAMP DEFAULT NOW()
        )
    """)

    # Tabla de sondajes DDH
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sondajes_ddh (
            id SERIAL PRIMARY KEY,
            tajo_id VARCHAR(50) REFERENCES tajos(id),
            codigo_ddh VARCHAR(30),
            perforado BOOLEAN DEFAULT FALSE,
            fecha_perforacion DATE,
            logueado BOOLEAN DEFAULT FALSE,
            fecha_logueo DATE,
            muestreado BOOLEAN DEFAULT FALSE,
            fecha_muestreo DATE,
            enviado_laboratorio BOOLEAN DEFAULT FALSE,
            fecha_envio_lab DATE,
            leyes_recibidas BOOLEAN DEFAULT FALSE,
            modelado BOOLEAN DEFAULT FALSE,
            enviado_sst BOOLEAN DEFAULT FALSE,
            geologo_responsable VARCHAR(100),
            observaciones TEXT,
            actualizado_en TIMESTAMP DEFAULT NOW()
        )
    """)

    # Tabla de usuarios/roles
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            telefono VARCHAR(20) PRIMARY KEY,
            nombre VARCHAR(100),
            rol VARCHAR(20),  -- 'perforista' o 'gerente'
            activo BOOLEAN DEFAULT TRUE
        )
    """)

    # ── DATOS FICTICIOS DE EJEMPLO ──────────────────────────────────────────
    # Insertar tajos de ejemplo (basados en tu estructura real)
    cur.execute("""
        INSERT INTO tajos VALUES
            ('1600_OB5_T-008', 1600, 'OB5', 'T-008', 'ENERO',
             10368.8, 0.0071, 0.1131, 0.3797, 1.935,
             'BAJO', 'BAJO', 'PERFORADO',
             'Ajustar modelo. Leyes de Cu y Ag solo pequeños sectores', NOW()),
            ('1640_OB5_T-007', 1640, 'OB5', 'T-007', 'FEBRERO',
             14140.5, 3.5997, 0.6824, 0.1708, 0.0922,
             'BAJO', 'BAJO', 'PERFORADO',
             'Actualizar MB. Aumenta sulfuro. Reducir Pb en estimación', NOW()),
            ('1880_OB6A_T-695', 1880, 'OB6A', 'T-695', 'FEBRERO',
             42275.4, 2.7644, 0.2384, 0.0941, 0.5189,
             'MEDIO', NULL, 'PENDIENTE',
             'Buscar cámara diamantina', NOW()),
            ('1940_OB13_T-1012', 1940, 'OB13', 'T-1012', 'MARZO',
             9050.0, 7.93, 3.57, 0.24, 3.08,
             'ALTO', 'MEDIO', 'PERFORADO',
             'Disminuye mineralización, pendiente leyes', NOW())
        ON CONFLICT (id) DO NOTHING
    """)

    # Insertar DDH de ejemplo
    cur.execute("""
        INSERT INTO sondajes_ddh
            (tajo_id, codigo_ddh, perforado, fecha_perforacion,
             logueado, fecha_logueo, muestreado, enviado_laboratorio,
             leyes_recibidas, modelado, enviado_sst, geologo_responsable)
        VALUES
            ('1600_OB5_T-008', 'DDH-8261', TRUE, '2026-04-10',
             TRUE, '2026-04-12', TRUE, TRUE,
             TRUE, TRUE, FALSE, 'Carlos Quispe'),
            ('1640_OB5_T-007', 'DDH-8255', TRUE, '2026-04-15',
             TRUE, '2026-04-17', TRUE, FALSE,
             FALSE, FALSE, FALSE, 'Maria Huanca'),
            ('1880_OB6A_T-695', 'DDH-8290', FALSE, NULL,
             FALSE, NULL, FALSE, FALSE,
             FALSE, FALSE, FALSE, 'Carlos Quispe'),
            ('1940_OB13_T-1012', 'DDH-8301', TRUE, '2026-04-20',
             TRUE, '2026-04-22', FALSE, FALSE,
             FALSE, FALSE, FALSE, 'Maria Huanca')
        ON CONFLICT DO NOTHING
    """)

    # Insertar usuarios de ejemplo
    cur.execute("""
        INSERT INTO usuarios VALUES
            ('51950156386', 'Giann (Admin)', 'gerente', TRUE),
            ('51987654321', 'Carlos Quispe', 'perforista', TRUE),
            ('51912345678', 'Maria Huanca', 'perforista', TRUE)
        ON CONFLICT (telefono) DO NOTHING
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Base de datos inicializada con datos de ejemplo.")

# ─── FUNCIONES DE CONSULTA ───────────────────────────────────────────────────
def obtener_rol(telefono):
    """Devuelve el rol del usuario o None si no está registrado."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT nombre, rol FROM usuarios WHERE telefono = %s AND activo = TRUE", (telefono,))
        resultado = cur.fetchone()
        cur.close()
        conn.close()
        return resultado  # (nombre, rol) o None
    except:
        return None

def estado_ddh(codigo_ddh):
    """Devuelve el estado completo de un DDH."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT d.codigo_ddh, t.id as tajo, t.nivel, t.cuerpo,
               d.perforado, d.logueado, d.muestreado,
               d.enviado_laboratorio, d.leyes_recibidas,
               d.modelado, d.enviado_sst, d.geologo_responsable
        FROM sondajes_ddh d
        JOIN tajos t ON d.tajo_id = t.id
        WHERE UPPER(d.codigo_ddh) = UPPER(%s)
    """, (codigo_ddh,))
    resultado = cur.fetchone()
    cur.close()
    conn.close()
    return resultado

def estado_tajo(tajo_id):
    """Devuelve el estado del tajo y sus DDHs."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, t.nivel, t.cuerpo, t.tonelaje,
               t.zn_pct, t.cu_pct, t.riesgo_final, t.estado_infill,
               COUNT(d.id) as total_ddh,
               SUM(CASE WHEN d.modelado THEN 1 ELSE 0 END) as ddh_modelados,
               SUM(CASE WHEN d.enviado_sst THEN 1 ELSE 0 END) as ddh_sst
        FROM tajos t
        LEFT JOIN sondajes_ddh d ON d.tajo_id = t.id
        WHERE UPPER(t.tajo) = UPPER(%s) OR UPPER(t.id) = UPPER(%s)
        GROUP BY t.id, t.nivel, t.cuerpo, t.tonelaje,
                 t.zn_pct, t.cu_pct, t.riesgo_final, t.estado_infill
    """, (tajo_id, tajo_id))
    resultado = cur.fetchone()
    cur.close()
    conn.close()
    return resultado

def actualizar_etapa_ddh(codigo_ddh, etapa, geologo):
    """Marca una etapa del DDH como completada."""
    etapas_validas = {
        'perforado':            ('perforado', 'fecha_perforacion'),
        'logueado':             ('logueado', 'fecha_logueo'),
        'muestreado':           ('muestreado', 'fecha_muestreo'),
        'laboratorio':          ('enviado_laboratorio', 'fecha_envio_lab'),
        'leyes':                ('leyes_recibidas', None),
        'modelado':             ('modelado', None),
        'sst':                  ('enviado_sst', None),
    }
    if etapa not in etapas_validas:
        return False
    campo, campo_fecha = etapas_validas[etapa]
    conn = get_db()
    cur = conn.cursor()
    if campo_fecha:
        cur.execute(f"""
            UPDATE sondajes_ddh
            SET {campo} = TRUE, {campo_fecha} = %s,
                geologo_responsable = %s, actualizado_en = NOW()
            WHERE UPPER(codigo_ddh) = UPPER(%s)
        """, (hora_peru().date(), geologo, codigo_ddh))
    else:
        cur.execute(f"""
            UPDATE sondajes_ddh
            SET {campo} = TRUE, geologo_responsable = %s, actualizado_en = NOW()
            WHERE UPPER(codigo_ddh) = UPPER(%s)
        """, (geologo, codigo_ddh))
    filas = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return filas > 0

def resumen_gerencia():
    """Resumen ejecutivo para gerencia."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(DISTINCT t.id) as total_tajos,
            SUM(CASE WHEN t.estado_infill = 'PERFORADO' THEN 1 ELSE 0 END) as perforados,
            SUM(CASE WHEN t.estado_infill = 'PENDIENTE' THEN 1 ELSE 0 END) as pendientes,
            SUM(CASE WHEN t.riesgo_final = 'ALTO' THEN 1 ELSE 0 END) as riesgo_alto,
            COUNT(d.id) as total_ddh,
            SUM(CASE WHEN d.enviado_sst THEN 1 ELSE 0 END) as completos
        FROM tajos t
        LEFT JOIN sondajes_ddh d ON d.tajo_id = t.id
    """)
    return cur.fetchone()

# ─── ENVIAR MENSAJE WHATSAPP ─────────────────────────────────────────────────
def enviar_mensaje(telefono, texto):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "text",
        "text": {"body": texto}
    }
    r = requests.post(url, json=data, headers=headers)
    print(f"WhatsApp API: {r.status_code} → {r.text}")

# ─── LÓGICA DEL BOT ──────────────────────────────────────────────────────────
def procesar_mensaje(mensaje, remitente):
    msg = mensaje.strip().lower()
    fecha_hora = hora_peru().strftime("%d/%m/%Y %H:%M")

    # Verificar si el usuario está registrado
    usuario = obtener_rol(remitente)

    # ── USUARIO NO REGISTRADO ────────────────────────────────────────────────
    if not usuario:
        return (
            f"⛔ Número no registrado en el sistema Cerro Lindo.\n"
            f"Contacta al administrador para registrarte.\n"
            f"📅 {fecha_hora}"
        )

    nombre, rol = usuario

    # ── MENÚ PRINCIPAL ───────────────────────────────────────────────────────
    if any(x in msg for x in ["hola", "inicio", "menu", "menú", "ayuda", "help"]):
        if rol == "gerente":
            return (
                f"👋 Hola {nombre}!\n"
                f"📅 {fecha_hora} | Cerro Lindo\n\n"
                f"*Panel Gerencia:*\n"
                f"📊 Escribe *resumen* → Estado general\n"
                f"🔍 Escribe *tajo T-008* → Estado de un tajo\n"
                f"🔍 Escribe *ddh DDH-8261* → Estado de un sondaje"
            )
        else:
            return (
                f"👋 Hola {nombre}!\n"
                f"📅 {fecha_hora} | Cerro Lindo\n\n"
                f"*Panel Perforista:*\n"
                f"✅ Escribe *perforado DDH-8255* → Marcar como perforado\n"
                f"✅ Escribe *logueado DDH-8255* → Marcar como logueado\n"
                f"✅ Escribe *muestreado DDH-8255* → Marcar muestreo\n"
                f"✅ Escribe *laboratorio DDH-8255* → Enviado a lab\n"
                f"✅ Escribe *modelado DDH-8255* → Marcado modelado\n"
                f"✅ Escribe *sst DDH-8255* → Enviado a Serv. Técnicos\n"
                f"🔍 Escribe *ddh DDH-8255* → Ver estado"
            )

    # ── CONSULTA DDH ─────────────────────────────────────────────────────────
    if msg.startswith("ddh "):
        codigo = mensaje.strip().split(" ", 1)[1].upper()
        r = estado_ddh(codigo)
        if not r:
            return f"❌ No encontré el sondaje *{codigo}*.\nVerifica el código e intenta de nuevo."
        (ddh, tajo, nivel, cuerpo,
         perforado, logueado, muestreado,
         enviado_lab, leyes, modelado, sst, geologo) = r
        check = lambda x: "✅" if x else "❌"
        return (
            f"🔍 *{ddh}* | Tajo: {tajo}\n"
            f"Nivel: {nivel} | Cuerpo: {cuerpo}\n"
            f"Geólogo: {geologo or 'No asignado'}\n\n"
            f"{check(perforado)} Perforado\n"
            f"{check(logueado)} Logueado\n"
            f"{check(muestreado)} Muestreado\n"
            f"{check(enviado_lab)} Enviado a Lab\n"
            f"{check(leyes)} Leyes recibidas\n"
            f"{check(modelado)} Modelado\n"
            f"{check(sst)} Enviado a SST"
        )

    # ── CONSULTA TAJO (solo gerencia) ────────────────────────────────────────
    if msg.startswith("tajo ") and rol == "gerente":
        codigo = mensaje.strip().split(" ", 1)[1].upper()
        r = estado_tajo(codigo)
        if not r:
            return f"❌ No encontré el tajo *{codigo}*."
        (tid, nivel, cuerpo, ton, zn, cu, riesgo, estado,
         total_ddh, ddh_mod, ddh_sst) = r
        return (
            f"📋 *{tid}*\n"
            f"Nivel: {nivel} | Cuerpo: {cuerpo}\n"
            f"Tonelaje: {ton:,.0f} t\n"
            f"Zn: {zn:.2f}% | Cu: {cu:.2f}%\n"
            f"Riesgo: {riesgo or 'Sin definir'}\n"
            f"Infill: {estado}\n\n"
            f"DDH total: {total_ddh}\n"
            f"✅ Modelados: {ddh_mod}/{total_ddh}\n"
            f"✅ Enviados SST: {ddh_sst}/{total_ddh}"
        )

    # ── RESUMEN GERENCIA ─────────────────────────────────────────────────────
    if "resumen" in msg and rol == "gerente":
        r = resumen_gerencia()
        if not r:
            return "⚠️ No hay datos disponibles aún."
        total, perf, pend, alto, total_ddh, completos = r
        return (
            f"📊 *RESUMEN CERRO LINDO*\n"
            f"📅 {fecha_hora}\n\n"
            f"*Tajos:*\n"
            f"  Total: {total}\n"
            f"  ✅ Perforados: {perf}\n"
            f"  ⏳ Pendientes: {pend}\n"
            f"  🔴 Riesgo alto: {alto}\n\n"
            f"*Sondajes DDH:*\n"
            f"  Total: {total_ddh}\n"
            f"  ✅ Completos (SST): {completos}/{total_ddh}"
        )

    # ── ACTUALIZAR ETAPA DDH (solo perforistas) ──────────────────────────────
    etapas = ["perforado", "logueado", "muestreado", "laboratorio", "leyes", "modelado", "sst"]
    for etapa in etapas:
        if msg.startswith(f"{etapa} "):
            if rol not in ["perforista", "gerente"]:
                return "⛔ No tienes permisos para actualizar etapas."
            codigo = mensaje.strip().split(" ", 1)[1].upper()
            exito = actualizar_etapa_ddh(codigo, etapa, nombre)
            if exito:
                return (
                    f"✅ *{codigo}* actualizado:\n"
                    f"   Etapa: *{etapa.upper()}*\n"
                    f"   Por: {nombre}\n"
                    f"   📅 {fecha_hora}"
                )
            else:
                return f"❌ No encontré el sondaje *{codigo}*.\nVerifica el código."

    # ── COMANDO NO RECONOCIDO ────────────────────────────────────────────────
    return (
        f"🤔 No entendí el comando.\n"
        f"Escribe *menu* para ver las opciones disponibles."
    )

# ─── WEBHOOK ─────────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["GET"])
def verify():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == VERIFY_TOKEN:
        return challenge
    return "Error de token", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    try:
        entry = data['entry'][0]['changes'][0]['value']
        if 'messages' in entry:
            msg_obj   = entry['messages'][0]
            remitente = msg_obj['from']
            if msg_obj.get('type') == 'text':
                mensaje = msg_obj['text']['body']
                print(f"📨 [{hora_peru().strftime('%H:%M')}] {remitente}: {mensaje}")
                respuesta = procesar_mensaje(mensaje, remitente)
                enviar_mensaje(remitente, respuesta)
    except Exception as e:
        print(f"❌ Error: {e}")
    return jsonify({"status": "ok"}), 200

# ─── INICIO ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    inicializar_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
