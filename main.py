"""
CERRO LINDO BOT — Punto de entrada principal
Solo maneja el webhook de WhatsApp y delega al router.
"""
import os
import requests
from flask import Flask, request, jsonify, send_file
from config import VERIFY_TOKEN, ACCESS_TOKEN, PHONE_NUMBER_ID, WA_API_URL

app = Flask(__name__)

# ── WEBHOOK WHATSAPP ──────────────────────────────────────────

@app.route("/webhook", methods=["GET"])
def verify():
    """Verificación del webhook por Meta."""
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == VERIFY_TOKEN:
        return challenge, 200
    return "Token inválido", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    """Recibe mensajes de WhatsApp y responde."""
    from modulos.router import procesar

    data = request.get_json()
    try:
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" not in entry:
            return jsonify({"status": "ok"}), 200

        msg_obj   = entry["messages"][0]
        remitente = msg_obj["from"]
        tipo      = msg_obj.get("type", "text")

        print(f"📨 [{tipo}] {remitente}")

        foto_url = None

        if tipo == "text":
            mensaje = msg_obj["text"]["body"]
            print(f"   Msg: {mensaje}")

        elif tipo == "image":
            # Descargar y guardar la imagen
            media_id = msg_obj["image"]["id"]
            foto_url = _descargar_media(media_id)
            mensaje  = msg_obj["image"].get("caption", "")
            print(f"   Foto: {foto_url}")

        elif tipo == "document":
            mensaje = f"[Documento adjunto: {msg_obj['document'].get('filename','')}]"

        else:
            # Tipo no soportado: audio, video, sticker, etc.
            enviar_mensaje(remitente,
                "📎 Solo proceso texto e imágenes por ahora. "
                "Escribe *hola* para ver el menú.")
            return jsonify({"status": "ok"}), 200

        respuesta = procesar(mensaje, remitente, foto_url)
        enviar_mensaje(remitente, respuesta)

    except Exception as e:
        print(f"❌ Webhook error: {e}")
        import traceback
        traceback.print_exc()

    return jsonify({"status": "ok"}), 200


# ── DESCARGA DE EXCEL ─────────────────────────────────────────

@app.route("/descargar/<nombre_archivo>")
def descargar_excel(nombre_archivo):
    """Endpoint para descarga de archivos Excel generados."""
    import os
    ruta = f"/tmp/{nombre_archivo}"
    if not os.path.exists(ruta):
        return "Archivo no encontrado o expirado", 404
    return send_file(
        ruta,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ── HEALTH CHECK ──────────────────────────────────────────────

@app.route("/health")
def health():
    """Railway lo usa para verificar que el servicio está vivo."""
    from config import hora_peru
    return jsonify({
        "status":  "ok",
        "sistema": "Cerro Lindo Bot",
        "hora_pe": hora_peru().strftime("%d/%m/%Y %H:%M")
    })


# ── ENVÍO DE MENSAJES ─────────────────────────────────────────

def enviar_mensaje(telefono: str, texto: str):
    """Envía un mensaje de texto por WhatsApp Cloud API."""
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type":  "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to":   telefono,
        "type": "text",
        "text": {"body": texto[:4096]}  # WhatsApp limit
    }
    try:
        r = requests.post(WA_API_URL, json=data, headers=headers, timeout=10)
        print(f"   WA status: {r.status_code}")
        if r.status_code != 200:
            print(f"   WA error: {r.text}")
    except Exception as e:
        print(f"❌ Error enviando mensaje: {e}")


def _descargar_media(media_id: str) -> str | None:
    """Descarga una imagen de WhatsApp y retorna la ruta local."""
    try:
        # 1. Obtener URL de la imagen
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
        r = requests.get(
            f"https://graph.facebook.com/v18.0/{media_id}",
            headers=headers, timeout=10
        )
        if r.status_code != 200:
            return None
        url_media = r.json().get("url")
        if not url_media:
            return None

        # 2. Descargar la imagen
        r2 = requests.get(url_media, headers=headers, timeout=30)
        if r2.status_code != 200:
            return None

        # 3. Guardar localmente
        ruta = f"/tmp/foto_{media_id}.jpg"
        with open(ruta, "wb") as f:
            f.write(r2.content)

        # En producción: subir a S3/GCS y retornar URL pública
        # Por ahora retornamos ruta local
        return ruta

    except Exception as e:
        print(f"❌ Error descargando media: {e}")
        return None


# ── INICIO ────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Cerro Lindo Bot iniciando en puerto {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)

