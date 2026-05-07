import os
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

# CONFIGURACIÓN
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")

def enviar_mensaje(telefono, texto):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "text",
        "text": {"body": texto}
    }
    requests.post(url, json=data, headers=headers)

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
        if 'messages' in data['entry'][0]['changes'][0]['value']:
            mensaje_recibido = data['entry'][0]['changes'][0]['value']['messages'][0]['text']['body'].lower()
            remitente = data['entry'][0]['changes'][0]['value']['messages'][0]['from']
            
            # Hora de Perú
            fecha_hora = (datetime.now() - timedelta(hours=5)).strftime("%d/%m/%Y %H:%M:%S")

            if "hola" in mensaje_recibido:
                respuesta = f"¡Hola! Soy tu asistente de Cerro Lindo.\n📅 Fecha/Hora: {fecha_hora}\n\n¿Qué deseas hacer hoy?\n1. Registrar avance (Perforista)\n2. Consultar resumen (Gerente)"
                enviar_mensaje(remitente, respuesta)
            
            print(f"Mensaje: {mensaje_recibido} de {remitente}")
    except Exception as e:
        print(f"Error: {e}")
    
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
