import os
import logging
import asyncio
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

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

IST = pytz.timezone("Asia/Kolkata")
user_watchlists = {}
alert_jobs = {}

# ─── TECHNICAL ANALYSIS ENGINE ────────────────────────────────────────────────

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast).mean()
    ema_slow = series.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

def compute_bollinger(series, period=20, std=2):
    sma = series.rolling(period).mean()
    sd = series.rolling(period).std()
    upper = sma + std * sd
    lower = sma - std * sd
    return upper, sma, lower

def compute_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def compute_supertrend(high, low, close, period=10, multiplier=3):
    atr = compute_atr(high, low, close, period)
    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr
    supertrend = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=int)
    for i in range(1, len(close)):
        if close.iloc[i] > upper_band.iloc[i-1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < lower_band.iloc[i-1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i-1]
        supertrend.iloc[i] = lower_band.iloc[i] if direction.iloc[i] == 1 else upper_band.iloc[i]
    return supertrend, direction

def compute_pivot_points(high, low, close):
    pivot = (high + low + close) / 3
    r1 = 2 * pivot - low
    s1 = 2 * pivot - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    r3 = high + 2 * (pivot - low)
    s3 = low - 2 * (high - pivot)
    return {"pivot": pivot, "r1": r1, "r2": r2, "r3": r3, "s1": s1, "s2": s2, "s3": s3}

def get_full_analysis(ticker="^NSEI", period="3mo", interval="1d"):
    try:
        stock = yf.Ticker(ticker)

        # Fetch multiple timeframes
        df_daily  = stock.history(period="3mo",  interval="1d")
        df_weekly = stock.history(period="1y",   interval="1wk")
        df_15m    = stock.history(period="5d",   interval="15m")

        if df_daily.empty:
            return None

        close  = df_daily["Close"]
        high   = df_daily["High"]
        low    = df_daily["Low"]
        volume = df_daily["Volume"]

        # ── Indicators ──
        rsi   = compute_rsi(close)
        macd, macd_signal, macd_hist = compute_macd(close)
        bb_upper, bb_mid, bb_lower   = compute_bollinger(close)
        atr    = compute_atr(high, low, close)
        ema9   = close.ewm(span=9).mean()
        ema21  = close.ewm(span=21).mean()
        ema50  = close.ewm(span=50).mean()
        ema200 = close.ewm(span=200).mean()
        sma20  = close.rolling(20).mean()

        # Supertrend on weekly
        wclose = df_weekly["Close"]
        whigh  = df_weekly["High"]
        wlow   = df_weekly["Low"]
        st_val, st_dir = compute_supertrend(whigh, wlow, wclose)

        # Pivot points (based on last completed day)
        if len(df_daily) >= 2:
            prev = df_daily.iloc[-2]
            pivots = compute_pivot_points(prev["High"], prev["Low"], prev["Close"])
        else:
            pivots = None

        # ── Current values ──
        curr_price  = round(close.iloc[-1], 2)
        prev_close  = round(close.iloc[-2], 2)
        change      = round(curr_price - prev_close, 2)
        change_pct  = round((change / prev_close) * 100, 2)
        curr_rsi    = round(rsi.iloc[-1], 2)
        curr_macd   = round(macd.iloc[-1], 2)
        curr_signal = round(macd_signal.iloc[-1], 2)
        curr_hist   = round(macd_hist.iloc[-1], 2)
        curr_atr    = round(atr.iloc[-1], 2)
        curr_ema9   = round(ema9.iloc[-1], 2)
        curr_ema21  = round(ema21.iloc[-1], 2)
        curr_ema50  = round(ema50.iloc[-1], 2)
        curr_ema200 = round(ema200.iloc[-1], 2) if not np.isnan(ema200.iloc[-1]) else None
        curr_bb_up  = round(bb_upper.iloc[-1], 2)
        curr_bb_low = round(bb_lower.iloc[-1], 2)
        curr_bb_mid = round(bb_mid.iloc[-1], 2)

        # Supertrend signal
        st_signal = "BULLISH" if st_dir.iloc[-1] == 1 else "BEARISH"

        # 52-week high/low
        df_52 = stock.history(period="1y", interval="1d")
        week52_high = round(df_52["High"].max(), 2) if not df_52.empty else "N/A"
        week52_low  = round(df_52["Low"].min(), 2)  if not df_52.empty else "N/A"

        # Volume analysis
        avg_vol  = int(volume.tail(20).mean())
        last_vol = int(volume.iloc[-1])
        vol_ratio = round(last_vol / avg_vol, 2) if avg_vol > 0 else 1

        # ── Signal Scoring System ──
        score = 0
        signals = []

        # RSI signals
        if curr_rsi < 30:
            score += 2; signals.append("RSI oversold (strong buy)")
        elif curr_rsi < 45:
            score += 1; signals.append("RSI below 45 (mild buy)")
        elif curr_rsi > 70:
            score -= 2; signals.append("RSI overbought (strong sell)")
        elif curr_rsi > 55:
            score -= 1; signals.append("RSI above 55 (mild sell)")

        # MACD signals
        if curr_macd > curr_signal and curr_hist > 0:
            score += 2; signals.append("MACD bullish crossover")
        elif curr_macd < curr_signal and curr_hist < 0:
            score -= 2; signals.append("MACD bearish crossover")

        # EMA signals
        if curr_ema9 > curr_ema21:
            score += 1; signals.append("EMA9 > EMA21 (bullish)")
        else:
            score -= 1; signals.append("EMA9 < EMA21 (bearish)")

        if curr_price > curr_ema50:
            score += 1; signals.append("Price above EMA50")
        else:
            score -= 1; signals.append("Price below EMA50")

        if curr_ema200 and curr_price > curr_ema200:
            score += 1; signals.append("Above EMA200 (long-term bullish)")
        elif curr_ema200:
            score -= 1; signals.append("Below EMA200 (long-term bearish)")

        # Bollinger Band signals
        if curr_price <= curr_bb_low:
            score += 2; signals.append("Price at lower Bollinger Band (buy zone)")
        elif curr_price >= curr_bb_up:
            score -= 2; signals.append("Price at upper Bollinger Band (sell zone)")

        # Supertrend
        if st_signal == "BULLISH":
            score += 2; signals.append("Supertrend BULLISH (weekly)")
        else:
            score -= 2; signals.append("Supertrend BEARISH (weekly)")

        # Volume confirmation
        if vol_ratio > 1.5 and change > 0:
            score += 1; signals.append(f"High volume on up day ({vol_ratio}x avg)")
        elif vol_ratio > 1.5 and change < 0:
            score -= 1; signals.append(f"High volume on down day ({vol_ratio}x avg)")

        # ── Trade Signal ──
        if score >= 5:
            trade_signal = "STRONG BUY 🟢🟢"
        elif score >= 2:
            trade_signal = "BUY 🟢"
        elif score <= -5:
            trade_signal = "STRONG SELL 🔴🔴"
        elif score <= -2:
            trade_signal = "SELL 🔴"
        else:
            trade_signal = "NEUTRAL ⚪"

        # ── Target & Stoploss (ATR-based) ──
        atr_val = curr_atr
        if "BUY" in trade_signal:
            entry      = curr_price
            stoploss   = round(entry - 1.5 * atr_val, 2)
            target1    = round(entry + 1.5 * atr_val, 2)
            target2    = round(entry + 2.5 * atr_val, 2)
            target3    = round(entry + 4.0 * atr_val, 2)
        elif "SELL" in trade_signal:
            entry      = curr_price
            stoploss   = round(entry + 1.5 * atr_val, 2)
            target1    = round(entry - 1.5 * atr_val, 2)
            target2    = round(entry - 2.5 * atr_val, 2)
            target3    = round(entry - 4.0 * atr_val, 2)
        else:
            entry = stoploss = target1 = target2 = target3 = None

        # ── 15-min intraday levels ──
        intraday_support = intraday_resist = None
        if not df_15m.empty and len(df_15m) >= 4:
            intraday_support = round(df_15m["Low"].tail(8).min(), 2)
            intraday_resist  = round(df_15m["High"].tail(8).max(), 2)

        return {
            "ticker": ticker,
            "price": curr_price,
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "rsi": curr_rsi,
            "macd": curr_macd,
            "macd_signal": curr_signal,
            "macd_hist": curr_hist,
            "atr": curr_atr,
            "ema9": curr_ema9,
            "ema21": curr_ema21,
            "ema50": curr_ema50,
            "ema200": curr_ema200,
            "bb_upper": curr_bb_up,
            "bb_mid": curr_bb_mid,
            "bb_lower": curr_bb_low,
            "supertrend": st_signal,
            "week52_high": week52_high,
            "week52_low": week52_low,
            "avg_volume": avg_vol,
            "last_volume": last_vol,
            "vol_ratio": vol_ratio,
            "score": score,
            "signals": signals,
            "trade_signal": trade_signal,
            "entry": entry,
            "stoploss": stoploss,
            "target1": target1,
            "target2": target2,
            "target3": target3,
            "pivots": pivots,
            "intraday_support": intraday_support,
            "intraday_resist": intraday_resist,
        }
    except Exception as e:
        logger.error(f"Analysis error for {ticker}: {e}")
        return None


def format_nifty_message(d):
    ist_now = datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")
    emoji = "📈" if d["change"] >= 0 else "📉"
    signal_emoji = "🟢" if "BUY" in d["trade_signal"] else ("🔴" if "SELL" in d["trade_signal"] else "⚪")

    msg = f"""
{emoji} *NIFTY 50 Analysis*
🕐 `{ist_now}`
━━━━━━━━━━━━━━━━━━━━

💰 *Price:* `{d['price']:,.2f}`
📊 *Change:* `{d['change']:+.2f} ({d['change_pct']:+.2f}%)`
📅 *Prev Close:* `{d['prev_close']:,.2f}`

━━━━━━━━━━━━━━━━━━━━
{signal_emoji} *SIGNAL: {d['trade_signal']}*
📊 *Score: {d['score']}/12*
━━━━━━━━━━━━━━━━━━━━
"""
    if d["entry"]:
        direction = "BUY" if "BUY" in d["trade_signal"] else "SELL"
        msg += f"""
🎯 *TRADE SETUP ({direction})*
┌ Entry:     `{d['entry']:,.2f}`
├ Target 1:  `{d['target1']:,.2f}`
├ Target 2:  `{d['target2']:,.2f}`
├ Target 3:  `{d['target3']:,.2f}`
└ Stoploss:  `{d['stoploss']:,.2f}`

⚠️ *Risk/Reward:* `1:{round(abs(d['target2']-d['entry'])/abs(d['entry']-d['stoploss']), 1)}`
"""

    msg += f"""
━━━━━━━━━━━━━━━━━━━━
📐 *TECHNICAL INDICATORS*
• RSI (14):       `{d['rsi']}` {'🔴 Overbought' if d['rsi']>70 else ('🟢 Oversold' if d['rsi']<30 else '⚪ Neutral')}
• MACD:           `{d['macd']}` | Signal: `{d['macd_signal']}`
• EMA 9/21/50:    `{d['ema9']:,.0f}` / `{d['ema21']:,.0f}` / `{d['ema50']:,.0f}`
• BB Upper/Lower: `{d['bb_upper']:,.0f}` / `{d['bb_lower']:,.0f}`
• Supertrend:     `{d['supertrend']}`
• ATR (14):       `{d['atr']:.2f}`
• Volume:         `{d['vol_ratio']}x` avg {'📈 High' if d['vol_ratio']>1.5 else ''}
"""

    if d["pivots"]:
        p = d["pivots"]
        msg += f"""
━━━━━━━━━━━━━━━━━━━━
🔢 *PIVOT POINTS*
• R3: `{p['r3']:,.2f}` | R2: `{p['r2']:,.2f}` | R1: `{p['r1']:,.2f}`
• Pivot: `{p['pivot']:,.2f}`
• S1: `{p['s1']:,.2f}` | S2: `{p['s2']:,.2f}` | S3: `{p['s3']:,.2f}`
"""

    if d["intraday_support"] and d["intraday_resist"]:
        msg += f"""
━━━━━━━━━━━━━━━━━━━━
⚡ *INTRADAY LEVELS (15m)*
• Resistance: `{d['intraday_resist']:,.2f}`
• Support:    `{d['intraday_support']:,.2f}`
"""

    msg += f"""
━━━━━━━━━━━━━━━━━━━━
📅 *52-WEEK RANGE*
High: `{d['week52_high']:,.2f}` | Low: `{d['week52_low']:,.2f}`

_⚠️ Not SEBI-registered advice. Educational only._
"""
    return msg.strip()


# ─── HANDLERS ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📊 Nifty Signal NOW", callback_data="nifty_signal")],
        [InlineKeyboardButton("🏦 Bank Nifty", callback_data="banknifty_signal"),
         InlineKeyboardButton("🌅 Market Overview", callback_data="market")],
        [InlineKeyboardButton("📋 Watchlist", callback_data="watchlist"),
         InlineKeyboardButton("🔔 Set Alert", callback_data="help_alert")],
    ]
    await update.message.reply_text(
        "🤖 *Advanced AI Trading Assistant*\n\n"
        "Real-time Nifty analysis with:\n"
        "✅ RSI, MACD, Bollinger Bands\n"
        "✅ Supertrend (Weekly)\n"
        "✅ Pivot Points\n"
        "✅ ATR-based Target & Stoploss\n"
        "✅ Buy/Sell Signal Scoring\n\n"
        "*Commands:*\n"
        "`/nifty` — Full Nifty 50 analysis\n"
        "`/banknifty` — Bank Nifty analysis\n"
        "`/analyze TICKER` — Any stock/index\n"
        "`/alert 24000` — Alert when Nifty hits level\n"
        "`/market` — All indices overview\n"
        "`/watch RELIANCE.NS` — Add to watchlist\n\n"
        "💬 Or ask anything about markets!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def nifty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⚡ Fetching real-time Nifty data & running analysis...", parse_mode="Markdown")
    data = get_full_analysis("^NSEI")
    if not data:
        await msg.edit_text("❌ Could not fetch Nifty data. NSE may be closed or data unavailable.")
        return
    text = format_nifty_message(data)
    kb = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="nifty_signal"),
         InlineKeyboardButton("🏦 Bank Nifty", callback_data="banknifty_signal")],
        [InlineKeyboardButton("🤖 AI Deep Analysis", callback_data="nifty_ai")],
    ]
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def banknifty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⚡ Fetching Bank Nifty data...", parse_mode="Markdown")
    data = get_full_analysis("^NSEBANK")
    if not data:
        await msg.edit_text("❌ Could not fetch Bank Nifty data.")
        return
    data["ticker"] = "BANK NIFTY"
    text = format_nifty_message(data).replace("NIFTY 50 Analysis", "BANK NIFTY Analysis")
    kb = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="banknifty_signal"),
         InlineKeyboardButton("📊 Nifty 50", callback_data="nifty_signal")],
    ]
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: `/analyze TICKER`\n\nExamples:\n`/analyze RELIANCE.NS`\n`/analyze TCS.NS`\n`/analyze ^NSEI`",
            parse_mode="Markdown"
        )
        return
    ticker = context.args[0].upper()
    msg = await update.message.reply_text(f"⚡ Analyzing `{ticker}`...", parse_mode="Markdown")
    data = get_full_analysis(ticker)
    if not data:
        await msg.edit_text(f"❌ Could not fetch data for `{ticker}`.\n\nTry: `RELIANCE.NS`, `TCS.NS`, `^NSEI`", parse_mode="Markdown")
        return
    data["ticker"] = ticker
    text = format_nifty_message(data).replace("NIFTY 50 Analysis", f"{ticker} Analysis")
    await msg.edit_text(text, parse_mode="Markdown")


async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Set a Nifty price alert:\n`/alert 24000` — alert when Nifty hits 24000\n`/alert 23500` — alert when Nifty hits 23500",
            parse_mode="Markdown"
        )
        return
    try:
        target_level = float(context.args[0].replace(",", ""))
        uid = update.effective_user.id
        chat_id = update.effective_chat.id

        if uid not in alert_jobs:
            alert_jobs[uid] = []

        alert_jobs[uid].append({"level": target_level, "chat_id": chat_id, "triggered": False})

        await update.message.reply_text(
            f"🔔 Alert set!\n\nI'll notify you when *Nifty 50* hits `{target_level:,.2f}`\n\n"
            f"_Note: Alerts check every 5 minutes during market hours (9:15 AM – 3:30 PM IST)_",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ Invalid level. Use: `/alert 24000`", parse_mode="Markdown")


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🌅 Fetching all indices...", parse_mode="Markdown")
    indices = {
        "Nifty 50": "^NSEI",
        "Bank Nifty": "^NSEBANK",
        "Nifty IT": "^CNXIT",
        "Sensex": "^BSESN",
        "S&P 500": "^GSPC",
        "NASDAQ": "^IXIC",
        "Gold": "GC=F",
        "Crude Oil": "CL=F",
        "USD/INR": "USDINR=X",
    }
    lines = [f"🌅 *Market Overview*\n🕐 `{datetime.now(IST).strftime('%d %b %Y %I:%M %p IST')}`\n━━━━━━━━━━━━━━━━━━━━\n"]
    for name, ticker in indices.items():
        try:
            t = yf.Ticker(ticker)
            h = t.history(period="2d", interval="1d")
            if not h.empty and len(h) >= 2:
                price = h["Close"].iloc[-1]
                prev  = h["Close"].iloc[-2]
                chg   = price - prev
                pct   = (chg / prev) * 100
                e = "🟢" if pct >= 0 else "🔴"
                lines.append(f"{e} *{name}:* `{price:,.2f}` ({pct:+.2f}%)")
            else:
                lines.append(f"⚪ *{name}:* Unavailable")
        except:
            lines.append(f"⚪ *{name}:* Unavailable")
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")


async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/watch RELIANCE.NS`", parse_mode="Markdown")
        return
    ticker = context.args[0].upper()
    uid = update.effective_user.id
    if uid not in user_watchlists:
        user_watchlists[uid] = []
    if ticker in user_watchlists[uid]:
        await update.message.reply_text(f"✅ `{ticker}` already in watchlist!", parse_mode="Markdown")
        return
    if len(user_watchlists[uid]) >= 10:
        await update.message.reply_text("⚠️ Watchlist full (max 10).")
        return
    try:
        t = yf.Ticker(ticker)
        h = t.history(period="1d")
        if h.empty:
            raise ValueError
        user_watchlists[uid].append(ticker)
        await update.message.reply_text(f"✅ `{ticker}` added to watchlist!", parse_mode="Markdown")
    except:
        await update.message.reply_text(f"❌ Invalid ticker `{ticker}`", parse_mode="Markdown")


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    wl = user_watchlists.get(uid, [])
    if not wl:
        await update.message.reply_text("📋 Watchlist is empty. Add with `/watch TICKER`", parse_mode="Markdown")
        return
    msg = await update.message.reply_text("📊 Loading watchlist...", parse_mode="Markdown")
    lines = ["📋 *Your Watchlist*\n━━━━━━━━━━━━━━━━━━━━\n"]
    for t in wl:
        try:
            stock = yf.Ticker(t)
            h = stock.history(period="2d", interval="1d")
            if not h.empty and len(h) >= 2:
                price = h["Close"].iloc[-1]
                prev  = h["Close"].iloc[-2]
                pct   = (price - prev) / prev * 100
                e = "🟢" if pct >= 0 else "🔴"
                lines.append(f"{e} *{t}*: `{price:,.2f}` ({pct:+.2f}%)")
            else:
                lines.append(f"⚪ *{t}*: Unavailable")
        except:
            lines.append(f"⚪ *{t}*: Error")
    kb = [[InlineKeyboardButton(t, callback_data=f"analyze_{t}")] for t in wl]
    kb.append([InlineKeyboardButton("🗑 Clear All", callback_data="clear_watchlist")])
    await msg.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    msg = await update.message.reply_text("🤔 Thinking...", parse_mode="Markdown")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
        system="""You are an expert Indian stock market analyst specializing in Nifty 50, Bank Nifty, 
F&O trading, and technical analysis. Give concise, actionable insights.
Use emojis for readability. Always mention risk. Not SEBI-registered advice.""",
        messages=[{"role": "user", "content": text}]
    )
    await msg.edit_text(response.content[0].text, parse_mode="Markdown")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "nifty_signal":
        context.args = []
        update.message = query.message
        await nifty_command(update, context)

    elif data == "banknifty_signal":
        update.message = query.message
        await banknifty_command(update, context)

    elif data == "nifty_ai":
        await query.message.reply_text("🤖 Running deep AI analysis on Nifty...", parse_mode="Markdown")
        nifty_data = get_full_analysis("^NSEI")
        if nifty_data:
            ai_prompt = f"""Do a deep analysis of Nifty 50:
Price: {nifty_data['price']} ({nifty_data['change_pct']:+.2f}%)
RSI: {nifty_data['rsi']}
MACD: {nifty_data['macd']} Signal: {nifty_data['macd_signal']}
EMA9/21/50: {nifty_data['ema9']}/{nifty_data['ema21']}/{nifty_data['ema50']}
Supertrend: {nifty_data['supertrend']}
BB: {nifty_data['bb_upper']}/{nifty_data['bb_lower']}
Score: {nifty_data['score']}
Signal: {nifty_data['trade_signal']}
Signals: {', '.join(nifty_data['signals'])}

Give: 1) Market context 2) Options strategy (CE/PE) 3) Key levels to watch 4) Risk factors"""
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                system="You are an expert Nifty F&O trader. Give detailed but actionable analysis. Not SEBI advice.",
                messages=[{"role": "user", "content": ai_prompt}]
            )
            await query.message.reply_text(response.content[0].text, parse_mode="Markdown")

    elif data == "market":
        update.message = query.message
        await market_command(update, context)

    elif data == "watchlist":
        update.message = query.message
        update.effective_user = query.from_user
        await watchlist_command(update, context)

    elif data.startswith("analyze_"):
        ticker = data.split("_", 1)[1]
        context.args = [ticker]
        update.message = query.message
        await analyze_command(update, context)

    elif data == "clear_watchlist":
        user_watchlists[query.from_user.id] = []
        await query.edit_message_text("🗑 Watchlist cleared!")

    elif data == "help_alert":
        await query.message.reply_text(
            "🔔 *Set Price Alerts*\n\nUsage: `/alert LEVEL`\n\nExamples:\n`/alert 24000` — when Nifty hits 24000\n`/alert 23500` — when Nifty hits 23500",
            parse_mode="Markdown"
        )


# ─── ALERT CHECKER (background task) ──────────────────────────────────────────

async def check_alerts(app):
    while True:
        await asyncio.sleep(300)  # every 5 minutes
        now = datetime.now(IST).time()
        market_open  = dtime(9, 15)
        market_close = dtime(15, 30)
        if not (market_open <= now <= market_close):
            continue
        if not any(alert_jobs.values()):
            continue
        try:
            t = yf.Ticker("^NSEI")
            h = t.history(period="1d", interval="5m")
            if h.empty:
                continue
            curr = h["Close"].iloc[-1]
            for uid, alerts in alert_jobs.items():
                for alert in alerts:
                    if alert["triggered"]:
                        continue
                    level = alert["level"]
                    if abs(curr - level) / level < 0.002:  # within 0.2%
                        alert["triggered"] = True
                        try:
                            await app.bot.send_message(
                                chat_id=alert["chat_id"],
                                text=f"🔔 *NIFTY ALERT TRIGGERED!*\n\nNifty is near your target level!\n"
                                     f"Current: `{curr:,.2f}`\nTarget: `{level:,.2f}`\n\n"
                                     f"Use /nifty for full analysis.",
                                parse_mode="Markdown"
                            )
                        except Exception as e:
                            logger.error(f"Alert send error: {e}")
        except Exception as e:
            logger.error(f"Alert check error: {e}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("🚀 Starting Advanced AI Trading Bot...")
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set!")
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set!")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("nifty",       nifty_command))
    app.add_handler(CommandHandler("banknifty",   banknifty_command))
    app.add_handler(CommandHandler("analyze",     analyze_command))
    app.add_handler(CommandHandler("alert",       alert_command))
    app.add_handler(CommandHandler("market",      market_command))
    app.add_handler(CommandHandler("watch",       watch_command))
    app.add_handler(CommandHandler("watchlist",   watchlist_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    loop = asyncio.get_event_loop()
    loop.create_task(check_alerts(app))

    print("✅ Advanced Bot is running!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
