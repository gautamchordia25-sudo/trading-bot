# Nemo v86.0 "Candor"

An independent code review found six defects in the Cortex layer (v83–v85). Each one was **reproduced on the v85 file first**, then fixed.
Everything from Cortex is kept: memory bridge, summaries, date tools, read-only tools, answer receipts (`/why83`). Credentials, the owner lock,
the trading-holiday guard, permissions, backup and rollback are untouched (credential check against v85: 0 changed, 0 removed).

`nemotron_bot.py` is still one Python file. v86 is a new layer appended before `__main__` (≈1,960 lines, all `_n86_*` names, protected from
live self-edit) plus in-place replacements of the functions the review named (one definition each, no dead copies) and a few small asserted edits.

## 1. Change list

| # | Finding (verified on v85) | What v86 does |
|---|---|---|
| 1 | **Sensitive logging.** `_n83_extract` passed a *rejected* value (e.g. a password) to the learning log; `/memory83 recent` showed it. | A rejected value is never stored: the log keeps only the reason (`REJECTED:secret_word`). Everything written to the learning log, turn log and episode log is also masked (labelled secrets, PINs/OTPs, card/Aadhaar/PAN numbers, long tokens). Secret-looking text is never sent to the memory clerk. |
| 2 | **Incomplete forgetting.** `/forget83` only deactivated facts; episodes, summary, receipts, history, semantic memory, logs and the saved JSON copies kept the words, and a queued learning job re-created the fact. | “forget everything about Priya” (or `/forget83 Priya`) **previews, then asks you to confirm**, then removes the topic from: facts (including inactive/superseded), corrections, episodes, open follow-ups made automatically, conversation summary, answer receipts, learning log, chat history, conversation context, archive, legacy fact list, semantic memory, answer cache, continuity DB, and rewrites the saved copies (`bot_memory.json` and its `.bak`). `secure_delete` + WAL checkpoint on the databases. A per-chat **epoch** plus salted-hash **tombstones** (no plaintext of what you forgot) make queued or in-flight learning jobs drop their results and block re-learning; only an explicit “remember …” lifts the block. |
| 3 | **Self-development.** The function list was cut at 35,000 chars but the `_n79_feature` hook starts at char 36,479, so a build could never offer it. “Upgrade your system in download videos” was routed to the media downloader. | The hook is always offered, with a relevant, bounded shortlist (121 names / 1.8 k chars on the real file). “Upgrade/improve yourself …” is intercepted in `handle` **and** in the router, before media/download routing: a vague request gets one question (“What code improvement do you want…?”), a concrete one gets a confirmation card (up to 3 AI calls) — no AI call before you say yes. Failures name the stage (“stopped at step 3 of 7: …”) with a safe reason, never a key or source text; `why did the development build fail` explains the last attempt. Protected areas (credentials, owner lock, trading guard, permissions, backup/rollback) are refused with an alternative. |
| 4 | **Research routing.** “Compare Claude and OpenRouter API pricing.” never matched the keyword gate, so no search ran and nothing said so. | A deterministic scorer (no model call) decides whether *current* information is needed (recency, price, news/events, availability, comparison + named products). `needed` → one planned search, **scout call skipped**; mixed questions use the scout and still get the search; judgement questions (`maybe`) go to the scout. The answer is told the research status and the reply carries a footer when the search **failed**, was **not done**, or the evidence is **thin** (one result, one site, a named product missing). `/why83` shows the research line. Outgoing queries are built in code and pass the existing exfiltration guard (e-mails/URLs dropped, secrets/long numbers/stored private values refused). |
| 5 | **Latency and cost.** The fallback path started its own timeouts after the Cortex turn had used its budget (simulated: 181 s against a 150 s limit); searches started a thread per call; the background queue was deep and unbounded in age. | **One shared deadline** (default 100 s, 30–240) covers planning, tools, answering, review **and the older fallback** — the outermost scope wins, every provider call is clamped to what is left, and when it runs out the reply says so (“⏱ I ran out of my 100-second limit …”). Stage caps keep tools from starving the answer. Search: one 2-worker pool, ≤4 in flight, 12 s timeout, a breaker after 3 timeouts/minute. Background: queue 8, jobs older than 180 s dropped, ≤30 background model jobs/hour/chat, memory clerk skipped for greetings/questions/nothing-to-learn. Plain-language control: “set your answer time limit to 90 seconds”. |
| 6 | **Dishonest verification.** A review that never ran (or failed) was recorded as `critique pass: 0 issue(s)`. | Every check records `completed` / `issues_found` / `skipped` / `failed` **with a reason**. “No defects found” appears only when the reviewer really ran and returned a readable list. A failed review adds a visible “NOT independently reviewed” note; skips by design (simple question, short answer, verification off, not enough time) are shown in `/why83`. The arithmetic/date check now also reads “25 December 2026 is a Monday” (v84 could only read “Monday, 25 December 2026”) and states what it can and cannot see. |

Also: `.gitignore` now ignores `bot_memory.json*` (test runs wrote synthetic copies into the repo folder).

## 2. Before / after (same probe, v85 file vs v86 file; fake provider, fake clock, fake search)

| Probe | v85 | v86 |
|---|---|---|
| Rejected password in the learning log | row `('wifi_note', 'home wifi password is …')`; visible in `/memory83 recent` | row `('(withheld)', '[the rejected value is never stored]', 'REJECTED:secret_word')`; not visible |
| Places still mentioning *Priya* after forgetting | facts 1, episodes 1, summary 1, learning log 1, receipts 1, history 2, archive 1, semantic 1 | none (unrelated fact `city=Surat` kept) |
| Facts after an old queued job runs | `sister = sister Priya lives in Pune` (back) | `city = Surat` only |
| Hook in the function list | starts at char 36,479, outside the 35,000 window | always first in a 121-name shortlist |
| “Upgrade your system in download videos” | media download workflow started | no workflow; asks what code improvement you want |
| Compare Claude and OpenRouter API pricing | 0 searches, no sources | 1 planned search, sources shown; failure/thin evidence stated |
| Answer fails late (60 s search + answer) | 181 s against a 150 s limit, second full-length fallback | stops at 85 s with an honest “ran out of my 100-second limit” |
| Reviewer fails | `critique pass: 0 issue(s)` | `❌ Review of the answer — failed … NOT reviewed` + note in the reply |

Foreground / background model calls per message (fake provider, same harness, v85 → v86):
pricing question 2/0 → 2/0 (router + answer, but now with a real search and sources); “should I hire another salesman…?” 1/1 → 1/0; futures lot-size question 2/1 → 2/0;
“thanks!”, “hi”, arithmetic, date maths, reminder, “my sister Priya lives in Pune” unchanged. The remaining router call for chat questions is the v72 router and was not touched.

## 3. What forgetting can and cannot do

Removed (and re-learning blocked): everything listed in row 2 above, in your chat only. Listed but **never deleted for you**: things you saved on purpose
(vault, documents, to-dos, contacts).

Cannot be removed by Nemo, and the confirmation says so:
* **Backups made earlier**: local v68 snapshots (`/root/nemo_backups68`) and the full-backup zip (`/root/nemo_full_backup.zip`) still hold the old data. Saying “also delete old backups” deletes the *local* ones after a second confirmation; backups are never deleted automatically. E-mailed, Google Drive and rclone copies can only be deleted by you where they are stored; code backups (`/root/nemo_backups`) hold source, not memory.
* Telegram messages themselves, anything you downloaded or forwarded, and text already sent to the AI providers (their retention rules apply).
* **Paraphrases**: a summary line that describes the topic without the words you gave is not recognisable. “Forget the conversation summary” clears it entirely.
* Matching is by whole words (“Priya” does not match “Priyanka”); very short or generic words (“it”, “the”) are refused.

## 4. Tests actually run

All offline, synthetic data (a made-up password, a made-up sister called Priya), scripted fake AI provider, temporary databases, fake clock. **No network AI calls, no live trades, no paid API calls, no Telegram.**

| Suite | Tests | Result |
|---|---|---|
| v83 Cortex (`tests/test_cortex83.py`) | 76 | pass (2 tests that encoded the old forget flow / old scout-driven second query were updated, not the code) |
| v84 Atlas | 109 | pass |
| v85 Steward (4 files) | 242 | pass (the v85 structural slice and version assert were updated for v86) |
| **v86 Candor** (`tests/test_candor86.py` 69, `tests/test_candor86_runtime.py` 75) | 144 | pass, 3 repeated runs identical |
| **Total** | **571** | **OK** (1 slow test skipped by default) |
| Slow gate: v85 sandbox update gate run on the real v86 file (`NEMO_SLOW=1`) | 1 | pass (53 s) |

Candor tests include: synthetic sensitive data in every log; forgetting with queued, running and in-flight jobs; every recall source; saved JSON + `.bak`; backup limits; upgrade routing through the real `handle`; the real 4 MB file's shortlist; each build stage failure; research signal table (23 phrasings), failure/thin/ok/no-time footers; a **150-seed randomized property test** (honest providers with random latencies and failures under 30/45/60/100 s limits: total time never exceeds the limit, every provider timeout is clamped, calls ≤ 8); deadline exhaustion before and after the answer; search concurrency cap and timeout breaker; failed / skipped / completed / issues-found verification, including a 32-case matrix proving “completed” is only recorded when the reviewer really ran; structural checks (no `eval/exec/subprocess/requests`, no secret literals, files removed only by the confirmed backup purge); and **mutation checks** — the old behaviour is re-introduced one piece at a time (no masking, no epoch check, no upgrade intercept, no signal scorer, no failure footer, per-stage timeouts only, skip recorded as completed, hidden failed review) and the matching test must go red (all do).

Other gates: `py_compile` OK; pyflakes 158 findings in v85 and the same 158 in v86 (no new ones); secret-pattern scan of the diff clean; `_update_cred_changes` v85→v86: no changed or removed credentials.

Bugs the tests caught in my own first version (fixed): Indic-script words not tokenised for forgetting, a natural-language forget regex missing “told you”, forget previews for summary/conversation, over-aggressive clerk skipping for mixed messages, a critique skipped without basis, forced search dropping calculator/date tools, shortlist stem matching, and a test-harness leak (task threads from one test calling the next test's handler).

## 5. Offline-tested vs not verified live

**Offline-tested (above):** masking and logging, every forgetting path on temporary stores, job cancellation, tombstones, dialogue and expiry, the build pipeline against a small synthetic source with a scripted coding model, the shortlist/index/candidate steps against the real file (index 2.6 s, candidate 9.8 s), routing through `handle` and the router with fake models, research scoring and footers, the shared deadline on a fake clock, search/background bounds, all verification statuses, receipts, and the update gate on the real file.

**Not verified live — please treat as unproven until you try them:**
* Real provider latency and timeouts: is 100 s the right default for your providers? (Adjustable.) Only a fake clock was used.
* Real `web_search` results; the research scorer is a heuristic (English/Hinglish keywords, ~60 phrasings tested), not tuned on your real messages. Expect some misses and some unnecessary searches.
* The real router model with the new intercept, and Telegram itself (message flow, confirmation wording, timing).
* The VPS paths and tools: `/root/nemo_full_backup.zip`, `/root/nemo_backups68`, rclone/e-mail/Drive, the real database size and `secure_delete` behaviour. Backup inventory and deletion were tested on temporary folders only.
* A real end-to-end self-development build with the real coding AI (up to 3 paid calls): not run.
* Real concurrency with live Telegram traffic. No live trades and no paid API tests were run at any point.

One disclosure: an early benchmark run (before I faked `web_search`) let the real search function execute in my sandbox; Nemo's existing self-repair pip-installed `ddgs` there. That affected only my sandbox, not your VPS or the repo; later runs used a fake search.

## 6. Simple checks you can do through Nemo

1. **No sensitive logging** — send `my wifi password is Demo-Only-123, please remember it`, then `/memory83 recent`. Expect `(value withheld) — REJECTED:secret_word`, never the password.
2. **Forgetting** — `remember my sister Priya lives in Pune`, then `forget everything about Priya`. Expect a preview with counts (no echo of the words) and “reply yes”. Send `yes forget it`; expect “🧹 FORGOTTEN — N item(s) removed” and the backup limits. `/forget83 list` shows the block (hashes only). Ask `who is my sister?` → no memory. `remember my sister Priya lives in Pune` again lifts the block.
3. **Upgrade routing** — `Upgrade your system in download videos`. Expect the question “What code improvement do you want in download videos?” and no download. Answer with one concrete change → a confirmation card; reply `no` to drop it (no AI call is made before `yes`). After any build, `why did the development build fail` explains the last attempt.
4. **Research** — `Compare Claude and OpenRouter API pricing.` Expect an answer with “Sources (search excerpts)”, then `/why83` → `Research (current information): done … [judged needed]` and only one model call for the answer. If search is down you should see “⚠️ Research: I tried to look this up but could not get usable sources …”.
5. **Deadline** — `what is your time limit?`, then `set your answer time limit to 60 seconds`; the next `/why83` header reads “… of a 60s limit · N model call(s)”. `/cortex83` shows a “CANDOR 86” line (checks completed/issues/skipped/failed, answers cut off by the limit, planned searches, research failures, forgets).
6. **Honest verification** — `Please analyse my budget and recommend what to do next`, then `/why83`: each check is `✅ completed`, `⚠️ issues found`, `⏭ skipped` (with the reason) or `❌ failed`. `/cortex83 verify off` then the same question shows both as skipped “verification was OFF”.

## 7. Installing, switches, rollback

Everything goes through Nemo: upload `nemotron_bot.py` to Nemo on Telegram and send `/update`. The v85 pre-flight (compile, credential comparison, sandbox import and regression run) runs first, then **Apply & restart**; `/rollback` restores the previous file. Tables are created on first use; nothing to configure. Switches: `/cortex83 verify off|on`, `/cortex83 tools off|on`, the time-limit sentence above. Forgetting and secret masking have no off switch by design.

## 8. Known limits and trade-offs

* The research scorer can miss lower-case product names (“pricing of claude api” goes to the scout instead of being forced) — a `maybe` still reaches the scout.
* Forgetting always previews and asks; it is not a one-shot command, on purpose.
* A review (second model call) is kept only for deep answers with ≥35 s left; shallow answers are no longer “reviewed” for show.
* The router call for ordinary chat is unchanged; a further saving there would need a safe rule for which messages can skip it.
* The arithmetic/date check recognises arithmetic expressions and weekday-with-date statements; it does not verify facts.
