import os
import base64
import requests
import yfinance as yf
import feedparser
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime
from zoneinfo import ZoneInfo
from groq import Groq

GROQ_API_KEY  = os.environ["GROQ_API_KEY"]
MAKE_URL      = os.environ["MAKE_WEBHOOK_URL"]
IMGBB_API_KEY = os.environ["IMGBB_API_KEY"]

client = Groq(api_key=GROQ_API_KEY)

CORE_TICKERS = {
    "Bitcoin":   "BTC-USD",
    "Gold":      "GC=F",
    "Crude Oil": "CL=F",
}

WEEKDAY_TICKERS = {
    "Nifty 50": "^NSEI",
    "Sensex":   "^BSESN",
    "USD/INR":  "INR=X",
}

RSS_FEED = "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"


def get_run_context():
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    mode = "morning" if now_ist.hour < 12 else "evening"
    is_weekday = now_ist.weekday() < 5  # Mon=0 ... Sun=6
    return mode, is_weekday


def get_market_data(tickers):
    data = []
    for name, symbol in tickers.items():
        try:
            hist = yf.Ticker(symbol).history(period="5d")
            if len(hist) < 2:
                continue
            last_close = hist["Close"].iloc[-1]
            prev_close = hist["Close"].iloc[-2]
            change = last_close - prev_close
            pct = (change / prev_close) * 100
            data.append({
                "name": name,
                "close": last_close,
                "change": change,
                "pct": pct,
            })
        except Exception as e:
            print(f"Data fetch error for {name}: {e}")
    return data


def format_market_text(data):
    lines = []
    for d in data:
        direction = "up" if d["change"] >= 0 else "down"
        lines.append(
            f"{d['name']}: {d['close']:.2f} ({direction} {abs(d['change']):.2f}, {d['pct']:+.2f}%)"
        )
    return "\n".join(lines)


def get_headlines(limit=6):
    try:
        feed = feedparser.parse(RSS_FEED)
        headlines = [entry.title for entry in feed.entries[:limit]]
        return "\n".join(f"- {h}" for h in headlines)
    except Exception as e:
        print(f"RSS fetch error: {e}")
        return ""


def generate_chart(data, path="chart.png"):
    names = [d["name"] for d in data]
    pcts = [d["pct"] for d in data]
    colors = ["#1a9e5c" if p >= 0 else "#d9364a" for p in pcts]

    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=150)
    bars = ax.bar(names, pcts, color=colors, width=0.5)

    for bar, pct in zip(bars, pcts):
        height = bar.get_height()
        va = "bottom" if height >= 0 else "top"
        offset = 0.05 if height >= 0 else -0.05
        ax.text(bar.get_x() + bar.get_width() / 2, height + offset,
                 f"{pct:+.2f}%", ha="center", va=va, fontsize=11, fontweight="bold")

    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.set_ylabel("% Change", fontsize=11)
    ax.set_title("Market Snapshot", fontsize=16, fontweight="bold", pad=15)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def upload_image(path):
    with open(path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    upload = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": IMGBB_API_KEY, "image": image_b64},
        timeout=60
    )
    print("imgbb status:", upload.status_code)
    print("imgbb response:", upload.text[:500])
    upload_data = upload.json()

    if upload_data.get("success"):
        return upload_data["data"]["url"]
    else:
        print("Image upload failed:", upload_data)
        return None


def generate_post(market_text, headlines, mode, is_weekday):
    if mode == "evening":
        structure = """1. A short, punchy headline line (under 10 words, no hashtags, one relevant emoji e.g. \U0001F4CA or \U0001F4C9 or \U0001F4C8)
2. A blank line
3. A 2-3 sentence paragraph stating today's real closing numbers (from the data above) in plain, confident language
4. A blank line
5. A 3-4 sentence paragraph analyzing WHY the market moved this way, grounded in the real headlines above
6. A blank line
7. One forward-looking sentence: what to watch tomorrow/this week
8. A blank line
9. Exactly 20 relevant, specific hashtags space-separated on one line"""
        framing = "This is an END-OF-DAY recap of today's session."
    else:
        structure = """1. A short, punchy headline line (under 10 words, no hashtags, one relevant emoji e.g. \U0001F305 or \U0001F4C8 or \U0001F4C9)
2. A blank line
3. A 2-3 sentence paragraph stating where things stand based on the last available data above (framed as "heading into today" context, not as today's result since markets haven't opened yet)
4. A blank line
5. A 3-4 sentence paragraph on what to watch TODAY, grounded in the real headlines above - key levels, events, or themes that could move markets. Use measured, analytical language (e.g. "could see pressure if X", "eyes will be on Y") - NEVER state a definitive prediction like "will hit X" or "will rally/crash"
6. A blank line
7. One sentence framing today as an opportunity to stay alert / disciplined
8. A blank line
9. Exactly 20 relevant, specific hashtags space-separated on one line"""
        framing = "This is a MORNING OUTLOOK post, published before markets open. It must read as analysis of what to watch, never as a guaranteed prediction."

    if is_weekday:
        scope = "Indian equity markets (Nifty, Sensex, USD/INR) plus crypto, gold, and crude oil."
    else:
        scope = "It is a weekend - Indian equity markets are closed, so this post covers ONLY crypto, gold, and crude oil, which trade independent of weekday market hours. Do not mention Nifty, Sensex, or Indian equities being open or closed unless briefly noting markets resume Monday."

    prompt = f"""You are a professional financial content writer creating a LinkedIn post
for a finance professional's personal profile.

{framing}
Scope: {scope}

Today's real market data:
{market_text}

Today's real market headlines:
{headlines}

Write a LinkedIn post that follows this EXACT structure, with blank lines between each section:

{structure}

Rules:
- No markdown formatting (no **, no #headers except the hashtags at the end)
- Do not fabricate any numbers or facts not given above
- Keep total length under 250 words excluding hashtags

Return ONLY the post text, nothing else."""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2500,
        temperature=0.8,
    )
    result = response.choices[0].message.content.strip()
    if not result:
        print("WARNING: Groq returned empty content. Finish reason:", response.choices[0].finish_reason)
        raise ValueError("Empty post generated - aborting to avoid posting blank content.")
    return result


def post_to_linkedin(text, image_url):
    payload = {"text": text}
    if image_url:
        payload["image_url"] = image_url
    result = requests.post(MAKE_URL, json=payload, timeout=30)
    print("Posted to Make.com:", result.status_code)


if __name__ == "__main__":
    mode, is_weekday = get_run_context()
    print(f"Mode: {mode} | Weekday: {is_weekday}")

    tickers = {**CORE_TICKERS, **WEEKDAY_TICKERS} if is_weekday else CORE_TICKERS

    print("Fetching market data...")
    market_data = get_market_data(tickers)
    market_text = format_market_text(market_data)
    print(market_text)

    print("Fetching headlines...")
    headlines = get_headlines()
    print(headlines)

    print("Generating chart...")
    chart_path = generate_chart(market_data)

    print("Uploading chart...")
    image_url = upload_image(chart_path)
    print("Image URL:", image_url)

    print("Generating post...")
    post_text = generate_post(market_text, headlines, mode, is_weekday)
    print(post_text)

    print("Posting to LinkedIn via Make.com...")
    post_to_linkedin(post_text, image_url)

    print("Done!")
