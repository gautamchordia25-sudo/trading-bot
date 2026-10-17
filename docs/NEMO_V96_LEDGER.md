# Nemo v96: Ledger (and how the stock-market agent really decides)

One release, one file (`nemotron_bot.py`, version 96.0). It answers three questions from the owner's screenshot of the day-end card (`STOCK-MARKET AGENT - DAY-END REPORT`, SHADOW mode, one NIFTY put, +₹2,918):

1. **How do I see its ledger or complete report?** → say **`ledger`** (new). Until now there was no way: the day-end card shows *today's trades only*.
2. **What are its logic and rules?** → say **`ledger logic`** (plain words, checked against the code by tests), and section 2 below (what I found when I read it).
3. **How can more features be added?** → section 4 (a ranked list; nothing in it is built yet except the ledger).

The ledger is **read-only**. It never places, changes or simulates an order, never changes what the agent does, and never touches the trading guards (holiday guard, entry window 09:20–14:30, daily loss limit), the owner lock, any credential or any setting of the agent. The one thing it adds to the agent's tick is a *look at the agent's state afterwards*; if that look fails, the agent is not affected (tested).

---

## 1. Seeing the record (owner only; say it to Nemo, `/ledger` also works)

| Say | You get |
|---|---|
| `ledger` | The summary in plain words: trades, wins/losses, result **before and after estimated charges**, average win and loss, best/worst trade, up/down days, **worst dip from a high point**, the win rate the agent needs just to break even at its own average win and loss, and a **"how much to trust it"** block (see below). Virtual (shadow) and real (live) results are always shown separately, never mixed. |
| `ledger today` / `week` / `month` / `30 days` | The same for a period. |
| `ledger days` | Day by day with a running total (aligned table). |
| `ledger trades` | The last 15 trades as a table. |
| `ledger trade 3` (or `ledger last`) | One trade in full: contract and expiry, entry and exit prices and times, how it ended, time held, days to expiry, the stop and target it planned, the maximum it could lose, the charges, and **the agent's own reason** ("AI NIFTY: … (conf 7/10)"). |
| `ledger breakdown` | What worked and what did not: by distance to expiry, call or put, how the trade ended, index or share, which brain chose it. (Needs 3 trades, and says that small counts are noise.) |
| `ledger csv` | A spreadsheet file of every trade (opens in Excel; text cells that could run as a formula are neutralised). |
| `ledger chart` | A growth chart of the result after charges, one dot per trade. |
| `ledger logic` | How the agent decides (section 2). |
| `ledger costs` | The charges used, and how to change them (`ledger costs stt_opt 0.1`, `ledger costs off`, `ledger costs reset`). |
| `ledger live` / `ledger virtual` | Pick one mode. |

Natural phrasing also works: "show my paper ledger", "full paper trading report", "how is the paper agent doing", "how does the shadow agent decide". A sentence that merely contains the word ("the ledger is balanced") is **not** taken: only sentences made of ledger words are.

The **day-end card** (15:45) is unchanged; when it had trades, **one extra line** follows: the running total, the win rate, the worst dip, and "only N trades so far: too few to judge" until there are 30.

### "How much to trust it" (the part the old card never had)

- **Win-rate range.** A win rate measured on few trades is unreliable. The ledger gives the 95% range (Wilson interval): 1 win in 1 trade = 100% on the card, but "could really be anywhere from 21% to 100%". After 30 trades it switches to a measured range and says whether even the low end is above the break-even rate.
- **Break-even.** With a stop at −30% and a target at +50% of the option price, the agent needs about **38%** winning trades before charges (a little more after). A low bar on paper; the ledger computes the real one from your own average win and loss.
- **Charges.** The old card shows gross profit. The ledger subtracts an *estimate* of brokerage, STT, exchange and SEBI fees, stamp duty and GST. For the screenshot trade (65 units bought at 77.80, sold at 122.70) that is **about ₹65**. The rates are editable because they change.
- **Flags:** how many trades were bought on expiry day or the day before; whether one day made most of the profit; the longest run of losing trades.
- **Virtual honesty:** shadow trades are bought at the ask and sold at the bid (so the spread *is* counted), but real orders can fill later or partly, and the agent only looks at prices about every 2 minutes, so real results usually come out a little worse.

### What is stored, and what could not be recovered

`AUTOLOG` (the agent's own list) keeps only the last **500** trades and never stored the **entry time, stop or target**. The ledger copies every closed trade once into Nemo's database (so nothing is lost after 500), and from the first tick after this version runs it notes the entry time, stop, target and reason the moment a position opens. Trades closed *before* this version have no entry time (the ledger says "not recorded"). Rows the agent writes to clear an old shadow position (`stale-shadow-reconciled`) are not trades: the old day-end card counts them as losses, the ledger does not count them at all.

---

## 2. How the agent decides (read from the code, not guessed)

*Where:* `auto_trade_tick` (the loop), `ai_decide` (the AI brain), `godmode_analyze` (the score), `_n81_entry_quote` / `_n81_session` (the safety gates), `index_atm_option` (the contract).

**When it looks.** Monday–Friday, about every **2 minutes** (the scheduler wakes every 60 s and ticks every second wake) from 09:15 to 15:35, only on days the NSE calendar lists as open. New trades only **09:20–14:30**; never while entries are paused, in master lockdown, after the daily loss limit (default ₹3,000), or beyond the daily trade limit (default **1**).

**What it looks at.** For NIFTY, BANKNIFTY and SENSEX a score from −6 to +6 from **daily** candles (price against its 20- and 50-day averages, the slope of the 20-day average, RSI(14), MACD momentum, nearness to a 3-month high/low).
- **AI brain (the default; the screenshot says `Brain: ai`):** the AI gets those scores, today's news, FII/DII flows, the owner's watchlist, and the agent's own last 45 days (once it has 6 trades). It answers one JSON line: buy a call, buy a put, buy a watchlist share, or nothing. It must be **at least 6/10 sure**; its instructions say "nothing" is usually the right answer.
- **GODMODE brain (fixed rules):** takes the strongest of the three scores and trades only if it is 4 or more, up or down.

**What it buys.** The at-the-money call (bullish) or put (bearish) from the broker's option chain, one lot (NIFTY 65 units). Buy only. **It does not choose the expiry:** the chain request has no expiry parameter, so it takes whatever the broker returns first, the nearest. Before buying it re-checks the quote: under 30 s old, buy-sell gap ≤ 2%, enough quantity offered, price within 1% of the decision, and the most the trade can lose must fit inside what is left of the day's loss limit. Virtual trades are bought at the **ask**.

**When it sells.** Stop-loss **−30%**, target **+50%** (of the *option's* price, not the index), or square-off at **15:10**, whichever first. Checked about every 2 minutes; the sale is booked at the price seen at that check (virtual sales use the **bid**), which is why the screenshot target (116.70) was booked at 122.70. In live mode with brackets on, the stop and target also sit at the exchange.

**Tests keep the explanation honest.** `ledger logic` is generated from the live settings, and a test checks 22 of its claims against the exact lines of the source. If someone changes the agent, that test fails until the explanation is updated.

---

## 3. What I found (for you to decide on; nothing was changed)

These are observations about the *existing* agent. I did not change any of them: they change what it trades, so they are your decision.

1. **The score uses daily candles only.** The AI is told the trend of recent months, not what the price did this morning. The closing message in the screenshot says "watch whether the opening range breaks and holds"; the agent itself does not look at the opening range, intraday trend, VWAP or the India VIX when entering.
2. **Nearest expiry, whatever the day.** The screenshot contract (`NIFTY26O0622550PE`) expires on 06 Oct; it was bought on 05 Oct, one day before expiry. Options that close to expiry gain and lose value very fast in both directions. A run of profits on them says little about skill. The ledger shows this (it flags expiry-day and day-before trades and breaks results down by distance to expiry).
3. **One trade a day means a slow, noisy record.** 30 trades is about six weeks. A win rate seen on 10 trades could easily be luck either way. Break-even is only about 38%, so a 60% win rate over a few weeks is not unusual by chance alone.
4. **Costs were not in the numbers.** The card and the daily-loss limit use gross profit. About ₹65 per round trip is small next to ₹2,918, but it adds up, and on a flat day it turns a "win" into a loss.
5. **Checks every 2 minutes.** A fast move can jump past the stop or the target; the booked price is whatever the quote showed at the check. The virtual fills can be better or worse than a real order for the same reason.
6. **The old day-end card counts a breakeven as a loss** and counts agent bookkeeping rows as losses; the ledger does neither.
7. **I cannot see your history.** I only have the one screenshot. "Making profits daily" is what you observe; I have not seen the record and cannot confirm or deny it. `ledger` will show it, with the honest range.

---

## 4. How more features could be added (ranked; none built yet)

**A. Measure more (read-only: the agent behaves exactly as now) — recommended next, as v97 "Lab"**
1. **A/B shadow strategies:** run several *virtual* variants in parallel on the same signals (for example: as now; skip contracts with fewer than 2 days to expiry; stop/target −25%/+40%; break-even stop after +25%; GODMODE brain) and compare them in the ledger after the same number of trades. This is the safe way to learn what actually helps: nothing real changes.
2. **"Why not" log:** every tick where the agent chose nothing or was blocked, with the reason (AI said NONE, confidence under 6, guard blocked, premium too high). Today only the last reason is kept.
3. **Direction hit rate:** did the index move the way the agent expected between entry and exit? It separates *direction skill* from *option-price luck*.
4. **Excursion tracking:** the best and worst price each trade reached while open, to see whether −30%/+50% are sensible.
5. **Weekly and monthly auto-report** (message plus CSV and PDF), and **alerts** on a drawdown limit or a losing streak.

**B. Change the agent's behaviour (only after A shows it helps; each in shadow first)**
1. Expiry-aware contract choice (a `min days to expiry` setting).
2. Intraday confirmation: opening range, VWAP, 15-minute trend, India VIX filter.
3. Trailing stop or break-even stop; time exit if there is no progress.
4. Event-day filter (results, RBI, budget, expiry) using the v94 Scout intel.
5. Virtual results *after* charges and slippage, so the daily-loss limit uses net numbers.
6. Position sizing from the loss budget instead of a fixed one lot.

**C. A promotion gate before `live`:** Nemo refuses `/autotrade live` unless the shadow ledger has, say, at least 60 trades, a positive result after charges, a low end of the win-rate range above break-even and a worst dip under a limit you set (you can still override by an explicit phrase). The ledger already computes every one of those numbers.

---

## 5. What was verified, and what was not

**Verified offline (automated tests, 78 new):**
- the charge maths against hand calculation for the screenshot trade, share vs option rates, switching charges off, bad saved settings;
- win rate range (known Wilson values), expiry parsing of weekly symbols (including Jan, Nov, Dec codes and impossible dates), money in Indian grouping;
- every number in a known set of trades (win rate, averages, break-even, profit factor, worst dip, current dip, streaks, running totals, groups);
- the archive (once each, survives the agent's 500-trade cut, bad rows skipped, a broken database never raises), entry notes joined only to the same contract, price, mode and an earlier time;
- the **real** agent tick running for real (broker, quote and calendar stubbed): a virtual NIFTY put at 77.80 reaches its target, the real code books +₹2,918.50 into `AUTOLOG`, the ledger archives it with its entry time, stop, target and hold time, and no broker function is called;
- that the tick wrapper passes the agent's result and errors through unchanged, and that a failing look never disturbs the agent; that the look changes nothing in the agent's state (compared before and after);
- the day-end card is unchanged, the extra line follows only when there were trades;
- CSV (header, order, formula neutralised, temp file removed), chart (PNG), all views and edge cases, the front door (16 ledger phrases, 6 logic phrases, 9 non-ledger sentences passed on, guests/groups/files not taken);
- structure: the layer contains no broker call, no network call, no AI call, no write into the agent's state or log, and only its own three tables; the explanation's claims match 22 exact lines of the source.

**Not verified (cannot be from the test machine):**
- **Your real history.** The ledger has never read your server's `AUTOLOG`; the first `ledger` after the update will import what is there (up to 500 trades).
- **Telegram delivery** of the aligned tables, the CSV file and the chart image (tested up to the Telegram call).
- **The charge rates.** The brokerage (₹20 per executed order) and the rates (STT 0.15% on the sell side of options since 1 April 2026, exchange charge 0.03503%, stamp 0.003%, SEBI ₹10 per crore, GST 18%) come from public pages I could read (ICICI Direct, Groww and others on the 2026 STT change; Chittorgarh's summary of Fyers' list). The broker's own page was not reachable from the test machine. Check against a contract note, and edit with `ledger costs` if they differ.
- That **no order** is placed was verified only for the ledger code and in the tests; nothing here can say what a real broker would do.

## 6. Try it, through Nemo

1. `ledger`: the whole record. Then `ledger days`, `ledger trades`, `ledger trade 1`.
2. `ledger logic`: how the agent decides.
3. `ledger csv` and `ledger chart` (the chart needs 2 or more trades).
4. `ledger costs`: check the charges against a contract note; change any that differ.
5. Wait for the 15:45 card: one extra line with the running total follows it.

## 7. What changed in older code (everything else is in the new layer, marker `# NEMO 96 - LEDGER`)

1. The docstring, `VERSION`, and `'_n96_'` in the live-self-edit protection list.
2. Wrapped (the old ones kept and called): `auto_trade_tick` (observer only, after the agent's own tick), `trading_day_report` (one extra line after it), `handle`, `main`, and the status, capabilities, abilities and regression-suite functions.

Tests: `tests/test_ledger96.py`. The v95 structural tests now stop at the v96 marker, and one v95 docstring check was relaxed the way the v94 one was.

## 8. Test results (offline, on the test machine)

- **Whole suite: 2,340 tests, 0 failures, 6 skipped** (the slow gate switched on), run on the exact file delivered. 78 of them are new (`tests/test_ledger96.py`).
- Pyflakes: the same 158 messages as v95, none new. Credential comparison against v95: no change to any saved credential. A scan of the added lines for keys, tokens or passwords found none.
- Nothing here placed, changed or simulated an order, called a broker, or used a paid service.
