# Research behind Nemo v101 "Globe" (world markets, macro knowledge, charts): what I looked for, what I found, what I used and what I refused

You asked for more Nemo knowledge around the globe, more detailed visualisations, and improvements. This page is the research. `NEMO_V101_GLOBE.md` is the build. Every finding carries one of these tags, so you can see how much weight it deserves:

| Tag | Meaning |
|---|---|
| **[web]** | A figure or claim I found in web search results (exchange or central-bank pages as snippets, press reports). I read snippets, not the original documents, so treat exact numbers as "reported" and confirm dates before relying on one. |
| **[rule]** | A calendar rule I know from the exchanges' published practice and compute in code (the 4th Thursday of November, Easter, "the nearest weekday"). Checkable offline; tests work the dates by hand. |
| **[text]** | Textbook material (correlation, least squares, out-of-sample testing). Stable and checkable offline. |
| **[mine]** | My own judgement or a rule I chose. Not tuned on data. |
| **[code]** | A fact about Nemo's own code that I read in this session. |

Nothing here predicts a market. Section 6 says exactly how far the "overnight cues" model is allowed to claim anything.

---

## 1. What Nemo already knew about the world (the audit) **[code]**

* One old `market_brief`: seven Yahoo quotes (`^NSEI`, `^BSESN`, `^GSPC`, `^N225`, `USDINR=X`, `CL=F`, `GC=F`, `^IXIC`) plus an AI write-up. No sessions, no holidays outside India, no yields, no volatility, no calendar of world events.
* The India trading calendar for 2026 only (`_N81_HOLIDAYS_2026`, v81), and the NSE session state (`_n81_session`).
* A plain-words glossary (v94) with trading words (PCR, theta, ATR …) and almost nothing about the macro world.
* A Pillow chart engine (v90 Studio, Scout's idea chart in v94) and Sigma's daily-feed layer with a cache (v100). Both are reused; no new program is added.
* Sigma (v100) saw only India: it had no idea that the US Fed was deciding that night, and it never drew a picture.

## 2. Exchanges, hours and sessions

| Fact | Tag | Used how |
|---|---|---|
| Tokyo trades 09:00-11:30 and 12:30-15:30 local; Hong Kong 09:30-12:00 and 13:00-16:00; Shanghai 09:30-11:30 and 13:00-15:00; Korea 09:00-15:30; Taiwan 09:00-13:30; Sydney 10:00-16:00; Singapore 09:00-17:00; London 08:00-16:30; Xetra, Euronext and SIX 09:00-17:30; New York 09:30-16:00; Toronto 09:30-16:00; São Paulo 10:00-17:00; Mexico 08:30-15:00 | **[web]** exchange pages as reported (lunch breaks as of the last published rules; a few exchanges have changed their hours in recent years) | A table of 16 exchanges; regular hours only. Pre-market, auctions and after-hours are **not** modelled and the pictures say so. |
| New York and Europe move their clocks on different dates, so the US session is 19:00-01:30 IST in summer and 20:00-02:30 in winter | **[rule]** | Computed from the real time-zone database (`zoneinfo`) with a fixed-offset fallback, never from a hard-coded "it is 01:30". |
| NYSE is closed on New Year's Day, Martin Luther King Jr. Day, Presidents' Day, Good Friday, Memorial Day, Juneteenth, Independence Day, Labor Day, Thanksgiving and Christmas; a holiday on a Saturday is observed on the Friday, on a Sunday on the Monday; 1 January on a Saturday is **not** observed on the Friday before | **[web]** NYSE holiday page as reported + **[rule]** | `_n101_us_holidays`. Tests check the whole 2026 list by hand (including Friday 3 July). |
| NYSE early closes (13:00) in 2026: 2 July, 27 November, 24 December | **[web]** as reported | Listed for 2026; for other years the day after Thanksgiving and 24 December when they fall on a weekday **[rule]**. |
| London: England's bank holidays (Easter, early May, spring, summer, Christmas and Boxing Day with substitute days) | **[rule]** | `_n101_uk_holidays`. |
| Xetra closes on New Year's Day, Good Friday, Easter Monday, 1 May, 24, 25, 26 and 31 December; Euronext Paris on New Year's Day, Good Friday, Easter Monday, 1 May, 25 and 26 December | **[web]** + memory of the published calendars, **marked "confirm on the exchange's page" in the code** | Used for the "closed" state only. |
| GIFT Nifty (NIFTY futures at NSE International Exchange, GIFT City) trades 06:30-15:40 and 16:35-02:45 IST and replaced SGX Nifty in 2023 | **[web]** as reported | **Mentioned, not used.** Nemo has no feed for it; the cues text says "check your broker's app". I did not invent a proxy. |
| Asian holidays (lunar new year, Golden Week, Diwali sessions elsewhere …) | - | **Not modelled.** Those markets show weekends only and say "holidays are not modelled for this market". A wrong "open" is worse than an honest "I do not know". |
| India after 2026 | **[code]** | The NSE table covers 2026 only; Globe says "unknown", not "open", for any other year. |

## 3. The world calendar

* **FOMC decision days, 2026:** 28 January, 18 March, 29 April, 17 June, 29 July, 16 September, 28 October, 9 December **[web]** (the Fed's published schedule as reported; each is the second day of a two-day meeting, with the statement at 2 pm New York time, about 23:30 IST). Marked "published" in the calendar.
* **US jobs report** (usually the first Friday, 8:30 am New York), **US monthly options expiry** (third Friday) and **quarterly "triple witching"** (third Friday of March, June, September, December), **NIFTY monthly expiry** (last Tuesday, as NSE set it in 2025) **[rule]**. These are marked "rule": they follow the usual pattern and can move, and the calendar says "confirm before relying on one".
* **Closed days** of the US, UK, Germany and India **[rule]/[code]**.
* **Your own events** (an RBI decision, a results day): `globe event add 2026-12-05 RBI policy decision`. Nothing here knows the RBI's dates and I will not guess them; this is the honest way to include them.
* **Why it matters for Sigma [mine]:** a short option strategy is a bet that nothing jumps; a known high-impact event is a scheduled jump. Sigma now refuses to sell premium into a high-impact event and puts a one-line note under any card on such a day. A decision made at 23:30 IST moves the **next** Indian day, so the Fed's date affects both dates.

## 4. What moves India overnight (and what the press says)

* Press commentary reports that a 1% fall in the S&P 500 has tended to coincide with a 0.4-0.7% fall in the NIFTY the next morning, that the relationship has weakened and strengthened at different times, and that the dollar, US yields and crude often matter as much **[web]**. I treated this as a hypothesis to measure, never a rule.
* Mechanism **[mine]**: the US session closes at 01:30 IST, before India opens at 09:15, so it is the first public information of the Indian day; the dollar and US yields drive foreign flows; crude is India's biggest import bill.

## 5. The glossary

35 words added to the plain-words glossary (DXY, yield curve and its inversion, the 10-year yield, basis point, carry trade, risk-on and risk-off, safe haven, Brent, WTI, contango, backwardation, GIFT Nifty, SGX Nifty, ADR, PMI, CPI, core CPI, NFP, FOMC, dot plot, QE and QT, hawkish and dovish, real yield, credit spread, CDS, emerging markets, MSCI, Nikkei, Hang Seng, DAX, FTSE, Dow, S&P 500, Nasdaq, triple witching) and about 40 aliases. They are definitions only: no rates, no sizes, nothing that goes stale. A word Nemo already had is never replaced.

## 6. The overnight-cues model: how it is kept honest **[text]/[mine]**

The question: how much of NIFTY's opening gap (today's open against yesterday's close) did the previous US session, the dollar, crude, US yields and the VIX explain?

1. **No look-ahead.** Each Indian day is paired only with the **latest US session that closed before it** (for a Monday, Friday's). The US session of the same calendar date closes *after* the Indian open and is never used. A test builds a world in which the gap follows that same-day session and checks that the model finds **nothing**.
2. **Selection and testing on different data.** Factors are chosen on the first 70% of the days (|t| at least 2, at most 3 of them), the fit is scored on the last 30% (out-of-sample R², how often the sign of the gap was right, typical error), and only then refitted on all days for today's estimate.
3. **A verdict that can say no.** `usable` (out-of-sample R² at least 10%), `weak` (2-10%), `none` (below 2%), or `too little data` (under 120 days). Tests: a planted relation is found and survives; pure noise is not "usable"; a chosen-by-luck factor is not trusted.
4. **Modest wording.** Even "usable" says "most of the gap comes from other things", prints a range, and says "a tendency, not a forecast"; the text names GIFT Nifty as the usual early guide and says Nemo has no feed for it.
5. **Not done [mine]:** no machine learning, no more than three factors, no intraday data, no regime switching, no claim about direction after the open. With two years of daily data any of those would mostly fit noise.

The correlation grid is a description, not a model: it matches daily changes by calendar date and says so, because same-date matching **understates** links between markets that trade at different hours (the cues model does that part properly).

## 7. Visual design (the dataviz method, applied) **[mine]**

* **Form first.** A heat-map grid for "everything today" (magnitude and sign across many items), a timeline for "when is each market open", candles plus indicator panels for a signal (price, volume, a bounded oscillator), a profit-and-loss line for an option structure, a running total with its dip for the scoreboard, a scatter with the fit for "does this relate to that", a diverging grid for correlation, a single line for one instrument, indexed lines on **one** axis for a comparison. No dual axes anywhere.
* **Colour computed, not eyeballed.** The categorical set (blue, orange, aqua, yellow, magenta, green, violet, red) passed the dataviz validator (lightness band, chroma floor, neighbour separation under colour-blind simulation). Its contrast warning is why **every mark is labelled directly and every picture has a text twin**. Rising and falling use blue and orange (colour-blind safe) by default and green and red on request (`globe colours classic`); a triangle or a sign is printed beside every colour; **text is never printed in a series colour**; diverging scales run through a grey middle.
* **Thin marks, quiet grid, labels that do not collide** (a small spreading routine keeps right-hand labels apart), sizes chosen for a phone, supersampled at twice the size for smooth lines and text.
* **Looked at.** I rendered every picture on synthetic data and read each one for collisions and overflow; several faults (a clipped "now" tag, a dashed line leaving its frame, clipped value labels) were found and fixed that way. The validator checks colour, not layout.

## 8. What I looked at and did not use

* **A third-party data source or API key** for world data: not needed (the public chart feed Sigma already uses carries every symbol on the board), and a second dependency is a second failure.
* **GIFT Nifty as a signal:** no feed available to Nemo; not faked.
* **Sentiment indices, "fear and greed", AI reading of news, price targets, economic forecasts:** weak or unfalsifiable. Headlines are shown as headlines.
* **Computing Asian holidays** (lunar calendars): error-prone and untestable here; named as not modelled.
* **A map with country shapes:** a tile grid reads faster on a phone and needs no map data.
* **matplotlib or any chart library:** Nemo already draws with Pillow (the server's memory is tight); nothing new is installed.

## 9. What I did not verify

* **Anything against the live feed.** The sandbox cannot reach the public chart feed, so no real price, candle or timestamp was read. Every test uses a generator. In particular: whether every symbol on the board answers (Yahoo's `^TNX` unit, `DX-Y.NYB`, `000001.SS`, `^BVSP`, `^MXX`, `^STI` and the futures symbols are the ones I am least sure of), the real candle timestamps for futures and FX (the alignment uses the New York date of each candle), and how stale a closed market's last candle looks. A symbol that does not answer is named in the board and the rest still show.
* **The exact FOMC, NYSE and exchange dates and hours** beyond what a search snippet showed (section 2 and 3): confirm any date you act on.
* **Whether the cues relation exists in your real two years of data.** The model is built to say "nothing usable"; the first real `global cues` is the experiment.
* **The pictures on a phone.** I looked at the PNGs; Telegram's own scaling and your screen are untested.
* No live trade was placed and no paid API was called.
