from flask import Flask, jsonify
from flask_cors import CORS
import subprocess
import sys

app = Flask(__name__)
CORS(app)  # 👈 this is the key line to allow cross-origin requests

@app.route("/run-feed", methods=["POST"])
def run_feed_script():
    try:
        venv_python = sys.executable
        result = subprocess.run([venv_python, "whitehouse_feed.py"], capture_output=True, text=True)
        return jsonify({
            "status": "success",
            "stdout": result.stdout,
            "stderr": result.stderr
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

if __name__ == "__main__":
    app.run(debug=True)
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)

