import os
import json

def save_summarized_feed(summarized_feed):
    # Ensure 'public' folder exists
    os.makedirs("public", exist_ok=True)

    # Define path to save summarized_feed.json inside 'public' folder
    output_path = os.path.join("public", "summarized_feed.json")

    # Save JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summarized_feed, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved summarized_feed.json to {output_path}")
