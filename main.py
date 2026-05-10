"""
CERRO LINDO BOT — Punto de entrada principal
Webhook WhatsApp + Cloudinary + Mensajes Interactivos
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

def subir_archivo_cloudinary(ruta_local: str, carpeta: str = "cerro_lindo_dxf",
                              resource_type: str = "raw") -> str | None:
    """Sube cualquier archivo (DXF, PDF, etc.) a Cloudinary como raw."""
    try:
        api_key, api_secret, cloud_name = _cloudinary_config()
        if not cloud_name:
            return None
        import hashlib, time
        timestamp = str(int(time.time()))
        firma_str = f"folder={carpeta}&timestamp={timestamp}{api_secret}"
        signature = hashlib.sha1(firma_str.encode()).hexdigest()
        with open(ruta_local, "rb") as f:
            resp = requests.post(
                f"https://api.cloudinary.com/v1_1/{cloud_name}/{resource_type}/upload",
                data={"api_key": api_key, "timestamp": timestamp,
                      "signature": signature, "folder": carpeta},
                files={"file": f}, timeout=30
            )
        if resp.status_code == 200:
            url = resp.json().get("secure_url")
            print(f"   Cloudinary DXF OK: {url}")
            return url
        print(f"   Cloudinary error: {resp.text}")
        return None
    except Exception as e:
        print(f"❌ Error Cloudinary doc: {e}")
        return None


def subir_foto_cloudinary(ruta_local: str, carpeta: str = "cerro_lindo") -> str | None:
    try:
        api_key, api_secret, cloud_name = _cloudinary_config()
        if not cloud_name:
            return None
        import hashlib, time
        timestamp = str(int(time.time()))
        firma_str = f"folder={carpeta}&timestamp={timestamp}{api_secret}"
        signature = hashlib.sha1(firma_str.encode()).hexdigest()
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
        mensaje  = ""

        if tipo == "text":
            mensaje = msg_obj["text"]["body"]
            print(f"   Msg: {mensaje}")

        elif tipo == "interactive":
            # Respuesta de botón o lista
            interactive = msg_obj["interactive"]
            tipo_int    = interactive.get("type")
            if tipo_int == "button_reply":
                btn     = interactive["button_reply"]
                mensaje = btn.get("title", "")
                btn_id  = btn.get("id", "")
                print(f"   Botón: {btn_id} = {mensaje}")
                # Normalizar respuestas comunes
                mensaje = _normalizar_interactivo(btn_id, mensaje)
            elif tipo_int == "list_reply":
                item    = interactive["list_reply"]
                mensaje = item.get("title", "")
                item_id = item.get("id", "")
                print(f"   Lista: {item_id} = {mensaje}")
                mensaje = _normalizar_interactivo(item_id, mensaje)

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
            doc       = msg_obj["document"]
            filename  = doc.get("filename", "archivo")
            media_id  = doc.get("id")
            extension = filename.split(".")[-1].lower() if "." in filename else ""
            print(f"   Documento: {filename}")
            if media_id and extension in ("dxf", "pdf", "zip", "dwg"):
                ruta_local = _descargar_media(media_id, filename)
                if ruta_local:
                    doc_url = subir_archivo_cloudinary(ruta_local)
                    try:
                        os.remove(ruta_local)
                    except:
                        pass
                    if doc_url:
                        # Inyectar en sesión activa como dxf_archivo_url
                        _inyectar_archivo_en_sesion(remitente, doc_url)
                        foto_url = doc_url
                        mensaje  = f"[dxf:{filename}]"
                    else:
                        mensaje = "error_subida"
                else:
                    mensaje = "error_descarga"
            else:
                mensaje = f"[Documento: {filename}]"
                enviar_mensaje(remitente,
                    f"📎 Archivo *{filename}* recibido pero no es un formato soportado.\n"
                    f"Formatos válidos: DXF, PDF, ZIP, DWG")

        else:
            enviar_mensaje(remitente,
                "📎 Solo proceso texto, imágenes y botones. "
                "Escribe *hola* para ver el menú.")
            return jsonify({"status": "ok"}), 200

        respuesta = procesar(mensaje, remitente, foto_url)

        # Manejar diferentes tipos de respuesta
        if isinstance(respuesta, dict):
            tipo_resp = respuesta.get("tipo")
            if tipo_resp == "imagen":
                enviar_imagen(remitente, respuesta["url"],
                              respuesta.get("caption", ""))
            elif tipo_resp == "interactivo":
                # El módulo ya envió el mensaje interactivo directamente
                pass
        else:
            enviar_mensaje(remitente, str(respuesta))

    except Exception as e:
        print(f"❌ Webhook error: {e}")
        import traceback
        traceback.print_exc()

    return jsonify({"status": "ok"}), 200


def _normalizar_interactivo(item_id: str, titulo: str) -> str:
    """
    Convierte IDs de botones/listas a texto que los módulos entienden.
    """
    # Botones de confirmación
    mapeo = {
        # Confirmaciones
        "btn_0_confirmar": "si",
        "btn_1_cancelar":  "no",
        "btn_0_sí":        "si",
        "btn_1_no":        "no",
        # Turno
        "btn_0_☀️_día":   "1",
        "btn_1_🌙_noche":  "2",
        # Sí/No/Fin
        "btn_0_sí":         "si",
        "btn_1_otra_máquina": "no",
        "btn_2_fin":        "fin",
        # Diámetro
        "btn_0_bq": "BQ",
        "btn_1_nq": "NQ",
        "btn_2_hq": "HQ",
    }

    # Normalizar por ID exacto
    if item_id in mapeo:
        return mapeo[item_id]

    # Máquinas: maq_1, maq_2, etc.
    if item_id.startswith("maq_"):
        try:
            num = int(item_id.replace("maq_", ""))
            return f"__maq_id_{num}__"
        except:
            pass

    # Tipo sondaje: tipo_INFILL, tipo_IND_MED, etc.
    if item_id.startswith("tipo_"):
        return item_id.replace("tipo_", "")

    # SGS desde menú principal: sgs_LOGUEO, sgs_MUESTREO, etc.
    if item_id.startswith("sgs_"):
        etapa = item_id.replace("sgs_", "").lower()
        etapas_map = {
            "logueo": "1", "muestreo": "2", "rqd": "3",
            "fotografia": "4", "densidad": "5"
        }
        return etapas_map.get(etapa, etapa)

    # Acciones del menú principal
    acciones_menu = {
        "matricula": "matricular", "perforacion": "perforacion",
        "sgs": "sgs", "certimin": "certimin", "resumen": "resumen",
        "descarga": "descargar", "tajo": "consultar tajo",
        "objetivo": "consultar objetivo", "consulta": "estado",
        "anular": "anular sondaje", "batch":"registrar batch",
        "anular_sgs":  "anular sgs", "reporte_sgs": "reporte sgs",
    }
    if item_id in acciones_menu:
        return acciones_menu[item_id]

    # Fotos: foto_0, foto_1, etc.
    if item_id.startswith("foto_"):
        try:
            return str(int(item_id.replace("foto_", "")) + 1)
        except:
            pass

    # Descargas
    desc_map = {
        "desc_avance": "1", "desc_estado": "2", "desc_mes": "3"
    }
    if item_id in desc_map:
        return desc_map[item_id]

    # Fallback: usar el título directamente
    return titulo


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

def _descargar_media(media_id: str, filename: str = None) -> str | None:
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
        ext  = filename.split(".")[-1] if filename and "." in filename else "jpg"
        ruta = f"/tmp/media_{media_id}.{ext}"
        with open(ruta, "wb") as f:
            f.write(r2.content)
        return ruta
    except Exception as e:
        print(f"❌ Error descargando media: {e}")
        return None

def _inyectar_archivo_en_sesion(remitente: str, url: str):
    """Guarda el URL del archivo en la sesión activa del usuario."""
    try:
        from db.usuarios import obtener_usuario
        from db.sesiones import obtener_sesion
        from db.conexion import ejecutar
        usuario = obtener_usuario(remitente)
        if not usuario:
            return
        sesion = obtener_sesion(usuario["id"])
        if not sesion:
            return
        datos = sesion.get("datos", {})
        datos["dxf_archivo_url"] = url
        import json
        ejecutar(
            "UPDATE sesiones_bot SET datos_parciales = %s WHERE id = %s",
            (json.dumps(datos), sesion["id"])
        )
        print(f"   DXF inyectado en sesión: {url}")
    except Exception as e:
        print(f"❌ Error inyectando DXF: {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Cerro Lindo Bot iniciando en puerto {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
