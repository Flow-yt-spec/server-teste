from flask import Flask, jsonify, request
from flask_cors import CORS
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import os

app = Flask(__name__)
# Autorise ton fichier HTML local à communiquer avec le serveur Render
CORS(app)

# Variable globale pour stocker la position du livreur en direct (coordonnées d'Abidjan par défaut)
position_livreur = {
    "lat": 5.3484,
    "lng": -4.0154
}

@app.route('/')
def home():
    return jsonify({
        "status": "success", 
        "message": "Le moteur de livraison en temps réel est actif ! 📡"
    })

# 1. ROUTE POUR LE LIVREUR : Met à jour la position GPS sur le serveur
@app.route('/mettre-a-jour-position', methods=['GET'])
def mettre_a_jour_position():
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    
    if not lat or not lng:
        return jsonify({"status": "error", "message": "Coordonnées lat ou lng manquantes"}), 400
        
    position_livreur["lat"] = float(lat)
    position_livreur["lng"] = float(lng)
    
    return jsonify({"status": "success", "nouvelle_position": position_livreur})

# 2. ROUTE POUR LE CLIENT : Récupère la position actuelle du livreur
@app.route('/recuperer-position-livreur', methods=['GET'])
def recuperer_position_livreur():
    return jsonify({
        "status": "success",
        "position": position_livreur
    })

# 3. ROUTE DE CALCUL : Géolocalise le trajet et estime le prix
@app.route('/calculer-course')
def calculer_course():
    depart = request.args.get('depart')
    arrivee = request.args.get('arrivee')
    
    if not depart or not arrivee:
        return jsonify({"status": "error", "message": "Départ et arrivée requis"}), 400
        
    try:
        geolocator = Nominatim(user_agent="livraison_app_pro")
        loc_depart = geolocator.geocode(depart + ", Côte d'Ivoire")
        loc_arrivee = geolocator.geocode(arrivee + ", Côte d'Ivoire")
        
        if not loc_depart or not loc_arrivee:
            return jsonify({"status": "error", "message": "Adresse introuvable en Côte d'Ivoire"}), 400
        
        # Calcul de la distance réelle en kilomètres
        coords_dep = (loc_depart.latitude, loc_depart.longitude)
        coords_arr = (loc_arrivee.latitude, loc_arrivee.longitude)
        distance = round(geodesic(coords_dep, coords_arr).kilometers, 2)
        
        # Tarif de base (600 FCFA) + 150 FCFA par kilomètre
        prix = int(600 + (distance * 150))
        
        return jsonify({
            "status": "success",
            "details": {
                "distance_km": distance,
                "lat_dep": loc_depart.latitude,
                "lng_dep": loc_depart.longitude,
                "lat_arr": loc_arrivee.latitude,
                "lng_arr": loc_arrivee.longitude
            },
            "resultats": {
                "prix_estimation_FCFA": prix
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
