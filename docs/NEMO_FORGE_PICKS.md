# What Nemo should get from GitHub / PyPI: verified picks and how to install them

You asked me to research what Nemo can get from GitHub that is best for him, and to write the install guide.
This is a shortlist, not a catalogue: **12 picks, 10 things to avoid, and the exact words to say to Nemo.**
Everything is installed through **Forge (v91.1)**, so every install is a card you approve, with pinned files, a health check and automatic rollback.

## 0. The short answer

| Do this first (works today, tiny) | Why |
|---|---|
| **ruff**, **vulture**, **detect-secrets** | A safety kit for every future Nemo upgrade: fast lint, dead-code finder, secret scanner. Ruff read the 5 MB `nemotron_bot.py` in 0.3 s. |
| **pdfplumber** (into himself) | Exact tables out of PDFs (contract notes, statements). Tested: it returned the table cell-for-cell. |
| **trafilatura** (into himself) | Clean article text for research (drops menus, cookie banners). Tested on a sample page. |

| Worth adding next (needs a Nemo version that uses it) | Why |
|---|---|
| **pandas-ta-classic**, **jugaad-data**, **quantstats** | Futures desk: 150+ indicators, NSE futures/index history, risk tear-sheets. Research only, never in the live order path. |
| **tesseract-ocr** (+ `pytesseract`) | Read text from pictures and scans, including Hindi. |
| **faster-whisper** | Voice notes without any key (backup when Groq's quota or key fails). |
| **sqlite-vec** (+ `fastembed`) | Local semantic memory, so recall does not depend on Gemini's embedding quota. |

**Important:** installing a *library* does not give Nemo a new ability by itself. A library only helps once a Nemo version imports it. The "tools" (ruff, vulture, detect-secrets) you can use immediately with `forge run`. If you want the libraries wired in, that is the next version (section 6).

## 1. How I researched this, and how far to trust it

* **Starting point: what Nemo already has and lacks** (read from the code): he already uses requests, Pillow, matplotlib, fpdf2, PyMuPDF, pypdf, openpyxl, python-docx, python-pptx, yt-dlp, youtube-transcript-api, ddgs, gTTS/edge-tts, Playwright, BeautifulSoup, OpenCV, Flask. Voice-in is Groq Whisper (cloud, needs a key). Embeddings are Gemini's (cloud). `pip-audit` and `bandit` are already available through his own security commands. His backtests are his own code. So I did not suggest any of those again.
* **Verified for real (free, no key):** for each candidate I ran Forge's own PyPI check and a real `pip download` on a test machine (Python 3.11, Linux x86-64): licence, age, release count, known vulnerabilities, whether finished wheels exist, how many packages and megabytes it adds. For nine of them I also **installed, ran and removed** them with the real Forge code, in isolated environments on the test machine (results are in the table; the "into yourself" sizes below were measured from a real download plan, not installed).
* **GitHub star counts** come from reading each repository page (a quick read, so treat them as approximate). Web-search results (blog lists, "skills" sites) were only pointers: most were low quality, and I did not rely on them.
* **Not the same machine as yours:** sizes and "does a wheel exist" are for the test machine. Your VPS's Python version, CPU and free disk can differ. **The approval card shows the real numbers for your server before you tap.**

## 2. The picks, ranked for Nemo

"Added here" = what the install adds on the test machine (the packages your server already has, such as numpy, pandas, Pillow and cryptography, are left alone).

| # | Pick | What it gives Nemo | Evidence (PyPI, checked now) | Added here | Verified live |
|---|---|---|---|---|---|
| 1 | **ruff** (tool) | Lint and format check of any new `nemotron_bot.py` before `/update`; finds unused code, undefined names | 0.16.10, MIT, 426 releases, updated yesterday, ~50k GitHub stars | 9.9 MB, 1 package | installed, ran, removed |
| 2 | **detect-secrets** (tool) | Scans a file for keys and tokens before it is sent or pushed (your "never embed secrets" rule) | 1.5.0, from Yelp, 38 releases, last release 2.4 years ago (still the standard tool) | 1.5 MB, 4 new | installed, ran, removed |
| 3 | **vulture** (tool) | Dead-code finder: useful in a file made of 150 stacked layers | 2.16, MIT, 56 releases | ~0 MB | installed, ran, removed |
| 4 | **pdfplumber** (library) | Exact **tables** from PDFs (it scored best on tables in one comparison I read, a blog, so weak evidence), text with positions | 0.11.10, MIT, 76 releases, updated 110 days ago, ~10.8k stars | +4 packages, 10.2 MB | table returned exactly |
| 5 | **trafilatura** (library) | Main text of a web page without menus/ads: better evidence for Research v2 than raw scraping | 2.3.0, Apache-2.0, updated yesterday, ~6.9k stars | +14 packages, 13.2 MB | extraction tested on a sample page |
| 6 | **pandas-ta-classic** (library) | 150+ technical indicators (RSI, ATR, ADX, Supertrend, VWAP…) in plain pandas | 0.8.32, MIT, updated 19 days ago | +2 packages, 0.6 MB | RSI and ATR computed |
| 7 | **jugaad-data** (library) | NSE data: stocks, indices and **F&O history**, RBI rates, built-in cache | 0.35.9, updated 10 days ago, ~583 stars. **Licence is a non-standard "YOLO" text:** read it before relying on it | +7 packages, 0.6 MB | not run (needs the NSE site) |
| 8 | **quantstats** (library) | Risk and performance tear-sheets (Sharpe, drawdown, Monte-Carlo) for the trade journal | 0.0.86, Apache-2.0, updated 5 days ago, ~7.7k stars | +17 packages, 49 MB | not run |
| 9 | **tesseract-ocr** + **pytesseract** | Read text from pictures and scanned PDFs, English and Hindi. (apt program + tiny Python part) | pytesseract 0.3.13, Apache-2.0; tesseract is on Forge's apt allow-list | pytesseract ~0 MB; apt a few tens of MB | not run |
| 10 | **faster-whisper** (library) | Local speech-to-text for voice notes, no key, 99 languages | 1.2.1, MIT, ~25.7k stars | +12 packages, **104 MB**, plus a model it downloads on first use (tiny ≈ 75 MB, small ≈ 450 MB: approximate) | not run (model download) |
| 11 | **sqlite-vec** (library) | Vector search **inside Nemo's existing SQLite** database | 0.1.9, MIT/Apache, ~8.2k stars. **Pre-1.0: expect breaking changes** | +1 package, 0.2 MB | nearest-neighbour query returned the right rows |
| 12 | **fastembed** (library) | Local text embeddings (ONNX, no PyTorch) to feed sqlite-vec | 0.8.1, Apache-2.0, updated 10 days ago, ~3.2k stars | +16 packages, 32.6 MB, plus a model on first use | not run |

Small helpers I checked but rank lower: **rapidfuzz** (3 MB, MIT; fuzzy matching, "did you mean"; it needs lower-casing to match well), **tenacity** (tiny; retry with backoff), **dateparser** (1.8 MB, BSD; natural dates), **duckdb** (20 MB; SQL over your CSV/Excel files for data reports).

**Choose by licence if you ever redistribute Nemo:** MIT/Apache/BSD are free of strings. `quantstats` is Apache-2.0. `arch` is NCSA. `backtesting` and `OpenAlgo` are **AGPL** and `piper-tts` is **GPL**. For private use on your own VPS none of that matters; it matters only if you share the code.

## 3. Install guide (say these to Nemo, in your private chat)

### Before you start
1. Make sure Nemo is **v91.1** (send `/version`). If not, send him the new `nemotron_bot.py`, type `/update` and tap **Apply & restart** after the pre-flight.
2. Optional but recommended: `forge key github <token>` (a read-only GitHub token; Nemo deletes your message). It only affects the GitHub look-ups, not PyPI installs.
3. Nemo must be allowed to reach `pypi.org`, `files.pythonhosted.org` (where pip downloads) and, for GitHub look-ups, `api.github.com`. If your VPS firewall limits outgoing sites, allow those.
4. Say `forge` → check **free disk** on the server is above 2 GB (Forge refuses to download with less than 1 GB free).

### Stage A: the upgrade-safety kit (tools, each in its own isolated environment)
```
install ruff
install vulture
install detect-secrets
```
For each one Nemo replies with a **card**: package, version, licence, age, the SHA-256 of every file, size, and risk lines. Tap **Approve**. He installs it, runs a health check, and tells you how to run it. Then:
```
forge run ruff ruff check --select F --statistics /root/nemotron_bot.py
forge run vulture vulture /root/nemotron_bot.py
forge run detect-secrets detect-secrets scan /root/nemotron_bot.py
```
(Change `/root/nemotron_bot.py` to wherever your bot file is on the server. `ruff`'s output ends with a count; `detect-secrets` prints JSON, and an empty "results" list means nothing was found. The three commands above are the forms I ran for real.)

### Stage B: libraries Nemo's own code can import ("into yourself")
```
install pdfplumber into yourself
install trafilatura into yourself
install pandas-ta-classic into yourself
install jugaad-data into yourself
```
The card says **"INTO MY OWN PYTHON (nothing already installed is changed)"** and lists what is already there and left alone. After you approve, Nemo checks the import and replies "import check passed". No restart is needed.
**If Nemo answers "its requirements clash with packages that are already installed"** (this happened with `trafilatura` on the first version of Forge): the newest release of a library often wants *newer* versions of core packages than your server has (trafilatura 2.3.0 asks for `charset_normalizer>=3.5.2`, `lxml>=6.1.3` and `urllib3>=2.8.0`), and Forge never changes what is already installed. **From v91.2 Forge no longer stops there:** it asks pip for the **newest release that fits** your server and shows it on the card with a warning, for example "the newest release (2.3.0) needs newer packages than this server has; this is the newest release that fits: 1.12.2". That older release goes through the same safety checks as any other. On a test server with older pinned core packages this installed trafilatura 1.12.2 and left every existing package exactly as it was.
If no release fits, the message now names the package in the way ("trafilatura 2.3.0 needs charset_normalizer>=3.5.2, this server has 3.3.2") and offers `install NAME as a tool` (its own environment, which cannot clash, but my own code cannot import from there). If a card says it would change something already installed, Forge refuses that by design and says which package clashed. If you ask for something that is already in Nemo, he says so instead of making an empty card.

OCR (needs one system program, so two steps):
```
forge apt tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin
install pytesseract into yourself
```
(`forge apt …` needs the bot to run as root, simulates first, refuses anything that would upgrade or remove a system package, and shows a card.)

Later, if you want them:
```
install quantstats into yourself
install sqlite-vec into yourself
install fastembed into yourself
install faster-whisper into yourself
```
(Add the word `big`, for example `install X into yourself big`, only if Nemo says a download is over the 300 MB limit; faster-whisper is about 104 MB.)

### Checking and undoing
* `what have you installed` lists everything Forge added, where, and when.
* `remove ruff` (or any name) takes it away: an isolated environment is deleted, or exactly the packages that install added are uninstalled. The approval card's **Undo** does the same within 24 hours.
* `forge status` shows the token, the GitHub allowance left and what is waiting for your tap.

### Let Nemo propose, you approve
You can also just ask: "which python library can read tables out of PDFs?" He can search and look up PyPI/GitHub himself and **propose** an install; you still get the card. If you trust one specific package, `forge allow ruff` lets his own proposals for that package skip the tap (never for the protected core packages).

## 4. What I would not install (and why)

| Package | Why not |
|---|---|
| `diskcache` | Two known security problems in the current version (GHSA-w8v5-vhqr-4h9v, PYSEC-2026-2447) and no release for 3 years. |
| `ta` | Publishes only source code, so installing it would run its build script on your server. Forge refuses it. `pandas-ta-classic` does the same job with wheels. |
| `pandas-ta` (the original) | Its current release needs Python 3.12 or newer. Forge refused it on the Python 3.11 test machine. Check your VPS's Python first. |
| `mplfinance` | Last release over 3 years ago and still a beta tag. Nemo already draws candles with matplotlib. |
| `markitdown` (plain) | Fine for HTML and Office files, but **it cannot read PDFs without its `[pdf]` extra**, and Forge installs a package by name only (no extras). pdfplumber covers PDFs. |
| `docling` | AI layout models: gigabytes of download, and one benchmark I read puts it near 6 GB of memory. Too heavy for a small VPS. |
| `vectorbt` | Very heavy (numba, plotly, dash) and Nemo already has his own backtests. |
| `backtesting` | AGPL licence, and it duplicates Nemo's own backtester. |
| `mcp` (the Python SDK) | His MCP presets deliberately **pin `mcp<2`** because version 2 broke the servers' imports. Do not install `mcp` yourself; use `/mcp preset fetch`, `/mcp preset time` and `/mcp preset git`. |
| `piper-tts` | GPL licence, voice files downloaded separately, and he already has gTTS and edge-tts. Only if you need offline voice. |

Also be careful with obscure packages that blog lists call a "personal AI assistant" (two turned up in my searches). I did not check or recommend them: little evidence of use, and a new package is exactly what an attacker would copy. Forge's checks (look-alike names, age, wheels only, hashes) apply to everything, but the safest package is one with many users.

## 5. Things on GitHub that are not packages

* **Your own repository** (done in v91): `forge source owner/name@branch`, then `check for upgrades on github`. This is the most powerful one: Nemo can fetch his next version himself and hand it to the normal `/update` gate.
* **MCP reference servers** (`modelcontextprotocol/servers`, ~91k stars): his presets already cover `fetch`, `time` and `git` (Python) and `filesystem`, `memory` (need Node). **Leave `filesystem` off**: it lets a model read and write files under `/root`.
* **Lists to search with Nemo** (`search github for awesome quant python`, `search github for awesome mcp servers`): good places to discover more, but read the card and scan before trusting a name.
* **OpenAlgo** (`marketcalls/openalgo`, ~2.8k stars, AGPL): a self-hosted trading platform whose 36 broker connectors include Fyers. Worth knowing about; **I do not recommend putting anything between Nemo and your live orders** without a separate review.

## 6. What is not wired yet (the honest gap) and what I propose for v92

Right now Forge can **get** these programs. The code that **uses** them does not exist yet, except the three Stage A tools you run by hand. I propose, in this order:

1. **Upgrade safety:** the update gate also runs ruff (new undefined names vs the old file), vulture and detect-secrets, and shows them as warnings next to the sandbox result.
2. **Document tables:** pdfplumber inside Document Intelligence and data reports (broker statements, contract notes).
3. **Research reading:** trafilatura for the page text Research v2 reads.
4. **Offline voice and OCR:** faster-whisper as a fallback when Groq fails; tesseract for pictures.
5. **Futures research lab:** pandas-ta-classic + jugaad-data + quantstats for indicator studies and journal tear-sheets, **read-only, never calling the broker.**
6. **Local memory:** sqlite-vec + fastembed as a fallback when Gemini's embedding quota is spent.

Say "wire the picks" (or choose numbers) and I will build it as the next version, with tests.

## 7. Two findings from this research

1. **A real Forge bug, fixed in v91.1:** some programs (ruff is the main one) ship their program as a plain file in the wheel instead of an entry point. Forge did not see it, so `forge run ruff …` would have been refused. v91.1 reads those programs, with a test that builds such a wheel, installs it for real and runs it. Verified with the real ruff.
2. **ruff already earned its place:** on the current `nemotron_bot.py` it reports 137 "F" findings (68 unused imports, 42 unused variables, 13 undefined names, 12 redefinitions…). Most come from the stacked-layer style and were in the earlier files too. I looked at two of the 13 undefined names (`tts_send`, `_hands_snapshot_text`): both sit inside `try/except` or a `globals().get(...)` check, so they are harmless. I did **not** check the other eleven; they are worth a triage when ruff is part of the gate.

## 8. Not verified (say so before relying on it)

* **Your VPS:** its Python version, free disk, RAM and firewall. The card shows the real size; if it is too big or no wheel exists, Forge says so.
* **GitHub itself from Forge** (still unreachable from my test machine) and the Telegram look of the cards.
* **Model-based picks** (faster-whisper, fastembed, rapidocr, tesseract languages): the packages install, but the models download on first use, and I did not run them.
* **jugaad-data and quantstats** against real market data.
* **Star counts** are approximate (read from the repository pages).
* No live trade was placed and no paid API was called.
