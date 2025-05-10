from pathlib import Path
import os
import json
from dotenv import load_dotenv
import openai
import feedparser
import requests
from datetime import datetime
import re

# Load environment variables
load_dotenv()
openai.api_key = os.environ["OPENAI_API_KEY"]
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")

# Define RSS feeds and Twitter accounts
rss_feeds = [
    ("https://trumpstruth.org/feed", "Truth Social"),
    ("https://www.whitehouse.gov/news/feed", "White House"),
]

twitter_accounts = [
    ("JDVance", "X - JD Vance"),
    ("POTUS", "X - POTUS"),
    ("elonmusk", "X - Elon Musk"),
    ("PressSec", "X - Press Secretary"),
    ("SecYellen", "X - Janet Yellen"),
]

print("Summarizing Latest White House Communications...\n")

def fetch_tweets(username, count=5):
    if not TWITTER_API_KEY:
        print("❌ Twitter API key missing. Skipping X feeds.")
        return []

    url = f"https://api.twitterapi.io/twitter/user/last_tweets?userName={username}&limit={count}"
    headers = {"x-api-key": TWITTER_API_KEY}

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json().get("data")
            if not data or "tweets" not in data:
                print(f"❌ No tweet data available for {username}. Raw response: {response.text}")
                return []
            return [
                {
                    "text": tweet["text"],
                    "link": tweet["url"],
                    "created_at": tweet["createdAt"],
                }
                for tweet in data.get("tweets", [])
            ]
        else:
            print(f"❌ Failed to fetch tweets for {username}: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Twitter fetch error for {username}: {e}")
        return []

def analyze_post(text):
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": """You are a geopolitical and financial analyst. You will analyze political and financial posts and return only the following fields in JSON format:

- A short and punchy headline (maximum 8 words)
- A concise summary (up to 6 sentences for shorter posts, up to 12 sentences if the post contains complex government information)
- 1–3 highly relevant tags
- A general sentiment rating: Bullish, Neutral, or Bearish (based on market relevance)
- An overall impact rating (0–5), based on how much this post could affect markets or policy.

Impact scale:
0 = No impact
1 = Very low
2 = Slight
3 = Moderate
4 = Strong
5 = Very strong / market moving

Output only valid JSON using this structure:

{
  "headline": "...",
  "summary": "...",
  "tags": ["...", "..."],
  "sentiment": "...",
  "impact": X
}
"""
                },
                {
                    "role": "user",
                    "content": f"Analyze the following post:\n\n{text}",
                },
            ],
            temperature=0.3,
        )
        result = response.choices[0].message.content.strip()
        return json.loads(result)
    except Exception as e:
        return {"summary": f"[ERROR] {e}"}

def should_skip(summary_text, original_text=""):
    skip_phrases = [
        "no specific information provided",
        "insufficient information provided for analysis",
        "unknown",
        "no content",
        "",
    ]
    summary_text = summary_text.lower().strip()
    original_text = original_text.lower().strip()

    if summary_text.startswith("[error") or summary_text in skip_phrases:
        return True

    if re.match(r"^https?://\S+$", summary_text) or re.match(r"^https?://\S+$", original_text):
        return True

    return False

def run_main():
    json_path = Path("public/summarized_feed.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)

    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            summarized_entries = json.load(f)
    else:
        summarized_entries = []

    existing_links = {entry["link"] for entry in summarized_entries}

    # Process RSS feeds
    for url, source in rss_feeds:
        try:
            feed = feedparser.parse(url)
            if not feed.entries:
                print(f"⚠️ No entries found for {source} at {url}")
                continue
        except Exception as e:
            print(f"❌ Failed to parse feed from {url}: {e}")
            continue

        for entry in feed.entries[:5]:
            if entry.link in existing_links:
                continue

            title_text = entry.title.strip() if hasattr(entry, "title") else ""
            if re.match(r"^https?://\S+$", title_text):
                print(f"⚠️ Skipping raw link-only post: {title_text}")
                continue

            post_title = title_text.lower()
            post_link = entry.link.lower()

            is_media_post = (
                hasattr(entry, "media_content") or
                "video" in post_title or
                "watch" in post_title or
                "speech" in post_title or
                "live" in post_title or
                "/videos/" in post_link or
                "/media/" in post_link
            )
            if is_media_post:
                print(f"⚠️ Skipping media post: {title_text or '[No Title]'}")
                continue

            result = analyze_post(title_text)
            summary = result.get("summary", "").strip()

            if should_skip(summary, title_text):
                print("❌ Skipping post due to weak/empty summary or raw link.")
                continue

            clean_title = result.get("headline", "")[:60] if source == "Truth Social" else (
                title_text if title_text else result.get("headline", "")[:60]
            )

            print(f"✅ Final Title: {clean_title}")

            summarized_entries.append({
                "title": clean_title,
                "link": entry.link,
                "published": getattr(entry, "published", None),
                "summary": summary,
                "tags": result.get("tags", []),
                "sentiment": result.get("sentiment", "Unknown"),
                "impact": result.get("impact", 0),
                "source": source,
                "timestamp": datetime.now().isoformat()
            })

    # Process Twitter accounts
    for username, source in twitter_accounts:
        print(f"📡 Fetching tweets from: {username}")
        tweets = fetch_tweets(username)[:1]
        print(f"📄 Found {len(tweets)} tweets from {username}")

        for tweet in tweets:
            if tweet["link"] in existing_links:
                continue

            tweet_text = tweet["text"].strip()
            if re.match(r"^https?://\S+$", tweet_text):
                print(f"⚠️ Skipping raw link-only tweet: {tweet_text}")
                continue

            result = analyze_post(tweet_text)
            summary = result.get("summary", "").strip()

            if should_skip(summary, tweet_text):
                print("❌ Skipping tweet due to weak/empty summary or raw link.")
                continue

            clean_title = tweet_text if len(tweet_text) <= 80 else tweet_text[:80] + "..."
            if not clean_title:
                clean_title = result.get("headline", "")[:60]

            print(f"✅ Final Title: {clean_title}")

            summarized_entries.append({
                "title": clean_title,
                "link": tweet["link"],
                "published": tweet["created_at"],
                "summary": summary,
                "tags": result.get("tags", []),
                "sentiment": result.get("sentiment", "Unknown"),
                "impact": result.get("impact", 0),
                "source": source,
                "timestamp": datetime.now().isoformat()
            })

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summarized_entries, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    run_main()
