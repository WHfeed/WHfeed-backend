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

print("🔎 Summarizing latest White House communications...\n")

def fetch_tweets(username, count=5):
    if not TWITTER_API_KEY:
        print("❌ Twitter API key missing. Skipping X feeds.")
        return []
    url = f"https://api.twitterapi.io/twitter/user/last_tweets?userName={username}&limit={count}"
    headers = {"x-api-key": TWITTER_API_KEY}
    try:
        res = requests.get(url, headers=headers)
        data = res.json().get("data", {}).get("tweets", []) if res.status_code == 200 else []
        return [
            {"text": t["text"], "link": t["url"], "created_at": t["createdAt"]}
            for t in data if "text" in t and "url" in t
        ]
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
                    "content": """You are a geopolitical and financial analyst. If the post contains no actual content or is just a link, return:
{ "headline": "Skip", "summary": "no content", "tags": [], "sentiment": "Neutral", "impact": 0 }

Otherwise return:
{
  "headline": "...",      # max 8 words
  "summary": "...",       # 6–12 sentences
  "tags": ["...", "..."],
  "sentiment": "Bullish" | "Neutral" | "Bearish",
  "impact": 0–5
}
"""
                },
                {"role": "user", "content": f"Analyze the following post:\n\n{text}"}
            ],
            temperature=0.3,
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        return {"summary": f"[ERROR] {e}"}

def should_skip(summary, raw_text=""):
    summary = summary.lower().strip()
    raw_text = raw_text.lower().strip()
    generic = [
        "no content", "unknown", "", 
        "no specific information", "insufficient information", 
        "the post does not provide"
    ]
    if summary.startswith("[error") or summary in generic:
        return True
    return re.match(r"^https?://\S+$", summary) or re.match(r"^https?://\S+$", raw_text)

def run_main():
    json_path = Path("public/summarized_feed.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            summarized_entries = json.load(f)
    except:
        summarized_entries = []

    existing_links = {e["link"] for e in summarized_entries}

    for url, source in rss_feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                if entry.link in existing_links:
                    continue

                # Require actual content
                raw_title = getattr(entry, "title", "").strip()
                raw_body = getattr(entry, "summary", "") or getattr(entry, "description", "")
                if not raw_body or re.match(r"^https?://\S+$", raw_body):
                    print(f"⚠️ Skipping empty or link-only body: {raw_title}")
                    continue

                # Skip media
                link = entry.link.lower()
                if any(x in raw_title.lower() for x in ["video", "watch", "live", "speech"]) or "/media/" in link or "/videos/" in link:
                    print(f"⚠️ Skipping media post: {raw_title}")
                    continue

                result = analyze_post(raw_body)
                summary = result.get("summary", "").strip()
                if should_skip(summary, raw_body):
                    print(f"❌ Skipping post: {raw_title}")
                    continue

                clean_title = result.get("headline", "")[:60] if source == "Truth Social" else (
                    raw_title if raw_title else result.get("headline", "")[:60]
                )

                print(f"✅ Title: {clean_title}")
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
        except Exception as e:
            print(f"❌ RSS error: {e}")

    for username, source in twitter_accounts:
        tweets = fetch_tweets(username)[:1]
        for tweet in tweets:
            if tweet["link"] in existing_links:
                continue
            text = tweet["text"].strip()
            if re.match(r"^https?://\S+$", text):
                print(f"⚠️ Skipping link-only tweet: {text}")
                continue

            result = analyze_post(text)
            summary = result.get("summary", "").strip()
            if should_skip(summary, text):
                print(f"❌ Skipping tweet: {text}")
                continue

            clean_title = text[:80] + "..." if len(text) > 80 else text
            print(f"✅ Tweet Title: {clean_title}")
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
