# More tools for Nemo: trading and image creation (researched, tested, ranked)

You asked me to research GitHub for more trading and image-creation tools Nemo can install. This is a second shortlist after `NEMO_FORGE_PICKS.md` (which already covers ruff, vulture,
detect-secrets, pdfplumber, trafilatura, pandas-ta-classic, jugaad-data, quantstats, tesseract, faster-whisper, sqlite-vec and fastembed, so none of those are repeated here).
Everything installs through **Forge** (a card you approve, pinned files, rollback). Nothing here was installed on your server; I tested each candidate in a throw-away environment.

## 0. The short answer

| Do (high value, tested) | Why | Measured here (peak memory, time) |
|---|---|---|
| **nselib** (trading) | One library for the NSE facts Scout currently lists as "not checked": **results dates, corporate actions, F&O ban list, FII/DII and participant-wise open interest, official India VIX history, delivery %, bulk/block deals, expiry dates, the official holiday list.** Apache-2.0. | imports in 84 MB; its NSE calls could **not** be tried from my sandbox (NSE is blocked), so live behaviour is unverified |
| **exchange_calendars** (trading) | Holiday calendar for BSE/NSE hours. Its 2026 weekday holidays are **exactly the same 16 dates** as Nemo's own table (an independent check). Nemo's table covers 2026 only; this gives a way to cover 2027+ by upgrading the package each December. | 76 MB, 1.3 s |
| **arch** (trading) | GARCH volatility forecast: compare what the market *expects* (implied volatility) with what the index has been *doing*, to choose between buying an option and a spread. | 145 MB, fit and forecast in 0.05 s |
| **realesrgan-ncnn-py** (images) | Real AI upscaling instead of "stretch and sharpen". Models are inside the wheel. Needs two system libraries (`libomp5`, `libvulkan1`). | art/illustration model: 1024→2048 px in 16 s, 225 MB; photo model: 160x120→640x480 in 20 s, 1.8 GB (see section 3) |
| **rembg** with the **silueta** model (images) | Remove a background with no key and no paid service (Studio today needs a remove.bg key). | 0.8 GB peak, 1-3 s per picture; the lite `u2netp` model is **not** good enough (it lost an arm in my test) |
| **vl-convert-python** (images/trading) | Draws charts (candles with entry/stop/target lines) to PNG **without a browser**. | 92 MB, 0.7 s, 30 MB wheel |

| Maybe later | Why not now |
|---|---|
| **TA-Lib** (61 candlestick patterns, wheel installs cleanly) | On random prices the "bullish/bearish engulfing" pattern fired on 22% of candles (89 of 400): a pattern flag alone says very little. Only add it if `scout test` shows it helps. |
| **fyers-apiv3** (official Fyers SDK, live tick socket) | Would let Scout watch stops live instead of every 10 minutes. But it is a trading SDK (orders included), pulls odd dependencies (an obsolete `asyncio` backport, `aws_lambda_powertools`), and Nemo already has working Fyers HTTP code. Use only the data socket, and only if you want live alerts. |
| **segno** (QR codes, pure Python, 0.1 MB) | Handy for UPI or business-card QR on Studio cards; small and safe, just not a priority. |
| **Chromium HTML cards** (already installed for Playwright) | Prettiest cards (Hindi text rendered correctly) but **941 MB** while running. Use for rich infographics only when memory is free. |
| **Local image generation** (Stable Diffusion on the VPS) | Your server cannot do this well (see section 3). The nine online engines already work. |

| Do not install (with the evidence) | |
|---|---|
| **vaderSentiment** | General-purpose sentiment misreads finance: it scored "Yes Bank faces SEBI probe, shares plunge" as **+0.60**, "HDFC profit falls, misses estimates" as +0.25 and "Asian Paints profit rises but margins shrink, shares fall" as +0.58 (3 of my 12 test headlines clearly wrong, 2 more doubtful). |
| **py_vollib** | Nemo already matches it: on your 8 real option prices Scout's solver agrees to 3 decimals (31.439% vs 31.439%), and the bot's Greeks agree to 4-7 decimals. Nothing to add. |
| **mplfinance** | Still a beta tag, last release 3.2 years ago. matplotlib (already installed) draws the same candles. |
| **OpenAlgo** (AGPL), **nsepython** (GPL, 495 days since last release), **backtesting.py** (AGPL) | Licences, and OpenAlgo would sit between Nemo and your orders. |
| **OpenBB, Qlib, FinRL, vectorbt** | Very heavy for a 3.8 GB server and they duplicate what Nemo has. |
| **stable-diffusion-cpp-python** | Source-only on PyPI: Forge refuses packages that need to be compiled. |
| **rembg's `u2netp` model** | 4.6 MB model, but it damaged a person photo (section 3). |
| **Real-ESRGAN 4x models without tiling, or on big pictures** | Untiled, the 4x anime model needed 4.3 GB for a 256 px picture and **10 GB** for 512 px (the photo model is bigger still). With tiling the photo model took 1.9 GB and 145 s for 512 px: too slow and heavy for your server except for small pictures. |
| **TradingAgents** (LLM "trading firm" framework, v0.3.1 July 2026) | A research framework: dozens of AI calls per analysis, built for US data, and its own README says it is not advice. Worth borrowing the *idea* of a bull-vs-bear debate step, not installing. |

## 1. How I researched this and how far to trust it

* **Starting point:** what Nemo already has (read from the code): Studio's nine image engines, text drawn by code (Hindi font handled), remove.bg by key, "2x bigger" = Lanczos stretch plus sharpening; Scout's news, indicators, option plan.
* **Landscape:** web searches (awesome-quant lists, NSE libraries, Fyers SDK, CPU image models), then **every candidate checked on PyPI today** (version, release date, licence, whether finished wheels exist, wheel size).
* **Tested for real** in clean virtual environments on my test machine (Python 3.11, **4 cores, 16 GB**). Your server has 2 cores and about 3.8 GB shared with another application: memory numbers carry over, **times will be about 2x longer**.
* **What I could not reach:** the NSE website (blocked), Hugging Face (blocked), the GitHub API (blocked: so no star counts this time). GitHub release files and raw files **were** reachable, so rembg's models were downloaded and tested for real.
* Pictures I made while testing were sent in chat so you can judge them yourself.

## 2. Trading tools

### nselib (Apache-2.0, 2.5.1, 30 releases, last release 155 days ago)
Requires pandas, pandas_market_calendars, pypdf, requests, scipy (small, common packages). Functions it exposes (read from the installed package):
* **Equities:** `event_calendar_for_equity`, `financial_results_for_equity`, `corporate_actions_for_equity`, `india_vix_data`, `top_gainers_or_losers`, `most_active_equities`, `bulk_deal_data`, `block_deals_data`, `short_selling_data`, `deliverable_position_data`, `week_52_high_low_report`, `pe_ratio`, `trading_holiday_calendar`, bhav copies.
* **Derivatives:** `fii_derivatives_statistics`, `participant_wise_open_interest`, `participant_wise_trading_volume`, `fno_security_in_ban_period`, `expiry_dates_option_index`, `nse_live_option_chain`, `fno_bhav_copy`.

**What it would fix in Scout:** every card says "Not checked: results dates, circuit limits, corporate actions". With nselib those become real checks (results due → the event penalty becomes exact; F&O ban → veto; split/bonus/dividend → warning), and FII/DII plus participant open interest becomes one more read in the index-option bias.
**Risk, plainly:** it reads the NSE website, which often blocks servers and changes its pages. I could not try it. Design it fail-soft with caching (like Scout's news): if NSE says no, the card says "could not check" and nothing breaks. The first real test is yours: install it and Nemo will report what answers.

### exchange_calendars (Apache-2.0, 4.13.2)
Verified: for 2026 the BSE calendar (`XBOM`) has 16 weekday holidays and they are **identical** to Nemo's `_N81_HOLIDAYS_2026` weekday entries (Nemo's extra entry, 8 Nov, is the Sunday Diwali special session). The calendar object ends at 31 Dec 2026, so it must be upgraded each year before it knows 2027. Use: cross-check Nemo's table automatically and warn when a year is uncovered.

### arch (NCSA licence, 8.0.0)
Fits a GARCH(1,1) volatility model to daily returns and forecasts the next days' volatility. Idea for Scout: **if the ATM implied volatility is well above the forecast, options are dear → prefer the spread; if below → buying outright is cheaper.** Evidence for the edge is mixed, so it should be shown as one more line on the card and tracked in `scout stats`, not a hard rule.

### Cross-checks that were done
* `py_vollib` vs Scout's implied-volatility solver on your **8 real rows**: worst difference 0.0000 volatility points.
* `py_vollib` vs the bot's `_n55_greeks` on 5 cases (price, delta, gamma, theta per day, vega): equal to 4-7 decimals.
* `exchange_calendars` vs Nemo's 2026 holidays: identical (above).

## 3. Image tools (what I saw)

**Background removal, three models on three real photos** (tiger, car with a person, woman with raised arms), original | u2netp | silueta | u2net:
* tiger and car: all three models were good;
* **person: `u2netp` lost one raised arm and part of the body; `silueta` and `u2net` were clean.**
* Memory and speed (1024x768 picture, warm): u2netp 734 MB and 0.4 s; **silueta 809 MB and 1-3 s** (44 MB model); u2net 1,155 MB and 0.6-0.9 s (176 MB model).
* **Cost of installing rembg:** it brings numba, scipy, scikit-image, OpenCV and onnxruntime, about 640 MB on disk. Install it as an **isolated tool environment** (not "into yourself") so it cannot disturb Nemo's own packages; run it as a one-at-a-time job like the Wire jobs, only when about 1.2 GB is free.

**Upscaling, a 160x120 photo crop made 2x bigger** (original | what Nemo does today | Real-ESRGAN animevideo-x2 | Real-ESRGAN x4plus):
* today (Lanczos + sharpening): soft, with dark halos around the ears;
* animevideo model: crisp edges in 0.4 s, but flat, "painted" fur: good for illustrations and AI art, not for photos;
* x4plus photo model: **the most natural, fur texture kept**, but 20 s for a tiny picture.
* Memory with tiling: animevideo x2, 1024→2048 px: 16 s, 225 MB. x4plus photo model: 256 px input 41 s and 1.3 GB; 512 px input 145 s and 1.9 GB. **Without tiling the 4x anime model alone needed 4.3 GB (256 px) and 10 GB (512 px).** Rule for Nemo: always tile; use the fast model for art, the photo model only for small pictures.
* Needs the system libraries `libomp5` and `libvulkan1` (not on Forge's default list: `forge apt allow libomp5`, `forge apt allow libvulkan1`, then `forge apt libomp5 libvulkan1`). The wheel itself is 44 MB and includes the models.

**Charts without a browser (vl-convert-python):** candles plus dashed entry, red stop and green target lines, 1536x818 PNG in 0.7 s using 92 MB. A good fit for putting a chart under every Scout idea. (matplotlib, already installed, can draw the same thing; vl-convert looks cleaner for little effort.)

**HTML card through Chromium:** a trade-idea card with a gradient, coloured numbers and a Hindi line rendered perfectly, 1.9 s, but the browser tree peaked at **941 MB**. Beautiful, heavy.

**Local image generation:** OnnxStream (C++, runs Stable Diffusion in under 300 MB of RAM) reports 29 minutes for one 512 px SDXL-Turbo picture on a Raspberry Pi Zero 2. A 2-core VPS is much faster than that, but it needs compiling a C++ program and downloading models from Hugging Face; I could not test either. With 3.8 GB shared, I would not plan on it; the nine online engines are the practical path (a RAM upgrade would change this).

## 4. What I would build with these (proposal; you pick)

| Version | Name | What it would do | New installs |
|---|---|---|---|
| **v94** | **Scout intel** | Results-date, F&O-ban and corporate-action checks replace "not checked"; FII/DII and participant OI become an index-bias read; official India VIX history; GARCH-vs-implied volatility line on option cards; holiday cross-check beyond 2026. Everything fail-soft and cached. | nselib, exchange_calendars, arch |
| **v94** | **Studio+** | "⬆ 2x bigger" uses Real-ESRGAN (art model by default, photo model for small pictures, always tiled); "remove background" works with no key through rembg (silueta); a chart picture under each Scout idea (vl-convert or matplotlib). | realesrgan-ncnn-py, rembg (tool env), vl-convert-python, apt: libomp5, libvulkan1 |
| later | Live stops | Fyers data socket for instant stop/target alerts. | fyers-apiv3 (data socket only) |

Memory guard values (the Wire runner refuses to start a job when free memory is under the need plus 300 MB): rembg 1,100 MB; Real-ESRGAN art 400 MB, photo 1,600 MB (inputs up to 256 px, else refuse); vl-convert 200 MB; arch 250 MB; nselib 250 MB; Chromium card 1,200 MB.

## 5. Install words (say these to Nemo in your private chat)

```
install nselib into yourself
install exchange_calendars into yourself
install arch into yourself
forge apt allow libomp5
forge apt allow libvulkan1
forge apt libomp5 libvulkan1
install realesrgan-ncnn-py into yourself
install vl-convert-python into yourself
install rembg
```
Each shows a card with the real size and dependencies for **your** server before you tap. `install rembg` (without "into yourself") makes the isolated environment. The libraries do nothing until a Nemo version uses them; installing now only lets you see the cards and sizes. Say "build v94 Scout intel" or "build v94 Studio+" (or both) and I will wire them with tests.

## 6. A bug I found in my own Scout while testing (fixed in v93.2)

Comparing sentiment tools on 12 real-style headlines showed that Scout's plain-rules reader (used only when the AI is down) matched words inside other words: "ban" matched **"banks"**, so "FII buying lifts banks" scored zero. It also missed "jump", "surge", "wins ... deal" and "cuts repo rate". It now matches whole words with their usual endings; all 12 headlines get the right sign, with tests (the AI reader is unchanged and still the main one).

## 7. Not verified

* **nselib against the live NSE site** (blocked from my sandbox) and how often NSE blocks your server.
* **Hugging Face models** (FinBERT-style news models, SDXL ONNX): unreachable, so not tested; they are also too heavy for 3.8 GB.
* **Your server's real speed and memory** for rembg and Real-ESRGAN (mine had 4 cores and 16 GB).
* **GitHub star counts** (API blocked); I used release dates, licences and wheels from PyPI.
* Quality judgements come from three photos and one crop, enough to rule `u2netp` out and to see the upscalers' character, not a benchmark.
* No live trade was placed and no paid API was called.
