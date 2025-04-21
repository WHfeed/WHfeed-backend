from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import os
from whitehouse_feed import run_main

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return "White House Feed Backend Running."

@app.route('/run-feed', methods=['GET', 'POST'])
def run_feed():
    run_main()
    return jsonify({"status": "Feed generated successfully."})

# ✅ Serve files from the public directory
@app.route('/public/<path:filename>')
def serve_public_file(filename):
    return send_from_directory('public', filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
