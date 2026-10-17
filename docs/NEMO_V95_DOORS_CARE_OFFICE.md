# Nemo v95: Doors + Care + Office

One release, one file (`nemotron_bot.py`, version 95.0). It follows from the audit in `NEMO_NEXT_POWERS.md` (the website's seven weaknesses), from what the owner's own screens showed (a cryptic Trade Lab stop, leftover processes), and from what the showroom needs (invoices).

1. **Doors**: the website gets Telegram login, a limit on guessed keys, safe headers and constant-time key checks. Every new protection that could lock the owner out is a switch with a guard.
2. **Care**: `care` reads the server and Nemo's own state and says what to do; `care clean` and a daily housekeeping step remove only Nemo's own leftovers; failure messages from **older** functions gain a fix-it line; `fyers login` is one phrase.
3. **Office**: GSTIN and PAN checks (and a tax-type check) on invoice drafts; a study helper with spaced repetition.

Nothing in v95 places, changes or simulates an order. It does not touch the trading agent, the trading guards (including the holiday guard) or the owner lock. The Telegram token is used only to *check* a signature and is never sent anywhere. Everything is owner-only.

---

## 1. Doors: the website

### The seven weaknesses from the audit, and what happened to each

| # | Weakness (v94 and earlier) | v95 |
|---|---|---|
| 1 | One 12-character key (48 bits), sent **in the address** (`?k=…`) | New keys are 128 bits (`doors rotate` makes one now). **Telegram login** removes the key from the address; `doors strict on` then refuses keys in the address. Every reply carries `Referrer-Policy: no-referrer`, so a key in an address can no longer leak to another site. |
| 2 | Key compared with `==`; no limit on guessing | Constant-time comparison everywhere (the website, the Twilio/TradingView/device paths and the outside-services gateway). **12 different wrong keys in 10 minutes block that address for 15 minutes**; at most 240 requests a minute per address. A page left open with one old key repeats the *same* wrong key and does **not** count (I found and fixed this self-lockout while reviewing: the Cockpit page asks every 10 seconds). |
| 3 | Fallback key "nemo" if none were set | Unchanged (a key is always created at start-up); the report names a short key. |
| 4 | Flask's development server on every network address | Same by default (so nothing stops working). **`doors lock on`** makes it listen on this server only (applies at the next restart); **waitress** (production server) is used automatically when installed. |
| 5 | Plain-`http` cockpit link with the key when no public address is set | Reported by `doors` ("none set … plain http ⚠️") with the step to fix it. |
| 6 | Quick-tunnel address changes | Not changed (needs a named tunnel or Tailscale: still open, roadmap A3). |
| 7 | Telegram's own proof of who you are was not used | **Telegram login**: the app button opens `/app`, which sends Telegram's signed `initData`; Nemo checks the signature (HMAC-SHA256 with a key made from the bot token, as Telegram documents), the age (under 24 h) and that the user is **you**; then sets a 12-hour `HttpOnly`, `SameSite=Strict` cookie (`Secure` behind https). Anyone else, even with a genuine Telegram signature, is refused. |

The checks apply to **every** route, including the ones other versions added (voice, devices, webhooks), because they are hooks on the whole site, not edits to each route.

### Switches (say them to Nemo; owner only)

- `doors`: who can get in, in plain words, and the next steps I suggest.
- `doors telegram on|off`: needs an https address; moves the app button to `/app`. Keys in the address keep working until you turn strict on.
- `doors strict on|off`: refuses keys in the address. **Refused until Telegram login is on**, so you cannot lock yourself out. If you ever lose access, `doors strict off` in Telegram undoes it.
- `doors lock on|off`: listen on this server only (tunnel and Tailscale keep working). With no public address set it asks for `doors lock on confirm`, because the direct address would be the only way in.
- `doors rotate`: a new 128-bit key; old links and Telegram logins stop (`/connect` gives the new links).
- `doors logout`: end the website's Telegram logins.

**Suggested order:** `doors` → (if the key is short) `doors rotate` → `doors telegram on` → open the Cockpit from the app button and check it loads → `doors strict on` → `doors lock on` if you use a tunnel.

---

## 2. Care

`care` (also "housekeeping", "server care"):

```
🩺 NEMO CARE: how the server and I are doing

✅ Disk: 40.0 GB free of 77.0 GB (52%)
✅ Memory: 2.1 GB available · not swapping now
✅ Nemo’s database: quick check ok · 12 MB
⚠️ Leftover job folders: 1 older than 30 minutes (2 MB): say “care clean”
✅ Old scratch files: none
✅ Backups: last one 2 h ago · OK · daily on
✅ Fyers: logged in today
⚠️ Website: short key, no Telegram login · say “doors”
Housekeeping: automatic, about 03:30 every day …
```

- **Backups** are read from the existing v68 continuity table (last backup, status, off-site copy, daily switch); the report says when there is no off-site copy.
- **`care clean`** removes only: helper-program job folders (`J92-…`, older than 30 minutes, through that runner's own safe remover), and scratch pictures/audio/PDFs in the temp folder whose names match `nemo_<name>.<png|jpg|pdf|mp3|mp4|wav|ogg|webm>` and are older than 3 days (plain files only, never links). It also compacts the database log. Nothing else.
- **Daily housekeeping** (about 03:30 IST): the job-folder part and the log compaction only; silent unless it freed 50 MB or more. `care auto off` stops it.
- **Low-disk alert** (under 2 GB or under 10%): one message a day. `care alerts off` stops it.

### Fix-it lines on older failures (improves previous functions)

Three rules, each one tested against the real wording in the source (so a rewording elsewhere cannot silently break a rule):

| The older message says | Nemo adds |
|---|---|
| "Fyers market-data request failed; check broker login" (the Trade Lab stop), "Connect Fyers first", "Broker not logged in", "FYERS is not connected", "Fyers returned no usable market data" | Fix: Fyers is not logged in today; say “fyers login”, or send /brokerurl; Nemo also logs in at 8:20 AM. (Not added when the message already names a fix.) |
| "No module named 'x'" | Fix: say “install x into yourself” (using the right PyPI name) |
| "No space left on device" | Fix: say “care”, then “care clean” |

`fyers login` / `connect fyers` / `broker login` runs the existing `/brokerlogin` (the same login as 8:20 AM); `fyers status` runs `/broker`.

---

## 3. Office

- **`gstin check 27AAPFU0939F1ZV`**: checks the length, the layout, the state code, the PAN inside it, the letter Z and the **check character** (Luhn mod 36). A mistyped character is named ("it should be V"). It does not prove the business is registered: look it up on the GST portal.
- **`pan check ABCPD1234E`**: layout and holder type.
- **Invoice drafts** (`/biz85 invoice …`, chat text and PDF) now end with a note: customer GSTIN valid or not; and, once you say **`my gstin <yours>`**, whether the tax type fits the two states ("your GSTIN is in Gujarat and the customer's in Maharashtra: this is normally inter-state (IGST), but the draft says CGST+SGST").
- **Study helper**: `card add Question | Answer` (optionally `deck=name`), `make cards from: <your text>` (the AI proposes up to 12 cards from *your* text; only well-formed short pairs are kept; you can delete any), `quiz me` → question → `show` → `again|hard|good|easy` (or 1–4), `skip`, `stop quiz`, `my cards`, `delete card 3`. Spacing: again = 10 minutes, then 1 day, 3 days, then growing by the card's ease (a simple SM-2 style rule), capped at a year.

---

## 4. What was verified, and what was not

**Verified offline (automated tests):**
- the website hooks on a real Flask app (headers, blocking, per-address counting, forged forwarded headers, rate limit, strict mode, login/logout, cookie flags, non-owner refusal) and the Telegram signature check against an independent copy of the documented algorithm (tamper, wrong bot, old/future login, duplicated fields);
- the GSTIN rule: 25 numbers made and validated with the python-stdnum library, 9 near-misses it rejects, every single-character error caught, and (when written) 30,000 random strings compared with stdnum's Luhn mod-36: no differences;
- the care report with scripted memory/disk, real temporary files, the safety of `care clean` (links, wrong names, young files, folders outside the work area), the daily step's clock logic, and each fix-it rule against the real source wording;
- invoice notes on real drafts (also in the PDF), the quiz flow, scheduling maths, AI card parsing with scripted answers.

**Not verified live (cannot be from the test machine):**
- **Telegram's real `initData`** was never produced by a real Telegram client here; the check matches the documented algorithm and my independent copy of it. **Whether your Telegram app's web view keeps the login cookie** is unknown. If the app button shows "Not allowed" or loops, say `doors telegram off` and the old link works again.
- **waitress and `doors lock on`** were tested with stand-ins, not on your server.
- **A real chat with the quiz and a real AI making cards** were tested with scripts.

## 5. Try it, through Nemo

1. `doors`, then `care`.
2. `gstin check 27AAPFU0939F1ZV` → valid; `gstin check 27AAPFU0939F1ZO` → "it should be V".
3. `my gstin <your GSTIN>`, then make a draft invoice for a customer in another state with `supply=intra`: the draft warns.
4. `card add What is PCR? | Open puts divided by open calls`, `quiz me`, `show`, `good`.
5. `fyers login` when Trade Lab says check broker login.
6. Website steps in section 1, one at a time.

## 6. What changed in older code (everything else is in the new layer, marker `# NEMO 95 - DOORS`)

1. The docstring, `VERSION`, and `'_n95_'` in the live-self-edit protection list.
2. The website: `ok_tok` asks one function who the owner is; the four webhook paths, the device-grid key and the gateway key use the constant-time comparison; the server starts through `_n95_serve` (same server and address unless you switched them); new keys are `token_hex(16)`; the app button address follows the Telegram-login switch (two small edits).
3. Replaced or wrapped (old ones kept): `build_web_app`, `send_text`, `_n85_invoice_text`, `handle`, `main`, status/capabilities/abilities/regression.
4. **A bug in an older function, found by the full suite and fixed:** the "what can you do" report (v88) cut itself at 3,900 characters. With the rows added by v93–v95 it had grown past that, so its last lines ("To fix: …" and the read-only/approval line) were being cut off. It now shortens long details, then drops the examples of working rows from the end (never of rows that need attention), so every row and the ending stay in one message (`_n95_fit_report`; six tests).

Tests: `tests/test_doors95.py`, `tests/test_care95.py`, `tests/test_office95.py` (Flask tests skip themselves when Flask is not installed). The v94 structural tests now stop at the v95 marker.

## 7. Test results (offline, on the test machine)

- **Whole suite: 2,262 tests, 0 failures, 6 skipped** (the slow gate switched on). 179 of them are new for v95 (`test_doors95`, `test_care95`, `test_office95`).
- The first full run found **one failure**, the old "what can you do" report losing its ending (section 6, item 4). It was fixed in the code, six tests were added, and the whole suite was run again from the start: that second run is the result above.
- Pyflakes: the same 158 messages as v94, none new. Credential comparison against v94: no change to any saved credential. A scan of the added lines for keys, tokens or passwords found none.
- Nothing here placed, changed or simulated an order, called a broker, or used a paid service.
