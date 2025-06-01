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
from dateutil import parser

# Load environment variables
load_dotenv()
openai.api_key = os.environ["OPENAI_API_KEY"]
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"
}

rss_feeds = [
    ("https://trumpstruth.org/feed", "Truth Social"),
    ("https://www.whitehouse.gov/news/feed", "White House"),
    ("https://www.federalreserve.gov/feeds/press_all.xml", "Federal Reserve"),
    ("https://www.state.gov/rss-feed/press-releases/feed/", "Department of State"),
    ("https://www.cbp.gov/rss/newsroom", "Customs and Border Protection"),
    ("https://www.commerce.gov/feeds/news", "Commerce Department"),
    ("https://www.sec.gov/news/pressreleases.rss", "SEC"),
    ("https://www.dhs.gov/news-releases", "DHS")
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
        res = requests.get(url, headers=HEADERS, timeout=6)
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
  \"headline\": \"(max 60 characters)\",
  \"summary\": \"...\",
  \"tags\": [\"...\"],
  \"sentiment\": \"...\",
  \"impact\": X
}"""
        else:
            system_prompt = """You are a geopolitical and financial analyst summarizing official government communications, policy statements, and regulatory developments.

Summarize the key points in 3–4 compact, high-signal sentences. The entire summary must stay under 200 characters total. Use direct, factual language. Do not include vague phrasing, commentary, or refer to 'the content' or 'the author'. Use active voice and name government entities when relevant.

Return only this JSON:
{
  \"headline\": \"(max 60 characters)\",
  \"summary\": \"max 200 characters total, split across 3–4 tight sentences)\",
  \"tags\": [\"...\"],
  \"sentiment\": \"...\",
  \"impact\": X
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

def generate_expanded_summary(text):
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a geopolitical and economic policy analyst. Expand the original summary with deeper detail and institutional context. Avoid generalities, speculation, or editorializing. Do not use phrases like 'the content you provided.' The tone should be neutral and informative. Target length: 120–150 words, and it should be more detailed than the initial summary."},
                {"role": "user", "content": f"Expand and clarify this content with more depth and any available factual context:\n\n{text}"}
            ],
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Failed to generate expanded summary: {e}")
        return ""

def run_main():
    json_path = Path("public/summarized_feed.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    existing_data = {}
    existing_posts = {}

    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                existing_posts = {p["link"]: p for p in existing_data.get("posts", [])}
        except Exception as e:
            print(f"⚠️ Failed to load existing JSON: {e}")

    deleted_links_path = Path("public/deleted_links.json")
    deleted_links = []
    if deleted_links_path.exists():
        try:
            with open(deleted_links_path, "r", encoding="utf-8") as f:
                deleted_links = json.load(f)
        except Exception as e:
            print(f"⚠️ Failed to load deleted links: {e}")

    summarized_entries = []

    def process_entry(text, link, published, source):
        existing = existing_posts.get(link)

        if link in deleted_links:
            print(f"🚫 Skipping deleted post: {link}")
            return

        # Skip entirely if raw text is the same → saves GPT cost + preserves timestamp
        if existing and existing.get("raw_content") == text:
            summarized_entries.append(existing)
            print(f"♻️ Reused full post for {link} (no change detected)")
            return
        
        if source != "White House" and re.match(r"\[No Title\] - Post from \w+ \d{1,2}, \d{4}", text.strip()):
            print("🚫 Skipping known generic '[No Title] - Post from ...' post.")
            return

        if is_useless_content(text):
            print("🔍 Weak content from feed, fetching page...")
            html_fallback = fetch_page_text(link)
            if is_useless_content(html_fallback):
                if source != "White House":
                    print("🚫 Skipping post: No usable content found (non-WH source).")
                    return
                else:
                    print("⚠️ Weak White House post, but allowing through.")
            else:
                text = html_fallback

        print(f"✏️ Sending to GPT: {text[:300]}")
        result = analyze_post(text, source)
        if result.get("summary", "").lower().startswith("[error"):
            print("❌ Skipping post due to GPT error.")
            return

        expanded = ""
        if source != "Truth Social" and not source.startswith("X -"):
            expanded = generate_expanded_summary(text)

        if existing and "timestamp" in existing:
            final_timestamp = existing["timestamp"]
            final_display = existing.get("display_time", final_timestamp)
        else:
            if published:
                try:
                    final_timestamp = parser.parse(published).astimezone(timezone.utc).isoformat()
                    final_display = final_timestamp
                except Exception:
                    final_timestamp = final_display = datetime.now(timezone.utc).isoformat()
            else:
                final_timestamp = final_display = datetime.now(timezone.utc).isoformat()

        summarized_entries.append({
            "title": result.get("headline", ""),
            "link": link,
            "published": published,
            "summary": result.get("summary", ""),
            "summary_expanded": expanded,
            "tags": result.get("tags", []),
            "sentiment": result.get("sentiment", "Unknown"),
            "impact": result.get("impact", 0),
            "source": source,
            "timestamp": final_timestamp,
            "display_time": final_display,
            "raw_content": text
        })

    for url, source in rss_feeds:
        print(f"\n🌐 Processing feed: {source}")
        try:
            feed = feedparser.parse(requests.get(url, headers=HEADERS, timeout=15).content)
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

    all_posts = summarized_entries + [p for l, p in existing_posts.items() if l not in {e["link"] for e in summarized_entries}]

    def sort_key(post):
        ts = datetime.fromisoformat(post["timestamp"])
        if post["source"] == "Truth Social" and (datetime.now(timezone.utc) - ts) < timedelta(hours=1):
            return datetime(9999, 1, 1, tzinfo=timezone.utc)
        return ts

    all_posts.sort(key=sort_key, reverse=True)

    IS_AUTO_FETCH = len(summarized_entries) > 0

    if IS_AUTO_FETCH:
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
    else:
        # Use everything from the restored feed
        trimmed_posts = list(all_posts)

    trimmed_posts.sort(key=sort_key, reverse=True)

    priority_sources = {"Truth Social", "White House"}
    priority_posts = [p for p in trimmed_posts if p["source"] in priority_sources][:8]
    fallback_posts = [p for p in trimmed_posts if p["source"] not in priority_sources]
    priority_posts += fallback_posts[: (10 - len(priority_posts))]

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
