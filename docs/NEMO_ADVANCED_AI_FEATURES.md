# What Nemo can add to understand, connect, communicate, express, "feel", search and act on its own (including typing for you)

You asked me to research deeply and list the features that would move Nemo toward what an advanced AI assistant does in 2026: understand you better, connect to things, communicate, express itself, "feel", search the web, and carry out tasks by itself, including typing. This page is that list, written after reading Nemo's own code and searching the web. It is a research page: **nothing in it is built yet.**

**How I read "typing automatically doing tasks".** Nemo acts for you by typing, clicking and filling things in: on websites (from the server), in apps on your Windows laptop, and possibly on your phone, plus dictation ("say it, Nemo types it where your cursor is"). If you meant something else, tell me.

**How I read "feel".** An AI does not feel, and I will not build Nemo to claim it does. What it can do honestly is (1) notice how *you* seem to feel, (2) answer in a way that fits, (3) keep a steady personality, and (4) refuse to flatter you or replace the people in your life. The "Heart" group below is that.

Evidence tags: **[code]** I read it in `nemotron_bot.py` this session; **[web]** a web-search result (press, blog, vendor or paper abstract: weak, treat numbers as "reported"; links at the end); **[mine]** my judgement; **[gap]** I looked and could not confirm it.

---

## 1. What the research says about the whole idea (read this before the list)

1. **Agents are good at short tasks and unreliable at long ones.** On the newer, longer OSWorld 2.0 benchmark (108 desktop workflows that take a person about 1.6 hours), the authors report the strongest setting reaches only about **20.6% strict task success** (54.8% partial credit); many failed runs loop or fail to find the right button **[web]**. The older τ-bench found that an agent that solved 61% of customer-service tasks once solved only about **25% of them eight times in a row** (pass^8; older model, 2024 paper) **[web]**. **What this means for Nemo [mine]:** every automation should be a short chain of small verified steps, with a receipt after each, a tap-to-approve before anything that changes the world, and a repeat-test before it is trusted.
2. **The danger is not the model, it is the combination.** An agent that can read private data, read untrusted content (web pages, emails, messages) *and* act outward can be tricked by a sentence hidden in a page: the "lethal trifecta" **[web]**. The popular open-source personal agent OpenClaw (messaging-app assistant that runs commands and controls browsers) drew a long list of advisories: prompt injection, plaintext keys, malicious community "skills", exposed instances; vendors advise a sandbox and narrow permissions **[web]**. **For Nemo [mine]:** keep your rule (nothing consequential without your tap), never let one run hold all three, and never install community skills unscanned. Nemo's owner lock, approvals and Forge are already the right shape.
3. **Proactive is now table stakes, and the lesson was "make it steerable".** ChatGPT's Pulse morning briefs were retired in June 2026 in favour of Scheduled Tasks, because proactive help worked best when it was personalised, action-oriented and steerable; Gemini has had Scheduled Actions since 2025 **[web]**. Nemo already has reminders, watchers and briefs **[code]**; the gap is one natural-language place to see and steer them all.
4. **Deep research is now common; trust in the citations is the product.** All the big assistants ship a research mode; one directory says they still invent citations 5-10% of the time (a rough, unsourced figure) **[web]**. Nemo's "verified research that checks its own quotes" (Steward 85) **[code]** is already the right idea.
5. **Emotional AI is risky when it flatters.** A sycophantic model update had to be rolled back; research on companion bots lists sycophancy, "companionship reinforcement", retention-driven engagement and isolating the user as behaviours to avoid; a 2026 experiment found low-sycophancy companions gave *better* support **[web]**. **For Nemo [mine]:** honest, kind, willing to disagree, and it nudges you toward people.
6. **The server is small.** Nemo's VPS has about 3.8 GB of memory, 2 cores, and little spare room **[code: the earlier `server status` reports]**. Heavy local models do not fit; the useful local models are small. **A good idea [mine]: use your Windows laptop as the workshop** (it is already enrolled as a device). Heavy local jobs (speech recognition, a voice, a vision model) can run there when it is awake, and the VPS stays light.

---

## 2. What Nemo already has (so the list below does not repeat it) **[code]**

| Area | What exists today |
|---|---|
| Understanding | Chat in English and Hindi/Hinglish with follow-ups and replied-to text; remembered facts and preferences (Cortex 83); "forget about X" (Candor 86); tool-using answers that search, recall and calculate; plain-words market replies; Cortex's date and arithmetic checks. Mood detection only from **explicit phrases** ("I feel…", "cheer me up") (`_n69_detect_mood`). |
| Communicating | Telegram text; voice notes in (Groq speech-to-text, a local fallback `faster-whisper`); voice replies out (Edge neural voice, gTTS fallback); a "talk mode"; a device voice queue; Twilio phone and WhatsApp webhooks; a website and phone-app chat page. A typing indicator while thinking. One reaction call. |
| Expressing | Personas (`nemo_persona_*`); verbosity and detail preferences; pictures from nine engines, posters, charts, reports, nine world pictures (v101). |
| Connecting | Email, calendar, Drive, tasks (read-only, Argus 88); MCP servers with permission tiers; GitHub/PyPI (Forge); an enrolled laptop that reports status and runs **read-only** diagnostic jobs ("never arbitrary shell"); family roles (Circle 89). |
| Web | Search (ddgs), page reading (trafilatura/Playwright), verified research, page watchers, news fetchers (Scout). |
| Acting | A **browser agent on the server** (Playwright: look, decide, click and type, with a checkpoint for sensitive steps and receipts); download chains; projects of up to eight steps; reminders and watchers; self-development with your approval. |
| **Not there** | **Any typing, clicking or dictation on your own laptop or phone.** Semantic (meaning-based) memory. Streaming replies. Stickers, polls, video notes, Telegram Business mode. Hindi/Gujarati voices chosen by language. Writing email or calendar items (all read-only). A single place to see and steer all routines. Mood or stress reading beyond explicit words. Receipts-with-undo for actions. |

---

## 3. The lists

Each row: what it is, what you get, and evidence/cost. **Effort**: S = hours, M = a day or two, L = several days. **Risk** is to your money, privacy or server. Rows I recommend first are marked ★.

### A. UNDERSTAND you better ("Mind")

| # | Feature | What you get | Evidence | Effort / risk |
|---|---|---|---|---|
| A1 ★ | **Meaning-based memory with time.** Keep facts as short statements with a date and an "as of", find them by meaning (embeddings), and mark a fact superseded instead of deleting it ("lives in Surat" → moved). | "What did I decide about the showroom lease?" works even if you never used those words; Nemo knows what changed. | [web] Mem0 (personal-assistant memory), Zep (temporal graph), Letta (agent edits its own memory) are the three families; Mem0's pipeline is extract → dedupe → embed → retrieve. Benchmark claims are contested. [code] Nemo has no vector store. | M / low; needs a small embedding model run as a one-at-a-time child process (the Wire pattern) or an API embedding. |
| A2 ★ | **"What I know about you" card.** One screen listing what Nemo believes about you (people, routines, preferences, projects, languages), each line editable or deletable by a sentence. | You see and control the profile. Builds trust and fixes wrong beliefs. | [mine]; fits Candor 86's forgetting. | S / low |
| A3 ★ | **Ask before guessing.** When a request is ambiguous and the action matters, ask *one* short question (or show a two-line plan with a Go/Change button) instead of guessing; stay quiet when it is clear. | Fewer wrong actions; faster than correcting later. | [web] Research frames "when to ask a clarifying question" as an open balance (too many is annoying, too few is costly); a perspective-taking prompt (infer the user's knowledge, goal and likely misunderstanding first) is a cheap approximation. | S / low |
| A4 | **Context fusion.** Answers use your calendar, tasks and mail when relevant ("you have a 4 pm call, so leave by 3:15"), with the source named. | Answers that fit your day. | [code] the readers exist (Argus); [mine] the joining. | M / low (read-only) |
| A5 ★ | **Indian-language understanding, end to end.** Detect Hindi, Gujarati, English and mixed speech; answer in the same language and script; keep names and numbers exact; transliteration both ways. | Family members can use Nemo in their own language. | [code] Hindi/Hinglish exist, Gujarati barely. [web] Sarvam's API lists speech-to-text and text-to-speech for 11 Indian languages including Gujarati; AI4Bharat's open Indic speech models are reported for 22 languages (vendor blog: unverified). [gap] I found no Gujarati speech benchmark. | M / low; test on your own voice notes first |
| A6 | **Multimodal understanding.** Understand short videos (not just pictures), screenshots of apps and receipts, and long PDFs with tables. | "What is wrong in this screenshot?", "summarise this 30-second clip". | [web] SmolVLM2 (256M-2.2B, Apache-2.0) and MiniCPM-V 4.6 (1.3B, video, Apache-2.0); Docling (MIT, CPU, one pip install) and MinerU (CPU pipeline mode) for documents. [gap] no open screen-understanding model confirmed. | M / low-medium (memory: run on the laptop or an API) |
| A7 | **Follow-up and reference resolution.** "That one", "the same as last time", "send it to him": resolve to the right thing from the last few turns, and say what it resolved to. | Natural conversation. | [code] partly exists. | S / low |
| A8 | **Learning from corrections.** When you correct Nemo, store the lesson as a rule you can see ("always give amounts in lakhs"), apply it, and test that it was applied. | Mistakes do not repeat. | [mine]; builds on A1/A2. | M / low |
| A9 | **A profile per family member.** Language, reading level, interests, do-not-discuss topics; a child mode (simple words, no web beyond a safe list). | Each person gets the Nemo that suits them. | [code] Circle has roles, not styles. | M / low |

### B. COMMUNICATE (channels, voice, speed)

| # | Feature | What you get | Evidence | Effort / risk |
|---|---|---|---|---|
| B1 ★ | **Streaming replies.** Text appears as it is written, like a person typing. | Feels alive; you can stop a wrong answer early. | [web] Telegram's Bot API reportedly added streaming (`sendMessageDraft`, said to be fully available from about version 9.5, early 2026), plus a "user stopped generation" update in 10.3; the sources disagree on dates. [gap] I could not open Telegram's own changelog from the sandbox: confirm on core.telegram.org/bots/api-changelog. [code] not used. | S-M / low |
| B2 ★ | **Voice conversation that fits you.** Send a voice note, get a voice note (a real voice-note bubble, not an audio file), in your language, with speed and tone you choose; text twin on request. | Hands-free use; elders and children can use it. | [code] voice in and out exist (Edge voice, gTTS). [web] Piper (the usual small local voice) was archived in October 2025; Kokoro (82M, fast, Hindi reported but unverified) and Svara-TTS (built on Orpheus, 19 Indian languages, emotion tags) are the candidates; Orpheus-size models need a GPU or a lot of RAM. | M / low |
| B3 | **Phone calls on your behalf** ("call the plumber, ask the price, tell me"). Live speech-to-text and text-to-speech over a phone line, with a summary afterwards. | Saves real time. | [code] Twilio call hooks exist. [web] open full-duplex speech models exist (Moshi: English only; an NVIDIA open model with tool calling); the practical route is a pipeline (speech-to-text → model → text-to-speech). **Needs rules [mine]:** say it is an AI at the start, never record without telling, never take payments or OTPs, your approval before any call, follow India's calling rules. | L / **high** (law, privacy); not before B2 is solid |
| B4 | **Talk to the world for you, with approval.** Draft replies to email and WhatsApp messages and send only after your tap; "triage my inbox" lists what needs you. Optionally Telegram Business mode (a bot replying inside your own chats). | Less time in inboxes. | [code] mail is read-only, WhatsApp via Twilio exists. [web] a May 2026 update is reported to let business bots manage a user's chats and allow chat automation; I could not confirm this against Telegram's own page. | M / medium (a wrong send is public) |
| B5 | **Interpreter mode.** Live translation between Hindi, Gujarati and English, text and voice ("translate what the vendor says"). | Everyday use with vendors and relatives. | [code] translation by AI exists; the mode and voice do not. | M / low |
| B6 | **Richer Telegram messages.** Polls ("which colour for the showroom wall?"), buttons, ephemeral (only-you) messages in groups, video notes. | Family decisions in the group chat. | [web] ephemeral messages and voice-note input reported in Bot API 10.2 (July 2026), rich buttons in 10.3 (August 2026). [code] none used. | S / low |
| B7 | **Notification manners.** Quiet hours per person, priority levels (urgent now / digest later), one daily digest instead of ten pings, "snooze Nemo for 2 hours". | Nemo stops being noisy as it does more. | [code] quiet-hours settings exist for some alerts; not global. | S / low |

### C. EXPRESS (personality and presentation)

| # | Feature | What you get | Evidence | Effort / risk |
|---|---|---|---|---|
| C1 | **Tone dials you can speak to.** "Be shorter", "more formal with customers", "joke less", "talk to me like a friend". Remembered per person and per situation. | Nemo sounds like the right Nemo. | [code] personas and verbosity exist; per-situation does not. | S / low |
| C2 | **Expressive voice and reactions.** Emotion in the voice (warm, calm, excited) chosen by the situation; a reaction emoji or a sticker where a person would send one. | Less robotic. | [web] Svara-TTS (emotion tags), Orpheus (guided emotion) **[unverified for Hindi quality]**. [code] one reaction call, no stickers. | S-M / low |
| C3 | **Explain with a picture.** A diagram, timeline, comparison table or one-page summary instead of a wall of text, when it helps. | Faster understanding. | [code] Studio draws charts, posters and reports (v90, v101). | S / low |
| C4 | **Teaching and storytelling modes.** Study mode (asks you questions, spaced repetition: already in Office 95), a bedtime-story mode for children, a "explain like I am new" mode. | Learning for the family. | [code] flashcards exist. | S / low |
| C5 | **"Why did you do that?" for actions, not just answers.** Every action gets a one-line reason and a receipt. | Trust. | [code] `/why83` explains answers. | S / low (and see H2) |

### D. "FEEL": understand your mood and answer kindly ("Heart")

| # | Feature | What you get | Evidence | Effort / risk |
|---|---|---|---|---|
| D1 ★ | **A consent-based mood and stress read.** From text (word choice, short curt replies, late-night messages, repeated rephrasing), and only if you switch it on. Shown as "you sound stressed, want a short answer?", never as a diagnosis. | Better-fitting replies; you can see and turn it off. | [code] explicit phrases only today. [web] voice-emotion models exist (Hume EVI is commercial; accuracy claims are vendor-adjacent; whether voice maps reliably to emotion across people and cultures is an open debate). **Do text first.** | S-M / medium (privacy; wrong reads) |
| D2 ★ | **An empathic reply policy.** Acknowledge first, then ask or offer; no lectures; no medical or legal claims; if you mention hurting yourself, a calm message with real helplines and a nudge to a person, and nothing cute. | A kinder Nemo that is safe in a bad moment. | [mine]; consistent with the companion-harm research [web]. | S / low (needs careful wording and tests) |
| D3 ★ | **Anti-flattery guard.** Nemo says when it disagrees, says when it is unsure, does not echo your mood to please you, does not say "I missed you" or claim feelings, and nudges you toward friends and family. A test set checks it. | An assistant you can trust to tell you the truth. | [web] sycophancy rollback, INTIMA benchmark categories, 2026 low-sycophancy experiment. | S-M / low |
| D4 ★ | **Trading-tilt guard.** After a losing streak, a big loss, or rapid-fire decisions, Nemo says so once ("three stops today; Sigma's breaker is on; want to stop for today?"). Ties to Sigma's circuit breaker and the Lab's streak alerts. | The most valuable "feeling" feature for you: it protects money. | [code] Sigma breaker and Lab alerts exist; [mine] the human-facing nudge. | S / low |
| D5 | **Wellbeing nudges (opt-in).** Water, a break after hours at the screen, a late-night "sleep?" once, a weekly "how are you" that you can ignore. | Small kindnesses without nagging. | [mine] | S / low |
| D6 | **Remembering the people side.** Birthdays, anniversaries, a relative's exam day, "call mom on Sunday", gift ideas from past mentions. | Nemo helps you show up for people. | [code] calendar read exists; [mine] the people memory (needs A1/A2). | M / low |

### E. CONNECT to your world

| # | Feature | What you get | Evidence | Effort / risk |
|---|---|---|---|---|
| E1 ★ | **Write actions with an approval card:** draft and send email, create a calendar event, add a task, upload a file. Always shown first, sent only on your tap, logged. | Nemo moves from "sees" to "does" safely. | [code] reads exist, approval cards exist (Steward 85). | M / medium |
| E2 | **More MCP tools, by tier.** Calendar, notes, maps, shopping lists; each new tool arrives read-only first; Nemo lists what each can do. | A wider reach without new code. | [code] MCP presets and tiers exist. [web] MCP and A2A now sit under the Linux Foundation's Agentic AI Foundation (founded December 2025); A2A (agent-to-agent) reached v1.0 in 2026; cross-agent messages are untrusted input. | S per tool / medium |
| E3 | **Smart home.** Lights, fans, AC, a "leaving home" routine, through Home Assistant (local, open-source). | "Turn off the showroom lights" from Telegram. | [web] Home Assistant's Assist plus an optional local model; start without a model. | M / medium (physical effects: confirm unlocks and heaters) |
| E4 | **Money, read-only.** Bills and due dates as reminders; GST and invoice drafts (exist); a UPI deep link you tap in your own app. **No automatic payments and no card or OTP handling, ever.** | Help with money without the risk. | [code] GST/invoice drafts exist. | S / low |
| E5 | **People and business graph.** Who is a customer, vendor, relative, with phone, notes and last contact; "who owes me?", "who have I not called?". | The showroom and the family in one memory. | [code] showroom copilot has leads and dues; [mine] the shared graph. | M / low |
| E6 | **Natural-language automations.** "When a customer's payment is more than 7 days late, remind me and draft a message." | Rules without code. | [web] Scheduled Tasks/Actions in ChatGPT and Gemini are the user-facing model. See G6. | M / low-medium |

### F. WEB SEARCH and knowledge

| # | Feature | What you get | Evidence | Effort / risk |
|---|---|---|---|---|
| F1 ★ | **Research that plans, reads, cross-checks and cites.** A plan (what to find out), several searches, each page read in full, claims tied to sources with dates, contradictions flagged, "what I could not confirm" listed. | Answers you can rely on and verify. | [code] Steward's verified research exists; [web] deep-research agents all follow plan → browse → evaluate → cite. | M / low |
| F2 | **Your own search engine and more sources.** SearXNG (self-hosted meta-search), news, Wikipedia, Reddit threads, YouTube transcripts, government and exchange notices (RBI, SEBI, NSE). | No search quota; better coverage. | [code] roadmap item C2 (AGPL; Docker or pip); transcripts via a library. | M / low |
| F3 | **"Watch this topic".** Standing research: Nemo checks daily and tells you only what *changed* ("RBI repo rate decision", "GST notification on X", "my competitor's price"). | News that finds you. | [code] page watchers exist; [mine] topic watching with diffs. | M / low |
| F4 | **Long video and audio reading.** A YouTube lecture or a news interview summarised with timestamps and the 5 claims worth checking. | Hours saved. | [code] YouTube download chain exists; transcripts [mine]. | M / low |
| F5 | **Live facts as tools.** Weather, local business hours and maps, flights and trains where an API exists, currency, sports scores. | Practical daily answers. | [mine] | S per tool / low |
| F6 | **Fact-check mode.** "Is this forward true?" Paste a message, get what is verifiable, what is not, and the sources. | Stops family-group misinformation. | [mine]; built on F1. | S / low |

### G. DO THINGS FOR YOU: automatic typing and tasks ("Hands")

This is the group you asked about most. The safe order is G1 → G2 → G3 → G4.

| # | Feature | What you get | Evidence | Effort / risk |
|---|---|---|---|---|
| G1 ★ | **Routines in plain words, with a log.** "Every Monday 9 am send me last week's sales", "daily 8:30 world markets + calendar", "remind me and ask before ordering". One place to list, pause, run now, edit, and see the history of each run (did it work? what did it do?). | The proactive Nemo, steerable. | [code] reminders, watchers, alerts and briefs exist in separate places. [web] ChatGPT retired Pulse for Scheduled Tasks because steerable beats surprising; Gemini caps scheduled actions at 10. | M / low |
| G2 ★ | **A stronger browser agent on the server.** Saved **playbooks** for sites you use (so it does not re-discover the page each time), a site allow-list, screenshots as receipts, resume after a failure, stop on anything unexpected, and a repeat-test before a playbook is trusted. | Reliable web chores: portals, forms, price checks, downloads. | [code] Playwright agent with sensitive-step checkpoints exists. [web] open frameworks: browser-use (MIT, about 89% on the WebVoyager benchmark, vendor-reported), Stagehand (MIT; code with AI only where needed), Skyvern (AGPL; vision, handles 2FA/CAPTCHA); **no independent head-to-head**, test on your own tasks. | M / medium |
| G3 ★ | **Nemo Hands on your Windows laptop** (opt-in, the step you asked about). A small program on the enrolled laptop that can: **type text** where your cursor is, press keys, open apps and files, click named buttons by reading the window's controls (not by guessing pixels), fill forms, copy/paste, and take a screenshot as a receipt. **Safety design [mine]:** every plan is shown as a card with Go/Stop; an on-screen "Nemo is controlling this PC" banner; a global **stop hotkey**; an app allow-list (nothing in your bank or password manager); it never types passwords or OTPs; a time limit per session; every step logged with a screenshot; typed-text preview before sending; disabled when you lock the screen. | "Open the GST portal, log in (you type the password), download the return" or "type this invoice into my billing software". | [code] today's laptop agent is read-only on purpose. [web] Windows-MCP (MIT) is an open reference for this: Click, Type, window-state tools; it states plainly that it takes real actions on your machine. Latency reported at 0.2-2.5 seconds per action. [web] on the hardest long desktop tasks even the best agents fail most runs (section 1), so keep tasks short. | L / **medium-high**; build in stages: (1) dictation, (2) type-into-this-box, (3) open/click named controls, (4) multi-step plans |
| G4 ★ | **Dictation anywhere.** Hold a hotkey, speak (Hindi, Gujarati or English), and Nemo types the cleaned-up text into whatever field is active. | The simplest big win of G3 and low risk (you speak, you see it type, you stay in control). | [code] speech-to-text exists; [web] on a small CPU use the multilingual `small` int8 model (about 1.5 GB of memory; 13 minutes of audio in under 2 minutes) or run it on the laptop; I found no Hindi accuracy numbers for the faster "turbo" model. | M / low |
| G5 | **Typing on your phone.** An Android route: ADB or an on-phone helper driven by a vision model, with confirmation for sensitive steps and manual takeover for logins. iPhone is not realistic (Apple blocks it; only Shortcuts). | "Send this message on WhatsApp", "open the app and check the balance". | [web] Open-AutoGLM (ADB or HDC; screen-reading model; confirmation and takeover built in; tested mostly on Chinese apps), DroidRun (LLM-agnostic; ADB). One secondary blog reports 36.2% on the AndroidLab benchmark for these phone agents (unclear which project). [mine] low reliability today. **Later**, after G3 is proven. | L / medium-high |
| G6 | **Form and document filling.** GST invoices, bank or government forms, quotation sheets: from your saved profile, shown as a preview, filled only after your tap. | Paperwork done. | [code] invoice drafts and GSTIN checks exist (Steward 85, Office 95). | M / medium |
| G7 | **Plans that run, not just lists.** A project of up to eight steps becomes a plan with tools, retries, a rollback point and a stop-on-surprise rule; each step reports. | Bigger tasks, done in the open. | [code] Projects keep steps; they do not execute them. [web] long-task reliability drops fast (section 1): keep each step short and verified. | L / medium |
| G8 | **Tidy-ups on your PC with a dry run.** Organise Downloads, rename scans, back up a folder: shown as a list of what *would* change, done on your tap, undoable. | Chores gone. | [mine]; via the laptop agent. | M / medium |

### H. TRUST, SAFETY and QUALITY (these make A-G usable)

| # | Feature | What you get | Evidence | Effort / risk |
|---|---|---|---|---|
| H1 ★ | **The "rule of two".** A run may combine at most two of: reading untrusted content, touching private data, acting outward. A third needs your tap. | Blocks the main attack on agents. | [web] lethal trifecta and the "Agents Rule of Two". | S / low |
| H2 ★ | **Receipts and undo.** Every action: what, why, when, the before/after, and an Undo where one exists (restore a file, delete a draft, cancel an event). "What did you do today?" already lists; it becomes "…and undo the last one". | You can let Nemo do more because you can reverse it. | [code] the activity log exists (Argus); undo does not. | M / low |
| H3 | **An injection filter.** Text from web pages, emails and documents is wrapped as data; instructions found in it are listed ("this page tried to tell me to…") and ignored. | Safer web reading. | [web] the research says no prompt wording is a reliable fix; the structure (separation, a second reviewer model, no outward action after untrusted input) is. | M / low |
| H4 ★ | **A repeat-test before trust.** Each automation runs five times in a safe sandbox or dry run; only if it passes every time is it marked "reliable". Failures show where. | You know which automations to rely on. | [web] τ-bench's pass^k idea. | M / low |
| H5 | **Budgets and manners.** A cost and time limit per task; heavy jobs one at a time and only when memory is free (Wire's rule). | No surprise bills; the VPS and the trading assistant stay safe. | [code] Candor 86 has time limits; Wire has the memory rule. | S / low |
| H6 | **A panic word.** "Nemo stop everything": halts routines, laptop control, calls and pending sends, and says what it stopped. | Calm. | [mine] | S / low |
| H7 | **Privacy walls and retention.** Each family member's memory is separate; your profile is never shown to others; old conversations expire on a schedule you choose; export and delete on request. | Family use without leaks. | [code] Circle isolates abilities; retention is not scheduled. India's data-protection law may apply to what you keep about other people: check with a professional. | M / low |

---

## 4. The order I would build things (small, safe, valuable first)

| Step | Name | Contents | Why here |
|---|---|---|---|
| 1 | **Mind** | A1 meaning-based memory, A2 "what I know about you" card, A3 ask-before-guessing, A5 Hindi/Gujarati understanding, A7 references | Everything else is better when Nemo understands you. Low risk. |
| 2 | **Voice** | B1 streaming, B2 voice-note conversation in your languages, B7 notification manners, C1-C2 tone and expression | Makes Nemo feel alive and usable by the whole family. |
| 3 | **Heart** | D1-D4 (mood read with consent, empathic policy, anti-flattery guard, trading-tilt guard), H6 panic word | Small and valuable; D4 protects money. |
| 4 | **Routines** | G1 routines with a log, E1 write actions with approval, H1 rule of two, H2 receipts and undo, H4 repeat-test | The base that makes any automation safe. |
| 5 | **Hands** | G2 browser agent upgrade, then G4 dictation anywhere, then G3 Nemo Hands on the laptop (in the four stages above) | The typing and clicking you asked for, built on the safety base of step 4. |
| 6 | **Reach** | F1-F4 deeper research and topic watching, E2/E3/E5 connections, B4 drafted replies | Breadth. |
| 7 | **Later / only if wanted** | G5 phone typing, B3 phone calls, G7 executing plans, A6 video understanding | Higher risk or lower reliability today. |

Offline mode (parked as v102) stays valid and independent; it fits between steps 2 and 4.

## 5. What I would not build (and why)

* **Anything that spends or moves money by itself** (payments, transfers, trades): the cost of one wrong action is too high; Nemo suggests, you tap in your own app.
* **Unattended sending** of email, WhatsApp or calls: every outward message goes through your tap until a routine has passed H4 for weeks.
* **Voice cloning of family or customers** without their clear consent.
* **Claiming feelings, or "missing" you.** It is not true, and the research says it is not good for people.
* **Community "skills" or plug-ins installed unscanned** (the OpenClaw lesson). Forge's approval, pinning and rollback stay the only way in.
* **A public version** that anyone can talk to with access to your tools.
* **A local large model on the VPS.** It does not fit. If you ever want one, it belongs on the laptop.

## 6. What I need from you

1. **Which computer should Nemo control?** The Windows laptop that is enrolled now? Any other? (G3/G4.)
2. **Do you want phone control** (Android only), or is the laptop enough for now? (G5.)
3. **Which languages do the family use** for typing and for voice (Hindi, Gujarati, English, mixed)? (A5, B2.)
4. **Do you want the mood read (D1)** on for you only, or also for family members who agree?
5. **Should Nemo be allowed to send email or messages after your tap,** and from which accounts? (E1, B4.)
6. **Which first,** the whole of step 1 (Mind) or something you feel the lack of today?

## 7. What I could not verify

* **Telegram's own changelog** (the sandbox cannot reach it): the streaming, Business-mode, ephemeral-message and voice-note items come from secondary sources that disagree on dates.
* **How the commercial agents (Operator, ChatGPT agent, Claude, Gemini) do in daily use:** the search returned benchmark pages, not product evaluations. Benchmarks are mostly vendor-reported.
* **Hindi and Gujarati speech quality** of every model named (no public benchmark found for Gujarati).
* **Any independent test of Hume-style voice emotion reading** (only vendor-adjacent reviews).
* **How the open browser frameworks compare** on your tasks: no independent head-to-head; run each on a fixed set of your own tasks.
* **Exact memory and speed on your 2-core server** for any model named: estimates only.
* Nothing here was run: this is research, not a build.

## Sources (web search results; read as "reported")

* OSWorld 2.0 and computer-use benchmarks: [OSWorld 2.0 leaderboard (Yutori)](https://yutori.com/leaderboards/osworld-2), [OSWorld 2.0 (benchlm)](https://benchlm.ai/benchmarks/osworld2), [AgentAtlas](https://arxiv.org/html/2605.20530v1)
* τ-bench and pass^k: [τ-bench paper](https://arxiv.org/pdf/2406.12045)
* OpenClaw and agent security: [The Hacker News](https://thehackernews.com/2026/03/openclaw-ai-agent-flaws-could-enable.html), [IBM X-Force](https://www.ibm.com/think/x-force/what-openclaw-reveals-about-agentic-ai-security-risks), [Cisco](https://blogs.cisco.com/ai/personal-ai-agents-like-openclaw-are-a-security-nightmare), [Jamf](https://www.jamf.com/blog/openclaw-ai-agent-insider-threat-analysis/), [Backslash](https://www.backslash.security/blog/openclaw-security-risks-explained)
* The lethal trifecta: [Simon Willison](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/), [GitLab docs](https://docs.gitlab.com/user/duo_agent_platform/security_threats/), [Sophos](https://www.sophos.com/blog/inside-the-lethal-trifecta-blast-radius-reduction-in-ai-agent-deployments)
* Memory frameworks: [Atlan comparison](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/), [mcp.directory](https://mcp.directory/blog/mem0-vs-letta-vs-zep-vs-cognee-2026)
* Voice and speech: [Svara-TTS](https://huggingface.co/blog/kenpath/svara-tts-open-multilingual-speech-for-india), [open TTS roundup](https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models), [speech-to-speech comparison](https://inworld.ai/resources/best-speech-to-speech-model), [Hugging Face speech-to-speech](https://github.com/huggingface/speech-to-speech), [Home Assistant local voice stack](https://www.kunalganglani.com/blog/local-ai-voice-assistant-whisper-piper-ollama)
* Indian languages: [Sarvam docs](https://docs.sarvam.ai/api-reference-docs/getting-started/models), [open voice AI for India overview](https://caller.digital/blog/open-source-voice-ai-india-sarvam-ai4bharat-bhasini-2026)
* Speech-to-text on CPU: [faster-whisper CPU deployment](https://codesphere.com/articles/deploying-faster-whisper-on-cpu), [Whisper large-v3 turbo](https://medium.com/axinc-ai/whisper-large-v3-turbo-high-accuracy-and-fast-speech-recognition-model-be2f6af77bdc)
* Emotion and companions: [Hume overview](https://getcoai.com/news/humes-ai-assistants-bring-emotional-intelligence-to-llms), [INTIMA benchmark](https://arxiv.org/pdf/2508.09998), [Harmful traits of AI companions](https://arxiv.org/pdf/2511.14972)
* Proactive assistants: [ChatGPT Pulse help page](https://help.openai.com/en/articles/12293630-chatgpt-pulse), [Gemini scheduled actions](https://blog.google/products-and-platforms/products/gemini/scheduled-actions-gemini-app/)
* Phone agents: [Open-AutoGLM](https://technode.com/2025/12/09/zhipu-ai-open-sources-autoglm-an-ai-agent-model-capable-of-full-phone-operation/), [DroidRun](https://landscape.jimmysong.io/projects/droidrun/)
* Desktop agents: [Windows-MCP](https://mcpservers.org/servers/CursorTouch/Windows-MCP)
* Browser agents: [Skyvern's comparison](https://www.skyvern.com/blog/browser-use-vs-stagehand-which-is-better/), [DevToolLab](https://devtoollab.com/blog/best-ai-browser-automation-tools)
* Telegram: [Bot API changelog](https://core.telegram.org/bots/api-changelog) (not opened), [Telegram Bot API for AI agents](https://zeroclaws.io/blog/telegram-bot-api-2026-ai-agent-developers-guide/), [TechTimes on bot-to-bot](https://www.techtimes.com/articles/316790/20260518/telegrams-bot-api-now-lets-autonomous-ai-agents-coordinate-directly-no-federal-multi-agent.htm)
* Agent standards: [A2A and MCP at the Linux Foundation](https://www.flowhunt.io/blog/agentic-ai-foundation-a2a-mcp-standards/)
* Documents and small vision models: [Docling vs MinerU](https://www.file2markdown.ai/blog/docling-vs-mineru), [MiniCPM-V 4.6](https://rits.shanghai.nyu.edu/ai/minicpm-v-4-6-a-1-3b-multimodal-model-built-for-phones/)
* Deep research: [2026 research-agent roundup](https://resources.rework.com/tools/ai-agents/best-ai-research-agents-2026)
* Understanding and clarifying questions: [UserHarness (explicit user-state tracking)](https://www.emergentmind.com/papers/2605.27721), [Does theory-of-mind improvement really benefit human-AI interaction? (a sceptical lead)](https://arxiv.org/pdf/2605.15205)
