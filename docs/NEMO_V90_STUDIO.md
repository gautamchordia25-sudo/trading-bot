# Nemo v90.1 "Studio": more image engines and tools, exact designs and honest charts, reports whose numbers are checked

You asked for more image creation tools and abilities, and for more precise report making.
Everything from v89 (Circle) and earlier is kept. Your credentials, owner lock, trading and holiday guards, approvals, backup and rollback are untouched
(credential check against v89: 0 changed, 0 removed). Keys are never printed, logged or put in a link.

## 1. What I found first (by reading and running the v89 file, not by guessing)

**Images**
1. **Two engines only:** NVIDIA FLUX (needs your key) and one keyless Pollinations address. If both failed you got "engines are busy" and no reason.
2. **Anything over 5 KB was sent as "your image".** An HTML error page or a rate-limit message from a provider would have been delivered as a picture.
3. One fixed size, no styles, no variants, no seed, and a shared temporary file name for every picture.
4. **No editing or design tools at all:** no resize/crop/text/filters/background removal, no posters, quote cards or logos with real spelling (diffusion models cannot spell).
5. **`make_chart` asked the AI for "representative values"** when you gave no numbers, so a chart could show invented data.

**Reports**
1. Researched reports were checked for sources, headings and layout, but **never for their numbers.** A model could write "oil rose 15% from 80 to 92", a Friday that was a Saturday, or a figure that is in no source, and the PDF went out.
2. No tables or figures from the evidence; every report was prose plus tiles.
3. A report **from your own file** (CSV, Excel, trade log) did not exist except as a loosely-worded AI summary, with numbers the AI made up arithmetic for.
4. The older code passes `godmode=False` through its wrappers, so in practice a report is draft → gate → PDF: no verifier, no editor, no repair pass. v90 adds one bounded correction pass for numbers without turning those expensive passes on.

## 2. What v90 adds

### 2.1 Pictures: nine engines in one verified chain

Tried in this order: engines that worked lately and are quick (30 s or less, quickest first), then engines never tried yet, then slow ones (for example a community queue), then ones that failed lately. An order you set yourself with `studio engines …` is kept exactly. One that fails three times in a row rests for 10 minutes; one shared time budget (170 s); each engine is time-boxed.

| Engine | Key (saved with `studio key …`) | Cost | Notes |
|---|---|---|---|
| NVIDIA FLUX | `nvidia` (your existing key is used) | your plan | tries each model with its own time cap (45 s) and keeps the provider's own complaint when it refuses |
| Gemini image | `gemini` | free tier at the time of writing, check limits | **also edits pictures** ("change the background to a beach") |
| Cloudflare Workers AI | `cloudflare` + `cloudflare_account` | free tier at the time of writing | FLUX schnell, then SDXL |
| Together FLUX | `together` | free model at the time of writing | |
| Hugging Face FLUX | `huggingface` (or `hf`) | free tier at the time of writing | |
| Pollinations (keyed) | `pollinations` | free tier at the time of writing | |
| Pollinations (keyless) | none | free | the old route, now only one of nine |
| AI Horde | none (anonymous key); `horde` key is faster | free, community GPUs, can be slow | submit → poll → download, cancelled if it runs out of time |
| OpenAI gpt-image | `openai` | **paid per picture; OFF until you say `studio paid on`** | |

Every reply is **decoded and checked** before it is called a picture: HTML/JSON pages (`not_image`), damaged files (`corrupt`), under 64 px (`tiny`), all-one-colour frames (`blank`) are rejected and the next engine is tried. The size you asked for is **exact** (cover-crop, never stretched). Each engine failure has its own word (`the key was rejected`, `free allowance used up or rate limit`, `too slow`, `the provider refused the prompt`, …), and the message after a failed request lists every engine and what to do next.

Styles (20, e.g. anime, watercolor, 3D, cinematic, pixel, logo), 1–4 variants, seeds, social-media sizes (Instagram post/story, YouTube thumbnail, LinkedIn, Twitter, Facebook, WhatsApp DP, wallpaper, A4 …), "without …" lists. A child-safety filter runs before any engine is called. The old `fetch_image()` that reports, PDFs and the family "draw" ability use now goes through the same chain (same contract: writes the file, returns True/False).

### 2.2 Edit a picture with no AI (Pillow; send or reply to a picture and say it)

resize / crop / pad to exact sizes and presets · rotate · flip · grayscale, sepia, invert, blur, sharpen, brightness, contrast, saturation, vignette, pixelate, vintage · add text, watermark · round corners, circle crop, border · **background removal** (rembg if installed, otherwise plain-background detection, otherwise remove.bg if you add its key; a busy background is **refused**, not cut badly) · upscale 2–4× · compress to N KB · convert to PNG/JPG/WebP/PDF · strip metadata/GPS (and a warning if a photo carries a location) · dominant-colour palette · image info · split into tiles / carousel · collage of your last pictures. Several in one sentence run in the order you say them.

Under every picture Nemo made: **[🔄 Again] [⬆ 2x bigger] [✂ No background]**. Pictures are kept privately for 24 hours (or 25 per chat) so follow-ups work, and are removed by "forget" or `studio clear`.

### 2.3 Designs with exact text, and wallpapers that need no AI

Poster, quote card, banner, thumbnail, greeting/business card, **logo (PNG and SVG)**: the words are drawn by code, so every letter is exactly as you wrote it (put them in quotes). Optional AI photo background ("with a background of a stormy sea"; a gradient is used and the message says so if the engines fail). Wallpapers (gradient, mesh, waves, geometric, clouds, radial) are made offline from a seed: same seed, same picture.

### 2.4 Charts from your numbers, never invented

Bar, horizontal bar, line, area, pie, donut, scatter, histogram, stacked, candlestick from pairs, a pasted table, `x: … y: …` lists, with Indian grouping (₹1,20,000), currencies, percents. The plotted values are **read back from the drawn chart** and compared with what you gave; a mismatch is refused. No numbers → Nemo asks for them (it never makes data up); "sample chart" gives clearly labelled illustrative data. `/chart` and the older chart tool use the same code.

### 2.5 Reports whose numbers are checked

Inside the existing evidence report (same research, same layout, same QA):

1. **Prompt rules:** every figure must come from the evidence with its `[n]` marker, copied exactly, no invented precision, no self-made conversions, "no figure found in the sources" instead of estimating; optional `DATA TABLE:` blocks.
2. **Audit of the first draft.** Every number, percentage, price, quantity and date is found, normalised (scale words, lakh/crore, `bps`, `x`, `%`, currency) and compared with the **title and text of the sources Nemo actually read** (plus live market data it was given). Findings: found in the cited source · found in another source · **more precise than the source** · **not found anywhere** · "rose 15% from 80 to 92" **recomputed** (and its direction) · dates that do not exist · **weekday names that do not match the calendar** · future dates written as past · citations `[n]` that point at nothing · placeholders (TBD, XX%) · the same measure given two different values.
3. **One bounded correction call** (only if the draft has problems), naming the exact figures. The corrected text is used only if it audits better; a cut-short or worse reply is ignored.
4. **Gate:** hard errors (wrong calculation, wrong direction, impossible date, wrong weekday, missing citation target, placeholder) or a report in which most figures cannot be verified are **refused with the exact reasons** ("Publisher QA refused this draft: numbers check: …"). A few unverified figures do not stop a report; they are listed.
5. **Verification pages** added after the layout QA (so they never trip its page limit): grade A–D with a plain explanation, the figure-by-figure result and source, problems found, and how it was checked (and its limits). `DATA TABLE:` blocks become a **chart plus table** with the values exactly as written, instead of stray text. The manifest file records the check, and you get a one-line summary: `🔢 Numbers check: 15 figures · 15 found in the cited source · grade A (100/100)`.

What it cannot do: it checks figures against the **text Nemo retrieved** (search snippets/pages), not against the whole web, and "found in the source" means the source says it, not that the source is right. Analysis, forecasts and durations ("next 6 to 24 months") are not checked. Switch it off with `studio precision off` (everything is then exactly as in v89).

### 2.5b Data reports from your own file

Send a **CSV, TSV, Excel (.xlsx) or JSON** file (a trade log, expenses, sales, anything with numbers) or paste a table, and say `analyse this file`, `summarise this csv` or `report on my trades`. You get a **PDF and an Excel file**.

* Every number is computed by code with **exact decimals** (sum, average, median, quartiles as Excel's `QUARTILE.INC`, sample standard deviation), by group, by month, unusual values (1.5×IQR, with their row numbers), correlations (only strong ones, with a "goes together, not causes" note), duplicate rows, missing cells.
* **Trade logs** (a P&L column): trades, win rate, net result, expectancy, profit factor, average win/loss, payoff, deepest drawdown of the running total (in date order when there is a date), best/worst, longest streaks, by symbol. It describes the past results in the file; it is not a forecast or advice. Nothing is traded.
* A "Total" row in your file is **set aside and checked** against the sum of the rows above it ("they agree" or a warning with the difference).
* **Every figure has its formula** in the PDF, and the Excel file has a Formulas sheet with live `SUM/AVERAGE/MEDIAN/STDEV.S/SUMIF` formulas pointing at the Data sheet next to Nemo's value.
* The AI may only **word a short summary** from those computed facts, and any figure in that wording that the code did not compute makes the summary be dropped (the note says why).
* Limits: 8 MB, 200,000 rows, 60 columns; `.xls` and PDF tables are not read (save as .xlsx/.csv).

### 2.6 Controls in plain words (only you, in your private chat; everyone else is untouched)

| Say | Effect |
|---|---|
| `studio` · `image engines` · `which image engines work` | menu and engine status (ready / no key / resting / paid off, last worked, counts) |
| `studio setup` · `how do I add more image engines` | where each key comes from |
| `studio key together <key>` (also gemini, huggingface/hf, cloudflare, cloudflare_account, pollinations, nvidia, horde, openai, removebg) | saves it in the same protected secrets file as your other keys, read when needed (no restart); **your message is deleted from the chat**; the key is never echoed or logged |
| `test image engines` | one tiny real 512×512 picture per ready engine, reporting each honestly (free engines only; paid ones skipped unless allowed) |
| `studio paid on/off` · `studio precision on/off` · `studio engines together gemini` / `studio engines auto` · `studio clear` | switches, order, forget the kept pictures |
| `draw …` · `/img …` · `make a poster saying "…"` · `design a logo for "…"` · `gradient wallpaper, ocean` · `bar chart: Jan 120, Feb 150` · `analyse this file` | the features above |

Everyday sentences are not taken: "draw a conclusion", "make the logo public", "make a pdf about …", "report on oil prices", "convert it to pdf" about a document, "resize it" when no picture was sent or made in the last 15 minutes are all passed on to the old code untouched (tested).

### 2.7 v90.1: fixes from your first live engine test

Your `test image engines` run on the real server showed Pollinations (keyless) working in 5 s, AI Horde working in 78 s, Gemini out of free allowance, and NVIDIA failing in 219 s (`flux.1-dev` server error 500, `flux.1-schnell` timeout, `flux.2-klein-4b` rejected with 422). That exposed three problems in v90.0, now fixed:

1. **A slow engine could be put first.** "The one that worked last goes first" would have put the 78-second community queue ahead of the 5-second engine just because it was tested last. The order now prefers quick engines that worked lately (see 2.1) and remembers how long each usually takes (shown in `studio`, for example "usually 5 s").
2. **NVIDIA was not held to its time.** The old NVIDIA helper had its own long timeouts, so one engine could use far more than its share of the 170-second budget. The NVIDIA engine now makes each call itself, one model after another, never more than 45 s per model and never more than the time it was given.
3. **A refusal told you nothing.** A 400 or 422 reply now keeps a short plain-words version of the provider's complaint (letters and digits only, long token-like strings removed, 70 characters), for example `flux.2-klein-4b:http_422 …`, so the request format can be corrected. The 422 for `flux.2-klein-4b` is a request-format rejection; it needs that complaint text to fix, which the next `test image engines` will show.

Not changed: Gemini's "free allowance used up or rate limit" is the provider's answer for your key (check its quota in Google AI Studio); AI Horde pictures are made at about 576 px and are enlarged to the size you asked for, so they are soft.

## 3. Behaviour changes to be aware of

* **A picture request that cannot be made now fails with the reason for each engine** instead of one vague line, and a provider's error page is never sent as a picture.
* **Transparent pictures (rounded corners, cut-outs) arrive as files**, because Telegram photos would flatten them.
* **`/chart` and the older chart tool no longer invent "representative values".** Without numbers they ask for them.
* **A researched report can now be refused** for hard numeric errors that survive one correction pass, and **may take one extra AI call** when its first draft has number problems. Clean reports cost nothing extra. Reports get 2–3 extra pages at the end.
* Pillow, matplotlib are installed on first use by Nemo's own existing installer if missing (once per run, and refused for protected modules); `pypdf` is optional (PyMuPDF is the fallback); `openpyxl` is optional (without it the data report has no Excel file and says so); `rembg` is optional.
* The family "draw a picture" ability (Circle) now uses the verified chain; its switch and limits are unchanged.

## 4. Tests actually run

All offline: a scripted HTTP fake for every image engine and every Telegram upload, scripted research and AI, a temporary SQLite database, synthetic pictures, data and people. The real Pillow, matplotlib, fpdf2, PyMuPDF and openpyxl are used where the sandbox has them (the tests skip cleanly where they are missing). **No Telegram, no image provider, no AI, no paid calls, no trades.**

| Suite | Tests | Result |
|---|---|---|
| v83 Cortex · v84 Atlas · v85 Steward · v86 Candor · v87 Relay · v88 Argus · v89 Circle (existing) | 1089 | pass (v89's structure tests now stop at the v90 layer boundary; their assertions are unchanged) |
| **v90.1 Studio** (`tests/test_studio90.py`) | 235 | pass |
| **Total** | **1324** | see the final result in the delivery message |

Studio tests cover: the nine engines (each real adapter run against scripted replies: Gemini, Cloudflare JSON and binary, Together, Hugging Face, Pollinations, OpenAI, NVIDIA helper, the AI Horde submit/poll/download/cancel), key and paid gating, last-good-first and the 10-minute rest, a crashing adapter, the shared time budget, **an HTML page / damaged / tiny / blank reply each rejected**, exact failure words, exact output size, no key or link in any message or URL; the parsers (sizes, presets with punctuation, styles, counts, seeds, subject extraction) and the child-safety filter; every picture operation (exact pixels, ordering, case-exact text and watermark, transparency, compression, formats, GPS, tiles, background removal vs a busy background, a decompression bomb, a non-image); designs and wallpapers (exact sizes, deterministic, readable on every palette, SVG escaping); charts (parsing incl. Indian grouping, refusals, read-back, every chart type, labelled sample data); **number extraction, matching, over-precision, truncation, arithmetic, direction, weekday and date checks, citations, placeholders, consistency, tables, scoring and a 200-case fuzz**; the **real report pipeline** (real fpdf2/PyMuPDF): clean, flawed-then-corrected, still-wrong-refused, worse-correction ignored, soft findings delivered and listed, check switched off, a failed merge, a crashing audit, manifest, tables as figures; data loading (every separator, BOM, cp1252, JSON, pasted, Excel with a stdlib fallback reader, types, dates, units, missing values, totals rows); the maths against independent calculations (decimals, Excel quartiles, trade profile by hand, group shares, outliers, correlations); the AI-wording check; the PDF and Excel files with **every Excel formula range re-evaluated against the Data sheet**; the front door (routing, owner-only, no hijacking of ordinary sentences, edits from a photo / reply / last picture, AI edit with and without Gemini, design, charts, data files, pasted tables); keys (stored, message deleted, never repeated or logged, shape checks, unwritable secrets file); the live test; buttons (owner only, others ignored); forgetting and pruning; status, capabilities, regression rows, command and menu button; and **structure checks** (owner check before any route; only owner-side code saves keys; secrets read in one place; named providers over https only; no shell/eval/pickle/process; files only in the private folder; one table; heavy libraries imported where used; `ask_ai` not wrapped). **Mutation checks** put the old behaviour back one piece at a time (an image check that accepts anything, unenforced size, an always-on paid engine, engines that never rest, a filter that lets blocked prompts through, an audit that finds nothing, a matcher that accepts every figure, a gate that ignores the numbers, the check always off, verification pages never attached, a chart maker that invents data, a front door open to everyone, buttons obeyed from anyone, a key echoed back, a status that prints keys, an unchecked AI summary, floating-point statistics, a wrong drawdown, a double-counted totals row, edits that do nothing, text not drawn by code, a hijacking router) and the matching test goes red (all do).

Other gates: `py_compile` OK; pyflakes 158 findings in v89 and the same 158 in v90; secret-pattern scan of the new layer clean (in the tests only the scanner's own pattern strings match; the fake keys used are obviously synthetic); `_update_cred_changes` v89→v90: no changed or removed credentials; the diff outside the appended layer is limited to the docstring line, the self-edit protection prefix and the secret-command list (so `studio key …` is never stored in the activity log).

## 5. Offline-tested vs not verified live

**Offline-tested:** everything above, against scripted replies.

**Not verified live (this sandbox could not reach any image provider, Telegram or the web) — please run the checks in section 6:**
* **Every image engine against its real service.** The adapters follow each provider's documented request and reply shapes, but providers change endpoints, model names, free limits and error replies; `test image engines` tells you what works from your server today. Your NVIDIA, Pollinations and Horde routes are the likeliest to differ.
* How pictures, files, captions and the three buttons look and behave in the real Telegram app, and the real size limits for uploads.
* A full researched report end to end with live search and the real AI: the numbers check was run on the real PDF pipeline with scripted research and AI, so how often real model drafts need the correction pass is unknown until you use it.
* Excel formulas were verified by re-computing every range from the Data sheet in Python; no spreadsheet application was available in the sandbox to open the file, so please open one Excel file.
* Fonts on your server (the verification and data PDFs use DejaVu if present, else a plain font with ASCII-safe text), `rembg` (not installed here), `pypdf` vs PyMuPDF merge on your server.
* Background removal quality on real photos (the plain-background method is conservative by design).
* No live trades and no paid-API tests were run.

## 6. Quick checks through Nemo

1. `studio` → the engine list; `test image engines` (a couple of minutes, free engines only); if all fail, `studio setup`, then `studio key together <key>` and test again.
2. `draw a lighthouse at dusk, watercolor, instagram story, 2 variants` → two exact-size pictures naming the engine; tap **🔄 Again** and **⬆ 2x bigger**.
3. Send a photo with the caption `resize to 1080x1080, black and white, add text "SALE" at the top`; then `remove the background` on a plain-background photo; `color palette`; `image info`.
4. `make a poster saying "Diwali Sale" "Up to 50% off" "12-14 Oct"` · `design a logo for "Nemo Studio"` · `gradient wallpaper, ocean` (no AI used).
5. `bar chart: Jan 120, Feb 150, Mar 90` · `make a chart of the gdp of india` (it should ask for numbers, not invent them).
6. `make a pdf about oil prices and the Indian economy` → look for the `🔢 Numbers check` line and the last pages of the PDF.
7. Send a trade log CSV and say `analyse this file`; open the Excel file and compare one figure with its formula.

## 7. Installing and rolling back

Upload `nemotron_bot.py` to Nemo on Telegram and send `/update` (v85 pre-flight: compile, credential comparison, sandbox import and regression run), then **Apply & restart**; `/rollback` restores the previous file. No key is required to start: add engine keys later with `studio key …`. Optional packages: `Pillow` and `matplotlib` (installed by Nemo when first needed), `openpyxl` (Excel export), `pypdf`, `rembg`. The only new database table is `studio90_image` (the pictures kept for follow-ups).
