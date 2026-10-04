# Nemo v85 "Steward": a chief of staff that proposes, and you decide

v85 is an additive layer on v84 (Atlas) and v83 (Cortex): one block before the `__main__` guard plus about fifteen lines of small, asserted in-place
edits (listed at the end). It delivers the seven features from the "what else could Nemo do besides trading" list, built on **one shared
approval mechanism** so that none of them can act on its own:

| # | Feature | One line |
|---|---|---|
| 1 | **Decision Inbox** | mail + calendar + open loops + projects + showroom data → a short, ranked queue of *grounded* proposals as Approve / Edit / Skip cards |
| 2 | **Research v2** | a loop that replans after every observation, reads full pages, and keeps a claim only if its quote is really in the page |
| 3 | **Sandbox-tested updates** | `/update` now imports the new file and runs its regression suite in a network-less sandbox *before* the Apply button exists |
| 4 | **MCP permission tiers** | every MCP call by any caller is read (runs) / write (needs your tap) / blocked |
| 5 | **Document intelligence** | page-cited answers, clause flags, version compare, table extraction |
| 6 | **Showroom copilot** | leads + follow-ups, dues, stock with reorder levels, exact GST invoice drafts, daily summary |
| 7 | **Watchers** | price / availability / keyword / change alerts that fire when something *changes* |

## The approval engine (what makes the rest safe)

* A **proposal** is a validated record `{kind, payload}` stored as *pending*. Proposing never executes anything (a structural test parses
  the code and fails if `_n85_propose` can reach an executor).
* The card shows the **exact** action. **Approve** claims the item atomically (`pending → executing`), runs it once, records the result and
  audits it. Double taps, stale cards, concurrent taps (6 threads in a test), expired items, and taps from any chat other than yours are
  harmless. A crash mid-run leaves the item `failed` after 10 minutes; it is never re-run silently.
* **Edit** (reply to the card) re-validates the new text; **Skip**, **Tomorrow** and **Undo** (reminders, to-dos, follow-ups, watchers; 24 h)
  are there too. Proposals expire after 2 days; at most 12 wait at once; duplicates are suppressed (7 days after approval, 14 after a skip).
* It **learns**: kinds you approve rank higher; a kind from a source you skipped 4 times with zero approvals is muted (`/steward85 stats`).
* The model never decides *what is allowed*. Kinds, URLs, recipients and tools are chosen or checked by code; model text is only ever
  filled into fields that code then validates.

| Kind | What approval does | Notes |
|---|---|---|
| `reminder`, `todo`, `followup` | adds to Nemo's own reminders / to-dos / open loops | undoable |
| `calendar_event` | Google Calendar insert | needs `/google` |
| `draft_message` | shows a draft; **Nemo sends nothing** | WhatsApp/SMS/e-mail text for you to copy |
| `send_email` | sends from your Gmail | **OFF by default** (`/steward85 send on`), only to the address that wrote the original mail, ≤10/day |
| `mcp_call` | runs a write-tier MCP tool with the stored arguments | blocked tier never runs, even after approval |
| `sheet_rows` | appends rows to a Google Sheet | from `/doc85 tables <id> sheet=<name>` |
| `biz_lead`, `biz_stock`, `biz_due` | writes to the showroom tables | from "lead: …", "inventory: …", "due: …" |
| `watch_add` | creates a page watcher | undoable |

## 1. Decision Inbox: `what needs my attention` · `/inbox85` · `/steward85 …`

Gathers unread mail (sender, subject, snippet), the next 3 days of calendar, your open follow-ups, next project steps, and the showroom
tables, then asks the model for at most five proposals. **Every LLM proposal must carry the item it came from and an exact quote (≥12
characters) from that item; the quote is verified in code and the proposal is dropped otherwise.** Further rules: unknown kinds, extra
fields and invalid payloads are dropped; drafts and e-mails may not contain a link the source did not contain; a `send_email` recipient must
equal the sender of that very mail (so an injected "forward everything to evil@…" cannot become a card), and while sending is off it is
downgraded to a draft. Mail text is redacted for secrets and labelled UNTRUSTED in the prompt. Rule-based proposals (no model): leads whose
follow-up date has come, overdue dues (both as *drafts*), low stock (as a to-do), so they survive a provider outage.

`/steward85 brief on` adds an opt-in 08:30 IST morning brief (once a day, silent if there is nothing). Other switches: `on|off`, `send`,
`watchers`, `gate`, `mcp`. `/steward85 pending | resend | clear | stats | status`.

## 2. Verified research: `/research85 [pdf] <question>` · `research: <question>`

A bounded loop (≤8 steps, ≤4 searches, ≤5 page fetches, ≤150 s): the model chooses *search / fetch source N / note / finish* after each
observation. It can only fetch sources it was **shown** (search results or a link you typed); queries pass the existing outbound-query guard.
A **note** is accepted only if (a) the quote appears verbatim in the fetched text (whitespace/case-insensitive, otherwise exact) and (b)
every number in the claim appears in the quote. Snippet-only sources are accepted at lower weight. The final answer is audited: citations
to sources without verified notes are removed and any number not in a verified note is flagged. Confidence is computed, not asked:
HIGH = ≥2 independent sites read in full and ≥3 strong notes and no conflict; conflicts are shown with both quotes. If nothing verifies,
the report says "I could not verify an answer" and shows no answer. Web pages can still be wrong; this proves *what the page says*.

## 3. Sandbox-tested updates: `/update`

Before v85, `/update` ran a compile check and a credential-line comparison and nothing else (the self-development path says "No runtime
validation"). Now the candidate is imported **and its regression suite run** in a child process with new mount + network namespaces
(`unshare -m -n`): no network, writes under `/root` discarded (overlay or tmpfs), a minimal environment (no keys). The *running* file is run
the same way, one after the other (not at once, to cap memory), and only **new** failures count, so environment-only failures cancel out.

* **FAIL** (import crash, missing critical functions, timeout 170 s, static reviewer REJECT) → Apply is **not** offered.
  `/updateforce85` then `/update` skips the pre-flight once.
* **WARN** (new failing rows, or the running build could not be compared, or only the static review could run) → shown, Apply still offered.
* If `unshare` is unavailable or less than 600 MB RAM is free, the runtime test is **skipped and the message says so**.
* On this machine the full-file gate takes ≈30 s; a deliberately broken copy is caught (`import-time failure`), and the running file passes
  its own gate. Two bugs in my first version were found by running it for real (see "What testing caught").

## 4. MCP permission tiers: `/mcp85`, `/mcp85 log`, `/mcp85 tier server.tool read|write|blocked`

`MCPClient.call` is wrapped, so **every** caller (`mcp_run`, `/mcp`, other layers) passes the gate. Tier = your override, else: write-ish
words in the name, a `command/script/code` input, or `destructiveHint` → **write**; a read-ish first word (`get_`, `list_`, `search_`,
`fetch_` …) → **read**; anything unknown → **write** (fail closed). A server's own `readOnlyHint` can only *confirm* a read-like name; it
cannot talk a `delete_all` into read. Reads run and their output is prefixed `[untrusted MCP output]`; writes become `mcp_call` cards
showing the tool and exact arguments; URL arguments must pass the SSRF guard (private/loopback/metadata addresses refused); arguments are
size/depth-limited; calls are logged (hash of arguments, never values). Chat (Cortex) gets **read-tier tools only, in round 1 only**, so
tool output cannot steer a second call.

## 5. Document intelligence: send a file with caption `doc` · `/doc85 …` · `doc: <question>`

PDF (needs `pypdf`), DOCX and XLSX (stdlib readers; XML with DTD/entities and oversize members are refused), TXT/MD/CSV/JSON/HTML.
Real pages for PDF, per sheet for XLSX, paragraph groups otherwise. Library of 40 documents, private to your chat.

* `ask`: BM25 retrieval → the model answers **with citations that are verified**: a quote must be in the cited page's text, a number in the
  answer that is not in a quote gets a ⚠️, and if nothing verifies you get the closest *relevant sentences* instead of a guess.
* `risks <id>`: **deterministic** regex scan for late fees, auto-renewal/lock-in, liability/indemnity, exclusivity, unilateral change,
  termination/notice, payment terms, deposits, jurisdiction, with page and the figures; it also lists important clauses *not found*.
  Pattern matching, **not legal advice**.
* `compare <old> <new>`: paragraph diff; changes that touch numbers/dates/amounts or key clauses are listed first, e.g.
  `30 days → 15 days`; added/removed clauses are flagged; wording-only edits are counted separately.
* `tables <id> [csv] [sheet=<name>]`: text-based table detection (≥3 consecutive rows, ≥3 columns); CSV file; optional Sheets card.
* Chat can use it as a read-only `docs` tool ("what does my agreement say about the late fee?").

## 6. Showroom copilot: `/biz85 help`

Leads with follow-up dates, dues with partial payments, stock with reorder levels (never negative; reorder alerts), customers (case-insensitive
dedupe), and a summary. Typed in plain words ("lead: Ramesh wants a 55 inch TV, quoted 62000, call Friday") the model fills a record that code
validates and you confirm on a card; the explicit `/biz85 lead name=… item=…` commands write directly. Customer messages are **drafts only**.

**GST invoice drafts** (`/biz85 invoice new customer=… supply=intra|inter lines="TV x1 @62000 gst18; Mount x2 @1500 gst18 disc100" [gstin=… date=…]`):
exact `Decimal` arithmetic: taxable = qty×rate − discount; tax per line rounded half-up to the paisa; intra-state splits into CGST (half, rounded)
+ SGST (the remainder, so no paisa is lost); inter-state is IGST; the payable is rounded half-up to the rupee with an explicit round-off line;
amount in words in the Indian system (lakh/crore). **The GST rate is mandatory on every line; Nemo never assumes one.** Numbering
`INV/2026-27/0001` per financial year; GSTIN format-checked; `issue … stock=yes` reduces stock all-or-nothing. This is a **draft for your
accountant's rules**: no HSN master, no e-invoice IRN/QR, no e-way bill.

## 7. Watchers: `/watch85 …` · `watch: <link> tell me when it drops below 49999`

`price` (target or % drop; structured data/meta tags first, `near="Deal price"` picks the amount right after that label), `stock`
(schema.org availability or page wording), `keyword` (appears/disappears), `change` (≥ a fraction of the text changed; optional ignore-numbers).
The first check only sets the **baseline**; alerts are **edge-triggered** (a price that stays below target alerts once; it re-arms after a
recovery), with a 3-hour cooldown per watcher. Polite by construction: `robots.txt` honoured (refused at creation, stopped if it changes),
one fetch per host per minute, 3 checks per 30-second tick, 30–1440 min intervals, ≤15 watchers, failures back off (×2 up to ×8) and pause
after 5 with a message. The URL always comes from *your* text (the model is not even shown it) and passes the SSRF guard on every fetch.

## What was verified, and how

* **Tests**: see the table at the end. v85 adds 240+ behavioural tests with expectations computed independently (hand-itemised GST,
  hand-built zips/PDF, scripted providers, concurrent taps, real sandbox runs); v83 (76) and v84 (109) suites still pass unchanged apart from
  three version assertions made version-agnostic.
* **Mutation checks**: deleting the atomic claim, the owner check, the expiry check, or the sandbox isolation each makes the matching tests
  fail (so the tests have teeth).
* **Structural tests on the code itself** (AST): no broker/order identifiers; no `eval/exec/pickle/shell=`; `subprocess` only in the sandbox
  runner; `requests` only in the two audited fetchers, with the SSRF guard before the request on every hop and redirects followed by hand;
  `send_email`, `gcal_add`, `sheet_log`, `_n38_add`, reminder/to-do writes and MCP calls only inside their approved executors; no credential
  variables read; no secret-like literals.
* **No extra model calls** on existing paths (the same 7-message benchmark as v84: identical call counts); non-matching messages cost <1 ms
  of dispatch each; import time +0.2 s.
* **Credentials unchanged**: `_update_cred_changes` against both v82 and v84 reports 0 changed / 0 removed; no secret patterns in the file.

### What testing caught (all fixed before release)
1. **Watchers could never have run**: the watcher record omitted `chat_id`, so every check raised `KeyError`. Found by the lifecycle tests.
2. The sandbox gate hid `pip --user` packages (so `requests` failed to import in the child) and two runs shared one overlay directory
   (spurious "64 failing checks"). Found by running the gate on the real file; fixed with per-process overlays and `PYTHONPATH`.
3. Price `near="Deal price"` picked the *earlier* MRP; it now prefers the amount right after the label.
4. Long-text change detection compared a 20,000-character baseline with the full new page and would always alert.
5. Document fallbacks cut passages off before the relevant words; tables in line-only text files were torn apart by blank lines.
6. Cosmetic: removed citations left "12 percent ." in audited answers; unused imports/locals cleaned (pyflakes: no new messages vs v84).

## Limits and assumptions (read these)

* **Not tested live**: Telegram, Gmail, Calendar, Sheets, real MCP servers, real shop websites, real search results, or any provider. The
  tests use scripted fakes and mocked HTTP. Expect to tune watcher extraction on your actual product pages (`near=`).
* **DNS rebinding**: every fetch hop is checked (scheme, port, private/loopback/link-local/metadata IPs, DNS) but `requests` resolves again
  when connecting, so a determined rebinding attack is not fully excluded.
* **PDF** needs `pip3 install pypdf --break-system-packages` (scanned PDFs have no text layer; send photos for OCR instead).
* **Sandbox** needs Linux `unshare` and permission to create namespaces (root in a normal VPS is fine). Otherwise it is static-only and says so.
* **Quote checks prove that a page says something, not that it is true.** Clause scans are pattern matching. Invoice drafts use *your* rates.
* **Cost**: Inbox reviews, research, document answers and NL record parsing use the same provider routes/keys as chat (no new keys).

## Deploy / roll back

1. Upload `nemotron_bot.py` to Nemo on Telegram and send `/update`. The new pre-flight runs (≈30–60 s), then the usual **Apply & restart**.
   Tables are created on first use; nothing else to configure. `/rollback` (existing) restores the previous file.
2. Everything is switchable: `/steward85 off` (inbox), `watchers off`, `gate off` (back to the compile-only check), `mcp off` (no tiers),
   `send off` (default). Documents, leads, stock and invoices live in the same SQLite file as Nemo's memory.

## Small edits to existing code (everything else is the new block)

version rows and the docstring prefix (6 lines, as in v84); `_n79_editable` protects `_n85_*`; five new flag defaults; the Cortex tool list,
scout prompt, tool validation and the tool runner gain `docs` and `mcp`; the tool-ish regex gains document words.

## Running the tests

    python -m unittest discover -s tests -p "test_*.py" -t .        # everything (about 1 minute; 427 tests, 1 skipped)
    NEMO_SLOW=1 python -m unittest tests.test_steward85.TestGateOnTheRealFile    # real full-file gate (about 1 minute)

| Suite | Tests |
|---|---|
| `tests/test_cortex83.py` | 76 |
| `tests/test_atlas84.py` | 109 |
| `tests/test_steward85.py` (approval engine, dispatch, research, fetcher, inbox, brief, MCP, update gate) | 117 (one slow test is opt-in) |
| `tests/test_steward85_docs.py` | 39 |
| `tests/test_steward85_biz.py` (GST, showroom, watchers, loop) | 59 |
| `tests/test_steward85_integration.py` (handler chain, rows, structural safety) | 27 |
