import os, logging, asyncio, requests
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

TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
client            = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
IST               = pytz.timezone("Asia/Kolkata")

user_watchlists = {}
alert_jobs      = {}

NIFTY_TICKERS     = ["^NSEI", "NIFTY50.NS", "NIFTYBEES.NS"]
BANKNIFTY_TICKERS = ["^NSEBANK", "BANKNIFTY.NS", "BANKBEES.NS"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://finance.yahoo.com",
}

# ─── DATA FETCHER ─────────────────────────────────────────────────────────────

def fetch_yahoo_direct(ticker, period="3mo", interval="1d"):
    enc = ticker.replace("^", "%5E")
    for base in ["query1", "query2"]:
        try:
            url = f"https://{base}.finance.yahoo.com/v8/finance/chart/{enc}?interval={interval}&range={period}&includePrePost=false"
            r   = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            res = r.json().get("chart", {}).get("result", [])
            if not res:
                continue
            res   = res[0]
            ts    = res.get("timestamp", [])
            q     = res.get("indicators", {}).get("quote", [{}])[0]
            if not ts or not q.get("close"):
                continue
            df = pd.DataFrame({
                "Open": q.get("open", []), "High": q.get("high", []),
                "Low":  q.get("low",  []), "Close": q.get("close", []),
                "Volume": q.get("volume", []),
            }, index=pd.to_datetime(ts, unit="s", utc=True))
            df = df.dropna(subset=["Close"])
            if not df.empty:
                return df
        except Exception as e:
            logger.warning(f"Direct fetch {ticker} {base}: {e}")
    return None

def fetch_data(tickers, period="3mo", interval="1d"):
    for ticker in tickers:
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval, timeout=20)
            if df is not None and not df.empty and len(df) >= 3:
                return df, ticker
        except Exception as e:
            logger.warning(f"yfinance {ticker}: {e}")
    for ticker in tickers:
        df = fetch_yahoo_direct(ticker, period, interval)
        if df is not None and len(df) >= 3:
            return df, ticker
    return None, None

# ─── INDICATORS ───────────────────────────────────────────────────────────────

def calc_rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return round(float(100 - 100 / (1 + g / l.replace(0, 1e-9))).iloc[-1] if hasattr((100 - 100 / (1 + g / l.replace(0, 1e-9))), 'iloc') else 50, 2)

def rsi_series(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + g / l.replace(0, 1e-9))

def calc_atr(h, l, c, n=14):
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def calc_macd(s):
    m  = s.ewm(span=12).mean() - s.ewm(span=26).mean()
    sg = m.ewm(span=9).mean()
    return round(float(m.iloc[-1]),2), round(float(sg.iloc[-1]),2), round(float((m-sg).iloc[-1]),2)

def calc_bb(s, n=20):
    sm = s.rolling(n).mean()
    sd = s.rolling(n).std()
    return round(float((sm+2*sd).iloc[-1]),2), round(float(sm.iloc[-1]),2), round(float((sm-2*sd).iloc[-1]),2)

def calc_supertrend(h, l, c, n=10, m=3):
    atr = calc_atr(h, l, c, n)
    mid = (h+l)/2
    ub, lb = mid + m*atr, mid - m*atr
    direction = pd.Series(1, index=c.index)
    for i in range(1, len(c)):
        if   c.iloc[i] > ub.iloc[i-1]: direction.iloc[i] =  1
        elif c.iloc[i] < lb.iloc[i-1]: direction.iloc[i] = -1
        else:                           direction.iloc[i] = direction.iloc[i-1]
    return "BULLISH" if direction.iloc[-1] == 1 else "BEARISH"

def calc_pivots(h, l, c):
    p = (h+l+c)/3
    return {"pivot": round(p,2),
            "r1": round(2*p-l,2), "r2": round(p+(h-l),2), "r3": round(h+2*(p-l),2),
            "s1": round(2*p-h,2), "s2": round(p-(h-l),2), "s3": round(l-2*(h-p),2)}

def find_sr_levels(df_15m, current_price):
    """
    Find realistic support/resistance from 15m candles.
    Uses swing highs/lows from recent price action.
    """
    if df_15m is None or len(df_15m) < 10:
        return None, None

    highs  = df_15m["High"].values
    lows   = df_15m["Low"].values
    closes = df_15m["Close"].values

    # Find swing highs (local maxima)
    swing_highs = []
    for i in range(2, len(highs)-2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            swing_highs.append(highs[i])

    # Find swing lows (local minima)
    swing_lows = []
    for i in range(2, len(lows)-2):
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            swing_lows.append(lows[i])

    # Find nearest resistance above current price
    resistance = None
    if swing_highs:
        above = [x for x in swing_highs if x > current_price * 1.001]
        if above:
            resistance = round(min(above), 2)

    # Find nearest support below current price
    support = None
    if swing_lows:
        below = [x for x in swing_lows if x < current_price * 0.999]
        if below:
            support = round(max(below), 2)

    # Fallback to session high/low if no swing levels found
    if resistance is None:
        resistance = round(float(df_15m["High"].tail(26).max()), 2)
    if support is None:
        support = round(float(df_15m["Low"].tail(26).min()), 2)

    return support, resistance


def calc_targets(current_price, signal, df_15m, df_daily, atr_15m):
    """
    Calculate accurate targets and stoploss using:
    1. 15-minute ATR for intraday precision
    2. Nearest support/resistance from swing levels
    3. Fixed risk/reward ratios
    """
    sup, res = find_sr_levels(df_15m, current_price)

    # Use 15m ATR (much tighter than daily ATR)
    atr = round(float(atr_15m), 2)

    if "BUY" in signal:
        # Stoploss = below nearest support OR 1x 15m ATR below entry
        if sup and sup > current_price - 3 * atr:
            sl = round(sup - atr * 0.3, 2)   # just below support
        else:
            sl = round(current_price - atr * 1.2, 2)

        risk = current_price - sl

        # Targets based on R:R ratios from entry
        t1 = round(current_price + risk * 1.0, 2)   # 1:1
        t2 = round(current_price + risk * 1.5, 2)   # 1:1.5
        t3 = round(current_price + risk * 2.5, 2)   # 1:2.5

        # If resistance is between entry and t1, use it as t1
        if res and current_price < res < t2:
            t1 = round(res - atr * 0.1, 2)

    elif "SELL" in signal:
        # Stoploss = above nearest resistance OR 1x 15m ATR above entry
        if res and res < current_price + 3 * atr:
            sl = round(res + atr * 0.3, 2)
        else:
            sl = round(current_price + atr * 1.2, 2)

        risk = sl - current_price

        t1 = round(current_price - risk * 1.0, 2)
        t2 = round(current_price - risk * 1.5, 2)
        t3 = round(current_price - risk * 2.5, 2)

        if sup and t2 < sup < current_price:
            t1 = round(sup + atr * 0.1, 2)
    else:
        return None, None, None, None, sup, res

    rr = round(abs(t2 - current_price) / max(abs(current_price - sl), 1), 1)
    return sl, t1, t2, t3, sup, res


# ─── MAIN ANALYSIS ────────────────────────────────────────────────────────────

def get_full_analysis(tickers):
    # Daily data (for RSI, MACD, EMA, BB, Supertrend)
    df_d, used = fetch_data(tickers, "3mo", "1d")
    if df_d is None or len(df_d) < 5:
        return None

    # 15-minute data (for intraday ATR, S/R, targets)
    df_15, _  = fetch_data(tickers, "5d",  "15m")

    # Weekly data (for Supertrend)
    df_w, _   = fetch_data(tickers, "1y",  "1wk")

    # 52-week data
    df_52, _  = fetch_data(tickers, "1y",  "1d")

    c, h, l, v = df_d["Close"], df_d["High"], df_d["Low"], df_d["Volume"]

    # Current price
    px   = round(float(c.iloc[-1]), 2)
    prev = round(float(c.iloc[-2]), 2)
    chg  = round(px - prev, 2)
    pct  = round(chg / prev * 100, 2)

    # Daily indicators
    rsi_val        = round(float(rsi_series(c).iloc[-1]), 2)
    macd, ms, mh   = calc_macd(c)
    bbu, bbm, bbl  = calc_bb(c)
    e9   = round(float(c.ewm(span=9).mean().iloc[-1]),  2)
    e21  = round(float(c.ewm(span=21).mean().iloc[-1]), 2)
    e50  = round(float(c.ewm(span=50).mean().iloc[-1]), 2)
    e200_s = c.ewm(span=200).mean()
    e200 = round(float(e200_s.iloc[-1]), 2) if len(c) >= 50 and not np.isnan(float(e200_s.iloc[-1])) else None

    daily_atr = round(float(calc_atr(h, l, c).iloc[-1]), 2)

    # 15m ATR for precise targets
    atr_15m = daily_atr / 6  # fallback: daily ATR / 6 ≈ 15m ATR
    if df_15 is not None and len(df_15) >= 14:
        atr_15m = float(calc_atr(df_15["High"], df_15["Low"], df_15["Close"]).iloc[-1])

    # Weekly Supertrend
    st = "N/A"
    if df_w is not None and len(df_w) >= 10:
        st = calc_supertrend(df_w["High"], df_w["Low"], df_w["Close"])

    # Pivot points from yesterday
    pvt = calc_pivots(float(h.iloc[-2]), float(l.iloc[-2]), float(c.iloc[-2])) if len(df_d) >= 2 else None

    # 52W range
    w52h = round(float(df_52["High"].max()), 2) if df_52 is not None else "N/A"
    w52l = round(float(df_52["Low"].min()),  2) if df_52 is not None else "N/A"

    # Volume
    avg_vol  = int(v.tail(20).mean())
    last_vol = int(v.iloc[-1])
    vol_ratio = round(last_vol / avg_vol, 2) if avg_vol > 0 else 1

    # ── Signal Scoring ──
    score   = 0
    signals = []

    if rsi_val < 30:    score += 2; signals.append("RSI oversold <30 — strong buy")
    elif rsi_val < 45:  score += 1; signals.append("RSI <45 — bullish bias")
    elif rsi_val > 70:  score -= 2; signals.append("RSI overbought >70 — sell")
    elif rsi_val > 55:  score -= 1; signals.append("RSI >55 — bearish bias")

    if macd > ms and mh > 0:   score += 2; signals.append("MACD bullish crossover")
    elif macd < ms and mh < 0: score -= 2; signals.append("MACD bearish crossover")

    if e9 > e21:   score += 1; signals.append("EMA9 > EMA21 — bullish")
    else:          score -= 1; signals.append("EMA9 < EMA21 — bearish")

    if px > e50:   score += 1; signals.append("Price above EMA50")
    else:          score -= 1; signals.append("Price below EMA50")

    if e200:
        if px > e200: score += 1; signals.append("Above EMA200 — long-term bull")
        else:         score -= 1; signals.append("Below EMA200 — long-term bear")

    if px <= bbl:   score += 2; signals.append("At lower Bollinger Band — buy zone")
    elif px >= bbu: score -= 2; signals.append("At upper Bollinger Band — sell zone")

    if st == "BULLISH":  score += 2; signals.append("Weekly Supertrend BULLISH")
    elif st == "BEARISH": score -= 2; signals.append("Weekly Supertrend BEARISH")

    if vol_ratio > 1.5 and chg > 0:  score += 1; signals.append(f"High volume up ({vol_ratio}x)")
    elif vol_ratio > 1.5 and chg < 0: score -= 1; signals.append(f"High volume down ({vol_ratio}x)")

    # Final signal
    if score >= 6:    sig = "STRONG BUY 🟢🟢"
    elif score >= 2:  sig = "BUY 🟢"
    elif score <= -6: sig = "STRONG SELL 🔴🔴"
    elif score <= -2: sig = "SELL 🔴"
    else:             sig = "NEUTRAL ⚪"

    # ── Precise Targets ──
    sl, t1, t2, t3, sup, res = calc_targets(px, sig, df_15, df_d, atr_15m)
    rr = round(abs(t2-px)/max(abs(px-sl),1), 1) if sl and t2 else None

    return {
        "ticker": used, "price": px, "prev": prev, "change": chg, "pct": pct,
        "rsi": rsi_val, "macd": macd, "macd_sig": ms, "macd_hist": mh,
        "atr_daily": daily_atr, "atr_15m": round(atr_15m, 2),
        "e9": e9, "e21": e21, "e50": e50, "e200": e200,
        "bbu": bbu, "bbm": bbm, "bbl": bbl,
        "supertrend": st, "w52h": w52h, "w52l": w52l,
        "avg_vol": avg_vol, "last_vol": last_vol, "vol_ratio": vol_ratio,
        "score": score, "signals": signals, "signal": sig,
        "sl": sl, "t1": t1, "t2": t2, "t3": t3, "rr": rr,
        "support": sup, "resistance": res, "pivots": pvt,
    }


# ─── FORMATTER ────────────────────────────────────────────────────────────────

def fmt_msg(d, name="NIFTY 50"):
    now = datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")
    e  = "📈" if d["change"] >= 0 else "📉"
    se = "🟢" if "BUY" in d["signal"] else ("🔴" if "SELL" in d["signal"] else "⚪")
    px = d["price"]

    msg = f"""{e} *{name} — Live Analysis*
🕐 `{now}`
━━━━━━━━━━━━━━━━━━━━
💰 *Price:* `{px:,.2f}`  {e} `{d['change']:+.2f} ({d['pct']:+.2f}%)`
📅 *Prev Close:* `{d['prev']:,.2f}`

━━━━━━━━━━━━━━━━━━━━
{se} *SIGNAL: {d['signal']}*
📊 *Score:* `{d['score']}/12`
━━━━━━━━━━━━━━━━━━━━"""

    if d["sl"] and d["t1"]:
        direction = "BUY ▲" if "BUY" in d["signal"] else "SELL ▼"
        risk  = abs(px - d["sl"])
        msg += f"""
🎯 *TRADE SETUP — {direction}*
```
Entry    :  {px:>10,.2f}
━━━━━━━━━━━━━━━━━━━
Target 1 :  {d['t1']:>10,.2f}  (+{abs(d['t1']-px):,.0f} pts)
Target 2 :  {d['t2']:>10,.2f}  (+{abs(d['t2']-px):,.0f} pts)
Target 3 :  {d['t3']:>10,.2f}  (+{abs(d['t3']-px):,.0f} pts)
━━━━━━━━━━━━━━━━━━━
Stoploss :  {d['sl']:>10,.2f}  (-{risk:,.0f} pts)
Risk/Rwd :  1:{d['rr']}
ATR 15m  :  {d['atr_15m']:>10,.2f}  pts
```"""

    # Key levels
    msg += f"""
━━━━━━━━━━━━━━━━━━━━
🔑 *KEY LEVELS*"""
    if d["resistance"]:
        msg += f"\n• Resistance: `{d['resistance']:,.2f}` {'⚠️ Near!' if abs(d['resistance']-px)/px < 0.005 else ''}"
    if d["support"]:
        msg += f"\n• Support:    `{d['support']:,.2f}` {'⚠️ Near!' if abs(d['support']-px)/px < 0.005 else ''}"

    msg += f"""
━━━━━━━━━━━━━━━━━━━━
📐 *INDICATORS*
• RSI (14):      `{d['rsi']}` {'🔴 Overbought' if d['rsi']>70 else '🟢 Oversold' if d['rsi']<30 else '⚪ Neutral'}
• MACD:          `{d['macd']}` / Sig: `{d['macd_sig']}`
• EMA 9/21/50:   `{d['e9']:,.0f}` / `{d['e21']:,.0f}` / `{d['e50']:,.0f}`"""
    if d["e200"]:
        msg += f"\n• EMA 200:       `{d['e200']:,.0f}` {'🟢' if px > d['e200'] else '🔴'}"
    msg += f"""
• BB Upper/Low:  `{d['bbu']:,.0f}` / `{d['bbl']:,.0f}`
• Supertrend:    `{d['supertrend']}` (Weekly) {'🟢' if d['supertrend']=='BULLISH' else '🔴' if d['supertrend']=='BEARISH' else ''}
• ATR Daily:     `{d['atr_daily']:.0f}` pts
• Volume:        `{d['vol_ratio']}x` avg {'📈' if d['vol_ratio']>1.5 else ''}"""

    if d["pivots"]:
        p = d["pivots"]
        msg += f"""
━━━━━━━━━━━━━━━━━━━━
🔢 *PIVOT POINTS*
```
R3:{p['r3']:>10,.0f}  R2:{p['r2']:>10,.0f}
R1:{p['r1']:>10,.0f}
PP:{p['pivot']:>10,.0f}
S1:{p['s1']:>10,.0f}
S2:{p['s2']:>10,.0f}  S3:{p['s3']:>10,.0f}
```"""

    msg += f"""
━━━━━━━━━━━━━━━━━━━━
📅 *52W:* High `{d['w52h']:,.2f}` | Low `{d['w52l']:,.2f}`

_⚠️ Not SEBI advice. Use your own judgment._"""
    return msg.strip()


# ─── TELEGRAM HANDLERS ────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📊 Nifty Signal", callback_data="nifty"),
         InlineKeyboardButton("🏦 Bank Nifty",   callback_data="banknifty")],
        [InlineKeyboardButton("🌅 All Markets",   callback_data="market"),
         InlineKeyboardButton("📋 Watchlist",     callback_data="watchlist")],
        [InlineKeyboardButton("🔔 Set Alert",     callback_data="help_alert")],
    ]
    await update.message.reply_text(
        "🤖 *AI Trading Bot v3 — Precise Signals*\n\n"
        "✅ 15m ATR-based Targets & Stoploss\n"
        "✅ Swing High/Low Support & Resistance\n"
        "✅ RSI · MACD · EMA9/21/50/200\n"
        "✅ Bollinger Bands · Supertrend\n"
        "✅ Daily Pivot Points\n"
        "✅ Signal Score -12 to +12\n"
        "✅ Price Alerts\n\n"
        "*Commands:*\n"
        "`/nifty` — Nifty 50 full analysis\n"
        "`/banknifty` — Bank Nifty\n"
        "`/analyze RELIANCE.NS` — Any stock\n"
        "`/alert 24000` — Price alert\n"
        "`/market` — All indices\n",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )

async def nifty_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⚡ Fetching Nifty data + 15m candles...", parse_mode="Markdown")
    d = get_full_analysis(NIFTY_TICKERS)
    if not d:
        await msg.edit_text("❌ Nifty data unavailable.\n• NSE may be closed\n• Try again in 2 min\n• Or use `/analyze RELIANCE.NS`", parse_mode="Markdown")
        return
    kb = [[InlineKeyboardButton("🔄 Refresh", callback_data="nifty"),
           InlineKeyboardButton("🏦 Bank Nifty", callback_data="banknifty")],
          [InlineKeyboardButton("🤖 AI Options View", callback_data="nifty_ai")]]
    await msg.edit_text(fmt_msg(d, "NIFTY 50"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def banknifty_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⚡ Fetching Bank Nifty...", parse_mode="Markdown")
    d = get_full_analysis(BANKNIFTY_TICKERS)
    if not d:
        await msg.edit_text("❌ Bank Nifty unavailable. Try in 2 min.", parse_mode="Markdown")
        return
    kb = [[InlineKeyboardButton("🔄 Refresh", callback_data="banknifty"),
           InlineKeyboardButton("📊 Nifty 50", callback_data="nifty")]]
    await msg.edit_text(fmt_msg(d, "BANK NIFTY"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/analyze RELIANCE.NS`", parse_mode="Markdown"); return
    ticker = context.args[0].upper()
    msg = await update.message.reply_text(f"⚡ Analyzing `{ticker}`...", parse_mode="Markdown")
    d = get_full_analysis([ticker])
    if not d:
        await msg.edit_text(f"❌ No data for `{ticker}`.\nNSE stocks: add `.NS` eg `INFY.NS`", parse_mode="Markdown"); return
    name = ticker.replace(".NS","").replace(".BO","")
    await msg.edit_text(fmt_msg(d, name), parse_mode="Markdown")

async def alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/alert 24000`", parse_mode="Markdown"); return
    try:
        level = float(context.args[0].replace(",",""))
        uid   = update.effective_user.id
        if uid not in alert_jobs: alert_jobs[uid] = []
        alert_jobs[uid].append({"level": level, "chat_id": update.effective_chat.id, "triggered": False})
        await update.message.reply_text(f"🔔 Alert set @ `{level:,.2f}`\n_Checks every 5 min, 9:15–3:30 IST_", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Use: `/alert 24000`", parse_mode="Markdown")

async def market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🌅 Loading markets...", parse_mode="Markdown")
    indices = {"Nifty 50": NIFTY_TICKERS, "Bank Nifty": BANKNIFTY_TICKERS,
               "Sensex": ["^BSESN"], "S&P 500": ["^GSPC"], "NASDAQ": ["^IXIC"],
               "Gold": ["GC=F"], "Crude Oil": ["CL=F"], "USD/INR": ["USDINR=X"]}
    now   = datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")
    lines = [f"🌅 *Market Overview*\n🕐 `{now}`\n━━━━━━━━━━━━━━━━━━━━\n"]
    for name, tlist in indices.items():
        df, _ = fetch_data(tlist, "2d", "1d")
        if df is not None and len(df) >= 2:
            px  = float(df["Close"].iloc[-1])
            pct = (px - float(df["Close"].iloc[-2])) / float(df["Close"].iloc[-2]) * 100
            e   = "🟢" if pct >= 0 else "🔴"
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
    df, _ = fetch_data([ticker], "1d", "1d")
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
        df, _ = fetch_data([t], "2d", "1d")
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
        system="Expert Indian stock market analyst. Nifty 50, Bank Nifty, F&O, technicals. Concise, actionable. Not SEBI advice.",
        messages=[{"role": "user", "content": update.message.text}]
    )
    await msg.edit_text(r.content[0].text, parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    update.message = q.message
    d = q.data
    if d == "nifty":                       await nifty_cmd(update, context)
    elif d == "banknifty":                 await banknifty_cmd(update, context)
    elif d == "market":                    await market_cmd(update, context)
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
        await q.message.reply_text("Usage: `/alert 24000`\nAlerts when Nifty is within 0.2% of your level.", parse_mode="Markdown")
    elif d == "nifty_ai":
        nd = get_full_analysis(NIFTY_TICKERS)
        if nd:
            r = client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=800,
                system="Expert Nifty F&O trader. Give CE/PE options strategy, key levels to watch, risk management. Not SEBI advice.",
                messages=[{"role": "user", "content":
                    f"Nifty at {nd['price']}, Signal={nd['signal']}, RSI={nd['rsi']}, "
                    f"MACD={nd['macd']}, EMA50={nd['e50']}, Supertrend={nd['supertrend']}, "
                    f"Support={nd['support']}, Resistance={nd['resistance']}, Score={nd['score']}. "
                    f"Give options strategy (ATM CE/PE), key levels, and risk management."}]
            )
            await q.message.reply_text(r.content[0].text, parse_mode="Markdown")

async def check_alerts(app):
    while True:
        await asyncio.sleep(300)
        now = datetime.now(IST).time()
        if not (dtime(9,15) <= now <= dtime(15,30)): continue
        if not any(alert_jobs.values()): continue
        try:
            df, _ = fetch_data(NIFTY_TICKERS, "1d", "5m")
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

def main():
    print("🚀 Starting Advanced Trading Bot v3...")
    if not TELEGRAM_TOKEN:     raise ValueError("TELEGRAM_BOT_TOKEN missing!")
    if not ANTHROPIC_API_KEY:  raise ValueError("ANTHROPIC_API_KEY missing!")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    for cmd, fn in [("start",start),("nifty",nifty_cmd),("banknifty",banknifty_cmd),
                    ("analyze",analyze_cmd),("alert",alert_cmd),("market",market_cmd),
                    ("watch",watch_cmd),("watchlist",watchlist_cmd)]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    loop = asyncio.get_event_loop()
    loop.create_task(check_alerts(app))
    print("✅ Bot v3 running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
