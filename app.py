import os
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
from pymongo import MongoClient
from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
CLOUD_NAME = os.getenv("CLOUD_NAME")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
PORT = int(os.getenv("PORT", 5000))

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

if not os.path.exists("uploads"):
    os.makedirs("uploads")

try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client.get_default_database()
    photos_collection = db["photos"]
    print("MongoDB Connected")
except Exception as e:
    print("MongoDB error:", e)

cloudinary.config(
    cloud_name=CLOUD_NAME,
    api_key=API_KEY,
    api_secret=API_SECRET,
)


def photo_to_dict(photo):
    return {
        "_id": str(photo["_id"]),
        "imageUrl": photo.get("imageUrl"),
        "createdAt": photo.get("createdAt"),
    }



@app.route("/test", methods=["GET"])
def test_connection():
    print("ESP32 terhubung")
    return "OK"


@app.route("/upload", methods=["POST"])
def upload_photo():
    try:
        buffer = request.get_data()  

        if not buffer or len(buffer) == 0:
            return jsonify({"error": "Buffer kosong"}), 400

        result = cloudinary.uploader.upload(
            buffer,
            resource_type="image",
        )

        photo_doc = {
            "imageUrl": result["secure_url"],
            "createdAt": datetime.now(timezone.utc),
        }
        insert_result = photos_collection.insert_one(photo_doc)
        photo_doc["_id"] = insert_result.inserted_id

        photo_json = photo_to_dict(photo_doc)

        socketio.emit("new-photo", photo_json)

        return jsonify(photo_json)

    except Exception as e:
        print("Upload error:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/photos", methods=["GET"])
def get_photos():
    try:
        photos = photos_collection.find().sort("createdAt", -1)
        return jsonify([photo_to_dict(p) for p in photos])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/photos/<id>", methods=["DELETE"])
def delete_photo(id):
    try:
        photos_collection.delete_one({"_id": ObjectId(id)})
        return jsonify({"success": True})
    except InvalidId:
        return jsonify({"error": "ID tidak valid"}), 400
    except Exception as e:
        print("Delete error:", e)
        return jsonify({"error": str(e)}), 500


@socketio.on("connect")
def handle_connect():
    print("Client connected:", request.sid)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=PORT, allow_unsafe_werkzeug=True)