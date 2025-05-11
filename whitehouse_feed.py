from pathlib import Path
import os
import json
import re
from dotenv import load_dotenv
import openai
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# Load environment variables
load_dotenv()
openai.api_key = os.environ["OPENAI_API_KEY"]
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")

rss_feeds = [
    ("https://trumpstruth.org/feed", "Truth Social"),
    ("https://www.whitehouse.gov/news/feed", "White House"),
    ("https://www.federalreserve.gov/feeds/press_all.xml", "Federal Reserve"),
    ("https://www.state.gov/feed/press-releases/", "Department of State"),
    ("https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=OUSDPA", "Department of Defense"),
    ("https://www.cbp.gov/rss/national-media-release.xml", "Customs and Border Protection"),
]

html_sources = [
    ("https://home.treasury.gov/news/press-releases", "Treasury"),
    ("https://www.sec.gov/news/pressreleases", "SEC"),
    ("https://www.dhs.gov/news-releases", "DHS"),
]

twitter_accounts = [
    ("JDVance", "X - JD Vance"),
    ("POTUS", "X - POTUS"),
    ("elonmusk", "X - Elon Musk"),
    ("PressSec", "X - Press Secretary"),
    ("SecYellen", "X - Janet Yellen"),
]

gpt_cache_path = Path("public/gpt_cache.json")
json_path = Path("public/summarized_feed.json")

gpt_cache = set()
if gpt_cache_path.exists():
    with open(gpt_cache_path, "r", encoding="utf-8") as f:
        try:
            gpt_cache.update(json.load(f))
        except:
            pass

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
    if not text or text.strip() == "":
        return True
    plain = BeautifulSoup(text, "html.parser").get_text(strip=True)
    return not plain or len(plain.split()) < 5

def analyze_post(text):
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """You are a geopolitical and financial analyst. Return only this JSON:
{
  \"headline\": \"(max 60 characters)\",
  \"summary\": \"...\",
  \"tags\": [\"...\"],
  \"sentiment\": \"...\",
  \"impact\": X
}""" },
                {"role": "user", "content": f"Analyze the following post:\n\n{text}"}
            ],
            temperature=0.3,
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"❌ OpenAI error: {e}")
        return {"summary": f"[ERROR] {e}"}

def summarize_feed_for_recap(entries):
    try:
        text = "\n".join([f"- {e['title']}: {e['summary']}" for e in entries])
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a professional news summarizer. Recap the day's news in 2–4 insightful sentences."},
                {"role": "user", "content": f"Summarize the following:\n{text}"}
            ],
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Recap generation failed: {e}")
        return "Recap temporarily unavailable due to processing error."

def run_main():
    json_path.parent.mkdir(parents=True, exist_ok=True)

    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                existing_data = json.load(f)
                existing_posts = {p["link"]: p for p in existing_data.get("posts", [])}
            except:
                existing_posts = {}
    else:
        existing_posts = {}

    blocked_links = {"https://trumpstruth.org/statuses/31027"}
    summarized_entries = []

    def process_entry(text, link, published, source):
        if link in blocked_links or link in gpt_cache:
            return

        print(f"\n=== PROCESSING: {link} ({source}) ===")
        raw_input = text.strip()

        if is_useless_content(raw_input):
            html_fallback = fetch_page_text(link)
            if is_useless_content(html_fallback):
                return
            raw_input = html_fallback

        print(f"✏️ Sending to GPT: {raw_input[:300]}")
        result = analyze_post(raw_input)
        if result.get("summary", "").lower().startswith("[error"):
            return

        clean_title = result.get("headline", "")
        now_iso = datetime.now(timezone.utc).isoformat()

        print(f"✅ Final Title: {clean_title}")
        gpt_cache.add(link)

        summarized_entries.append({
            "title": clean_title,
            "link": link,
            "published": published,
            "summary": result["summary"],
            "tags": result.get("tags", []),
            "sentiment": result.get("sentiment", "Unknown"),
            "impact": result.get("impact", 0),
            "source": source,
            "timestamp": now_iso,
            "display_time": now_iso
        })

    for url, source in rss_feeds:
        print(f"\n🌐 Processing RSS: {source}")
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                link = entry.link
                title = getattr(entry, "title", "").strip()
                published = getattr(entry, "published", None)
                if link not in gpt_cache:
                    process_entry(title, link, published, source)
                else:
                    print(f"♻️ Skipped previously cached: {link}")
        except Exception as e:
            print(f"❌ Failed to parse RSS for {source}: {e}")

    for url, source in html_sources:
        print(f"\n📰 Scraping HTML: {source}")
        try:
            res = requests.get(url, timeout=6)
            soup = BeautifulSoup(res.text, "html.parser")
            links = soup.find_all("a", href=True)
            count = 0
            for a in links:
                href = a["href"]
                if not href.startswith("http"):
                    href = requests.compat.urljoin(url, href)
                if href not in gpt_cache and count < 5:
                    process_entry(a.get_text(strip=True), href, None, source)
                    count += 1
                else:
                    gpt_cache.add(href)
        except Exception as e:
            print(f"❌ Error scraping {source}: {e}")

    for username, source in twitter_accounts:
        tweets = fetch_tweets(username)
        for tweet in tweets:
            process_entry(tweet["text"], tweet["link"], tweet["created_at"], source)

    all_posts = summarized_entries + [
        p for l, p in existing_posts.items()
        if l not in {e["link"] for e in summarized_entries}
    ]

    all_posts.sort(key=lambda x: x["timestamp"], reverse=True)

    buckets = {}
    for post in all_posts:
        buckets.setdefault(post["source"], [])
        if len(buckets[post["source"]]) < 12:
            buckets[post["source"]].append(post)

    final_posts = [p for posts in buckets.values() for p in posts]
    final_posts.sort(key=lambda x: x["timestamp"], reverse=True)

    recap = summarize_feed_for_recap(final_posts[:10])
    output = {
        "recap": recap,
        "recap_time": datetime.now(timezone.utc).strftime("%I:%M %p UTC").lstrip("0"),
        "posts": final_posts
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    with open(gpt_cache_path, "w", encoding="utf-8") as f:
        json.dump(list(gpt_cache), f)

    print(f"\n✅ Saved {len(final_posts)} posts and recap to {json_path}")

if __name__ == "__main__":
    run_main()
