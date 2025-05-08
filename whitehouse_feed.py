from pathlib import Path
import os
import json
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
                    "content": """You are a geopolitical and financial analyst. For each post, return:

- A brief summary (1–2 sentences)
- Tags (1–3 keywords like Immigration, Energy, Foreign Policy)
- Sentiment rating (Bullish, Neutral, Bearish)
- JSON impact ratings (0–5) for stock_market, bond_market, currency, immigration_policy, global_relations, law_enforcement
- Stock and bond directional sentiment (Bullish, Neutral, Bearish)

Use this exact format:
{
  "summary": "...",
  "tags": ["..."],
  "sentiment": "...",
  "impact": {
    "stock_market": X,
    "stock_sentiment": "...",
    "bond_market": X,
    "bond_sentiment": "...",
    "currency": X,
    "immigration_policy": X,
    "global_relations": X,
    "law_enforcement": X
  }
}"""
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
        return {"summary": "[ERROR] " + str(e)}

def should_skip(summary_text):
    skip_phrases = [
        "no specific information provided",
        "unknown",
        "no content",
        "",
    ]
    
    # Normalize summary text for comparison
    summary_text = summary_text.lower().strip()

    # Skip if summary starts with [ERROR]
    if summary_text.startswith("[error"):
        return True

    return summary_text in skip_phrases

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
            if hasattr(entry, "media_content") or "video" in entry.title.lower():
                print(f"⚠️ Skipping media post: {entry.title}")
                continue

            print(f"📰 Source: {source}")
            print(f"📢 Original Post: {entry.title}")
            print(f"🔗 {entry.link}")

            result = analyze_post(entry.title)
            if "summary" not in result or should_skip(result.get("summary", "")):
                print("❌ Skipping post due to weak/empty summary.")
                continue

            # Clean title logic
            clean_title = entry.title.strip() if hasattr(entry, "title") and entry.title.strip() != "" else None
            if not clean_title:
                clean_title = result.get("summary", "")[:60] + "..."

            print(f"✅ Final Title: {clean_title}")

            summarized_entries.append({
                "title": clean_title,
                "link": entry.link,
                "published": entry.published if "published" in entry else None,
                "summary": result.get("summary", ""),
                "tags": result.get("tags", []),
                "sentiment": result.get("sentiment", "Unknown"),
                "impact": result.get("impact", {}),
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

            print(f"📰 Source: {source}")
            print(f"📢 Tweet: {tweet['text']}")
            print(f"🔗 {tweet['link']}")

            result = analyze_post(tweet["text"])
            if "summary" not in result or should_skip(result.get("summary", "")):
                print("❌ Skipping tweet due to weak/empty summary.")
                continue

            clean_title = tweet["text"].strip()
            if len(clean_title) > 80:
                clean_title = clean_title[:80] + "..."

            if not clean_title:
                clean_title = result.get("summary", "")[:60] + "..."

            print(f"✅ Final Title: {clean_title}")

            summarized_entries.append({
                "title": clean_title,
                "link": tweet["link"],
                "published": tweet["created_at"],
                "summary": result.get("summary", ""),
                "tags": result.get("tags", []),
                "sentiment": result.get("sentiment", "Unknown"),
                "impact": result.get("impact", {}),
                "source": source,
                "timestamp": datetime.now().isoformat()
            })

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summarized_entries, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    run_main()
