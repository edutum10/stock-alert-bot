import feedparser
import requests
from datetime import datetime

# ======================
# KONFIGURASI
# ======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

RSS_FEEDS = {
    "CNBC": "https://www.cnbcindonesia.com/market/rss",
    "Kontan": "https://investasi.kontan.co.id/rss",
    "Reuters": "https://www.reuters.com/rssFeed/asia-pacificNews"
}

KEYWORDS_NEGATIVE = [
    "suspend", "suspensi", "bea ekspor", "suku bunga naik",
    "rights issue", "private placement", "rugi",
    "downgrade", "utang", "rupiah melemah", "hawkish"
]

KEYWORDS_POSITIVE = [
    "laba naik", "dividen", "stimulus",
    "harga naik", "bullish", "rating naik"
]

WATCHLIST = {
    "🏦 BANK": ["BBRI", "BBCA", "BMRI", "BBNI"],
    "🌴 SAWIT": ["AALI", "SSMS", "SMAR", "LSIP"],
    "⛏️ BATUBARA": ["ADRO", "PTBA", "ITMG", "INDY"],
    "⚡ ENERGI": ["AKRA", "ELSA", "PGAS"]
}

# ======================
def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    })

# ======================
def classify_news(title):
    title_lower = title.lower()

    for word in KEYWORDS_NEGATIVE:
        if word in title_lower:
            return "🚨 ALERT NEGATIF"

    for word in KEYWORDS_POSITIVE:
        if word in title_lower:
            return "🟢 ALERT POSITIF"

    return None

# ======================
def detect_sector(title):
    impacted = []
    for sector, stocks in WATCHLIST.items():
        for stock in stocks:
            if stock.lower() in title.lower():
                impacted.append(sector)
    return impacted

# ======================
def check_news():
    for source, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:3]:
            status = classify_news(entry.title)
            if status:
                sectors = detect_sector(entry.title)
                sector_text = ", ".join(sectors) if sectors else "Makro / Umum"

                message = f"""
{status}
📰 Sumber: {source}
📌 Judul: {entry.title}

🎯 Sektor: {sector_text}
🔗 {entry.link}

⏰ {datetime.now().strftime('%d-%m-%Y %H:%M')}
"""
                send_message(message)

# ======================
def daily_summary():
    message = f"""
📊 RINGKASAN HARIAN
Tanggal: {datetime.now().strftime('%d-%m-%Y')}

Fokus hari ini:
- Bank & IHSG
- Komoditas (CPO, Batubara)
- Rupiah & kebijakan global

Tetap disiplin:
✅ Cut loss cepat
❌ Hindari FOMO
"""
    send_message(message)

# ======================
if __name__ == "__main__":
    check_news()
