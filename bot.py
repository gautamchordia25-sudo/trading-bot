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
    "Accept": "application/json,text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com",
}

# ─── DATA FETCHER — 3 sources ─────────────────────────────────────────────────

def fetch_stooq(ticker, period="3mo", interval="1d"):
    """Stooq.com — free, no auth, works from any server IP."""
    stooq_map = {
        "^NSEI": "^nsei", "NIFTY50.NS": "^nsei", "NIFTYBEES.NS": "^nsei",
        "^NSEBANK": "^nsebank", "BANKNIFTY.NS": "^nsebank",
        "^BSESN": "^bsesn", "^GSPC": "^spx", "^IXIC": "^ndq",
        "^DJI": "^dji", "^N225": "^nk225", "GC=F": "gc.f",
        "CL=F": "cl.f", "USDINR=X": "usd/inr", "^INDIAVIX": "^vix",
    }
    sym = stooq_map.get(ticker, ticker.lower().replace(".ns","").replace("^","^"))
    try:
        url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
        r   = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200 or "No data" in r.text or len(r.text) < 50:
            return None
        from io import StringIO
        df = pd.read_csv(StringIO(r.text), parse_dates=["Date"], index_col="Date")
        df.columns = [c.strip().title() for c in df.columns]
        if "Close" not in df.columns or df.empty: return None
        df = df.dropna(subset=["Close"]).sort_index()
        # Filter to requested period
        days_map = {"1d":1,"5d":5,"1mo":30,"3mo":90,"6mo":180,"1y":365}
        days = days_map.get(period, 90)
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
        df = df[df.index >= cutoff]
        if "Volume" not in df.columns: df["Volume"] = 0
        return df if len(df) >= 3 else None
    except Exception as e:
        logger.warning(f"Stooq {ticker}: {e}")
        return None

def fetch_yahoo_direct(ticker, period="3mo", interval="1d"):
    """Direct Yahoo Finance API — fallback method."""
    enc = ticker.replace("^", "%5E")
    for base in ["query2", "query1"]:
        try:
            url = f"https://{base}.finance.yahoo.com/v8/finance/chart/{enc}?interval={interval}&range={period}&includePrePost=false"
            r   = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200: continue
            res = r.json().get("chart", {}).get("result", [])
            if not res: continue
            res = res[0]
            ts  = res.get("timestamp", [])
            q   = res.get("indicators", {}).get("quote", [{}])[0]
            if not ts or not q.get("close"): continue
            df = pd.DataFrame({
                "Open": q.get("open",[]), "High": q.get("high",[]),
                "Low":  q.get("low", []), "Close": q.get("close",[]),
                "Volume": q.get("volume",[]),
            }, index=pd.to_datetime(ts, unit="s", utc=True))
            df = df.dropna(subset=["Close"])
            if not df.empty: return df
        except Exception as e:
            logger.warning(f"Yahoo direct {ticker} {base}: {e}")
    return None

def fetch_data(tickers, period="3mo", interval="1d"):
    """Try: 1) Stooq  2) yfinance  3) Yahoo direct API"""
    # Source 1: Stooq (most reliable from Railway servers)
    if interval == "1d":
        df = fetch_stooq(tickers[0], period, interval)
        if df is not None and len(df) >= 3:
            return df, tickers[0]

    # Source 2: yfinance library
    for ticker in tickers:
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval, timeout=20)
            if df is not None and not df.empty and len(df) >= 3:
                return df, ticker
        except Exception as e:
            logger.warning(f"yfinance {ticker}: {e}")

    # Source 3: Yahoo Finance direct API
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

    # ── Signal Scoring — weighted with momentum ──
    score   = 0
    signals = []

    # 1. PRICE MOMENTUM (highest weight — most important)
    # Check last 5 candles trend
    if len(c) >= 5:
        recent_trend = c.iloc[-1] - c.iloc[-5]
        pct_5d = recent_trend / c.iloc[-5] * 100
        if pct_5d < -2:   score -= 3; signals.append(f"Falling {pct_5d:.1f}% in 5 days — bearish momentum")
        elif pct_5d < -1: score -= 2; signals.append(f"Down {pct_5d:.1f}% in 5 days — weak")
        elif pct_5d > 2:  score += 3; signals.append(f"Rising {pct_5d:.1f}% in 5 days — bullish momentum")
        elif pct_5d > 1:  score += 2; signals.append(f"Up {pct_5d:.1f}% in 5 days — strong")

    # 2. TODAY'S CANDLE direction
    if chg < -0.5:  score -= 2; signals.append(f"Strong red candle today ({pct:+.2f}%)")
    elif chg < 0:   score -= 1; signals.append(f"Red candle today ({pct:+.2f}%)")
    elif chg > 0.5: score += 2; signals.append(f"Strong green candle today ({pct:+.2f}%)")
    elif chg > 0:   score += 1; signals.append(f"Green candle today ({pct:+.2f}%)")

    # 3. RSI
    if rsi_val < 30:    score += 2; signals.append("RSI oversold <30")
    elif rsi_val < 45:  score += 1; signals.append("RSI <45 — mild bullish")
    elif rsi_val > 70:  score -= 2; signals.append("RSI overbought >70")
    elif rsi_val > 55:  score -= 1; signals.append("RSI >55 — mild bearish")

    # 4. MACD
    if macd > ms and mh > 0:   score += 2; signals.append("MACD bullish crossover")
    elif macd < ms and mh < 0: score -= 2; signals.append("MACD bearish crossover")

    # 5. EMA alignment
    if e9 > e21 > e50:   score += 2; signals.append("EMAs perfectly stacked — bullish")
    elif e9 < e21 < e50: score -= 2; signals.append("EMAs bearish stack — sell pressure")
    elif e9 > e21:       score += 1; signals.append("EMA9 > EMA21 — short bullish")
    else:                score -= 1; signals.append("EMA9 < EMA21 — short bearish")

    if px > e50:   score += 1; signals.append("Price above EMA50")
    else:          score -= 1; signals.append("Price below EMA50")

    if e200:
        if px > e200: score += 1; signals.append("Above EMA200 — long-term bull")
        else:         score -= 1; signals.append("Below EMA200 — long-term bear")

    # 6. Bollinger Bands
    if px <= bbl:   score += 1; signals.append("At lower BB — potential bounce")
    elif px >= bbu: score -= 1; signals.append("At upper BB — potential reversal")

    # 7. Weekly Supertrend (trend filter — veto signal)
    if st == "BULLISH":   score += 2; signals.append("Weekly Supertrend BULLISH")
    elif st == "BEARISH": score -= 2; signals.append("Weekly Supertrend BEARISH")

    # 8. Volume confirmation
    if vol_ratio > 1.5 and chg > 0:  score += 1; signals.append(f"High volume up ({vol_ratio}x)")
    elif vol_ratio > 1.5 and chg < 0: score -= 1; signals.append(f"High volume down ({vol_ratio}x)")

    # ── TREND OVERRIDE: If price is in strong downtrend, cap score ──
    # Prevents BUY signal in clearly falling market
    if len(c) >= 10:
        trend_10d = (c.iloc[-1] - c.iloc[-10]) / c.iloc[-10] * 100
        if trend_10d < -3 and score > 0:
            score = min(score, 1)   # cap at max NEUTRAL in strong downtrend
            signals.append(f"⚠️ Trend override: {trend_10d:.1f}% drop in 10 days")
        if trend_10d > 3 and score < 0:
            score = max(score, -1)  # cap at max NEUTRAL in strong uptrend

    # Final signal with tighter thresholds
    if score >= 7:    sig = "STRONG BUY 🟢🟢"
    elif score >= 3:  sig = "BUY 🟢"
    elif score <= -7: sig = "STRONG SELL 🔴🔴"
    elif score <= -3: sig = "SELL 🔴"
    else:             sig = "NEUTRAL ⚪ — Wait"

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
        "🤖 *AI Trading Bot v5 — 20 Features*\n\n"
        "📊 *Analysis:*\n"
        "`/nifty` `/banknifty` `/analyze TICKER`\n"
        "`/mtf` · `/vix` · `/sector` · `/expiry`\n"
        "`/pattern` · `/topgainers` · `/market`\n\n"
        "📡 *Scanner:*\n"
        "`/scan rsi_low` · `/scan breakout`\n"
        "`/scan volume` · `/scan 52w_high`\n\n"
        "📰 *News & Events:*\n"
        "`/news` — Live market sentiment\n"
        "`/calendar` — RBI, GDP, Fed dates\n\n"
        "📓 *Journal & Portfolio:*\n"
        "`/trade BUY 23650 SL 23590 T1 23720`\n"
        "`/exit 23710` · `/pnl`\n"
        "`/portfolio add RELIANCE.NS 10 2450`\n"
        "`/size 500000 1` · `/backtest`\n\n"
        "🔔 *Alerts & Auto Messages:*\n"
        "`/briefing` · `/closing` · `/volalert`\n"
        "`/alert 24000` — Price alert\n\n"
        "🧠 *Learn:*\n"
        "`/quiz` · `/rules add RULE`\n\n"
        "📸 *Send any chart image for AI analysis!*\n",
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


async def handle_chart_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyse any chart image sent to the bot using Claude Vision."""
    msg = await update.message.reply_text(
        "🔍 Analysing your chart... Please wait 10-15 seconds.",
        parse_mode="Markdown"
    )
    try:
        # Download the photo from Telegram
        photo   = update.message.photo[-1]  # highest resolution
        file    = await context.bot.get_file(photo.file_id)
        img_bytes = await file.download_as_bytearray()
        import base64
        img_b64 = base64.b64encode(bytes(img_bytes)).decode("utf-8")

        caption = update.message.caption or ""
        prompt  = f"""You are an expert technical analyst specialising in Indian stock markets (Nifty, Bank Nifty, NSE stocks).

Analyse this trading chart image carefully and provide:

1. 📊 **CHART OVERVIEW**
   - What instrument/timeframe if visible
   - Current price level and trend direction

2. 📈 **TECHNICAL SIGNALS**
   - Key patterns visible (head & shoulders, double top/bottom, flags, triangles, wedges)
   - Support and resistance levels you can see
   - Any indicators visible (RSI, MACD, moving averages, Bollinger Bands)
   - Candlestick patterns at current price

3. 🎯 **TRADE SETUP**
   - Signal: BUY / SELL / NEUTRAL
   - Entry zone
   - Stop Loss level
   - Target 1 and Target 2
   - Risk:Reward ratio

4. ⚠️ **KEY RISKS**
   - What would invalidate this setup
   - Key level to watch

5. 💡 **SUMMARY**
   - One clear actionable sentence

{f"User note: {caption}" if caption else ""}

Be specific with price levels if visible. Not SEBI-registered advice."""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": img_b64,
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        analysis = response.content[0].text
        await msg.edit_text(
            f"📸 *Chart Analysis*\n━━━━━━━━━━━━━━━━━━━━\n\n{analysis}\n\n"
            f"_⚠️ Not SEBI advice. Always verify with your own analysis._",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Chart analysis error: {e}")
        await msg.edit_text(
            "❌ Could not analyse the chart.\n\n"
            "Tips:\n• Send a clear screenshot of the chart\n"
            "• Make sure the chart is readable\n• Try again",
            parse_mode="Markdown"
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-form text questions about markets."""
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
        # 6 new free features
        ("news",       news_cmd),
        ("pattern",    pattern_cmd),
        ("calendar",   calendar_cmd),
        ("portfolio",  portfolio_cmd),
        ("backtest",   backtest_cmd),
        ("scan",       scan_cmd),
    ]
    for cmd, fn in commands:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_chart_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    loop = asyncio.get_event_loop()
    loop.create_task(check_alerts(app))
    loop.create_task(morning_briefing_scheduler(app))
    loop.create_task(closing_scheduler(app))
    loop.create_task(weekly_scheduler(app))
    loop.create_task(volatility_scheduler(app))
    loop.create_task(quiz_scheduler(app))
    print("✅ Bot v5 running — 20 features active!")
    app.run_polling(drop_pending_updates=True)

# ══════════════════════════════════════════════════════════════
#  FREE FEATURE 1 — NEWS SENTIMENT SCRAPER
# ══════════════════════════════════════════════════════════════

NEWS_SOURCES = [
    ("MoneyControl", "https://www.moneycontrol.com/news/business/markets/"),
    ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/stocks/news"),
    ("LiveMint Markets", "https://www.livemint.com/market"),
]

def scrape_headlines(url: str, max_headlines: int = 8) -> list:
    """Scrape headlines from a financial news page."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return []
        from html.parser import HTMLParser
        class HeadlineParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.headlines = []
                self.in_tag = False
                self.current = ""
            def handle_starttag(self, tag, attrs):
                if tag in ("h2", "h3", "h4"):
                    self.in_tag = True
                    self.current = ""
            def handle_endtag(self, tag):
                if tag in ("h2", "h3", "h4") and self.in_tag:
                    txt = self.current.strip()
                    if len(txt) > 20 and len(txt) < 200:
                        self.headlines.append(txt)
                    self.in_tag = False
            def handle_data(self, data):
                if self.in_tag:
                    self.current += data
        p = HeadlineParser()
        p.feed(r.text)
        return p.headlines[:max_headlines]
    except Exception as e:
        logger.warning(f"Scrape error {url}: {e}")
        return []

async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scrape financial news and get AI sentiment analysis."""
    msg = await update.message.reply_text(
        "📰 Scraping latest market news...", parse_mode="Markdown"
    )
    all_headlines = []
    sources_used  = []
    for name, url in NEWS_SOURCES:
        headlines = scrape_headlines(url)
        if headlines:
            all_headlines.extend(headlines)
            sources_used.append(name)
        if len(all_headlines) >= 15:
            break

    if not all_headlines:
        await msg.edit_text(
            "❌ Could not fetch news right now. Try again in a minute.",
            parse_mode="Markdown"
        )
        return

    await msg.edit_text("🤖 Claude is analysing sentiment...", parse_mode="Markdown")

    headlines_text = "\n".join(f"- {h}" for h in all_headlines[:15])
    try:
        r = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=700,
            system="""You are an expert Indian market analyst. Analyse news headlines and give:
1. Overall market sentiment score: -5 (very bearish) to +5 (very bullish)
2. Top 3 bullish headlines with brief reason
3. Top 3 bearish headlines with brief reason
4. Key theme of today's market
5. One-line trading implication for Nifty
Use emojis. Not SEBI advice.""",
            messages=[{"role": "user", "content":
                f"Analyse these Indian market headlines for Nifty sentiment:\n\n{headlines_text}"}]
        )
        analysis = r.content[0].text
    except Exception as e:
        analysis = "AI analysis unavailable right now."

    now = datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")
    await msg.edit_text(
        f"📰 *Market News Sentiment*\n🕐 `{now}`\n"
        f"_Sources: {', '.join(sources_used)}_\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{analysis}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"_⚠️ Not SEBI advice. Sentiment is AI-generated._",
        parse_mode="Markdown"
    )


# ══════════════════════════════════════════════════════════════
#  FREE FEATURE 2 — CANDLESTICK PATTERN DETECTOR
# ══════════════════════════════════════════════════════════════

def detect_patterns(df: pd.DataFrame) -> list:
    """Detect common candlestick patterns from OHLC data."""
    patterns = []
    if len(df) < 3:
        return patterns

    o = df["Open"].values
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values

    # Last 3 candles
    o1,h1,l1,c1 = o[-3],h[-3],l[-3],c[-3]
    o2,h2,l2,c2 = o[-2],h[-2],l[-2],c[-2]
    o3,h3,l3,c3 = o[-1],h[-1],l[-1],c[-1]

    body3   = abs(c3 - o3)
    range3  = h3 - l3
    avg_body = abs(c - o).mean()

    # Doji — tiny body
    if range3 > 0 and body3 / range3 < 0.1:
        patterns.append(("⚪ Doji", "Indecision — watch for breakout direction", "neutral"))

    # Hammer — small body, long lower wick, at bottom
    lower_wick3 = min(o3, c3) - l3
    upper_wick3 = h3 - max(o3, c3)
    if body3 > 0 and lower_wick3 > 2 * body3 and upper_wick3 < body3:
        patterns.append(("🔨 Hammer", "Bullish reversal signal at support", "bullish"))

    # Shooting Star — small body, long upper wick, at top
    if body3 > 0 and upper_wick3 > 2 * body3 and lower_wick3 < body3:
        patterns.append(("⭐ Shooting Star", "Bearish reversal signal at resistance", "bearish"))

    # Bullish Engulfing
    if c2 < o2 and c3 > o3 and o3 < c2 and c3 > o2:
        patterns.append(("🟢 Bullish Engulfing", "Strong bullish reversal — buyers took control", "bullish"))

    # Bearish Engulfing
    if c2 > o2 and c3 < o3 and o3 > c2 and c3 < o2:
        patterns.append(("🔴 Bearish Engulfing", "Strong bearish reversal — sellers took control", "bearish"))

    # Morning Star (3-candle)
    if c1 < o1 and body3 < avg_body * 0.3 and c3 > o3 and c3 > (o1 + c1) / 2:
        patterns.append(("🌟 Morning Star", "Powerful 3-candle bullish reversal", "bullish"))

    # Evening Star (3-candle)
    if c1 > o1 and body3 < avg_body * 0.3 and c3 < o3 and c3 < (o1 + c1) / 2:
        patterns.append(("🌙 Evening Star", "Powerful 3-candle bearish reversal", "bearish"))

    # Three White Soldiers
    if c3 > o3 and c2 > o2 and c1 > o1 and c3 > c2 > c1:
        patterns.append(("💪 Three White Soldiers", "Strong bullish continuation — 3 green candles", "bullish"))

    # Three Black Crows
    if c3 < o3 and c2 < o2 and c1 < o1 and c3 < c2 < c1:
        patterns.append(("🪦 Three Black Crows", "Strong bearish continuation — 3 red candles", "bearish"))

    # Inside Bar (consolidation)
    if h3 < h2 and l3 > l2:
        patterns.append(("📦 Inside Bar", "Consolidation — breakout coming soon", "neutral"))

    return patterns if patterns else [("⚪ No pattern", "No clear pattern on last 3 candles", "neutral")]


async def pattern_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detect candlestick patterns on any ticker."""
    ticker = "^NSEI"
    name   = "Nifty 50"
    if context.args:
        ticker = context.args[0].upper()
        name   = ticker.replace(".NS","").replace(".BO","")

    msg = await update.message.reply_text(
        f"🕯 Detecting patterns on *{name}*...", parse_mode="Markdown"
    )
    df, _ = fetch_data([ticker], "3mo", "1d")
    if df is None or len(df) < 5:
        await msg.edit_text(f"❌ No data for `{ticker}`", parse_mode="Markdown")
        return

    patterns = detect_patterns(df)
    px  = round(float(df["Close"].iloc[-1]), 2)
    chg = round(float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2]), 2)
    pct = round(chg / float(df["Close"].iloc[-2]) * 100, 2)
    e   = "📈" if chg >= 0 else "📉"

    lines = [
        f"🕯 *Candlestick Pattern Report — {name}*",
        f"🕐 `{datetime.now(IST).strftime('%d %b %Y %I:%M %p IST')}`",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"{e} Price: `{px:,.2f}` ({chg:+.2f}, {pct:+.2f}%)",
        f"\n*Patterns Detected (Last 3 Candles):*",
    ]
    bull = [p for p in patterns if p[2] == "bullish"]
    bear = [p for p in patterns if p[2] == "bearish"]
    neut = [p for p in patterns if p[2] == "neutral"]

    for name_p, desc, _ in bull:
        lines.append(f"🟢 *{name_p}*\n   _{desc}_")
    for name_p, desc, _ in bear:
        lines.append(f"🔴 *{name_p}*\n   _{desc}_")
    for name_p, desc, _ in neut:
        lines.append(f"⚪ *{name_p}*\n   _{desc}_")

    if bull and not bear:
        lines.append(f"\n━━━━━━━━━━━━━━━━━━━━\n💡 *Bias: BULLISH* — Look for long setups")
    elif bear and not bull:
        lines.append(f"\n━━━━━━━━━━━━━━━━━━━━\n💡 *Bias: BEARISH* — Look for short setups")
    else:
        lines.append(f"\n━━━━━━━━━━━━━━━━━━━━\n💡 *Bias: MIXED* — Wait for confirmation")

    lines.append(f"\n_Usage: /pattern RELIANCE.NS or /pattern ^NSEBANK_")
    lines.append(f"_⚠️ Not SEBI advice. Educational only._")
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════
#  FREE FEATURE 3 — ECONOMIC CALENDAR
# ══════════════════════════════════════════════════════════════

ECONOMIC_EVENTS = [
    # (month, day, event, impact, description)
    (6,  6,  "RBI MPC Policy Decision",         "🔴 HIGH",  "Rate decision — major market mover"),
    (6,  12, "India CPI Inflation Data",         "🟠 MED",   "Consumer price index — affects RBI stance"),
    (6,  14, "India WPI Inflation",              "🟡 LOW",   "Wholesale price index data"),
    (6,  17, "India IIP Data",                   "🟠 MED",   "Industrial production — growth indicator"),
    (6,  18, "US Fed FOMC Meeting",              "🔴 HIGH",  "US rate decision — affects FII flows to India"),
    (6,  28, "India GDP Q4 Data",                "🔴 HIGH",  "Quarterly GDP — big market impact"),
    (7,  4,  "RBI MPC Minutes",                  "🟠 MED",   "RBI meeting minutes released"),
    (7,  11, "India CPI Inflation",              "🟠 MED",   "Monthly inflation data"),
    (7,  25, "US Fed Meeting",                   "🔴 HIGH",  "US rate decision"),
    (8,  8,  "RBI MPC Policy Decision",          "🔴 HIGH",  "Rate decision"),
    (8,  15, "Independence Day — Market Holiday","⚫ HOLI",  "NSE/BSE closed"),
]

async def calendar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show upcoming economic events."""
    now   = datetime.now(IST)
    lines = [
        f"📅 *Economic Calendar*",
        f"🕐 `{now.strftime('%d %b %Y')}`",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"*Upcoming Events (Next 60 days):*\n",
    ]
    found = 0
    for month, day, event, impact, desc in ECONOMIC_EVENTS:
        year = now.year
        try:
            ev_date = datetime(year, month, day, tzinfo=IST)
        except:
            continue
        if ev_date < now:
            ev_date = datetime(year + 1, month, day, tzinfo=IST)
        days_away = (ev_date.date() - now.date()).days
        if 0 <= days_away <= 60:
            dow = ev_date.strftime("%a %d %b")
            prefix = "🔜 TODAY" if days_away == 0 else (f"⏳ {days_away}d away")
            lines.append(f"{impact} *{event}*\n   📅 {dow} — {prefix}\n   _{desc}_\n")
            found += 1

    if found == 0:
        lines.append("No major events in the next 60 days.")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("*Impact guide:* 🔴 High | 🟠 Medium | 🟡 Low | ⚫ Holiday")
    lines.append("_Plan your trades around high-impact events!_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════
#  FREE FEATURE 4 — PORTFOLIO TRACKER
# ══════════════════════════════════════════════════════════════

portfolios = {}   # uid -> {ticker: {qty, avg_price}}

async def portfolio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Portfolio tracker: /portfolio add RELIANCE.NS 10 2450"""
    uid  = update.effective_user.id
    args = context.args

    if not args:
        port = portfolios.get(uid, {})
        if not port:
            await update.message.reply_text(
                "💼 *Portfolio Tracker*\n\n"
                "*Add a holding:*\n`/portfolio add RELIANCE.NS 10 2450`\n"
                "_(ticker, quantity, avg buy price)_\n\n"
                "*Remove:*\n`/portfolio remove RELIANCE.NS`\n\n"
                "*View P&L:*\n`/portfolio` or `/portfolio view`",
                parse_mode="Markdown"
            )
            return
        # Show P&L
        msg  = await update.message.reply_text("💼 Calculating portfolio P&L...", parse_mode="Markdown")
        total_invested = 0
        total_current  = 0
        lines = ["💼 *Portfolio P&L*\n━━━━━━━━━━━━━━━━━━━━\n"]
        for ticker, data in port.items():
            df, _ = fetch_data([ticker], "2d", "1d")
            if df is not None and not df.empty:
                curr_px = float(df["Close"].iloc[-1])
                invested = data["qty"] * data["avg"]
                current  = data["qty"] * curr_px
                pnl      = current - invested
                pnl_pct  = pnl / invested * 100
                total_invested += invested
                total_current  += current
                e = "🟢" if pnl >= 0 else "🔴"
                name = ticker.replace(".NS","").replace(".BO","")
                lines.append(
                    f"{e} *{name}* ({data['qty']} shares)\n"
                    f"   Avg: `₹{data['avg']:,.2f}` → CMP: `₹{curr_px:,.2f}`\n"
                    f"   P&L: `{pnl:+,.0f}` ({pnl_pct:+.1f}%)\n"
                )
            else:
                lines.append(f"⚪ *{ticker}*: Price unavailable\n")

        total_pnl     = total_current - total_invested
        total_pnl_pct = total_pnl / total_invested * 100 if total_invested > 0 else 0
        e = "🟢" if total_pnl >= 0 else "🔴"
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{e} *Total Invested:* `₹{total_invested:,.0f}`")
        lines.append(f"{e} *Current Value:*  `₹{total_current:,.0f}`")
        lines.append(f"{e} *Total P&L:*      `{total_pnl:+,.0f}` ({total_pnl_pct:+.1f}%)")
        await msg.edit_text("\n".join(lines), parse_mode="Markdown")
        return

    subcmd = args[0].lower()
    if subcmd == "add":
        if len(args) < 4:
            await update.message.reply_text(
                "Usage: `/portfolio add RELIANCE.NS 10 2450`", parse_mode="Markdown"
            )
            return
        ticker = args[1].upper()
        try:
            qty = float(args[2])
            avg = float(args[3])
        except:
            await update.message.reply_text("❌ Invalid qty or price.", parse_mode="Markdown")
            return
        if uid not in portfolios:
            portfolios[uid] = {}
        portfolios[uid][ticker] = {"qty": qty, "avg": avg}
        name = ticker.replace(".NS","").replace(".BO","")
        await update.message.reply_text(
            f"✅ *{name}* added!\n"
            f"Qty: `{qty}` | Avg Price: `₹{avg:,.2f}`\n"
            f"Invested: `₹{qty*avg:,.0f}`\n\n"
            f"Use `/portfolio` to see full P&L.",
            parse_mode="Markdown"
        )
    elif subcmd == "remove":
        if len(args) < 2:
            await update.message.reply_text("Usage: `/portfolio remove RELIANCE.NS`", parse_mode="Markdown")
            return
        ticker = args[1].upper()
        if uid in portfolios and ticker in portfolios[uid]:
            del portfolios[uid][ticker]
            await update.message.reply_text(f"🗑 `{ticker}` removed from portfolio.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ `{ticker}` not found.", parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "Usage:\n`/portfolio add TICKER QTY AVG_PRICE`\n`/portfolio remove TICKER`\n`/portfolio` — view P&L",
            parse_mode="Markdown"
        )


# ══════════════════════════════════════════════════════════════
#  FREE FEATURE 5 — SIGNAL BACKTESTER
# ══════════════════════════════════════════════════════════════

async def backtest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Backtest current buy/sell signal logic on 1 year of Nifty data."""
    msg = await update.message.reply_text(
        "⏪ Running backtest on 1 year of Nifty data...\n_This takes ~20 seconds_",
        parse_mode="Markdown"
    )
    df, _ = fetch_data(NIFTY_TICKERS, "1y", "1d")
    if df is None or len(df) < 50:
        await msg.edit_text("❌ Not enough data for backtest.", parse_mode="Markdown")
        return

    c = df["Close"]
    h = df["High"]
    l = df["Low"]
    v = df["Volume"]

    trades    = []
    in_trade  = None
    wins = losses = 0
    total_pts = 0.0

    # Compute indicators for full series
    rsi_s   = rsi_series(c)
    ema9_s  = c.ewm(span=9).mean()
    ema21_s = c.ewm(span=21).mean()
    ema50_s = c.ewm(span=50).mean()
    macd_s  = c.ewm(span=12).mean() - c.ewm(span=26).mean()
    sig_s   = macd_s.ewm(span=9).mean()
    atr_s   = calc_atr(h, l, c)
    bb_mid  = c.rolling(20).mean()
    bb_std  = c.rolling(20).std()
    bb_up   = bb_mid + 2 * bb_std
    bb_lo   = bb_mid - 2 * bb_std

    for i in range(30, len(c) - 1):
        px_i   = float(c.iloc[i])
        rsi_i  = float(rsi_s.iloc[i])
        e9_i   = float(ema9_s.iloc[i])
        e21_i  = float(ema21_s.iloc[i])
        e50_i  = float(ema50_s.iloc[i])
        mac_i  = float(macd_s.iloc[i])
        msi_i  = float(sig_s.iloc[i])
        atr_i  = float(atr_s.iloc[i])
        bbu_i  = float(bb_up.iloc[i])
        bbl_i  = float(bb_lo.iloc[i])
        chg_i  = px_i - float(c.iloc[i-1])

        # 5-day momentum
        pct5 = (px_i - float(c.iloc[i-5])) / float(c.iloc[i-5]) * 100

        # Score (simplified version of live signal)
        sc = 0
        if pct5 > 2:   sc += 3
        elif pct5 > 1: sc += 2
        elif pct5 < -2: sc -= 3
        elif pct5 < -1: sc -= 2
        if chg_i > 0: sc += 1
        else:          sc -= 1
        if rsi_i < 45:  sc += 1
        elif rsi_i > 55: sc -= 1
        if mac_i > msi_i: sc += 2
        else:             sc -= 2
        if e9_i > e21_i > e50_i: sc += 2
        elif e9_i < e21_i < e50_i: sc -= 2

        # Check 10d trend override
        pct10 = (px_i - float(c.iloc[i-10])) / float(c.iloc[i-10]) * 100
        if pct10 < -3 and sc > 0: sc = min(sc, 1)
        if pct10 > 3  and sc < 0: sc = max(sc, -1)

        signal = "BUY" if sc >= 3 else ("SELL" if sc <= -3 else "HOLD")

        if in_trade is None:
            if signal in ("BUY", "SELL"):
                sl  = px_i - 1.5 * atr_i if signal == "BUY" else px_i + 1.5 * atr_i
                tp  = px_i + 2.5 * atr_i if signal == "BUY" else px_i - 2.5 * atr_i
                in_trade = {"dir": signal, "entry": px_i, "sl": sl, "tp": tp, "bar": i}
        else:
            px_next = float(c.iloc[i+1])
            hit_sl  = (px_next <= in_trade["sl"]) if in_trade["dir"] == "BUY" else (px_next >= in_trade["sl"])
            hit_tp  = (px_next >= in_trade["tp"]) if in_trade["dir"] == "BUY" else (px_next <= in_trade["tp"])
            if hit_sl or hit_tp or (i - in_trade["bar"]) >= 10:
                exit_px = in_trade["sl"] if hit_sl else (in_trade["tp"] if hit_tp else px_next)
                pnl_pts = (exit_px - in_trade["entry"]) if in_trade["dir"] == "BUY" else (in_trade["entry"] - exit_px)
                trades.append(pnl_pts)
                total_pts += pnl_pts
                if pnl_pts > 0: wins += 1
                else: losses += 1
                in_trade = None

    total = wins + losses
    win_rate  = round(wins / total * 100) if total > 0 else 0
    avg_win   = round(sum(p for p in trades if p > 0) / wins, 1) if wins > 0 else 0
    avg_loss  = round(sum(p for p in trades if p <= 0) / losses, 1) if losses > 0 else 0
    profit_factor = round(abs(sum(p for p in trades if p > 0)) / abs(sum(p for p in trades if p < 0)), 2) if losses > 0 else 0

    e = "✅" if total_pts > 0 else "❌"
    await msg.edit_text(
        f"⏪ *Backtest Results — Nifty 1 Year*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Total Trades:    `{total}`\n"
        f"✅ Wins:            `{wins}` ({win_rate}%)\n"
        f"❌ Losses:          `{losses}` ({100-win_rate}%)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{e} Total P&L:       `{total_pts:+.1f} pts`\n"
        f"📈 Avg Win:         `+{avg_win} pts`\n"
        f"📉 Avg Loss:        `{avg_loss} pts`\n"
        f"⚖️ Profit Factor:   `{profit_factor}x`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{'✅ Strategy is PROFITABLE on historical data' if total_pts > 0 else '⚠️ Strategy needs improvement — tweak signals'}\n\n"
        f"_Note: Past performance ≠ future results._\n"
        f"_Backtest uses simplified signal logic._\n"
        f"_⚠️ Not SEBI advice._",
        parse_mode="Markdown"
    )


# ══════════════════════════════════════════════════════════════
#  FREE FEATURE 6 — STOCK SCANNER
# ══════════════════════════════════════════════════════════════

ALL_SCAN_STOCKS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
    "HINDUNILVR.NS","SBIN.NS","BHARTIARTL.NS","KOTAKBANK.NS","ITC.NS",
    "LT.NS","AXISBANK.NS","ASIANPAINT.NS","MARUTI.NS","WIPRO.NS",
    "ULTRACEMCO.NS","TITAN.NS","SUNPHARMA.NS","BAJFINANCE.NS","HCLTECH.NS",
    "POWERGRID.NS","NTPC.NS","TECHM.NS","ONGC.NS","TATASTEEL.NS",
    "HINDALCO.NS","JSWSTEEL.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS",
]

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan stocks by filter: /scan rsi_low | rsi_high | breakout | volume"""
    filter_type = context.args[0].lower() if context.args else "rsi_low"
    valid = ["rsi_low","rsi_high","breakout","volume","52w_high","52w_low"]
    if filter_type not in valid:
        await update.message.reply_text(
            f"📡 *Stock Scanner*\n\nUsage: `/scan FILTER`\n\n"
            f"*Available filters:*\n"
            f"`/scan rsi_low` — RSI below 35 (oversold)\n"
            f"`/scan rsi_high` — RSI above 65 (overbought)\n"
            f"`/scan breakout` — 5-day high breakout\n"
            f"`/scan volume` — Volume 2x+ average\n"
            f"`/scan 52w_high` — Near 52-week high\n"
            f"`/scan 52w_low` — Near 52-week low",
            parse_mode="Markdown"
        )
        return

    filter_labels = {
        "rsi_low": "RSI Oversold (<35)", "rsi_high": "RSI Overbought (>65)",
        "breakout": "5-Day Breakout", "volume": "High Volume (2x+)",
        "52w_high": "Near 52W High", "52w_low": "Near 52W Low",
    }
    msg = await update.message.reply_text(
        f"📡 Scanning {len(ALL_SCAN_STOCKS)} stocks for *{filter_labels[filter_type]}*...\n"
        f"_Takes ~30 seconds_",
        parse_mode="Markdown"
    )

    results = []
    for ticker in ALL_SCAN_STOCKS:
        try:
            df, _ = fetch_data([ticker], "3mo", "1d")
            if df is None or len(df) < 20:
                continue
            c = df["Close"]
            h = df["High"]
            l = df["Low"]
            v = df["Volume"]
            px   = float(c.iloc[-1])
            prev = float(c.iloc[-2])
            pct  = (px - prev) / prev * 100
            name = ticker.replace(".NS","")

            if filter_type == "rsi_low":
                rv = float(rsi_series(c).iloc[-1])
                if rv < 35:
                    results.append((name, f"RSI: `{rv:.1f}`", pct))

            elif filter_type == "rsi_high":
                rv = float(rsi_series(c).iloc[-1])
                if rv > 65:
                    results.append((name, f"RSI: `{rv:.1f}`", pct))

            elif filter_type == "breakout":
                high5 = float(h.iloc[-6:-1].max())
                if px > high5:
                    results.append((name, f"Broke {high5:,.0f}", pct))

            elif filter_type == "volume":
                avg_v = float(v.tail(20).mean())
                last_v = float(v.iloc[-1])
                ratio = last_v / avg_v if avg_v > 0 else 0
                if ratio >= 2.0:
                    results.append((name, f"Vol: `{ratio:.1f}x` avg", pct))

            elif filter_type == "52w_high":
                high52 = float(h.max())
                if px >= high52 * 0.98:
                    results.append((name, f"52W High: `{high52:,.0f}`", pct))

            elif filter_type == "52w_low":
                low52 = float(l.min())
                if px <= low52 * 1.02:
                    results.append((name, f"52W Low: `{low52:,.0f}`", pct))

        except Exception as e:
            logger.warning(f"Scan error {ticker}: {e}")

    if not results:
        await msg.edit_text(
            f"📡 *Scan: {filter_labels[filter_type]}*\n\n"
            f"No stocks matched this filter right now.\n"
            f"Try a different filter or check during market hours.",
            parse_mode="Markdown"
        )
        return

    results.sort(key=lambda x: -x[2])
    lines = [
        f"📡 *Scan: {filter_labels[filter_type]}*",
        f"🕐 `{datetime.now(IST).strftime('%d %b %Y %I:%M %p IST')}`",
        f"Found *{len(results)}* stocks\n━━━━━━━━━━━━━━━━━━━━\n",
    ]
    for name, detail, pct in results[:12]:
        e = "🟢" if pct >= 0 else "🔴"
        lines.append(f"{e} *{name}* — {detail} ({pct:+.2f}%)")

    lines.append(f"\n_Use /analyze TICKER.NS for full analysis_")
    lines.append(f"_⚠️ Not SEBI advice. Scan is for discovery only._")
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")


if __name__ == "__main__":
    main()
