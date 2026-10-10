# Research behind Nemo v100 "Sigma" (signals desk): what I looked for, what I found, what I used and what I refused

You asked me to research deeply and build, inside Nemo, a trading assistant that studies market data and option chains and gives trade ideas and signals for stocks and options with proper logic, entry, exit and stop-loss.
This page is the research. `NEMO_V100_SIGMA.md` is the build. Every finding carries one of these tags, so you can see how much weight it deserves:

| Tag | Meaning |
|---|---|
| **[web]** | A figure or claim I found in web search results (press reports, exchange or broker pages). I read search snippets, not the original SEBI or NSE documents, so treat the exact numbers as "reported". |
| **[text]** | Standard textbook material (Black-Scholes, ATR, Wilder's indicators, fixed-fractional sizing). Stable and checkable offline. |
| **[lit]** | A finding from the academic or practitioner literature that I know from memory. Not re-read today. |
| **[mine]** | My own judgement or a rule I chose. Not tuned on data. |
| **[code]** | A fact about Nemo's own code that I read in this session. |

Nothing below is "proof that a rule makes money". Section 9 says what that would take and how Sigma measures it.

---

## 1. The base rate you are fighting (why Sigma is built around not losing)

* SEBI's studies of individual equity-derivative (F&O) traders, as reported in the press **[web]**: about 91% lost money in FY25, about 87.7% in FY26; options buyers were about 97% of the individuals; 65.6% lost money in every year from FY22 to FY26. Average losses were large relative to the gains of the minority.
* Consequence for design **[mine]**: the default output of a signal tool must be "no trade". A tool that always finds something to buy is a tool that feeds the 91%. Sigma therefore refuses most scans, says *why* it refused, and ranks "stand aside" as a legitimate result.
* The cost side is not small **[web]**: from 1 April 2026 the securities transaction tax is reported as 0.15% on the premium of options sold (futures 0.05%), plus brokerage, exchange, GST and stamp. For a trader who buys a ₹100 option and sells it for ₹130 the tax and fees together eat a visible slice of the ₹30. Sigma subtracts costs from every backtest and every tracked signal, using the rates already in Nemo's ledger (v96) **[code]**.

## 2. The market itself (India facts that change the rules)

| Fact | Source | Use in Sigma |
|---|---|---|
| NIFTY lot size 65 **[code]** (already in Nemo); NIFTY has the only weekly expiry among the index options, on **Tuesday**; the other indices are monthly **[web]** | exchange circulars as reported | Sigma uses weekly options only on NIFTY. It reads the calendar from the option chain's own expiry list, so a change by the exchange is picked up. |
| Expiry-day extreme loss margin raised (+2%) and the calendar-spread margin benefit removed on expiry day **[web]** | SEBI measures as reported | No expiry-day strategies. No calendar spreads. Short options on the last day are never issued. |
| Holidays: only the 2026 calendar is in Nemo **[code]** | v81 | Outside 2026 Sigma says "calendar unverified" and does not issue time-critical signals. |
| Registration: giving tips, signals or recommendations to other people, even in a closed Telegram group, needs SEBI registration as an investment adviser or research analyst **[web]** | regulator statements as reported | Sigma is a **personal tool**. It is owner-only in this release (a read-only family view through Desk is a possible follow-up); it never broadcasts, posts to a channel or sells anything. Every signal carries a one-line reminder. This is not legal advice; ask a registered professional if you ever want to share signals beyond your own household. |

## 3. Option-chain analytics: what the evidence supports

| Tool | What it is | Evidence | Decision |
|---|---|---|---|
| **Expected move** | One standard deviation = S × IV × √(T/365). An at-the-money straddle costs about 0.8 of that (so one standard deviation is about 1.25 × the straddle; some web pages quote the expected move as “about 85% of the straddle”, a looser rule of thumb) **[text]** | Sound arithmetic; a market-implied range, not a forecast of direction. Sigma's own test: on a Black-Scholes chain the two figures agree within 3%, and the card warns when they differ by more than 25%. | **Used** as the yardstick for every target: a plan whose target is more than 1.3 expected moves away is refused. Short strikes are placed outside 0.8 to 0.9 of it. |
| **IV percentile / IV rank** | where today's implied volatility sits in its own history | Standard for choosing between buying and selling options **[text]**; for India the VIX is the usual proxy | **Used** to choose the structure: cheap options (low percentile) → buy debit structures; dear options (high percentile) → prefer defined-risk credit structures. Nemo's v93 used the VIX percentile; Sigma also **stores the chain's own ATM implied volatility every time it looks** (new table), so after a few weeks it has its own history and stops relying on the proxy. |
| **Variance risk premium** | implied volatility usually exceeds the volatility that follows | Positive on average for index options in India and elsewhere, with rare, large losses **[lit]** | Explains why sellers win often and lose big. Sigma only issues **defined-risk** short-volatility structures, sizes them by their maximum loss, and runs a "short-volatility proxy study" (section 8) so you see the tails. No naked selling, ever. |
| **Open-interest build-up classification** | price up/down together with OI up/down: long build-up, short build-up, short covering, long unwinding; for options: call writing, put writing and so on **[text]** | Widely used; the information is real (who is adding risk) but the direction signal is modest **[lit]** | **Used** as one of several weighted reads, never alone; and **shown** so you can see it. |
| **PCR (put/call ratio)** | put OI ÷ call OI | Extremes are used as a contrarian tilt; evidence for index options is weak and unstable **[lit]** | **Used with a small weight** and only at extremes (below 0.7 or above 1.3), as a tilt not a trigger. |
| **OI walls (largest call/put OI strikes)** | strikes where writers have the most at stake | Often cited as support and resistance; the evidence that they hold is anecdotal **[lit]** | **Used** as places where a plan's target or stop is likely to meet friction, not as predictions. |
| **Max pain** | strike where option buyers lose most at expiry | The evidence is thin, and what exists is for small illiquid US stocks, not Indian index options **[lit]** | **Shown for context only, weight zero.** I will not let a doubtful number move a score. |
| **Skew (put IV minus call IV)** | how much dearer downside protection is | A real, persistent feature; a rise in skew often accompanies stress **[lit]** | **Used** as a risk-off flag and to price the put wing of condors honestly. |
| **Greeks-based "gamma exposure"** | dealer positioning inferred from OI | Needs the unobservable dealer sign **[code]**: Nemo's own tool says "heuristic" | **Rejected as a signal.** Shown nowhere in Sigma. |
| **Participant-wise OI** (FII index-futures long/short ratio) | NSE publishes it daily | Information is real but needs a daily NSE download that Nemo's sandbox cannot reach **[mine]** | **Not built.** Listed as a candidate for a later version once it can be read on your server. |

## 4. Stock and index strategies: what I adopted

All of these have **fixed parameters decided before any test** (no optimisation, so there is nothing to over-fit), a stated invalidation level and a stated exit.

| Strategy | Logic | Why it is in | Weak points (shown on the card) |
|---|---|---|---|
| **Trend pullback (RSI-2)** | price above its 200-day average and RSI(2) below 10 → buy the dip; exit when price closes above the 5-day average or after 8 days | Short-term reversal inside an uptrend is one of the most replicated equity effects **[lit]**; RSI(2) is its common form **[text]** | Fails in a bear market (hence the 200-day filter) and in crashes; no stop is natural, so Sigma imposes a 2.5×ATR disaster stop. |
| **Donchian breakout** | close above the 55-day high on volume at least 1.3 × average, ADX at least 20 → trend entry; trail with a 3×ATR Chandelier exit | The oldest systematic trend rule; works in trending markets and loses small, often, in ranges **[lit]** | Low win rate (35 to 45% is normal), so it needs the 2R-plus winners. |
| **52-week-high momentum** | within 5% of the 52-week high, above the 200-day average, 6-month return in the top of the stock's own history | Nearness to the 52-week high and medium-term momentum are robust return predictors, including in India **[lit]** | Momentum crashes at sharp market reversals. |
| **Volatility squeeze breakout** | Bollinger band width in the lowest 20% of its last 120 days, then a close outside the band with above-average volume | A squeeze signals that *a move is coming*, not which way **[lit]**; Sigma waits for the break to give direction | False breaks; hence the volume and close requirements. |
| **Supertrend flip with ADX filter** | trend-following flip, only taken when ADX ≥ 20; the stop is the Supertrend line, which is about 3 ATR away by construction (so the allowed stop is 1 to 4 ATR here, against 3.5 for the other rules) | Supertrend alone whipsaws in ranges **[lit]**; the ADX filter removes most of that | Still lags; a wide stop. |
| **Opening-range breakout (index, intraday)** | after the first 15 minutes, a 5-minute close beyond the opening range, on the right side of the session's average price and not against the daily trend, entry window 09:30 to 13:30; stop at the middle of the range, target 1.5 times the risk, out by 15:10 | A standard intraday rule with mixed published evidence **[lit]** | Many false breaks on range days. It **cannot be back-tested here** (5-minute history is days long): its record is built only by following the signals it gives. |
| **VWAP reclaim / rejection (index, intraday)** | price crosses VWAP with volume after a stretch away from it, in the direction of the daily trend | Institutional benchmark; mean reversion to VWAP is common intraday **[text]** | **Not built.** A true VWAP needs volume and the index candle feed carries none (every index candle has volume 0 **[code]**). Sigma uses the plain average of the session's typical prices as a filter inside the opening-range rule and says on the card that it is not a VWAP. |

Rejected: candlestick patterns (no reliable evidence **[lit]**), "AI price prediction" (nothing I can test), Fibonacci levels (no edge over round-number levels), indicator pile-ups that agree with each other because they are all functions of price (a confirmation of nothing).

## 5. Option structures: choosing by view × volatility × time

| View | IV percentile low (≤ 35) | middle | high (≥ 65) |
|---|---|---|---|
| **Bullish** | long call or **bull call debit spread** | debit spread | **bull put credit spread** (short strike beyond the expected move) |
| **Bearish** | long put or **bear put debit spread** | debit spread | **bear call credit spread** |
| **Neutral / range** | no trade (buying volatility is usually overpriced **[lit]**) | no trade | **iron condor** (short strikes just outside the expected move, wings 1 step to 3 steps out) |

Rules **[mine]** built on the table: all structures have a maximum loss that is known when the trade is opened; under 1 day to expiry → nothing; a long option or a credit structure needs 3 or more days (debit spreads from 1 day); liquidity filters (a live bid and ask, a spread under 3% or ₹1, open interest of at least 50 lots); a bought structure is sized by its loss at the planned exit and a sold one by its *maximum loss*, never by the premium; acceptance tests fixed in the code (reward to risk at least 1.4 for bought structures; for sold ones a credit of at least 12% of the width, a model chance of profit after charges of at least 60% and charges under 35% of the best case); profit target on credit structures at 50% of the credit received and a loss limit at 2× the credit, a common management rule whose edge is vendor-claimed and **unproven [lit]**, shown that way.

Rejected: naked short options (unbounded or very large loss), straddle/strangle buying as a default (negative expected value under a positive variance risk premium), calendar spreads (the exchange removed their margin benefit on expiry day **[web]**), anything that needs a margin number I cannot compute (the card says "broker margin applies").

## 6. Risk management (the part that decides survival)

| Rule | Detail | Evidence |
|---|---|---|
| **Fixed-fractional sizing** | risk per signal is a fixed share (default 1%) of capital; quantity is rounded **down**; "0 lots" is a valid answer and is said plainly | **[text]**; Kelly sizing needs a proven edge that Sigma does not have, so it is not used. At most half or quarter Kelly is what practitioners suggest even when an edge is known **[lit]** |
| **ATR stops** | 2 to 3 × ATR(14) for swing trades, beyond the structural swing where there is one; never closer than 1 × ATR | **[text]** |
| **Chandelier trailing exit** | highest high since entry minus 3 × ATR(14) (22-day) | **[text]** (Le Beau) |
| **Time stop** | every signal has a last day; it is closed at the then price | **[mine]** |
| **Portfolio heat** | the total risk of open signals is capped (default 3% of capital); correlated signals (same side, same index or sector) count together | **[text]** |
| **Daily circuit breaker** | after 3 stopped-out signals in a day, or a day's total below −2R, Sigma issues nothing more that day | **[mine]**; a tool that keeps signalling after a bad run feeds revenge trading |
| **Event gates** | expiry within a day, the first and last minutes of the session (signals only 09:30 to 14:30), stale data, a closed market, an unverified calendar. **Not built in v100:** results dates and policy dates (Scout reads them from news; Sigma lists “macro news” as *not checked* on every option card) | **[mine]** |

## 7. Validation: how a signal gets to claim anything

Backtests lie in predictable ways **[lit]**: look-ahead, survivorship bias, ignoring costs, and selection after many trials (backtest over-fitting; "deflated Sharpe", "probability of backtest over-fitting"). What Sigma does:

1. **Parameters are fixed in advance and never tuned by Sigma.** A strategy that was not optimised cannot be over-optimised.
2. **No look-ahead**: signals use only candles up to the close of the signal bar; entry is at the *next* open; a test changes the future and checks the past does not move.
3. **Costs and slippage** are charged on every simulated trade.
4. **Stop first** when a candle touches both the stop and the target.
5. **Out-of-sample split**: the history is split in time; Sigma reports both halves. A strategy earns the label *"promising"* only if both halves are positive, there are at least 30 trades and a bootstrap confidence interval on the average result in R stays above zero. Otherwise it is *"unproven"* or *"negative"*, and says so.
6. **Forward tracking is the real test.** Every signal Sigma issues is saved and followed on later prices; the scoreboard shows, per strategy, the trades, win rate with its Wilson interval, average R after costs and the evidence label. Under 30 settled signals the scoreboard says "too few to mean anything".
7. **Option structures cannot be backtested here**: there are no historical option prices. Instead of pretending, Sigma offers a **short-volatility proxy study**: it prices a weekly condor with the India VIX as the implied volatility and settles it on the real NIFTY move, so you can see how often the short strikes hold and how deep the bad weeks are. It is a proxy (no skew, no costs of fills), labelled as one.

## 8. What I did not find, and what I could not check

* I found **no public, independently audited evidence that any retail rule set in this list makes money after costs on Indian options**. I looked for it. The honest statement is: Sigma is a disciplined, measured idea generator, not a proven edge.
* I could not read the SEBI and NSE documents themselves from the build machine; the numbers marked **[web]** come from press and broker pages in search results.
* Nothing in Sigma was run against live broker or exchange data in this session (the sandbox cannot reach them). The tests use made-up and synthetic data. Section "Verified and not verified" of the build page lists exactly what that means.
* Facts that go stale: lot sizes, expiry weekday, tax rates and margin rules change. Sigma reads lot sizes and expiries from Nemo's own tables and the live chain, and the cost rates can be edited with `ledger costs` (v96).

## 9. A separate Telegram bot?

You asked for "a new bot". Sigma lives **inside Nemo** on purpose: that way it inherits the owner lock, the approvals, the trading guards, the holiday calendar, the broker connection, the backups and the rollback, and "all VPS changes go through Nemo" stays true. A separate Telegram bot would need its own BotFather token and its own running copy of the file on the server, and would have none of those protections unless they were copied. If you still want a second bot (for example a read-only bot for family), say so; it is a small step on top of this, not part of this release.
