from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

mongo_host = os.environ.get("MONGO_HOST", "localhost")
mongo_port = os.environ.get("MONGO_PORT", "27017")
mongo_user = os.environ.get("MONGO_USERNAME")
mongo_pass = os.environ.get("MONGO_PASSWORD")
mongo_auth_db = os.environ.get("MONGO_AUTH_SOURCE", "admin")

if mongo_user and mongo_pass:
    mongo_uri = (
        f"mongodb://{mongo_user}:{mongo_pass}@{mongo_host}:{mongo_port}/"
        f"?authSource={mongo_auth_db}"
    )
else:
    mongo_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")

client = MongoClient(mongo_uri)
db = client.flask_db
collection = db.data

@app.route('/')
def index():
    return f"Welcome to the Flask app! The current time is: {datetime.now()}"

@app.route('/healthz')
def healthz():
    return jsonify({"status": "ok"}), 200

@app.route('/data', methods=['GET', 'POST'])
def data():
    if request.method == 'POST':
        payload = request.get_json()
        collection.insert_one(payload)
        return jsonify({"status": "Data inserted"}), 201
    return jsonify(list(collection.find({}, {"_id": 0}))), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
