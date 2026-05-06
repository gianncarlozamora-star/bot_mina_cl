from flask import Flask, request, jsonify
import datetime

app = Flask(__name__)

# Este es el código que inventaste en Meta (Verify Token)
# Úsalo para configurar el Webhook en el paso 3 de Meta
VERIFY_TOKEN = "Mina_Giann_2026"

@app.route("/webhook", methods=["GET"])
def verify():
    # Meta usa esto para validar tu servidor
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == VERIFY_TOKEN:
        return challenge
    return "Token de verificación incorrecto", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    try:
        # Extraemos el mensaje y el número
        message = data['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        from_no = data['entry'][0]['changes'][0]['value']['messages'][0]['from']
        
        # Obtenemos la fecha actual de Perú
        ahora = datetime.datetime.now() - datetime.timedelta(hours=5)
        fecha_texto = ahora.strftime("%d/%m/%Y %H:%M:%S")

        print(f"Mensaje recibido: {message} de {from_no}")
        
        # Por ahora solo imprimimos en la consola de Railway para probar
        return jsonify({"status": "recibido"}), 200
    except:
        return jsonify({"status": "error"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
