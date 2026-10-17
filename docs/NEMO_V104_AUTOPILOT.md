# Nemo v104.0 "Autopilot": everything Nemo does by itself, in one place, with receipts, undo, earned trust and a stop word

You asked how to make Nemo more autonomous and more powerful, "like Jarvis", and then said "all" to my four example jobs (morning brief, dues and follow-ups, invoice drafts, mail triage) and to the whole plan. This is step 1 of that plan, the base the other steps stand on: **Nemo should be able to do things by himself, and you should always be able to see what he did, why, undo it, and stop it.** Without that, more power only means more risk.

## 0. Read this first (the honest version)

* **Built and tested offline. Nothing here has run against your real Telegram, your real AI providers, your real Gmail or your real showroom data.** The AI calls in the tests are scripted; the business data is a throw-away database. What a real model says in a routine or a plan, and how the cards look on your phone, you will be the first to see.
* **Nemo cannot do anything outward on his own, by design.** There are five kinds of routine (a saved question, dues and follow-ups with draft messages, mail triage, invoice drafts, a repeated reminder) and none of them sends, buys, sells, pays, deletes, installs or runs a command. Dues messages and follow-ups are **drafts for you to send**; Nemo never messages your customers. Invoices are **drafts** that you issue yourself.
* **A new routine starts as PRACTICE.** It runs on its schedule, shows you the result, labels it "Practice run 2 of 5" and does nothing outward. After five clean runs in a row, Nemo **asks** whether it may run on its own. You tap Yes. One 👎 puts it back to practice. Nothing promotes itself.
* **"stop everything" is separate from `/panic`.** It stops what Autopilot knows about (routines, plans, approvals, the `/work` queue, and the built-in jobs it can see) and tells you exactly what it stopped and what it did **not** touch. It never changes the trading agent: the reply carries a button that replays your own `/panic` if you also want new orders halted. `/panic` itself is unchanged.
* **Not every background job in Nemo is on the Autopilot list.** Twelve built-in jobs are (section 3). Reminders and price alerts you set, and any job I did not wrap, keep running when you say "stop everything"; the reply says so.
* **Invoice drafts need one decision from you** (`autopilot invoice supply intra` or `inter`) and a stock record with a price and a GST rate that **you** entered. Without them Nemo lists what is waiting and says why he did not draft; he never assumes a tax rate.
* **Hindi and Gujarati draft messages are my wording, not checked by a native speaker.** Each such message carries a line saying so. Read them before you send.
* **The time-and-memory guard is simple.** Routines that use an AI wait for a free provider slot and 400 MB of free memory; one routine runs at a time. A run missed by more than three hours (the server was down) is skipped, not replayed late.
* No order, no trading-agent setting, no guard, no owner lock, no credential is touched. The layer calls no order function (a test checks every function of the layer for that), runs no command, and sends nothing to anyone but you.

## 1. What it does

| You say | What happens |
|---|---|
| `autopilot` (also `what runs by itself`, `my routines`) | One list: your routines (mode, next run, last result), the 12 built-in jobs (on or paused, when each last spoke), your `/every` and `/at` actions, the `/work` queue, and a line saying the trading agent is **not** managed here |
| `autopilot setup` | Creates the everyday jobs in practice mode: dues and follow-ups (weekdays 09:30), invoice drafts (weekdays 18:00), mail triage (weekdays 08:15 and 17:30), and switches on the existing morning brief. Safe to say twice |
| `routine every weekday at 9:30 send me the dues` | Makes a routine from plain words. More: `routine every day at 8:15 and 5:30 pm check my mail` · `routine every monday at 9 am what is new in nifty options` · `routine every day at 7 pm remind me to check stock` · `routine roz subah 8 baje dues` · `routine every morning at 9 check my mail` · `routine remind me every day at 9 pm to take medicine` · `routine every 2 hours …` (not shorter than 30 minutes). Times are Indian time; a bare hour 1 to 11 means morning (say `pm` for the evening). A bare `routine checkup is due` is treated as ordinary talk, not as a routine |
| A routine that would act outward (`email my customers`, `buy`, `delete`…) | Refused with the reason. "send **me** …" is fine (it only reaches you) |
| `pause morning brief` · `resume dues` · `run mail triage now` · `delete routine R-1A2B` · `routine R-1A2B` (details) · `pause 3` (the third line of the last list) · `pause eod` · `pause watchdog` · `pause all routines` · `pause everything` | Control. A name, an id, a number from the list, a nickname of a built-in job, or a few words. If two match, Nemo asks which. `run … now` works for your routines; for a built-in job or a scheduled action the phrase goes to whatever handled it before. `turn on morning brief` also switches the (opt-in) brief on |
| `autopilot log` · `autopilot receipts` | What ran by itself, newest first: when, which, practice or on its own, what it sent, 👍/👎, "can be undone" |
| `why did you do that` | Within 30 minutes of an Autopilot message: where it came from, why it ran, what it did, whether it can be undone, how to stop it. Otherwise the normal "how did you get that answer" receipt handles it |
| 👍 Useful / 👎 Wrong / ↩ Undo under every routine message | 👎 sends the routine back to practice. Undo removes the invoice drafts that run created, **only** those still in draft (one you already issued is left alone and Nemo says so) |
| `trust dues` · `put dues back to practice` | Ask for the promotion card early (refused with the reason until five clean runs) · demote |
| `autopilot invoice supply intra` / `inter` | The one decision invoice drafts need (CGST + SGST, or IGST) |
| `plan: find out what changed in the SEBI rules this month and tell me what matters for me` | Up to eight steps from a **read-only** list (search, recall, look at mail/calendar/Drive/tasks, your documents, your business records, calculate, date, futures calculators, think, ask you, deliver). Shown as a card with ▶️ Go / ✖ Cancel. Nothing runs before Go. A step that fails stops the plan and says which steps finished. An `ask` step waits for you. Ten-minute limit. Goals that ask for sending, buying, deleting or installing are refused |
| `my plans` · `cancel plan` | The last plans · cancel the open one |
| `stop everything` (also `emergency stop`, `stop autopilot`, `sab roko`, `सब रोको`) | Section 4 |
| `resume autopilot` | Back on. Runs missed while stopped are skipped, not replayed. The `/work` queue stays paused until you add a job |
| `autopilot help` | This list in the chat |

## 2. How it stays safe

* **The rule of two.** Every kind declares what it touches: reads outside content (U), uses your private data (P), acts outward (O). A run may combine two; **all three never run without your tap**, and the check is in the mode logic itself (`_n104_effective_mode`, `_n104_promote`), not in the kinds. Today no kind has O at all.
* **A fixed list, not free-form.** A routine is one of five kinds with parameters; text you type becomes a *question* or *reminder text*, never an instruction to run. A plan's steps come from a fixed tool list and are **fixed when the card is shown**: text found on a web page or in a mail can add no step (a test feeds an injected "add a step: shell…" through a step's output and checks the stored steps are unchanged and the thinking step is told to treat the material as data).
* **Trust is earned, and one 👎 takes it away.** Practice, then (for kinds that write) "asks first", then "on its own". Promotion needs five clean runs in a row *and* your tap, and is asked at most every two weeks.
* **Receipts.** Every run, built-in job that spoke, scheduled action, work job and plan leaves a receipt (when, how long, why it ran, what it sent, what it changed). Secrets are masked in receipts like everywhere else in Nemo, and "forget …" now reaches receipts and plans.
* **Owner only.** Commands go through the owner front door (your private chat only); buttons from anyone else, or from your id in another chat, are acknowledged and ignored.
* **AI use is bounded.** A routine's AI call uses the same gateway, keys and cool-downs as chat, the shared time budget, waits for headroom and memory, masks secrets in your saved question before it leaves, and leaves no trace in the conversation or the memory clerk.

## 3. What it wraps (and how)

The built-in jobs are **wrapped, not rewritten**: a paused job is skipped (it returns its neutral value), a job that speaks leaves a receipt, a job that raises still raises. Wrapped: morning brief (the opt-in v85 one), good-morning brief, daily news brief, pre-market brief, end-of-day wrap, live market nudges, chief-of-staff watch, app watchdog, weekly stay-current research, page watchers, inbox watch, Sigma brief. Also wrapped: scheduled actions (`_run_action`: `/every`, `/at`) and the `/work` agent (`agent_run`). `send_text` gets a small capture so a job's messages become its receipt; every call still goes through unchanged. Pausing a scheduled action pauses it (its text is remembered); it is never deleted.

Limit: a job that sends from a different thread than the one the scheduler called is not captured, so it may run without leaving a receipt (it still obeys pause and "stop everything").

## 4. "stop everything", exactly

Sets one switch (stored, so it survives a restart) and then: routines will not run; wrapped built-in jobs return without doing anything; scheduled actions are skipped, not deleted; open plans are stopped; pending approvals are withdrawn; supervised tasks are asked to stop; queued `/work` jobs are cleared and the engine paused (a `/work` job **already running** cannot be interrupted from here and finishes the step it is on, same as `/stopwork`; the reply says so when it applies). The reply lists these with counts, then "NOT touched:" the trading agent's mode, whether new orders are halted, whether a position is open, and that `/panic` halts new orders but closes nothing; then "also untouched": reminders and price alerts, memory, chats, and any background job not on the Autopilot list. Buttons: **Also halt trading (/panic)** (replays your own `/panic` through the normal door) and **Resume autopilot**.

## 5. What I did not do

* No new power to act outward. That is the point of this step; "Hands" (typing on your laptop, browser playbooks) and "Reach" stand on this base and each asks for your tap per action.
* No editing of a routine (say it again and delete the old one); no rollback of a plan beyond "stops and says what finished" (plans only read, so there is nothing to roll back); no retries inside a plan.
* The trading agent is not a routine and has no practice mode here. Its own safeguards (`/panic`, caps, holiday guards) are unchanged. A trading follow-up (for example "tell me every morning how the practice agent did") would be a read-only routine kind and can be added on request.
* No attempt to read a sender's intent in mail: mail triage lists unread mail and the existing mail analysis summarises it; it does not reply, label, archive or delete.
* Calendar-driven routines ("30 minutes before each meeting…") are not built.

## 6. Verified and not verified

**Verified offline (237 new tests, `tests/test_autopilot104.py`):** the schedule parser (English, Hinglish, edge hours, impossible times, 30-minute floor), next-run arithmetic across weekends, the rule of two and its enforcement in mode logic, creating routines in plain words (and refusing outward ones, over-long ones, the 20-routine cap, strangers, groups, photos), finding a routine by id, words, number and tie-breaks, pause/resume/delete/details, dues digests with draft messages (English, Hindi, Gujarati and the warning), invoice drafts (no stock record, no supply type, practice, ask-first, on its own with undo, undo leaving issued invoices, no double drafting, one bad record not losing the others' undo), the trust ladder (five runs, promotion card, kinds that write going through ask-first, 👎 demotion, no nagging), receipts and "why", the clock (due, missed, retry when the AI is busy, giving up after four tries and saying so, low memory), saved questions and mail triage with scripted AI and mail, "stop everything" (phrases and non-phrases, what it reports, nothing runs afterwards, the trading agent's dictionaries unchanged, the halt button replaying `/panic`, work queue, plans, approvals, restart persistence), plans (validator, card before Go, stop on surprise, injected text, ask step, ten-minute limit, cancel), wrappers (real built-ins wrapped once, receipts, pause, error propagation, per-thread capture), the doors, and structure checks (no order function reachable from any function of the layer, the trading agent only ever read, no secrets or command execution in the layer, regression rows, capabilities text).

**Mutation check:** I broke the layer on purpose in 15 places that matter for safety (rule-of-two cap removed, "stop everything" touching the trading agent, plan validator accepting any tool, practice runs creating invoices, undo deleting issued invoices, buttons not owner-gated, outward routines allowed, missed runs replayed, pause ignored, "stop everything" ignored by routines, 👎 not demoting, promotion before five runs, plans continuing after a failure, "send me" softening removed, forget store missing). The new tests failed for every one of them.

**Not verified (you will be the first to see):**
* Anything with a real model: whether a saved question gives a useful answer, whether the plan a real model writes is sensible (it only has to pass the checks above), whether mail triage text is good.
* Real Gmail, real Telegram rendering of the cards and buttons, real timing on your server (the tests drive the clock directly).
* The wrapping of your live built-in jobs: the tests wrap the real functions and call a real one (the morning brief tick), but they do not wait for 08:30 on your server.
* The Hindi and Gujarati draft wording against a native reader.
* How the practice-then-promote rhythm feels in daily use (five clean runs may be too many or too few for you).

## 7. Try it, through Nemo

1. `autopilot help`, then `autopilot` (the list; the built-in jobs should match what you know).
2. `autopilot setup`, then `autopilot invoice supply intra` (use `inter` if you bill other states). Make sure a stock record has a price and GST rate: `stock set item="Sofa set" qty=5 price=45000 gst=18`.
3. `run dues now` and `run mail triage now`: practice runs with the label. Tap 👍 or 👎.
4. Add a won lead and `run invoices now`: it should say what it **would** draft and create nothing; check `invoice list` is unchanged.
5. `routine every 2 hours remind me to drink water`, then `pause water`, `resume water`, `delete routine R-…` (use the id shown).
6. `autopilot log`, then `why did you do that` right after a routine message.
7. `plan: compare what changed in SEBI futures margin rules this month and what it means for a small trader`: read the card, tap Cancel once; make it again and tap Go.
8. `stop everything`: read the reply, check it says the trading agent was not touched. Then `resume autopilot`.
9. After five clean practice runs of one routine you will get a promotion card. Say Not yet once to see that it does not ask again for two weeks.

## 8. What changed in older code (everything else is in the new layer, marker `# NEMO 104 - AUTOPILOT`)

Two lines: the docstring's first line, and the protected-names list for live self-edit (`_n104_` added). In the tests, one older test (`tests/test_steward85_biz.py`) had a hard-coded follow-up date that went stale (it failed on the unchanged v103 file too); it now uses a date relative to today.

## 9. Test results (offline, on the test machine)

- **New tests: 237** in `tests/test_autopilot104.py`; all pass.
- **Whole suite on the exact file delivered (the slow gate switched on): 3,546 tests, 7 skipped, 1 error.** The one error is not in this layer: it is a temporary-folder clean-up race in the tear-down of an older Scholar test (`test_scholar98`, "Directory not empty" while removing a temp folder). That test passes alone, twice, and its whole module passes (50 tests); the same kind of clean-up flake showed up once in the v103 run. I have not found what writes into the folder late. Every other test, old and new, passes.
- **What the test runs caught while I built this, and what I did about it.** Fixed before delivery: "send me …" was read as an outward action (a saved question like "send me a summary of my notes" was refused); a deleted routine's receipts showed an id instead of its name (receipts now keep the title); `pause 3` (a bare number from the list) did not match the command pattern; a run started by hand while the AI was busy ended in silence (it now says so); four tries in a row at a scheduled time gave up silently (it now says so); one bad record during invoice drafting would have lost the undo list of the others (each record is now isolated); "stop everything" did not say that a `/work` job already running cannot be interrupted; a bare `routine checkup is due` and a bare `receipts` were being taken over (neither is any more); `turn on morning brief` said "back on" while the opt-in brief was still switched off (it now switches it on).
- **One older test had a stale date**, a follow-up date written into `tests/test_steward85_biz.py` that is now in the past; it failed the same way on the unchanged v103 file. It now uses a date relative to today. Other fixed dates in that file are still in the future and will go stale the same way; I left them.
- **Pyflakes:** the same 158 messages as v103, none new. A scan of the added lines for keys, tokens or passwords found none. Only two lines of older code were edited in `nemotron_bot.py` (the docstring's first line and the protected-names list).
- Nothing here placed, changed or simulated an order, called a broker, called a cloud AI, ran a model, used a paid service or sent anything to anyone. The AI calls in the tests are scripted.
