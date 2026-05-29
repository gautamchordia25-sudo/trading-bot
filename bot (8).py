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

user_watchlists      = {}
alert_jobs           = {}
briefing_subscribers = {}   # uid -> chat_id
trade_journals       = {}   # uid -> list of trades
trading_rules        = {}   # uid -> list of rule strings
closing_subscribers  = {}   # uid -> chat_id
volatility_subscribers = {} # uid -> chat_id
quiz_subscribers     = {}   # uid -> chat_id
last_nifty_price     = {}   # for volatility tracking

NIFTY50_STOCKS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
    "HINDUNILVR.NS","SBIN.NS","BHARTIARTL.NS","KOTAKBANK.NS","ITC.NS",
    "LT.NS","AXISBANK.NS","ASIANPAINT.NS","MARUTI.NS","NESTLEIND.NS",
    "WIPRO.NS","ULTRACEMCO.NS","TITAN.NS","SUNPHARMA.NS","BAJFINANCE.NS",
    "HCLTECH.NS","POWERGRID.NS","NTPC.NS","TECHM.NS","ONGC.NS",
]

TRADING_QUIZ = [
    {"q":"What does RSI above 70 indicate?","a":"Overbought — price may reverse down soon","opt":["Bullish breakout","Overbought — price may reverse down soon","Oversold zone","Strong buy signal"]},
    {"q":"What is a Doji candlestick?","a":"Open and close are nearly equal — market indecision","opt":["Strong bullish candle","Open and close are nearly equal — market indecision","Strong bearish candle","High volume candle"]},
    {"q":"What does MACD crossover above signal line mean?","a":"Bullish momentum — possible buy signal","opt":["Sell signal","Neutral market","Bullish momentum — possible buy signal","Overbought condition"]},
    {"q":"What is India VIX above 20 called?","a":"High fear zone — markets are volatile","opt":["Low volatility","Normal market","High fear zone — markets are volatile","Bullish signal"]},
    {"q":"What does PCR > 1.2 indicate for Nifty?","a":"More puts than calls — bullish for market","opt":["Bearish signal","More puts than calls — bullish for market","Neutral market","High volatility"]},
    {"q":"What is the Supertrend indicator used for?","a":"Identifying trend direction and trailing stop","opt":["Volume analysis","RSI divergence","Identifying trend direction and trailing stop","Finding pivot points"]},
    {"q":"What does EMA9 crossing above EMA21 signal?","a":"Short-term bullish momentum","opt":["Long-term bearish trend","Short-term bullish momentum","Reversal signal","Volume spike"]},
    {"q":"What is ATR used for in trading?","a":"Measuring volatility to set stop losses","opt":["Finding support levels","Measuring volatility to set stop losses","Predicting price direction","Calculating volume"]},
    {"q":"In options, what is Max Pain?","a":"Price where maximum options expire worthless","opt":["Highest traded price","Price where maximum options expire worthless","Most profitable strike","Put Call ratio level"]},
    {"q":"What does a Hammer candlestick at support indicate?","a":"Potential bullish reversal","opt":["Bearish continuation","Strong selling pressure","Potential bullish reversal","Sideways movement"]},
]

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
        "🤖 *AI Trading Bot v4 — Full Pack*\n\n"
        "📊 *Analysis:*\n"
        "`/nifty` `/banknifty` `/analyze TICKER`\n"
        "`/mtf` · `/vix` · `/sector` · `/expiry`\n"
        "`/topgainers` · `/toplosers` · `/market`\n\n"
        "📓 *Journal & Sizing:*\n"
        "`/trade BUY 23650 SL 23590 T1 23720`\n"
        "`/exit 23710` · `/pnl`\n"
        "`/size 500000 1` — Position sizer\n\n"
        "🔔 *Alerts & Auto Messages:*\n"
        "`/briefing` — 9 AM daily briefing\n"
        "`/closing` — 3:30 PM summary\n"
        "`/alert 24000` — Price alert\n"
        "`/volalert` — Volatility spike alert\n\n"
        "🧠 *Learn:*\n"
        "`/quiz` — Daily trading quiz\n"
        "`/rules add RULE` — Personal rules\n",
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

async def build_morning_briefing() -> str:
    """Build the full 9 AM morning briefing message."""
    now = datetime.now(IST).strftime("%d %b %Y")
    day = datetime.now(IST).strftime("%A")

    lines = [
        f"🌅 *Good Morning! Market Briefing*",
        f"📅 *{day}, {now}*",
        f"━━━━━━━━━━━━━━━━━━━━",
    ]

    # ── Indian indices ──
    indian = {"Nifty 50": NIFTY_TICKERS, "Bank Nifty": BANKNIFTY_TICKERS, "Sensex": ["^BSESN"]}
    lines.append("\n🇮🇳 *Indian Indices*")
    for name, tlist in indian.items():
        df, _ = fetch_data(tlist, "2d", "1d")
        if df is not None and len(df) >= 2:
            px   = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2])
            pct  = (px - prev) / prev * 100
            e    = "🟢" if pct >= 0 else "🔴"
            lines.append(f"{e} *{name}:* `{px:,.2f}` ({pct:+.2f}%)")
        else:
            lines.append(f"⚪ *{name}:* Unavailable")

    # ── Global cues ──
    global_idx = {"SGX Nifty (approx)": ["^NSEI"], "Dow Jones": ["^DJI"],
                  "S&P 500": ["^GSPC"], "NASDAQ": ["^IXIC"], "Nikkei": ["^N225"]}
    lines.append("\n🌍 *Global Cues*")
    for name, tlist in global_idx.items():
        df, _ = fetch_data(tlist, "2d", "1d")
        if df is not None and len(df) >= 2:
            px   = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2])
            pct  = (px - prev) / prev * 100
            e    = "🟢" if pct >= 0 else "🔴"
            lines.append(f"{e} *{name}:* `{px:,.2f}` ({pct:+.2f}%)")
        else:
            lines.append(f"⚪ *{name}:* Unavailable")

    # ── Commodities ──
    comms = {"Gold": ["GC=F"], "Crude Oil": ["CL=F"], "USD/INR": ["USDINR=X"]}
    lines.append("\n🏗 *Commodities & Currency*")
    for name, tlist in comms.items():
        df, _ = fetch_data(tlist, "2d", "1d")
        if df is not None and len(df) >= 2:
            px   = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2])
            pct  = (px - prev) / prev * 100
            e    = "🟢" if pct >= 0 else "🔴"
            lines.append(f"{e} *{name}:* `{px:,.2f}` ({pct:+.2f}%)")
        else:
            lines.append(f"⚪ *{name}:* Unavailable")

    # ── Nifty key levels from analysis ──
    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    nd = get_full_analysis(NIFTY_TICKERS)
    if nd:
        lines.append("📐 *Nifty Key Levels Today*")
        lines.append(f"• Last Close:  `{nd['prev']:,.2f}`")
        if nd["pivots"]:
            p = nd["pivots"]
            lines.append(f"• Pivot Point: `{p['pivot']:,.2f}`")
            lines.append(f"• Resistance:  `{p['r1']:,.2f}` / `{p['r2']:,.2f}`")
            lines.append(f"• Support:     `{p['s1']:,.2f}` / `{p['s2']:,.2f}`")
        if nd["support"] and nd["resistance"]:
            lines.append(f"• Swing Res:   `{nd['resistance']:,.2f}`")
            lines.append(f"• Swing Sup:   `{nd['support']:,.2f}`")

        # ── AI market outlook ──
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append("🤖 *AI Market Outlook*")
        try:
            prompt = (
                f"Nifty closed at {nd['prev']}, RSI={nd['rsi']}, MACD={nd['macd']}, "
                f"Supertrend={nd['supertrend']}, Signal={nd['signal']}, Score={nd['score']}. "
                f"Write a crisp 3-line morning market outlook for an Indian trader: "
                f"1) Overall bias 2) Key level to watch 3) One trading tip for today. "
                f"Keep it under 60 words. Not SEBI advice."
            )
            r = client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=120,
                system="Expert Nifty analyst. Crisp, actionable morning outlook. 3 lines max.",
                messages=[{"role": "user", "content": prompt}]
            )
            lines.append(r.content[0].text.strip())
        except Exception as e:
            logger.error(f"AI outlook error: {e}")
            lines.append("_AI outlook unavailable today._")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("📊 Use /nifty for live signal | /banknifty | /market")
    lines.append("_⚠️ Not SEBI advice. Trade responsibly._")
    lines.append(f"\n🕘 Market opens at *9:15 AM IST*. Good luck! 🍀")

    return "\n".join(lines)


async def briefing_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subscribe or unsubscribe from morning briefings."""
    uid     = update.effective_user.id
    chat_id = update.effective_chat.id

    if uid in briefing_subscribers:
        # Already subscribed — show options
        kb = [
            [InlineKeyboardButton("📨 Send Briefing Now", callback_data="briefing_now")],
            [InlineKeyboardButton("❌ Unsubscribe",        callback_data="briefing_unsub")],
        ]
        await update.message.reply_text(
            "✅ *You are subscribed to morning briefings!*\n\n"
            "Every weekday at *9:00 AM IST* you'll get:\n"
            "• Nifty & Bank Nifty levels\n"
            "• Global market cues\n"
            "• Commodities & USD/INR\n"
            "• Key support/resistance\n"
            "• AI market outlook\n\n"
            "Want to receive today's briefing now or unsubscribe?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        briefing_subscribers[uid] = chat_id
        kb = [[InlineKeyboardButton("📨 Send Now (Preview)", callback_data="briefing_now")]]
        await update.message.reply_text(
            "🔔 *Subscribed to Morning Briefing!*\n\n"
            "Every weekday at *9:00 AM IST* I'll send you:\n"
            "• 🇮🇳 Nifty, Bank Nifty, Sensex\n"
            "• 🌍 Dow, S&P 500, NASDAQ, Nikkei\n"
            "• 🏗 Gold, Crude Oil, USD/INR\n"
            "• 📐 Key support & resistance levels\n"
            "• 🤖 AI market outlook for the day\n\n"
            "Want to see a preview right now?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )


async def send_morning_briefing_now(chat_id: int, app) -> bool:
    """Actually send the briefing to a chat_id. Returns True on success."""
    try:
        text = await build_morning_briefing()
        await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        return True
    except Exception as e:
        logger.error(f"Briefing send error to {chat_id}: {e}")
        return False


async def morning_briefing_scheduler(app):
    """Background task — sends briefing at 9:00 AM IST on weekdays."""
    sent_today = set()   # track which uids got today's briefing

    while True:
        await asyncio.sleep(30)   # check every 30 seconds
        now     = datetime.now(IST)
        weekday = now.weekday()   # 0=Mon … 4=Fri, 5=Sat, 6=Sun

        # Reset sent_today at midnight
        if now.hour == 0 and now.minute == 0:
            sent_today.clear()

        # Only send on weekdays between 9:00 and 9:05 AM IST
        if weekday >= 5:
            continue
        if not (now.hour == 9 and 0 <= now.minute <= 4):
            continue
        if not briefing_subscribers:
            continue

        for uid, chat_id in list(briefing_subscribers.items()):
            if uid in sent_today:
                continue
            ok = await send_morning_briefing_now(chat_id, app)
            if ok:
                sent_today.add(uid)
                logger.info(f"Morning briefing sent to {uid}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🤔 Thinking...", parse_mode="Markdown")
    r = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=700,
        system="Expert Indian stock market analyst. Nifty 50, Bank Nifty, F&O, technicals. Concise, actionable. Not SEBI advice.",
        messages=[{"role": "user", "content": update.message.text}]
    )
    await msg.edit_text(r.content[0].text, parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    msg = q.message          # use q.message directly — never set update.message
    uid = q.from_user.id
    await q.answer()
    d = q.data

    if d == "nifty":
        # Send a fresh reply then run analysis against it
        sent = await msg.reply_text("⚡ Fetching Nifty data + 15m candles...", parse_mode="Markdown")
        data = get_full_analysis(NIFTY_TICKERS)
        if not data:
            await sent.edit_text("❌ Nifty data unavailable. Try in 2 min.", parse_mode="Markdown")
            return
        kb = [[InlineKeyboardButton("🔄 Refresh", callback_data="nifty"),
               InlineKeyboardButton("🏦 Bank Nifty", callback_data="banknifty")],
              [InlineKeyboardButton("🤖 AI Options View", callback_data="nifty_ai")]]
        await sent.edit_text(fmt_msg(data, "NIFTY 50"), parse_mode="Markdown",
                             reply_markup=InlineKeyboardMarkup(kb))

    elif d == "banknifty":
        sent = await msg.reply_text("⚡ Fetching Bank Nifty...", parse_mode="Markdown")
        data = get_full_analysis(BANKNIFTY_TICKERS)
        if not data:
            await sent.edit_text("❌ Bank Nifty unavailable. Try in 2 min.", parse_mode="Markdown")
            return
        kb = [[InlineKeyboardButton("🔄 Refresh", callback_data="banknifty"),
               InlineKeyboardButton("📊 Nifty 50", callback_data="nifty")]]
        await sent.edit_text(fmt_msg(data, "BANK NIFTY"), parse_mode="Markdown",
                             reply_markup=InlineKeyboardMarkup(kb))

    elif d == "market":
        sent = await msg.reply_text("🌅 Loading markets...", parse_mode="Markdown")
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
        await sent.edit_text("\n".join(lines), parse_mode="Markdown")

    elif d == "watchlist":
        wl = user_watchlists.get(uid, [])
        if not wl:
            await msg.reply_text("📋 Empty. Add with `/watch TICKER`", parse_mode="Markdown")
            return
        sent  = await msg.reply_text("📊 Loading...", parse_mode="Markdown")
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
        await sent.edit_text("\n".join(lines), parse_mode="Markdown",
                             reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("analyze_"):
        ticker = d.split("_", 1)[1]
        sent   = await msg.reply_text(f"⚡ Analyzing `{ticker}`...", parse_mode="Markdown")
        data   = get_full_analysis([ticker])
        if not data:
            await sent.edit_text(f"❌ No data for `{ticker}`.", parse_mode="Markdown")
            return
        name = ticker.replace(".NS","").replace(".BO","")
        await sent.edit_text(fmt_msg(data, name), parse_mode="Markdown")

    elif d == "clear_watchlist":
        user_watchlists[uid] = []
        await q.edit_message_text("🗑 Watchlist cleared!")

    elif d == "help_alert":
        await msg.reply_text(
            "🔔 *Set a Price Alert*\n\nUsage: `/alert 24000`\n"
            "I'll notify you when Nifty is within 0.2% of your level.",
            parse_mode="Markdown"
        )

    elif d == "briefing_now":
        sent = await msg.reply_text("📨 Building your briefing, please wait...", parse_mode="Markdown")
        text = await build_morning_briefing()
        await sent.edit_text(text, parse_mode="Markdown")

    elif d == "briefing_unsub":
        briefing_subscribers.pop(uid, None)
        await q.edit_message_text(
            "❌ Unsubscribed from morning briefings.\n\nUse /briefing to re-subscribe."
        )

    elif d.startswith("quiz_"):
        chosen = d[5:]
        state  = user_quiz_state.get(uid)
        if not state:
            await q.answer("Quiz expired. Use /quiz for a new one!"); return
        correct = state["answer"]
        if chosen.strip() == correct.strip()[:len(chosen.strip())]:
            await q.edit_message_text(
                f"✅ *Correct!*\n\n*Q:* {state['asked']}\n*A:* {correct}\n\n"
                f"_Use /quiz for another question!_", parse_mode="Markdown"
            )
        else:
            await q.edit_message_text(
                f"❌ *Wrong!*\n\n*Q:* {state['asked']}\n*Correct Answer:* {correct}\n\n"
                f"_Use /quiz to try another!_", parse_mode="Markdown"
            )
        user_quiz_state.pop(uid, None)

    elif d == "nifty_ai":
        nd = get_full_analysis(NIFTY_TICKERS)
        if nd:
            r = client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=800,
                system="Expert Nifty F&O trader. Give CE/PE options strategy, key levels, risk management. Not SEBI advice.",
                messages=[{"role": "user", "content":
                    f"Nifty at {nd['price']}, Signal={nd['signal']}, RSI={nd['rsi']}, "
                    f"MACD={nd['macd']}, EMA50={nd['e50']}, Supertrend={nd['supertrend']}, "
                    f"Support={nd['support']}, Resistance={nd['resistance']}, Score={nd['score']}. "
                    f"Give options strategy (ATM CE/PE), key levels, and risk management."}]
            )
            await msg.reply_text(r.content[0].text, parse_mode="Markdown")

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

# ══════════════════════════════════════════════════════════════
#  FEATURE 1 — SECTOR HEATMAP
# ══════════════════════════════════════════════════════════════
SECTORS = {
    "🖥 IT":      ["TCS.NS","INFY.NS","WIPRO.NS","HCLTECH.NS","TECHM.NS"],
    "🏦 Bank":    ["HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS"],
    "🚗 Auto":    ["MARUTI.NS","TATAMOTORS.NS","BAJAJ-AUTO.NS","EICHERMOT.NS","HEROMOTOCO.NS"],
    "💊 Pharma":  ["SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","APOLLOHOSP.NS"],
    "⚡ Energy":  ["ONGC.NS","POWERGRID.NS","NTPC.NS","BPCL.NS","IOC.NS"],
    "🏗 Metals":  ["TATASTEEL.NS","HINDALCO.NS","JSWSTEEL.NS","COALINDIA.NS","VEDL.NS"],
    "🛒 FMCG":   ["HINDUNILVR.NS","ITC.NS","NESTLEIND.NS","BRITANNIA.NS","DABUR.NS"],
    "🏠 Realty":  ["DLF.NS","GODREJPROP.NS","OBEROIRLTY.NS","PRESTIGE.NS","PHOENIXLTD.NS"],
}

async def sector_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔥 Building sector heatmap...", parse_mode="Markdown")
    lines = [f"🗺 *Nifty Sector Heatmap*\n🕐 `{datetime.now(IST).strftime('%d %b %Y %I:%M %p IST')}`\n━━━━━━━━━━━━━━━━━━━━\n"]
    for sector, tickers in SECTORS.items():
        gains = []
        for t in tickers:
            try:
                df, _ = fetch_data([t], "2d", "1d")
                if df is not None and len(df) >= 2:
                    pct = (float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2])) / float(df["Close"].iloc[-2]) * 100
                    gains.append(pct)
            except: pass
        if gains:
            avg = sum(gains) / len(gains)
            bar = "🟢" * min(int(abs(avg) * 2) + 1, 5) if avg >= 0 else "🔴" * min(int(abs(avg) * 2) + 1, 5)
            trend = "▲" if avg >= 0 else "▼"
            lines.append(f"{sector}: `{avg:+.2f}%` {trend} {bar}")
        else:
            lines.append(f"{sector}: ⚪ Unavailable")
    lines.append("\n_Tip: Green = sector buying, Red = sector selling_")
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════
#  FEATURE 2 — TRADE JOURNAL
# ══════════════════════════════════════════════════════════════
async def trade_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log a trade: /trade BUY 23650 SL 23590 T1 23720"""
    uid = update.effective_user.id
    if uid not in trade_journals: trade_journals[uid] = []
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "📓 *Trade Journal*\n\n"
            "*Log a trade:*\n`/trade BUY 23650 SL 23590 T1 23720`\n`/trade SELL 23700 SL 23750 T1 23620`\n\n"
            "*Close a trade:*\n`/exit 23710`\n\n"
            "*View journal:*\n`/pnl`",
            parse_mode="Markdown"
        ); return
    direction = args[0].upper()
    if direction not in ["BUY","SELL"]:
        await update.message.reply_text("❌ Use BUY or SELL. Example: `/trade BUY 23650 SL 23590 T1 23720`", parse_mode="Markdown"); return
    try:
        entry = float(args[1])
        sl = float(args[3]) if len(args) > 3 else None
        t1 = float(args[5]) if len(args) > 5 else None
        trade = {
            "id": len(trade_journals[uid]) + 1,
            "direction": direction, "entry": entry,
            "sl": sl, "t1": t1, "exit": None, "pnl": None,
            "time": datetime.now(IST).strftime("%d %b %I:%M %p"),
            "status": "OPEN"
        }
        trade_journals[uid].append(trade)
        risk = abs(entry - sl) if sl else "N/A"
        reward = abs(t1 - entry) if t1 else "N/A"
        rr = round(reward / risk, 1) if sl and t1 and risk > 0 else "N/A"
        await update.message.reply_text(
            f"✅ *Trade #{trade['id']} Logged!*\n\n"
            f"📌 Direction: `{direction}`\n"
            f"💰 Entry: `{entry:,.2f}`\n"
            f"🛑 Stoploss: `{sl:,.2f}`\n"
            f"🎯 Target: `{t1:,.2f}`\n"
            f"📊 Risk/Reward: `1:{rr}`\n\n"
            f"_Use /exit PRICE to close this trade_",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text("❌ Format: `/trade BUY 23650 SL 23590 T1 23720`", parse_mode="Markdown")

async def exit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Close last open trade: /exit 23710"""
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: `/exit 23710`", parse_mode="Markdown"); return
    trades = trade_journals.get(uid, [])
    open_trades = [t for t in trades if t["status"] == "OPEN"]
    if not open_trades:
        await update.message.reply_text("❌ No open trades. Log one with `/trade`", parse_mode="Markdown"); return
    try:
        exit_price = float(context.args[0])
        trade = open_trades[-1]
        trade["exit"] = exit_price
        trade["status"] = "CLOSED"
        if trade["direction"] == "BUY":
            trade["pnl"] = round(exit_price - trade["entry"], 2)
        else:
            trade["pnl"] = round(trade["entry"] - exit_price, 2)
        emoji = "✅ PROFIT" if trade["pnl"] > 0 else "❌ LOSS"
        await update.message.reply_text(
            f"{emoji} *Trade #{trade['id']} Closed!*\n\n"
            f"Entry: `{trade['entry']:,.2f}` → Exit: `{exit_price:,.2f}`\n"
            f"P&L: `{trade['pnl']:+.2f} pts`\n\n"
            f"_Use /pnl to see full journal_",
            parse_mode="Markdown"
        )
    except:
        await update.message.reply_text("❌ Usage: `/exit 23710`", parse_mode="Markdown")

async def pnl_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show trade journal and stats: /pnl"""
    uid = update.effective_user.id
    trades = trade_journals.get(uid, [])
    if not trades:
        await update.message.reply_text("📓 No trades yet. Start with `/trade BUY 23650 SL 23590 T1 23720`", parse_mode="Markdown"); return
    closed = [t for t in trades if t["status"] == "CLOSED"]
    open_t = [t for t in trades if t["status"] == "OPEN"]
    total_pnl = sum(t["pnl"] for t in closed)
    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]
    win_rate = round(len(wins) / len(closed) * 100) if closed else 0
    lines = [
        "📓 *Trade Journal*\n━━━━━━━━━━━━━━━━━━━━",
        f"📊 Total Trades: `{len(closed)}` | Win Rate: `{win_rate}%`",
        f"💰 Total P&L: `{total_pnl:+.2f} pts`",
        f"✅ Wins: `{len(wins)}` | ❌ Losses: `{len(losses)}`",
        "\n*Recent Trades:*"
    ]
    for t in reversed(trades[-8:]):
        st = "🟡 OPEN" if t["status"] == "OPEN" else ("✅" if t["pnl"] > 0 else "❌")
        pnl_str = f"`{t['pnl']:+.2f} pts`" if t["pnl"] is not None else "Open"
        lines.append(f"{st} #{t['id']} {t['direction']} @ `{t['entry']:,.0f}` → {pnl_str}")
    if open_t:
        lines.append(f"\n🟡 *{len(open_t)} open trade(s) — use /exit PRICE to close*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════
#  FEATURE 3 — POSITION SIZER
# ══════════════════════════════════════════════════════════════
async def size_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calculate position size: /size 500000 1"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📐 *Position Sizer*\n\nUsage: `/size CAPITAL RISK%`\n\nExample:\n`/size 500000 1` → ₹5,00,000 capital, 1% risk\n`/size 200000 0.5` → ₹2,00,000 capital, 0.5% risk",
            parse_mode="Markdown"
        ); return
    try:
        capital = float(context.args[0].replace(",",""))
        risk_pct = float(context.args[1].replace("%",""))
        risk_amt = capital * risk_pct / 100
        nd = get_full_analysis(NIFTY_TICKERS)
        atr = nd["atr_15m"] if nd else 50
        nifty_price = nd["price"] if nd else 23500
        lot_size = 25  # Nifty F&O lot size
        risk_per_lot = atr * 1.5 * lot_size
        max_lots = int(risk_amt / risk_per_lot) if risk_per_lot > 0 else 0
        margin_per_lot = nifty_price * lot_size * 0.12  # approx 12% margin
        total_margin = max_lots * margin_per_lot
        await update.message.reply_text(
            f"📐 *Position Size Calculator*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Capital:      `₹{capital:,.0f}`\n"
            f"⚠️ Risk:         `{risk_pct}%` = `₹{risk_amt:,.0f}`\n"
            f"📊 Nifty Price:  `{nifty_price:,.2f}`\n"
            f"📉 ATR (15m):    `{atr:.1f} pts`\n"
            f"🎯 Risk/Lot:     `₹{risk_per_lot:,.0f}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ *Max Lots:     `{max_lots} lots`*\n"
            f"💳 Approx Margin: `₹{total_margin:,.0f}`\n\n"
            f"_Lot size = 25 | Stop = 1.5x ATR from entry_\n"
            f"_⚠️ Not SEBI advice. Adjust per your broker margin._",
            parse_mode="Markdown"
        )
    except:
        await update.message.reply_text("❌ Usage: `/size 500000 1`", parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════
#  FEATURE 4 — WEEKLY REPORT  (Friday 3:35 PM scheduler)
# ══════════════════════════════════════════════════════════════
async def build_weekly_report() -> str:
    now = datetime.now(IST).strftime("%d %b %Y")
    lines = [f"📅 *Weekly Market Report — {now}*\n━━━━━━━━━━━━━━━━━━━━\n"]
    weekly_idx = {"Nifty 50": NIFTY_TICKERS, "Bank Nifty": BANKNIFTY_TICKERS,
                  "Sensex": ["^BSESN"], "S&P 500": ["^GSPC"], "Gold": ["GC=F"], "Crude": ["CL=F"]}
    lines.append("📊 *Weekly Performance*")
    for name, tlist in weekly_idx.items():
        df, _ = fetch_data(tlist, "1mo", "1wk")
        if df is not None and len(df) >= 2:
            px   = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2])
            pct  = (px - prev) / prev * 100
            e    = "🟢" if pct >= 0 else "🔴"
            lines.append(f"{e} *{name}:* `{px:,.2f}` ({pct:+.2f}% this week)")
        else:
            lines.append(f"⚪ *{name}:* Unavailable")
    # Top Nifty gainers/losers this week
    gainers, losers = [], []
    for t in NIFTY50_STOCKS[:15]:
        try:
            df, _ = fetch_data([t], "1mo", "1wk")
            if df is not None and len(df) >= 2:
                pct = (float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2])) / float(df["Close"].iloc[-2]) * 100
                name = t.replace(".NS","")
                if pct > 0: gainers.append((name, pct))
                else: losers.append((name, pct))
        except: pass
    gainers.sort(key=lambda x: -x[1])
    losers.sort(key=lambda x: x[1])
    if gainers:
        lines.append("\n🏆 *Top Gainers This Week*")
        for name, pct in gainers[:3]: lines.append(f"🟢 {name}: `{pct:+.2f}%`")
    if losers:
        lines.append("\n📉 *Top Losers This Week*")
        for name, pct in losers[:3]: lines.append(f"🔴 {name}: `{pct:+.2f}%`")
    try:
        r = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=120,
            system="Expert market analyst. Write a crisp 2-line weekly summary.",
            messages=[{"role": "user", "content": f"Write a 2-line weekly market summary. Nifty weekly change approx {gainers[0][1] if gainers else 0:.1f}%. Mention key theme. Not SEBI advice."}]
        )
        lines.append(f"\n🤖 *AI Weekly Insight*\n{r.content[0].text.strip()}")
    except: pass
    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("_See you next week! Use /nifty for live signals anytime._")
    return "\n".join(lines)

async def weekly_scheduler(app):
    sent_this_week = set()
    while True:
        await asyncio.sleep(60)
        now = datetime.now(IST)
        if now.weekday() != 4: continue           # Friday only
        if not (now.hour == 15 and now.minute == 35): continue
        all_subs = {**briefing_subscribers, **closing_subscribers}
        for uid, chat_id in all_subs.items():
            if uid in sent_this_week: continue
            try:
                text = await build_weekly_report()
                await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
                sent_this_week.add(uid)
            except Exception as e:
                logger.error(f"Weekly report error {uid}: {e}")
        if now.weekday() == 0: sent_this_week.clear()  # reset Monday


# ══════════════════════════════════════════════════════════════
#  FEATURE 5 — MULTI-TIMEFRAME ANALYSIS
# ══════════════════════════════════════════════════════════════
async def mtf_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⚡ Fetching 15m + 1h + Daily signals...", parse_mode="Markdown")
    results = []
    configs = [("15 min", "5d","15m"), ("1 Hour", "1mo","1h"), ("Daily", "3mo","1d")]
    for label, period, interval in configs:
        df, _ = fetch_data(NIFTY_TICKERS, period, interval)
        if df is None or len(df) < 10:
            results.append((label, "❓ No data", 0)); continue
        c = df["Close"]
        rsi_v  = float(rsi_series(c).iloc[-1])
        e9_v   = float(c.ewm(span=9).mean().iloc[-1])
        e21_v  = float(c.ewm(span=21).mean().iloc[-1])
        m, ms, _ = calc_macd(c)
        score = 0
        if rsi_v < 50: score += 1
        else: score -= 1
        if e9_v > e21_v: score += 1
        else: score -= 1
        if m > ms: score += 1
        else: score -= 1
        if score >= 2:   sig = "🟢 BULLISH"
        elif score <= -2: sig = "🔴 BEARISH"
        else:             sig = "⚪ NEUTRAL"
        results.append((label, sig, score))
    lines = [f"📊 *Multi-Timeframe Analysis — Nifty*\n🕐 `{datetime.now(IST).strftime('%d %b %I:%M %p IST')}`\n━━━━━━━━━━━━━━━━━━━━\n"]
    for label, sig, score in results:
        lines.append(f"*{label}:* {sig} (score: {score}/3)")
    all_scores = [r[2] for r in results]
    total = sum(all_scores)
    if total >= 5:   conf = "🟢🟢 HIGH CONFIDENCE BUY — All timeframes aligned!"
    elif total >= 2: conf = "🟢 BULLISH BIAS — Most timeframes agree"
    elif total <= -5: conf = "🔴🔴 HIGH CONFIDENCE SELL — All timeframes aligned!"
    elif total <= -2: conf = "🔴 BEARISH BIAS — Most timeframes agree"
    else:            conf = "⚪ MIXED — Wait for clearer signal"
    lines.append(f"\n━━━━━━━━━━━━━━━━━━━━\n🎯 *Confluence: {conf}*")
    lines.append("\n_Best trades happen when all 3 timeframes agree_")
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════
#  FEATURE 6 — EXPIRY DAY ANALYSIS  (Thursday special)
# ══════════════════════════════════════════════════════════════
async def expiry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📅 Building expiry analysis...", parse_mode="Markdown")
    now = datetime.now(IST)
    is_expiry = now.weekday() == 3
    nd = get_full_analysis(NIFTY_TICKERS)
    if not nd:
        await msg.edit_text("❌ Could not fetch Nifty data."); return
    px    = nd["price"]
    atr   = nd["atr_15m"]
    # Expected expiry range based on ATR
    upper = round(px + atr * 3, 0)
    lower = round(px - atr * 3, 0)
    # Nearest round number (max pain approximation)
    max_pain = round(px / 100) * 100
    lines = [
        f"{'🔴 TODAY IS EXPIRY DAY!' if is_expiry else '📅 Weekly Expiry Analysis'}",
        f"\n🕐 `{now.strftime('%d %b %Y %I:%M %p IST')}`",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"💰 *Nifty CMP:* `{px:,.2f}`",
        f"🎯 *Approx Max Pain:* `{max_pain:,.0f}`",
        f"📊 *Expected Range Today:*",
        f"   Upper: `{upper:,.0f}` | Lower: `{lower:,.0f}`",
        f"   Width: `{upper-lower:.0f} pts`",
        f"\n━━━━━━━━━━━━━━━━━━━━",
        f"⚡ *Expiry Day Strategies:*",
        f"• If Nifty > Max Pain → CE buyers profit, sell OTM PE",
        f"• If Nifty < Max Pain → PE buyers profit, sell OTM CE",
        f"• Straddle at `{max_pain:,.0f}` if expecting big move",
        f"• Iron Condor between `{lower:,.0f}`–`{upper:,.0f}`",
        f"\n⚠️ *Expiry Day Rules:*",
        f"• Avoid buying options after 1:30 PM (theta kills value)",
        f"• Max pain acts as a magnet — price tends to gravitate to it",
        f"• High VIX on expiry = bigger moves, be cautious",
        f"\n_⚠️ Not SEBI advice. Options trading involves high risk._"
    ]
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════
#  FEATURE 7 — CLOSING SUMMARY  (3:30 PM auto message)
# ══════════════════════════════════════════════════════════════
async def closing_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    chat_id = update.effective_chat.id
    if uid in closing_subscribers:
        closing_subscribers.pop(uid)
        await update.message.reply_text("❌ Unsubscribed from closing summary.", parse_mode="Markdown")
    else:
        closing_subscribers[uid] = chat_id
        await update.message.reply_text(
            "🌆 *Subscribed to Closing Summary!*\n\nEvery weekday at *3:30 PM IST* you'll get:\n"
            "• How Nifty closed\n• Day's high/low\n• Key levels for tomorrow\n• AI next-day outlook\n\n"
            "_Send /closing again to unsubscribe_",
            parse_mode="Markdown"
        )

async def build_closing_summary() -> str:
    now = datetime.now(IST).strftime("%d %b %Y")
    nd  = get_full_analysis(NIFTY_TICKERS)
    if not nd: return "❌ Could not build closing summary today."
    px = nd["price"]; chg = nd["change"]; pct = nd["pct"]
    e  = "🟢" if chg >= 0 else "🔴"
    df, _ = fetch_data(NIFTY_TICKERS, "1d", "15m")
    day_high = round(float(df["High"].max()), 2) if df is not None else "N/A"
    day_low  = round(float(df["Low"].min()),  2) if df is not None else "N/A"
    try:
        r = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=100,
            system="Expert Nifty analyst. 2-line next-day outlook only. Not SEBI advice.",
            messages=[{"role": "user", "content":
                f"Nifty closed {px} ({pct:+.2f}%), RSI={nd['rsi']}, Signal={nd['signal']}. "
                f"Write 2-line tomorrow's outlook — bias and key level to watch."}]
        )
        ai_outlook = r.content[0].text.strip()
    except: ai_outlook = "AI outlook unavailable."
    pvt = nd["pivots"]
    return (
        f"🌆 *Nifty Closing Summary — {now}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{e} *Close:* `{px:,.2f}` ({chg:+.2f}, {pct:+.2f}%)\n"
        f"📈 Day High: `{day_high:,}` | 📉 Day Low: `{day_low:,}`\n"
        f"📊 Signal: `{nd['signal']}`\n"
        f"\n━━━━━━━━━━━━━━━━━━━━\n📐 *Tomorrow's Key Levels*\n"
        f"• Pivot: `{pvt['pivot']:,.2f}`\n"
        f"• Resistance: `{pvt['r1']:,.2f}` / `{pvt['r2']:,.2f}`\n"
        f"• Support: `{pvt['s1']:,.2f}` / `{pvt['s2']:,.2f}`\n"
        f"\n🤖 *AI Outlook for Tomorrow*\n{ai_outlook}\n"
        f"\n_⚠️ Not SEBI advice. Trade safely tomorrow!_ 🌙"
    )

async def closing_scheduler(app):
    sent_today = set()
    while True:
        await asyncio.sleep(30)
        now = datetime.now(IST)
        if now.weekday() >= 5: continue
        if now.hour == 0 and now.minute == 0: sent_today.clear()
        if not (now.hour == 15 and 30 <= now.minute <= 34): continue
        for uid, chat_id in list(closing_subscribers.items()):
            if uid in sent_today: continue
            try:
                text = await build_closing_summary()
                await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
                sent_today.add(uid)
            except Exception as e: logger.error(f"Closing summary error {uid}: {e}")


# ══════════════════════════════════════════════════════════════
#  FEATURE 8 — TOP GAINERS / LOSERS
# ══════════════════════════════════════════════════════════════
async def topgainers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📈 Scanning Nifty 50 stocks...", parse_mode="Markdown")
    movers = []
    for t in NIFTY50_STOCKS:
        try:
            df, _ = fetch_data([t], "2d", "1d")
            if df is not None and len(df) >= 2:
                px   = float(df["Close"].iloc[-1])
                prev = float(df["Close"].iloc[-2])
                pct  = (px - prev) / prev * 100
                movers.append((t.replace(".NS",""), pct, px))
        except: pass
    movers.sort(key=lambda x: -x[1])
    gainers = movers[:5]
    losers  = list(reversed(movers[-5:]))
    lines   = [f"📊 *Top Nifty Movers Today*\n🕐 `{datetime.now(IST).strftime('%d %b %I:%M %p IST')}`\n━━━━━━━━━━━━━━━━━━━━\n"]
    lines.append("🏆 *Top Gainers*")
    for name, pct, px in gainers:
        lines.append(f"🟢 *{name}*: `{px:,.2f}` ({pct:+.2f}%)")
    lines.append("\n📉 *Top Losers*")
    for name, pct, px in losers:
        lines.append(f"🔴 *{name}*: `{px:,.2f}` ({pct:+.2f}%)")
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")

async def toplosers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ["losers"]
    await topgainers_cmd(update, context)


# ══════════════════════════════════════════════════════════════
#  FEATURE 9 — DAILY TRADING QUIZ
# ══════════════════════════════════════════════════════════════
user_quiz_state = {}  # uid -> {q_idx, answered}

async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    import random
    idx   = random.randint(0, len(TRADING_QUIZ) - 1)
    q     = TRADING_QUIZ[idx]
    opts  = q["opt"][:]
    random.shuffle(opts)
    user_quiz_state[uid] = {"answer": q["a"], "asked": q["q"]}
    kb = [[InlineKeyboardButton(opt, callback_data=f"quiz_{opt[:40]}")] for opt in opts]
    await update.message.reply_text(
        f"🧠 *Daily Trading Quiz*\n━━━━━━━━━━━━━━━━━━━━\n\n*Q: {q['q']}*\n\nChoose your answer:",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )

async def quiz_scheduler(app):
    sent_today = set()
    while True:
        await asyncio.sleep(60)
        now = datetime.now(IST)
        if now.weekday() >= 5: continue
        if now.hour == 0: sent_today.clear()
        if not (now.hour == 8 and now.minute == 45): continue
        for uid, chat_id in list(briefing_subscribers.items()):
            if uid in sent_today: continue
            try:
                import random
                q    = TRADING_QUIZ[random.randint(0, len(TRADING_QUIZ)-1)]
                opts = q["opt"][:]
                random.shuffle(opts)
                user_quiz_state[uid] = {"answer": q["a"], "asked": q["q"]}
                kb = [[InlineKeyboardButton(opt, callback_data=f"quiz_{opt[:40]}")] for opt in opts]
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=f"🧠 *Morning Quiz — {now.strftime('%d %b')}*\n\n*Q: {q['q']}*\n\nTap your answer:",
                    parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
                )
                sent_today.add(uid)
            except Exception as e: logger.error(f"Quiz error {uid}: {e}")


# ══════════════════════════════════════════════════════════════
#  FEATURE 10 — VOLATILITY SPIKE ALERT
# ══════════════════════════════════════════════════════════════
async def volalert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    chat_id = update.effective_chat.id
    if uid in volatility_subscribers:
        volatility_subscribers.pop(uid)
        await update.message.reply_text("❌ Volatility alerts OFF.", parse_mode="Markdown")
    else:
        volatility_subscribers[uid] = chat_id
        await update.message.reply_text(
            "⚡ *Volatility Alerts ON!*\n\nYou'll be notified when Nifty moves *>1% in 15 minutes*.\n\n"
            "_Checks every 15 min during market hours (9:15–3:30 IST)_\n"
            "_Send /volalert again to turn off_",
            parse_mode="Markdown"
        )

async def volatility_scheduler(app):
    while True:
        await asyncio.sleep(900)  # every 15 min
        now = datetime.now(IST).time()
        if not (dtime(9,15) <= now <= dtime(15,30)): continue
        if not volatility_subscribers: continue
        try:
            df, _ = fetch_data(NIFTY_TICKERS, "1d", "15m")
            if df is None or len(df) < 2: continue
            curr  = float(df["Close"].iloc[-1])
            prev  = float(df["Close"].iloc[-2])
            move  = (curr - prev) / prev * 100
            if abs(move) < 1.0: continue
            direction = "📈 SURGE" if move > 0 else "📉 DROP"
            for uid, chat_id in list(volatility_subscribers.items()):
                try:
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=f"⚡ *NIFTY VOLATILITY SPIKE!*\n\n"
                             f"{direction}: `{move:+.2f}%` in 15 min\n"
                             f"Current: `{curr:,.2f}` | Prev: `{prev:,.2f}`\n\n"
                             f"Use /nifty for full analysis 🚀",
                        parse_mode="Markdown"
                    )
                except Exception as e: logger.error(f"Volalert send error {uid}: {e}")
        except Exception as e: logger.error(f"Volatility scheduler error: {e}")


# ══════════════════════════════════════════════════════════════
#  FEATURE 11 — INDIA VIX TRACKER
# ══════════════════════════════════════════════════════════════
async def vix_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📊 Fetching India VIX...", parse_mode="Markdown")
    df, _ = fetch_data(["^INDIAVIX"], "1mo", "1d")
    if df is None or df.empty:
        await msg.edit_text("❌ India VIX data unavailable. Try again later."); return
    curr = round(float(df["Close"].iloc[-1]), 2)
    prev = round(float(df["Close"].iloc[-2]), 2)
    chg  = round(curr - prev, 2)
    pct  = round(chg / prev * 100, 2)
    wk_high = round(float(df["High"].max()), 2)
    wk_low  = round(float(df["Low"].min()),  2)
    if curr < 13:   zone = "🟢 LOW — Very calm market. Good for option selling."; bias = "Sell options premium"
    elif curr < 17: zone = "🟡 NORMAL — Balanced market. Trade normally."; bias = "Normal trading"
    elif curr < 20: zone = "🟠 ELEVATED — Some fear. Reduce position size."; bias = "Reduce size"
    elif curr < 25: zone = "🔴 HIGH FEAR — Big moves likely. Buy options."; bias = "Buy options / hedge"
    else:           zone = "🚨 EXTREME FEAR — Market panic. Caution!"; bias = "Avoid / wait"
    e = "📈" if chg >= 0 else "📉"
    await msg.edit_text(
        f"😨 *India VIX — Fear Index*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{e} *VIX:* `{curr}` ({chg:+.2f}, {pct:+.2f}%)\n"
        f"📅 Prev: `{prev}` | 1M High: `{wk_high}` | Low: `{wk_low}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*Zone: {zone}*\n"
        f"💡 *Suggested Bias:* `{bias}`\n\n"
        f"*VIX Guide:*\n"
        f"• `<13` → Low fear, sell options\n"
        f"• `13–17` → Normal, trade freely\n"
        f"• `17–20` → Caution, smaller size\n"
        f"• `>20` → High fear, buy options / hedge\n"
        f"• `>25` → Panic, avoid trading\n\n"
        f"_⚠️ Not SEBI advice. VIX is educational only._",
        parse_mode="Markdown"
    )


# ══════════════════════════════════════════════════════════════
#  FEATURE 12 — TRADING RULES REMINDER
# ══════════════════════════════════════════════════════════════
async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    args = context.args
    if not args:
        rules = trading_rules.get(uid, [])
        if not rules:
            await update.message.reply_text(
                "📋 *Trading Rules Reminder*\n\n"
                "No rules set yet. Add your personal rules:\n\n"
                "`/rules add Never trade without a stoploss`\n"
                "`/rules add Max 2 trades per day`\n"
                "`/rules add No trading in first 15 min`\n\n"
                "Every morning at 9 AM you'll be reminded of your rules!\n\n"
                "Other commands:\n"
                "`/rules list` — see your rules\n"
                "`/rules clear` — delete all rules",
                parse_mode="Markdown"
            ); return
        lines = ["📋 *Your Trading Rules*\n━━━━━━━━━━━━━━━━━━━━\n"]
        for i, r in enumerate(rules, 1): lines.append(f"{i}. {r}")
        lines.append("\n_These are sent to you every morning at 9 AM before market opens_")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown"); return
    subcmd = args[0].lower()
    if subcmd == "add":
        rule_text = " ".join(args[1:])
        if not rule_text:
            await update.message.reply_text("Usage: `/rules add Never average a losing trade`", parse_mode="Markdown"); return
        if uid not in trading_rules: trading_rules[uid] = []
        trading_rules[uid].append(rule_text)
        await update.message.reply_text(f"✅ Rule added: _{rule_text}_\n\nYou now have {len(trading_rules[uid])} rule(s). Use `/rules` to see all.", parse_mode="Markdown")
    elif subcmd == "list":
        rules = trading_rules.get(uid, [])
        if not rules:
            await update.message.reply_text("No rules yet. Add with `/rules add YOUR RULE`", parse_mode="Markdown"); return
        lines = ["📋 *Your Trading Rules*\n"]
        for i, r in enumerate(rules, 1): lines.append(f"{i}. {r}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    elif subcmd == "clear":
        trading_rules[uid] = []
        await update.message.reply_text("🗑 All rules cleared.", parse_mode="Markdown")
    else:
        await update.message.reply_text("Usage: `/rules add RULE` | `/rules list` | `/rules clear`", parse_mode="Markdown")


def main():
    print("🚀 Starting Advanced Trading Bot v4 — All 12 Features...")
    if not TELEGRAM_TOKEN:     raise ValueError("TELEGRAM_BOT_TOKEN missing!")
    if not ANTHROPIC_API_KEY:  raise ValueError("ANTHROPIC_API_KEY missing!")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    commands = [
        ("start",      start),
        ("nifty",      nifty_cmd),
        ("banknifty",  banknifty_cmd),
        ("analyze",    analyze_cmd),
        ("alert",      alert_cmd),
        ("market",     market_cmd),
        ("watch",      watch_cmd),
        ("watchlist",  watchlist_cmd),
        ("briefing",   briefing_cmd),
        # 12 new features
        ("sector",     sector_cmd),
        ("trade",      trade_cmd),
        ("exit",       exit_cmd),
        ("pnl",        pnl_cmd),
        ("size",       size_cmd),
        ("mtf",        mtf_cmd),
        ("expiry",     expiry_cmd),
        ("closing",    closing_cmd),
        ("topgainers", topgainers_cmd),
        ("toplosers",  toplosers_cmd),
        ("quiz",       quiz_cmd),
        ("volalert",   volalert_cmd),
        ("vix",        vix_cmd),
        ("rules",      rules_cmd),
    ]
    for cmd, fn in commands:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    loop = asyncio.get_event_loop()
    loop.create_task(check_alerts(app))
    loop.create_task(morning_briefing_scheduler(app))
    loop.create_task(closing_scheduler(app))
    loop.create_task(weekly_scheduler(app))
    loop.create_task(volatility_scheduler(app))
    loop.create_task(quiz_scheduler(app))
    print("✅ Bot v4 running — all 12 features active!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
