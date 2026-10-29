# Nemo v106.0 "Steady": updates that answer, checks that tell the truth

You sent the v105 file, typed `/update`, and Nemo said nothing. You also got three alerts (Gemini quota, Gmail sign-in, voice engine), and asked me to "fix Nemo completely". This release fixes why that happened. It adds no new skills.

Evidence tags used below: **[measured]** = I measured it on the test machine; **[code]** = I read it in the code; **[your screens]** = from your screenshots; **[not verified]** = I could not check it on your server.

## 0. Read this first (the honest version)

* **Why `/update` went quiet [code, measured, your screens].** Your running v103 does its heaviest work **inside the live bot, before it says a word**:
  * it scans the new file with the extra tools (ruff, and vulture twice at about 770 MB each);
  * it builds four complete syntax trees of the 6.5 MB file, about 700 MB and 9 s each on a fast machine, with the rest of Nemo frozen meanwhile;
  * it compiles the file twice in separate processes, with a 40-second limit;
  * it compiles it once more inside the bot (about 470 MB), and once more at Apply.

  Last time this took **4 minutes** before the first message (21:45 → 21:49) and then reported a false "pre-flight FAIL", because the 40-second compile limit ran out. In the 18:49 screenshot, the clock on your laptop shows the same minute you sent `/update`. So Nemo was very likely still working. On your server (often under 400 MB free, swap nearly full), it may also have been stopped for lack of memory. **[not verified]** I can't see your server's log, so I can't tell which.
* **The fix only works once v106 is installed, and v106 has to be installed through v103's old path once.** Section 1 gives the steps that make that one install as light as v103 allows.
* **Built and tested offline.** The child processes in the tests are real (Python compiling and starting files), and the safety net was run against a fake service manager that crash-loops. **Nothing here has run on your server yet**, with real systemd, real Google or real Gemini.
* **No trading change, no credential change, no change to backup, rollback, owner lock, holiday guards or approvals.** Apply still needs your tap, and a backup is still written first.

## 1. Installing v106 through your running v103 (one time)

Do these in order in Telegram:

1. `/forgetdoc`: v103 kept the Nemo file you sent as your "uploaded document" and sends its first 50,000 characters with **every question** you ask (about 12,000 extra words of code per question **[code]**). This stops that today. It most likely adds to your Gemini quota use **[not verified]**.
2. `/server`: look at "available" memory. **If it is under about 1.2 GB, or swap is over 80% used,** restart Nemo first so he starts small: `/sre add nemobot`, then `/sre restart nemobot`, then `/sre approve SRE-…` with the code it shows. Wait a minute and send `/server` again.
3. `/steward85 gate off`: this switches off v103's pre-flight, the part that builds the four syntax trees and gave the false FAIL. You switch it back on in step 7.
4. *(Optional; it shortens the silent minutes)* `remove vulture`. v103 runs vulture twice before its first message. v106 runs it only when 1.5 GB is free. If Nemo says it has nothing called vulture, that's fine.
5. Send the v106 file. Wait for "This looks like a new version of ME (v106.0, I'm on v103.0)", then send `/update` **once**. Then **wait up to 10 minutes and send nothing else**:
   * You may see "🔎 EXTRA CHECKS ON THE NEW FILE".
   * Then "🆕 New version ready … ✓ Passed my compile-check" with **✅ Apply & restart**. While v103 compiles inside itself, it may be slow to answer anything else. v106 fixes that.
6. Tap **✅ Apply & restart**. Within about 2 minutes: "✅ Update to v106.0 booted cleanly - confirmed healthy."
7. `/steward85 gate on`. In v106 this switch only controls the trial start, which now runs outside the bot and only when memory allows. Then send `/steady` to see the new status page.

**If nothing comes within 10 minutes:** send `/version` (still v103?), then `/sre add nemobot` and `/sre logs nemobot 150`, and send me a screenshot. Look for lines with "Killed", "Out of memory" or "oom". If Nemo restarted, he has forgotten the file: send it again and repeat step 5 after step 2. **If anything feels wrong after the update:** `/rollback`.

## 2. What `/update` looks like from v106 on

You send the file and Nemo answers at once: "🆕 Got nemotron_bot.py: v107.0 of me … Send /update to install it". The file is **not** added to your documents or to the library, so it doesn't ride along with your questions. Send it with the caption `update` and the check starts by itself.

`/update` replies at once with **one status message that updates itself**:

| Step | What runs, and where | What you see |
|---|---|---|
| Quick checks | Text checks inside the bot (cheap): is it a complete Nemo file, real version, which key/config lines change (names only, never values) | ✅ or ❌ "not a complete Nemo file: it has no def handle_callback(" |
| Server memory | Read from `/proc/meminfo` | ℹ️ free memory and swap |
| Compile check | **A separate process at the lowest priority, marked as the kernel's first choice to stop if memory runs out** (never the bot). Skipped, with the reason, if less than about 600 MB is free | ✅ compiles (seconds) · ❌ the exact line of the error · ❓ "could not check: only 340 MB of memory is free…" with a **🔁 Check again** button and **no Apply** |
| Trial start | The v85 sandbox (no network, writes thrown away), also lowest priority and first to be stopped. Only when about 900 MB is free; the running version is started for comparison only if the new one has failing self-checks | ✅ started in N s, its self-test results · ❌ crashed while starting (no Apply) · ➖ skipped, and why · ❓ could not finish (Apply still offered: the compile passed) |
| Extra tools | ruff and detect-secrets if installed; vulture only with 1.5 GB free | information lines |
| Apply card | Lists every result, the key changes and the safety net | ✅ Apply & restart · ❌ Cancel |

It shows "⏳ … 45 s" every 30 seconds while a step runs. `/update status` tells where it is. `/update cancel` stops it and the process it started. A second `/update` while one runs gets the status instead of a second check.

**Apply** writes the backup first, as before. It **does not compile the file again**: the result of the check is remembered by the file's fingerprint. `/rollback` checks the backup in a separate process first, and never restores a backup it could not check.

**Safety net (new).** Just before Apply, Nemo starts a small watcher as **its own short-lived systemd service, outside Nemo's service**, so the restart does not stop it. For up to 10 minutes it watches whether the new version keeps crashing at start: the service fails, or restarts twice by itself. If it does, the watcher checks that the backup is exactly the recorded previous version and that it compiles. Then it puts it back, restarts Nemo, and Nemo tells you when he is back. It does nothing when:
* the update booted (`booted cleanly`);
* the file on disk is not the update;
* the backup does not match or does not compile.

It leaves a log in `nemo_update_guard.log` next to Nemo's file. It only works when the restart command is `systemctl restart <service>` and `systemd-run` exists; `/steady` says whether it is ready. The old automatic roll-back code lives **inside the new file**, so it cannot help when that file fails to load. That is why the watcher lives outside.

## 3. Your three alerts

| Alert | What it really was | What v106 does | What you do |
|---|---|---|---|
| **Voice engine (TTS): empty/false response, 9 in a row** | A false alarm **[code]**. The check looked for functions called `tts` or `voice_reply`, which do not exist (Nemo's voice is `speak`, with edge-tts and gTTS), so it could never pass | Checks the real path: the reply function, an installed engine, and a real two-word synthesis at most every 6 hours | Nothing |
| **Backup brain (Gemini): rate limit/quota, 9 in a row** | Real, but not a fault: the free allowance was used up. The check itself made **up to 6 real requests** every run, and the idle self-improvement loop ran a full health check **every 30 minutes** (up to 24 times a day) **[code]**. The old file-as-document problem (section 1, step 1) likely added to it **[not verified]** | At most 2 requests per check, none while the allowance is used up (it rests until Google's daily reset at midnight Pacific time, about 12:30 pm India time until 1 November and 1:30 pm after, at most 3 hours at a time). The idle loop reuses a health check up to 3 hours old. A used-up allowance is no longer an alert; it shows as a note | Nothing; or add billing in Google AI Studio if you want more Gemini |
| **Email sending: Google OAuth token refresh failed, 2 in a row** | Real. Google refused Nemo's saved sign-in. The old code threw away Google's reason. The most common cause **for a personal Google Cloud app is "Testing" mode: Google ends those sign-ins after 7 days** | Keeps Google's own words (for example "invalid_grant: Token has been expired or revoked") and when you last signed in. If it was about 7 days, it says it's the Testing limit. It stops asking Google again for 10 minutes after a refusal | **`/google` and sign in again.** If it ends again after about 7 days: Google Cloud Console → your project → Google Auth Platform → Audience (older screens: APIs & Services → OAuth consent screen) → **Publish app**, so it says "In production". Then `/google` once more: a sign-in made while the app was in Testing still ends after 7 days. Ask Nemo `gmail status` any time |

Alerts are now in plain words with "What to do". The old line "run /doctor … then a focused /drill before changing production code" is gone.

## 4. Other things that made Nemo freeze, now fixed

* `/doctor`, the nightly doctor, `/prime`, `/regress` and two self-audit tools read Nemo's **own** source by building a full syntax tree inside the bot (about 700 MB, everything frozen). They only needed the function names, so they now use a line scan (0.1 s). On the v106 file, the scan finds every function a full parse finds; it also counts 38 `def` lines that sit inside long text templates, which is harmless here **[measured]**.
* **Evaluation Lab** (`/eval`, `/prime`): reads the real version (it used to read the first `VERSION` line, 27.0, so every update warned "same version"). Compiles in the separate process, once per file. A check that couldn't run is "NOT CHECKED (why)", not "FAIL", and doesn't cost 45 points. The running v106 file now scores 96/100; before, every big file scored about 43 because of the false compile failure **[measured]**.
* `/updatecheck` and `/rollback` no longer block Nemo's message loop while they check.
* Old check folders left behind by a crash are cleaned up a day later.

## 5. Commands

| You say | What happens |
|---|---|
| Send the file (optionally with the caption `update`) · `/update` | Section 2 |
| `/update status` · `/update cancel` | Where the check is · stop it (nothing changes) |
| `/steady` | Update status, free memory, trial start on/off, safety net ready or not, Google sign-in, Gemini resting or not, voice |
| `gmail status` · `why is gmail failing` | Google's reason and the fix |
| `/eval` | Evaluation Lab for the running file, with "NOT CHECKED (why)" when it could not compile-check |
| `/updateforce85` then `/update` | Skip the trial start once (the compile check always runs) |
| `/steward85 gate off` / `on` | Trial start off/on |

## 6. Verified and not verified

| Claim | Status |
|---|---|
| The compile check runs in a separate process; the bot's memory stays flat while it checks the 6.6 MB file (504 MB before and after; the child took 6 s) | **[measured]** on the test machine |
| The child and the trial start are marked as the kernel's first choice to stop (`oom_score_adj` 1000) and run at the lowest priority | **[measured]** (tests read the value back from inside the child) |
| A crash-looping or failed service is rolled back by the watcher; a healthy one, a confirmed update, a backup that doesn't match or doesn't compile are left alone | **[measured]** with a fake `systemctl` |
| `systemd-run` starts the watcher outside Nemo's service on your server | **[not verified]**: standard systemd behaviour, but not run here |
| Google's 7-day limit for "Testing" apps | Secondary sources agree; not checked against Google's current page **[not verified]** |
| Gemini daily limits reset at midnight Pacific time | Google's rate-limit page, as quoted by the search tool **[not verified]** by me directly |
| Your server stopped v103 for lack of memory at 18:49 | **[not verified]**: the logs in section 1 would show it |
| Your Gemini quota was used up partly by the Nemo file riding along with questions | **[not verified]**; the riding along itself is **[code]** |

## 7. Sources

* Google, Gemini API rate limits: https://ai.google.dev/gemini-api/docs/rate-limits ("requests per day … reset at midnight Pacific time"; limits are per project).
* Refresh tokens and the 7-day limit for apps in Testing (secondary write-ups of Google's OAuth documentation): https://www.nango.dev/blog/google-oauth-invalid-grant-token-has-been-expired-or-revoked , https://workos.com/blog/invalid-grant-oauth-errors-by-provider
* Linux `oom_score_adj` (a process may raise its own value to 1000 to be chosen first): the proc(5) manual page.

## 8. Test results (offline, on the test machine)

- **New tests: 83** in `tests/test_steady106.py`, all passing. They use real child processes: Python compiling a file, and the trial runner starting a file. The safety-net watcher is run as a real script against a fake `systemctl` that crash-loops, fails or stays healthy.
- **`/update` end to end on the real 6.6 MB file** (the v106 file checking itself; the trial start in the real sandbox; test machine with plenty of memory):

  | | v103 (what you run now) | v106 |
  |---|---|---|
  | First message | at once (with the extra tools installed, as on your server: after the tools finish, which took 4 minutes for you) | at once, always |
  | Bot's own memory during the check | +382 MB (peak 832 MB) | **+25 MB** (peak 136 MB) |
  | Heavy work inside the bot | 4 full syntax trees, 1 compile; Apply compiles again | none; Apply uses the remembered result |
  | Whole check | 50 s | 29 s (compile 2 s, trial start 26 s) |
  | Version it reports | "candidate 27.0" (wrong) | v106.0 |

  On your server it will be slower. The point is that the slow part now runs outside the bot, at the lowest priority, and is the first thing the kernel stops if memory runs out.
- **Deliberate bugs:** I planted 27 bugs, one at a time. **The tests failed for every one.** The bugs were:
  * the old in-bot pre-flight comes back;
  * a big file is compiled inside the bot;
  * "not checked" is reported as "does not compile";
  * Apply is offered for an unchecked file;
  * the compile process, or the trial start, is not the kernel's first to stop;
  * no memory guard before compiling, or before the trial;
  * the force-skip is not one-shot;
  * the compile result is not remembered;
  * the Evaluation Lab's false FAIL, or its first-VERSION reading, comes back;
  * a full syntax tree of the own file is built inside the bot;
  * the safety net restores any backup, ignores a confirmed boot, or rolls back a healthy service;
  * Apply runs without the safety net;
  * the voice false alarm comes back;
  * the Gemini check makes six requests, or re-tests while resting;
  * a refused Google sign-in is asked again at once;
  * a Nemo file is read as a document, or a copy of Nemo is sent with every question;
  * a used-up Gemini allowance alerts as a fault;
  * a cancel is not recorded;
  * `/rollback` restores an unchecked backup;
  * the library keeps copies of Nemo.
- **Bugs the tests caught while I built this, both fixed:**
  * `/update cancel` was reported as "the server stopped the check (out of memory)" instead of "stopped by you";
  * the safety net would not have recognised an update saved with Windows line endings, so it would have stood down without acting.
- **Pyflakes:** the same 158 messages as v105, none new.
- **Whole suite on the exact file delivered (the slow gate switched on): 3,713 tests, 7 skipped, 1 failure, 0 errors; the failure is fixed.** It was v105's version test, which asked for exactly 105.0. It now asks for 105.0 or later, as v104's did last time, and the v105 test file passes again (84 tests). The file itself did not change.
- Nothing here placed or changed an order, called a cloud AI, Google or Gemini, used a paid service, or touched a real systemd.

## 9. What changed in older code (everything else is in the new layer, marker `# NEMO 106 - STEADY`)

* **Changed lines in older code:** the docstring's first line, and the protected-names list for live self-edit (`_n106_` added).
* **Wrapped by the layer:**
  * update path: `_compile_check` (only for code over 1 MB), `self_update`, `apply_self_upgrade`, `self_rollback`;
  * Evaluation Lab: `prime_eval_file`, `prime_eval_deep`, `prime_eval_compare`;
  * health and alerts: `_health_probe` (voice only), `gemini_probe_diagnostic`, `prime_health_run` (reuse from the idle loop only), `_v136_proactive_signal`;
  * Google: `google_token`, `google_exchange`, `_email_api_health`;
  * uploads: `handle_document`, `lib_save`, `build_system`;
  * entry points: `handle`, `handle_callback`, `prime_regression_suite`, `main`.
* **Redirected:** the names `_prime_ast`, `_v180_ast` and `_n52_ast` now point to a stand-in that uses the real parser for everything except a source over 1 MB.
* **Still in the chain:** the v85 pre-flight and the v92 extra checks are behind the new `/update`. Their tests now call them there (two older test files changed for that).
* **Older tests:** v105's version test now accepts later versions.
