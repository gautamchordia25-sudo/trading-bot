# Nemo v100.0 "Sigma": a signal desk inside Nemo (stocks, NIFTY/BANKNIFTY, option structures; entry, stop, exit, size, charges, and a record that decides what it may claim)

One release, one file (`nemotron_bot.py`, version 100.0). You asked me to research deeply and build, with Nemo's control, a trading assistant that analyses market data and option chains and gives trade ideas and signals for stocks and options with proper logic, entry, exit and stop-loss, and with new things I find. `NEMO_V100_RESEARCH.md` is the research (every claim tagged with how far to trust it). This page is the build.

> **Where it lives.** I built it **inside Nemo**, not as a second Telegram bot. That way it inherits the owner lock, approvals, trading guards, holiday calendar, broker connection, backups and rollback, and "all VPS changes go through Nemo" stays true. A second bot would need its own BotFather token and its own running copy of the file, with none of those protections. If you still want one (for example a read-only bot for family), say so: it is a small step on top of this.

Everything from v99.1 and earlier is kept. Credentials, owner lock, trading and holiday guards, permissions and approvals, backup and rollback are untouched. **Sigma never places, changes or simulates an order**, never touches the autonomous trading agent (`/autotrade`), the paper ledger, the broker login, the guards or the owner lock, and **never calls an AI** (so it works, and costs nothing, when every brain is down).

---

## 0. Read this first (the honest version)

* **Sigma is a disciplined, measured idea generator, not a proven edge.** I looked for public, audited evidence that any retail rule set makes money after costs on Indian options and found none. SEBI's studies, as reported in the press, say about 9 in 10 individual F&O traders lose money. So Sigma's default answer is **"no trade"**, it says why, and it records every signal it issues so you can see for yourself, after weeks, whether any rule deserves trust.
* **A rule only earns a label from the record.** Fixed rules (nothing is tuned), costs on every trade, no look-ahead, a time split, a bootstrap range, a **control of entries at random times under the same filter and exits**, and then a forward scoreboard. "Promising" needs 30 trades, a positive average whose 90% range stays above zero, positive halves, and a margin over the random-timing control. Under 30 trades the label is "too few".
* **Personal use.** Giving signals to other people can need SEBI registration (even in a closed Telegram group). Sigma is owner-only in this release and never broadcasts. Every card ends with a reminder. This is not legal advice.
* **Not run against any live source.** From my build sandbox the public price feed (Yahoo), NSE and your broker are unreachable (the proxy refuses them), so every test uses fixtures and synthetic markets. Section 11 lists exactly what that means and what you will be the first to see.

---

## 1. How you use it (owner only, private chat; plain words work)

| You say | What happens |
|---|---|
| `sigma` · `signals` · `any signals today` · `give me trade signals` | A full scan: your universe (watch-list, then the NIFTY names, up to 30), NIFTY on its daily rules, the opening-range rule and the option structure. Cards for what passes; one summary line saying what did not and what came close. |
| `sigma market` · `market brief` · `sigma brief banknifty` | The whole read in plain words: trend and regime, next session's pivot levels, India VIX and its percentile, expected move and at-the-money volatility against realised, PCR, walls, open-interest build-up, skew, the volatility percentile, and a **stance** (which kind of structure the conditions favour; a reading, not an instruction). |
| `sigma nifty` · `sigma banknifty` · `nifty signal` · `option signals` | The option structure for the index (market hours, broker connected). A card with the legs, or the reason there is none. |
| `sigma TCS` · `signals for infy` | One name: an indicator panel (ATR, ADX, RSI, averages, 52-week high, band width), any signal that passes, and for every rule that did not fire **why not**, plus the rules that are close. Names Nemo knows only (add others with `scout watch add X`). |
| `sigma board` · `sigma SG100-ABC123` · `sigma check SG100-ABC123` · `sigma drop SG100-ABC123` | Open signals; one in full; is it still valid (and it settles if the plan has resolved); stop following it. |
| `sigma stats` | The scoreboard: every settled signal, per rule, with the win rate and its honest range, the average result in risk units after charges, the worst dip and the evidence label. |
| `sigma test TCS` · `sigma test TCS rsi2` · `sigma test all` | Replays the daily rules on five years of history (one name, or pooled over your universe) with charges, a time split and the random-timing control. |
| `sigma volproxy` | The short-volatility proxy study (section 7). |
| `sigma rules` · `sigma research` | The fixed rules; the short version of the research. |
| `sigma config` · `sigma config capital=5L risk=1% heat=3 max=4 min=65 universe=30 shorts=off breaker=on perday=4` | Your numbers. **Capital and risk follow `scout config` unless you set them here.** |
| `sigma alerts on` / `off` | Opt-in scans at five times on trading days (section 8). Off by default. |
| `sigma help` | The list and this run's counters. |

None of these phrases is taken from older features: "trade ideas", "scout …", "what is the nifty today", "should I buy X" and the rest still go where they went (tested).

---

## 2. How a signal is made

```
daily candles (2 years, public chart feed, cached)  ─┐
NIFTY trend + regime, India VIX                       ├→ the rules (fixed, in advance) → score table → gates → size → card → saved → followed on later prices → scoreboard
5-minute index candles (broker, Yahoo fallback)       │
option chain: quotes, OI, OI change, implied vol     ─┘→ chain analytics → view (six weighted reads) → structure chosen by view × volatility × time → legs, worst case, chance, charges → size → card
```

**Stock and index rules** (every parameter is a constant in the code and is never changed by it):

| Rule | Fires when | Stop · exit · limit |
|---|---|---|
| **Trend pullback (RSI-2)** | price above its 200-day average and RSI(2) below 10 (shorts: mirror) | stop 2.5 ATR · leave at the next open after a close above the 5-day average · 8 sessions |
| **Donchian breakout** | close above the 55-day high on 1.3x volume, ADX ≥ 20, above the 200-day average, not more than 3.5 ATR above the 20-day average | stop 2.5 ATR, trailed 3 ATR behind the best price · leave on a close below the 20-day low · 60 sessions |
| **52-week-high momentum** (long only) | a fresh 20-day high within 3% of the 52-week high, above the 50- and 200-day averages, 6-month return ≥ 10%, RSI(14) ≤ 80 | stop 2.5 ATR, trailed 3 ATR · leave on a close below the 50-day average · 40 sessions |
| **Volatility-squeeze breakout** | Bollinger band width in its lowest 20% of 120 days (within the last 3 bars), then a close outside the bands on 1.2x volume | stop at the middle band (1 to 3 ATR) · target 2R · 20 sessions |
| **Supertrend flip (ADX filter)** | Supertrend(10,3) turns and ADX ≥ 20 | stop at the line (1 to 4 ATR: it is 3 ATR by construction), which then trails · leave when it turns back · 80 sessions |
| **Opening-range breakout** (NIFTY, BANKNIFTY) | after 09:30 a 5-minute close beyond the first 15 minutes' range, on the right side of the session's average price, not against the daily trend, range between 0.15 and 1.2 daily ATR | stop at the middle of the range · target 1.5R · out by 15:10 |

* **Entry is at the next session's open** (a daily signal) and a plan that the open has already made void (opened beyond the stop or the target, or more than 1.5 risk units from the stop) is **skipped, not counted**. A candle that touches both the stop and the target counts as the stop; a gap through the stop exits at the open, worse than the stop.
* The index feed carries no volume, so a true VWAP is not available: the opening-range rule uses the plain average of the session's typical prices and the card says so. 5-minute history is only days long, so **this one rule cannot be back-tested**; its record is built only by following its signals.
* **Score (0-100, a checklist total, not a probability):** fit 25 + setup quality 25 + strength against NIFTY 15 + market backdrop 15 (can go to -10) + risk structure 20. Bands: A 78+, B 66-77, C 55-65; signals are issued from your line (default 65). **Vetoes**: stale data, history under 130 days, average traded value under ₹5 crore, a stop wider than 3.5 ATR (4 for Supertrend), charges over half a risk unit, a price that has already run half an ATR since the close. Anything that could not be read is listed under **NOT CHECKED**, never passed.
* **Charges** (all shown on the card): shares round trip 0.393% of the value (STT 0.1% on both legs, brokerage, exchange, SEBI, stamp, GST, 0.05% slippage a side); index futures about 0.10%; options use Nemo's own ledger table (v96) whatever the ledger's switch says, so a plan is never flattered.

### 2.1 Option structures

**The view** is six weighted reads, each in -1..1 or "not read": daily trend 30%, intraday (5-minute averages, session average, opening range) 25%, **open-interest build-up** near the money 20% (call writing is bearish, put writing bullish, short covering the reverse), fresh daily signal 10%, OI walls 10%, PCR tilt 5% (only at extremes; the evidence for PCR is weak). **Max pain is shown for context and has weight zero.** A direction needs a net bias of 0.30 or more, at least 4 reads, 70% of the weight readable, at least 3 of 5 agreeing, at most 1 strongly against. A range play needs a bias of 0.20 or less, a ranging regime, a volatility percentile of 60 or more, no fast-rising India VIX and no extreme put skew. News is **not** read (Scout does that); every option card says so.

**The structure** (volatility percentile from the chain's **own stored history** once it has 40 readings over 10 days, else the India VIX's range as a stand-in, said on the card):

| | percentile ≤ 35 | 35 to 65 or unknown | ≥ 65 |
|---|---|---|---|
| view up or down | long call/put, else debit spread | debit spread, else long | credit spread (bull put / bear call), else debit spread |
| range | | | iron condor |

Under 3 days to expiry only a debit spread is allowed; under 1 day, nothing (Sigma never opens an expiry-day option trade, no calendar spreads, nothing naked). Every structure has a **worst case known at entry**. A bought structure is **sized by its loss at the planned exit**, a sold one by **its worst case**; lots are rounded down; zero is a valid answer and the card then says the capital that one lot would need ("to risk 1% on one lot you would need about ₹…").

**The card** shows: the legs at the prices you would really get (buy at the ask, sell at the bid), net cost or credit per lot, **worst case, best case, break-evens, a model chance of profit after charges**, the charges in rupees and as a share of the best case, **the model's expected result after charges** (a fairly priced option is worth about zero before charges; this only pays if your view beats the market's), the **exit plan** (a bought structure leaves at its stop value or when the index closes beyond the invalidation level, takes profit at its target value; a sold one takes profit at half the credit, leaves when it costs twice the credit to close or the index closes beyond a short strike; every structure is out the day before expiry), the size, an alternative, the open-interest facts, what was not checked, and what would make it wrong.

**Acceptance tests** (fixed in the code): bought structures need reward to risk ≥ 1.4 at the plan, a break-even within 0.9 of the expected move, time decay under 12% a day and charges under 35% of the best case; sold ones a credit of at least 12% of the width, a model chance of profit after charges of at least 60%, charges under 35% of the best case and short strikes at least 0.8 of the expected move away. The chance is a one-volatility lognormal model priced off the chain's own forward; it ignores the smile, gaps and any view, and says so.

### 2.2 Limits and gates

| Gate | Default | What it does |
|---|---|---|
| risk per signal | 1% of capital (follows `scout config`) | sizes every signal |
| portfolio heat | 3% of capital | a signal that would take the open risk past this is held back |
| at most per scan / per sector | 4 / 2 | |
| **circuit breaker** | 3 stopped-out signals, or today's settled signals at -2R | nothing more is issued that day (`sigma config breaker=off` switches it off) |
| session | signals for the index and options only 09:30-14:30 on a trading day with a verified calendar (2026) | otherwise the reason is named |
| data | stale series, thin history, missing quotes, odd chains | refused with the reason |

---

## 3. The record: how Sigma stays honest

Every issued signal is saved (one per symbol, rule and side per day) and followed on later prices: daily signals on later daily candles (entry at the next open, stop first, gap exits at the open, the rule's own exit, a time limit), the opening-range rule on 5-minute candles to 15:10, option structures **marked every 10 minutes while the market is open on the chain's live mid prices** (or on the model, said so) and settled at the plan's stop, target, a close beyond the invalidation level, or the last day. Results are in units of the planned risk **after charges**. When one settles you get one line. Skipped plans are not in the record. Nothing is tuned from the record automatically (that would over-fit): you read it and decide.

## 4. The backtest (and its control)

`sigma test TCS` and `sigma test all` replay the five daily rules with the same code as live (no look-ahead: a test changes the future and checks that closed trades do not move), entry at the next open, **charges and slippage on every trade**, stop first, one position per rule at a time, trades still open at the end left out. They report trades, win rate with its range, average result after charges with a bootstrap range, profit factor, worst dip, halves split in time, and the **control**: the same rule's stop, trail, exit and time limit applied at **random times** on bars that pass the rule's own side-of-market filter. A rising market lifts those entries as much as it lifts the rule, so the rule has to beat them.

What I measured **on synthetic markets** (not real prices, so it says how the code behaves, not how the market behaves):

| Market | Result |
|---|---|
| random walk, no drift (20 markets, 1,090 trades) | average **-0.06R** after charges; no rule "promising" |
| random walk with a drift of 0.08% a day | 52-week-high momentum shows **+0.30R** (it looks great), but entering at random times with the same exits earns **+0.20R**; its timing adds +0.10R with a range from -0.08 to +0.28: label **UNPROVEN** |
| returns with a little momentum | no rule's margin over random timing is distinguishable from zero |

The caveats all flatter a result and are printed under every test: today's index members are a survivor list; the rules were written knowing how these markets behaved; a daily candle cannot show what came first inside the day; fills at the open are assumed. Trades on different stocks in the same weeks are not independent, so the pooled ranges are narrower than the truth.

## 5. The short-volatility proxy study (`sigma volproxy`)

There is no historical option data here, so option structures cannot be back-tested. Instead Sigma prices a **weekly iron condor** on the real NIFTY history with the India VIX as every leg's volatility, short strikes one expected move out, wings two strikes further, 1 lot, held to expiry, settled on the real close, with charges and slippage, and shows: win rate with its range, average and total per lot, **the worst week, the worst five weeks, the deepest dip, the longest losing run, how often the short strikes were breached against the 32% a fair one-sigma strike implies, and the real move against the implied one**. It is a **proxy**: it prices the far wings with the same volatility as the near strikes (real wings cost more, so the credit here is too good), ignores the skew and the real bid-ask, and has no management. Its job is to show the *shape* of selling options (many small wins, rare large losses) with your own market's numbers, not to forecast.

## 6. New things in this release (from the research)

1. **A control for drift** in every backtest (random-timing entries, same filter and exits).
2. **The chain's own implied-volatility history**: every time Sigma reads the chain it keeps the at-the-money volatility (at most every 20 minutes), so after a few weeks the volatility percentile is Sigma's own and no longer the VIX stand-in.
3. **Open-interest build-up read** (who is adding or leaving, from the change in open interest against the change in price), **skew**, **expected move from two sources that must agree**, and the **forward price implied by put-call parity** for the probability model.
4. **The model's expected result after charges** on every option card, so a structure that is a coin flip minus costs says so.
5. **Capital honesty**: "0 lots", and the capital one lot would need, instead of rounding up.
6. **Circuit breaker, portfolio heat, per-sector cap** and a daily alert quota.
7. **A forward scoreboard** with evidence labels, and the short-volatility proxy.
8. **"Why not" for every rule on every name**, plus a watch-list of rules that are close to firing.

## 7. Alerts (opt-in, `sigma alerts on`)

Five slots on trading days with a verified calendar: 08:50 (before the open: shares and NIFTY on their daily rules), 09:45, 11:30 and 13:15 (NIFTY: opening range, option structure), 15:50 (after the close: shares). Each slot scans at most once a day, sends only signals that pass your line and the limits, at most `perday` (default 4) in total, and nothing when none passes. Open signals are followed every 10 minutes while the market is open and every 3 hours otherwise.

## 8. Cost and storage

* **No AI, no paid call.** Data: the public daily chart feed (about one request per name per scan, cached 10 minutes in the session and 6 hours outside it), Nemo's existing market fabric for the 5-minute index candles and India VIX, and the broker's option-chain read (the same one `/chain55` uses). A scan of 30 names is about 31 daily-history requests, cached.
* **Storage:** four small tables in the database Nemo already uses (`sig100_signal`, `sig100_iv`, `sig100_setting`, `sig100_cache`): a signal is a few KB, an IV reading about 100 bytes (pruned after 400 days), cached history pruned after 3 days.

## 9. What I did not do

* No orders, no change to the trading agent, the guards, the owner lock or any credential. No second bot.
* No stock options (index options only: stock option chains differ in lot sizes and liquidity, and I have no way to test them here).
* No news, results-date or policy-date gate (Scout reads news; Sigma lists "macro news" as not checked), no participant-wise open interest (the NSE file needs your server), no true VWAP (no index volume), no margin calculation for sold legs (the card says broker margin applies).
* No family view (a possible follow-up through Desk, read-only, without sizing).
* The one-screen `nemostatus` and the abilities screen are already full (each layer adds a line or a row and the screens are cut at about 4,000 characters; v99.1's status line is already cut): Sigma's counters are on `sigma status`, and Sigma is not listed on the abilities screen (it is in the capabilities text and on `sigma help`).

## 10. A trade-off you should know about

Fixed, pre-declared rules cannot be over-fitted by Sigma, but they cannot adapt either: if a rule stops working, Sigma will keep issuing it until the scoreboard shows it, and you decide. The thresholds (RSI below 10, 55 days, 1.3x volume, the acceptance tests, the score weights) are my judgement, **not tuned on data**; `sigma stats` and `sigma test` are how you find out whether they hold in your markets.

## 11. Verified and not verified

**Verified offline (213 new tests, `tests/test_sigma100.py`):**
* the indicators against hand-worked numbers (RSI, ATR, Bollinger bands, pivots, realised volatility, option payoffs, break-evens, a probability model whose mean is the forward and whose fair-priced options are worth about zero), and that **the value at bar i never depends on later bars**;
* each rule on a built case, each why-not, the walker (stop first, gaps, targets, time exit, rule exit at the next open, trailing, skipped and chasing plans, Supertrend trail, a deadline), **no look-ahead** at the trade level;
* the chain analytics (expected move from both sources, skew, PCR, walls, build-up quadrants, liquidity, the IV history and the percentile order), every structure's geometry and exit plan, the acceptance tests, sizing that never rounds up (including the ₹20,000 account), the structure choice by volatility and time;
* the option signal end to end (bullish with cheap options, dear options, a range, no condor when options are cheap, an expiry within a day, disagreeing reads, a target too far, a small account) and the opening-range rule;
* scoring and vetoes, issuing (duplicates, score line, per-sector cap, heat, the circuit breaker), the tracker for shares, the opening range and options (target, stop, time, last day, model marking), the statistics and labels (a rising market does not make a rule promising when random timing does as well), the scoreboard, the volatility proxy;
* the data layer (feed parsing, the forming candle, the cache, fallbacks, the split flag), the front door (every phrase, the phrases it must not take, guests, files, groups), a whole scan, the alert slots and quota, the brief, the wiring (version, protection, wrapped functions, regression rows), and **structural tests**: the layer names no order function, no AI call, no secret-shaped text, assigns nothing to the owner lock or the agent, makes exactly one network call (the public daily feed), and writes only its own four tables.

**Not verified (you will be the first to see):**
* **Anything against live sources.** The public chart feed's real responses, your broker's real option chain (field names for open-interest change and price change: Sigma reads `oi_change` and `chp` as the v55 parser names them, and the build-up read says "not available" when they are missing), the real bid and ask after hours, real expiry timestamps, real 5-minute candles.
* **Whether any rule makes money on your markets.** Nothing here proves it; `sigma test all` and, above all, `sigma stats` over weeks are how you find out.
* The wording of the cards was judged by reading them, not by anyone in your position.
* The model chance of profit and the proxy study are models: they ignore the smile, gaps, skew and real fills.

## 12. Try it, through Nemo

1. `sigma help`, then `sigma rules` and `sigma research` (free, instant).
2. `sigma config` and set your capital and risk honestly (`sigma config capital=… risk=…`; it follows `scout config` otherwise).
3. After the close or before the open: `sigma` (a scan of shares and NIFTY's daily rules). In market hours (09:30-14:30): `sigma market`, then `sigma nifty`.
4. `sigma TCS` to see the panel and why each rule did or did not fire.
5. `sigma test TCS`, `sigma test all` and `sigma volproxy` to see what the rules and the structures would have done, with the control and the caveats.
6. If you want it to come to you: `sigma alerts on`. Leave it a few weeks, then `sigma stats`.
7. Tell me what the first live scan said (and any message that reads wrongly): the first real chain is where the fixtures will meet the truth.

## 13. What changed in older code (everything else is in the new layer, marker `# NEMO 100 - SIGMA`)

1. The docstring, `VERSION`, and `'_n100_'` in the live-self-edit protection list (two lines of older code).
2. Wrapped (the old function kept and called): `handle` (the front door, owner only), `_n82_capabilities`, `_n83_status_text`, `prime_regression_suite` (7 more rows), `main` (creates the tables and starts the quiet loop). **Not wrapped: the “what can you do” abilities screen** (`_n88_abilities`): it is already full (its fitting routine is at its limit, and one more row breaks the v88 report test), so Sigma is listed in the capabilities text and on `sigma help` instead.
3. One command (`/sigma`) and one menu button added to the existing command list and main menu.
4. Tests: `tests/test_sigma100.py`. The v99.1 structural tests already stop at this layer's marker.

## 14. Test results (offline, on the test machine)

* **Whole suite on the exact file delivered (the slow gate switched on): 2,928 tests, 6 skipped, 0 failures.** 213 of them are new (`tests/test_sigma100.py`); the earlier 2,715 all pass. A first full run of an earlier build found three conflicts with older tests, all fixed before this one: the v91 structure test required the file's first line to start with `v9` (loosened to any version number: Nemo has reached three digits); the v94 test counts one older line of code that my loader had copied word for word (my copy was renamed); and the "what can you do" screen is so full that even one more row broke the v88 report test, so Sigma is not listed there (section 13).
* Pyflakes: the same 158 messages as v99.1, none new. Only two lines of older code were edited (the docstring's first line and the protection list); a scan of the 3,361 added lines for keys, tokens or passwords found none. The tests also assert that the layer names no order function, no AI call and no secret-shaped text, assigns nothing to the owner lock or the agent, makes exactly one network call (the public daily feed) and writes only its own four tables.
* Nothing here placed, changed or simulated an order, called a broker, called an AI, or used a paid service, and **no real market data was read** (the sandbox cannot reach the feeds). Every market in the tests is synthetic; every expectation can be checked by hand.
* The slowest new group is the backtest and its random-timing control (about 40 seconds for the whole new file).
