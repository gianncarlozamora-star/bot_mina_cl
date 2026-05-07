import os
import requests
import psycopg2
import anthropic
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
VERIFY_TOKEN    = os.environ.get("VERIFY_TOKEN", "Mina_Giann_2026")
ACCESS_TOKEN    = os.environ.get("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
DATABASE_URL    = os.environ.get("DATABASE_URL")
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY")

cliente_ai = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# ─── HORA PERÚ ────────────────────────────────────────────────────────────────
def hora_peru():
    return datetime.utcnow() - timedelta(hours=5)

# ─── BASE DE DATOS ────────────────────────────────────────────────────────────
def get_db():
    return psycopg2.connect(DATABASE_URL)

def inicializar_db():
    conn = get_db()
    cur = conn.cursor()

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            telefono VARCHAR(20) PRIMARY KEY,
            nombre VARCHAR(100),
            rol VARCHAR(20),
            activo BOOLEAN DEFAULT TRUE
        )
    """)

    # Datos ficticios de ejemplo basados en Cerro Lindo
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

    cur.execute("""
        INSERT INTO sondajes_ddh
            (tajo_id, codigo_ddh, perforado, fecha_perforacion,
             logueado, fecha_logueo, muestreado, enviado_laboratorio,
             leyes_recibidas, modelado, enviado_sst, geologo_responsable)
        VALUES
            ('1600_OB5_T-008', 'DDH-8261', TRUE, '2026-04-10',
             TRUE, '2026-04-12', TRUE, TRUE, TRUE, TRUE, FALSE, 'Carlos Quispe'),
            ('1640_OB5_T-007', 'DDH-8255', TRUE, '2026-04-15',
             TRUE, '2026-04-17', TRUE, FALSE, FALSE, FALSE, FALSE, 'Maria Huanca'),
            ('1880_OB6A_T-695', 'DDH-8290', FALSE, NULL,
             FALSE, NULL, FALSE, FALSE, FALSE, FALSE, FALSE, 'Carlos Quispe'),
            ('1940_OB13_T-1012', 'DDH-8301', TRUE, '2026-04-20',
             TRUE, '2026-04-22', FALSE, FALSE, FALSE, FALSE, FALSE, 'Maria Huanca')
        ON CONFLICT DO NOTHING
    """)

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
    print("✅ Base de datos inicializada.")

# ─── CONSULTAS DB ─────────────────────────────────────────────────────────────
def obtener_rol(telefono):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT nombre, rol FROM usuarios WHERE telefono=%s AND activo=TRUE", (telefono,))
        res = cur.fetchone()
        cur.close(); conn.close()
        return res
    except:
        return None

def estado_ddh(codigo):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT d.codigo_ddh, t.id, t.nivel, t.cuerpo,
               d.perforado, d.logueado, d.muestreado,
               d.enviado_laboratorio, d.leyes_recibidas,
               d.modelado, d.enviado_sst, d.geologo_responsable
        FROM sondajes_ddh d
        JOIN tajos t ON d.tajo_id = t.id
        WHERE UPPER(d.codigo_ddh) = UPPER(%s)
    """, (codigo,))
    res = cur.fetchone()
    cur.close(); conn.close()
    return res

def estado_tajo(tajo_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, t.nivel, t.cuerpo, t.tonelaje,
               t.zn_pct, t.cu_pct, t.riesgo_final, t.estado_infill,
               COUNT(d.id), SUM(CASE WHEN d.modelado THEN 1 ELSE 0 END),
               SUM(CASE WHEN d.enviado_sst THEN 1 ELSE 0 END)
        FROM tajos t
        LEFT JOIN sondajes_ddh d ON d.tajo_id = t.id
        WHERE UPPER(t.tajo)=UPPER(%s) OR UPPER(t.id)=UPPER(%s)
        GROUP BY t.id, t.nivel, t.cuerpo, t.tonelaje,
                 t.zn_pct, t.cu_pct, t.riesgo_final, t.estado_infill
    """, (tajo_id, tajo_id))
    res = cur.fetchone()
    cur.close(); conn.close()
    return res

def actualizar_etapa(codigo, etapa, geologo):
    etapas = {
        'perforado':   ('perforado', 'fecha_perforacion'),
        'logueado':    ('logueado', 'fecha_logueo'),
        'muestreado':  ('muestreado', 'fecha_muestreo'),
        'laboratorio': ('enviado_laboratorio', 'fecha_envio_lab'),
        'leyes':       ('leyes_recibidas', None),
        'modelado':    ('modelado', None),
        'sst':         ('enviado_sst', None),
    }
    if etapa not in etapas:
        return False
    campo, campo_fecha = etapas[etapa]
    conn = get_db()
    cur = conn.cursor()
    if campo_fecha:
        cur.execute(f"""
            UPDATE sondajes_ddh SET {campo}=TRUE, {campo_fecha}=%s,
            geologo_responsable=%s, actualizado_en=NOW()
            WHERE UPPER(codigo_ddh)=UPPER(%s)
        """, (hora_peru().date(), geologo, codigo))
    else:
        cur.execute(f"""
            UPDATE sondajes_ddh SET {campo}=TRUE,
            geologo_responsable=%s, actualizado_en=NOW()
            WHERE UPPER(codigo_ddh)=UPPER(%s)
        """, (geologo, codigo))
    ok = cur.rowcount > 0
    conn.commit(); cur.close(); conn.close()
    return ok

def resumen_gerencia():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT t.id),
               SUM(CASE WHEN t.estado_infill='PERFORADO' THEN 1 ELSE 0 END),
               SUM(CASE WHEN t.estado_infill='PENDIENTE' THEN 1 ELSE 0 END),
               SUM(CASE WHEN t.riesgo_final='ALTO' THEN 1 ELSE 0 END),
               COUNT(d.id),
               SUM(CASE WHEN d.enviado_sst THEN 1 ELSE 0 END)
        FROM tajos t LEFT JOIN sondajes_ddh d ON d.tajo_id=t.id
    """)
    res = cur.fetchone()
    cur.close(); conn.close()
    return res

# ─── CLAUDE AI: INTERPRETA LENGUAJE NATURAL ───────────────────────────────────
def interpretar_con_ia(mensaje, nombre, rol):
    import json
    system_prompt = f"""Eres el asistente de gestión minera del proyecto Cerro Lindo (Perú).
Analiza el mensaje y devuelve SOLO un JSON con esta estructura exacta:
{{
  "intencion": "<menu | ddh | tajo | resumen | actualizar | desconocido>",
  "codigo": "<código DDH normalizado, ej: DDH-8261>",
  "tajo": "<código de tajo, ej: T-008>",
  "etapa": "<perforado | logueado | muestreado | laboratorio | leyes | modelado | sst>",
  "respuesta_libre": "<respuesta corta en español, solo si intencion=desconocido>"
}}

Reglas de interpretación:
- "loguear / logueo / logueé / ya loguié" → etapa=logueado
- "perforar / perforé / terminé de perforar" → etapa=perforado
- "muestra / muestreo / muestreé" → etapa=muestreado
- "laboratorio / lab / mandé al lab / envié al lab" → etapa=laboratorio
- "leyes / resultados del lab / llegaron las leyes" → etapa=leyes
- "modelo / modelé / modelado" → etapa=modelado
- "SST / servicios técnicos / envié a SST" → etapa=sst
- Números solos como "8261" normalizar a "DDH-8261"
- Usuario actual: {nombre} | Rol: {rol}
- Devuelve SOLO el JSON sin texto adicional ni backticks."""

    respuesta = cliente_ai.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": mensaje}]
    )
    texto = respuesta.content[0].text.strip()
    texto = texto.replace("```json", "").replace("```", "").strip()
    return json.loads(texto)

# ─── LÓGICA PRINCIPAL ─────────────────────────────────────────────────────────
def procesar_mensaje(mensaje, remitente):
    fecha_hora = hora_peru().strftime("%d/%m/%Y %H:%M")
    usuario = obtener_rol(remitente)

    if not usuario:
        return "⛔ Número no registrado en Cerro Lindo.\nContacta al administrador."

    nombre, rol = usuario

    try:
        intent = interpretar_con_ia(mensaje, nombre, rol)
        accion = intent.get("intencion", "desconocido")

        # MENÚ
        if accion == "menu":
            if rol == "gerente":
                return (
                    f"👋 Hola {nombre}!\n📅 {fecha_hora}\n\n"
                    f"*Panel Gerencia:*\n"
                    f"📊 _dame el resumen_ → KPIs generales\n"
                    f"🔍 _estado del tajo T-008_ → Detalle tajo\n"
                    f"🔍 _cómo va el DDH 8261_ → Estado sondaje"
                )
            else:
                return (
                    f"👋 Hola {nombre}!\n📅 {fecha_hora}\n\n"
                    f"*Panel Perforista:*\n"
                    f"✅ _ya logueé el 8255_ → Marca logueo\n"
                    f"✅ _terminé de perforar el 8290_ → Marca perforación\n"
                    f"✅ _mandé el 8255 al lab_ → Marca laboratorio\n"
                    f"🔍 _cómo va el 8261_ → Ver estado DDH"
                )

        # CONSULTA DDH
        elif accion == "ddh":
            codigo = intent.get("codigo", "")
            if not codigo:
                return "❓ ¿De qué sondaje DDH necesitas el estado?"
            r = estado_ddh(codigo)
            if not r:
                return f"❌ No encontré *{codigo}*. Verifica el código."
            ddh, tajo, nivel, cuerpo, perf, log, mues, lab, leyes, mod, sst, geo = r
            c = lambda x: "✅" if x else "❌"
            return (
                f"🔍 *{ddh}* | {tajo}\n"
                f"Nivel {nivel} | {cuerpo} | Geólogo: {geo or 'N/A'}\n\n"
                f"{c(perf)} Perforado\n"
                f"{c(log)} Logueado\n"
                f"{c(mues)} Muestreado\n"
                f"{c(lab)} Enviado a Lab\n"
                f"{c(leyes)} Leyes recibidas\n"
                f"{c(mod)} Modelado\n"
                f"{c(sst)} Enviado a SST"
            )

        # CONSULTA TAJO
        elif accion == "tajo":
            if rol != "gerente":
                return "⛔ Solo gerencia puede consultar tajos."
            codigo = intent.get("tajo", "")
            if not codigo:
                return "❓ ¿Qué tajo quieres consultar? Ejemplo: T-008"
            r = estado_tajo(codigo)
            if not r:
                return f"❌ No encontré el tajo *{codigo}*."
            tid, nivel, cuerpo, ton, zn, cu, riesgo, estado, total, mod, sst = r
            return (
                f"📋 *{tid}*\n"
                f"Nivel: {nivel} | Cuerpo: {cuerpo}\n"
                f"Tonelaje: {ton:,.0f} t\n"
                f"Zn: {zn:.2f}% | Cu: {cu:.2f}%\n"
                f"Riesgo: {riesgo or 'Sin definir'} | Infill: {estado}\n\n"
                f"DDH: {total} total | ✅ Modelados: {mod} | SST: {sst}"
            )

        # RESUMEN GERENCIA
        elif accion == "resumen":
            if rol != "gerente":
                return "⛔ Solo gerencia puede ver el resumen."
            r = resumen_gerencia()
            if not r:
                return "⚠️ Sin datos disponibles."
            total, perf, pend, alto, total_ddh, completos = r
            return (
                f"📊 *RESUMEN CERRO LINDO*\n📅 {fecha_hora}\n\n"
                f"*Tajos:* {total} total\n"
                f"  ✅ Perforados: {perf}\n"
                f"  ⏳ Pendientes: {pend}\n"
                f"  🔴 Riesgo alto: {alto}\n\n"
                f"*Sondajes DDH:* {total_ddh} total\n"
                f"  ✅ Completos (SST): {completos}/{total_ddh}"
            )

        # ACTUALIZAR ETAPA
        elif accion == "actualizar":
            codigo = intent.get("codigo", "")
            etapa  = intent.get("etapa", "")
            if not codigo:
                return "❓ ¿Qué sondaje DDH quieres actualizar?"
            if not etapa:
                return "❓ ¿Qué etapa quieres marcar?\n(perforado, logueado, muestreado, laboratorio, leyes, modelado, sst)"
            ok = actualizar_etapa(codigo, etapa, nombre)
            if ok:
                return (
                    f"✅ *{codigo}* actualizado\n"
                    f"   Etapa: *{etapa.upper()}*\n"
                    f"   Por: {nombre}\n"
                    f"   📅 {fecha_hora}"
                )
            else:
                return f"❌ No encontré *{codigo}*. Verifica el código."

        # RESPUESTA LIBRE
        else:
            return intent.get("respuesta_libre",
                "🤔 No entendí. Escribe *hola* para ver el menú.")

    except Exception as e:
        print(f"❌ Error IA: {e}")
        return "⚠️ Error procesando tu mensaje. Escribe *hola* para ver opciones."

# ─── WHATSAPP ─────────────────────────────────────────────────────────────────
def enviar_mensaje(telefono, texto):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "text",
        "text": {"body": texto}
    }
    r = requests.post(url, json=data, headers=headers)
    print(f"WhatsApp: {r.status_code}")

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
                print(f"📨 {remitente}: {mensaje}")
                respuesta = procesar_mensaje(mensaje, remitente)
                enviar_mensaje(remitente, respuesta)
    except Exception as e:
        print(f"❌ Webhook error: {e}")
    return jsonify({"status": "ok"}), 200

# ─── INICIO ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    inicializar_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
