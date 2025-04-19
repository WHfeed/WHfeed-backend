from dotenv import load_dotenv
import os
import openai
import feedparser
import json
from datetime import datetime
from pathlib import Path

# Load environment variables from .env file
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# List of RSS feeds (Trump + Official White House News)
rss_feeds = [
    "https://trumpstruth.org/feed",
    "https://www.whitehouse.gov/news/feed"
]

print("Summarizing Latest Donald Trump Truth Social Posts...\n")

# Analyze and score a post using GPT
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

# Load existing file or create empty list
json_path = Path("C:/Users/Leroy/trump-feed-dashboard/public/summarized_feed.json")
if json_path.exists():
    with open(json_path, "r", encoding="utf-8") as f:
        summarized_entries = json.load(f)
else:
    summarized_entries = []


existing_links = {entry["link"] for entry in summarized_entries}

# Process new posts from all RSS sources
for url in rss_feeds:
    feed = feedparser.parse(url)

    for entry in feed.entries[:5]:
        if entry.link in existing_links:
            continue

        print(f"📰 Source: {url}")
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
            "timestamp": datetime.now().isoformat()
        })



# Save updated list
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(summarized_entries, f, indent=4, ensure_ascii=False)

