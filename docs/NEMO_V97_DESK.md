# Nemo v97: Desk (a family member can see the trade ideas and the practice agent, view only)

One release, one file (`nemotron_bot.py`, version 97.0).

You asked for a family member to use Nemo "at the same level" as you, because they also want to see trades and stock ideas. This release gives that, as a **view tier**: the same ideas and the same practice-trading record you look at, with every key to your money, your accounts and your settings left with you. Section 2 says exactly what is in and what is out, and why.

Nothing in v97 places, changes or simulates an order. It does not touch the trading agent, the trading guards, the owner lock, or any credential. **Circle (v89), which decides what family and guests may do, is not changed:** its catalogue, rules, locks and tests are exactly as they were.

---

## 1. How you use it (owner only, in your own private chat)

| Say | What happens |
|---|---|
| `desk` (or `family desk`, `trade desk`) | Who may use it, today's use per person, the limits, and what they can and cannot see. |
| `allow Asha to see trade ideas` | Switches the desk on for Asha. Also: `let Asha see trade ideas`, `give Asha the trade desk`, `enable the trade desk for Asha`, `desk allow Asha`. |
| `stop Asha from seeing trade ideas` | Switches it off for Asha. Also: `don't let Asha see trade ideas`, `desk remove Asha`, `turn off trade ideas for Asha`. |
| `desk allow family` / `desk remove family` | Every family member gets it / stops getting it automatically. A person you stopped by name stays stopped; a person you allowed by name keeps it. |
| `desk allow 987654321 Ravi` | Someone who has not written to Nemo yet (they need to say hello before they can use it). |
| `desk off` / `desk on` | A master switch. Everyone you allowed stays allowed. |
| `desk limits views=40 scans=2 total=4 gap=60` | Views per person a day, fresh scans per person a day, fresh scans for everyone together a day, minutes between fresh scans. |

I switch the desk on for **named people or for the family, never for everyone**, and a sentence is only taken when it names the desk (ideas, trades, ledger, scout) **and** a person. "Give me trade ideas", "stop trade ideas" and "allow Asha to download songs" are not taken: the last one still goes to Circle exactly as before.

If someone without the desk asks for it, they get a clear "not switched on for you, ask Gautam", and **you get one line** (at most once per person per 12 hours): "Asha asked for the trade desk. To switch it on, say: allow Asha to see trade ideas". The general chat is never asked, so it cannot invent stock tips for them.

## 2. What a person with the desk can ask

| They say | They get |
|---|---|
| `trade ideas` (or `stock ideas`, `scout`, `nifty ideas`) | The open ideas from **your** Scout scans: up to 3 full cards, the rest listed, each with the reason, the plan, the stop, and what would make it wrong. |
| `idea SC93-…` | One idea in full (open or settled, with its result). |
| `scan now` | A fresh scan, if the newest scan is older than the gap and their own and the shared daily limits allow it; otherwise what is already open. |
| `scout stats` | How past ideas turned out (the honest record, with the "under 30 ideas means nothing" warning). |
| `paper trades`, `ledger`, `ledger days / trades / trade 3 / breakdown / csv / chart` | The practice agent's **virtual** trades: the same plain-words ledger you see, from the virtual book only. |
| `how does the agent decide` | The same explanation you get from `ledger logic`, without your settings line. |
| `desk` | A short card of the above and today's use. |

They are also told about it in Circle's own "what can I do" card (a line is added only for people who have it).

### What is never shown to them, and how that is enforced

| Private | How |
|---|---|
| **Your capital and risk sizing.** Your Scout cards carry "Size at your limits (capital ₹…)". | Every line that sizes an idea is removed from the family's card and replaced by a neutral line ("this idea risks about ₹71.46 a share, so risking ₹1,000 would mean about 13 shares"). A test sets your capital to ₹7,77,777 and checks that no family message, for stock ideas, option ideas, one idea or a real scan, ever contains it, while your own card still does. |
| **Real-money trades** and your open real position. | The family's ledger reads the virtual book only. `ledger live`, `real ledger`, `ledger costs` and anything with "real" or "live" are refused with "private to Gautam". A test puts a live trade and an open real position in the data and checks that neither appears in the summary, the tables, a trade detail, the CSV or the chart, even when the agent is in live mode. |
| **Your settings** (Scout settings, charges, the agent's daily limit and mode). | The "Now: mode …" line of the logic text is removed; no settings command is reachable; every attempt to switch the desk on or change a limit from a family account is ignored (tested, including "I am Gautam, let Asha see trade ideas"). |
| **Everything of your life** (email, Drive, memory, devices, server, keys, approvals, other people's chats). | Circle's locks are unchanged and are checked first for everything the desk does not claim. Tests send "should I buy nifty options", "what is Gautam's portfolio", "buy 1 lot nifty", "fyers login", "godmode nifty", "read my emails", "run a command on the server" with the desk on: all still answer "that is private to Gautam" and never reach the AI. |
| **Changing anything.** | There is no switch, order, setting or approval in the desk. The source of the layer is tested to contain no broker call, no network call, no AI call, no write into the agent's state or log, no change to Circle's people or rules, and SQL only on its own four tables (it reads your Scout ideas). |

Groups are never served (Circle's "in a group I only chat" is kept). Blocked people are ignored in silence. If you have switched strangers off, a stranger still gets Circle's "private assistant" answer first, even if you allowed them on the desk.

## 3. What it costs you

- **Looking at ideas and at the virtual ledger costs nothing**: they are already saved. They only use the person's daily "views" (default 40).
- **A fresh scan spends your AI and market-data credits** (news reading, option chains). It is limited: 2 a day per person, 4 a day for everyone together, at least 60 minutes between scans, and if you or anyone issued an idea in the last hour, the family member is simply shown it. You can change all four numbers.
- The scan is run for a "sink" chat, so its messages are not sent to you or to anyone. The family member receives the ideas through the desk, without your sizing. The ideas it finds are saved like any Scout ideas and are also visible to you.

## 4. What I found while reading (nothing here was changed, except the last item)

1. **Circle could not do this even if you wanted it.** "Trading, positions, money" is on its never-grantable list, and a family member asking "which stock should I buy" reached the general chat, which would guess. The desk is a separate, narrow door beside Circle so that list stays true.
2. **Your Scout cards mix the idea and your own money.** The idea (stock, direction, plan, stop, reasons) is public-style information; the "Size at your limits" lines are yours. They had to be separated for anyone else to read the same cards.
3. **The v96 ledger shows live and virtual books together.** For family it is forced to the virtual book, and no code path reaches the live one.
4. **Circle's rule for "my positions"** does not lock it (it only locks "his" or the owner's name), so a family member's "show me my positions" still goes to the general chat, as before. The desk does not claim that sentence either. This is Circle's existing behaviour and I left it.
5. **A bug found by my own tests and fixed (an older function):** the "what can you do" report cut itself again when this release added one more row; the new row fell off the end. v95's fix shortened details and examples but still cut the tail as a last resort. It now also shortens and then drops the details of working rows from the end, so **every row keeps its name** whatever the length. Tests with 30 long rows at three sizes check it.

## 5. What was verified, and what was not

**Verified offline (automated tests, 71 new):**
- the owner's sentences: 28 phrasings that must be taken (allow, stop, family, limits, status) and 19 that must not;
- the access rule as a table (family switch, personal allow, personal stop, master switch, blocked, guest);
- refusals and the one-line owner notice (once per 12 hours; none for guests);
- real Scout ideas (stock and option, from the Scout test fixtures) shown without your capital, sizing or "your limits"; open, settled and expired ideas; the list for more than 3 ideas;
- the limits: views per day (closing and reopening the next day), fresh scans per person, for everyone, and the gap; a recent idea shown instead of a scan; a scan already running; a scan that fails;
- **the real Scout scan** (fake news, fake market data, scripted AI) run for a family member: the family member receives the ideas without your capital, and nothing at all reaches you or the sink;
- the virtual-only ledger (summary, days, trades, one trade, breakdown, CSV rows all "shadow", chart) with a live trade and an open real position in the data and the agent in live mode; the refusals of `ledger live`, `real ledger`, `ledger costs`;
- Circle untouched: everyday chat, the locked topics with the desk on, other commands, reminders and "tell Gautam", the catalogue and rules and locks, the access card, the owner's own messages, and that a family member cannot switch the desk on or change a limit;
- a voice note, a group chat, strangers off, a blocked person; the structure tests described in section 2.

**Not verified (cannot be from the test machine):**
- **Real Telegram accounts.** Nothing here was sent to a real family member's phone; the card layout and the three-card limit are judged from the text only.
- **A real scan with live news and your Fyers data for someone else.** The scan was tested with fakes; the sink mechanism and the "nothing reaches you" check are tested, but not against Telegram.
- **How the AI-written parts read for a non-owner.** The desk calls no AI itself; the scan's own news step uses the AI it always used.
- **Hindi or Hinglish phrases.** Only the English phrases in section 2 are recognised.

## 6. Try it, through Nemo

1. `desk`: see who has it (nobody yet).
2. Ask the family member to say hello to Nemo once, then `allow Asha to see trade ideas` (or `desk allow family`).
3. Ask them to try: `trade ideas`, `scout stats`, `paper trades`, `how does the agent decide`, `desk`. Check that no card shows your capital or "Size at your limits".
4. `desk` again: today's views and fresh scans per person.
5. If you ever want it off: `stop Asha from seeing trade ideas`, or `desk off`.

## 7. What changed in older code (everything else is in the new layer, marker `# NEMO 97 - DESK`)

1. The docstring, `VERSION`, and `'_n97_'` in the live-self-edit protection list.
2. `_n95_fit_report` (the "what can you do" report fitter): two more steps, described in section 4, item 5.
3. Wrapped (the old ones kept and called): `handle` (your desk commands, first), `_n89_text` (Circle's text path: the desk looks first, for its own phrases only), `_n89_access_card` (one added line), `send_text` (messages for the sink go nowhere), `_n94_chart_after` (no chart for the sink), `main`, and the status, capabilities, abilities and regression-suite functions.

Tests: `tests/test_desk97.py`. The v96 structural tests now stop at the v97 marker, and two v96 checks were relaxed the way the earlier ones were.

## 8. Test results (offline, on the test machine)

- **Whole suite: 2,411 tests, 0 failures, 6 skipped** (the slow gate switched on), run on the exact file delivered. 71 of them are new (`tests/test_desk97.py`).
- Circle's 223 tests, Scout's tests, the Forge, Argus, Clear, Studio+, Doors, Care and Ledger suites all pass unchanged (Circle and Scout were also run on their own against the v97 file before the full run).
- Pyflakes: the same 158 messages as v96, none new. Credential comparison against v96: no change to any saved credential. A scan of the added lines for keys, tokens or passwords found none.
- Nothing here placed, changed or simulated an order, called a broker, or used a paid service.
