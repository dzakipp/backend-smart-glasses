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

# ── Load environment variables ─────────────────────────────
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
CLOUD_NAME = os.getenv("CLOUD_NAME")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
PORT = int(os.getenv("PORT", 5000))

# ── App & extensions ────────────────────────────────────────
app = Flask(__name__)

# CORS — izinkan semua origin (setara app.use((req,res,next)=>{...}) di Express)
CORS(app, resources={r"/*": {"origins": "*"}})

# Socket.IO — cors_allowed_origins "*" setara { cors: { origin: "*" } } di Node
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Pastikan folder uploads ada (untuk kebutuhan lokal, seperti fs.existsSync di Node)
if not os.path.exists("uploads"):
    os.makedirs("uploads")

# ── MongoDB ─────────────────────────────────────────────────
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client.get_default_database()
    photos_collection = db["photos"]
    print("MongoDB Connected")
except Exception as e:
    print("MongoDB error:", e)

# ── Cloudinary ──────────────────────────────────────────────
cloudinary.config(
    cloud_name=CLOUD_NAME,
    api_key=API_KEY,
    api_secret=API_SECRET,
)


# ── Helpers ─────────────────────────────────────────────────
def photo_to_dict(photo):
    """Ubah dokumen MongoDB jadi JSON yang formatnya sama seperti versi Node
    (field _id sebagai string, imageUrl, createdAt)."""
    return {
        "_id": str(photo["_id"]),
        "imageUrl": photo.get("imageUrl"),
        "createdAt": photo.get("createdAt"),
    }


# ── Routes ──────────────────────────────────────────────────

# Test koneksi ESP32
@app.route("/test", methods=["GET"])
def test_connection():
    print("ESP32 terhubung")
    return "OK"


# Upload foto dari ESP32 → simpan ke Cloudinary → simpan ke MongoDB
@app.route("/upload", methods=["POST"])
def upload_photo():
    try:
        buffer = request.get_data()  # raw bytes, setara express.raw({type:"image/jpeg"})

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


# Ambil semua foto (terbaru duluan)
@app.route("/photos", methods=["GET"])
def get_photos():
    try:
        photos = photos_collection.find().sort("createdAt", -1)
        return jsonify([photo_to_dict(p) for p in photos])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Hapus foto
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


# ── Socket ──────────────────────────────────────────────────
@socketio.on("connect")
def handle_connect():
    print("Client connected:", request.sid)


# ── Entrypoint ──────────────────────────────────────────────
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=PORT)
