from pathlib import Path
import os
import json
import re
from dotenv import load_dotenv
import openai
import feedparser
import requests
from datetime import datetime

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
                print(f"❌ No tweet data for {username}")
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
                    "content": """You are a geopolitical and financial analyst. Return only the following fields in JSON:

- headline (max 8 words)
- summary (6–12 sentences depending on source)
- 1–3 tags
- sentiment: Bullish, Neutral, or Bearish
- impact: number 0–5

Use this format:

{
  "headline": "...",
  "summary": "...",
  "tags": ["..."],
  "sentiment": "...",
  "impact": X
}
"""
                },
                {
                    "role": "user",
                    "content": f"Analyze the following post:\n\n{text}"
                },
            ],
            temperature=0.3,
        )
        result = response.choices[0].message.content.strip()
        return json.loads(result)
    except Exception as e:
        print(f"❌ OpenAI error: {e}")
        return {"summary": f"[ERROR] {e}"}

def should_skip(summary_text, original_text=""):
    skip_phrases = [
        "no specific information provided",
        "insufficient information provided for analysis",
        "the post does not provide any specific information",
        "the post does not provide any specific information or context to analyze",
        "unknown",
        "no content",
        "",
    ]
    summary_text = summary_text.lower().strip()
    original_text = original_text.lower().strip()

    is_error = summary_text.startswith("[error")
    is_raw_link = re.match(r"^https?://\S+$", summary_text) or re.match(r"^https?://\S+$", original_text)

    return is_error or summary_text in skip_phrases or is_raw_link

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
                print(f"⚠️ No entries in feed: {source}")
                continue
        except Exception as e:
            print(f"❌ Failed to parse {source}: {e}")
            continue

        for entry in feed.entries[:5]:
            if entry.link in existing_links:
                continue

            raw_title = entry.title.strip() if hasattr(entry, "title") else ""
            if re.match(r"^https?://\S+$", raw_title):
                print(f"⚠️ Skipping link-only post: {raw_title}")
                continue

            link = entry.link.lower()
            is_media = (
                hasattr(entry, "media_content") or
                any(word in raw_title.lower() for word in ["video", "speech", "watch", "live"]) or
                any(seg in link for seg in ["/media/", "/videos/"])
            )
            if is_media:
                print(f"⚠️ Skipping media post: {raw_title}")
                continue

            result = analyze_post(raw_title)
            summary = result.get("summary", "").strip()
            if should_skip(summary, raw_title):
                print(f"❌ Skipping post: {raw_title}")
                continue

            clean_title = result.get("headline", "")[:60] if source == "Truth Social" else (
                raw_title or result.get("headline", "")[:60]
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
        print(f"📄 Found {len(tweets)} tweets")

        for tweet in tweets:
            if tweet["link"] in existing_links:
                continue

            tweet_text = tweet["text"].strip()
            if re.match(r"^https?://\S+$", tweet_text):
                print(f"⚠️ Skipping link-only tweet: {tweet_text}")
                continue

            result = analyze_post(tweet_text)
            summary = result.get("summary", "").strip()
            if should_skip(summary, tweet_text):
                print(f"❌ Skipping tweet: {tweet_text}")
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
