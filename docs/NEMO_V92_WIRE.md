# Nemo v92.0 "Wire": the libraries you installed become chat commands

You installed the picks from `NEMO_PICKS_HOWTO.md` (pdfplumber, tesseract, trafilatura, pandas-ta-classic, quantstats, ruff, vulture, detect-secrets, …).
In v91 nothing in Nemo called them. v92 wires each one to a plain sentence in chat. Everything from v91 (Forge) and earlier is kept. Your credentials, owner lock,
trading and holiday guards, existing permissions and approvals, backup and rollback are untouched. **Nothing here places an order, reads the broker's account or
writes to the broker.** Every command is owner-only, in a private chat.

Type **`wire`** (or tap 🔌 Wire in the menu) at any time: Nemo lists which of the commands below are ready and which library is still missing, with the sentence that installs it.

## 1. Why one runner, and the memory rule

Your server has 2 cores and about 3.8 GB, shared with another application, and its swap was nearly full. A heavy library loaded inside the trading bot would push the bot into swap.
So every heavy job goes through **one runner** (`_n92_child`):

- a **separate short-lived Python** (the same Python the Forge installs libraries into), started with `nice -n 10` (low priority);
- an environment **with none of Nemo's keys or tokens** (the Forge minimal environment);
- **one job at a time** (a second request gets "busy, try in a minute");
- started **only when the server has the memory**: available memory must exceed the job's need plus 300 MB, and the kernel's memory-stall figure (PSI) must be under 20%. Otherwise: *"I am low on memory right now (…), so I did not start it and the trading bot stays out of swap."* When the server does not report its memory, the job is allowed;
- a time limit per job, a plain sentence when it fails (library missing, model not downloaded, system program missing, timeout), and the job's temporary folder deleted afterwards (only folders created by this layer can be deleted).

Memory each job really used on the test machine (peak, MB): pdfplumber 37, trafilatura 35, pandas-ta-classic 69, tesseract 44, quantstats 208. The guard asks for more than that (250, 250, 200, 350, 350 MB, plus the 300 MB margin). The model-based job
(faster-whisper) could not be measured here (the model host is not reachable from my sandbox), so its 500 / 800 / 1500 MB figures are estimates.

Programs still start in exactly one place (`_n91_run`, from Forge). The v92 layer opens no web address itself: pages are opened by the existing safe fetcher (`_n85_fetch`: scheme, ports, private addresses, redirects, size and type are checked).

## 2. The commands

| You say | What happens | Needs |
|---|---|---|
| `tables from this pdf` (send a PDF with those words, or reply to a PDF) | the tables found by pdfplumber come back as an `.xlsx` (one sheet per table, numbers converted); a scanned PDF is detected and you are told to use `read this picture` instead | pdfplumber, openpyxl |
| `read this picture` / `ocr` (photo with the words as caption, or reply to a picture) · add `in hindi` / `in english` | the text in the picture, English + Hindi by default | pytesseract, pillow, and the program tesseract (`forge apt tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin`) |
| `read article https://…` (also `clean text of`, `extract the page`, `read the story from`) | the page is fetched by the safe fetcher, trafilatura keeps the article and drops menus and cookie banners; long text also comes as a file. The text is labelled as written by a third party (untrusted) and secrets are masked. If the extractor finds little, you get the plain page text and are told | trafilatura |
| `indicators NIFTY` / `technical read RELIANCE` | RSI(14), ADX(14) with +DI/−DI, Supertrend(10,3), Bollinger(20,2), EMA20/50, MACD histogram, ATR on the **daily** candles Nemo already reads (≥ 35 candles). Descriptive wording only: it is not a signal and nothing goes to the broker | pandas-ta-classic |
| `tearsheet` / `journal report` · `tearsheet capital=5L days=60` | quantstats report of your trade journal as an HTML file, plus a short summary. Daily P&L is divided by capital (default: your saved capital setting). Needs at least 10 trades on 8 different days, otherwise Nemo says so instead of printing noise | quantstats |
| `nse history RELIANCE from 2026-09-01 to 2026-09-30` · `nse index NIFTY 50 last 30 days` · `nse futures NIFTY expiry 2026-10-28 from … to …` | a CSV from the NSE site with the first rows shown; start before end, within one year | jugaad-data |
| (automatic) a voice note when **Groq fails** | the note is transcribed on the server with faster-whisper and Nemo says so once every ten minutes. The setting `wire_stt_model` (read from the environment or `bot_secrets.json`, like the Studio settings) is `tiny`, `base` (default) or `small`; the guard asks for 500 / 800 / 1500 MB free (my estimates, not measured here). The model downloads once on first use | faster-whisper |
| (automatic) `update` with a new file waiting | before the normal update flow, an extra message compares the **new** file with the **running** one using ruff (undefined names and all findings), vulture (certain dead code) and detect-secrets (new possible secrets). **Information only**: the existing sandbox pre-flight and your Apply tap still decide | the three tools installed through Forge |

Dates accept `2026-09-01`, `01-09-2026`, `01/09/2026`, `1 Sep 2026`, `1 September 2026`. Amounts accept `5L`, `1.5cr`, `250k`.
Other messages that merely contain a link or the word "indicators" are left to the older layers exactly as before; only these phrases are caught.

## 3. Also fixed: MCP servers no longer linger

`server status` (v91.5) showed an `npm exec @modelcontextprotocol/server-filesystem` wrapper and its `node` server running while no MCP server was registered. The wrapper started the node
process, and stopping the wrapper left the node process behind. Now each MCP server starts in its own session, `stop()` ends the whole group (npm wrapper **and** node server; if the group
is somehow Nemo's own, it falls back to ending the single process), and every server is stopped when Nemo exits. Leftovers from before this version are still cleaned with the v91.5 card (`forge stop …`).

## 4. How to check it, through Nemo (nothing here trades or spends)

1. `update` Nemo to v92.0 with your usual flow. Say `version`: it should say 92.0.
2. `wire`: you should see ✅ for the libraries you installed and a "not ready: install X into yourself" line for the others. If something is missing, say what it tells you, and tap Approve on the card.
3. `tables from this pdf`: send a bank statement or contract note PDF with those words.
4. Send any screenshot with the caption `read this picture`.
5. `read article` and a news link.
6. `indicators NIFTY`.
7. `tearsheet` (needs a journal of at least 10 trades on 8 days).
8. `nse history RELIANCE last 10 days`: this one may be blocked by the NSE site; that is not a Nemo fault (see section 6).
9. Send a voice note while Groq is not configured or is down; the first transcription downloads the model.
10. Next time you send me a new file: `update` and look for the "EXTRA CHECKS" message before the pre-flight result.
11. Say `server status` before and after a heavy job to see memory (Nemo runs one job at a time).

## 5. Tests (offline, no network, no trades, no paid calls)

- `tests/test_wire92.py`: **89 tests**. The runner (one JSON line, bad output, clean environment, `nice`, timeout, failure words, memory guard, one-at-a-time lock, job-folder containment, pruning), every command with a stubbed runner (phrases that count and those that must not, files, masks, empty and failing results), the voice fallback (Groq first, local second, one notice per ten minutes), the update checks (using small fake tools in an environments folder), the status and front door (owner only, private chat only), the MCP group stop, and structural checks on the source (the v92 layer starts no program of its own, uses no shell, opens no address, never touches the broker or the trading guards, only reads the owner lock; helper programs are valid and print exactly one JSON line).
- `TestRealLibraries` (5 tests, run when `NEMO_WIRE_PY` points at a Python that has the libraries): pdfplumber returns a generated PDF's table cell for cell; tesseract reads a generated picture; trafilatura drops the menu and keeps the article; pandas-ta-classic gives numeric RSI/ATR/ADX/Supertrend/Bollinger/EMA/MACD; quantstats writes a report. **They passed on my test machine** with the libraries installed in a fresh virtual environment.
- Whole suite on the final file: **1603 tests OK** (6 skipped: the 5 real-library tests, which run only when `NEMO_WIRE_PY` is set, and the slow update-gate test, which I ran separately with `NEMO_SLOW=1` and passed). `tests/test_forge91.py` (186 tests) is part of it. The first full run found one older regression row (`v167-stt-large-v3-primary`) that read the model name from `groq_transcribe` itself and could not see through the new wrapper; the wrapper now exposes `__wrapped__` and that row looks through it (a test covers it).

## 6. What is verified and what is not

**Verified offline (tests above):** all routing, owner and private-chat checks, memory guard, one-at-a-time, clean environment and low priority, time limits, temporary-folder cleanup, file and text output, masking of secrets and the untrusted label, update-check comparison logic, MCP group stop, and that the layer never touches trading.

**Verified against the real libraries on a test machine:** PDF tables, OCR (English and Hindi through the installed tesseract), article extraction, indicators, quantstats report.

**Not verified live (you are the first real run):**
- **NSE data (`jugaad-data`)**: the NSE site was not reachable from my sandbox, and it changes and blocks automated access from time to time. The command is built and tested with a stubbed result; a real answer depends on the site that day. Always compare with your broker before acting.
- **Local voice (`faster-whisper`)**: its model downloads from a model host that my sandbox cannot reach, so the transcription itself was not run here. Everything around it (when it starts, the memory guard, the notice, the failure messages) is tested.
- **The extra update checks with the real ruff/vulture/detect-secrets on a 5 MB file**: tested with small stand-in tools and, in v91, with the real tools one at a time; the combined run on the full file on your server is untested, which is why it is information-only and time-limited.
- **Telegram display** of the new messages and files, and **`forge apt` on your server**.
- **Your server's memory in practice**: the guard's numbers are conservative but come from my test machine.

## 7. What I deliberately did not build yet

**Local semantic memory ("search my files", sqlite-vec + fastembed).** It needs a separate index, and local embeddings have a different size from Gemini's, so mixing them in the existing memory would corrupt search. It deserves its own version (v96 "Knowledge" in `NEMO_NEXT_POWERS.md`), after you see how Wire behaves on your server.

## 8. Edits to older code (small, listed on purpose)

1. The self-development guard's editable prefixes now include `_n92_`; the older regression row `v167-stt-large-v3-primary` looks through the voice wrapper's `__wrapped__`.
2. `MCPClient.start` starts the server in its own session; `MCPClient.stop` ends the process group (section 3).
3. Wrappers: `groq_transcribe` (local fallback after Groq), `self_update` (extra checks first), `handle` (owner front door), `_n82_capabilities`, `_n83_status_text`, `_n88_abilities` (list the new abilities), `prime_regression_suite` (8 `v92-*` rows), `main` (prunes old job folders and registers the MCP stop at exit). The command list gets `wire`.
