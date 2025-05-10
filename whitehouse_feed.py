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

def is_useless_html(text):
    """Check if content is just an image, placeholder, or non-informative."""
    if not text or text.strip() == "":
        return True
    text = text.lower().strip()

    # Strip HTML, test for minimal content
    plain = BeautifulSoup(text, "html.parser").get_text(strip=True)
    if not plain or len(plain.split()) < 5:
        return True

    # Typical fallback phrases
    if "no specific information provided" in text:
        return True
    if "does not provide a specific title or content" in text:
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

def is_raw_link(text):
    return re.match(r"^https?://\S+$", text.strip())

def is_short(text):
    return len(text.strip().split()) <= 3

def should_skip(summary_text, original_text=""):
    skip_phrases = [
        "no specific information provided",
        "insufficient information provided for analysis",
        "the post does not provide any specific information",
        "the post does not provide any specific information or context to analyze",
        "this post lacks context",
        "this update offers no insight",
        "unknown", "no content", ""
    ]
    summary_text = summary_text.lower().strip()
    original_text = original_text.lower().strip()
    return (
        summary_text.startswith("[error")
        or summary_text in skip_phrases
        or is_raw_link(summary_text)
        or is_raw_link(original_text)
        or "does not provide a specific title or content" in summary_text
    )

def run_main():
    json_path = Path("public/summarized_feed.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)

    blocked_links = {
        "https://trumpstruth.org/statuses/31027",
    }

    summarized_entries = []

    def process_entry(text, link, published, source):
        if link in blocked_links:
            print(f"💣 BLOCKED: Skipping known bad link: {link}")
            return

        raw_input = text.strip()

        if is_raw_link(raw_input) or is_short(raw_input) or is_useless_html(raw_input):
            print(f"🔍 Weak input: {raw_input[:60]}...")
            html_text = fetch_page_text(link)
            if is_useless_html(html_text):
                print("🚫 No usable fallback content. Skipping.")
                return
            raw_input = html_text

        result = analyze_post(raw_input)
        summary = result.get("summary", "").strip()

        if should_skip(summary, raw_input):
            print(f"❌ Skipping post after GPT analysis: {raw_input[:60]}...")
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
            body = getattr(entry, "summary", "") or getattr(entry, "description", "")
            link = entry.link
            published = getattr(entry, "published", None)

            process_entry(body if source == "White House" else title, link, published, source)

    for username, source in twitter_accounts:
        tweets = fetch_tweets(username)
        for tweet in tweets:
            process_entry(tweet["text"], tweet["link"], tweet["created_at"], source)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summarized_entries, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    run_main()
