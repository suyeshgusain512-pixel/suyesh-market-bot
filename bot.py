import os
import requests
import yfinance as yf
import feedparser
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
    lines = []
    for name, symbol in TICKERS.items():
        try:
            hist = yf.Ticker(symbol).history(period="5d")
            if len(hist) < 2:
                continue
            last_close = hist["Close"].iloc[-1]
            prev_close = hist["Close"].iloc[-2]
            change = last_close - prev_close
            pct = (change / prev_close) * 100
            direction = "up" if change >= 0 else "down"
            lines.append(
                f"{name}: {last_close:.2f} ({direction} {abs(change):.2f}, {pct:+.2f}%)"
            )
        except Exception as e:
            print(f"Data fetch error for {name}: {e}")
    return "\n".join(lines)


def get_headlines(limit=6):
    try:
        feed = feedparser.parse(RSS_FEED)
        headlines = [entry.title for entry in feed.entries[:limit]]
        return "\n".join(f"- {h}" for h in headlines)
    except Exception as e:
        print(f"RSS fetch error: {e}")
        return ""


def generate_post(market_data, headlines):
    prompt = f"""You are a professional financial content writer creating a LinkedIn post
for a finance professional's personal profile.

Today's real market data:
{market_data}

Today's real market headlines:
{headlines}

Write a LinkedIn post (150-220 words) that:
- Opens with a strong, specific hook about today's market movement (use the real numbers above)
- Gives a short, grounded analysis of what likely drove the movement, referencing the real headlines
- Avoids generic filler phrases like "markets were volatile today" without substance
- Ends with one forward-looking sentence (what to watch tomorrow/this week)
- Uses plain paragraph text, no markdown formatting, no headers
- Ends with 5-8 relevant finance/markets hashtags on a new line
- Does not fabricate any numbers or facts not given above

Return ONLY the post text, nothing else."""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
        temperature=0.8,
    )
    return response.choices[0].message.content.strip()


def post_to_linkedin(text):
    result = requests.post(MAKE_URL, json={"text": text}, timeout=30)
    print("Posted to Make.com:", result.status_code)


if __name__ == "__main__":
    print("Fetching market data...")
    market_data = get_market_data()
    print(market_data)

    print("Fetching headlines...")
    headlines = get_headlines()
    print(headlines)

    print("Generating post...")
    post_text = generate_post(market_data, headlines)
    print(post_text)

    print("Posting to LinkedIn via Make.com...")
    post_to_linkedin(post_text)

    print("Done!")
