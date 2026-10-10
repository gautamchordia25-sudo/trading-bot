# Nemo v88.0 "Argus": Nemo can see (mail, calendar, Drive, his own work), analyse and watch

You said: *"when I ask him to read the last 5 emails it says I cannot see them … Nemo cannot see what is going on or what he is doing … make Nemo an ultimate assistant who sees, reads, analyses and watches."*
Everything from v87 (Relay) and earlier is kept. Credentials, the owner lock, the trading holiday guards, permissions/approval cards, backup and rollback are untouched
(credential check against v87: 0 changed, 0 removed).

## 1. What was wrong (found by reading the code, not guessed)

Nemo already had **readers** for almost everything: the Gmail/Calendar/Drive API helpers, IMAP settings, task and download tables, reminders, watchers, the audit ledger, the error log, device records, positions.
But the *conversation* (the part that answers free text) had only six read-only tools — web search, recall, calculator, date, futures, documents (plus MCP) — and **no knowledge of what Nemo is connected to**.
So when you said "read my last 5 emails", the chat model had no way to look and no way to know it could, and it answered the safe-sounding thing: *"I cannot see them."*
The same hole explained "what are you doing?", "what did you do today?", "what can you do?" and "how is everything going?": nothing fed those answers to the model.
Where mail could not be read for a real reason (Google not connected, scope missing, API switched off, login expired) the reason was never said.

## 2. What v88 does

### a) Eyes — read-only, owner-only, private chat only

| Say (any natural wording, Hinglish too) | Nemo does |
|---|---|
| `read my last 5 emails` · `any new mail?` · `check my inbox` · `how many unread emails do I have` | Lists sender, subject, time (IST), unread flag, a snippet. Numbers are remembered. |
| `any mail from Rahul about the invoice?` · `who emailed me today` · `mails from yesterday` | Searches (Gmail query built from your words). |
| `read #2` · `open the second one` · `read the latest email from the bank` | Full text of one mail (attachments are named, **not opened**). Numbers only work while a list is on screen. |
| `summarise my inbox` · `do I have any urgent emails` · `what matters in my email` | Same list **plus one AI read**: what needs you, by when, what can wait. Mail text is passed to the AI as *data, never instructions*; one-time codes/passwords/card numbers are withheld from the AI. |
| `can you see my emails?` · `what are you connected to` | A **live check** against Google, not a guess: "Yes — connected as …" or the exact reason. |
| `what is on my calendar tomorrow` · `what do I have today` · `am I free on Friday` | Calendar events with times. |
| `show my recent files in Drive` · `search Drive for invoice` | Drive listing / search (name search only, query escaped). |
| `what are you doing right now` · `show running tasks` | Running/queued tasks, downloads, recent actions. |
| `what did you do today` · `what happened yesterday` · `who messaged you today` | **Flight recorder**: who asked what and when, answers, tasks, downloads, errors, watcher alerts. |
| `show my reminders` · `list my todos` · `what are you watching` | Reminders, to-dos, alerts, watchers (incl. the inbox watch). |
| `how is the server` · `any errors` | Uptime, memory, disk, backups, unresolved errors. |
| `which devices are online` · `show my open positions` | Devices (enrolled/online), positions (from Fyers when it is logged in today). |
| `what can you do` · `/argus` | A **live map** of abilities: ✅ ready (and verified how long ago) · ⚪ off · 🔧 needs setup / problem — each with the one thing to say or do next. |
| `how is everything going` | A short **situation brief**: mail, calendar today, tasks, reminders, server, positions; one failing source never hides the others; one AI line only if a model is available. |

Everything above is **read-only**. Nothing is sent, deleted, marked read, labelled or archived; Google is only ever called with GET; the mailbox fallback opens `INBOX` with `readonly=True` and fetches with `BODY.PEEK`.
Sending, deleting, buying, selling and every other action still go through the existing approval cards. Sentences like *"send an email to Rahul"*, *"reply to Rahul"*, *"what is my email address"*, *"mark all mail as read"* are **not** taken by the new eyes — they go on to the normal path.

### b) Exact reasons instead of "I cannot see"

When something cannot be read, the message names the cause and the fix: Google not connected → *say "connect Google"*; login expired → reconnect; Gmail/Calendar/Drive **permission (scope) missing** → reconnect and approve it;
**API switched off** in your Google project → enable the Gmail/Calendar/Drive API; rate limit; network; other HTTP codes by number.
If Google is not usable but Nemo's **own mailbox** (`BOT_EMAIL`/`BOT_EMAIL_PASS`) is configured, mail is read from there over IMAP and **labelled clearly** ("Nemo's own mailbox, not your Gmail"). If both fail, both reasons are shown.

### c) The conversation gets a `see` tool and knows itself

* One new read-only tool, `see`, validated and time-boxed like the others: `mail`, `calendar`, `drive`, `tasks`, `reminders`, `watchers`, `activity`, `system`, `devices`, `positions`, `downloads`, `abilities`. So free-form questions combine them: *"is there anything from Rahul I should deal with, and what is on my calendar Friday?"*
* A failed source reaches the answer as **FAILED … do not pretend this was checked** with its exact reason. Output is labelled `[PRIVATE data …]`, mail as untrusted data, codes withheld.
* The chat prompt carries a short **live self-knowledge block** ("email: yes / calendar: connected / drive: NOT CONNECTED / inbox watch: off …", no network call, refreshed each minute) and the rule *never answer "I cannot see/access that" unless the tool itself failed*.
* The v86 "planned web search" shortcut no longer swallows a see-request (a real interplay bug the tests found: the forced search ran even after the scout chose `see`).

### d) Watching — your inbox

`watch my inbox` (or `…for everything`) · `stop watching my inbox` · `is my inbox being watched?`
Every 10 minutes Nemo looks for **new unread** mail and tells you about the important ones: real people, or automated mail that talks about money, deadlines, security, decisions. Promotions/newsletters (Gmail categories, unsubscribe headers, no-reply senders) stay quiet unless you chose "everything".
The first check only notes what is already there (no flood); each mail is announced once; you can answer with `read #1`. If mail cannot be read, you are told **once per 6 hours**, recovery is silent, and the state survives a restart.

### e) Privacy

* Owner only, private chat only; other people and groups cannot make Nemo read your mail or see the log.
* The flight recorder keeps **one line per message** (who, when, kind, first ~100 characters with secret-looking values masked); commands that carry secrets (`/env`, `/broker set`, `/email set`, `/proxy set`, …) and "forget/delete …" requests are recorded **without their text**. Rows older than 30 days are pruned.
* "Forget everything about X" (v86) now also clears the activity log and the in-memory mail list.
* Mail text goes to an AI provider **only** when you ask to analyse/summarise (or via the `see` tool during a conversation about your mail); codes and secrets are masked first.

## 3. Quick checks through Nemo (say these)

1. `what can you do` — expect a ✅/⚪/🔧 map; Gmail/Calendar/Drive should say *verified … as your@gmail*.
2. `can you see my emails?` — a live yes, or the exact reason (e.g. scope/API).
3. `read my last 5 emails` → `read #2` → `summarise my inbox`.
4. `what is on my calendar tomorrow` · `show my recent files in Drive`.
5. `what did you do today` · `what are you doing right now` · `how is everything going` · `how is the server`.
6. `watch my inbox` → wait for a real mail → `read #1` → `stop watching my inbox`.
7. `/argus` — the same map as (1).

If (2) says a permission is missing, say `connect Google` and approve Gmail, Calendar and Drive (the existing Google connection already asks for these scopes, so an account connected earlier normally has them); if it says an API is switched off, enable it in your Google Cloud project once.

## 4. Tests actually run

All offline: a **fake Google API** (Gmail, Calendar, Drive, with scripted failures: expired login, missing scope, API disabled, quota, 5xx, network), a **fake IMAP server** that records every command, temporary SQLite databases, a scripted fake AI provider, synthetic people and mail. **No Google, no AI network call, no trades, no paid APIs.**

| Suite | Tests | Result |
|---|---|---|
| v83 Cortex · v84 Atlas · v85 Steward · v86 Candor · v87 Relay (existing) | 718 | pass (v87's structure test now stops at the v88 layer marker) |
| **v88 Argus** (`tests/test_argus88.py`) | 148 | pass |
| **Total** | **866** | **OK** (1 slow test skipped by default) |
| Slow gate: v85 sandbox update gate run on the real v88 file | 1 | pass (57 s) |

The Argus tests cover: the failure-reason table and its sentences; Gmail parsing (sorting, unread, MIME-encoded names, HTML-only bodies, long bodies, bad ids refused before any request, attachments named not opened); the IMAP fallback (read-only select, PEEK fetches, only read commands issued, rejected password named); the mail phrase tables (lists, searches, time words, Hinglish, numbered reads only while a list is on screen, analysis words, watch phrases) and **look-alike sentences that must not be hijacked** (sending, replying, "what is my email address", other people's chats, groups); the front door end to end (no model call for a plain list, one call for an analysis, codes withheld, mail that gives orders treated as data, failures stated); calendar/Drive/tasks/reminders/watchers/devices/positions/system; the activity feed and its windows; the live abilities map; the situation brief (one failing source does not hide the others); the flight recorder (owner as "you", others by name, secrets and forget-requests not stored, pruning, a broken recorder never breaks chat); the `see` tool (parsing, refusal of anything else, scout validation, labelled private output, exact failure text, end-to-end through the conversation); the self-knowledge block; the inbox watch (baseline, importance, noise, no repeats, interval, once-per-6h failure notice, restart); **structure checks** (Google only via GET in one function, IMAP read-only, database writes only to the recorder table, no shell/eval/pickle/process calls, no sending/approval hooks, owner-private front door, no secret literals, credential/trading guards still present); and **mutation checks** — put the old blind behaviour back one piece at a time (vague "cannot see" text, unmasked codes, announcing newsletters, a front door that steals ordinary chat, a `see` tool that hides failures, a writable mailbox, repeat announcements, no recorder, forgetting that skips the new stores) and the matching test goes red (all do).

Other gates: `py_compile` OK; pyflakes 158 findings in v87 and the same 158 in v88; secret-pattern scan of the diff and tests clean; `_update_cred_changes` v87→v88: no changed or removed credentials; diff outside the appended layer is limited to the docstring line, the self-edit protection prefix, the `see` tool plumbing in the Cortex scout (`_N83_TOOLS`, the scout JSON spec, the validator and runner branches) and one condition in the v86 forced-search step.

## 5. Offline-tested vs not verified live

**Offline-tested:** everything above, against fakes.

**Not verified live — treat as unproven until you try the checks in section 3:**
* The real Gmail, Calendar and Drive responses on **your** Google account, including that your saved login has the read scopes and that the three APIs are enabled in your Google project (the fake API mirrors Google's documented shapes and error reasons; a real account may differ).
* The IMAP fallback against your real mailbox (Gmail needs an app password and IMAP enabled).
* Telegram message flow and timing of the inbox watch in the running bot.
* Fyers positions on a logged-in day; device records on your real devices.
* The quality of the AI analysis lines (a model summarises mail; check anything that matters in the original).

No live trades and no paid-API tests were run. No code reads or changes your credentials.

## 6. Limits

* Read-only by design. "Reply to Rahul", "delete these", "mark as read", "archive" are not done by Argus; they keep their existing paths/approvals (and mail actions are not part of this release).
* Mail attachments are listed, not opened. Very long mails are cut.
* The inbox watch checks every 10 minutes (not push). "Important" is a rule of thumb, not a promise; say "watch my inbox for everything" if you want every new mail.
* Activity before v88 is not in the flight recorder; it starts when you install this version.

## 7. Installing and rolling back

Upload `nemotron_bot.py` to Nemo on Telegram and send `/update` (v85 pre-flight: compile, credential comparison, sandbox import and regression run), then **Apply & restart**; `/rollback` restores the previous file. Nothing else to configure. Then run the checks in section 3 in order.
