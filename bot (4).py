import os, logging, asyncio, requests, json
from datetime import datetime, time as dtime
import pytz
import pandas as pd
import numpy as np
import yfinance as yf
import anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
IST = pytz.timezone("Asia/Kolkata")

user_watchlists = {}
alert_jobs      = {}

# ─── ROBUST DATA FETCHER ──────────────────────────────────────────────────────
# Multiple fallback methods for Nifty data

NIFTY_TICKERS   = ["^NSEI", "NIFTY50.NS", "NIFTYBEES.NS"]
BANKNIFTY_TICKERS = ["^NSEBANK", "BANKNIFTY.NS", "BANKBEES.NS"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com",
}

def fetch_yahoo_direct(ticker, period="3mo", interval="1d"):
    """Direct Yahoo Finance API call with proper headers."""
    interval_map = {"1d": "1d", "15m": "15m", "1wk": "1wk", "5m": "5m"}
    range_map    = {"3mo": "3mo", "1y": "1y", "5d": "5d", "1mo": "1mo"}
    enc_ticker = ticker.replace("^", "%5E")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{enc_ticker}"
           f"?interval={interval}&range={period}&includePrePost=false")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            # try query2
            url2 = url.replace("query1", "query2")
            r = requests.get(url2, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        res      = result[0]
        ts       = res.get("timestamp", [])
        quotes   = res.get("indicators", {}).get("quote", [{}])[0]
        if not ts or not quotes.get("close"):
            return None
        df = pd.DataFrame({
            "Open":   quotes.get("open", []),
            "High":   quotes.get("high", []),
            "Low":    quotes.get("low", []),
            "Close":  quotes.get("close", []),
            "Volume": quotes.get("volume", []),
        }, index=pd.to_datetime(ts, unit="s", utc=True))
        df = df.dropna(subset=["Close"])
        return df if not df.empty else None
    except Exception as e:
        logger.error(f"Direct fetch error {ticker}: {e}")
        return None


def fetch_with_fallback(tickers_list, period="3mo", interval="1d"):
    """Try multiple tickers until one works."""
    # Method 1: yfinance with each ticker
    for ticker in tickers_list:
        try:
            yf.set_tz_cache_location("/tmp/yf_cache")
            t = yf.Ticker(ticker)
            df = t.history(period=period, interval=interval, timeout=20)
            if df is not None and not df.empty and len(df) >= 3:
                logger.info(f"yfinance OK: {ticker}")
                return df, ticker
        except Exception as e:
            logger.warning(f"yfinance failed {ticker}: {e}")

    # Method 2: Direct Yahoo Finance API call
    for ticker in tickers_list:
        df = fetch_yahoo_direct(ticker, period=period, interval=interval)
        if df is not None and not df.empty:
            logger.info(f"Direct API OK: {ticker}")
            return df, ticker

    return None, None


# ─── TECHNICAL ANALYSIS ───────────────────────────────────────────────────────

def rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + g / l.replace(0, 1e-9))

def macd(s, f=12, sl=26, sig=9):
    m = s.ewm(span=f).mean() - s.ewm(span=sl).mean()
    sg = m.ewm(span=sig).mean()
    return m, sg, m - sg

def bollinger(s, n=20, k=2):
    sm = s.rolling(n).mean()
    sd = s.rolling(n).std()
    return sm + k*sd, sm, sm - k*sd

def atr(h, l, c, n=14):
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def supertrend(h, l, c, n=10, m=3):
    a = atr(h, l, c, n)
    mid = (h + l) / 2
    ub, lb = mid + m*a, mid - m*a
    direction = pd.Series(1, index=c.index)
    for i in range(1, len(c)):
        if c.iloc[i] > ub.iloc[i-1]:
            direction.iloc[i] = 1
        elif c.iloc[i] < lb.iloc[i-1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i-1]
    return direction

def pivot_points(h, l, c):
    p = (h + l + c) / 3
    return {
        "pivot": round(p,2), "r1": round(2*p - l, 2), "r2": round(p + (h-l), 2),
        "r3": round(h + 2*(p-l), 2), "s1": round(2*p - h, 2),
        "s2": round(p - (h-l), 2), "s3": round(l - 2*(h-p), 2)
    }


def get_full_analysis(tickers_list):
    # Fetch daily data
    df_d, used_ticker = fetch_with_fallback(tickers_list, "3mo", "1d")
    if df_d is None or len(df_d) < 5:
        return None

    c, h, l, v = df_d["Close"], df_d["High"], df_d["Low"], df_d["Volume"]

    # Fetch weekly for supertrend
    df_w, _ = fetch_with_fallback(tickers_list, "1y", "1wk")

    # Fetch 15m intraday
    df_15, _ = fetch_with_fallback(tickers_list, "5d", "15m")

    # ── Compute indicators ──
    r   = rsi(c)
    m, ms, mh = macd(c)
    bbu, bbm, bbl = bollinger(c)
    at  = atr(h, l, c)
    e9  = c.ewm(span=9).mean()
    e21 = c.ewm(span=21).mean()
    e50 = c.ewm(span=50).mean()
    e200= c.ewm(span=200).mean() if len(c) >= 200 else None

    st_dir = supertrend(df_w["High"], df_w["Low"], df_w["Close"]) if df_w is not None and len(df_w) >= 10 else None

    # Pivot from previous day
    pvt = pivot_points(float(h.iloc[-2]), float(l.iloc[-2]), float(c.iloc[-2])) if len(df_d) >= 2 else None

    # 52-week high/low
    df_52, _ = fetch_with_fallback(tickers_list, "1y", "1d")
    w52h = round(float(df_52["High"].max()), 2) if df_52 is not None else "N/A"
    w52l = round(float(df_52["Low"].min()), 2)  if df_52 is not None else "N/A"

    # Current values
    px   = round(float(c.iloc[-1]), 2)
    prev = round(float(c.iloc[-2]), 2)
    chg  = round(px - prev, 2)
    pct  = round(chg / prev * 100, 2)

    curr_rsi  = round(float(r.iloc[-1]), 2)
    curr_macd = round(float(m.iloc[-1]), 2)
    curr_ms   = round(float(ms.iloc[-1]), 2)
    curr_mh   = round(float(mh.iloc[-1]), 2)
    curr_atr  = round(float(at.iloc[-1]), 2)
    curr_e9   = round(float(e9.iloc[-1]), 2)
    curr_e21  = round(float(e21.iloc[-1]), 2)
    curr_e50  = round(float(e50.iloc[-1]), 2)
    curr_e200 = round(float(e200.iloc[-1]), 2) if e200 is not None and not np.isnan(e200.iloc[-1]) else None
    curr_bbu  = round(float(bbu.iloc[-1]), 2)
    curr_bbm  = round(float(bbm.iloc[-1]), 2)
    curr_bbl  = round(float(bbl.iloc[-1]), 2)
    avg_vol   = int(v.tail(20).mean())
    last_vol  = int(v.iloc[-1])
    vol_ratio = round(last_vol / avg_vol, 2) if avg_vol > 0 else 1

    st_signal = "BULLISH" if (st_dir is not None and st_dir.iloc[-1] == 1) else "BEARISH"

    # Intraday levels
    intra_sup = intra_res = None
    if df_15 is not None and len(df_15) >= 4:
        intra_res = round(float(df_15["High"].tail(16).max()), 2)
        intra_sup = round(float(df_15["Low"].tail(16).min()), 2)

    # ── Signal Scoring ──
    score   = 0
    signals = []

    if curr_rsi < 30:   score += 2; signals.append("RSI oversold — strong buy zone")
    elif curr_rsi < 45: score += 1; signals.append("RSI below 45 — bullish bias")
    elif curr_rsi > 70: score -= 2; signals.append("RSI overbought — sell zone")
    elif curr_rsi > 55: score -= 1; signals.append("RSI above 55 — bearish bias")

    if curr_macd > curr_ms and curr_mh > 0:  score += 2; signals.append("MACD bullish crossover")
    elif curr_macd < curr_ms and curr_mh < 0: score -= 2; signals.append("MACD bearish crossover")

    if curr_e9 > curr_e21:  score += 1; signals.append("EMA9 > EMA21 — short-term bullish")
    else:                    score -= 1; signals.append("EMA9 < EMA21 — short-term bearish")

    if px > curr_e50: score += 1; signals.append("Price above EMA50")
    else:             score -= 1; signals.append("Price below EMA50")

    if curr_e200:
        if px > curr_e200: score += 1; signals.append("Above EMA200 — long-term bullish")
        else:              score -= 1; signals.append("Below EMA200 — long-term bearish")

    if px <= curr_bbl:   score += 2; signals.append("At lower Bollinger Band — buy zone")
    elif px >= curr_bbu: score -= 2; signals.append("At upper Bollinger Band — sell zone")

    if st_signal == "BULLISH": score += 2; signals.append("Weekly Supertrend BULLISH")
    else:                       score -= 2; signals.append("Weekly Supertrend BEARISH")

    if vol_ratio > 1.5 and chg > 0: score += 1; signals.append(f"High volume up day ({vol_ratio}x)")
    elif vol_ratio > 1.5 and chg < 0: score -= 1; signals.append(f"High volume down day ({vol_ratio}x)")

    # ── Final Signal ──
    if score >= 6:    sig = "STRONG BUY 🟢🟢"
    elif score >= 2:  sig = "BUY 🟢"
    elif score <= -6: sig = "STRONG SELL 🔴🔴"
    elif score <= -2: sig = "SELL 🔴"
    else:             sig = "NEUTRAL ⚪ — Wait for confirmation"

    # ── ATR-based targets ──
    if "BUY" in sig:
        entry=px; sl=round(px-1.5*curr_atr,2); t1=round(px+1.5*curr_atr,2); t2=round(px+2.5*curr_atr,2); t3=round(px+4.0*curr_atr,2)
    elif "SELL" in sig:
        entry=px; sl=round(px+1.5*curr_atr,2); t1=round(px-1.5*curr_atr,2); t2=round(px-2.5*curr_atr,2); t3=round(px-4.0*curr_atr,2)
    else:
        entry=sl=t1=t2=t3=None

    return {
        "ticker": used_ticker, "price": px, "prev": prev, "change": chg, "pct": pct,
        "rsi": curr_rsi, "macd": curr_macd, "macd_sig": curr_ms, "macd_hist": curr_mh,
        "atr": curr_atr, "e9": curr_e9, "e21": curr_e21, "e50": curr_e50, "e200": curr_e200,
        "bbu": curr_bbu, "bbm": curr_bbm, "bbl": curr_bbl,
        "supertrend": st_signal, "w52h": w52h, "w52l": w52l,
        "avg_vol": avg_vol, "last_vol": last_vol, "vol_ratio": vol_ratio,
        "score": score, "signals": signals, "signal": sig,
        "entry": entry, "sl": sl, "t1": t1, "t2": t2, "t3": t3,
        "pivots": pvt, "intra_sup": intra_sup, "intra_res": intra_res,
    }


def format_message(d, name="NIFTY 50"):
    now = datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")
    e = "📈" if d["change"] >= 0 else "📉"
    se = "🟢" if "BUY" in d["signal"] else ("🔴" if "SELL" in d["signal"] else "⚪")

    msg = f"""{e} *{name} Analysis*
🕐 `{now}` | Src: `{d['ticker']}`
━━━━━━━━━━━━━━━━━━━━
💰 *Price:* `{d['price']:,.2f}`  {e} `{d['change']:+.2f} ({d['pct']:+.2f}%)`
📅 *Prev Close:* `{d['prev']:,.2f}`

━━━━━━━━━━━━━━━━━━━━
{se} *SIGNAL: {d['signal']}*
📊 Score: `{d['score']}/12`
━━━━━━━━━━━━━━━━━━━━"""

    if d["entry"]:
        direction = "BUY ▲" if "BUY" in d["signal"] else "SELL ▼"
        rr = round(abs(d['t2']-d['entry']) / max(abs(d['entry']-d['sl']), 1), 1)
        msg += f"""
🎯 *TRADE SETUP — {direction}*
```
Entry    : {d['entry']:>10,.2f}
Target 1 : {d['t1']:>10,.2f}
Target 2 : {d['t2']:>10,.2f}
Target 3 : {d['t3']:>10,.2f}
Stoploss : {d['sl']:>10,.2f}
Risk/Rwd : 1:{rr}
```"""

    msg += f"""
━━━━━━━━━━━━━━━━━━━━
📐 *INDICATORS*
• RSI (14):     `{d['rsi']}` {'🔴 Overbought' if d['rsi']>70 else '🟢 Oversold' if d['rsi']<30 else '⚪ Neutral'}
• MACD:         `{d['macd']}` / Signal: `{d['macd_sig']}`
• EMA 9/21/50:  `{d['e9']:,.0f}` / `{d['e21']:,.0f}` / `{d['e50']:,.0f}`"""
    if d['e200']:
        msg += f"\n• EMA 200:      `{d['e200']:,.0f}` {'🟢' if d['price']>d['e200'] else '🔴'}"
    msg += f"""
• BB Upper/Low: `{d['bbu']:,.0f}` / `{d['bbl']:,.0f}`
• Supertrend:   `{d['supertrend']}` (Weekly) {'🟢' if d['supertrend']=='BULLISH' else '🔴'}
• ATR (14):     `{d['atr']:.2f}` (volatility)
• Volume:       `{d['vol_ratio']}x avg` {'📈 High' if d['vol_ratio']>1.5 else ''}"""

    if d["pivots"]:
        p = d["pivots"]
        msg += f"""
━━━━━━━━━━━━━━━━━━━━
🔢 *PIVOT POINTS*
```
R3: {p['r3']:>10,.2f}    R2: {p['r2']:>10,.2f}
R1: {p['r1']:>10,.2f}
PP: {p['pivot']:>10,.2f}
S1: {p['s1']:>10,.2f}
S2: {p['s2']:>10,.2f}    S3: {p['s3']:>10,.2f}
```"""

    if d["intra_res"] and d["intra_sup"]:
        msg += f"""
━━━━━━━━━━━━━━━━━━━━
⚡ *INTRADAY LEVELS (15m)*
• Resistance: `{d['intra_res']:,.2f}`
• Support:    `{d['intra_sup']:,.2f}`"""

    msg += f"""
━━━━━━━━━━━━━━━━━━━━
📅 *52W:* High `{d['w52h']:,.2f}` | Low `{d['w52l']:,.2f}`

_⚠️ Not SEBI-registered advice. Educational only._"""
    return msg.strip()


# ─── HANDLERS ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📊 Nifty Signal", callback_data="nifty"),
         InlineKeyboardButton("🏦 Bank Nifty", callback_data="banknifty")],
        [InlineKeyboardButton("🌅 All Markets", callback_data="market"),
         InlineKeyboardButton("📋 Watchlist", callback_data="watchlist")],
        [InlineKeyboardButton("🔔 Set Alert", callback_data="help_alert")],
    ]
    await update.message.reply_text(
        "🤖 *Advanced AI Trading Bot*\n\n"
        "✅ Real-time Nifty & Bank Nifty\n"
        "✅ RSI · MACD · EMA · Bollinger\n"
        "✅ Supertrend · ATR · Pivots\n"
        "✅ Auto Buy/Sell Signal + Score\n"
        "✅ Target 1/2/3 + Stoploss\n"
        "✅ Price Alerts\n\n"
        "*Commands:*\n"
        "`/nifty` — Nifty 50 full analysis\n"
        "`/banknifty` — Bank Nifty analysis\n"
        "`/analyze RELIANCE.NS` — Any stock\n"
        "`/alert 24000` — Price alert\n"
        "`/market` — All indices\n"
        "`/watch INFY.NS` — Watchlist\n\n"
        "💬 Ask anything about markets!",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )

async def nifty_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⚡ Fetching Nifty data from multiple sources...", parse_mode="Markdown")
    d = get_full_analysis(NIFTY_TICKERS)
    if not d:
        await msg.edit_text(
            "❌ *All Nifty data sources failed.*\n\n"
            "Possible reasons:\n"
            "• NSE is closed (weekends/holidays)\n"
            "• Yahoo Finance rate-limited this IP\n\n"
            "Try again in 2 minutes or use /analyze RELIANCE.NS",
            parse_mode="Markdown"
        )
        return
    kb = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="nifty"),
         InlineKeyboardButton("🏦 Bank Nifty", callback_data="banknifty")],
        [InlineKeyboardButton("🤖 AI Deep Analysis", callback_data="nifty_ai")],
    ]
    await msg.edit_text(format_message(d, "NIFTY 50"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def banknifty_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⚡ Fetching Bank Nifty data...", parse_mode="Markdown")
    d = get_full_analysis(BANKNIFTY_TICKERS)
    if not d:
        await msg.edit_text("❌ Bank Nifty data unavailable. Try again in 2 min.", parse_mode="Markdown")
        return
    kb = [[InlineKeyboardButton("🔄 Refresh", callback_data="banknifty"),
           InlineKeyboardButton("📊 Nifty 50", callback_data="nifty")]]
    await msg.edit_text(format_message(d, "BANK NIFTY"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/analyze RELIANCE.NS`\n\nAdd `.NS` for NSE stocks.\nBSE stocks: `.BO`", parse_mode="Markdown")
        return
    ticker = context.args[0].upper()
    msg = await update.message.reply_text(f"⚡ Analyzing `{ticker}`...", parse_mode="Markdown")
    d = get_full_analysis([ticker])
    if not d:
        await msg.edit_text(f"❌ No data for `{ticker}`.\n\nTips:\n• NSE: `RELIANCE.NS`\n• BSE: `RELIANCE.BO`\n• Index: `^NSEI`", parse_mode="Markdown")
        return
    await msg.edit_text(format_message(d, ticker.replace(".NS","").replace(".BO","")), parse_mode="Markdown")

async def alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/alert 24000`\nI'll notify when Nifty is within 0.2% of your level.", parse_mode="Markdown")
        return
    try:
        level = float(context.args[0].replace(",", ""))
        uid = update.effective_user.id
        if uid not in alert_jobs: alert_jobs[uid] = []
        alert_jobs[uid].append({"level": level, "chat_id": update.effective_chat.id, "triggered": False})
        await update.message.reply_text(
            f"🔔 Alert set for Nifty @ `{level:,.2f}`\n\n_Checks every 5 min during market hours (9:15–3:30 IST)_",
            parse_mode="Markdown"
        )
    except:
        await update.message.reply_text("❌ Use: `/alert 24000`", parse_mode="Markdown")

async def market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🌅 Fetching all markets...", parse_mode="Markdown")
    indices = {
        "Nifty 50": NIFTY_TICKERS,
        "Bank Nifty": BANKNIFTY_TICKERS,
        "Sensex": ["^BSESN"],
        "S&P 500": ["^GSPC"],
        "NASDAQ": ["^IXIC"],
        "Gold": ["GC=F"],
        "Crude Oil": ["CL=F"],
        "USD/INR": ["USDINR=X"],
    }
    now = datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")
    lines = [f"🌅 *Market Overview*\n🕐 `{now}`\n━━━━━━━━━━━━━━━━━━━━\n"]
    for name, tlist in indices.items():
        df, _ = fetch_with_fallback(tlist, "2d", "1d")
        if df is not None and len(df) >= 2:
            px   = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2])
            pct  = (px - prev) / prev * 100
            e = "🟢" if pct >= 0 else "🔴"
            lines.append(f"{e} *{name}:* `{px:,.2f}` ({pct:+.2f}%)")
        else:
            lines.append(f"⚪ *{name}:* Unavailable")
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")

async def watch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/watch RELIANCE.NS`", parse_mode="Markdown"); return
    ticker = context.args[0].upper()
    uid = update.effective_user.id
    if uid not in user_watchlists: user_watchlists[uid] = []
    if ticker in user_watchlists[uid]:
        await update.message.reply_text(f"✅ `{ticker}` already in watchlist!", parse_mode="Markdown"); return
    if len(user_watchlists[uid]) >= 10:
        await update.message.reply_text("⚠️ Watchlist full (max 10)."); return
    df, _ = fetch_with_fallback([ticker], "1d", "1d")
    if df is None:
        await update.message.reply_text(f"❌ Invalid `{ticker}`", parse_mode="Markdown"); return
    user_watchlists[uid].append(ticker)
    await update.message.reply_text(f"✅ `{ticker}` added!", parse_mode="Markdown")

async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    wl  = user_watchlists.get(uid, [])
    if not wl:
        await update.message.reply_text("📋 Empty. Add with `/watch TICKER`", parse_mode="Markdown"); return
    msg = await update.message.reply_text("📊 Loading...", parse_mode="Markdown")
    lines = ["📋 *Watchlist*\n━━━━━━━━━━━━━━━━━━━━\n"]
    for t in wl:
        df, _ = fetch_with_fallback([t], "2d", "1d")
        if df is not None and len(df) >= 2:
            px  = float(df["Close"].iloc[-1])
            pct = (px - float(df["Close"].iloc[-2])) / float(df["Close"].iloc[-2]) * 100
            e   = "🟢" if pct >= 0 else "🔴"
            lines.append(f"{e} *{t}*: `{px:,.2f}` ({pct:+.2f}%)")
        else:
            lines.append(f"⚪ *{t}*: Unavailable")
    kb = [[InlineKeyboardButton(t, callback_data=f"analyze_{t}")] for t in wl]
    kb.append([InlineKeyboardButton("🗑 Clear", callback_data="clear_watchlist")])
    await msg.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🤔 Thinking...", parse_mode="Markdown")
    r = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=700,
        system="You are an expert Indian stock market analyst. Specialize in Nifty 50, Bank Nifty, F&O, technicals. Concise, actionable. Not SEBI advice.",
        messages=[{"role": "user", "content": update.message.text}]
    )
    await msg.edit_text(r.content[0].text, parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    update.message = q.message

    if d == "nifty":
        await nifty_cmd(update, context)
    elif d == "banknifty":
        await banknifty_cmd(update, context)
    elif d == "market":
        await market_cmd(update, context)
    elif d == "watchlist":
        update.effective_user = q.from_user
        await watchlist_cmd(update, context)
    elif d.startswith("analyze_"):
        context.args = [d.split("_",1)[1]]
        await analyze_cmd(update, context)
    elif d == "clear_watchlist":
        user_watchlists[q.from_user.id] = []
        await q.edit_message_text("🗑 Cleared!")
    elif d == "help_alert":
        await q.message.reply_text("Usage: `/alert 24000`\nI'll alert when Nifty hits that level.", parse_mode="Markdown")
    elif d == "nifty_ai":
        nd = get_full_analysis(NIFTY_TICKERS)
        if nd:
            r = client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=800,
                system="Expert Nifty F&O trader. Give options strategy, key levels, risk. Not SEBI advice.",
                messages=[{"role": "user", "content":
                    f"Deep Nifty analysis: Price={nd['price']}, RSI={nd['rsi']}, MACD={nd['macd']}, "
                    f"EMA50={nd['e50']}, Supertrend={nd['supertrend']}, Score={nd['score']}, "
                    f"Signal={nd['signal']}, Signals={', '.join(nd['signals'][:5])}. "
                    f"Give: 1) Market context 2) CE/PE options strategy 3) Key levels 4) Risk"}]
            )
            await q.message.reply_text(r.content[0].text, parse_mode="Markdown")

# ─── ALERT CHECKER ────────────────────────────────────────────────────────────

async def check_alerts(app):
    while True:
        await asyncio.sleep(300)
        now = datetime.now(IST).time()
        if not (dtime(9,15) <= now <= dtime(15,30)):
            continue
        if not any(v for v in alert_jobs.values()):
            continue
        try:
            df, _ = fetch_with_fallback(NIFTY_TICKERS, "1d", "5m")
            if df is None: continue
            curr = float(df["Close"].iloc[-1])
            for uid, alerts in alert_jobs.items():
                for a in alerts:
                    if a["triggered"]: continue
                    if abs(curr - a["level"]) / a["level"] < 0.002:
                        a["triggered"] = True
                        await app.bot.send_message(
                            chat_id=a["chat_id"],
                            text=f"🔔 *NIFTY ALERT!*\nCurrent: `{curr:,.2f}`\nTarget: `{a['level']:,.2f}`\n\nUse /nifty for analysis.",
                            parse_mode="Markdown"
                        )
        except Exception as e:
            logger.error(f"Alert error: {e}")

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("🚀 Starting Advanced Trading Bot v2...")
    if not TELEGRAM_TOKEN:  raise ValueError("TELEGRAM_BOT_TOKEN missing!")
    if not ANTHROPIC_API_KEY: raise ValueError("ANTHROPIC_API_KEY missing!")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("nifty",      nifty_cmd))
    app.add_handler(CommandHandler("banknifty",  banknifty_cmd))
    app.add_handler(CommandHandler("analyze",    analyze_cmd))
    app.add_handler(CommandHandler("alert",      alert_cmd))
    app.add_handler(CommandHandler("market",     market_cmd))
    app.add_handler(CommandHandler("watch",      watch_cmd))
    app.add_handler(CommandHandler("watchlist",  watchlist_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    loop = asyncio.get_event_loop()
    loop.create_task(check_alerts(app))
    print("✅ Bot running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
