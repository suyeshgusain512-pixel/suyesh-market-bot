import os
import requests
import yfinance as yf
import feedparser
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from groq import Groq

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
MAKE_URL     = os.environ["MAKE_WEBHOOK_URL"]

client = Groq(api_key=GROQ_API_KEY)

TICKERS = {
    "Nifty 50": "^NSEI",
    "Sensex":   "^BSESN",
    "USD/INR":  "INR=X",
}

RSS_FEED = "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"


def get_market_data():
    data = []
    for name, symbol in TICKERS.items():
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

    fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
    bars = ax.bar(names, pcts, color=colors, width=0.5)

    for bar, pct in zip(bars, pcts):
        height = bar.get_height()
        va = "bottom" if height >= 0 else "top"
        offset = 0.05 if height >= 0 else -0.05
        ax.text(bar.get_x() + bar.get_width() / 2, height + offset,
                 f"{pct:+.2f}%", ha="center", va=va, fontsize=12, fontweight="bold")

    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.set_ylabel("% Change", fontsize=11)
    ax.set_title("Market Snapshot", fontsize=16, fontweight="bold", pad=15)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def upload_image(path):
    with open(path, "rb") as f:
        upload = requests.post(
            "https://tmpfiles.org/api/v1/upload",
            files={"file": f},
            timeout=60
        )
    print("tmpfiles status:", upload.status_code)
    print("tmpfiles response:", upload.text[:500])
    upload_data = upload.json()

    if upload_data.get("status") == "success":
        raw_url = upload_data["data"]["url"]
        return raw_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
    else:
        print("Image upload failed:", upload_data)
        return None


def generate_post(market_text, headlines):
    prompt = f"""You are a professional financial content writer creating a LinkedIn post
for a finance professional's personal profile.

Today's real market data:
{market_text}

Today's real market headlines:
{headlines}

Write a LinkedIn post that follows this EXACT structure, with blank lines between each section:

1. A short, punchy headline line (under 10 words, no hashtags, can use one relevant emoji e.g. \U0001F4CA or \U0001F4C9 or \U0001F4C8)
2. A blank line
3. A 2-3 sentence paragraph stating today's real numbers (from the data above) in plain, confident language
4. A blank line
5. A 3-4 sentence paragraph analyzing WHY the market moved this way, grounded in the real headlines above
6. A blank line
7. One forward-looking sentence: what to watch tomorrow/this week
8. A blank line
9. Exactly 20 relevant, specific hashtags space-separated on one line (mix broad market tags like #StockMarket #Nifty50 #Sensex #Investing with niche ones like #FinancialAnalysis #MacroEconomics #IndianEconomy #WealthManagement #TradingInsights etc.)

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
    print("Fetching market data...")
    market_data = get_market_data()
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
    post_text = generate_post(market_text, headlines)
    print(post_text)

    print("Posting to LinkedIn via Make.com...")
    post_to_linkedin(post_text, image_url)

    print("Done!")
