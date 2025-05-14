from pathlib import Path
import os
import json
import re
from dotenv import load_dotenv
import openai
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

# Load environment variables
load_dotenv()
openai.api_key = os.environ["OPENAI_API_KEY"]
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")

rss_feeds = [
    ("https://trumpstruth.org/feed", "Truth Social"),
    ("https://www.whitehouse.gov/news/feed", "White House"),
    ("https://www.federalreserve.gov/feeds/press_all.xml", "Federal Reserve"),
    ("https://www.state.gov/feed/press-releases/", "Department of State"),
    ("https://www.cbp.gov/rss/national-media-release.xml", "Customs and Border Protection"),
    ("https://home.treasury.gov/news/press-releases", "Treasury (HTML)"),
    ("https://www.sec.gov/news/pressreleases", "SEC (HTML)"),
    ("https://www.dhs.gov/news-releases", "DHS (HTML)"),
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
    if not text or text.strip() == "":
        return True
    plain = BeautifulSoup(text, "html.parser").get_text(strip=True)
    return not plain or len(plain.split()) < 5

def analyze_post(text, source=""):
    try:
        if source == "Truth Social":
            system_prompt = """You are summarizing communications from President Trump. Follow these rules:
- Always refer to him as 'President Trump', not 'the author' or 'this post'.
- Be direct, use active phrasing, and summarize as if for political and market analysts.
- Avoid vague or generic phrases. Assume readers are professionals.
Return only this JSON:
{
  "headline": "(max 60 characters)",
  "summary": "...",
  "tags": ["..."],
  "sentiment": "...",
  "impact": X
}"""
        else:
            system_prompt = """You are a geopolitical and financial analyst. When summarizing or titling, follow these rules strictly:
- Never refer to 'the author' or 'this post' — use names if known (e.g. 'President Trump' for Truth Social posts).
- Do not include phrases like 'Analysis of...' in titles — just summarize directly.
- Avoid vague phrases like 'generating interest' or 'creating awareness'.
- Use active, specific language.
Return only this JSON:
{
  "headline": "(max 60 characters)",
  "summary": "...",
  "tags": ["..."],
  "sentiment": "...",
  "impact": X
}"""

        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
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
    json_path = Path("public/summarized_feed.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)

    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                existing_data = json.load(f)
                existing_posts = {p["link"]: p for p in existing_data.get("posts", [])}
            except Exception:
                existing_posts = {}
    else:
        existing_posts = {}

    blocked_links = {"https://trumpstruth.org/statuses/31027"}
    summarized_entries = []

    def process_entry(text, link, published, source):
        if link in blocked_links:
            print(f"💣 BLOCKED: {link}")
            return
        if link in existing_posts:
            cached = existing_posts[link]

            # Check for missing timestamp or display_time
            if not cached.get("timestamp") or not cached.get("display_time"):
                print(f"⚠️ Cached post for {link} missing timestamp → regenerate")
            else:
                summarized_entries.append({
                    "title": cached.get("title", ""),
                    "link": cached.get("link", ""),
                    "published": cached.get("published"),
                    "summary": cached.get("summary", ""),
                    "tags": cached.get("tags", []),
                    "sentiment": cached.get("sentiment", "Unknown"),
                    "impact": cached.get("impact", 0),
                    "source": cached.get("source", ""),
                    "timestamp": cached.get("timestamp"),
                    "display_time": cached.get("display_time"),
                })
                print(f"♻️ Reused cached summary for {link}")
                return


        print(f"\n=== PROCESSING: {link} ({source}) ===")
        raw_input = text.strip()

        if source != "White House" and re.match(r"\[No Title\] - Post from \w+ \d{1,2}, \d{4}", raw_input):
            print("🚫 Skipping known generic '[No Title] - Post from ...' post.")
            return

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

        print(f"✏️ Sending to GPT: {raw_input[:300]}")
        result = analyze_post(raw_input, source)
        summary = result.get("summary", "").strip()

        if summary.lower().startswith("[error"):
            print("❌ Skipping post due to GPT error.")
            return

        clean_title = result.get("headline", "")
        now_iso = datetime.now(timezone.utc).isoformat()

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
            "timestamp": now_iso,
            "display_time": now_iso
        })

    for url, source in rss_feeds:
        print(f"\n🌐 Processing feed: {source}")
        try:
            if "(HTML)" in source:
                res = requests.get(url, timeout=6)
                soup = BeautifulSoup(res.text, "html.parser")
                links = soup.find_all("a", href=True)
                seen = set()
                for a in links:
                    href = a["href"]
                    if not href.startswith("http"):
                        href = requests.compat.urljoin(url, href)
                    text = a.get_text(strip=True)
                    if href not in seen and len(text) > 10:
                        process_entry(text, href, None, source)
                        seen.add(href)
                        if len(seen) >= 5:
                            break
            else:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    title = getattr(entry, "title", "").strip()
                    summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
                    link = entry.link
                    published = getattr(entry, "published", None)
                    content = summary if source == "White House" else title
                    process_entry(content, link, published, source)
        except Exception as e:
            print(f"❌ Failed to parse feed for {source}: {e}")

    for username, source in twitter_accounts:
        tweets = fetch_tweets(username)
        for tweet in tweets:
            process_entry(tweet["text"], tweet["link"], tweet["created_at"], source)

    all_posts = summarized_entries + [
        p for l, p in existing_posts.items()
        if l not in {e["link"] for e in summarized_entries}
    ]

    def sort_key(post):
        ts = datetime.fromisoformat(post["timestamp"])
        if post["source"] == "Truth Social" and (datetime.now(timezone.utc) - ts) < timedelta(hours=1):
            return datetime(9999, 1, 1, tzinfo=timezone.utc)
        return ts

    all_posts.sort(key=sort_key, reverse=True)

    source_buckets = {}
    for post in all_posts:
        src = post["source"]
        if src not in source_buckets:
            source_buckets[src] = []
        if len(source_buckets[src]) < 12:
            source_buckets[src].append(post)

    trimmed_posts = []
    for bucket in source_buckets.values():
        trimmed_posts.extend(bucket)

    trimmed_posts.sort(key=sort_key, reverse=True)

    priority_sources = {"Truth Social", "White House"}
    priority_posts = [p for p in trimmed_posts if p["source"] in priority_sources][:8]
    fallback_posts = [p for p in trimmed_posts if p["source"] not in priority_sources]
    priority_posts += fallback_posts[: (10 - len(priority_posts))]

    recap = summarize_feed_for_recap(priority_posts)

    output = {
        "recap": recap,
        "recap_time": datetime.now(timezone.utc).strftime("%I:%M %p UTC").lstrip("0"),
        "posts": trimmed_posts
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    print(f"\n✅ Saved {len(trimmed_posts)} posts and recap to {json_path}")

if __name__ == "__main__":
    run_main()
