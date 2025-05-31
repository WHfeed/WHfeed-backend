from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import os
import json
from pathlib import Path
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

@app.route('/reset-and-run-feed', methods=['POST'])
def reset_and_run_feed():
    token = request.headers.get("x-auth-token")
    if token != os.environ.get("RESET_TOKEN"):
        return jsonify({"error": "Unauthorized"}), 403

    json_path = os.path.join(app.static_folder, "summarized_feed.json")
    try:
        if os.path.exists(json_path):
            os.remove(json_path)
            print("🗑️ Old summarized_feed.json deleted.")
    except Exception as e:
        return jsonify({"error": f"Failed to delete file: {e}"}), 500

    run_main()
    return jsonify({"status": "Feed reset and regenerated successfully."})

@app.route("/clean-feed", methods=["GET"])
def clean_feed():
    json_path = Path("public/summarized_feed.json")
    if not json_path.exists():
        return jsonify({"error": "Feed file not found"}), 404

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return jsonify({"error": f"Failed to parse JSON: {e}"}), 500

    original_len = len(data.get("posts", []))
    filtered_posts = [p for p in data["posts"] if not p["source"].startswith("DoD")]
    removed = original_len - len(filtered_posts)
    data["posts"] = filtered_posts

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        return jsonify({"error": f"Failed to write cleaned feed: {e}"}), 500

    return jsonify({
        "status": "success",
        "removed": removed,
        "remaining": len(filtered_posts)
    }), 200

@app.route('/delete-post', methods=['POST'])
def delete_post():
    token = request.headers.get("x-auth-token")
    if token != os.environ.get("DELETE_TOKEN"):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    link_to_delete = data.get("link")

    if not link_to_delete:
        return jsonify({"error": "Missing 'link' parameter"}), 400

    json_path = Path("public/summarized_feed.json")
    if not json_path.exists():
        return jsonify({"error": "Feed file not found"}), 404

    try:
        # Load and filter summarized feed
        with open(json_path, "r", encoding="utf-8") as f:
            feed = json.load(f)

        original_len = len(feed.get("posts", []))
        feed["posts"] = [p for p in feed["posts"] if p["link"] != link_to_delete]

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(feed, f, indent=4, ensure_ascii=False)

        removed = original_len - len(feed["posts"])

        # Append to deleted_links.json
        deleted_links_path = Path("public/deleted_links.json")
        try:
            if deleted_links_path.exists():
                with open(deleted_links_path, "r", encoding="utf-8") as f:
                    deleted_links = json.load(f)
            else:
                deleted_links = []

            if link_to_delete not in deleted_links:
                deleted_links.append(link_to_delete)
                with open(deleted_links_path, "w", encoding="utf-8") as f:
                    json.dump(deleted_links, f, indent=2)

        except Exception as e:
            return jsonify({"error": f"Failed to update deleted_links.json: {e}"}), 500

        return jsonify({"status": "success", "removed": removed}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/restore-feed', methods=['POST'])
def restore_feed():
    token = request.headers.get("x-auth-token")
    if token != os.environ.get("DELETE_TOKEN"):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    if not isinstance(data, list):
        return jsonify({"error": "Invalid data format: must be a JSON array"}), 400

    json_path = Path("public/summarized_feed.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return jsonify({"status": "Feed restored successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to write feed: {e}"}), 500
    
@app.route('/backup-feed', methods=['GET'])
def backup_feed():
    token = request.headers.get("x-auth-token")
    if token != os.environ.get("DELETE_TOKEN"):
        return jsonify({"error": "Unauthorized"}), 403

    json_path = Path("public/summarized_feed.json")
    if not json_path.exists():
        return jsonify({"error": "Feed file not found"}), 404

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"Failed to read feed: {e}"}), 500


# ✅ Keep only one main block
if __name__ == "__main__":
    port = os.environ.get("PORT")
    if port is None:
        raise RuntimeError("PORT environment variable not set.")
    app.run(host="0.0.0.0", port=int(port), debug=False)
