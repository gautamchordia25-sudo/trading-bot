# Nemo v101.0 "Globe": the world desk (markets, hours, calendar, overnight cues for India), nine detailed pictures, Sigma polish, and the family fix

One release, one file (`nemotron_bot.py`, version 101.0). You asked for more Nemo knowledge around the globe, more detailed visualisations, and improvements; and, while I was building it, you sent a screenshot of a family member being refused ("On it — I will send it here when it is ready", then "Only the Boss can download media") and said you want your family to be able to use everything. Both are in this release. Section 1 is the family fix, because it was a bug; sections 2-6 are Globe.

Everything from v100.0 and earlier is kept. Credentials, owner lock, trading and holiday guards, permissions and approvals, backup and rollback are untouched. **Globe never places, changes or simulates an order, never calls an AI, never touches the trading agent, and every picture has its numbers in words.**

> **How I read your request.** "Knowledge around the globe" became a read-only **world desk**: 17 exchanges with their hours and holidays, a world calendar, country cards, 35 new plain-words glossary entries, a live world board and "how may India open?". "More detailed visualisations" became **nine pictures** drawn with Pillow (already in Nemo: nothing new is installed). "Improvement" became fixes to Sigma's wording, Sigma pictures and an event guard for Sigma. If you meant something different by "globe" (for example a 3-D globe, or news in other languages), tell me; the rest stands on its own.

---

## 0. Read this first (the honest version)

* **Nothing here was run against a live source.** From my build sandbox the public price feed is unreachable, so every test uses a generator. The board, the cues and every chart will meet real data for the first time on your server. A symbol that does not answer is named on the board; the rest still show.
* **The overnight-cues model is allowed to say "nothing usable".** It chooses factors on the first 70% of the days, tests them on the last 30%, uses only the US session that closed *before* the Indian open, and says "a tendency, not a forecast". If your real data show no relation, it says so. See `NEMO_V101_RESEARCH.md` section 6.
* **Dates are "as reported".** The Fed's 2026 dates and the NYSE's 2026 early closes came from search snippets; the other calendar entries are rules (third Friday …) that can move. The calendar says which is which. Confirm any date you act on.
* **Holidays are modelled for the US, UK, Germany, France and India (your 2026 table).** Asian markets show weekends only and say so.
* **No GIFT Nifty.** It is the usual early guide for India's open; Nemo has no feed for it, and I did not invent a proxy.

---

## 1. The family fix (the screenshot)

**What was wrong.** A family member whom you had allowed to download asked for a video. Circle (v89) accepted it and answered "On it — I will send it here when it is ready." Then the original v41 media engine, which only knew the owner, answered "Only the Boss can download media." The older tests stubbed that engine, so they could not see it. This is the only engine that still refused someone Circle had let through; I read every family ability's engine (chat, reminders, list, message to you, web, files, voice, pictures, PDFs, downloads, calendar) for the same trap.

**What changed.**

| | |
|---|---|
| The downloader | The engine asks `_n101_may_download`: the owner, or a person Circle has switched **downloads** on for (blocked people never). Nothing else can reach it, because Circle's gate still refuses everyone who is not allowed. |
| Failure hints | A family member who hits a login-only video no longer gets your cookie instructions ("send /browsercookies") or a server file path; they get a plain sentence. You still get the cookie steps. |
| "play / send me" | "play tum hi ho song", "send me kesariya song", "please send me the dhoom machale video" become download requests (same ability, same daily limits). |

**"I want everything for my family."** One phrase, from you only: **`family everything`** (also: "give my family everything", "give family full access"). It switches **on** every ability Circle has for the family role (chat, reminders, shared list, messages to you, web look-ups, reading photos/files/voice, pictures, PDFs, song and video downloads, your free/busy times: times only, never titles), the **trade desk (view only)** from v97, and the **world desk** from this release. A new family member gets it all at once. It reports what it did and what it left:

* **Still locked for everyone, whatever any switch says** (this is Circle's own list, unchanged, and it is deliberate): your email; your Drive, files, documents and library; what Nemo remembers about you; trading, positions, money and bank; the server, commands, code and updates; your devices; settings, keys, passwords and approvals; other people's chats and who uses Nemo; the activity log. A family member who asks for one of these is told it is private, as before; "give me full access" is still refused. I will not turn these on: they are the keys to your money and your server, and a message from a family phone should never be able to reach them.
* **Personal switches you set earlier are kept** (a switch for one person beats the family-wide one) and the reply lists them ("Asha has making pictures off").
* **Limits stay**: 100 answers and 10 special requests (web, files, pictures, PDFs, downloads, world pictures) per person per day by default; `set family special limit to 20` changes it.
* **Guests and strangers are untouched.**

`family everyday only` goes back to the shipped defaults (chat, reminders, list, messages, web, files) and turns the desk off for family; personal switches stay.

**The world desk for family** (read-only, public data, no credits): "world markets", "globe map", "market hours", "is Tokyo open", "global cues", "world calendar", "globe gold", "globe japan", "globe compare nifty nasdaq gold", "what is DXY" (instant and free: no AI). Private chats only (in a group they chat as before). They cannot add events or change a setting; the heavy views count towards their special-request limit; `family world off` switches it off. It appears on their "what can I do" card.

---

## 2. How you use Globe (owner, private chat; plain words work)

| You say | What happens |
|---|---|
| `globe` · `world markets` · `global markets` · `how are the global markets doing` | The **world board** in words (Americas, Europe, Asia-Pacific indices, volatility, currencies, commodities, US yields, crypto, US futures; 1-day, 5-day, 1-month, tone) and the **heat-map picture**. |
| `globe map` | The picture alone (the same numbers are in "world markets"). |
| `global cues` · `how will nifty open` · `globe india` | **Overnight cues for India**: the latest moves of the S&P 500, Nasdaq, VIX, dollar index, crude, Brent, US 10-year yield and gold; what they explained of NIFTY's opening gap over two years with the out-of-sample check; an estimate with a range **only if** the verdict allows; Asia today; events in the next three days; and the **cue picture** (scatter with the fit and a bar chart against the noise band). |
| `market hours` · `which markets are open` · `world clock` | 16 exchanges on one Indian clock in words and as a timeline picture (lunch breaks, a line at "now", the NSE session shaded, holidays named). |
| `is Tokyo open` · `is wall street open` · `when does the London market open` | One exchange: open or not, when it opens next in Indian time, its hours local and in IST, and a note where holidays are not modelled. (The Indian exchanges are left to the older layers, so there is one answer for them.) |
| `world calendar` · `globe events 60 days` | The Fed's published dates, rule-based dates (jobs report, options expiry, triple witching, NIFTY expiry), closed days of the US, UK, Germany and India, and your own events. Each is tagged published / rule / yours. |
| `globe event add 2026-12-05 RBI policy decision` (optional `high` / `medium` / `low`) · `globe event remove EV-…` | Your own events. **A high-impact event stops Sigma selling premium** that day (and the day after, for a late-evening event); see section 4. |
| `globe brent` · `globe gold` · `globe rupee` · `globe nikkei` · `globe 10 year` · `globe bitcoin` | One instrument: its numbers in words and a one-year line with the 50-day average, the year's high and low. |
| `globe compare nifty nasdaq gold 6m` (up to six; `90 days`, `1y` …) | Indexed to 100 on one axis, with a legend and end labels; words list who led and who lagged. |
| `globe japan` · `globe germany` · `globe euro area` | A country card: exchange and hours, index, currency, central bank, one stable note. No rates or sizes that could go stale. |
| `globe correlation` | How the world moves together: a 14-by-14 grid of daily-change correlations in a picture, the six strongest pairs and the closest to NIFTY in words, with the caveat about different trading hours. |
| `globe news` | World market headlines from the same fetcher Scout uses (headlines only; no AI reads them). |
| `globe colours safe` / `classic` · `globe charts on` / `off` | Blue and orange (colour-blind safe, default) or green and red; pictures under answers on or off (they still draw on request). |
| `globe help` | The list and this run's counters. |

None of these phrases is taken from older features ("market brief", "sigma", "scout …", "is the market open", "how is my portfolio" still go where they went; tested).

---

## 3. The nine pictures (each has a text twin)

| Picture | Form and what is on it |
|---|---|
| **World map** | A tile grid by region and group: colour = direction and size of the 1-day move (grey at zero, full colour at 3% for indices, 1% for currencies, 6% crypto, 15% VIX), a triangle and a sign on every tile, the level, "closed" where the market is shut, a grey "no data" tile for anything that did not answer, a colour scale. |
| **Market hours** | 16 exchanges on 00:00-24:00 IST, sessions as bars with lunch gaps, the NSE session shaded, "now" marked, holidays and weekends written in the row. |
| **Signal chart** (`sigma chart NIFTY`, `sigma chart TCS`, and under every Sigma card) | Up to 110 daily candles, the 20-, 50- and 200-day averages, volume (when the feed has it) with its 20-day average, RSI(14) with its 30/70 bands, the next session's pivot levels for an index, and for a saved signal its entry, stop and targets with the risk and the reward shaded. |
| **Payoff diagram** (`sigma payoff`, and under every option card) | Profit or loss per lot at expiry, before charges (solid) and after (dashed), the break-evens, best and worst case, the options' own expected move shaded, the legs on the axis, and the model's spread of where the index ends. |
| **Scoreboard curve** (`sigma equity`) | The running result in R after charges, its running peak, the dip shaded, every signal's own result below. |
| **Cue picture** | The strongest cue against NIFTY's gap, one dot a day, the fit, today's cue; and each cue's correlation against the band that noise alone would give. |
| **Correlation grid** | Every cell printed, a diverging scale through grey. |
| **One instrument** and **comparison** | A year of closes with the 50-day average and the high and low; indexed lines on one axis with a legend and end labels. |

Design rules (from the dataviz method; see `NEMO_V101_RESEARCH.md` section 7): form chosen first; a validated colour set; blue and orange for rising and falling by default; a sign or triangle beside every colour; text never in a series colour; every mark labelled directly; no dual axes; each picture looked at for collisions.

---

## 4. Sigma: what improved

1. **A chart under every Sigma card** (and a payoff diagram under option cards); `sigma charts off` stops it.
2. **The event guard.** If a high-impact event is due today or tomorrow (the Fed's decision night counts for the next Indian day; your own events count), Sigma **does not sell premium** (credit spreads and condors become "no signal: a high-impact event is due, …"). A bought option or a debit spread gets a note on the card, and every card gets a one-line "Event risk" message.
3. **Wording fixed**: "-0.0 in 5 days" is gone (a move that rounds to zero prints without a sign), "51th percentile" is "51st", "a up trend" is "an up trend".
4. **The one-screen status** (`nemostatus`) is cut at about 4,000 characters by earlier layers, so Sigma's and Globe's lines do not fit; I tried squeezing the older lines and stopped, because older tests rely on their exact wording. Both layers' counters are in `sigma help` and `globe help`.

---

## 5. Cost and storage

* **No AI, no paid call.** Data: the same public daily chart feed Sigma uses (one request per symbol, cached ten minutes while a big market is open and an hour otherwise; a world board is about 40 symbols read 8 at a time). Pictures: Pillow, 1100 px wide, 100-350 KB each, drawn in about a third of a second.
* **Storage:** two small tables (`globe101_setting`, `globe101_event`; your events are capped at 200) and the existing Sigma cache table.
* Network call sites added: **one** (`_n101_fetch`, the public chart feed; a test asserts it).

## 6. What I did not do

* No orders, no change to the trading agent, the guards, the owner lock or any credential. No second bot. No AI.
* No GIFT Nifty, no intraday world data, no Asian holiday calendars, no pre-market or after-hours sessions.
* The family switch does **not** unlock anything on Circle's locked list, and it does not touch a guest or a stranger.
* A world picture for family counts as a "special request"; a "what is DXY" does not.

## 7. Verified and not verified

**Verified offline (149 new tests, `tests/test_globe101.py`):**
* the calendar rules against dates worked by hand (Easter 2024-2027, Thanksgiving, Memorial Day, the whole 2026 NYSE closed list including Friday 3 July, early closes, England's substitute days, 1 January on a Saturday), session states at exact instants in both clock regimes (open, lunch, pre, closed, holiday, weekend), the next open across a weekend and a holiday, the US session in IST in summer and winter, the table of every exchange;
* the instruments, aliases, country cards, the world calendar (the Fed's dates, rule dates, your events added, listed, removed and refused when odd, event risk including the late-evening decision), the glossary additions;
* the helpers (no "-0.0", ordinals, ticks, label spreading), regression and correlation against known answers, the board (a failing symbol named, nothing readable said plainly, the cache), the tone;
* the cue model: the alignment (each Indian open with the US session that closed before it; Monday with Friday), a planted relation found and surviving the out-of-sample check, noise not "usable", **the same-day US move never used**, too little data refused, the wording;
* every picture draws (also with unreadable rows, holidays, weekends, flat data, many signals, a far-away level), the colour choice, text never in a series colour, a failing chart counted and not raised;
* every owner phrase and the phrases it must not take, owner-only, no group, no network, no AI, no broker call over a whole session;
* Sigma: the event veto and note, the chart under a card, the sink chat never gets a picture, `sigma chart/payoff/equity`, the wording fixes;
* **the family**: the real Circle gate and the real v41 downloader (only the network and the downloader program stubbed): the screenshot case, a song name, "play/send me", the engine still refusing anyone not allowed (a blocked person, the sink chat, no id), the owner unchanged, no cookie steps or server paths for family; `family everything` end to end (chat, download, picture, PDF), the locked tier staying locked, personal switches kept and reported, guests untouched, a family member unable to say the phrase, `family everyday only`, the world desk for family (instant glossary, no event ids, limits, groups, blocked, guests);
* structure: the layer names no order function, broker, guard or owner-lock write, calls no AI, has exactly one network call, touches only its own tables (and reads Circle's and the desk's rules and Sigma's records), contains no secret-shaped text or model name.

**Not verified (you will be the first to see):**
* **Anything against live sources** (section 0). In particular whether every symbol on the board answers on the feed.
* Whether the overnight-cues relation exists in your two years of data.
* The pictures on your phone; the wording was judged by reading it, not by anyone in your position.
* The exact dates of the Fed, the NYSE's early closes and the Xetra and Euronext closed days beyond what a search snippet showed.

## 8. Try it, through Nemo

1. `family everything`: check the reply (what is on, what stays locked), then ask a family member to send `download tum hi ho song` (it needs yt-dlp on the server, as for you). If anything else is refused for them, tell me the exact reply.
2. `globe help`, then `world markets` and `globe map` (the first real read of the feed: tell me which symbols it names as "not read").
3. `market hours`, `is Tokyo open`, `world calendar`.
4. `global cues`: read the verdict line first. If it says "nothing usable", believe it.
5. `globe brent`, `globe compare nifty nasdaq gold 6m`, `globe japan`, `globe correlation`.
6. `sigma chart NIFTY`; after the next Sigma card, look at the chart under it; `sigma equity` once something has settled.
7. Add an event you know (`globe event add 2026-12-05 RBI policy decision`) and see Sigma refuse to sell premium that day.

## 9. What changed in older code (everything else is in the new layer, marker `# NEMO 101 - GLOBE`)

1. The docstring, `VERSION`, and `'_n101_'` in the live-self-edit protection list.
2. Sigma's wording (v100 text only): "-0.0", ordinals and "an up trend", in nine places; one added line in `_n100_issue` that calls the chart/event hook after each card.
3. The v41 downloader: its owner-only check now asks `_n101_may_download`, and two hints that a family member should not see (the cookie steps and a server path) are conditional.
4. Wrapped (the old function kept and called): `handle` (the front door, owner only), `_n100_option_signal` (the event guard), `_n89_text` (Circle's text path: "play/send me" and the family world desk), `_n89_access_card`, `_n82_capabilities`, `prime_regression_suite` (9 more rows), `main` (creates the tables).
5. One command (`/globe`) and one menu button.
6. Tests: `tests/test_globe101.py` (new); `tests/test_sigma100.py` stubs the picture sender and switches pictures off for its card tests, and its version test accepts a later layer; `tests/test_desk97.py` switches the world-desk line off before comparing a family card with the desk layer's own.

## 10. Test results (offline, on the test machine)

* **Whole suite on the exact file delivered: 3,077 tests, 8 skipped, 0 failures.** 149 of them are new (`tests/test_globe101.py`); the earlier 2,928 all pass. (Eight skipped, two more than at v100: those two need the optional libraries `arch` and `exchange_calendars`, which are not installed in this sandbox now; they skip, they do not fail.) A first full run found three failures that I had caused: my attempt to squeeze the older status lines broke two older tests that look for their exact wording (Lab and Ledger), and the new world-desk line on a family member's card broke a test that compares the card with the desk layer's own. I removed the squeeze and made that one test switch the line off; the final run is clean.
* Pyflakes: the same 158 messages as v100.0, none new. Only 14 lines of older code were changed (the docstring's first line, the protection list, nine lines of Sigma wording, three lines of the v41 downloader) and one line added (the hook after a Sigma card); a scan of the 2,966 added lines for keys, tokens or secret-shaped text found none.
* Nothing here placed, changed or simulated an order, called a broker, called an AI, or used a paid service, and **no real market data was read** (the sandbox cannot reach the feed). Every market in the tests is a seeded generator; every picture was also rendered on synthetic data and looked at.
* The family tests run the real Circle gate and the real v41 downloader with only the network and the downloader program stubbed; the slowest new group is the pictures (about 33 seconds for the whole new file).
