# Nemo: what it can do today, and every development, ability and feature still on the list

One page that gathers everything: what exists (v83 to v101), everything planned or proposed, what is parked, what I would not build, a recommended build order, and what still needs a live check. The longer reasoning, evidence and sources stay in the research pages named in each section; this page is the list.

Sizes: **S** = hours, **M** = a day or two, **L** = several days. **Risk** is to your money, privacy or server. **★** = I would build it first. Status of every item in sections 2 to 6 is **not built** unless it is marked BUILT or PART BUILT (v102 Hearth built O4; v103 Mind built M1, M2, F1 and parts of M3 and M5; v104 Autopilot built T1, R1, R2, R4, R6 and parts of T7, R5, C6, X5; v105 Web Hands built T2 and parts of T6, R3, C4; v106 Steady was a fix release: light, talkative updates with a safety net, and honest health checks, see `NEMO_V106_STEADY.md`; v107 Reach built K1 (dated sources added to v85's research), K2, K3, K4, K6 and part of K7; v107.1 Pine was a fix release: Pine Script requests go straight to the Pine engine, and "with your survival logic" builds Nemo's own Survival Strategy, see `NEMO_V107_1_PINE.md`; v108 Voice built V1, V2, V7, X1, X2 and most of V6, see `NEMO_V108_VOICE.md`).

---

## 1. What Nemo can do today (v83 to v108, all built, tested offline, pushed)

| Area | What it does | Layer |
|---|---|---|
| **Understanding and memory** | Chats in English and Hindi/Hinglish; follow-ups and replied-to text; remembers facts and preferences; "forget about X" works everywhere including queued jobs; checks its own dates and arithmetic; says why it answered (`/why83`) | Cortex 83, Candor 86 |
| **Speed** | Instant answers for simple questions, router bypass, tools run in parallel, typing indicator kept alive | Atlas 84 |
| **Plain words** | Market replies and data dumps rewritten so a person can read them (for example the NIFTY option chain) | Clear 94 |
| **Research** | Verified research that checks its own quotes; shared time and cost limit; page watchers; news fetchers; Scholar: you say what Nemo is weak at, he searches GitHub/PyPI/MCP, compares, recommends one, and puts a one-tap install card in front of you | Steward 85, Candor 86, Scout 93, Scholar 98 |
| **Documents and office** | Reads PDFs, tables, pictures (OCR); precise reports and PDFs from your files; GSTIN/PAN checks; amount in words; fuzzy name matching; invoice drafts; study and quiz helper; showroom copilot (leads, dues) | Steward 85, Studio 90, Wire 92, Office 95 |
| **Pictures** | Nine image engines, posters, charts, real AI enlarging, background removal, nine world-market pictures | Studio 90, Studio+ 94, Globe 101 |
| **Voice** | Voice notes in (cloud speech-to-text with a local fallback), voice replies out, talk mode | earlier layers |
| **Your accounts** | Read-only eyes on mail, calendar, Drive, tasks, activity and the server, with honest "I can't see that" messages | Argus 88 |
| **Downloads** | Multi-source download chain, save to Drive, share link; allowed family members can download too | Relay 87, Globe 101 fix |
| **Family** | Default-deny ability menu per person or role (Circle); view-only trade desk for family; `family everything` / `family everyday only` / `family world on|off` | Circle 89, Desk 97, Globe 101 |
| **Installs and updates** | GitHub access, safe program installs with approval, inspection, isolated environments and rollback; update gate with extra checks; installed libraries become chat commands | Forge 91, Wire 92 |
| **Server care** | Reads memory, swap, disk, CPU and the biggest processes with the service that owns them; tells stale swap from real pressure; card to stop leftover MCP servers; housekeeping and doctor reports | v91.3 to v91.5, Care 95 |
| **Website and phone app** | Installable chat page, cockpit, dashboard; log in with Telegram, key-guess rate limit, constant-time checks, safe headers, optional local-only binding | Doors 95 |
| **Trading: futures** | Calendar, basis, roll, sizing, check, edge, journal and stats, alerts | Atlas 84 |
| **Trading: ideas and signals** | Scout trade ideas from news and market tools; Sigma fixed-rule signals for stocks and NIFTY/BANKNIFTY with option-chain analytics, defined-risk structures, backtest with a control and a forward scoreboard | Scout 93, Sigma 100 |
| **Trading: records** | Ledger of every trade the practice agent made (results before and after charges, worst dip, one trade in full, CSV); Lab: price paths, replay of 12 rules, "why not" log, weekly/monthly reports, losing-streak alerts, readiness checklist | Ledger 96, Lab 99 |
| **World knowledge** | 17 exchanges with hours, sessions and holidays; world calendar (Fed dates, your events; Sigma will not sell premium into them); live world board and heat-map; overnight cues for India with an out-of-sample check; country cards; glossary; nine detailed pictures | Globe 101 |
| **Safety backbone** | Owner lock, approval cards for anything consequential, trading-holiday guards, backups and rollback, no secrets in logs | throughout |
| **Autopilot** | One list of everything that runs by itself (12 built-in jobs, `/every` and `/at` actions, the `/work` queue, new routines) with pause, resume, run now, receipts, "why did you do that" and Undo; routines in plain words from five safe kinds (saved question, dues and follow-ups with draft messages, mail triage, invoice drafts, repeated reminder); new routines start as practice and earn trust after five clean runs; the rule of two; read-only plans of up to eight steps that run only after your Go; "stop everything" (the trading agent is deliberately not touched) | Autopilot 104 |
| **Web Hands** | Jobs on websites you name with a headless browser the page cannot steer (the model that picks the clicks never sees the page text; a separate reader with no tools reads it); types only your words, never into password/OTP fields, never uploads, answers no to every dialog, opens only the run's sites, stops before Submit/Pay/Send and asks; price comparison across Amazon, Flipkart, Croma, Reliance Digital; forms filled up to Submit; playbooks that replay a job and run as routines (also monthly); your own login from a cookies.txt file; a screenshot for every step | Web Hands 105 |
| **Steady** | `/update` answers at once and keeps one status message up to date; the compile check and trial start run in separate low-priority processes the kernel stops first (never inside the bot); "could not check" is never "failed"; a watcher outside Nemo's service puts the previous version back if an update keeps crashing at start; honest voice, Gemini and Gmail checks with plain-words alerts; `/steady`, `gmail status` | Steady 106 |
| **Reach** | Backup search engines behind every web search (one that refuses rests); dated sources in quote-checked research; SEBI/RBI/NSE/PIB and your own feeds; topic watches that tell only new stories; the whole of a long video or podcast read in parts with timestamps and 5 claims to check; fact-checks whose verdicts need a quote found on the page; `my research` | Reach 107 |
| **Self-development** | Nemo can build and test changes to himself, with your approval | Candor 86, Scholar 98 |

**Limits today:** no typing, clicking or dictation on your own laptop or phone; no meaning-based memory; no streaming replies; mail and calendar are read-only; one Telegram door (the website and WhatsApp doors are weaker and two have a gap, see 3); Gujarati is weak; mood is read only from explicit words.

---

## 2. Features still to build (87 features and 2 fixes, grouped)

Reasons, evidence and sources for each: `NEMO_ADVANCED_AI_FEATURES.md` (A to H groups), `NEMO_OUT_OF_TELEGRAM.md` (doors), `NEMO_NEXT_POWERS.md` (site, offline, knowledge).

### MIND: understand you better

| ID | Feature | You get | Size / risk |
|---|---|---|---|
| M1 ★ | **BUILT in v103.0 Mind** (see `NEMO_V103_MIND.md`): Meaning-based memory with time | "What did I decide about the lease?" works without the exact words; a changed fact replaces the old one but keeps its date | M / low |
| M2 ★ | **BUILT in v103.0 Mind**: "What I know about you" card | One screen of everything Nemo believes about you; edit or delete a line by a sentence | S / low |
| M3 ★ | **PART BUILT in v103.0 Mind** ("who do you mean?" for people only; the two-line plan with Go/Change for other ambiguous requests is not built): Ask before guessing | One short question (or a two-line plan with Go/Change) when a request is ambiguous and the action matters | S / low |
| M4 | Context fusion | Answers use your calendar, tasks and mail when relevant, naming the source | M / low |
| M5 ★ | **PART BUILT in v103.0 Mind** (memory reads, stores and finds Hindi/Gujarati script and Hinglish; the answer model is told to reply in the language you wrote; voice and live quality unverified): Hindi / Gujarati / English end to end | Detects and answers in the same language and script; exact names and numbers | M / low |
| M6 | Multimodal | Short videos, app screenshots, receipts, long PDFs with tables | M / low-medium |
| M7 | Reference resolution | "That one", "same as last time", "send it to him" resolved, and Nemo says to what | S / low |
| M8 | Learning from corrections | Your correction becomes a visible rule that is applied and tested | M / low |
| M9 | A profile per family member | Language, reading level, interests, off-limit topics, child mode | M / low |

### VOICE: communicate

| ID | Feature | You get | Size / risk |
|---|---|---|---|
| V1 ★ | **BUILT in v108.0 Voice** (live drafts with a stop button; Anthropic and OpenRouter answers): Streaming replies | Text appears as it is written; stop a wrong answer early | S-M / low |
| V2 ★ | **BUILT in v108.0 Voice** (voice notes go through the whole of Nemo; voice-note replies in English, Hindi, Gujarati; family too): Voice-note conversation | A real voice-note bubble back, in your language, with speed and tone; text twin on request | M / low |
| V3 | Phone calls on your behalf | "Call the plumber and ask the price"; says it is an AI, your approval first, no payments or OTPs | L / **high** |
| V4 | Draft replies, send after your tap | Mail and WhatsApp drafts; "triage my inbox" | M / medium |
| V5 | Interpreter mode | Live Hindi / Gujarati / English, text and voice | M / low |
| V6 | **PART BUILT in v108.0 Voice** (polls, quiz polls, round video notes, buttons on voice notes; only-you messages in groups not built): Richer Telegram messages | Polls, buttons, only-you messages in groups, video notes | S / low |
| V7 ★ | **BUILT in v108.0 Voice** (quiet hours, snooze, daily digest; urgent and replies never held; off until turned on): Notification manners | Quiet hours, urgent vs digest, one daily digest, "snooze Nemo 2 hours" | S / low |

### EXPRESSION

| ID | Feature | You get | Size / risk |
|---|---|---|---|
| X1 | **BUILT in v108.0 Voice** (per person and situation, given to the answer model and the family chat): Tone dials | "Shorter", "more formal with customers", remembered per person and situation | S / low |
| X2 | **BUILT in v108.0 Voice** (calm/warm/excited/serious delivery; reactions instead of "you are welcome"): Expressive voice and reactions | Warm/calm/excited voice by situation; emoji or sticker where a person would | S-M / low |
| X3 | Explain with a picture | Diagram, timeline or comparison table when it helps | S / low |
| X4 | Teaching and story modes | Study mode, bedtime stories, "explain like I am new" | S / low |
| X5 | **PART BUILT in v104.0 Autopilot** (for what Autopilot, the built-in jobs and scheduled actions send; chat answers keep their own "how did you get that answer"): "Why did you do that?" for actions | One-line reason and a receipt for every action | S / low |

### HEART: notice how you feel, never pretend to feel

| ID | Feature | You get | Size / risk |
|---|---|---|---|
| H1 ★ | Mood and stress read, with your consent | "You sound stressed, want a short answer?" from text only, switchable | S-M / medium |
| H2 ★ | Empathic reply policy | Acknowledge first, no lectures, no medical/legal claims, calm helplines if you mention self-harm | S / low |
| H3 ★ | Anti-flattery guard | Disagrees when it should, admits doubt, never claims feelings or "missed you", points you to people; tested | S-M / low |
| H4 ★ | Trading-tilt guard | After a losing streak or rapid-fire decisions: "three stops today, breaker is on, stop for today?" | S / low |
| H5 | Wellbeing nudges (opt-in) | Water, a break, a late-night "sleep?" once | S / low |
| H6 | Remembering the people side | Birthdays, a relative's exam day, "call mom Sunday", gift ideas | M / low |

### CONNECT

| ID | Feature | You get | Size / risk |
|---|---|---|---|
| C1 ★ | Write actions behind an approval card | Draft and send mail, create calendar events, add tasks, upload files, only on your tap, logged | M / medium |
| C2 | More MCP tools by tier | Calendar, notes, maps, shopping lists; each read-only first | S per tool / medium. Many servers need a tool finder first: see `NEMO_STRATA_ANALYSIS.md` (native BM25 finder recommended; the Strata package is not) |
| C3 | Smart home | "Turn off the showroom lights" through Home Assistant; confirm locks and heaters | M / medium |
| C4 | **PART BUILT** (v104 dues digest and invoice drafts; v105 downloads your bills from sites you log in to and compares shop prices): Money, read-only | Bill and due-date reminders, invoice drafts, UPI link you tap yourself; **never** auto-payments, cards or OTPs | S / low |
| C5 | People and business graph | Customer, vendor, relative with notes and last contact; "who owes me?", "who have I not called?" | M / low |
| C6 | **PART BUILT in v104.0 Autopilot** ("routine every weekday at 9:30 dues" covers late payments; free-form triggers such as "7 days late" are not built): Plain-words automations | "When a payment is 7 days late, remind me and draft a message" (shares the engine of T1) | M / low-medium |

### KNOWLEDGE: web search and facts

| ID | Feature | You get | Size / risk |
|---|---|---|---|
| K1 ★ | **BUILT** (v85 quote-checked research; v107 adds each source's date and backup search engines): Research that plans, reads, cross-checks, cites | A plan, several searches, whole pages read, claims tied to dated sources, contradictions and "could not confirm" listed | M / low |
| K2 | **BUILT in v107.0 Reach** (backup engines behind every search; SearXNG supported when you run it; Brave with a key): Your own search engine | SearXNG meta-search, no quota; more sources (news, Wikipedia, Reddit, transcripts, RBI/SEBI/NSE notices) | M / medium |
| K3 | **BUILT in v107.0 Reach** (topic routines that tell only new stories; page differences were already in v85): "Watch this topic" with diffs | Daily check; tells you only what changed; page-change watchers show the difference | M / low |
| K4 | **BUILT in v107.0 Reach** (whole transcript in parts, timestamps, 5 claims to check; podcasts and files in ten-minute parts): Long video and audio reading | A lecture or interview summarised with timestamps and five claims worth checking | M / low |
| K5 | Live facts as tools | Weather, maps and hours, trains and flights, currency, scores | S per tool / low |
| K6 | **BUILT in v107.0 Reach** (verdicts need a quote found on the page; warning signs; optional fact-checker ratings): Fact-check mode | Paste a forward, get what is verifiable, what is not, and sources | S / low |
| K7 | **PART BUILT in v107.0 Reach** (RSS/Atom feeds: SEBI, RBI, NSE, PIB and yours, as routines; a store of reports; arXiv and Wikipedia were already in OmniSource; NSE data files not built): Feeds and structured sources | RSS, Wikipedia, arXiv, NSE data; cited research store | S-M / low |

### HANDS: doing things, including typing

| ID | Feature | You get | Size / risk |
|---|---|---|---|
| T1 ★ | **BUILT in v104.0 Autopilot** (see `NEMO_V104_AUTOPILOT.md`; to change a routine, say it again and delete the old one): Routines in plain words, with a log | List, pause, run now, edit and see each run's history in one place | M / low |
| T2 ★ | **BUILT in v105.0 Web Hands** (see `NEMO_V105_WEB_HANDS.md`; a second engine beside the old one, which stays the default unless you switch): Stronger browser agent on the server | Saved playbooks per site, allow-list, screenshots as receipts, resume after failure, repeat-test | M / medium |
| T3 ★ | **Nemo Hands on your Windows laptop** | Types text, presses keys, opens apps, clicks named controls, fills forms, screenshot receipts. Safety: Go/Stop card, on-screen banner, stop hotkey, app allow-list, never passwords/OTPs, time limit. Four stages: dictation, type-into-this-box, open/click named controls, multi-step plans | L / medium-high |
| T4 ★ | Dictation anywhere | Hold a hotkey, speak Hindi/Gujarati/English, Nemo types the cleaned-up text into the active field | M / low |
| T5 | Typing on your phone (Android only) | "Send this on WhatsApp", with confirmation and manual takeover for logins | L / medium-high |
| T6 | **PART BUILT in v105.0 Web Hands** (web forms: your values only, stop before Submit with a screenshot and a tap; documents and saved profiles not built): Form and document filling | GST invoices, quotations, forms from your saved profile, preview first | M / medium |
| T7 | **PART BUILT in v104.0 Autopilot** (read-only plans of up to eight steps, shown first, run only after your Go, stop on any surprise, ten-minute limit; no retries or write steps): Plans that actually run | An up-to-eight-step project with tools, retries, rollback point and stop-on-surprise | L / medium |
| T8 | PC tidy-ups with a dry run | Organise Downloads, rename scans, back up a folder: list first, tap, undoable | M / medium |

### RULES: trust and safety that make the rest usable

| ID | Feature | You get | Size / risk |
|---|---|---|---|
| R1 ★ | **BUILT in v104.0 Autopilot**: The rule of two | A run may combine at most two of: untrusted content, private data, acting outward; a third needs your tap | S / low |
| R2 ★ | **BUILT in v104.0 Autopilot** (an Undo exists where a routine writes: invoice drafts): Receipts and undo | Every action: what, why, when, before/after, and an Undo where one exists | M / low |
| R3 | **PART BUILT in v105.0 Web Hands** (for web jobs: the step planner never sees page text and the reader has no tools; mail and documents still go through the older path): Injection filter | Text from pages, mail and documents is data; instructions inside it are listed and ignored | M / low |
| R4 ★ | **BUILT in v104.0 Autopilot** (as five clean practice runs in a row plus your tap, not as scripted dry runs): Repeat-test before trust | Each automation passes five dry runs before it is called reliable | M / low |
| R5 | **PART BUILT in v104.0 Autopilot** (AI routines wait for provider headroom and 400 MB free memory, one routine at a time; no cost limit per task): Budgets and manners | Cost and time limit per task; heavy jobs one at a time when memory is free | S / low |
| R6 ★ | **BUILT in v104.0 Autopilot** (routines, plans, approvals, built-in jobs and the `/work` queue; the trading agent is deliberately not touched and `/panic` stays separate; laptop control and calls do not exist yet): Panic word | "Nemo stop everything" halts routines, laptop control, calls and pending sends and says what stopped | S / low |
| R7 | Privacy walls and retention | Separate memory per family member, expiring old chats, export and delete | M / low |

### DOORS: Nemo outside Telegram

| ID | Feature | You get | Size / risk |
|---|---|---|---|
| D0 ★ | Foundation: pairing, one turn function, outbox | Every door signs in a real person (you or a family member) and runs the *real* Nemo as that person, with Circle, limits and approvals identical everywhere; one conversation across devices | L / medium |
| D1 ★ | **Nemo app** (installable) | Streaming, voice notes, pictures, charts, approval buttons, family accounts, push; no app store | M / low-medium |
| D2 | Siri / Action Button shortcut | "Hey Siri, ask Nemo" | S / low-medium |
| D3 | Phone-call line | Call from any phone, even a basic one (good for elders), caller allow-list | M / medium |
| D4 | Windows desktop app | Tray icon, chat window, push-to-talk hotkey (carries T3/T4) | M-L / medium |
| D5 | Android widget or assistant | Home-screen widget now; a real default-assistant app later | L / medium |
| D6 | Browser side panel | Chat beside any page, "summarise this" | M / low-medium |
| D7 | OpenAI-compatible address | Other chat apps (Open WebUI and similar) use Nemo as a backend | S-M / medium |
| D8 | Nemo as an MCP server | Claude Desktop and similar call Nemo's tools, read-only first | M / medium |
| D9 | Email-in | Mail a question from an approved sender and get an answer | S / medium |
| D10 | Home voice speaker | Home Assistant voice satellite at home or the showroom | L / medium |
| D11 | Showroom WhatsApp for customers | Official WhatsApp Business API: prices, stock, hours, order status. (A general assistant on WhatsApp is barred; a business-support bot is allowed) | M / medium |
| D12 | Other messengers | Signal, Matrix, Discord, only if you want a private channel | M / low-medium |

### SITE and OPERATIONS

| ID | Feature | You get | Size / risk |
|---|---|---|---|
| S1 ★ | Stable, safe address | Tailscale (private, simplest) or a named Cloudflare Tunnel with Access (fixed address for family); fixes the changing quick-tunnel address | S-M / low |
| S2 | GitHub webhook | A signed message when you push; "new version available: apply?" through the update gate | S-M / low |
| S3 | Server health cards | Disk, memory, bot, tunnel, token ages, with a Telegram alert when something is wrong | S-M / low |
| S4 | Firewall and intrusion help | `ufw`/`fail2ban` as card-approved installs | S / medium (a wrong rule can lock you out) |
| S5 | Apps lane in Forge | Safe install of programs (not just Python wheels): named release pages, checked hash, private folder, limited user, remove | L / medium; build last |

### OFFLINE and LOCAL BRAIN

| ID | Feature | You get | Size / risk |
|---|---|---|---|
| O1 | Offline mode (written, parked as "Offline") | Notices when the internet or all AI providers are down, says so, queues non-urgent work, uses local tools; `go offline` / `go online` | M / low |
| O2 | Fully local tools | OCR, speech-to-text, PDF tables, meaning-based memory with no internet | M / low |
| O3 | Offline encyclopaedia | Wikipedia and more from compressed files (Kiwix); disk is the cost | M / low |
| O4 | **Local brain on your laptop** (BUILT in v102.0 Hearth, see `NEMO_V102_HEARTH.md` and `NEMO_LOCAL_BRAIN_GUIDE.md`) | A relay (the computer only makes outgoing calls, nothing to open on the router) or a direct address; the cloud brains first and the local brain when they fail; `private: ...` answered on your own computer only; `go offline` / `go online`; optional simple-questions-first; `test local brain`. Tested offline; not yet run on your hardware | done |

### TRADING follow-ups (each only if the data or you ask)

| ID | Feature | You get | Size / risk |
|---|---|---|---|
| P1 | Lab: guard against overlapping checks | Skip a check while the last is running, if `lab status` shows overlaps (two checks could both buy) | S / low |
| P2 | Lab: second virtual agent | Fixed-rules brain beside the AI brain, to see if the AI adds anything | M / low |
| P3 | Lab: refusal in live when the readiness checklist fails | Changes the live path, so only on request | S / medium |
| P4 | Lab: adopt a proven rule, in shadow first | Only after the evidence says so | M / medium |
| P5 | Sigma: family view of open signals | Through Desk, no sizing | S / low |
| P6 | Sigma: "what can I trade with ₹X" | Smallest defined-risk structures on today's chain | M / low |
| P7 | Sigma: FII/DII participant open interest | When the NSE file can be read on your server | M / low |
| P8 | Sigma: results-date and RBI-date gates | From Scout's intel jobs | S-M / low |
| P9 | Globe: scheduled morning world brief (new proposal) | A daily world snapshot and calendar to you at a time you pick | S / low |
| P10 | Globe: strong-cue alert (new proposal) | A message only when the overnight cue is strong *and* passes the out-of-sample check | S / low |

### FIXES owed to what already exists

| ID | Fix | Why |
|---|---|---|
| F1 ★ | **BUILT in v103.0 Mind** (default deny; allow your own number with `allow whatsapp +91...`): WhatsApp and phone-call hooks must check who is calling | Today anyone who can message the number gets the plain chat running on **your** memory |
| F2 ★ | Website chat must run as the signed-in person, not as the owner | Same reason; website login also should not depend on Telegram alone |

**Count:** M 9, V 7, X 5, H 6, C 6, K 7, T 8, R 7, D 13, S 5, O 4, P 10 = 87 features, plus the 2 fixes F1 and F2 = 89 rows; 26 are marked ★.

---

## 3. Parked, dropped and "not building"

| Item | Status | Why |
|---|---|---|
| **Offline** (O1 to O3) | Written, parked (O4 is built) | Valid and independent; fits between Voice and Routines |
| A local AI brain **on the VPS** | Dropped for now | The server has about 3.8 GB memory, 2 cores and swap nearly full; the laptop is the place for it (O4, built) |
| Money moved by Nemo (payments, transfers, orders) | Not building | One wrong action costs too much; Nemo suggests, you tap in your own app |
| Unattended sending of mail, WhatsApp or calls | Not building | Every outward message goes through your tap until a routine has passed R4 for weeks |
| Voice cloning of family or customers | Not building | Needs clear consent; not worth the risk |
| Claiming feelings or "missing you" | Not building | Not true, and the research says it is not good for people |
| Unscanned community "skills" and plug-ins | Not building | The OpenClaw lesson: Forge's approval, pinning and rollback stay the only way in |
| A public Nemo with access to your tools | Not building | A separate public product would be its own service (see `NEMO_PUBLIC_LAUNCH_PLAN.md`); you set that phase aside |
| WhatsApp through unofficial libraries | Not recommended | Risks losing the number; breaks without warning |

---

## 4. Recommended build order (v102 Hearth, v103 Mind, v104 Autopilot and v105 Web Hands are built; v106 went to Steady, a fix release, so the numbers below moved up by one; v107 Reach and v108 Voice are built and the next one is v109)

| Step | Name | Contents | Why here |
|---|---|---|---|
| 1 | **v103 Mind (BUILT)** | M1, M2, M3 (people), M5 (memory side), F1 built; M7 ("that one", "same as last time"), the rest of M3, and F2 not built | Everything else works better when Nemo understands you; the phone door is closed; low risk |
| 2 | **v104 Autopilot (BUILT)** | T1, R1, R2, R4, R6, X5 built; T7, R5, C6 in part | The base that makes any automation trustworthy: see it, pause it, undo it, stop it, let it earn trust |
| 3 | **v105 Web Hands (BUILT)** | T2 built; T6 (web forms) and R3 (for web jobs) in part | Nemo works on websites, with a browser the page cannot steer |
| 3a | **v106 Steady (BUILT, fix release)** | No list items: `/update` that answers at once and checks in separate processes, a safety net outside Nemo's service, honest voice/Gemini/Gmail checks, a Nemo file no longer sent with every question | Your update went silent on a small server; it had to come first |
| 3b | **v107 Reach (BUILT)** | K1 (dates), K2, K3, K4, K6 built; K7 in part | The second web step |
| 3c | **Laptop hands** | T4 dictation, then T3 on your Windows laptop in four stages (through the Hearth relay) | The typing and clicking on your own computer; every action through your tap and the stop word |
| 4 | **v108 Voice (BUILT)** | V1, V2, V7, X1, X2 built; V6 in part | Nemo feels alive and the family can use it by voice |
| 5 | **v109 App** | D0 foundation, D1 Nemo app, D2 Siri shortcut, S1 stable address | The "out of Telegram" step; needs the streaming and voice pieces from step 4 |
| 6 | **v110 Heart** | H1 to H4 | Small, valuable; H4 protects money (R6 is already built) |
| 7 | **Reach, the rest** | V4, C2, C5 | Breadth: connections, drafts |
| Any time | **Offline** | O1 to O3 | Independent |
| Later / only if wanted | T5, V3, T7 (the rest), M6, D3 to D12, S2 to S5, C3 | Higher risk, lower reliability or needs hardware |
| On request only | P1 to P10 | Each waits for evidence or your decision |

You can reorder freely; each step stands alone.

---

## 5. Still to confirm on your server (everything is tested offline only)

My sandbox cannot reach Yahoo, NSE, your broker or Telegram, so these have not run live:

1. `family everything`, then ask a family member to send `download tum hi ho song`: confirms the family download fix (it needs `yt-dlp` on the server, as for you).
2. `globe help`, `world markets`, `globe map`: the first real read of the world feed; tell me which symbols it names as "not read".
3. `market hours`, `is Tokyo open`, `world calendar`.
4. `global cues`: read the verdict line first. If it says "nothing usable", believe it.
5. `sigma chart NIFTY`, and the chart under the next Sigma card; `sigma equity` once something has settled.
6. `globe event add 2026-12-05 RBI policy decision`, then see Sigma refuse to sell premium that day.

Not confirmed at all: Telegram's streaming and Business-mode features (their changelog could not be opened), Gujarati speech quality of any model, and the speed or memory of any local model on your 2-core server.

---

## 6. What I need from you to start (defaults in brackets)

1. **Which step first?** [step 1, v103 Mind]
2. **Which computer may Nemo control later?** [the enrolled Windows laptop only; no phone control yet]
3. **Which languages do family members use?** [English, Hindi, Gujarati, mixed]
4. **Mood read (H1):** [off by default, on for you only if you say so]
5. **Send mail or messages after your tap?** [not yet; drafts only until step 5]
