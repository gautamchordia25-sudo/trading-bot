import os
import logging
from datetime import datetime
import yfinance as yf
import anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

user_watchlists = {}

SYSTEM_PROMPT = """You are an expert AI trading assistant for Indian (NSE/BSE) and global markets.
Analyze stocks and give clear, actionable insights.
Always structure your response with these sections:
📊 Current Status
📈 Technical Signals  
🧠 Key Insights
⚠️ Risks
💡 Summary

Use emojis for readability. Always end with: ⚠️ Not SEBI-registered advice. Educational only."""


def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1mo")
        if hist.empty:
            return None
        info = stock.info
        current = round(float(hist["Close"].iloc[-1]), 2)
        prev = round(float(hist["Close"].iloc[-2]), 2) if len(hist) > 1 else current
        change = round(((current - prev) / prev) * 100, 2)
        ma7 = round(float(hist["Close"].tail(7).mean()), 2)
        ma20 = round(float(hist["Close"].tail(20).mean()), 2) if len(hist) >= 20 else None
        avg_vol = int(hist["Volume"].mean())
        last_vol = int(hist["Volume"].iloc[-1])
        return {
            "ticker": ticker.upper(),
            "name": info.get("longName", ticker),
            "price": current,
            "change": change,
            "currency": info.get("currency", "USD"),
            "market_cap": info.get("marketCap", "N/A"),
            "pe": info.get("trailingPE", "N/A"),
            "high52": info.get("fiftyTwoWeekHigh", "N/A"),
            "low52": info.get("fiftyTwoWeekLow", "N/A"),
            "ma7": ma7,
            "ma20": ma20 or "N/A",
            "avg_vol": avg_vol,
            "last_vol": last_vol,
            "vol_ratio": round(last_vol / avg_vol, 2) if avg_vol > 0 else "N/A",
            "sector": info.get("sector", "N/A"),
        }
    except Exception as e:
        logger.error(f"Stock fetch error {ticker}: {e}")
        return None


def fmt(n):
    try:
        n = float(n)
        if n >= 1e9: return f"{n/1e9:.2f}B"
        if n >= 1e6: return f"{n/1e6:.2f}M"
        if n >= 1e3: return f"{n/1e3:.1f}K"
        return str(round(n, 2))
    except:
        return str(n)


def ai_analyze(data, question=""):
    prompt = f"""Analyze this stock:
Name: {data['name']} ({data['ticker']})
Price: {data['currency']} {data['price']} ({data['change']:+}%)
Market Cap: {fmt(data['market_cap'])}
P/E Ratio: {data['pe']}
52W High: {data['high52']} | Low: {data['low52']}
7-Day MA: {data['ma7']} | 20-Day MA: {data['ma20']}
Volume: {fmt(data['last_vol'])} (ratio: {data['vol_ratio']}x avg)
Sector: {data['sector']}
{f"User question: {question}" if question else ""}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📈 Analyze Stock", callback_data="help_analyze")],
        [InlineKeyboardButton("📋 My Watchlist", callback_data="watchlist"),
         InlineKeyboardButton("🌅 Market Overview", callback_data="market")],
    ]
    await update.message.reply_text(
        "👋 *Welcome to your AI Trading Assistant!*\n\n"
        "Powered by Claude AI for NSE, BSE, NYSE & NASDAQ\n\n"
        "*Commands:*\n"
        "📊 `/analyze RELIANCE.NS` — Stock analysis\n"
        "👁 `/watch INFY.NS` — Add to watchlist\n"
        "📋 `/watchlist` — Your watchlist\n"
        "🌅 `/market` — Market overview\n\n"
        "💬 Or just type any market question!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: `/analyze TICKER`\n\nExamples:\n`/analyze RELIANCE.NS`\n`/analyze TCS.NS`\n`/analyze AAPL`",
            parse_mode="Markdown"
        )
        return

    ticker = context.args[0].upper()
    question = " ".join(context.args[1:])
    msg = await update.message.reply_text(f"🔍 Fetching *{ticker}*...", parse_mode="Markdown")

    data = get_stock_data(ticker)
    if not data:
        await msg.edit_text(
            f"❌ Could not find `{ticker}`\n\n💡 Indian stocks need `.NS` (e.g. `INFY.NS`)",
            parse_mode="Markdown"
        )
        return

    await msg.edit_text(f"🤖 Analyzing *{data['name']}* with Claude AI...", parse_mode="Markdown")

    emoji = "📈" if data['change'] >= 0 else "📉"
    header = (
        f"{emoji} *{data['name']}* (`{data['ticker']}`)\n"
        f"💰 {data['currency']} *{data['price']}*  ({data['change']:+}%)\n"
        f"📦 Market Cap: {fmt(data['market_cap'])}\n"
        f"━━━━━━━━━━━━━━━━\n\n"
    )

    analysis = ai_analyze(data, question)
    kb = [
        [InlineKeyboardButton("👁 Add to Watchlist", callback_data=f"addwatch_{ticker}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{ticker}")]
    ]
    await msg.edit_text(header + analysis, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text("⚠️ Watchlist full (max 10). Remove one first.")
        return
    data = get_stock_data(ticker)
    if not data:
        await update.message.reply_text(f"❌ Invalid ticker `{ticker}`", parse_mode="Markdown")
        return
    user_watchlists[uid].append(ticker)
    await update.message.reply_text(f"✅ *{data['name']}* added to watchlist!", parse_mode="Markdown")


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    wl = user_watchlists.get(uid, [])
    if not wl:
        await update.message.reply_text(
            "📋 Watchlist is empty.\n\nAdd stocks with `/watch TICKER`",
            parse_mode="Markdown"
        )
        return
    msg = await update.message.reply_text("📊 Loading watchlist...", parse_mode="Markdown")
    lines = ["📋 *Your Watchlist*\n━━━━━━━━━━━━━━━━\n"]
    for t in wl:
        d = get_stock_data(t)
        if d:
            e = "🟢" if d["change"] >= 0 else "🔴"
            lines.append(f"{e} *{t}* — {d['currency']} {d['price']} ({d['change']:+}%)")
        else:
            lines.append(f"⚪ *{t}* — Unavailable")
    kb = [[InlineKeyboardButton(t, callback_data=f"analyze_{t}")] for t in wl]
    kb.append([InlineKeyboardButton("🗑 Clear All", callback_data="clear_watchlist")])
    await msg.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🌅 Fetching market data...", parse_mode="Markdown")
    indices = {"Nifty 50": "^NSEI", "Sensex": "^BSESN", "S&P 500": "^GSPC",
               "NASDAQ": "^IXIC", "Gold": "GC=F", "Crude Oil": "CL=F"}
    lines = ["🌅 *Market Overview*\n━━━━━━━━━━━━━━━━\n"]
    for name, ticker in indices.items():
        d = get_stock_data(ticker)
        if d:
            e = "🟢" if d["change"] >= 0 else "🔴"
            lines.append(f"{e} *{name}*: {d['price']} ({d['change']:+}%)")
        else:
            lines.append(f"⚪ *{name}*: Unavailable")
    lines.append(f"\n🕐 _{datetime.now().strftime('%d %b %Y, %I:%M %p IST')}_")
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🤔 Thinking...", parse_mode="Markdown")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": update.message.text}]
    )
    await msg.edit_text(response.content[0].text, parse_mode="Markdown")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("analyze_") or data.startswith("refresh_"):
        ticker = data.split("_", 1)[1]
        context.args = [ticker]
        update.message = query.message
        await analyze(update, context)

    elif data.startswith("addwatch_"):
        ticker = data.split("_", 1)[1]
        uid = query.from_user.id
        if uid not in user_watchlists:
            user_watchlists[uid] = []
        if ticker not in user_watchlists[uid]:
            user_watchlists[uid].append(ticker)
            await query.message.reply_text(f"✅ `{ticker}` added to watchlist!", parse_mode="Markdown")
        else:
            await query.message.reply_text(f"✅ `{ticker}` already in watchlist.", parse_mode="Markdown")

    elif data == "clear_watchlist":
        user_watchlists[query.from_user.id] = []
        await query.edit_message_text("🗑 Watchlist cleared!")

    elif data == "watchlist":
        update.message = query.message
        update.effective_user = query.from_user
        await watchlist(update, context)

    elif data == "market":
        update.message = query.message
        await market(update, context)

    elif data == "help_analyze":
        await query.message.reply_text(
            "Send: `/analyze TICKER`\n\nExamples:\n`/analyze RELIANCE.NS`\n`/analyze TCS.NS`\n`/analyze AAPL`",
            parse_mode="Markdown"
        )


def main():
    print("🚀 Starting AI Trading Bot...")
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set!")
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set!")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("watch", watch))
    app.add_handler(CommandHandler("watchlist", watchlist))
    app.add_handler(CommandHandler("market", market))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Bot is running!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
