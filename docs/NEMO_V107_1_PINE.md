# Nemo v107.1 "Pine": Pine Scripts that arrive, built on Nemo's own survival rules

You sent a screenshot. You asked Nemo "create a new pine script", answered its question with "create a pine script with your survival logics", and four minutes later got only: *"Work W71-E8FAC87056 partial. Completed 2 planned steps … Error: WORK_BUDGET_REACHED."* No script.

v107.1 is a fix release, like v99.1 and v106. The next planned feature version is still **v108 Voice**.

Evidence tags: **[code]** = read in Nemo's code; **[tested]** = covered by the offline tests; **[parsed]** = passed a real Pine grammar parser (pynescript 0.3.0) on the test machine; **[source]** = from the pages in section 8; **[not verified]** = not checked live.

## 0. Read this first (the honest version)

* **I could not compile anything inside TradingView.** The test machine cannot reach tradingview.com: its network blocks it. What was checked:
  * Nemo's own Pine checks [tested]: version line, one declaration, v6 names, balanced brackets, no plots inside blocks, plain ASCII.
  * A real Pine grammar parser, pynescript [parsed]. It catches syntax errors (a missing bracket, a bad indent, `> >`). It does **not** check types or whether a function exists. TradingView can still reject a script that parses.
* **If TradingView shows an error**, paste the error text to Nemo, for example *line 45: Undeclared identifier 'x'*. Nemo fixes the last script it sent and checks the fix again.
* **The survival script is not advice and has not been backtested by me.** It is Nemo's own rules written as a strategy. Run it in TradingView's Strategy Tester and on paper first.
* **On a NIFTY chart it trades the index itself as a stand-in.** Nemo's trading agent buys an at-the-money CE or PE on the same signal. Option premiums are not on the index chart, so the agent's −30%/+50% premium stop and target can't be reproduced there. The script uses the agent's other rule: stop 1.5 × ATR, target 3 × ATR [code].
* **No order, no trade, no change to the trading agent, guards, owner lock or credentials.** It writes a `.pine` file and sends it to you; it emails the file only when you ask.

## 1. What went wrong [code]

1. Every message you type goes first to the AI intent router (v72). For "create a new pine script" the router asked a question. For your answer it chose **work**: the general work planner (W71).
2. The work planner plans search and drafting steps under a **3-minute budget**. It finished two steps, ran out of time, and reported only the internal code `WORK_BUDGET_REACHED`.
3. Nemo has had a proper Pine engine since v11.29 (verified templates, a linter, a repair loop). Its fixed route sits in the older handler **behind** the router, so it was never asked.
4. Nothing in Nemo knew what "your survival logic" means for a Pine Script.

## 2. What v107.1 does

| You say | What happens | AI used? |
|---|---|---|
| "create a pine script with your survival logic(s)", "your own rules", "Nemo's strategy", "godmode" | **Nemo Survival Strategy** (section 3), built from a fixed, checked template | **No** |
| …plus settings: "risk 2% per trade", "2 trades a day", "long only", "lot 65", "capital 50000", "stop after 1 loss", "daily loss 2%", "weekly loss 5%", "stop 2 atr", "target 4 atr", "score 5", "signals on hourly", "entries between 9:30 and 14:00", "square off 15:00" | The same script with those settings. Each is kept inside a safe range (risk 0.1–5%, at most 10 trades a day, entries inside 09:15–15:30). The message lists what your words changed | No |
| "make it long only" right after a script arrived | The same survival script again, **keeping** your earlier changes | No |
| "create a new pine script", "/pine" (no details) | A choice card: 🛡 my survival strategy (first), EMA crossover, Supertrend, opening range breakout, VWAP reversion, RSI + trend filter, confluence. Or describe your own rules | No |
| A card button for a ready-made script | That script from Nemo's verified library, at once | No |
| "pine script: buy when RSI crosses 30 above the 200 EMA, stop 1%, target 2%" | The AI writes it, Nemo checks it, the AI fixes problems (at most twice, within 8 minutes). If it still fails, Nemo sends a checked script for the same approach **and says why** | Yes |
| "survival logic but use supertrend for the entries" | The AI changes the survival script. Every survival rule must still be in it, or the AI is told to put it back | Yes |
| "add a trailing stop to that script" | The AI changes the last script. If the change fails the checks, the old script stays and no new file is sent | Yes |
| A TradingView error ("line 45: Undeclared identifier …", "Syntax error at input …"), or a script pasted with its error | The last script (or the pasted one) is fixed and checked again | Yes |
| "my pine script shows an error" (no error text) | Nemo asks for the exact error line | No |
| "… and email it to x@y.com" / "mail it to me" | Also emailed, as the old Pine route did | No |
| "send the pine file again", "pine status" | Sends the file again; shows the last script, whether the grammar parser is installed, and counts | No |

* **Questions stay ordinary chat** [tested]: "what is pine script?", "how do I add a pine script to the chart".
* **Only you**, in your private chat [tested]. Other people, groups and card buttons pressed by others get nothing.
* **The router can't misroute it again** [tested]:
  * Pine requests go to the Pine engine **before** the router.
  * If the work planner still receives one, it hands it to the Pine engine. Research *about* Pine ("compare Pine libraries and make a PDF report") still goes to the planner.
* **The router's own clarifying question counts too** [tested]. When the router asks a question about a Pine Script, your answer in the next 15 minutes ("with your survival logics") reaches the Pine engine.
* **"Out of time" now reads in plain words** [tested]. When any work plan runs out of its 3-minute limit, the message says so: *"Work W71-… stopped: it ran out of its 3-minute limit after 2 of 4 steps (search, search). Nothing was sent anywhere and nothing was changed."*

## 3. Nemo Survival Strategy: the rules, and where each comes from

**The signal is Nemo's GODMODE score** [code: `godmode_analyze`], computed on **completed** bars of the signal timeframe (daily by default). Completed bars only means `request.security` with `lookahead_on` on the previous bar, so the backtest does not repaint. The points:

| Points | Rule |
|---|---|
| ±2 | Price above a rising EMA20 above EMA50 (or below, for −2), only when the two EMAs are more than 0.15% apart (a real trend) |
| ±1 | EMA20 slope over 5 bars |
| ±1 | RSI(14) ≥ 55 or ≤ 45. Nemo's RSI uses simple averages, and so does the script |
| ±1 | MACD histogram above 0 and rising, or below 0 and falling |
| +1 / −1 | Within 2% of the high, or the low, of the last ~80 bars (about 3 months of days) |

It trades **only a strong signal: +4 or more** (or −4 or less for shorts, which you can switch off). That is the same threshold the agent uses [code].

**The survival rules** come from v99.1's "how I would try to survive" [code: `_n991_capital_texts`], the agent's settings [code: `AUTO`, `atr_levels`, `can_enter`, `must_square_off`] and the paper ledger [code: `_P75_DEFAULTS`]:

* one position at a time and never adds to a loser (`pyramiding=0`, entries only when flat);
* the stop (1.5 × ATR) and the target (3 × ATR) are attached the moment the order is placed;
* risk 1% of equity per trade (v99.1: "a prudent limit is 1 to 2%"). Whole lots if you set a lot size; never more than the equity, so no leverage;
* at most `AUTO['maxtrades']` trades a day (1 unless you changed it);
* stop for the day after 2 losing trades;
* no new trades once the day is down 3% or the week down 6%;
* intraday charts: new entries only 09:20–14:30 IST (the agent's entry window), and square-off from 15:10 (the agent's square-off time).

On the chart:
* stop and target lines;
* entry markers;
* a red background while a loss limit has stopped trading;
* a status table (score, RSI, trades and losses today, day and week P/L against the limits, status);
* three alerts.

**Small differences from the live agent, on purpose:**
* Nemo's EMAs start from the first price; TradingView's start from an average. The first few dozen bars can differ by a point.
* The live agent reads the day's unfinished candle; the script uses completed bars so its backtest is honest.

## 4. The grammar check (pynescript)

* **What it is** [source]: pynescript is a pure-Python Pine Script parser (LGPL-3.0, uses the ANTLR runtime). Nemo does not have it yet. Say **"install pynescript"** and Forge installs it after your approval.
* **What I measured** [parsed]:
  * Its first parse in a fresh process is slow, about 38 seconds for the survival script. That is a one-time warm-up of the parser's tables.
  * After that, a parse takes 0.1 to 0.2 seconds.
  * Peak memory was 35 MB.
* **How Nemo uses it:** the parser runs in its own process at the lowest priority. It is the first one the system would stop if memory runs short. It starts warming up while the AI writes, so it is ready when the script arrives.
* **What it is not used for:** the survival script and the library scripts are fixed. They passed the parser when this version was built [parsed], so Nemo does not re-parse them each time.
* **When it isn't there:** if pynescript is not installed, or a parse takes longer than 150 seconds, Nemo says that the grammar parse did not run. It never claims a check that did not happen [tested].

## 5. Tests (offline)

`tests/test_pine1071.py`: **50 tests**.
* With no parser installed: **49 run, all pass; the real-grammar test is skipped**.
* With `NEMO_PINE_PY` set to a python that has pynescript: **all 50 pass**. The survival script in three settings and all six library scripts parse; a broken line is reported at the right line number.

Covered:
* the screenshot message;
* the hand-over by the work planner;
* the plain out-of-time message;
* the choice card and its answers, the router's question, and the card expiring;
* every setting from words, and the safe ranges;
* "make it long only";
* AI scripts: repaired, falling back with the reason, the time budget, survival rules kept, grammar errors driving a repair, changes to the last script;
* TradingView errors, Python errors and ordinary sentences that are not Pine errors;
* questions passing through, and other people;
* the parser child: protocol, unavailable, too slow, looked up once;
* email, resend and an unconfirmed upload;
* status, forgetting, self-development lock, and no orders or secrets in the layer.

Mutation check: 31 deliberate bugs, each run against the tests (results in the commit message).

## 6. Simple checks to run through Nemo (after installing)

1. `create a pine script with your survival logic`. You get the explanation and `nemo_survival_strategy.pine` within seconds, with no "W71".
2. `create a new pine script`. You get the choice card; tap 🛡 or a ready-made script.
3. `make it long only` (right after 1). You get the same script with "Also trade strong bearish signals" off.
4. In TradingView: Pine Editor → paste the file → Save → Add to chart → Strategy Tester. **This is the step I could not do.** If it shows an error, paste the error line to Nemo.
5. `pine status`. It shows the last script and whether the grammar parser is installed.
6. Optional: `install pynescript` (approve the card). Then a custom script, e.g. `pine script: buy when RSI crosses above 30 and price is above the 200 EMA, stop 1%, target 2%`, should say "a full Pine grammar parse found no syntax error".

## 7. Files

* `nemotron_bot.py`: version **107.1**. New layer `# NEMO 107.1 - PINE`. One in-place change: the self-development tool may not edit `_n1071_` functions.
* `tests/test_pine1071.py`: the tests above.
* `docs/NEMO_V107_1_PINE.md`: this file.

## 8. Sources

* pynescript on PyPI and its metadata (version 0.3.0, LGPL-3.0-or-later, requires antlr4-python3-runtime ≥ 4.13.2): installed and run on the test machine.
* TradingView, "To Pine Script® version 6": https://tradingview.com/pine-script-docs/migration-guides/to-pine-version-6. I could not open it from the test machine; what I used came from search summaries:
  * `strategy.exit()` no longer ignores relative `profit`/`loss` when absolute `limit`/`stop` are also given. The survival script uses only relative ticks.
  * `for` loop end values are re-checked on every pass. The survival script's loop end does not change inside the loop.
  * There are no `na` booleans, and the default strategy margin is now 100%.
* Secondary summaries of the v6 changes: https://blog.traderspost.io/article/pine-script-v6-breaking-changes, https://blog.traderspost.io/article/convert-v5-strategy-exit-to-v6, https://blog.traderspost.io/article/pine-script-dynamic-for-loops [not verified against the official page].
