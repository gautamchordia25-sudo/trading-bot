# Nemo v84 "Atlas": Futures Desk + speed

v84 is an additive layer on v83 (Cortex). It is one more block before the `__main__` guard plus small, asserted edits to v83's
own code. Every new feature has a switch or is read-only, and any failure falls back to the previous behaviour.

**Interpretation note.** "More advanced features for futures" was read as *futures trading* (NSE index/stock futures), because Nemo
is a trading assistant and had options + a long-only paper lab but **no futures support at all** (every "futures" hit in v82 was
Python's `concurrent.futures`). If you meant something else, say so and I will redirect.

## 1. Futures Desk (`/fut84 …`): advisory maths, never orders

Nothing here places, modifies or simulates an order, and it does not use the broker, the paper ledger (`TradeLab75`), the v81 trading
guard or any network call. A test (`TestAdvisoryOnlyGuarantee`) parses the v84 block and fails if it ever references a broker/order
function, `requests`, a shell or file I/O, and checks that the only trading-code helpers it borrows are read-only
(`lot_size`, `_n81_session`, `_N81_HOLIDAYS_2026`).

| Command | What it computes |
|---|---|
| `/fut84 expiry [sym=NIFTY] [count=3]` | next monthly expiries, holiday roll-back (e.g. Nov 2026: last Tuesday 24 Nov is Guru Nanak Jayanti → Mon 23 Nov), sessions left, roll window, `NSE:NIFTY26OCTFUT`-style hint |
| `/fut84 basis spot= fut= (days= \| expiry= \| sym=)` | cost-of-carry fair value, basis, annualised carry, implied financing rate, rich/cheap vs fair |
| `/fut84 roll near= next= (days= \| sym=) lots=` | calendar spread, annualised roll yield, spread vs fair carry, ₹ cost per position |
| `/fut84 size capital= risk=(₹\|%) entry= stop= [target= margin=\|margin_per_lot= slip= sym=\|lot=]` | lots from risk and margin cap, notional, leverage, max loss, R:R and break-even win rate |
| `/fut84 pnl side= entry= (exit=\|ltp=) lots=` | points, gross, charges (only if you configured rates), break-even price |
| `/fut84 check …` | pre-trade checklist → CLEAR / CAUTION / BLOCK (advisory): risk vs your limit, margin use, R:R, ATR sanity, days to expiry, market session |
| `/fut84 edge win= payoff= [n= streak= risk=]` | expectancy (R), Kelly/half-Kelly, exact probability of a losing streak |
| `/fut84 journal add\|list\|del`, `/fut84 stats` | **owner-reported** closed trades; win rate, payoff, profit factor, expectancy (₹ and R), max drawdown, streaks, by-tag |
| `/fut84 config …`, `/fut84 alerts on\|off` | your settings; opt-in 08:45 IST brief, sent only if something matters |

Numbers accept `5L` (=5,00,000), `1.5cr`, `500k`, `₹5,00,000`, percentages with `%`. Unknown parameters and impossible inputs are rejected
with an example, never guessed. All of it is also available to chat as **one read-only Cortex tool** (`futures`): ask "how many lots of
nifty futures can I take with 5L risking 1%, entry 24500 stop 24440?" and the answer is built from the exact computed result. The tool
cannot write the journal, change settings or toggle alerts (tested, including a deliberately bypassed validator).

### What was verified, and how
Every formula was checked against an independent calculation: fair value `S·e^{(r−q)T}`, annualised carry, implied rate, roll spread and fair
spread, lot sizing floors, margin-cap binding, slippage, charges (hand-itemised STT/exchange/SEBI/stamp/GST), expectancy/Kelly, journal stats
and drawdown (hand-built 3-trade and 7-trade sequences), calendars (Oct/Nov/Dec 2026 and the 2027 roll, session counts hand-counted). The
losing-streak probability is an exact DP, checked against brute-force enumeration for 288 (q, n, k) cases and a closed-form recurrence
(P(≥6 straight losses in 100 trades at 55% loss rate) = 72.90%). That check also caught a wrong expectation in one of my own regression rows.

### Assumptions you must confirm (each is labelled in the output)
* **Expiry rule** = last *Tuesday* of the month, moved to the previous session day if it is a holiday. This is my understanding of NSE's
  current schedule and is an **estimate**; change it with `/fut84 config expiry_weekday=<mon..fri>`. Holidays are known for **2026 only**
  (Nemo's existing v81 table); other years are flagged "calendar unverified".
* **Lot sizes** come from Nemo's existing `LOT_ORDER` table (NIFTY 65, BANKNIFTY 30 …) and are labelled *not verified today*. Pass `lot=` from
  your broker to override. Nemo's own paper lab insists on a daily instrument master for the same reason.
* **Rates** (financing 6.5% to match the existing options code, dividend 0%) are placeholders. **Charges default to 0** so P&L is gross until
  you set brokerage/STT/exchange/SEBI/stamp/GST yourself; no tax rates are baked in.
* **Margin** is whatever you supply (`margin=12%` or `margin_per_lot=`). There is no SPAN engine; without margin the cap is *not* applied and
  the output says so.
* The **pre-trade check** does not see live prices, your broker positions, or the v81 guard. It is arithmetic on what you typed.

## 2. Speed (measured first)

Profiling with a zero-latency fake provider showed the **non-network overhead is already tiny: ~23 ms for the router wrapper chain and
~3 ms for a whole Cortex turn.** Wall-clock time is the model calls, so v84 removes or overlaps them instead of micro-optimising SQLite:

* **Zero-model answers**: pure arithmetic ("what is 18% of 1250", "(1250 x 3)/4"), common date questions ("what day is 25 Dec 2026",
  "what date will it be in 45 days", "how many days until …"), exact "futures expiry" phrases and every `/fut84` command are answered locally, before
  the task engine. Guards: never when Nemo's last message was a question or an approval/upload/browser flow is pending; dates, codes and
  phone-number-like strings are never treated as sums; a bare `5/6` is not a division unless you say "what is" or end with `=`.
* **Router bypass for plain conversation**: a broad deny-list (171 action/integration/trading/Hinglish alternatives, URLs, e-mail addresses,
  code, ids) keeps every action request on the router. A wrong skip only means chat answers and says a workflow is needed; a wrong non-skip
  only costs the router call. Futures *calculation* questions go to Cortex's tool; order-like messages ("buy 1 lot nifty futures") never do.
* **Parallel tool rounds** (3 searches ≈ the slowest one, not the sum), **typing indicator kept alive** (Telegram drops it after ~5 s),
  **per-stage timings** in `/why83` and **p50/p95** in `/cortex83`.

Measured through the real `handle()` path with a call-counting provider (this counts sequential model calls; it is **not** a live latency test). Across these seven messages: **15 → 6** sequential model calls.

| message | v83 | v84 |
|---|---|---|
| "hi" | 1 | 1 |
| "should I hire another salesman for the showroom?" | 2 (router + answer) | 1 |
| "what is 18% of 1250" | 3 (router + scout + answer) | **0** |
| "what date will it be in 45 days" | 3 | **0** |
| "how many lots of nifty futures …" | 3 | 2 (scout + exact tool + answer) |
| "remind me to call Rahul tomorrow" | 1 (router) | 1 (router, unchanged) |
| "my sister Priya lives in Pune" | 2 | 1 |

Kill-switches: `/cortex83 fastpath off`, `/cortex83 instant off`, `/cortex83 tools off`.

## 3. Smarter
* **Weekday/date audit** (new, deterministic): every "Friday, 25 December 2026"-style claim in an answer is checked against the calendar and fed
  through the same one-shot repair as v83's arithmetic audit; an unrepairable one is flagged with a visible "Date check" line.
* The chat prompt now tells the model to use the futures tool for expiry/sizing/basis/P&L, never to invent live prices or lot sizes, and that
  Nemo cannot place orders.

## 4. Bugs found and fixed while building it (by my own tests)
* A typo in the router deny-list (`fort?`) matched the word **"for"** and would have disabled the fast path for most messages.
* Two help strings printed a literal `%%`.
* My own regression row for the streak maths had the wrong expected value (the code was right; verified by brute force).

## 5. Tests and limits
`tests/test_atlas84.py` (109 tests) + `tests/test_cortex83.py` (76) all pass; the bot's own `/regress` gains 24 `v84-*` rows with no new failures
versus the v82 baseline (the same 5 environment-dependent rows). **Not verified:** live providers/Telegram, real latency, real NSE/broker data.
Alerts are tested with an injected clock, not a real 08:45 wake-up.

## 6. Deploy / roll back
Send `nemotron_bot.py` to Nemo → `/update` → Apply (you should see `v83.0 → v84.0`; credential lines unchanged). `/rollback` restores the previous file.
Then try: `/fut84 help`, `/fut84 expiry sym=NIFTY`, "what is 18% of 1250", `/cortex83`. First, set your numbers once: `/fut84 config capital=5L`.

## 7. Not done (and why)
* **Live prices/option-chain-driven basis, SPAN margin, open-position tracking**: need broker data and freshness checks like the v75 lab; I would not
  ship those untested against the real API.
* **Futures paper-trading**: `TradeLab75` is deliberately long-only for cash/CE/PE; adding shorts, margin and MTM touches money-adjacent invariants
  and deserves its own reviewed change.
* **Hedged/streaming provider calls** and per-role cooldown keys in Brain73 remain follow-ups.
