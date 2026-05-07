import os
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

# CONFIGURACIÓN
VERIFY_TOKEN = "Mina_Giann_2026"
ACCESS_TOKEN = "EAAmlw4rzjS0BRSF9ygexZA2xezhWvNAyOerG575vl2fMGs33fRRj4iUtHG8nHyce3Bc1c9B6OP9HjWap4N4c2ruSrJOTHyovKsRmdwdleqqmQv3JONQpXvodx0R3fHmWH8g0uFzZC6d0y3Y00ZBS93c0QUoCQHXolIKBqf8ayXG9F5u3KgmzReyLcptZAQZDZD" # <--- Pega aquí el Token largo que generaste en Meta
PHONE_NUMBER_ID = "1106542105873680" # Tu ID que vimos en la imagen anterior

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
