# Nemo v82 → v83 "Cortex": analysis, research basis and what changed

`nemotron_bot.py` in this repo is the **v83.0** build. Commit 1 on this branch is your v82.0 upload byte-for-byte; commit 2 is
v83. `git diff` between them shows the whole change: 6 modified lines plus one contiguous 1,533-line block inserted before the
`if __name__ == '__main__':` guard. `bot.py` / `Procfile` (the older NSE trading bot) are untouched.

## 1. What Nemo v82 is (verified by AST, import and execution)

| Fact | Value |
|---|---|
| Size | 64,555 lines · 3.98 MB · 3,233 top-level functions (2,693 unique names) · 6 classes |
| Structure | One file built as ~145 stacked "layers" (`_n28_`, `_n50_`, `_n69_` …). A newer layer re-defines a function and wraps the old one: `handle` is defined 109×, `main` 104×, `ask_ai` 23× (83 names in total) |
| Surface | ~1,100 slash-command literals · 260 SQLite tables · 444 `Thread(` call sites · 87 shell/subprocess call sites · 89 runtime `pip`/`_imp` references |
| Dependencies | stdlib + `requests`; everything else installs itself or degrades |
| Secrets | **None embedded** (v70.1+ resolves from env / `/root/bot_secrets.json`). Scanned for 11 key shapes |
| Loads cleanly | `import` takes ~2.5 s, no network, no threads started at import |
| Self-checks | `prime_regression_suite()` = 795 rows; **790 pass in a clean sandbox**. The 5 failing rows are environmental (no matplotlib ×2, kv table not initialised, no network ×2) |

### How an owner message flows today (v80–v82)
`handle()` (outermost wrapper) → `_n82_dispatch` (exact phrases) → … → `_n72_dispatch` → task engine (`_n66`, 4 workers, 12 admitted)
→ `_n72_task` → **an LLM intent-router call (18 s budget)** → one of 13 routes (`chat80`, `work`, `legacy`, `trade75`,
`drive76`, `develop79`, `project82`, …). Model calls go through **Brain73** (`_n73_request`): per-role provider/model chains,
3-slot gate, per-(provider,model) cooldowns, redacted receipts. The money/message/trade rails (Guardian, approvals,
paper-only `trade75`, v81 trading guard) are separate and are not touched by v83.

### Verified gaps in v82 (each reproduced, not assumed)
1. **The main conversation route has amnesia.** `chat80 → _n80_chat → _n73_core_reply` bypasses `ask_ai()`, where the Unified
   Mind memory was injected, and nothing on that route extracts facts. Result: *"what is my wife's name?"* gets no stored fact
   in its prompt. Test `TestBaselineGapIsReal` proves the v82 prompt lacks the fact and the v83 prompt has it.
2. **No sense of time.** The chat prompt contains no current date/time, so "this Friday", deadlines and day-of-week arithmetic
   are guesses.
3. **No tools in chat.** The prompt tells the model to say "a tool workflow is needed"; there is no way to look something up,
   recall, or calculate inside a turn. Router mistakes therefore turn into stale or invented answers.
4. **No answer verification** on this route (arithmetic is a classic silent failure).
5. **Long chats are not compacted**: 12 messages of RAM history, nothing durable.
6. **Every message pays for an LLM router call**, including "hi" / "thanks".
7. **Latent bug:** `_n60_j` is called in the media-resolver failure report but is never defined → `NameError` exactly when
   every downloader has failed (pyflakes finding, confirmed at runtime).
8. **Legacy extractor false positives** (`_n35_extract`): "my city is different now" stores `city = "Different Now"`
   (its relation pattern accepts any word). v83 deliberately does not call it.
9. **Gateway design hazard (not fixed, worked around):** Brain73 cools a model down for 45 s–60 min on *any* failed call and
   the cooldown is shared across roles. One failing optional call (e.g. a malformed helper request) can therefore degrade the
   main chat model. See §4 for how v83 avoids creating such failures. A per-role cooldown key would be a worthwhile follow-up.

## 2. Research basis → design

| Practice (2025-26 sources) | v83 feature |
|---|---|
| Agent memory = extract → compare with existing → ADD / UPDATE / NOOP (Mem0, Zep temporal facts), consolidate, give users control | `cx83` memory bridge: model proposes, deterministic rules dispose; supersession via existing `_n35_set_fact`; near-duplicate skip; `/memory83`, `/forget83`, pause, audit log |
| Context engineering: compaction + structured notes (Anthropic) | Rolling conversation summary stored in SQLite, injected as user-role *data* |
| ReAct / plan-and-execute with a small, observable tool loop; external ground truth beats self-assessment | Scout → read-only tools (search, recall, calculate, date) → answer; **deterministic arithmetic audit** |
| Chain-of-Verification (draft → verify → revise) | Critique pass for complex answers; only issues whose *quoted text really appears in the draft* are acted on |
| "Lethal trifecta" (untrusted input + sensitive data + exfil channel): remove a leg architecturally | See §4 |
| Proactivity must be calibrated; users want transparency and control | No new unsolicited messages except one rate-limited "did this change?" question; `/why83` receipt |

## 3. What v83 adds

* **Memory bridge** – relevant stored facts (with *age*: "learned 3 weeks ago") go into every chat turn. New durable facts are
  learned in the background from the **owner's own message only**. Rejected outright: secrets, links, ≥9-digit numbers,
  instruction/permission-like text ("always buy…", "never ask me…"), reserved keys (`standing_instruction`, `password`, …),
  questions, forwarded/quoted/pasted content, and sensitive topics (health, beliefs, legal trouble) unless you say "remember".
  A well-established fact is never silently overwritten by a model guess: Nemo asks once per day per fact.
* **Grounding** – IST date/time in every prompt; exact date arithmetic (`today + 45 days`, `days until 25 Dec 2026`,
  `weekday of 26/01/2027`, `next friday`, month-end/leap clamping).
* **Tool loop** – a cheap scout decides if `search` / `recall` / `calculate` / `date` are needed (≤3 per round, ≤2 rounds).
  Search results appear as labelled untrusted evidence; sources are appended when the model didn't cite them.
* **Verification** – every answer's `a op b = c` and `X% of Y = Z` statements are recomputed with the existing safe calculator;
  a wrong one triggers one repair call, else a visible ⚠️ line. Complex answers also get the quote-verified critique.
* **Compaction** – after ~10 long-chat turns older messages are folded into a ≤1,200-char summary.
* **Fast path** – greetings/thanks skip the router model call.
* **Transparency** – `/why83` shows evidence tools, memory keys, checks, model, latency of the last answer.
* **Fix** – `_n60_j` defined. `_n83_*` added to the self-development "never edit" list (like v81/v82 rails).

### Commands (owner only, exact phrases, no model involved)
`/cortex83` status · `/memory83` list · `/memory83 recent` learning log · `/forget83 <word>` · `/memory83 pause|resume` ·
`/why83` · `/cortex83 <memory|notify|verify|tools> <on|off>` · natural: "what do you remember about me", "pause memory",
"why did you say that", "show your sources".

## 4. Safety model
* **Tools cannot act.** `search`, `recall`, `calculate`, `date` are read-only. No send/write/trade/install/delete tool exists in the loop,
  and the chat prompt still forbids claiming an action was done.
* **Trifecta broken by construction:** (a) memory is written only from owner-authored text, never from web/tool output;
  (b) round 2 of the loop can never call `search`, so tool output cannot steer an outbound query; (c) outbound queries are
  validated (≤100 chars, no links/emails/long numbers/secret words/stored phone, email, address, salary… values).
* **Authority unchanged:** stored facts are labelled data; they never grant money, messaging, trading, deletion or install
  authority. The summary (model-written text) is placed in a user-role message, not the system prompt.
* **Fail-open to the old behaviour:** any Cortex exception, missing key, busy gateway or timeout falls back to the v80 `_n80_chat`.
  Cancellation returns "Stopped", it never re-runs the legacy path.
* **Gateway-friendly:** helper JSON calls reuse the `route` model chain through `_route_override` but are sent with a
  non-validated role (the gateway would reject non-router JSON for role `route` and start a cooldown), and always carry a
  non-empty system message. Background jobs only run when ≥2 of the 3 provider slots are free.

## 5. Verification performed (and what it does not prove)
* `tests/test_cortex83.py`: **76 tests**, all passing. Includes: the before/after amnesia demonstration; date grammar incl.
  leap/month-end; arithmetic audit with false-positive guards; extraction guards (secrets, links, instructions, sensitive
  topics, caps, conflicts); tool-loop injection test (search text trying to trigger a second query); verification repair and
  quote-verified critique; compaction; owner-only controls; the real daemon worker thread (failure, overflow, headroom);
  and **integration runs through the real Brain73 gateway** with only HTTP faked (this caught a real defect, see §4).
* Static: `py_compile` OK; pyflakes shows **no new messages** (2 fewer than v82); diff vs v82 is exactly 6 lines + one block.
* The bot's own `/regress` suite: 795 + 21 new `v83-*` rows; no new failures vs the v82 baseline.
* An owner message was driven through the real `handle()` → task engine → existing router → Cortex → `send_text` chain.
* **Not verified:** behaviour against live Anthropic/OpenAI/OpenRouter/Gemini endpoints, real Telegram delivery, answer
  *quality*, and cost. The fake provider proves plumbing and safety logic, not that the model writes good answers. Treat the
  first day as a canary: watch `/cortex83` counters and `/why83`.
* **Coverage:** I analysed architecture, the message path, Brain73, memory, task engine, update path, security posture and
  regression health. I did **not** audit the media/YouTube, device-grid, browser-agent, trading or PDF modules line by line.

## 6. Deploy / roll back
1. Download `nemotron_bot.py` from this branch, send it to Nemo in Telegram, send `/update`. It compile-checks, shows
   `v82.0 → v83.0`, and waits for **Apply & restart**. `/rollback` restores the previous file.
2. After restart send `/regress` (expect only the environment-dependent rows to differ from before) and `/cortex83`.
3. Try: "my sister Priya lives in Pune" → later "what do I know about my sister?" · "what date is it in 45 days?" ·
   "18% of 1250?" · `/memory83` · `/why83`.
4. Kill-switches without redeploying: `/cortex83 tools off`, `verify off`, `memory off`.
   Cost note: a normal turn is 1 answer call (+1 cheap scout call when the message looks tool-ish) + 1 background cheap call
   for personal messages; deep questions use the `reason` route plus a cheap critique.

To run the tests: `python -m unittest tests.test_cortex83 -v` (importing the bot has filesystem side effects by design,
e.g. writes under `/root/` when run as root; use a throwaway container).

## 7. Recommended next steps (not done here)
1. Work71 (the research/file agent) is plan-once-then-execute: add replanning after observations, full-page fetch, and a
   grounding check of the draft against its evidence.
2. Per-role cooldown keys in Brain73 (see gap 9).
3. Semantic (embedding) retrieval for the new memory block, and a periodic consolidation job.
4. Tighten the legacy `_n35_extract` relation pattern (names must look like names).
5. Long-term: the layered-wrapper structure (109-deep `handle`) makes every change risky and slow to reason about; splitting the
   file into modules with one dispatcher would pay for itself quickly.
