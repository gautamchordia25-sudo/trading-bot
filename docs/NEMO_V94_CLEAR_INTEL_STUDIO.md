# Nemo v94: Clear + Scout intel + Studio+

One release, one file (`nemotron_bot.py`, version 94.0). It does three things:

1. **Clear**: every market reply and every data dump Nemo sends is in plain words.
2. **Scout intel**: Scout can read what NSE publishes (results dates, F&O ban list, corporate actions, FII flows), cross-check Nemo's holiday table, and compare option prices with a volatility forecast.
3. **Studio+**: real AI enlarging of pictures, background removal with no key, and a chart under every Scout idea.

Nothing in v94 places, changes or simulates an order. It does not touch the trading agent, the trading guards (including the holiday guard), the owner lock or any credential. Everything is owner-only, like Scout.

---

## 1. Clear: "I can not understand the `/chain55 NIFTY` reply" (fixed)

### What was wrong

`/chain55 NIFTY` sent the raw data structure, cut at 3,600 characters:

```
{"ok": true, "symbol": "NIFTY", "spot": 22421.95, "atm": 22400.0, "pcr_oi": 1.2, "expiry": "06-10-2026", "iv": null, "timestamp": null, "rows": [{"symbol": "NSE:NIFTY26O0621800CE", "type": "CE", "strike": 21800.0, "ltp": 661.9, ... "iv": null ...
```

It had no words, `null` where the broker sent nothing, and the first 12 of 50 rows, which are the cheapest strikes, far from the price. The same was true of the other 24 MarketOS commands, and about a hundred diagnostic commands print JSON too.

### What it is now

```
📊 NIFTY OPTION CHAIN, in plain words

Index now: 22,421.95 · nearest strike to it (“at the money”): 22,400
Expiry: 06-10-2026 · about 2.1 days left
Put/Call ratio: 1.20 (open puts 40.25 lakh vs open calls 34.25 lakh) → slightly more puts than calls: balanced to mildly supportive.

Strikes around the price (prices are ₹ per unit; OI = contracts still open):
22,350 │ Call ₹145.78 · OI 74,074 │ Put ₹65.63 · OI 74,074
22,400 ◀ price │ Call ₹116.59 · OI 1.00 lakh │ Put ₹86.41 · OI 1.00 lakh
22,450 │ Call ₹91.30 · OI 74,074 │ Put ₹111.11 · OI 74,074
 … (11 strikes around the price)

Most open call contracts above the price: 22,600 (25.00 lakh). Traders often treat this as a ceiling.
Most open put contracts below the price: 22,200 (31.00 lakh). Traders often treat this as a floor.
So many traders are set up for NIFTY to stay between 22,200 and 22,600. That is a tendency, not a promise.

A call and a put at 22,400 together cost ₹203.00. That is how far the market expects the index to move by expiry: about ±203 points (±0.9%).
Implied volatility at the money: 15.0% (normal) · worked out by Nemo from the option prices, because the broker did not send it
How to read it: a Call gains when the index rises, a Put gains when it falls. ...
ℹ️ Information only. Nemo placed no order and nothing was changed.
```

### Everything else

| Where | What changed |
|---|---|
| The 25 MarketOS commands (`/mdata55` … `/footprint55`) | Each has its own plain-words reply: what the numbers are, what they say, what to watch, an "In plain words" line and a caveat. Rupees, lakh and crore. A failed command says why in words and what to do (for example "send /brokerurl"). |
| Any other JSON dump (about 100 diagnostic commands, today's and tomorrow's) | A safety net in `send_text` turns a message that is a JSON object (with an optional short title) into readable lines: humanised names, rounded numbers, Indian grouping, dates for epoch times, no braces or quotes. A dump that was cut to fit a message is closed at the last complete item and says it was cut. Ordinary messages are never touched. |
| The option-chain reader | The broker sends no implied volatility. The reader now solves it from each option's own price (same solver Scout uses), before the snapshot is stored. Greeks, the IV surface, the strike ranking and the before/after price breakdown work on this server too. |
| Trading words | "what is PCR", "what does theta mean", "explain open interest" … answered instantly from a built-in glossary of 50+ words: no AI call, no cost. "glossary" lists them. |
| "guide" | A one-screen list of what you can say, by theme. |
| "plain off" / "plain on" | `plain off` shows the raw data again everywhere; `plain on` (the default) brings the words back. |

---

## 2. Scout intel (needs `nselib`, `exchange-calendars`, `arch` installed through Nemo)

Each source runs in a short-lived separate Python (never inside the trading bot): niced, clean environment (none of Nemo's keys), one at a time, only when memory is free, answers cached (6 h results/actions/flows, 3 h ban list, 24 h calendar, 12 h forecast). A failure is cached for 30 minutes so a blocked website cannot slow every scan (busy or low memory: one minute). When a source cannot be read Nemo says so in one line and goes on; nothing is guessed.

| Source | What Scout does with it |
|---|---|
| NSE results calendar | Results due **today or the next session** → no new idea on that stock ("a stop cannot protect against a results gap"). Within 4 sessions → the existing `results_due` penalty (−8) with the exact date. Otherwise a line on the card. |
| NSE F&O ban list | A stock in the ban period: −6 and a clear line. |
| NSE corporate actions | A split, bonus or merger ex-date inside the trade window: −4 (the price will be adjusted and a stop set now would be wrong). A dividend is a line only. |
| FII flows (index futures buy/sell, FII/DII/Pro/Client positions) | One more small part (weight 0.15) in the NIFTY/BANKNIFTY option view, only when it was read. The data is one day old; the report says so. |
| arch (GARCH) forecast | A line on every option idea: "recent behaviour points to about X% a year; the option is priced at Y% → dear / cheap / about right". It never changes the score or the plan; it adds a point against an outright buy when options are dear and one in favour when they are cheap. |
| exchange-calendars | `holiday check` compares Nemo's 2026 holiday table with the library for the next 120 days. |

**Important finding (not a bug, but you must know):** Nemo's holiday table covers **2026 only**. From 1 Jan 2027 his guards treat the calendar as "unverified" and keep **new trade entries closed** until the table is updated (fail-safe, as designed). The exchange-calendars library ends 31 Dec 2026 too, so 2027 cannot be filled automatically yet. NSE normally publishes next year's list in December: say `holiday check` then, and the next version can load it. Nemo's guards were not changed.

New things you can say (owner only): `scout intel` (status, `on`/`off`), `results RELIANCE` / `when are TCS results`, `ban list`, `fii flow`, `volatility forecast nifty`, `holiday check`.

---

## 3. Studio+

| Tool | Behaviour | Measured (test machine: 4 cores, 16 GB; your server is about 2× slower) |
|---|---|---|
| AI enlarging, Real-ESRGAN (`realesrgan-ncnn-py`) | Replaces the plain Lanczos enlarge for **2×** (input up to 1280 px, art/general model, tiled) and **4×** (input up to 320 px, photo model). Anything else (3×, bigger pictures, low memory, tool missing) uses the old method, and the picture note says which was used and why. The note on an AI result warns it adds plausible detail, so it is not for evidence or documents. | ×2 1024→2048: 16 s, 225 MB. ×4 160×120→640×480: 20 s, 1.8 GB. Needs the system libraries `libomp5` and `libvulkan1` (`forge apt allow libomp5 libvulkan1`, then `forge apt libomp5 libvulkan1`). |
| Background removal, rembg (`silueta` model) | A plain background is still cut out by colour first (free, instant). A busy background goes to the AI model, **no key needed**; remove.bg (key) is only the last resort. Works on a small copy, so memory does not grow with the picture. | 809 MB, 1–3 s. Downloads a 43 MB model on first use. |
| Chart under each Scout idea | Drawn with Pillow in the bot (no extra install): last 60 daily candles, the 20-day average, entry zone, stop, T1, T2, a footer "not advice". Sent right after the idea card. `scout chart SC93-XXXXXX` draws one for an older idea; `scout charts off` stops it. | Under 100 KB, well under a second. |

`studio ai on` / `studio ai off` switches both AI tools. `studio status` shows what is ready and what to say to get the rest.

---

## 4. What was verified, and what was not

**Verified offline (automated tests, all in this repository):**
- the reply formats for all 25 MarketOS commands (against the real result shapes), the user's real chain shape, the JSON safety net (including cut-off dumps and the kinds of ordinary text it must not touch);
- the implied-volatility fill against the broker's real payload shape;
- the NSE readers against the exact table shapes in the installed `nselib` source; the **real helper program** was also run against a stand-in `nselib` (and the real `exchange_calendars`: its 2026 weekday holidays are identical to Nemo's table; and the real `arch`);
- caching, negative caching, memory refusal, one-job-at-a-time, never an order, never a key in a helper's environment;
- the AI-enlarge and rembg wiring with scripted stand-ins, every fallback, the notes under pictures, and the real chart drawing.

**Not verified live (cannot be from the test machine):**
- **NSE itself**: NSE blocked the test machine, so the real `nselib` calls were never answered. The column names of the results and corporate-action tables are matched without regard to case and spaces, but they come from NSE's website and have changed before. If NSE blocks your server too, Scout says "NSE could not be read" and carries on as in v93.
- **Real-ESRGAN and rembg on your server**: measured on a 4-core test machine; your server will be slower and has less memory. The memory guard refuses when there is not enough, and the old method is used.
- **How Telegram shows the new layout** (spacing of the `│` strike table on your phone).

---

## 5. Try it, through Nemo

1. `/chain55 NIFTY` (after Fyers login): the new readable reply. (`/brokerurl` if it says Fyers is not connected.)
2. `what is PCR`, `glossary`, `guide`.
3. `/oi55 NIFTY`, `/move55 NIFTY`, `/mtf55 NIFTY`: plain words.
4. `plain off` then `/move55 NIFTY` (raw), then `plain on`.
5. `scout intel`: shows what is installed. To add the intel: `install nselib into yourself`, `install exchange-calendars into yourself`, `install arch into yourself` (you approve each card). Then `ban list`, `results RELIANCE`, `fii flow`, `holiday check`, `volatility forecast nifty`, `trade ideas`.
6. `studio status`, then for pictures: `install rembg`, `install realesrgan-ncnn-py into yourself` plus the two `forge apt` lines it names.

## 6. What changed in older code (everything else is in the new layer, marker `# NEMO 94 - CLEAR`)

1. The docstring and `VERSION`.
2. `'_n94_'` added to the live-self-edit protection list.
3. `_n55_option_chain_struct`: two lines solving the missing implied volatility before the snapshot is stored.
4. `_n90_apply_ops`: the note under an enlarged picture says how it was done.
5. `_n93_scan` and `_n93_symbol_job` card sends: a chart follows the card (two lines); `_n93_scan` header: one intel line.
6. `_n93_index_view`: the "volatility was solved" note also counts the chain reader's solving.
7. Replaced functions (old ones kept as fallbacks): `_n55_trim_result`, `send_text` (wrapper), `_n90_op_upscale`, `_n90_remove_bg_rembg`, `_n90_remove_background` (plain colour first, then the AI model, then the key).

**Test results (final file, version 94.0):** the whole suite, 2,083 tests, **OK**; the slow update gate was switched on (`NEMO_SLOW=1`) and passed. 6 tests skip themselves: 5 Wire tests that need the real libraries installed, and 1 that needs `nselib` to be absent. The v94 tests are 235 of those: `test_clear94` 64, `test_intel94` 90, `test_studioplus94` 81. Pyflakes finds nothing new (158 messages, the same as before v94). The credential and settings comparison between v93.2 and v94.0 is empty (nothing changed, nothing removed), and no secret appears in the added lines.

Tests: `tests/test_clear94.py` (plain words), `tests/test_intel94.py` (NSE/forecast/holidays, plus the real helper programs when a Python with pandas is available: `NEMO_TEST_VENV=/path/to/venv`), `tests/test_studioplus94.py` (pictures, charts, structure). The v93 structural test now stops at the v94 marker.
