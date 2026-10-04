# What to add to Nemo next: offline and online controls, web knowledge, and a website

You asked what more we can add for more offline and online control, more web knowledge, and a website that serves a more powerful Nemo to the web. This is the researched answer, in the order I would build it.

**How to read the evidence tags:** **[ran]** I ran it for real; **[code]** I read it in `nemotron_bot.py`; **[page]** I read the project's GitHub page (star counts are approximate); **[search]** only web-search snippets (weak: treat as a hint); **[idea]** my design, not yet tested.

## 1. First, what Nemo already has (so I do not suggest it twice)

**He already has a website [code].** A Flask app named `nemo_web` starts with the bot on port 8090: a chat page that installs as a phone app (manifest + service worker), `/api/chat`, a dashboard, a **cockpit** page, file upload, a browser screenshot view, voice endpoints, a TradingView webhook, Twilio phone and WhatsApp webhooks, device enrolment and a health check. `/setdomain` and a Cloudflare quick tunnel give it an `https` address, and the cockpit opens inside Telegram as a **Web App button** when that address is set. The cockpit's actions are an allow-list of read-only ones (status, brain, cyber audit, hands, VPN status, browser status); the code says consequential actions stay Telegram-confirmed.

**What I found weak in that website [code; row 6 is general knowledge about quick tunnels]** (not a verdict, a to-do list):

| # | What the code does | Why it matters |
|---|---|---|
| 1 | The only login is one shared token: 12 hex characters (48 bits), created at start-up, **sent in the address (`?k=…`)** | Addresses end up in browser history and server logs; anyone who sees one has full web access. |
| 2 | The token is compared with `==`, there is **no rate limit** | Guessing attempts are not slowed down; a plain compare leaks timing. |
| 3 | If the token were ever empty the fallback is the word `nemo` | Safe only because a later start-up step always creates one. |
| 4 | It runs on Flask's built-in development server, **bound to every network address (`0.0.0.0:8090`)** | The tunnel is not the only way in: if the port is open to the internet, people can reach it directly, over plain `http`. |
| 5 | When no public address is set, the cockpit link Nemo prints is `http://<your-ip>:8090/cockpit?k=<token>` | The token travels in clear text over the internet. |
| 6 | The quick-tunnel address changes whenever the tunnel restarts | You must re-send `/setdomain`; the phone app breaks. |
| 7 | The Web App button gets the token from the address instead of **checking who Telegram says you are** | Telegram already proves your identity to a Mini App; Nemo does not use it. |

Everything else Nemo has (search, MCP presets, document work, watchers, Circle roles for family, Forge) is not repeated below.

## 1b. Your server (from your own screenshots)

You ran the two commands yourself because Nemo could not answer ("I don't have live memory-or-disk figures"; v91.3 fixes that, he now reads it himself: say `server status`). What they show **[ran by you]**:

| What | Value | What it means |
|---|---|---|
| Memory | 3.8 GB total, 2.2 GB used, **1.6 GB available** | Enough for the bot and one small job at a time, not for several heavy things together. |
| Swap | 2.0 GB, **1.7 GB used (85%)** | **The server is already leaning on swap before any new add-on runs.** Swapping makes everything slow, and an out-of-memory kill of the bot would also stop the trading assistant. |
| Disk | 77 GB, 32 GB used, **45 GB free (42%)** | Plenty. Models, offline Wikipedia files and backups fit easily. |
| CPU | the host name says `1vcpu`, but memory is 3.8 GB, so the plan was probably changed | Unknown until `server status` prints the cores; with 1 core, local speech-to-text and embeddings are slow. |

**Update: your live `server status` (v91.3 running on the server).** The real numbers, read by Nemo himself:

| What | Value | How I read it |
|---|---|---|
| Memory | 3.8 GB total, 1.6 GB used, **2.2 GB available** | Better than the first screenshot (1.6 GB available); not short right now. |
| Swap | 2.0 GB, 1.8 GB used (**89%**) | With 2.2 GB of memory free this is **most likely old, unused data sitting in swap, not an active slowdown**. v91.3 called it a warning anyway; that was too blunt, and v91.4 measures whether the server is swapping *right now* before it warns. |
| CPU | **2 cores**, load 1.37 / 0.81 / 0.57 | About 0.7 per core and rising over the last 15 minutes: something is working. The `1vcpu` in the host name is out of date; the plan was resized. |
| Biggest memory users | Nemo 0.7 GB (37 threads); a `python` process 0.2 GB (unknown); `systemd-journal` 94 MB; `npm exec @model…` 90 MB and `node` 78 MB | The last two are **probably an MCP server started through npx** (Nemo's `filesystem` or `memory` preset), about 170 MB together. v91.4 shows which one, and which tool environment the `python` belongs to. |

**Second reading (v91.4 running), and a finding.** Memory 2.1 GB available, swap 89% but **"not swapping now"** (so it is old unused data, as I guessed), 2 cores at about 0.5 per core, 31.8 GB of disk used. The process list now names things, and it shows two surprises:

1. **`/mcp list` says "No external MCP servers registered", yet `node …/mcp-server-filesystem …//root` (80 MB) and `npm exec @modelcontextprotocol/server-filesystem` (74 MB) are running.** That is a filesystem MCP server pointed at `/root`, about 154 MB, that Nemo says he does not have. A stdio MCP server listens on no network port and only answers the program that started it, so the risk is low, but it is memory you did not know you were spending, and I do not yet know whose it is. (In the code, `MCPClient.stop()` only stops the direct child, and nothing stops MCP servers when Nemo exits; the restart command is `systemctl restart nemobot`.)
2. **Another application shares the server:** `python …/app5/quantumfx_bot.py`, about 0.2 GB. Anything I add has to leave room for it too.

v91.5 answers "whose is it": each big process now shows the **service it belongs to** and **how long it has been running**, e.g. `node 80 MB […] (nemobot.service, up 30 h)`. If MCP servers belong to Nemo's own service but none of his connections owns them, `server status` says so and `stop leftover mcp` gives you a **card** to stop exactly those processes (a polite stop, then a forced one after 5 seconds, each re-checked just before). Processes of any other service, including `quantumfx_bot.py`, are never offered and never touched.

What to do with that (read-only checks first): ask Nemo `/mcp list` to see which MCP servers are connected, and switch off any you do not use (**especially `filesystem`, which lets a model read and write files under `/root`**). Then say `server status` again.

What I conclude (these change the plan):

1. **A local AI brain (B3) is not realistic on this server.** Even a small 3B model needs about 2 GB free and you have 2.2 GB at best, shared with the bot, and the swap is nearly full. I drop it. The cloud fallback chain Nemo already has (several providers) stays the fallback. If you later want local models, the sensible route is a bigger plan or a second small machine, not this one.
2. **Heavy add-ons must be polite.** The v92 "Wire" work will run each heavy library (voice model, embeddings, report builder) in a **short-lived child process, one at a time**, and only when enough memory is free; otherwise Nemo says "low on memory, try later" instead of pushing the bot into swap. Nothing heavy stays loaded inside the bot.
3. **Disk is not the problem,** so the offline encyclopaedia (B4) and local models of the small kind (speech-to-text `tiny`/`base`) are fine from the disk side.
4. **Find out what is eating the memory first.** `server status` now lists the biggest memory users. My guess (not verified) is the bot itself plus a browser started by Playwright; if a browser process is left running, that is the first thing to fix.

## 2. Principles I would keep

1. **Private by default, two doors.** An *owner door* (everything, strongly authenticated) and, only if you want one, a *public door* (read-only, rate-limited, no keys, no trading, no mail, no Forge).
2. **Nothing consequential from a web page.** Keep the rule already in the code: risky actions are a card in Telegram that you tap.
3. **Offline is a mode, not an accident.** Nemo should know when the internet or a provider is down, say so, and switch to local tools.
4. **Every new program arrives through Forge** (approval, pinned files, rollback). Where Forge cannot (a server program, not a Python wheel), the guide says so.

## 3. Ranked additions

Effort: S = a few hours, M = about a day, L = several days. Risk is for your VPS and your money.

### A. The website: stronger and more useful

| Rank | Addition | What you get | Evidence | Effort / risk |
|---|---|---|---|---|
| A1 | **Log in with Telegram, not a token** | The cockpit/chat page proves you are *you* using what Telegram signs and sends to a Mini App (`initData`): no password, no secret in the address, guests can be limited by Circle roles. | **[ran]** I wrote the check (the documented HMAC-SHA256 with the bot token) and tested it: the real owner passes; another user id, a tampered field, an old timestamp and a wrong token all fail. Nemo already opens the cockpit as a Web App button **[code]**. | S–M / low (it only adds a check) |
| A2 | **Serve it properly:** a production server (`waitress`, wheel 0.1 MB), **bind to 127.0.0.1**, keep the token only as a fallback in a header or cookie (HttpOnly), constant-time compare, rate limit (`flask-limiter`, 1.1 MB wheels, or `slowapi`) | Closes weaknesses 1–5 above. | **[ran]** Forge's own PyPI check and a real download of all of these: wheels exist and are small. | S–M / low |
| A3 | **A stable, safe way in.** Choose one: **(a) Tailscale** (private; the site is only reachable from your own devices; nothing public), **(b) a named Cloudflare Tunnel on a domain you own, with Cloudflare Access in front** (email one-time code or Google/GitHub login, even before Nemo sees a request). | (a) simplest and safest for you alone. (b) works from any browser and for family, with a fixed address. | **[page]** `cloudflared` (about 16k stars, Apache-2.0): a named tunnel needs a site on Cloudflare and a DNS change. **[search]** Access supports email allow-lists, SSO and one-time codes. Not installable through Forge (a program, not a wheel). | S–M / low |
| A4 | **A better owner app:** streaming replies as they are written, send files straight into Document Intelligence, the futures desk on a dashboard (journal, stats, expiry calendar), the approval cards visible on the web too. | The "powerful Nemo on the web" you described. | **[idea]** built on the existing Flask routes. | M–L / medium |
| A5 | **A public showroom page** (only if you want one): pages Nemo writes, a guest chat limited to a short list of safe tools, cached, rate-limited, behind Cloudflare, **no access to your keys, mail, files, trading or Forge**. | A business-facing Nemo (the showroom copilot already exists in v85 for you). | **[idea]** | M–L / **highest**: public = attacked; needs its own review |
| A6 | **An OpenAI-compatible endpoint** (`/v1/chat/completions`, owner-only key) so polished chat apps can use Nemo as a backend. | Phone/desktop chat apps and **Open WebUI** work with Nemo without building a UI. | **[page]** Open WebUI (about 154k stars) connects to "Ollama and OpenAI-compatible APIs"; its licence adds a **branding-preservation requirement** (not plain open-source). | M / medium |

**My recommendation for the website:** do **A1 + A2 + A3(a)** first. That makes the existing site safe and tied to your Telegram identity with no public exposure. Add A3(b) when you want family or other devices, A4 when you want more features, and A5/A6 only when you have a clear use.

### B. Offline powers

| Rank | Addition | What you get | Evidence | Effort / risk |
|---|---|---|---|---|
| B1 | **Use what is already installed offline:** local OCR (tesseract), local speech-to-text (faster-whisper), local semantic memory (sqlite-vec + fastembed), local PDF tables (pdfplumber). | Voice notes, pictures, PDFs and "search my files" keep working with no internet or key. | **[ran]** OCR English and Hindi, PDF tables, vector search. The two model-based ones need the models downloaded once. | M / low (this is v92 "Wire") |
| B2 | **An offline mode switch:** Nemo notices the internet or all AI providers are down, says so, queues non-urgent work, and uses only local tools; "go offline" / "go online" by hand. | No silent failures. | **[idea]** Nemo's brain router and health tracking exist **[code]**. | M / low |
| B3 | **A local brain as a last resort:** a small model on the server (`llama.cpp`'s server, MIT, about 130k stars, plain CPU, OpenAI-compatible; or Ollama, MIT, about 182k stars). | Nemo can still answer simple things when every cloud provider fails. | **[page]** both. **[search]** a 7B model at 4-bit needs about 5.5 GB of RAM and gives roughly 5–15 words a second on 8 CPU cores; a 3B model is "comfortable". **[ran]** Forge refuses `llama-cpp-python` (source only), and the `ollama` Python client (3 MB) installs fine, but the **server programs are not wheels**: they need a new Forge lane (below) or a manual install. **On your server (1.6 GB available, swap in use) this is not realistic: dropped.** | M–L / medium |
| B4 | **Offline encyclopaedia:** Kiwix (Wikipedia, Stack Exchange and more as compressed `.zim` files). Nemo reads them with the small `libzim` package, or serves them with `kiwix-serve`. | Facts with no internet. | **[ran]** `kiwix-tools` 3.5.0 exists in Ubuntu 24.04's apt; `libzim` has a 10 MB wheel. **[search]** the full English Wikipedia with pictures is about 100+ GB, smaller no-picture editions are much smaller (check sizes before downloading). | M / low (disk is the cost) |

### C. Web knowledge (online)

| Rank | Addition | What you get | Evidence | Effort / risk |
|---|---|---|---|---|
| C1 | **A research pipeline with sources:** search (ddgs, as now) → read each page cleanly (trafilatura, installed) → store text, link and date in a local knowledge base (sqlite-vec) → answer **with citations and the date of the page**. | Fewer wrong answers, and "what did I read about X last month?" | **[ran]** the pieces; **[idea]** the glue. | M / low |
| C2 | **Your own search engine (SearXNG):** a self-hosted meta-search with a JSON output, so no search company key or quota. | Unlimited searches from your own server. | **[page]** SearXNG: about 38k stars, **AGPL-3.0**, installs by Docker or pip. I did **not** confirm the JSON switch from the page; it is a setting to enable and test. Not a wheel Forge can install. | M / medium |
| C3 | **Pages that need a browser:** Nemo already has Playwright **[code]**; `crawl4ai` (Apache-2.0, about 85k stars) adds LLM-ready crawling but needs browsers and is heavy. | Better reading of script-heavy sites. | **[page]** I would not add it until C1 shows a real gap. | M / medium |
| C4 | **Feeds and structured sources:** RSS (`feedparser`, 0.1 MB), Wikipedia (`wikipedia-api`, 0.8 MB), arXiv (`arxiv`, 5.6 MB), NSE live data (`jugaad-data`, installed), RBI/SEBI/exchange notices. | Reliable, structured facts instead of scraping. | **[ran]** the three small packages install; the exact RBI/SEBI feed addresses I have **not verified**. | S–M / low |
| C5 | **Page watchers with a diff:** "tell me when this page changes" with what changed and a short summary. | Alerts on notices, circulars, prices. | **[code]** watchers exist (v85); **[idea]** the page diff. | S / low |

### D. Controls and operations

| Rank | Addition | What you get | Evidence | Effort / risk |
|---|---|---|---|---|
| D1 | **GitHub → Nemo webhook:** when you push a new version, Nemo gets a signed message and shows "new version available: check and apply?" (through the existing update gate). | One-tap upgrades from your phone after a push. | **[idea]** GitHub signs webhooks with HMAC-SHA256; the TradingView webhook shows the pattern **[code]**. | S–M / low |
| D2 | **Server health cards:** disk, memory, bot alive, tunnel alive, certificate/token ages, with a Telegram alert when something is wrong. | You hear about problems first. | **[code]** `see` already reads the server; **[page]** Uptime Kuma (MIT, about 92k stars, Telegram alerts) is the off-the-shelf alternative, but needs Node or Docker. | S–M / low |
| D3 | **Safe firewall and intrusion help:** put `ufw` and `fail2ban` on Forge's apt allow-list (each install is still a card). | Fewer attacks on port 22/8090. | **[idea]** | S / medium (a wrong firewall rule can lock you out) |
| D4 | **Workflows without code (n8n):** optional. | Connect many services. | **[page]** about 207k stars, but a **fair-code "Sustainable Use" licence, not open source**, and it runs in Docker. I would not add it unless a specific workflow needs it. | M / medium |

### E. A Forge "apps lane" (the missing piece for B3, B4, C2, A3)
Forge installs only Python wheels. The best offline and web tools (llama.cpp, kiwix-serve, cloudflared, SearXNG) are **programs or containers**. A safe lane would: download only from named GitHub release pages, check a SHA-256 you approve on the card, unpack into a private folder, run **as a normal user with limits**, never `curl | sh` (the exact pattern Forge's scanner flags), and offer `remove`. **[idea]**, effort L, and I would build it last.

## 4. The order I recommend

| Version | Name | What it delivers | Why this order |
|---|---|---|---|
| **v92** | **Wire** | Everything you installed becomes a chat command (`NEMO_PICKS_HOWTO.md` section 3): update-gate checks, PDF tables, OCR, clean article reading, indicators, NSE data, journal tear-sheets, local voice fallback, local semantic memory | You already paid the install cost; nothing else is blocked on it |
| **v93** | **Doors** | Website hardening (A1 Telegram login, A2 server, rate limits, cockpit audit); guide for A3(a) Tailscale | Fixes the real weaknesses before adding anything public |
| **v94** | **Offline** | B2 offline mode, B1 fully local tools, B4 offline encyclopaedia; B3 local brain only after the server has more memory | Needs v92 |
| **v95** | **Knowledge** | C1 cited research pipeline, C4 feeds, C5 page diffs | Needs v92 (trafilatura, sqlite-vec) |
| **v96** | **Site** | A4 richer owner app, optional A5 public showroom and A6 OpenAI-compatible API, D1 GitHub webhook | Only after the doors are safe |
| **v97** | **Apps lane** | E, then C2 SearXNG and any local brain | Biggest and riskiest |

## 5. Four answers I need from you (they change the plan)

1. ~~How much memory and disk does the server have?~~ **Answered by your screenshots** (section 1b). New question: how many CPU cores? (`server status` will show it.)
2. **Do you own a domain name?** Needed for a stable Cloudflare address (A3b); not needed for Tailscale (A3a).
3. **Who else should use the website?** Only you, family (Circle roles), or the public/customers?
4. **Should Nemo ever act from the web page,** or only show and answer (my recommendation: only show and answer, with actions staying as Telegram cards)?

## 6. What I did not verify

* **What is using your memory** (the swap at 85%). I only know the totals from your screenshot.

* **Your server:** its memory, CPU, disk, Python version, firewall, and whether it can reach `huggingface.co`, `nseindia.com`, `files.pythonhosted.org`.
* **Local-model speed and quality** on your hardware, **Kiwix sizes**, and **Cloudflare Access's free limits**: web-search hints only.
* **SearXNG's JSON mode**, **RBI/SEBI feed addresses**, and any **n8n** or **Open WebUI** behaviour beyond their GitHub pages.
* **How `web_ai` (the website's chat brain) is restricted:** I did not audit which tools a web chat message can reach. That belongs in v93 before anything else is exposed.
* No live trade was placed and no paid API was called.
