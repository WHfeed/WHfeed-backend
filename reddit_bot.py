import json
import time
import os
import praw
import requests
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# === Reddit Auth (from environment variables) ===
reddit = praw.Reddit(
    client_id=os.getenv("CLIENT_ID"),
    client_secret=os.getenv("CLIENT_SECRET"),
    username=os.getenv("REDDIT_USERNAME"),
    password=os.getenv("REDDIT_PASSWORD"),
    user_agent="WhiteHouseFeedBot/0.1 by ProfileEmotional6042"
)

subreddit_name = "WhiteHouseFeed"
log_path = Path("posted_reddit_links.json")

# === Load already-posted links ===
if log_path.exists():
    with open(log_path, "r") as f:
        posted_links = set(json.load(f))
else:
    posted_links = set()

# === Fetch live feed from backend ===
try:
    print("🌐 Fetching live feed from backend...")
    response = requests.get("https://whfeed-backend.onrender.com/feed")
    response.raise_for_status()
    feed_data = response.json()
except Exception as e:
    print(f"❌ Failed to fetch feed: {e}")
    exit(1)

# === Only allow posts from the last 2 hours ===
cutoff_time = datetime.now(timezone.utc).timestamp() - (2 * 60 * 60)

new_links = []
for post in feed_data["posts"]:
    print(f"⏳ Checking post: {post['title']} at {post['timestamp']}")
    if post["link"] in posted_links:
        print("⏭️ Already posted")
        continue

    try:
        post_time = datetime.fromisoformat(post["timestamp"]).timestamp()
        if post_time < cutoff_time:
            print("⏭️ Skipping (too old)")
            continue
    except Exception as e:
        print(f"⚠️ Skipping due to bad timestamp in post: {post.get('title', 'No Title')}")
        continue

    # === Format Reddit Post ===
    title = post["title"]
    summary = post["summary"]
    link = "https://whitehousefeed.com"
    body = f"{summary}\n\n[More at WhiteHouseFeed]({link})"

    try:
        reddit.subreddit(subreddit_name).submit(title=title, selftext=body)
        print(f"✅ Posted to Reddit: {title}")
        posted_links.add(post["link"])
        new_links.append(post["link"])
        time.sleep(10)  # Prevent rate-limiting
    except Exception as e:
        print(f"❌ Failed to post {title}: {e}")

# === Save log ===
with open(log_path, "w", encoding="utf-8") as f:
    json.dump(list(posted_links), f, indent=2)
