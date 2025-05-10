from pathlib import Path
import os
import json
import re
from dotenv import load_dotenv
import openai
import feedparser
import requests
from bs4 import BeautifulSoup
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

def fetch_tweets(username, count=5):
    if not TWITTER_API_KEY:
        print("❌ Twitter API key missing. Skipping X feeds.")
        return []
    url = f"https://api.twitterapi.io/twitter/user/last_tweets?userName={username}&limit={count}"
    headers = {"x-api-key": TWITTER_API_KEY}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json().get("data", {}).get("tweets", [])
            return [{"text": t["text"], "link": t["url"], "created_at": t["createdAt"]} for t in data]
        else:
            print(f"❌ Failed to fetch tweets for {username}: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Twitter fetch error for {username}: {e}")
        return []

def fetch_page_text(url):
    try:
        res = requests.get(url, timeout=6)
        soup = BeautifulSoup(res.text, "html.parser")
        paragraphs = soup.find_all("p")
        return " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)).strip()
    except Exception as e:
        print(f"⚠️ Could not extract HTML content from {url}: {e}")
        return ""

def is_useless_content(text):
    """Returns True if text is just a link/image/video or too short to be meaningful."""
    if not text or text.strip() == "":
        return True
    plain = BeautifulSoup(text, "html.parser").get_text(strip=True)
    if not plain or len(plain.split()) < 5:
        return True
    return False

def analyze_post(text):
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """You are a geopolitical and financial analyst. Return only this JSON:
{
  "headline": "...",
  "summary": "...",
  "tags": ["..."],
  "sentiment": "...",
  "impact": X
}""" },
                {"role": "user", "content": f"Analyze the following post:\n\n{text}"}
            ],
            temperature=0.3,
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"❌ OpenAI error: {e}")
        return {"summary": f"[ERROR] {e}"}

def run_main():
    json_path = Path("public/summarized_feed.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)

    blocked_links = {
        "https://trumpstruth.org/statuses/31027",
    }

    summarized_entries = []

    def process_entry(text, link, published, source):
        if link in blocked_links:
            print(f"💣 BLOCKED: {link}")
            return

        print(f"\n=== PROCESSING: {link} ({source}) ===")
        raw_input = text.strip()

        # 🔒 Hard skip: known junk from Truth Social like "[No Title] - Post from ..."
        if source != "White House" and re.match(r"\[No Title\] - Post from \w+ \d{1,2}, \d{4}", raw_input):
            print("🚫 Skipping known generic '[No Title] - Post from ...' post.")
            return

        # Try fallback HTML content if initial content looks weak
        if is_useless_content(raw_input):
            print("🔍 Weak content from feed, fetching page...")
            html_fallback = fetch_page_text(link)
            if is_useless_content(html_fallback):
                if source != "White House":
                    print("🚫 Skipping post: No usable content found (non-WH source).")
                    return
                else:
                    print("⚠️ Weak White House post, but allowing through.")
            else:
                raw_input = html_fallback

        if source == "White House":
            print("🏛️ Analyzing WH post (always included).")
        else:
            print(f"✏️ Sending to GPT: {raw_input[:300]}")

        result = analyze_post(raw_input)
        summary = result.get("summary", "").strip()

        if summary.lower().startswith("[error"):
            print("❌ Skipping post due to GPT error.")
            return

        clean_title = result.get("headline", "")[:60]
        print(f"✅ Final Title: {clean_title}")

        summarized_entries.append({
            "title": clean_title,
            "link": link,
            "published": published,
            "summary": summary,
            "tags": result.get("tags", []),
            "sentiment": result.get("sentiment", "Unknown"),
            "impact": result.get("impact", 0),
            "source": source,
            "timestamp": datetime.now().isoformat()
        })

    for url, source in rss_feeds:
        print(f"\n🌐 Processing feed: {source}")
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"❌ Failed to parse feed: {e}")
            continue

        for entry in feed.entries[:5]:
            title = getattr(entry, "title", "").strip()
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            link = entry.link
            published = getattr(entry, "published", None)

            content = summary if source == "White House" else title
            process_entry(content, link, published, source)

    for username, source in twitter_accounts:
        tweets = fetch_tweets(username)
        for tweet in tweets:
            process_entry(tweet["text"], tweet["link"], tweet["created_at"], source)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summarized_entries, f, indent=4, ensure_ascii=False)

    print(f"\n✅ Saved {len(summarized_entries)} posts to {json_path}")

if __name__ == "__main__":
    run_main()
