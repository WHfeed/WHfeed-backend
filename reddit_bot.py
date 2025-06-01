import json
import time
import praw
from datetime import datetime, timezone
from pathlib import Path

# === Reddit Auth ===
reddit = praw.Reddit(
    client_id="Q_3ktGvZNGC71dCrIWtQkQ",
    client_secret="vOjmdfZKS3o-VNjyhw2XiVQ4sqUZgQ",
    username="ProfileEmotional6042",
    password="MalRob114!",
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

# === Load summarized feed ===
with open("public/summarized_feed.json", "r", encoding="utf-8") as f:
    feed_data = json.load(f)

# === Only allow posts from the last 15 minutes ===
cutoff_time = datetime.now(timezone.utc).timestamp() - (15 * 60)

new_links = []
for post in feed_data["posts"]:
    if post["link"] in posted_links:
        continue

    try:
        post_time = datetime.fromisoformat(post["timestamp"]).timestamp()
        if post_time < cutoff_time:
            continue  # Skip old post
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
