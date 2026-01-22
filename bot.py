# =========================================================
# IMPORT
# =========================================================
import os
import re
import csv
import requests
import feedparser
from datetime import datetime

import yfinance as yf
import pandas as pd

feedparser.USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# =========================================================
# ENV CONFIG (DARI GITHUB SECRETS)
# =========================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("BOT_TOKEN atau CHAT_ID tidak terbaca dari Secrets")


# =========================================================
# MODE BOT
# =========================================================
MODE = "TRADER"   # TRADER atau INVESTOR

MODE_RULES = {
    "TRADER": {
        "buy_rsi": 35,
        "sell_rsi": 65,
        "min_confidence": 60
    },
    "INVESTOR": {
        "buy_rsi": 30,
        "sell_rsi": 70,
        "min_confidence": 75
    }
}


# =========================================================
# LOAD MASTER EMITEN (CSV – BISA 500)
# =========================================================
def load_emiten_master(path="emiten_master.csv"):
    data = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data[row["ticker"]] = {
                "sector": row["sector"],
                "aliases": row["aliases"].split("|")
            }
    return data


EMITEN_MASTER = load_emiten_master()

# sektor yang dipantau
ACTIVE_SECTORS = {"BANK", "BATUBARA", "PANGAN", "ALATKEBAKARAN", "ALATKESEHATAN", "ASURANSI", "BAN", "BANGUNAN", "BEER", "BIMBEL", "BUDIDAYA", "ELEKTRONIK", "EMAS", "FARMASI", "FILM", "FURNITUR", "GAS", "HOTEL", "HUTAN", "INTERNET", "INVESTASI", "JALANTOL", "KABEL", "KANTORAN", "KAYU", "KERTAS", "KESEHATAN", "KIMIA", "KOMPUTER", "KONSTRUKSI", "LINGKUNGAN", "LISTRIK", "LOGAM", "LOGISTIK", "MAKANAN", "MATERIAL", "MESIN", "MESINKONSTRUKSI", "MINUMAN", "MULTISEKTOR", "OBAT", "OLAHRGA", "OTOMOTIF", "PAKAIAN", "PELABUHAN", "PEMBIAYAAN", "PENERBANGAN", "PENYIARAN", "PERAWATAN", "PERCETAKAN", "PERIKLANAN", "PLASTIK", "REALESTATE", "REKREASI", "ROKOK", "RUMAHMAKAN", "RUMAHTANGGA", "SEPATU", "SOFTWARE", "STORE", "SUPERMARKET", "SUSU", "TAMBANG", "TEKNOLOGI", "TEKSTIL", "TELEKOMUNIKASI", "TEMBAGA", "TRANSPORTASI", "TRAVEL"}


# ======================
# KATA KUNCI
# ======================
KEYWORDS_NEGATIVE = [
    "anjlok", "melemah", "turun", "tertekan", "outflow",
    "rugi", "beban", "ketidakpastian", "tekanan jual",
    "penurunan", "ditunda"
]

KEYWORDS_POSITIVE = [
    "laba naik", "dividen", "stimulus", "optimis", "rebound",
    "ekspansi", "harga naik", "bullish", "rating naik",
    "meningkat"
]


# =========================================================
# DEDUPLICATION (ANTI BERITA SAMA)
# =========================================================
SENT_LINKS_FILE = "sent_links.txt"

def load_sent_links():
    if not os.path.exists(SENT_LINKS_FILE):
        return set()
    with open(SENT_LINKS_FILE, "r") as f:
        return set(line.strip() for line in f)

def save_sent_link(link):
    with open(SENT_LINKS_FILE, "a") as f:
        f.write(link + "\n")


# =========================================================
# EMITEN DETECTION (REGEX, ANTI FALSE POSITIVE)
# =========================================================
def extract_emitens(text):
    found = []
    t = text.lower()

    for ticker, info in EMITEN_MASTER.items():
        if info["sector"].upper() not in ACTIVE_SECTORS:
            continue

        for alias in info["aliases"]:
            pattern = r"\b" + re.escape(alias.lower()) + r"\b"
            if re.search(pattern, t):
                found.append(ticker)
                break

    return found


# =========================================================
# SENTIMENT & CONTEXT
# =========================================================
NEWS_TYPE_KEYWORDS = {
    "REGULATORY": [
        "izin dicabut", "pencabutan izin", "sanksi",
        "dibekukan", "dihentikan", "pembekuan"
    ],
    "FUNDAMENTAL": [
        "laba", "rugi", "kinerja", "pendapatan",
        "utang", "rasio", "keuangan"
    ],
    "PRICE": [
        "ara", "arb", "limit atas", "limit bawah",
        "melonjak", "anjlok tajam"
    ],
    "MARKET": [
        "ihsg", "pasar", "bursa", "indeks",
        "asing", "global"
    ]
}

def classify_news_type(text):
    t = text.lower()
    found = []

    for ntype, keywords in NEWS_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in t:
                found.append(ntype)
                break

    if not found:
        return "UNKNOWN"

    if len(found) > 1:
        return "MIXED"

    return found[0]

SENTIMENT_WEIGHTS = {
    "NEGATIVE_STRONG": {
        "words": ["izin dicabut", "pencabutan izin", "pailit", "bangkrut"],
        "score": -2
    },
    "NEGATIVE_WEAK": {
        "words": ["melemah", "tertekan", "koreksi"],
        "score": -1
    },
    "POSITIVE_STRONG": {
        "words": ["ara", "limit atas", "buyback besar"],
        "score": +2
    },
    "POSITIVE_WEAK": {
        "words": ["rebound", "menguat", "naik"],
        "score": +1
    }
}

def analyze_sentiment_v2(text, news_type):
    t = text.lower()
    score = 0

    for group in SENTIMENT_WEIGHTS.values():
        for w in group["words"]:
            if w in t:
                score += group["score"]

    # 🔑 KONTEKS: MARKET NEGATIVE TIDAK BOLEH KALAHKAN PRICE ACTION
    if news_type == "MIXED":
        if score < 0:
            score += 1  # netralisasi market noise

    return max(min(score, 2), -2)

def context_adjustment(title):
    t = title.lower()
    if "setelah anjlok" in t or "pasca koreksi" in t:
        return +1
    if "berpotensi tertekan" in t:
        return -1
    return 0


# =========================================================
# RSI
# =========================================================
def get_rsi(symbol):
    try:
        data = yf.download(
            f"{symbol}.JK",
            period="3mo",
            interval="1d",
            progress=False
        )

        if data.empty or "Close" not in data:
            return None

        delta = data["Close"].diff()

        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()

        rs = avg_gain / avg_loss
        rsi_series = 100 - (100 / (1 + rs))

        last_rsi = rsi_series.dropna()

        if last_rsi.empty:
            return None

        return float(round(last_rsi.iloc[-1], 2))

    except Exception as e:
        print(f"[RSI ERROR] {symbol}: {e}")
        return None


# =========================================================
# CONFIDENCE & ACTION
# =========================================================
NEWS_TYPE_CONFIDENCE = {
    "REGULATORY": 30,
    "FUNDAMENTAL": 25,
    "PRICE": 20,
    "MARKET": 10,
    "MIXED": 15,
    "UNKNOWN": 5
}

def confidence_score_v2(sentiment, rsi, news_type):
    score = 0

    # kontribusi jenis berita
    score += NEWS_TYPE_CONFIDENCE.get(news_type, 5)

    # kontribusi sentimen
    if sentiment == 2 or sentiment == -2:
        score += 40
    elif abs(sentiment) == 1:
        score += 25

    # kontribusi RSI
    if isinstance(rsi, (int, float)):
        if rsi <= 30 or rsi >= 70:
            score += 30
        elif rsi <= 40 or rsi >= 60:
            score += 20

    return min(score, 100)

def final_action(sentiment, rsi, confidence):
    rule = MODE_RULES[MODE]

    if rsi is None:
        return "🟡 HOLD / WAIT"

    if sentiment >= 1 and rsi <= rule["buy_rsi"] and confidence >= rule["min_confidence"]:
        return "🟢 BUY / ACCUMULATE"

    if sentiment <= -1 and rsi >= rule["sell_rsi"] and confidence >= rule["min_confidence"]:
        return "🔴 SELL / REDUCE"

    return "🟡 HOLD / WAIT"


# =========================================================
# TELEGRAM
# =========================================================
def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
        },
        timeout=10
    )


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


# =========================================================
# RSS SOURCE (FINAL)
# =========================================================
RSS_FEEDS = {
    "Google News IDX": (
        "https://news.google.com/rss/search?"
        "q=saham+Indonesia+OR+IHSG+OR+IDX+OR+emiten"
        "&hl=id&gl=ID&ceid=ID:id"
    )
}

SKIP_KEYWORDS = ["rangkuman", "ringkasan", "recap"]


# =========================================================
# MAIN
# =========================================================
def run_bot():
    sent_links = load_sent_links()

    for source, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        if not feed.entries:
            continue

        for entry in feed.entries[:5]:
            if entry.link in sent_links:
                continue

            if any(k in entry.title.lower() for k in SKIP_KEYWORDS):
                continue

            text = f"{entry.title} {entry.get('summary', '')}"

            emitens = extract_emitens(text)
            if not emitens:
                emitens = ["MARKET"]
                
            news_type = classify_news_type(text)
            sentiment = analyze_sentiment_v2(text, news_type)

            for emiten in emitens:
                rsi = get_rsi(emiten) if emiten != "MARKET" else None
                conf = confidence_score_v2(sentiment, rsi, news_type)
                action = final_action(sentiment, rsi, conf)

                message = (
                    "📰 ANALISIS BERITA + TEKNIKAL\n"
                    f"Sumber: {source}\n"
                    f"Judul: {entry.title}\n\n"
                    f"🗂 Jenis Berita: {news_type}\n"
                    f"🏷 Emiten: {emiten}\n"
                    f"📊 Sentimen: {sentiment}\n"
                    f"📈 RSI: {rsi if rsi else 'N/A'}\n"
                    f"🧠 Confidence: {conf}%\n"
                    f"🔁 Mode: {MODE}\n\n"
                    f"📌 Aksi:\n➡️ {action}\n\n"
                    f"🔗 {entry.link}\n"
                    f"⏰ {datetime.now().strftime('%d-%m-%Y %H:%M')}"
                )

                send_message(message)

            save_sent_link(entry.link)

if __name__ == "__main__":
    run_bot()
