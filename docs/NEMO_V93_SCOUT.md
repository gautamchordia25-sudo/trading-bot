# Nemo v93.1 "Scout": trade ideas for stocks and NIFTY options from news and market tools, with the logic shown

> **v93.1** (the same day): you ran `/chain55 NIFTY` on your server and pasted the result. It was the first real data Scout met, and it showed two things my fixtures did not have:
> **(1)** the broker's chain sends **no implied volatility** (`"iv": null` on every row), and Scout's option plan needs it for Greeks and repricing, so NIFTY option ideas would never have appeared;
> **(2)** every expiry **timestamp was null**, because the older v55 parser dropped an epoch the broker sends as text, so Scout could not load the next expiry when the nearest was two days away.
> Fixed: Scout now **solves the implied volatility from each option's own price** (same Black-Scholes conventions as the bot's Greeks helper; rows that do come with a volatility are left alone; results outside 3-150% are not
> trusted) and says so on the card; the v55 expiry parser now keeps a text epoch, and where the feed gives none the next expiry is found from its date. Tested on eight of your real rows (they give volatilities of
> about 21-31%, believable for the day) and on a chain built without volatility. It still has not seen a live *plan* on your data: that needs a market session, so run `scout nifty` and tell me what it says.

You asked for Nemo to give trades for stocks and NIFTY options from news analysis and his market tools, using proper logic, and to be a smarter, more powerful Nemo
(no domain yet, storage can be resized, and Nemo will be for everyone later). Everything from v92 (Wire) and earlier is kept. Your credentials, owner lock, trading and holiday guards,
existing permissions and approvals, backup and rollback are untouched.

## 0. Read this first (the honest version)

* **Scout gives ideas. It never places, changes or simulates an order**, never touches the autonomous trading agent (`/autotrade`), the paper ledger, the broker connection, the trading
  guards or the owner lock. You place any order yourself. A test parses the whole layer and fails if it ever names an order function or those objects.
* **I cannot prove these rules make money, and neither can anyone from an armchair.** What I can do, and did, is make every idea show its workings, size it to your own risk limit, refuse weak
  setups, and **measure Scout's real record from now on** (`scout stats`). Until that record has 30+ settled ideas, treat the ideas as a structured second opinion, not as signals.
* **Options buying is hard to win.** SEBI's own studies of individual F&O traders (2023 and 2024) found that roughly nine in ten lost money (from memory: I could not fetch the studies from my
  sandbox). That is why Scout prefers debit spreads when options are expensive, refuses buy ideas in the last day before expiry, checks the break-even against the move the options themselves
  expect, and tells you the **real money risk of one lot** before anything else.
* **Not run against any live source.** From my build sandbox Google News, Yahoo, NSE, and the broker are unreachable, so every test uses fixtures. Section 8 lists exactly what is verified and
  what you will be the first to see.

## 1. What I found first (by reading the v92 file)

1. **News was only forwarded.** `check_news()` (the "radar") asks the AI whether a headline is big and forwards it. Nothing read headlines into structured facts, nothing tied a headline to a stock,
   and nothing asked whether the price had reacted.
2. **A big market toolbox existed but nothing joined it.** v55 has candles from the broker with a public fallback, regimes, structure, option chain, OI, Greeks, IV, expected move, sector rotation.
   There was no step that turned them into one reasoned idea.
3. **The autonomous options agent has no logic about the trade itself.** It enters on a score (or an AI answer) and fixes the stop and target at **-30% / +50% of the premium** whatever the
   market is doing. I left it exactly as it is (section 9) and built the reasoning beside it.
4. **Two traps for a small account**: a NIFTY lot is 65 units; one lot with a sensible stop risks several thousand rupees. Ideas that cannot fit your risk limit must say so, not round up.

## 2. How an idea is made

```
headlines (Google News feed → dated search → plain search)        ─┐
   → one story per event (same story from 3 outlets = 1 story + 3 sources; two different companies never merge)
   → read into facts by the AI chain (event, direction -2..2, size 1..5, new or old, confidence), whitelisted,
     or by plain rules when the AI is down                         ─┤  the AI never decides a trade
   → one signal per stock / for the market: direction, strength, conflict, flags (results due, policy due)
                                                                    │
daily candles → trend, momentum, volume, structure, swings, ATR     ├→ setups → levels → score table → gates → size → card → ledger → followed on later candles
NIFTY trend, India VIX, sector strength vs NIFTY                    │
option chain (OI, PCR, walls, IV, Greeks) for NIFTY / BANKNIFTY    ─┘
```

**News is a catalyst, not a trigger.** A story with no price reaction, volume or trend behind it is a *watch*. Ideas need an aligned, fresh, reasonably reliable story **and** a setup on the chart.

### 2.1 Setups (stocks)

| Setup | Fires when | Invalidation (the stop goes just beyond it) |
|---|---|---|
| BREAKOUT / BREAKDOWN | closes beyond the 20-day high/low on volume ≥ 1.2x its average (or volume unknown), not more than 3.5 ATR from the 20-day average | the broken level or today's low/high |
| TREND_PULLBACK | 20-day average above (below) the 50-day, price near the 20-day average, RSI 38-62 | the last swing low (high) |
| NEWS_CONTINUATION | strong aligned news, price moved at least 0.4 ATR the same way, closed in the top (bottom) of the day's range, not against the 50-day average | the news-day low (high) |

Levels: stop never closer than 1 ATR and refused if the natural stop is further than 2.6 ATR; targets 1.5R and 2.5R (the first pulled in under the nearest overhead swing, and refused if that swing is
closer than 1.25R). Entry zone = the close to +0.25 ATR; a price that opens more than half an ATR above it is "chasing": skip.

### 2.2 The score (0-100, a checklist total, **not a probability**)

| Part | Points | What earns them |
|---|---|---|
| Catalyst | 0-30 | news pointing the same way x its strength (fresh, reliable outlet, confident, new information, 2+ outlets); read by plain rules counts 70% |
| Trend | 0-20 | price vs 20-day average, 20 vs 50, ADX, higher highs and lows |
| Confirmation | 0-15 | volume vs average, strength vs NIFTY over 20 days, where it closed in the day's range |
| Context | -6..15 | NIFTY trend agrees, India VIX not high and not rising, sector ahead of NIFTY |
| Risk structure | -5..20 | room to the next obstacle, a structural stop, not stretched, RSI not extreme, liquidity |
| Event | 0 or -8 | results look due soon (the price can gap through any stop) |

* **No aligned news = the score is capped at 64**, below the default issue line of 65: technical-only ideas are *watches*. Lower the line yourself with `scout config min=60` if you want to see them.
* **Vetoes (never issued):** strong news the other way, too stretched (> 3.5 ATR from the 20-day average), average daily traded value under ₹5 crore, natural stop too far, resistance too close.
* **Missing data is "not checked", never a pass:** each card lists what could not be read (volume while the day is still trading, NIFTY trend, VIX, sector).
* Bands: A 78+, B 66-77, C 55-65 (C is only shown "on the radar"). A scan issues at most your `max` ideas and at most two per sector.
* These cut-offs are my judgement, **not tuned on data**. `scout stats` will show how each band really did.

### 2.3 NIFTY / BANKNIFTY options

1. **Direction** from four reads with fixed weights: daily trend 35%, intraday structure 25%, open interest (PCR and the walls) 20%, macro news 20%. A read that cannot be made is dropped and lowers the
   confidence. An idea needs a net bias of at least +/-0.35, confidence 60%, enough reads agreeing (3 of 4, or 2 of 3) and no strong contradiction.
2. **Expiry:** under one day left → no buy idea; under 2.5 days → the next expiry is used.
3. **A plan on the index first** (same level rules as stocks, on the daily ATR): invalidation level, first target. If the target is more than 1.3x the move the options expect by expiry → no idea.
4. **Structure from volatility** (India VIX percentile of its own recent range, as a proxy for NIFTY implied volatility):

| VIX percentile | Preferred | Why |
|---|---|---|
| 70 or more | **debit spread** (long ATM-ish, short at about the first target) | dear options punish an outright buy when volatility falls |
| 30 or less and 3+ days to expiry | **buy the option** (delta nearest 0.55 among liquid strikes) | options are cheap, time decay is slow |
| in between / unknown | the outright option if it pays at least 1.5 to 1 with moderate time decay, otherwise the spread; the other is shown as an alternative when it also pays | |

5. **The premium plan is computed, not guessed:** the option is repriced with the bot's own Black-Scholes helper at the stop and at the first target (one day of decay assumed). The premium stop is the
   tighter of that and **-40% of the premium**. Contracts with a spread over 3% are skipped. A plan needs reward to risk of at least 1.4, time decay under 12% of the premium a day and a break-even
   within 90% of the expected move.
6. **Size:** lots = your risk amount divided by the real per-lot risk, rounded **down**. If that is zero the card says: *"0 lots at your ₹1,000 limit. One lot really risks ₹X (Y% of your capital)."*
   With the default ₹1,00,000 and 1% that is most NIFTY ideas: say `scout config capital=...` and `risk=...` honestly.
7. A policy decision looking due (RBI, Fed, budget) in the news costs 8 points and is noted: the index can gap and option prices can fall even when the direction is right.

## 3. Commands (owner only, private chat; natural language works)

| You say | What happens |
|---|---|
| `trade ideas` · `scout` · `any good trades today?` · `what to buy` | full scan: news, market, your watch-list, the scanner's leaders and laggards, stocks the news names, and NIFTY/BANKNIFTY options; cards for what passes; a short "why not" for what did not |
| `scout RELIANCE` · `trade idea for TCS` · `should I buy INFY?` | one name: its news, its chart, an idea or the honest reasons there is none (known names only; anything else goes to the normal chat) |
| `scout nifty` · `nifty option idea` · `which banknifty option to buy` | options only |
| `scout news [RELIANCE]` | the stories and how each was read (event, direction, size, new or old), no trade logic: use it to judge the reading |
| `scout ideas` · `scout SC93-ABC123` · `scout check SC93-ABC123` · `scout drop SC93-ABC123` | open ideas; one in full; is it still valid (still in zone, chasing, weak, closed); stop following it |
| `scout stats` | the real record: by band, stocks vs options, by setup |
| `scout test RELIANCE` | replays the technical rules (no news) on the stock's daily history with the same code, one trade at a time |
| `scout config` · `scout config capital=5L risk=1% max=5 min=65 hours=24 position=25` | your numbers; Scout uses them only to size ideas |
| `scout watch add TCS INFY` · `scout alerts on` | extra names; an opt-in 08:50 scan on trading days (sends only ideas that pass; nothing otherwise) |
| `scout help` | the list |

Open ideas are followed in the background (every 10 minutes while the market is open, every 3 hours otherwise); when one settles you get one line.

## 4. The record (how Scout stays honest)

Every issued idea is saved and followed on later candles: **stop first when a candle touches both**, a gap through the stop is booked as the worse loss for stocks, the first target pays its planned R, and
at the time limit the idea closes at the last price. Option ideas are followed on the **index levels** (not on option prices, which Scout does not see after issuing), so their R is an approximation and says so.
Nothing is tuned from the record automatically (that would over-fit); you read it and decide.

## 5. What was measured offline (and what it does and does not mean)

The replay (`scout test`) uses the *same code* as live scoring and takes one trade at a time at the next open with 0.05% slippage each way. On **synthetic** markets of 700 candles, 40 runs each, final rules:

| Market | Trades | Average result | Meaning |
|---|---|---|---|
| random walk (no edge exists) | 380 | -0.01R (+/-0.11) | the replay does not invent profit: **no look-ahead leak** (a test also changes the future and checks past trades do not move) |
| momentum (returns tend to continue) | 410 | +0.11R (+/-0.11) | the rules can pick up a trend when one exists |
| mean-reverting | 333 | -0.13R (+/-0.10) | trend rules lose when moves reverse |

This says how the rules *behave*. It says **nothing** about real NIFTY or stock prices, news, or costs. Run `scout test` on your own symbols, and read `scout stats` over weeks.

## 6. Small things you may notice

* Scout reads **your own watch-list** (`/watchlist`, read-only) and its own (`scout watch`). Option contracts and indexes in a watch-list are skipped.
* It adds one entry to an older table: `INDIAVIX` in the v55 index map, so India VIX can be read like any index.
* News text is third-party: it is masked and clipped in every message, the AI's answer is checked against a whitelist (tickers, events, numbers) and nothing the AI writes is copied into an idea.
* The 2026 trading holiday table is the only calendar Nemo has (v81). Outside 2026 Scout says "calendar unverified".

## 7. Storage, domain, and "for everyone later"

* **Storage:** Scout keeps small rows in the database Nemo already uses: classified stories (about 400 bytes each, pruned after 90 days) and ideas (a few KB each). A year is tens of megabytes. Resizing the
  disk matters later for bigger archives (option-chain snapshots are already stored by the v55 tool); nothing here needs it.
* **Domain:** not needed. Nothing in Scout uses the website.
* **For everyone later:** Scout is owner-only by design, and Circle **never grants trading** to anyone. When you decide to let others see ideas, that must be a separate, deliberate step. In India, giving
  investment recommendations to others, especially for a fee or publicly, can require SEBI registration as a research analyst; I am not a lawyer, so check before offering this to anyone but yourself.

## 8. What is verified and what is not

**Verified offline (tests: 242 for Scout; whole suite on the final file 1831 OK, 6 skipped = the 5 real-library Wire tests and the slow update-gate test, which I ran separately with `NEMO_SLOW=1` and passed; your own server's in-bot regression run showed 937 passed, 0 failed):** headline feed parsing (including a feed that tries to declare entities, oversized or broken feeds), story merging (and never across different companies), the rules
reader, the AI answer whitelist and the prompt-injection defence, news weighting by age, outlet, confidence, novelty and corroboration, event flags, indicator facts, levels and gates (every branch, both
sides), setups, the score table, sizing that never rounds up, the replay (determinism, no overlap, no look-ahead, no edge on noise), stop-first following, option bias, structure choice, spread arithmetic, premium
plan, sizing with the real per-lot risk, the ledger and the record, the scan end to end (sector cap, idea cap, no news, no market data, time limit, one at a time), every chat phrase and what must *not* be taken, the
owner-only door, the morning alert, wiring, and a structural check that the layer never names an order function, the trading agent, the broker, the guards or writes the owner lock.

**Not verified live (you are the first real run):**
* **News feeds:** Google News RSS, dated search news and plain search were unreachable from my sandbox. Every parser is tested on realistic samples, but the real feeds may differ. `scout news` shows exactly what was read.
* **The AI's reading of real headlines:** tested with a scripted AI and with the plain-rules fallback, not with your providers. `scout news` shows each story's reading so you can judge it.
* **FYERS / market data / option chain:** the chain shape is now confirmed from your own `/chain55 NIFTY` output (spot, ATM, PCR, bid, ask, volume, OI present; IV and expiry epochs missing, handled as above). Candles, the 15-minute and daily history, and how the next-expiry request behaves on your broker are still unseen.
* **India VIX** through the broker or the public fallback (added as one index entry).
* **How the messages look in Telegram.**
* **Anything about profitability.** See sections 0 and 5.

## 9. The autonomous trading agent (left alone, on purpose)

The agent still enters on its own score and uses the fixed -30% / +50% premium rule. Scout does **not** feed it, change it or override it. My suggestion: keep it in `shadow` mode; once `scout stats` shows a
record you trust, we can discuss, as a separate change with your approval, whether Scout's plan should drive its stops and targets.

## 10. Simple checks to run through Nemo

1. `scout help` (it also shows the counters of this run).
2. `scout config capital=<your trading capital> risk=1%` and `scout config` to confirm.
3. `scout news`: should list stories. If it says it could not read any news, tell me; that is the first thing to fix.
4. `scout news RELIANCE`, then `scout RELIANCE`.
5. `trade ideas` (before 09:20 or any time: outside the entry window the cards say "a plan for the next session").
6. `scout nifty`.
7. `scout test RELIANCE` (needs about 140 daily candles).
8. After a day or two: `scout ideas`, `scout check <id>`, then `scout stats` every week.
9. Optional: `scout alerts on`.

Paste me what you see (screenshots are fine) and I will fix what the real sources do differently from my fixtures.

## 11. Edits to older code (four, listed on purpose)

1. The docstring's first line.
2. The self-development guard's protected prefixes now include `_n93_`.
3. One entry, `INDIAVIX`, added to the v55 index map (done from the new layer at start, not by editing the old table).
4. (v93.1) `_n55_expiry_value`: an expiry epoch the broker sends as text is kept instead of dropped (it also helps the older IV-surface tool, which needs those epochs).

Wrappers added: `handle` (owner front door), `_n82_capabilities`, `_n83_status_text`, `_n88_abilities`, `prime_regression_suite` (8 `v93-*` rows), `main` (opens the tables, starts the quiet background loop).
The command list gets `scout` and the menu a 🔭 button.

## 12. Next (updated roadmap)

v94 **Doors** (website: Telegram login instead of the `?k=` token, serve properly, rate limits; Tailscale guide; a domain later), then **Offline**, **Knowledge** (cited research, local semantic memory), **Site**, **Apps lane**.
Scout feeds the next steps: its news archive and ledger become the dataset for a calibrated, tested score, once there is enough settled history.
