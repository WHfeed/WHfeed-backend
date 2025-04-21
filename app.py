from flask import Flask, jsonify
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

if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
