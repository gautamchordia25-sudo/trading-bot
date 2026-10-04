# How to use each program you installed

You installed the picks from `NEMO_FORGE_PICKS.md`. This guide says, for each one: what it is for, how to use it **today** (every command here was run for real on a test machine unless it says "not run"), and what it will do for you once Nemo's own code calls it.

## 0. The one thing to know first

There are two kinds of installs, and they work differently:

| Kind | What you installed | How you use it **today** |
|---|---|---|
| **Tools** (each in its own isolated environment) | ruff, vulture, detect-secrets | From Telegram: `forge run <name> <program> <arguments>`. They work now. |
| **Libraries** ("into yourself") | pdfplumber, trafilatura, pandas-ta-classic, jugaad-data, quantstats, pytesseract, sqlite-vec, fastembed, faster-whisper | **Nemo has no chat command that calls them yet.** They are installed and import correctly, but a library only helps once a Nemo version uses it. Section 2 shows what each does (with code I ran) and section 3 lists the commands the next version would add. |

Check what is installed any time: `what have you installed`. Take anything away with `remove NAME`.

## 1. The three tools (use them now)

Use the real path of the bot file on your server instead of `/root/nemotron_bot.py` if it is somewhere else. `forge run` only runs programs Forge installed, with no shell, a clean environment (none of Nemo's keys), a 120-second limit, and output cut to the last ~3,300 characters.

### ruff: finds mistakes in Python code, in a fraction of a second
```
forge run ruff ruff check --select F --statistics /root/nemotron_bot.py
forge run ruff ruff check --select F /root/nemotron_bot.py
```
* `--select F` = the "pyflakes" family: unused imports (F401), unused variables (F841), **undefined names (F821)**, redefinitions (F811).
* The first command prints a summary count; the second lists each finding with the line.
* "exit code 1" just means it found something. On the current file it reports about 137 findings in 0.3 s. Most are normal for a file made of stacked layers (F811 redefinitions, unused imports). **F821 (undefined name) is the one to look at**: of the 13 in the file I checked two (`tts_send`, `_hands_snapshot_text`) and both are inside `try/except`, so harmless; the rest are not triaged.
* Use it before you apply an upgrade: a new version should not have *more* F821 than the old one.

### vulture: finds code nothing uses
```
forge run vulture vulture /root/nemotron_bot.py --min-confidence 100
forge run vulture vulture /root/nemotron_bot.py --min-confidence 90
```
* At 100 it reports 39 certain problems (for example `unsatisfiable 'if' condition` at a few lines); at 90 it reports 88 (mostly unused imports). Lower numbers print a lot more, and the reply is cut at about 3,300 characters, so start at 100.
* Exit code 3 means "found something".
* Dead code is a clue, not an order: in this file, functions are often replaced by later layers on purpose.

### detect-secrets: looks for keys and passwords left in a file
```
forge run detect-secrets detect-secrets scan /root/nemotron_bot.py
```
* It prints JSON. **An empty `"results": {}` means nothing was found.** The end of the reply is what matters.
* On the current file it reports **one** finding, and it is a false alarm: the example proxy address `http://user:pass@host:port` in the help text on line 1. That is how to read it: a type (here "Basic Auth Credentials") and a line number; open that line and decide.
* Run it on any file before you send it or share it, especially a file you did not write.

## 2. The libraries (installed; what each does and how it behaves)

These snippets run in the same Python Nemo runs in. They are what the next version's commands would do under the hood. All were run in a test environment unless marked "not run".

### pdfplumber: exact tables and text from PDFs
```python
import pdfplumber
with pdfplumber.open("statement.pdf") as pdf:
    tables = pdf.pages[0].extract_tables()
# [[['Contract','Qty','Price'], ['NIFTY OCT FUT','75','24590.50'], ...]]
```
* On a test contract-note-style PDF it returned the table cell for cell. The command-line form `pdfplumber statement.pdf --format text` also works (it keeps the column layout).
* Works on machine-made PDFs (broker statements, contract notes). For scanned pages use OCR (below).

### trafilatura: the main text of a web page, without menus and banners
```python
import trafilatura
text = trafilatura.extract(html)                       # plain text
md   = trafilatura.extract(html, output_format="markdown")
```
* On a sample news page the command-line form (`trafilatura --input-dir pages --output-format txt`) kept the headline and the two paragraphs and dropped the menu and footer. **Very short pages can keep a menu line** (my tiny test page kept "Home"), so treat it as better than raw scraping, not perfect.
* If Forge installed an older release because the newest needs newer core packages than your server has (see `NEMO_FORGE_PICKS.md`), the function names above still work.

### pandas-ta-classic: 150+ technical indicators
```python
import pandas_ta_classic as ta
rsi = ta.rsi(close, length=14)
atr = ta.atr(high, low, close, length=14)
# also: ta.adx, ta.bbands, ta.supertrend, ta.vwap
```
* On 200 synthetic candles it computed RSI(14) and ATR(14); `adx`, `bbands`, `supertrend` and `vwap` exist in the package.
* It works on a pandas table of your candles. Research only: **it never touches the broker.**

### jugaad-data: NSE history and live data (index, stocks, futures and options)
Function names and signatures read from the installed package (**not run: the NSE website is not reachable from my test machine**):
```python
from jugaad_data.nse import stock_df, index_df, derivatives_df, expiry_dates, bhavcopy_fo_save, NSELive
# stock_df(symbol, from_date, to_date, series='EQ')
# index_df(symbol, from_date, to_date)
# derivatives_df(symbol, from_date, to_date, expiry_date, instrument_type, strike_price=None, option_type=None)
# expiry_dates(dt, instrument_type='', symbol='', contracts=0)
# bhavcopy_fo_save(dt, dest, skip_if_present=True)      # the day's F&O bhavcopy file
# NSELive(): live_fno, all_indices, holiday_list, index_option_chain, corporate_announcements ...
```
* NSE can change its pages or block a server; the package has had a "YOLO" licence text. Treat it as a convenient data source, not a guaranteed one, and always compare with your broker's data before acting on it.

### quantstats: performance and risk reports
```python
import quantstats as qs
qs.stats.sharpe(returns); qs.stats.max_drawdown(returns); qs.stats.cagr(returns)
qs.reports.html(returns, output="journal.html", title="Journal")
```
* On 400 synthetic daily returns it computed Sharpe, max drawdown and CAGR and wrote a **440 KB HTML tear-sheet**. It needs a table of daily returns (from your trade journal), not individual trades.

### pytesseract + tesseract: read text from pictures (English and Hindi)
Needs the system program too (`forge apt tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin`).
```python
import pytesseract; from PIL import Image
pytesseract.image_to_string(Image.open("shot.png"), lang="eng")
pytesseract.image_to_string(Image.open("hindi.png"), lang="hin")
```
* On a test screenshot it returned `NIFTY OCT FUT Qty 75 Price 24590.50` exactly; on a Hindi line (`भारतीय रिज़र्व बैंक ब्याज दर`) it returned the same text exactly. Clean, large text is easy; blurry photos, small print or handwriting are much worse.

### sqlite-vec: nearest-neighbour search inside SQLite
```python
import sqlite3, sqlite_vec
db = sqlite3.connect("memory.db"); db.enable_load_extension(True); sqlite_vec.load(db)
db.execute("create virtual table v using vec0(e float[384])")
# insert vectors, then:  select rowid, distance from v where e match ? and k=5
```
* On a 3-number toy it returned the nearest two rows with the right distances. It is **pre-1.0**: expect changes.

### fastembed: turn text into vectors locally (feeds sqlite-vec)
```python
from fastembed import TextEmbedding
model = TextEmbedding("BAAI/bge-small-en-v1.5")
vectors = list(model.embed(["text one", "text two"]))
```
* **Not run:** it downloads a model from Hugging Face on first use, and my test machine cannot reach that site. **Your server must be allowed to reach `huggingface.co`** (and its download hosts).

### faster-whisper: speech to text on the server, no key
```python
from faster_whisper import WhisperModel
model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe("voice.ogg")
text = " ".join(s.text for s in segments)
```
* **Not run** (same reason: model download from Hugging Face). Model sizes are approximate: `tiny` about 75 MB, `base` about 145 MB, `small` about 465 MB; bigger is better and slower. On a CPU-only server expect it to be slower than Groq's cloud Whisper, which is why it is a fallback, not a replacement.

## 2b. Will it fit in your server's memory?

Your server has **1.6 GB of memory available and 1.7 of 2.0 GB of swap already in use** (your screenshot), so each job should be small and run one at a time. I measured the real peak memory of a typical job for each library (a separate process, Python 3.11 on a test machine; yours will differ a little). A bare Python process is 8 MB.

| Job | Peak memory | Verdict for your server |
|---|---|---|
| ruff / vulture / detect-secrets on the bot file | small (a few tens of MB; not measured separately) | fine |
| pdfplumber: a one-page 40-row table | **37 MB** | fine (a big, many-page PDF uses more) |
| trafilatura: one article | **35 MB** | fine |
| pandas-ta-classic: RSI, ATR, Supertrend on 2,000 candles | **69 MB** | fine |
| sqlite-vec: 1,000 vectors | **13 MB** | fine |
| tesseract: one 1200×800 picture | **44 MB** | fine |
| quantstats: a tear-sheet from 400 days of returns | **208 MB** | fine alone; the heaviest of these |
| faster-whisper (voice) and fastembed (vectors) | **not measured** (they need a model download my test machine cannot do) | the `tiny`/`base` models are the realistic ones; expect several hundred MB while loaded and a slow 1-core CPU |

The rule for the next version: **one heavy job at a time, in a short-lived separate process, only when enough memory is free**, otherwise "low on memory, try again in a few minutes". That keeps the trading bot out of swap. Check the server yourself any time: say `server status` (v91.3) and Nemo reads memory, swap, disk, CPU and the biggest memory users directly.

## 3. Now built: v92 "Wire" (these are real chat commands)

**Status: built in v92.0 except item 9** (semantic memory is deferred; see `NEMO_V92_WIRE.md`, which has the exact phrases, the memory rule and what is verified). Each is owner-only and read-only, and none touches the broker:

1. `check this file` / `before update`: runs ruff, vulture and detect-secrets on the new file and puts the result next to the sandbox pre-flight (warning only).
2. `tables from this pdf` (send or reply to a PDF) → the tables as a spreadsheet; works with the existing document flow.
3. `read this picture` (send or reply to a picture) → the text, English or Hindi.
4. `read this article <link>` → the clean text, then your normal summary or notes.
5. `indicators NIFTY 15m` → RSI, ATR, ADX, Supertrend on your own candle feed, as text or a chart.
6. `nse history NIFTY futures from … to …` → a table, if the NSE site answers.
7. `tearsheet my journal` → the quantstats report as a file.
8. Voice notes keep using Groq; **if Groq fails, Nemo transcribes locally** and says so.
9. `search my files` / semantic memory (sqlite-vec + fastembed), with a fallback when Gemini's embedding quota is used up.

Until you update to v92.0, the three tools in section 1 are the only ones you can use from Telegram. Say `wire` after updating to see which commands are ready.

## 4. What I could not check

* **Your server:** where `nemotron_bot.py` lives, its free memory and disk, and whether it can reach `huggingface.co`, `nseindia.com` and `pypi.org`.
* **Model-based libraries** (fastembed, faster-whisper): not run, no model download was possible here.
* **jugaad-data** against the live NSE site.
* No live trade was placed and no paid API was called.
