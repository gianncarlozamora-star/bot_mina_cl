"""
CERRO LINDO BOT — Punto de entrada principal
Webhook WhatsApp + Cloudinary para fotos.
"""
import os
import requests
from flask import Flask, request, jsonify, send_file
from config import VERIFY_TOKEN, ACCESS_TOKEN, PHONE_NUMBER_ID, WA_API_URL

app = Flask(__name__)

CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")

def _cloudinary_config():
    import urllib.parse
    r = urllib.parse.urlparse(CLOUDINARY_URL)
    return r.username, r.password, r.hostname

def subir_foto_cloudinary(ruta_local: str, carpeta: str = "cerro_lindo") -> str | None:
    try:
        api_key, api_secret, cloud_name = _cloudinary_config()
        if not cloud_name:
            return None
        import hashlib, time
        timestamp  = str(int(time.time()))
        firma_str  = f"folder={carpeta}&timestamp={timestamp}{api_secret}"
        signature  = hashlib.sha1(firma_str.encode()).hexdigest()
        with open(ruta_local, "rb") as f:
            resp = requests.post(
                f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload",
                data={"api_key": api_key, "timestamp": timestamp,
                      "signature": signature, "folder": carpeta},
                files={"file": f}, timeout=30
            )
        if resp.status_code == 200:
            url = resp.json().get("secure_url")
            print(f"   Cloudinary OK: {url}")
            return url
        print(f"   Cloudinary error: {resp.text}")
        return None
    except Exception as e:
        print(f"❌ Error Cloudinary: {e}")
        return None

@app.route("/webhook", methods=["GET"])
def verify():
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == VERIFY_TOKEN:
        return challenge, 200
    return "Token inválido", 403

@app.route("/webhook", methods=["POST"])
def webhook():
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
            media_id   = msg_obj["image"]["id"]
            caption    = msg_obj["image"].get("caption", "")
            ruta_local = _descargar_media(media_id)
            if ruta_local:
                foto_url = subir_foto_cloudinary(ruta_local)
                try:
                    os.remove(ruta_local)
                except:
                    pass
            mensaje = caption or ""
            print(f"   Foto URL: {foto_url}")
        elif tipo == "document":
            mensaje = f"[Documento: {msg_obj['document'].get('filename','')}]"
        else:
            enviar_mensaje(remitente,
                "📎 Solo proceso texto e imágenes. Escribe *hola* para ver el menú.")
            return jsonify({"status": "ok"}), 200
        respuesta = procesar(mensaje, remitente, foto_url)
        if isinstance(respuesta, dict) and respuesta.get("tipo") == "imagen":
            enviar_imagen(remitente, respuesta["url"], respuesta.get("caption",""))
        else:
            enviar_mensaje(remitente, str(respuesta))
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        import traceback
        traceback.print_exc()
    return jsonify({"status": "ok"}), 200

@app.route("/descargar/<nombre_archivo>")
def descargar_excel(nombre_archivo):
    ruta = f"/tmp/{nombre_archivo}"
    if not os.path.exists(ruta):
        return "Archivo no encontrado o expirado", 404
    return send_file(ruta, as_attachment=True, download_name=nombre_archivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/health")
def health():
    from config import hora_peru
    return jsonify({"status": "ok", "sistema": "Cerro Lindo Bot",
                    "hora_pe": hora_peru().strftime("%d/%m/%Y %H:%M")})

def enviar_mensaje(telefono: str, texto: str):
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}",
               "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": telefono,
            "type": "text", "text": {"body": texto[:4096]}}
    try:
        r = requests.post(WA_API_URL, json=data, headers=headers, timeout=10)
        print(f"   WA status: {r.status_code}")
    except Exception as e:
        print(f"❌ Error enviando: {e}")

def enviar_imagen(telefono: str, url_imagen: str, caption: str = ""):
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}",
               "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": telefono,
            "type": "image",
            "image": {"link": url_imagen, "caption": caption[:1024]}}
    try:
        r = requests.post(WA_API_URL, json=data, headers=headers, timeout=10)
        print(f"   WA imagen: {r.status_code}")
        if r.status_code != 200:
            enviar_mensaje(telefono, f"📸 {caption}\n{url_imagen}")
    except Exception as e:
        print(f"❌ Error enviando imagen: {e}")

def _descargar_media(media_id: str) -> str | None:
    try:
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
        r = requests.get(f"https://graph.facebook.com/v18.0/{media_id}",
                         headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        url_media = r.json().get("url")
        if not url_media:
            return None
        r2 = requests.get(url_media, headers=headers, timeout=30)
        if r2.status_code != 200:
            return None
        ruta = f"/tmp/foto_{media_id}.jpg"
        with open(ruta, "wb") as f:
            f.write(r2.content)
        return ruta
    except Exception as e:
        print(f"❌ Error descargando media: {e}")
        return None

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Cerro Lindo Bot iniciando en puerto {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
