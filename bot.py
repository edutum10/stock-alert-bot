import os
import feedparser
import requests
from datetime import datetime

# ======================
# KONFIGURASI (AMBIL DARI GITHUB SECRETS)
# ======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("BOT_TOKEN atau CHAT_ID tidak terbaca dari Secrets")

# ======================
# SUMBER BERITA
# ======================
RSS_FEEDS = {
    "CNBC": "https://www.cnbcindonesia.com/market/rss",
    "Kontan": "https://investasi.kontan.co.id/rss",
    "Reuters": "https://www.reuters.com/rssFeed/asia-pacificNews"
}

# ======================
# KATA KUNCI
# ======================
KEYWORDS_NEGATIVE = [
    "melemah",
    "turun",
    "tertekan",
    "waspada",
    "ketidakpastian",
    "hawkish",
    "tekanan jual",
    "risk off",
    "aksi jual",
    "foreign sell",
    "outflow",
    "bearish",
    "negatif",
    "penurunan"
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
# FUNGSI KIRIM PESAN
# ======================
def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=10
    )
    response.raise_for_status()

# ======================
# KLASIFIKASI BERITA
# ======================
def classify_news(title):
    t = title.lower()
    for word in KEYWORDS_NEGATIVE:
        if word in t:
            return "🚨 ALERT NEGATIF"
    for word in KEYWORDS_POSITIVE:
        if word in t:
            return "🟢 ALERT POSITIF"
    return None

def is_market_news(title):
    keywords = ["ihsg", "saham", "pasar", "bursa", "bank", "rupiah"]
    return any(k in title.lower() for k in keywords)

def detect_sector(title):
    impacted = []
    t = title.lower()
    for sector, stocks in WATCHLIST.items():
        for stock in stocks:
            if stock.lower() in t:
                impacted.append(sector)
    return impacted

# ======================
# CEK BERITA
# ======================
def check_news():
    for source, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:3]:
            status = classify_news(entry.title)
            if not status and not is_market_news(entry.title):
                continue

            label = status if status else "🟡 INFO PASAR"

            sectors = detect_sector(entry.title)
            sector_text = ", ".join(sectors) if sectors else "Makro / Umum"

            message = (
                f"{label}\n"
                f"📰 Sumber: {source}\n"
                f"📌 {entry.title}\n\n"
                f"🎯 Sektor: {sector_text}\n"
                f"🔗 {entry.link}\n\n"
                f"⏰ {datetime.now().strftime('%d-%m-%Y %H:%M')}"
            )

            send_message(message)

# ======================
# MAIN
# ======================
if __name__ == "__main__":
    check_news()
