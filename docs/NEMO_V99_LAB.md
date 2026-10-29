# Nemo v99: Lab (what-if tests on the practice trading agent, read only)

One release, one file (`nemotron_bot.py`, version 99.0).

You said "build next". The next item on the list from the ledger release (`NEMO_V96_LEDGER.md`, section 4A) is a laboratory beside the stock-market agent. Your own ledger showed why it matters: most of the profit came from exits booked beyond the plan (carried overnight) and a handful of trades carried the result. The closed trades cannot say whether a different rule would have done better, because the agent keeps *where it bought and where it sold*, not *the road in between*. Lab keeps the road and replays rules over it.

**Nothing in v99 places, changes or simulates an order, and nothing changes what the agent does.** It does not switch any rule of the agent, and it does not touch the trading guards (holiday guard, entry window, daily loss limit), the owner lock, Circle, Desk or any credential. What it adds is observation: it copies the quotes and decisions the agent already makes, and (switchable) asks for one more quote per check for a contract the agent has just sold.

---

## 1. How you use it (owner only, in your own private chat)

| Say | What you get |
|---|---|
| `lab` | The agent's own rule against 11 other rules, after charges, on the same trades, with a plain verdict for each (section 3). |
| `lab what if stop 20 target 40` | Your own rule, tested the same way. Also: `break-even 25`, `trailing 20/15`, `time 60/10`, `never overnight`, or several together. |
| `lab excursions` | How far each trade went (best and worst price while held), how many went up 25% and then ended below the buying price, what happened after a stop-loss or a target sale. |
| `lab direction` | Did the index move the way the agent expected between buying and selling, and how often the option still made or lost money against that. |
| `lab why` / `lab why yesterday` / `lab why week` | Why the agent did or did not trade: every check (about every 2 minutes) with its reason, how many AI questions were used, and a "most recent changes" list. |
| `lab week` / `lab month` / `lab last week` / `lab last month` | A period report with the results, best and worst day, worst dip, trades carried overnight, the reasons for no entry, a CSV file and a growth chart. **Also sent by itself on the last trading day of the week and of the month**, after the day-end card (once each). |
| `lab ready` | An advisory checklist before real money (section 6). |
| `lab alerts` / `lab alerts streak=5 dip=20000` / `lab alerts off` | The two alerts (section 5). |
| `lab follow off` / `on` | The follow-through after a sale (section 2). |
| `lab weekly off` / `lab monthly off` | Switch the automatic reports. |
| `lab status` / `lab help` | What is being recorded; the list of commands. |

Add `live` (or `real`) to look at real-money trades instead of the virtual ones: `lab live`. Plain sentences work too: "what if the stop was 20% and the target 40%", "which exit rules would have done better", "how far do the trades go", "is the agent right about the direction", "why did the agent not trade today", "is the agent ready for live", "weekly trading report". A sentence is only taken when it is clearly about this: "lab report for my blood test", "why did you not trade" (the guard's own phrase) and everything in the ledger are left to their own handlers (tested).

The day-end card also gets one more message **on a day with no trade**: "No trade today. The agent checked 98 times and each time: 61 × the AI looked and chose no trade, 22 × outside the entry window, …". And the older guard status ("check trading safety") ends with the same reasons when there are any.

## 2. How it works, in plain words

**The recorder.** The agent asks the broker for a quote of its open position at every check. Lab keeps a copy of that quote (bid, ask, last price, trade time, and whether the agent's own quality test would accept it: "clean"). The quote the agent *bought on* starts the path. No extra broker call is made for this. Paths are saved in Nemo's database; trades from before v99 have none (they are used only for the entry rules, section 3).

**Index levels.** When a position is opened and when it is sold, one price lookup of the index (or the share) is made, for the direction report. Two lookups per trade.

**Follow-through (switchable, on by default).** After the agent sells, Lab keeps asking for one quote per check of that contract until 15:12 that day (not after a 15:10 square-off sale, not on a closed market, five failures in a row stop it). That is the only extra broker traffic of this release: market-data reads, no orders, at most one per check from the sale to 15:12 (up to about 140 on a morning sale, about 65 on an early-afternoon one), none on a day without a trade or after a 15:10 square-off sale. It is what makes it possible to ask "did the price come back after the stop?" and to test rules that would have held on longer. `lab follow off` stops it; the wider-rule tests then cannot use the trades recorded after that.

**The replay.** For each closed option trade with a complete record Lab replays the agent's own rule (stop -30%, target +50%, out at the 15:10 square-off, in that order, using the levels the agent saved, accepting only clean quotes) and **it must reproduce the agent's real exit price and reason**. A trade where it does not, a trade with a hole of more than 12 minutes in its record, a trade with no entry record, and every share trade are **left out and counted by reason**, never guessed. Only then are other rules replayed over the same road.

**The rules (the 11 in `lab`).**

| Rule | Definition |
|---|---|
| As the agent | stop -30%, target +50% (the baseline) |
| Tighter | stop -25%, target +40% |
| Wider | stop -40%, target +70% |
| Target +30 | stop -30%, target +30% |
| Break-even at +25 | as the agent, but once the price has been 25% up the stop moves up to the buying price |
| Trailing 20/15 | stop -30%, **no fixed target**; once 20% up, the stop follows 15% below the high |
| Time exit 60m | as the agent, plus out after 60 minutes unless up 10% |
| Never overnight | as the agent, but sold at the last clean quote of the day it was bought |
| Skip near expiry | *entry rule*: do not take contracts with fewer than 2 days to expiry |
| Skip before 09:50 | *entry rule*: do not buy in the first 30 minutes |
| AI conf 8+ | *entry rule*: only trades the AI rated 8/10 or more (a trade with no stated confidence counts as not shown to be high) |

Entry rules can only **remove** trades the agent took. They can never add a trade the agent did not take, because nothing is known about those.

**What stops it from fooling you.**
- **No winner on a few trades.** Under 30 trades a rule only gets "too few trades (N of 30 needed)". From 30 trades a clear difference is "early sign of better/worse"; "worth a closer look" needs **60 trades**, a clear difference (t value of 2.5 or more, stricter than the usual 2 because 11 rules are tried at once and one always looks good by luck) **and the same direction in both the earlier and the later half** of the trades.
- **Same trades on both sides.** Every line says "against the agent's ₹… on the same N trades", and says how many trades were left out because the record ends before that rule would have sold.
- **A rule that never triggers** is squared off at the end of the day when the record followed the contract to the end of that day (like the agent's own 15:10 rule). Without that, wider rules would only be compared on the trades where they happened to win, which flatters them. Where the record stops earlier the trade is left out.
- **Your own `what if`** carries a reminder that a rule picked after seeing the results is easier to flatter than the list.
- **Blind spots stated:** prices are read about every 2 minutes (a spike between two checks is invisible, to the agent as well), virtual buys are at the ask and sells at the bid, real orders fill later and worse.

## 3. Why not, overlaps and the AI bill

Every check of the agent that ends without an entry is saved with its reason, read from what the agent did during the check (what the AI said, what the price checks said, which guard stopped it) and from the same conditions the agent tests, in the same order. The reasons: the AI chose no trade (with its words), the AI leaned to a trade but was under 6/10, the AI gave no usable answer, no index had a strong enough signal (the fixed-rules brain, with the strongest read), the price checks refused the entry, no option contract found, a share not on the watchlist, outside the entry window, entries paused, market closed or calendar not verified, master lockdown, daily loss limit, today's trade limit, broker halted or not logged in, an error in the check, or "reason not recorded".

`lab why` also counts **how many questions were put to the AI**. This is a finding, not a guess (section 4, item 2).

## 4. What I found while reading the agent (nothing here was changed)

1. **The road is not kept.** A closed trade has the buy price, the sell price, a reason and a time. That is why rules could not be tested before. (Solved by the recorder.)
2. **The AI is asked at every check that gets as far as a decision.** The scheduler wakes every minute, runs a check every second minute from 09:15 to 15:35, and the entry window is 09:20 to 14:30: up to about **155 AI questions on a day in which the agent finds nothing** (`ask_ai(..., deep=True, timeout=180)` each). Whether that matters depends on your AI plan. `lab why` now shows the count.
3. **Two checks can overlap.** The scheduler starts a new check in its own thread every 2 minutes and never waits for the last one; `auto_trade_tick` has no lock, and the brain gate allows 3 AI calls at once. The AI step has a budget of up to 100 seconds per request and the answer chain can fall back to further providers. If an answer takes longer than the gap, a second check starts, finds no open position yet, asks the AI too, and **both can buy**: the second position replaces the first in the agent's memory (the first is never booked) and the day's trade counter goes over the limit. In live mode that would be two real orders. I could not tell from the code how often an answer is that slow. **Lab now counts overlaps (`lab status`, `lab why`) and, if the day's trade count goes over the limit, tells you once that day.** I did **not** change the agent. A guard that skips a check while one is running is a small change; I will propose it as its own release if the counter ever shows an overlap.
4. **The stop and target are computed from the price seen before the quote the agent buys on** (for example levels 70.0 and 150.0 from 100.0, bought at 100.2). The effect is a fraction of a percent; the replay uses the saved levels so that it matches.
5. **A weakness in the ledger's own join (v96), not fixed here:** the entry details are matched to a closed trade by contract and entry price. Two trades of the same contract at the same entry price could be matched to each other's entry time. It is rare. Lab leaves out any trade whose record does not reproduce its sale, so this cannot flatter a rule.
6. **"Why didn't you trade" only ever showed the last guard message** (`Last guard result`); the reason of an ordinary "no" from the AI was not kept anywhere. Now it is.

## 5. Alerts, weekly and monthly reports

- **Losing streak** (default 4 in a row, after charges) and **deep dip** (default: 5 times your daily loss limit below the high point, so ₹15,000 at the default ₹3,000; set your own number). Each alert is sent **once** to your private chat only (not to the phone push, not to WhatsApp), and again only after the streak was broken or the dip eased to half the limit. The first look after install is silent about history. Virtual and real trades are looked at separately and an alert says "LIVE (real money)" when it is.
- **Weekly and monthly reports** are sent after the day-end card on the last trading day of the week and of the month (a Friday holiday makes Thursday the last; the calendar is the agent's own), once each, only if there were trades in the period. CSV and chart are attached.
- Both can be switched off. Nothing in an alert or a report changes anything.

## 6. `lab ready`: a checklist, not a gate

Seven checks on the virtual record: at least 60 trades over at least 20 trading days; a profit after charges; the low end of the win-rate range above the break-even rate; the worst dip within your limit; no single trade made more than 40% of the profit; the last 20 trades are profitable too; less than half of the profit comes from trades carried over a night. Checks that depend on there being a profit are marked "not applicable" (not passed) when there is none. It says "advice only": **`/autotrade live` is neither blocked nor changed.** A refusal in the live switch would change the live path, so it is not built; say so if you want it.

## 7. What was verified, and what was not

**Verified offline (automated tests, 186 new):**
- the replay engine as pure numbers: stop, target and square-off in the agent's order, only clean quotes sell, quotes before the purchase are ignored, break-even, trailing, time exit, never-overnight, rounding the way the agent rounds, the saved levels, holes in the record, a path that ends before a rule sells (unknown, not guessed), a complete record squaring a rule off at the end;
- which trades are usable (every exclusion reason) and that the agent's own rule must replay to its real exit;
- the numbers of each rule on a small set of trades worked out by hand; the entry rules without a price record; the verdict ladder (under 30, 30 to 59, 60+, the two-halves test, the t threshold, the baseline); an end-to-end set of 62 trades where a break-even stop is better on every trade;
- **the real agent tick, end to end** (broker, quotes, AI, calendar and clock stubbed): the AI says buy a put, the agent buys, the record starts with the quote it bought on, the index level is noted, the stop sells, the record follows the contract, then the trade is replayed and the rules compared; **and that the agent's state, log and reports are identical with and without the lab's hooks**;
- the "why not" classification for every reason in the agent's own order, the storage (counts per day, the latest detail, a bounded event list), the status line of the older guard, the decision wrappers passing results and errors through unchanged;
- excursions, direction (right, wrong, flat; late lookups left out), `what if` parsing (ranges, refusals), weekly and monthly (bounds across year ends and leap years, the last trading day with holidays, once only, not when someone asks for the card, off switches), alerts (first look silent, one per streak, re-arm, dip, limits, live wording, owner only, no phone push), overlap counting, the over-limit notice, the readiness checklist;
- the front door: 18 commands and 19 plain sentences taken; 24 other sentences left alone (including the ledger's and the guard's own phrases and "lab report for my blood test"); a guest, a file, a picture, a group are not served; no broker or AI call; **the agent's state unchanged by every command**;
- structure: the layer never assigns into the agent's state, reads only a handful of its keys (position, mode, brain, trade count and limit, loss limit, the day's result, watchlist), writes only its own five tables (and only reads the ledger's), calls nothing but the quote functions, the index price, the date and a message to the owner, contains no secret-shaped text.

**Not verified (cannot be from the test machine):**
- **A real trading day.** Nothing here ran against the live broker or a real Telegram chat. The replay was verified against the agent's own tick with scripted quotes, not against real exchange data: the first real check is the line "the agent's own rule gave its real exit price and reason on N of the M trades it was tried on" in `lab`. If that is far from "all", the record or the replay has a problem and I want to hear.
- **How often real quotes are "clean".** If many are not, more trades are left out of the tests.
- **Whether two checks ever overlap in practice** (item 3 above): the lab will tell.
- **Hindi or Hinglish phrases.** Only the English phrases in section 1 are recognised.
- **Real-money trades with exchange-side brackets.** The agent's exit is then made by the exchange at a price the lab cannot see; those trades will mostly be "did not replay" and left out. The lab is built for the virtual agent.

## 8. Try it, through Nemo

1. `lab status`: nothing recorded yet. Leave the agent in shadow mode as it is.
2. After the next trade: `lab` (the price record line should say 1 of 1 and the check "1 of the 1 trades"); `lab excursions`; `lab why`.
3. After a week: `lab week`. After a month or 30 trades: `lab` again, and `lab what if break-even 25`.
4. `lab ready` whenever you wonder about real money.
5. Switch things off any time: `lab follow off`, `lab alerts off`, `lab weekly off`, `lab monthly off`.

## 9. What changed in older code (everything else is in the new layer, marker `# NEMO 99 - LAB`)

1. The docstring, `VERSION`, and `'_n99_'` in the live-self-edit protection list.
2. Wrapped, the old function kept and called, its answer or error passed on: `handle` (the lab's commands, for the owner), `auto_trade_tick` (a note of what the agent decided, then a look at its state afterwards), `_n75_quote` and `live_ltp` (a copy of the quote or price of the open position), `ai_decide`, `godmode_analyze`, `_n81_entry_quote` and `_option_chain_failure_notice` (a note of what was decided during a check), `trading_day_report` (the no-trade line, the weekly and monthly reports), `_n81_status` (the reasons), `_n82_capabilities`, `_n83_status_text`, `_n88_abilities`, `prime_regression_suite` (8 more rows), `main`.
3. Tests: `tests/test_lab99.py`. The v98 structural tests now stop at the v99 marker.

## 10. What I did not build, and why

- **A second virtual agent with a different brain** (fixed rules instead of the AI, running side by side). It needs its own option-chain and quote calls for hypothetical positions and its own day counters; it is the right next step if the rule tests show that the exit rules matter little. Not started.
- **Switching a rule in the agent.** The lab shows; adopting a rule would be its own release, tried in shadow first.
- **The live-switch gate** (section 6).
- **The single-flight guard** (section 4, item 3), until the counter says it is needed.
- **Family access.** Lab is owner-only: Desk's family view shows the ledger and the explanation of the logic, as before.

## 11. Test results (offline, on the test machine)

- **Whole suite on the exact file delivered (the slow gate switched on): 2,647 tests, 6 skipped, 2,646 passed, 1 failed.** The one failure was not in the bot: a test of the Forge "upgrade from GitHub" feature used "99.0" as its example of a *newer* version, and the running version is now 99.0, so the upgrade check correctly refused it. I changed that fixture to 999.0 and re-ran that group (8 tests): all pass. I did not repeat the 23-minute full run for a one-number change in a test file.
- 186 of the tests are new (`tests/test_lab99.py`). The older suites that exercise the functions this release wraps (ledger, desk, scholar, care, doors, atlas, steward integration, studio+, scout: 790 tests) pass unchanged except for the v98 structural tests, which now stop at the v99 marker as the earlier ones did.
- Pyflakes: the same 158 messages as v98, none new. Credential comparison against v98: no change to any saved credential. A scan of the added lines for keys, tokens or passwords found none. Only two lines of older code were edited (the docstring's first line and the protection list); the lab itself is appended.
- Nothing here placed, changed or simulated an order, called a broker with an order, or used a paid service. The tests use scripted quotes and a fake clock.
