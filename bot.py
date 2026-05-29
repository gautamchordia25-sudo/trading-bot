"""
==============================================
  AI Trading Assistant - Telegram Bot
  Powered by Claude AI + Yahoo Finance
==============================================
"""

import os
import json
import logging
from datetime import datetime
import yfinance as yf
import anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_API_KEY")

# ─── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── ANTHROPIC CLIENT ─────────────────────────────────────────────────────────
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# In-memory user watchlists (use a DB for production)
user_watchlists = {}

# ─── SYSTEM PROMPT ────────────────────────────────────────────────────────────
TRADING_SYSTEM_PROMPT = """You are an expert AI trading assistant specializing in both Indian markets (NSE/BSE) 
and global markets. You provide clear, actionable insights based on real stock data.

Your capabilities:
- Technical analysis (moving averages, RSI, volume trends)
- Fundamental analysis (PE ratio, market cap, earnings)
- News sentiment interpretation
- Risk assessment and position sizing advice
- Portfolio review and rebalancing suggestions

Guidelines:
- Always mention key risks alongside any recommendation
- Use simple language; avoid excessive jargon
- Format responses with emojis for readability (📈 📉 ⚠️ ✅)
- Include a brief summary at the end of every analysis
- Always add a disclaimer that this is not SEBI-registered financial advice
- For Indian stocks, use NSE ticker format (e.g., RELIANCE.NS, TCS.NS, INFY.NS)
- For US stocks, use standard format (e.g., AAPL, TSLA, NVDA)

Always structure your analysis as:
1. 📊 Current Status
2. 📈 Technical Signals
3. 🧠 Key Insights
4. ⚠️ Risks to Watch
5. 💡 Summary & Suggestion
"""

# ─── HELPER: FETCH STOCK DATA ─────────────────────────────────────────────────
def get_stock_data(ticker: str) -> dict | None:
    """Fetch comprehensive stock data from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Get recent price history (30 days)
        hist = stock.history(period="1mo")
        if hist.empty:
            return None

        current_price = hist["Close"].iloc[-1]
        prev_price = hist["Close"].iloc[-2] if len(hist) > 1 else current_price
        change_pct = ((current_price - prev_price) / prev_price) * 100

        # Simple moving averages
        ma7 = hist["Close"].tail(7).mean()
        ma20 = hist["Close"].tail(20).mean() if len(hist) >= 20 else None

        # Volume analysis
        avg_volume = hist["Volume"].mean()
        last_volume = hist["Volume"].iloc[-1]

        # 52-week high/low
        week52_high = info.get("fiftyTwoWeekHigh", "N/A")
        week52_low = info.get("fiftyTwoWeekLow", "N/A")

        return {
            "ticker": ticker.upper(),
            "name": info.get("longName", ticker),
            "current_price": round(current_price, 2),
            "change_pct": round(change_pct, 2),
            "currency": info.get("currency", "USD"),
            "market_cap": info.get("marketCap", "N/A"),
            "pe_ratio": info.get("trailingPE", "N/A"),
            "eps": info.get("trailingEps", "N/A"),
            "52w_high": week52_high,
            "52w_low": week52_low,
            "ma7": round(ma7, 2),
            "ma20": round(ma20, 2) if ma20 else "N/A",
            "avg_volume": int(avg_volume),
            "last_volume": int(last_volume),
            "volume_ratio": round(last_volume / avg_volume, 2) if avg_volume > 0 else "N/A",
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
        }
    except Exception as e:
        logger.error(f"Error fetching {ticker}: {e}")
        return None


def format_number(n) -> str:
    """Format large numbers (e.g., 1.2B, 450M)."""
    if n == "N/A" or n is None:
        return "N/A"
    try:
        n = float(n)
        if n >= 1_000_000_000:
            return f"{n/1_000_000_000:.2f}B"
        elif n >= 1_000_000:
            return f"{n/1_000_000:.2f}M"
        elif n >= 1_000:
            return f"{n/1_000:.1f}K"
        return str(round(n, 2))
    except:
        return str(n)


# ─── AI ANALYSIS ──────────────────────────────────────────────────────────────
def get_ai_analysis(stock_data: dict, user_question: str = "") -> str:
    """Send stock data to Claude for analysis."""
    prompt = f"""
Analyze this stock data and provide a comprehensive trading insight:

Stock: {stock_data['name']} ({stock_data['ticker']})
Current Price: {stock_data['currency']} {stock_data['current_price']}
Today's Change: {stock_data['change_pct']}%
Market Cap: {format_number(stock_data['market_cap'])}
P/E Ratio: {stock_data['pe_ratio']}
EPS: {stock_data['eps']}
52-Week High: {stock_data['52w_high']}
52-Week Low: {stock_data['52w_low']}
7-Day MA: {stock_data['ma7']}
20-Day MA: {stock_data['ma20']}
Volume Today: {format_number(stock_data['last_volume'])} (vs avg {format_number(stock_data['avg_volume'])})
Volume Ratio: {stock_data['volume_ratio']}x average
Sector: {stock_data['sector']}
Industry: {stock_data['industry']}

{f"User's specific question: {user_question}" if user_question else ""}

Please provide a structured analysis following your guidelines.
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=TRADING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ─── COMMAND HANDLERS ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message."""
    keyboard = [
        [InlineKeyboardButton("📈 Analyze a Stock", callback_data="help_analyze")],
        [InlineKeyboardButton("📋 My Watchlist", callback_data="watchlist"),
         InlineKeyboardButton("🌅 Market Overview", callback_data="market_overview")],
        [InlineKeyboardButton("❓ Help", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 *Welcome to your AI Trading Assistant!*\n\n"
        f"I'm powered by Claude AI and can analyze stocks from *NSE, BSE, NYSE, NASDAQ* and more.\n\n"
        f"*What I can do:*\n"
        f"📊 `/analyze RELIANCE.NS` — Deep stock analysis\n"
        f"👁️ `/watch INFY.NS` — Add to watchlist\n"
        f"📋 `/watchlist` — See your watchlist\n"
        f"🌅 `/market` — Market overview\n"
        f"💬 Just type any question about markets!\n\n"
        f"⚠️ _Not SEBI-registered advice. For educational use only._",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyze a stock: /analyze TICKER"""
    if not context.args:
        await update.message.reply_text(
            "📌 Usage: `/analyze TICKER`\n\nExamples:\n"
            "• `/analyze RELIANCE.NS` (NSE)\n"
            "• `/analyze TCS.NS` (NSE)\n"
            "• `/analyze AAPL` (NASDAQ)\n"
            "• `/analyze TSLA` (NYSE)",
            parse_mode="Markdown"
        )
        return

    ticker = context.args[0].upper()
    user_question = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    msg = await update.message.reply_text(f"🔍 Fetching data for *{ticker}*...", parse_mode="Markdown")

    stock_data = get_stock_data(ticker)
    if not stock_data:
        await msg.edit_text(
            f"❌ Could not find data for `{ticker}`.\n\n"
            f"💡 Tips:\n• Indian stocks: add `.NS` (e.g., `INFY.NS`)\n"
            f"• BSE stocks: add `.BO` (e.g., `INFY.BO`)",
            parse_mode="Markdown"
        )
        return

    await msg.edit_text(f"🤖 Analyzing *{stock_data['name']}* with Claude AI...", parse_mode="Markdown")

    direction_emoji = "📈" if stock_data['change_pct'] >= 0 else "📉"
    header = (
        f"{direction_emoji} *{stock_data['name']}* (`{stock_data['ticker']}`)\n"
        f"💰 Price: *{stock_data['currency']} {stock_data['current_price']}*  "
        f"({'+' if stock_data['change_pct'] >= 0 else ''}{stock_data['change_pct']}%)\n"
        f"📦 Market Cap: {format_number(stock_data['market_cap'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    analysis = get_ai_analysis(stock_data, user_question)

    keyboard = [
        [InlineKeyboardButton(f"👁️ Add to Watchlist", callback_data=f"addwatch_{ticker}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{ticker}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await msg.edit_text(
        header + analysis,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add stock to watchlist: /watch TICKER"""
    if not context.args:
        await update.message.reply_text("📌 Usage: `/watch RELIANCE.NS`", parse_mode="Markdown")
        return

    ticker = context.args[0].upper()
    user_id = update.effective_user.id

    if user_id not in user_watchlists:
        user_watchlists[user_id] = []

    if ticker in user_watchlists[user_id]:
        await update.message.reply_text(f"✅ `{ticker}` is already in your watchlist!", parse_mode="Markdown")
        return

    if len(user_watchlists[user_id]) >= 10:
        await update.message.reply_text("⚠️ Watchlist full! Max 10 stocks. Use `/unwatch TICKER` to remove one.")
        return

    # Validate ticker
    stock_data = get_stock_data(ticker)
    if not stock_data:
        await update.message.reply_text(f"❌ Invalid ticker `{ticker}`. Please check and try again.", parse_mode="Markdown")
        return

    user_watchlists[user_id].append(ticker)
    await update.message.reply_text(
        f"✅ *{stock_data['name']}* (`{ticker}`) added to your watchlist!\n\n"
        f"Use /watchlist to see all your stocks.",
        parse_mode="Markdown"
    )


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's watchlist with current prices."""
    user_id = update.effective_user.id
    watchlist = user_watchlists.get(user_id, [])

    if not watchlist:
        await update.message.reply_text(
            "📋 Your watchlist is empty.\n\nAdd stocks with `/watch TICKER`\n"
            "Example: `/watch RELIANCE.NS`",
            parse_mode="Markdown"
        )
        return

    msg = await update.message.reply_text("📊 Fetching your watchlist...", parse_mode="Markdown")

    lines = ["📋 *Your Watchlist*\n━━━━━━━━━━━━━━━━━━━━\n"]
    for ticker in watchlist:
        data = get_stock_data(ticker)
        if data:
            emoji = "🟢" if data["change_pct"] >= 0 else "🔴"
            sign = "+" if data["change_pct"] >= 0 else ""
            lines.append(
                f"{emoji} *{ticker}* — {data['currency']} {data['current_price']} "
                f"({sign}{data['change_pct']}%)"
            )
        else:
            lines.append(f"⚪ *{ticker}* — Data unavailable")

    lines.append("\n_Tap a stock to analyze it:_")

    keyboard = [[InlineKeyboardButton(t, callback_data=f"analyze_{t}")] for t in watchlist]
    keyboard.append([InlineKeyboardButton("🗑️ Clear Watchlist", callback_data="clear_watchlist")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await msg.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=reply_markup)


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get a quick market overview."""
    msg = await update.message.reply_text("🌅 Fetching market overview...", parse_mode="Markdown")

    indices = {
        "Nifty 50": "^NSEI",
        "Sensex": "^BSESN",
        "S&P 500": "^GSPC",
        "NASDAQ": "^IXIC",
        "Gold": "GC=F",
        "Crude Oil": "CL=F",
    }

    lines = ["🌅 *Market Overview*\n━━━━━━━━━━━━━━━━━━━━\n"]
    for name, ticker in indices.items():
        data = get_stock_data(ticker)
        if data:
            emoji = "🟢" if data["change_pct"] >= 0 else "🔴"
            sign = "+" if data["change_pct"] >= 0 else ""
            lines.append(f"{emoji} *{name}*: {data['current_price']} ({sign}{data['change_pct']}%)")
        else:
            lines.append(f"⚪ *{name}*: Unavailable")

    lines.append(f"\n🕐 _Updated: {datetime.now().strftime('%d %b %Y, %I:%M %p IST')}_")

    await msg.edit_text("\n".join(lines), parse_mode="Markdown")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-form questions about trading/markets."""
    user_text = update.message.text.strip()
    msg = await update.message.reply_text("🤔 Thinking...", parse_mode="Markdown")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        system=TRADING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_text}]
    )

    await msg.edit_text(response.content[0].text, parse_mode="Markdown")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("analyze_"):
        ticker = data.split("_", 1)[1]
        context.args = [ticker]
        await query.message.reply_text(f"🔍 Analyzing *{ticker}*...", parse_mode="Markdown")
        update.message = query.message
        await analyze_command(update, context)

    elif data.startswith("addwatch_"):
        ticker = data.split("_", 1)[1]
        user_id = query.from_user.id
        if user_id not in user_watchlists:
            user_watchlists[user_id] = []
        if ticker not in user_watchlists[user_id]:
            user_watchlists[user_id].append(ticker)
            await query.message.reply_text(f"✅ `{ticker}` added to your watchlist!", parse_mode="Markdown")
        else:
            await query.message.reply_text(f"✅ `{ticker}` is already in your watchlist.", parse_mode="Markdown")

    elif data == "clear_watchlist":
        user_watchlists[query.from_user.id] = []
        await query.edit_message_text("🗑️ Watchlist cleared!")

    elif data == "watchlist":
        update.message = query.message
        update.effective_user = query.from_user
        await watchlist_command(update, context)

    elif data == "market_overview":
        update.message = query.message
        await market_command(update, context)

    elif data.startswith("refresh_"):
        ticker = data.split("_", 1)[1]
        context.args = [ticker]
        update.message = query.message
        await analyze_command(update, context)

    elif data == "help":
        await query.message.reply_text(
            "📖 *Commands:*\n\n"
            "`/analyze TICKER` — Full AI stock analysis\n"
            "`/watch TICKER` — Add to watchlist\n"
            "`/unwatch TICKER` — Remove from watchlist\n"
            "`/watchlist` — View all watchlist stocks\n"
            "`/market` — Market overview (Nifty, Sensex, S&P500)\n\n"
            "💬 Or just type any trading question!\n\n"
            "_Examples:_\n"
            "• `What is RSI and how to use it?`\n"
            "• `How to read candlestick charts?`\n"
            "• `Best sectors in India right now?`",
            parse_mode="Markdown"
        )


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("🚀 Starting AI Trading Bot...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CommandHandler("watch", watch_command))
    app.add_handler(CommandHandler("watchlist", watchlist_command))
    app.add_handler(CommandHandler("market", market_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Bot is running! Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
