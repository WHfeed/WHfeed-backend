from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import os
from whitehouse_feed import run_main

app = Flask(__name__, static_folder="public")
CORS(app)

@app.route('/')
def home():
    return "White House Feed Backend Running."

@app.route('/run-feed', methods=['GET', 'POST'])
def run_feed():
    run_main()
    return jsonify({"status": "Feed generated successfully."})

@app.route('/feed', methods=['GET'])
def get_feed():
    try:
        return send_from_directory(app.static_folder, "summarized_feed.json")
    except FileNotFoundError:
        return jsonify({"error": "Feed file not found"}), 404

if __name__ == "__main__":
    port = os.environ.get("PORT")
    if port is None:
        raise RuntimeError("PORT environment variable not set.")
    app.run(host="0.0.0.0", port=int(port), debug=False)
