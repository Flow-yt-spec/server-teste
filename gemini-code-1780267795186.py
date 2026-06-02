import uuid
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_carte_pure_123'
socketio = SocketIO(app, cors_allowed_origins="*")

# Stockage en RAM : { socket_id: { "temp_id": str, "lat": float, "lng": float } }
CONNECTED_USERS = {}

@app.route('/')
def index():
    # Sert l'interface avec la carte Leaflet
    return render_template_string(HTML_TEMPLATE)

@socketio.on('connect')
def handle_connect():
    """Génère un ID temporaire anonyme à la connexion d'un utilisateur"""
    temp_id = f"User_{uuid.uuid4().hex[:4]}"
    CONNECTED_USERS[request.sid] = {
        "temp_id": temp_id,
        "lat": None,
        "lng": None
    }
    # Envoie l'ID temporaire à l'utilisateur qui vient de se connecter
    emit('init_user', {"temp_id": temp_id})

@socketio.on('share_location')
def handle_location(data):
    """Reçoit la position d'un utilisateur et la diffuse à tout le monde"""
    sid = request.sid
    if sid in CONNECTED_USERS:
        CONNECTED_USERS[sid]["lat"] = float(data["lat"])
        CONNECTED_USERS[sid]["lng"] = float(data["lng"])
        temp_id = CONNECTED_USERS[sid]["temp_id"]
        
        # On diffuse la mise à jour GPS à TOUS les utilisateurs connectés
        emit('update_map', {
            "id": temp_id, 
            "lat": data["lat"], 
            "lng": data["lng"]
        }, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    """Supprime l'utilisateur de la RAM et de la carte dès qu'il quitte"""
    sid = request.sid
    if sid in CONNECTED_USERS:
        temp_id = CONNECTED_USERS[sid]["temp_id"]
        del CONNECTED_USERS[sid]
        # On signale à tout le monde d'effacer ce marqueur de leur carte
        emit('remove_user', {"id": temp_id}, broadcast=True)


# ==============================================================================
# 2. INTERFACE HTML ET CARTE LIVE
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8" />
    <title>Carte GPS Collaborative en Temps Réel</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    
    <style>
        body { margin: 0; padding: 0; font-family: sans-serif; display: flex; height: 100vh; }
        #sidebar { width: 300px; background: #2c3e50; color: white; padding: 20px; box-sizing: border-box; }
        #map { flex: 1; height: 100%; }
        .info { background: #34495e; padding: 15px; border-radius: 5px; margin-top: 15px; }
        input { width: 80px; padding: 5px; margin: 5px; }
    </style>
</head>
<body>

    <div id="sidebar">
        <h2>🌐 Carte Live Pure</h2>
        <p>Chaque onglet ouvert simule un utilisateur différent sur la carte.</p>
        
        <div class="info">
            <h3>Mon Profil</h3>
            <p id="my-id">Connexion...</p>
            <hr>
            <h4>Simuler mon GPS :</h4>
            Lat: <input type="number" id="lat" value="48.8566" step="0.001" oninput="sendLocation()"><br>
            Lng: <input type="number" id="lng" value="2.3522" step="0.001" oninput="sendLocation()">
        </div>
    </div>

    <div id="map"></div>

    <script>
        // Initialisation de la carte (Centrée par défaut sur Paris)
        const map = L.map('map').setView([48.8566, 2.3522], 14); 

        // Chargement des fonds de carte OpenStreetMap
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap'
        }).addTo(map);

        // Dictionnaire local des marqueurs présents sur l'écran : { temp_id: marker_leaflet }
        const userMarkers = {};
        let myTempId = null;

        // Connexion WebSocket automatique
        const socket = io();

        // Réception de notre identifiant unique temporaire
        socket.on('init_user', function(data) {
            myTempId = data.temp_id;
            document.getElementById('my-id').innerHTML = `ID éphémère : <b style="color:#1abc9c;">${myTempId}</b>`;
            sendLocation(); // Envoi immédiat de notre première position par défaut
        });

        // Fonction pour envoyer nos coordonnées au serveur
        function sendLocation() {
            let lat = parseFloat(document.getElementById('lat').value);
            let lng = parseFloat(document.getElementById('lng').value);
            socket.emit('share_location', { lat: lat, lng: lng });
        }

        // Réception des positions de TOUT LE MONDE
        socket.on('update_map', function(data) {
            // Si le marqueur existe déjà, on le déplace
            if (userMarkers[data.id]) {
                userMarkers[data.id].setLatLng([data.lat, data.lng]);
            } else {
                // Sinon, on crée un marqueur sur la carte
                // Différencier notre marqueur (Rouge) des autres (Bleu)
                const isMe = data.id === myTempId;
                const dotColor = isMe ? 'red' : 'blue';

                const customIcon = L.divIcon({
                    className: 'custom-icon',
                    html: `<div style="background-color:${dotColor}; width:14px; height:14px; border-radius:50%; border:2px solid white; box-shadow:0 0 4px rgba(0,0,0,0.4);"></div>`,
                    iconSize: [14, 14],
                    iconAnchor: [7, 7]
                });

                userMarkers[data.id] = L.marker([data.lat, data.lng], {icon: customIcon}).addTo(map)
                    .bindPopup(isMe ? "<b>Moi</b>" : `<b>${data.id}</b>`);
            }
        });

        // Quand un utilisateur quitte, on l'enlève de la carte
        socket.on('remove_user', function(data) {
            if (userMarkers[data.id]) {
                map.removeLayer(userMarkers[data.id]);
                delete userMarkers[data.id];
            }
        });
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)
