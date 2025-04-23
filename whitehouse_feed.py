from pathlib import Path
import os
import openai
import feedparser
import json
import requests
from datetime import datetime

# Use OpenAI and TwitterAPI.io keys from environment
openai.api_key = os.environ["OPENAI_API_KEY"]
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")

# List of RSS feeds with platform labels
rss_feeds = [
    ("https://trumpstruth.org/feed", "Truth Social"),
    ("https://www.whitehouse.gov/news/feed", "White House"),
]

# Twitter accounts to fetch from
twitter_accounts = [
    ("JDVance1", "X - JD Vance"),
    ("elonmusk", "X - Elon Musk"),
    ("PressSec", "X - Press Secretary"),
    ("SecYellen", "X - Janet Yellen")
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
            tweets = response.json().get("tweets", [])
            return [
                {
                    "text": tweet["text"],
                    "link": tweet["url"],
                    "created_at": tweet["createdAt"]
                }
                for tweet in tweets
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
                    "content": """You are a geopolitical and financial analyst. For each Trump post, return the following:

- A brief summary (1–2 sentences)
- Tags (1–3 keywords like Immigration, Energy, Border, Foreign Policy, etc.)
- A general sentiment rating: Bearish, Neutral, or Bullish
- A JSON object with impact and directional sentiment ratings:

Impact scores use this scale:
0 = No impact
1 = Very low impact
2 = Slight impact
3 = Moderate impact
4 = Strong impact
5 = High / likely impact

Return scores for:
- stock_market (0–5)
- bond_market (0–5)
- currency (0–5)
- immigration_policy (0–5)
- global_relations (0–5)
- law_enforcement (0–5)

Also include:
- stock_sentiment: Bullish / Bearish / Neutral (based on stock_market context)
- bond_sentiment: Bullish / Bearish / Neutral (based on bond/treasury implications)

If a category is not relevant to the post, assign it a score of 0.

Only return valid JSON using this structure:

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
                    "content": f"Analyze the following post:\n\n{text}"
                }
            ],
            temperature=0.3
        )
        result = response.choices[0].message.content.strip()
        return json.loads(result)
    except Exception as e:
        return {"summary": "[ERROR] " + str(e)}

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
            if "summary" not in result:
                print("❌ Failed to process post.")
                continue

            print(f"🧠 Summary: {result['summary']}")
            print(f"🏷 Tags: {result.get('tags', [])}")
            print(f"📈 Sentiment: {result.get('sentiment', 'Unknown')}")
            print(f"📊 Impact: {json.dumps(result.get('impact', {}), indent=2)}")
            print("-" * 60)

            summarized_entries.append({
                "title": entry.title,
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
        tweets = fetch_tweets(username)
        for tweet in tweets:
            if tweet["link"] in existing_links:
                continue

            print(f"📰 Source: {source}")
            print(f"📢 Tweet: {tweet['text']}")
            print(f"🔗 {tweet['link']}")
            result = analyze_post(tweet["text"])
            if "summary" not in result:
                print("❌ Failed to process tweet.")
                continue

            print(f"🧠 Summary: {result['summary']}")
            print(f"🏷 Tags: {result.get('tags', [])}")
            print(f"📈 Sentiment: {result.get('sentiment', 'Unknown')}")
            print(f"📊 Impact: {json.dumps(result.get('impact', {}), indent=2)}")
            print("-" * 60)

            summarized_entries.append({
                "title": tweet["text"][:60] + "...",
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
