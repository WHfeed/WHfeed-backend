from pathlib import Path
import os
import json
import re
from dotenv import load_dotenv
import openai
import feedparser
import requests
from datetime import datetime

# Load secrets
load_dotenv()
openai.api_key = os.environ["OPENAI_API_KEY"]
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")

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

def fetch_tweets(username, count=5):
    if not TWITTER_API_KEY:
        print("❌ No Twitter API key.")
        return []
    url = f"https://api.twitterapi.io/twitter/user/last_tweets?userName={username}&limit={count}"
    headers = {"x-api-key": TWITTER_API_KEY}
    try:
        res = requests.get(url, headers=headers)
        tweets = res.json().get("data", {}).get("tweets", []) if res.status_code == 200 else []
        return [{"text": t["text"], "link": t["url"], "created_at": t["createdAt"]} for t in tweets]
    except Exception as e:
        print(f"❌ Twitter fetch failed: {e}")
        return []

def analyze_post(text):
    try:
        res = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            temperature=0.3,
            messages=[
                {"role": "system", "content": """You are a geopolitical and financial analyst. Only return JSON:

{
  "headline": "...",
  "summary": "...",
  "tags": ["..."],
  "sentiment": "Bullish | Neutral | Bearish",
  "impact": X (0–5)
}
"""}, {"role": "user", "content": f"Analyze:\n\n{text}"}
            ],
        )
        return json.loads(res.choices[0].message.content.strip())
    except Exception as e:
        print(f"❌ OpenAI error: {e}")
        return {"summary": f"[ERROR] {e}"}

def is_raw_link_only(text):
    return bool(re.fullmatch(r"https?://\S+", text.strip()))

def should_skip(summary, original=""):
    skip_phrases = [
        "no specific information provided",
        "insufficient information provided for analysis",
        "the post does not provide any specific information",
        "the post does not provide any specific information or context to analyze",
        "unknown", "no content", ""
    ]
    s, o = summary.lower().strip(), original.lower().strip()
    return (
        s.startswith("[error") or s in skip_phrases or
        is_raw_link_only(s) or is_raw_link_only(o)
    )

def run_main():
    json_path = Path("public/summarized_feed.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.load(open(json_path)) if json_path.exists() else []
    seen_links = {e["link"] for e in existing}

    entries = []

    for url, source in rss_feeds:
        print(f"\n🌐 RSS: {source}")
        try:
            feed = feedparser.parse(url)
            if not feed.entries:
                print("⚠️ No entries found.")
                continue
        except Exception as e:
            print(f"❌ Parse error: {e}")
            continue

        for entry in feed.entries[:5]:
            if entry.link in seen_links:
                continue

            title = getattr(entry, "title", "").strip()
            body = getattr(entry, "summary", "") or getattr(entry, "description", "")
            post_link = entry.link.lower()

            if is_raw_link_only(title) or is_raw_link_only(body):
                print(f"⚠️ Skipping link-only RSS post.")
                continue

            if hasattr(entry, "media_content") or any(
                word in title.lower() for word in ["video", "speech", "watch", "live"]
            ) or any(seg in post_link for seg in ["/media/", "/videos/"]):
                print(f"⚠️ Skipping media: {title}")
                continue

            text_to_analyze = body if source == "White House" else title
            result = analyze_post(text_to_analyze)
            summary = result.get("summary", "").strip()

            if should_skip(summary, text_to_analyze):
                print(f"❌ Skipping weak content.")
                continue

            final_title = result.get("headline", "")[:60] if source == "Truth Social" else title or result.get("headline", "")[:60]
            print(f"✅ {final_title}")
            entries.append({
                "title": final_title,
                "link": entry.link,
                "published": getattr(entry, "published", None),
                "summary": summary,
                "tags": result.get("tags", []),
                "sentiment": result.get("sentiment", "Unknown"),
                "impact": result.get("impact", 0),
                "source": source,
                "timestamp": datetime.now().isoformat()
            })

    for username, source in twitter_accounts:
        print(f"\n📡 Tweets: {username}")
        tweets = fetch_tweets(username)[:1]
        print(f"📄 {len(tweets)} tweets.")

        for tweet in tweets:
            if tweet["link"] in seen_links:
                continue

            text = tweet["text"].strip()
            if is_raw_link_only(text):
                print(f"⚠️ Skipping raw link tweet.")
                continue

            result = analyze_post(text)
            summary = result.get("summary", "").strip()

            if should_skip(summary, text):
                print(f"❌ Skipping tweet.")
                continue

            final_title = text if len(text) <= 80 else text[:80] + "..."
            entries.append({
                "title": final_title,
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
        json.dump(existing + entries, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    run_main()
