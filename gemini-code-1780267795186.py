import uuid
import math
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_ultra_securise_temporaire'
# cors_allowed_origins="*" permet de tester facilement en local
socketio = SocketIO(app, cors_allowed_origins="*")

# ==============================================================================
# STOCKAGE EN MÉMOIRE RAM (Pas de base de données)
# ==============================================================================

# Structure : { temp_id: { "socket_id": str, "lat": float, "lng": float, "status": "available"/"busy" } }
ACTIVE_DRIVERS = {}

# Structure : { temp_id: { "socket_id": str } }
ACTIVE_CLIENTS = {}

# Structure : { order_id: { "client_id": str, "driver_id": str, "status": "pending"/"accepted" } }
ORDERS = {}


# ==============================================================================
# FONCTIONS UTILITAIRES
# ==============================================================================

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calcule la distance en kilomètres entre deux points GPS (Formule de Haversine).
    """
    R = 6371.0  # Rayon de la Terre en km
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


# ==============================================================================
# API REST (JSON)
# ==============================================================================

@app.route('/connect/client', methods=['POST'])
def connect_client():
    """
    1. Connexion d'un client.
    Génère un identifiant temporaire unique sans stocker d'info personnelle.
    """
    temp_id = f"client_{uuid.uuid4().hex[:8]}"
    ACTIVE_CLIENTS[temp_id] = {"socket_id": None}
    
    return jsonify({
        "status": "success",
        "message": "Client connecté temporairement",
        "temp_id": temp_id
    }), 200


@app.route('/connect/driver', methods=['POST'])
def connect_driver():
    """
    2. Connexion d'un livreur.
    Génère un identifiant temporaire unique.
    """
    temp_id = f"driver_{uuid.uuid4().hex[:8]}"
    ACTIVE_DRIVERS[temp_id] = {
        "socket_id": None,
        "lat": None,
        "lng": None,
        "status": "available"
    }
    
    return jsonify({
        "status": "success",
        "message": "Livreur connecté temporairement",
        "temp_id": temp_id
    }), 200


@app.route('/location/update', methods=['POST'])
def update_location_http():
    """
    3. Mise à jour GPS via HTTP (Optionnel, Socket.IO est recommandé pour le temps réel).
    """
    data = request.json
    temp_id = data.get("temp_id")
    lat = data.get("lat")
    lng = data.get("lng")
    
    if temp_id in ACTIVE_DRIVERS:
        ACTIVE_DRIVERS[temp_id]["lat"] = float(lat)
        ACTIVE_DRIVERS[temp_id]["lng"] = float(lng)
        return jsonify({"status": "success", "message": "Position mise à jour"}), 200
        
    return jsonify({"status": "error", "message": "Livreur introuvable ou déconnecté"}), 404


@app.route('/drivers/nearby', methods=['GET'])
def get_nearby_drivers():
    """
    4. Recherche du livreur disponible le plus proche.
    Prend en paramètres query: lat, lng
    """
    try:
        client_lat = float(request.args.get('lat'))
        client_lng = float(request.args.get('lng'))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Coordonnées lat/lng invalides"}), 400

    closest_driver = None
    min_distance = float('inf')

    # Parcours des livreurs connectés et disponibles qui ont une position GPS valide
    for d_id, d_info in ACTIVE_DRIVERS.items():
        if d_info["status"] == "available" and d_info["lat"] is not None and d_info["lng"] is not None:
            dist = calculate_distance(client_lat, client_lng, d_info["lat"], d_info["lng"])
            if dist < min_distance:
                min_distance = dist
                closest_driver = {
                    "driver_id": d_id,
                    "distance_km": round(dist, 2),
                    "lat": d_info["lat"],
                    "lng": d_info["lng"]
                }

    if closest_driver:
        return jsonify({"status": "success", "closest_driver": closest_driver}), 200
    return jsonify({"status": "error", "message": "Aucun livreur disponible à proximité"}), 404


@app.route('/order/create', methods=['POST'])
def create_order():
    """
    5. Création d'une commande.
    Le client envoie son ID temporaire et les métadonnées de livraison (sans infos réelles persistées).
    """
    data = request.json
    client_id = data.get("client_id")
    driver_id = data.get("driver_id") # Optionnel si sélectionné via /drivers/nearby
    
    if client_id not in ACTIVE_CLIENTS:
        return jsonify({"status": "error", "message": "Client invalide"}), 400
        
    order_id = f"order_{uuid.uuid4().hex[:6]}"
    ORDERS[order_id] = {
        "client_id": client_id,
        "driver_id": driver_id,
        "status": "pending"
    }
    
    # Si un livreur spécifique était ciblé, on le notifie via WebSocket
    if driver_id and driver_id in ACTIVE_DRIVERS:
        driver_sid = ACTIVE_DRIVERS[driver_id]["socket_id"]
        if driver_sid:
            socketio.emit('new_order_request', {'order_id': order_id, 'client_id': client_id}, to=driver_sid)

    return jsonify({"status": "success", "order_id": order_id, "status": "pending"}), 201


@app.route('/order/accept', methods=['POST'])
def accept_order():
    """
    6. Acceptation d'une commande par le livreur.
    Met en relation le client et le livreur dans une "room" éphémère.
    """
    data = request.json
    order_id = data.get("order_id")
    driver_id = data.get("driver_id")
    
    if order_id not in ORDERS:
        return jsonify({"status": "error", "message": "Commande introuvable"}), 404
        
    order = ORDERS[order_id]
    if order["status"] != "pending":
        return jsonify({"status": "error", "message": "Commande déjà traitée"}), 400
        
    # Mise à jour des états
    order["driver_id"] = driver_id
    order["status"] = "accepted"
    if driver_id in ACTIVE_DRIVERS:
        ACTIVE_DRIVERS[driver_id]["status"] = "busy"
    
    # 7. Échange temporaire d'informations (via canaux de communication WebSocket)
    # On informe le client que sa commande est acceptée
    client_id = order["client_id"]
    client_sid = ACTIVE_CLIENTS.get(client_id, {}).get("socket_id")
    
    if client_sid:
        socketio.emit('order_accepted', {'order_id': order_id, 'driver_id': driver_id}, to=client_sid)
        
    return jsonify({"status": "success", "message": "Commande acceptée, canal éphémère ouvert"}), 200


@app.route('/order/complete', methods=['POST'])
def complete_order():
    """
    8. Suppression automatique des informations temporaires après la livraison.
    """
    data = request.json
    order_id = data.get("order_id")
    
    if order_id not in ORDERS:
        return jsonify({"status": "error", "message": "Commande introuvable"}), 404
        
    order = ORDERS[order_id]
    driver_id = order["driver_id"]
    client_id = order["client_id"]
    
    # Notifier les parties de la clôture via la room WebSocket dédiée à la commande
    socketio.emit('order_closed', {'order_id': order_id}, room=order_id)
    
    # Remettre le livreur disponible s'il est toujours en ligne
    if driver_id in ACTIVE_DRIVERS:
        ACTIVE_DRIVERS[driver_id]["status"] = "available"
        
    # NETTOYAGE STRICT EN MÉMOIRE
    if order_id in ORDERS:
        del ORDERS[order_id]
        
    return jsonify({"status": "success", "message": "Livraison terminée. Données éphémères détruites."}), 200


# ==============================================================================
# COMMUNICATION EN TEMPS RÉEL (Flask-SocketIO)
# ==============================================================================

@socketio.on('register')
def handle_register(data):
    """
    Permet d'associer l'ID temporaire généré par l'API REST au ID de session (sid) WebSocket.
    """
    temp_id = data.get('temp_id')
    role = data.get('role') # 'client' ou 'driver'
    
    if role == 'driver' and temp_id in ACTIVE_DRIVERS:
        ACTIVE_DRIVERS[temp_id]["socket_id"] = request.sid
        print(f"[WebSocket] Livreur {temp_id} enregistré avec le SID {request.sid}")
        emit('registration_confirmed', {'status': 'connected'})
        
    elif role == 'client' and temp_id in ACTIVE_CLIENTS:
        ACTIVE_CLIENTS[temp_id]["socket_id"] = request.sid
        print(f"[WebSocket] Client {temp_id} enregistré avec le SID {request.sid}")
        emit('registration_confirmed', {'status': 'connected'})
    else:
        emit('error', {'message': 'Identifiant temporaire invalide ou expiré'})


@socketio.on('join_order_room')
def handle_join_room(data):
    """
    Permet au client et au livreur de rejoindre un salon privé de discussion/suivi pour la commande.
    """
    order_id = data.get('order_id')
    if order_id in ORDERS:
        join_room(order_id)
        print(f"[WebSocket] {request.sid} a rejoint le salon éphémère : {order_id}")


@socketio.on('update_location_realtime')
def handle_location_push(data):
    """
    3. Mise à jour GPS en temps réel via WebSocket.
    Diffuse également la position en direct au client si le livreur est en course.
    """
    driver_id = data.get('driver_id')
    lat = float(data.get('lat'))
    lng = float(data.get('lng'))
    order_id = data.get('order_id') # Optionnel, fourni si le livreur est en course
    
    if driver_id in ACTIVE_DRIVERS:
        ACTIVE_DRIVERS[driver_id]["lat"] = lat
        ACTIVE_DRIVERS[driver_id]["lng"] = lng
        
        # Si le livreur est en cours de livraison, on pousse sa position uniquement dans la room de sa commande
        if order_id and order_id in ORDERS:
            emit('driver_location_shared', {'lat': lat, 'lng': lng}, room=order_id, include_self=False)


@socketio.on('disconnect')
def handle_disconnect():
    """
    9. Gestion de la déconnexion. 
    Nettoie instantanément la mémoire RAM si un utilisateur quitte l'application.
    """
    # Nettoyage côté livreurs
    for d_id, d_info in list(ACTIVE_DRIVERS.items()):
        if d_info["socket_id"] == request.sid:
            print(f"[WebSocket] Livreur {d_id} déconnecté. Suppression des données GPS.")
            del ACTIVE_DRIVERS[d_id]
            break
            
    # Nettoyage côté clients
    for c_id, c_info in list(ACTIVE_CLIENTS.items()):
        if c_info["socket_id"] == request.sid:
            print(f"[WebSocket] Client {c_id} déconnecté. Suppression des sessions.")
            del ACTIVE_CLIENTS[c_id]
            break


if __name__ == '__main__':
    # Lancement du serveur avec support WebSocket natif
    socketio.run(app, debug=True, port=5000)
