from flask import Flask, jsonify
import os

# Création de l'application Flask
app = Flask(__name__)

# La route principale
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "success",
        "message": "Le serveur fonctionne ! 🚀"
    })

# Démarrage du serveur
if __name__ == "__main__":
    # Render attribue un PORT dynamiquement, en local on prend le 5000 par défaut
    port = int(os.environ.get("PORT", 5000))
    # On force l'écoute sur 0.0.0.0 pour que Render puisse rediriger le trafic vers l'application
    app.run(host="0.0.0.0", port=port)