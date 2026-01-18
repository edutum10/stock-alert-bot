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
# EMITEN DETECTION (REGEX, ANTI FALSE POSITIVE)
# =========================================================
def extract_emitens(text):
    found = []
    t = text.lower()

    for ticker, info in EMITEN_MASTER.items():
        if info["sector"] not in ACTIVE_SECTORS:
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
def analyze_sentiment(text):
    score = 0
    t = text.lower()

    for w in NEGATIVE_WORDS:
        if w in t:
            score -= 1
    for w in POSITIVE_WORDS:
        if w in t:
            score += 1

    return score

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
        data = yf.download(f"{symbol}.JK", period="3mo", interval="1d", progress=False)
        if data.empty:
            return None

        delta = data["Close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return round(rsi.iloc[-1], 2)
    except Exception:
        return None


# =========================================================
# CONFIDENCE & ACTION
# =========================================================
def confidence_score(sentiment, rsi):
    score = 0

    if sentiment >= 2:
        score += 40
    elif sentiment == 1:
        score += 25
    elif sentiment == 0:
        score += 10

    if rsi is not None:
        if rsi <= 30 or rsi >= 70:
            score += 40
        elif rsi <= 40 or rsi >= 60:
            score += 25

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
# MAIN
# =========================================================
RSS_FEEDS = {
    "CNBC": "https://www.cnbcindonesia.com/market/rss",
    "Kontan": "https://investasi.kontan.co.id/rss",
    "Reuters": "https://www.reuters.com/rssFeed/asia-pacificNews",
    "Gapki": "https://gapki.id/berita-terkini/rss",
    "Bisnis": "https://market.bisnis.com/rss",
    "BI": "https://www.bi.go.id/id/rss/default.aspx"

}

def run_bot():
    for source, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)

        for entry in feed.entries[:5]:
            summary = entry.get("summary", "")
            text = f"{entry.title} {summary}"

            emitens = extract_emitens(text)
            if not emitens:
                continue

            sentiment = analyze_sentiment(text)
            sentiment += context_adjustment(entry.title)

            for emiten in emitens:
                rsi = get_rsi(emiten)
                conf = confidence_score(sentiment, rsi)
                action = final_action(sentiment, rsi, conf)

                message = (
                    "📰 ANALISIS BERITA + TEKNIKAL\n"
                    f"Sumber: {source}\n"
                    f"Judul: {entry.title}\n\n"
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


if __name__ == "__main__":
    run_bot()
