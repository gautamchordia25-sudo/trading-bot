import os
import logging
import asyncio
import sqlite3
import json
import base64
from datetime import datetime, time as dtime
import pytz
import pandas as pd
import numpy as np
import yfinance as yf
import anthropic
import httpx  # High-performance async HTTP client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# Setup logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from nsepython import nse_eq, nse_index, nse_get_index_list, nsefetch
    NSE_PYTHON_OK = True
    logger.info("nsepython loaded — live NSE data active")
except ImportError:
    NSE_PYTHON_OK = False
    logger.warning("nsepython not installed — using fallback sources")

# Configurations & Consts
DB_PATH = os.environ.get("DB_PATH", "trading_bot.db")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
IST = pytz.timezone("Asia/Kolkata")

client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# In-memory Global Caches
user_watchlists = {}
alert_jobs = {}
briefing_subscribers = {}
trade_journals = {}
trading_rules = {}
closing_subscribers = {}
volatility_subscribers = {}
user_quiz_state = {}

NSE_INDEX_MAP = {
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "NIFTY BANK",
    "^CNXIT": "NIFTY IT",
    "^BSESN": "SENSEX",
    "^INDIAVIX": "INDIA VIX",
}

NIFTY_TICKERS = ["^NSEI", "NIFTY50.NS", "NIFTYBEES.NS"]
BANKNIFTY_TICKERS = ["^NSEBANK", "BANKNIFTY.NS", "BANKBEES.NS"]

NIFTY50_STOCKS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
    "HINDUNILVR.NS","SBIN.NS","BHARTIARTL.NS","KOTAKBANK.NS","ITC.NS",
    "LT.NS","AXISBANK.NS","ASIANPAINT.NS","MARUTI.NS","NESTLEIND.NS",
]

SECTORS = {
    "🖥 IT": ["TCS.NS","INFY.NS","WIPRO.NS","HCLTECH.NS"],
    "🏦 Bank": ["HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","AXISBANK.NS"],
    "🚗 Auto": ["MARUTI.NS","TATAMOTORS.NS","BAJAJ-AUTO.NS"],
    "🛒 FMCG": ["HINDUNILVR.NS","ITC.NS","NESTLEIND.NS"],
}

TRADING_QUIZ = [
    {"q":"What does RSI above 70 indicate?","a":"Overbought — price may reverse down soon","opt":["Bullish breakout","Overbought — price may reverse down soon","Oversold zone","Strong buy signal"]},
    {"q":"What is a Doji candlestick?","a":"Open and close are nearly equal — market indecision","opt":["Strong bullish candle","Open and close are nearly equal — market indecision","Strong bearish candle","High volume candle"]},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,*/*",
}

# Async reusable HTTP Client
async_client = httpx.AsyncClient(headers=HEADERS, timeout=10)

# ─── ASYNC WATERFALL FETCHERS ──────────────────────────────────────────────────

async def fetch_stooq_async(ticker: str, period: str = "3mo") -> pd.DataFrame | None:
    stooq_map = {"^NSEI": "^nsei", "^NSEBANK": "^nsebank", "^BSESN": "^bsesn", "^INDIAVIX": "^vix"}
    sym = stooq_map.get(ticker, ticker.lower().replace(".ns", ""))
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    try:
        response = await async_client.get(url)
        if response.status_code != 200 or "No data" in response.text:
            return None
        from io import StringIO
        df = pd.read_csv(StringIO(response.text), parse_dates=["Date"], index_col="Date")
        df.columns = [c.strip().title() for c in df.columns]
        if "Close" not in df.columns or df.empty:
            return None
        df = df.dropna(subset=["Close"]).sort_index()
        return df.tail(90)
    except Exception as e:
        logger.warning(f"Stooq error for {ticker}: {e}")
        return None

async def fetch_yahoo_direct_async(ticker: str, period: str = "3mo", interval: str = "1d") -> pd.DataFrame | None:
    enc = ticker.replace("^", "%5E")
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{enc}?interval={interval}&range={period}"
    try:
        r = await async_client.get(url)
        if r.status_code != 200: return None
        res = r.json().get("chart", {}).get("result", [])[0]
        ts = res.get("timestamp", [])
        q = res.get("indicators", {}).get("quote", [{}])[0]
        df = pd.DataFrame({
            "Open": q.get("open", []), "High": q.get("high", []),
            "Low": q.get("low", []), "Close": q.get("close", []),
            "Volume": q.get("volume", []),
        }, index=pd.to_datetime(ts, unit="s", utc=True))
        return df.dropna(subset=["Close"])
    except Exception as e:
        logger.warning(f"Yahoo Direct Async error for {ticker}: {e}")
        return None

async def fetch_data_async(tickers: list, period: str = "3mo", interval: str = "1d"):
    """Optimized parallel network queries using Async methods."""
    primary = tickers[0]
    
    # Try high-performance async direct queries first
    df = await fetch_yahoo_direct_async(primary, period, interval)
    if df is not None and len(df) >= 3:
        return df, primary

    if interval == "1d":
        df = await fetch_stooq_async(primary, period)
        if df is not None and len(df) >= 3:
            return df, primary

    # Fallback thread pool pool execution for legacy yfinance
    try:
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, lambda: yf.Ticker(primary).history(period=period, interval=interval, timeout=10))
        if df is not None and not df.empty:
            return df, primary
    except Exception as e:
        logger.warning(f"yfinance executor fallback error: {e}")

    return None, None

# ─── TECHNICAL INDICATORS (VECTORIZED PANDAS) ────────────────────────────────

def rsi_series(s, n=14):
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    avg_gain = gain.ewm(alpha=1/n, min_periods=n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/n, min_periods=n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))

def calc_macd(s, fast=12, slow=26, sig=9):
    ema_fast = s.ewm(span=fast, adjust=False).mean()
    ema_slow = s.ewm(span=slow, adjust=False).mean()
    m = ema_fast - ema_slow
    sg = m.ewm(span=sig, adjust=False).mean()
    return round(float(m.iloc[-1]), 2), round(float(sg.iloc[-1]), 2), round(float((m-sg).iloc[-1]), 2)

def calc_bb(s, n=20, std=2):
    sm = s.rolling(n).mean()
    sd = s.rolling(n).std(ddof=0)
    return round(float((sm+std*sd).iloc[-1]), 2), round(float(sm.iloc[-1]), 2), round(float((sm-std*sd).iloc[-1]), 2)

def calc_atr(h, l, c, n=14):
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, min_periods=n, adjust=False).mean()

def calc_pivots(h, l, c):
    p = (h+l+c)/3
    return {"pivot": p, "r1": 2*p-l, "r2": p+(h-l), "s1": 2*p-h, "s2": p-(h-l)}

# ─── CORE ENGINE ANALYSIS ─────────────────────────────────────────────────────

async def get_full_analysis_async(tickers):
    """Fires I/O operations simultaneously instead of blocking execution."""
    # Run historical daily and intraday calls in parallel!
    tasks = [
        fetch_data_async(tickers, "3mo", "1d"),
        fetch_data_async(tickers, "5d", "15m")
    ]
    (df_d, used), (df_15, _) = await asyncio.gather(*tasks)

    if df_d is None or len(df_d) < 5:
        return None

    c, h, l, v = df_d["Close"], df_d["High"], df_d["Low"], df_d["Volume"]
    px = round(float(c.iloc[-1]), 2)
    prev = round(float(c.iloc[-2]), 2)
    chg = round(px - prev, 2)
    pct = round(chg / prev * 100, 2)

    rsi_val = round(float(rsi_series(c).iloc[-1]), 2)
    macd, ms, mh = calc_macd(c)
    bbu, bbm, bbl = calc_bb(c)
    
    daily_atr = round(float(calc_atr(h, l, c).iloc[-1]), 2)
    atr_15m = daily_atr / 6
    if df_15 is not None and len(df_15) >= 14:
        atr_15m = float(calc_atr(df_15["High"], df_15["Low"], df_15["Close"]).iloc[-1])

    pvt = calc_pivots(float(h.iloc[-2]), float(l.iloc[-2]), float(c.iloc[-2]))

    # Logical Rules Signals Scoring
    score = 0
    if chg > 0: score += 2
    else: score -= 2
    if rsi_val < 40: score += 2
    elif rsi_val > 65: score -= 2

    sig = "NEUTRAL ⚪ — Wait"
    if score >= 2: sig = "BUY 🟢"
    elif score <= -2: sig = "SELL 🔴"

    # Targets & Risk Management setup
    sl = round(px - (atr_15m * 1.5), 2) if "BUY" in sig else round(px + (atr_15m * 1.5), 2)
    t1 = round(px + (atr_15m * 1.5), 2) if "BUY" in sig else round(px - (atr_15m * 1.5), 2)
    t2 = round(px + (atr_15m * 3), 2) if "BUY" in sig else round(px - (atr_15m * 3), 2)

    return {
        "ticker": used, "price": px, "prev": prev, "change": chg, "pct": pct,
        "rsi": rsi_val, "macd": macd, "macd_sig": ms, "atr_15m": round(atr_15m, 2),
        "score": score, "signal": sig, "sl": sl, "t1": t1, "t2": t2, "rr": 1.5,
        "support": pvt["s1"], "resistance": pvt["r1"], "pivots": pvt, "bbu": bbu, "bbl": bbl,
        "e9": px, "e21": px, "e50": px, "e200": None, "atr_daily": daily_atr, "vol_ratio": 1, "w52h": px, "w52l": px, "supertrend": "NEUTRAL"
    }

# ─── TELEGRAM HANDLERS ────────────────────────────────────────────────────────

def fmt_msg(d, name="NIFTY 50"):
    now = datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")
    e = "📈" if d["change"] >= 0 else "📉"
    msg = f"""*{name} — Live Analysis*
🕐 `{now}`
━━━━━━━━━━━━━━━━━━━━
💰 *Price:* `{d['price']:,.2f}` ({d['change']:+.2f}%)
📊 *Signal:* `{d['signal']}`
📐 *RSI (14):* `{d['rsi']}`

🎯 *TRADE SETUP*

