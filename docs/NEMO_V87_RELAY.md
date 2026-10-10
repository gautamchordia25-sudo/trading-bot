# Nemo v87.0 "Relay": more video sources, one verified chain, a Drive link you can open

You asked for YouTube downloads that work, with more sources, saved to Google Drive and a link you can open.
Everything from v86 (Candor) and earlier is kept; credentials, the owner lock, the trading guards, permissions, backup and rollback are untouched
(credential check against v86: 0 changed, 0 removed).

## 1. What was wrong (found by reading the v76–v78 download path)

I do **not** have access to your VPS and my test machine cannot reach YouTube, so I could not reproduce your exact failure. What the code review did show:

1. **One source only.** Every "download <link>" goes through the v78 queue → v77 `_n77_media`, which only ever ran **yt-dlp**. The independent engines built in v59–v62 (pytubefix, YouTube.js, Piped/Invidious mirrors, Cobalt) were no longer reached by that path.
2. **yt-dlp was never refreshed** (YouTube changes weekly), only the default client profile was tried, Node.js was ignored when Deno was missing, the solver package (EJS) had no fallback, your `/proxy` was ignored, and a missing `bv*[height<=N]` format ended the job instead of falling back.
3. **Failures said almost nothing.** The job card read "The source returned a sign-in/session rejection… Diagnose YouTube before resuming" — no source, no reason per source, no next step.
4. **The Drive link was private by design** ("restricted link"): a link you cannot open was reported as success.

## 2. What v87 does

A **source chain**, each source verified (ffprobe: a real video/audio stream with a duration) and time-boxed, in this order:

| # | Source | Needs | Helps when |
|---|---|---|---|
| 1–6 | **yt-dlp**, six client profiles: default · TV · embedded player · VR · web/mobile-web · iOS (Deno and/or Node.js 20+, your cookies, your proxy; H.264/AAC mp4 up to the quality you asked, falling back instead of failing) | yt-dlp in the bot's Python | normal case; different profiles dodge different YouTube blocks |
| auto | **yt-dlp update** (stable, then nightly if unchanged), once per 6 h, then the default profile is retried | pip | the page "could not be read", format missing, JS challenge failed (not for a bot check — a newer yt-dlp cannot fix that) |
| 7 | **pytubefix** (isolated worker process, 6 client names, merges adaptive streams with ffmpeg) | `pytubefix` | yt-dlp is broken but another library still works |
| 8 | **YouTube.js** (InnerTube via Node) | Node.js + `youtubei.js` | same, different implementation |
| 9 | **Piped mirrors** | public instances reachable | server IP distrusted by YouTube but mirrors proxy the stream |
| 10 | **Invidious mirrors** | same | same |
| 11 | **Cobalt server** | one you configure (optional) | your own Cobalt instance |

* The source that **worked last is tried first** next time (within 3 days).
* A **definitive answer** (DRM, private video, live/premiere not available) stops the chain at once — other sources cannot change it. "Video unavailable" does *not* stop it (another client may still work).
* **Every failure is classified** (bot check, rejected cookies, age gate, PO token, JS challenge, out-of-date yt-dlp, rate limit, region block, no format, disk full, timeout, …) and the failed job card lists **each source with its reason**, the most likely cause, and **what to do** (e.g. `/cookies`, `/proxy set <url>`, "set up download sources"). Links, file paths and cookie names are never shown.
* The same extractor, queue, size/disk guards, cancellation, resume and Drive resumable upload (with MD5 verification) from v76–v78 are used. One download at a time; overall limit is your existing `media_timeout` (900 s).
* More video sites are accepted by the download manager: Rumble, Odysee, Streamable, Imgur, Mixcloud, Bandcamp, TED, Pinterest, Threads, Bluesky, VK, OK.ru, BitChute, Niconico, Loom, YouTube-nocookie.

**Drive links.** Each finished download is shared as **"anyone with the link can view"** (not searchable), and Google must confirm the permission before Nemo says so. If Google refuses (some accounts/organisations block public links) the file is still saved, the card says sharing could not be enabled, and the link stays private. **This changes the old default from private.** Switch any time: "keep my download links private", "share my downloads with name@gmail.com" (that account only, no e-mail sent), or "make my download links public". "share my last download" opens the latest file even in private mode.

## 3. Controls (say these to Nemo; owner, private chat only)

| Say | Result |
|---|---|
| `download sources` | yt-dlp version, JavaScript runtime, solver, cookies, proxy, ffmpeg, the order of sources with their record (worked/failed counts), Drive binding, link sharing, last attempt |
| `test youtube download` | live proof: fetches YouTube's first video (19 s) through the whole chain into a temporary folder, checks it, **deletes it, no Drive upload**, and lists every source that failed first (up to ≈3 min) |
| `set up download sources` / `update yt-dlp` | updates yt-dlp with its extras in the bot's own Python, installs pytubefix, installs YouTube.js with npm if Node exists, installs Deno **only if there is no Node 20+/Deno** (official installer script from deno.land — said before it runs); installer output is never shown |
| `download https://youtu.be/… [720p] [mp3]` | the usual flow, now through the chain; card shows `Source: …` and the link note |
| `make my download links public` / `keep my download links private` / `share my downloads with a@b.com` / `who can open my download links?` | sharing mode |
| `share my last download` | link anyone can open for the latest finished download |

If YouTube still refuses everything, the report will usually say one of: **bot check** → send a `cookies.txt` (say `/cookies` for the 3 steps) or set your own proxy (`/proxy set <url>`); **JavaScript challenge / outdated** → "set up download sources"; **age-restricted** → cookies; **rate limit** → wait or proxy. If every source says "bot check", YouTube is distrusting this server's IP, and no software choice fixes that without cookies or a proxy.

## 4. Tests actually run

All offline: tiny synthetic videos made with ffmpeg, a **fake yt-dlp executable** with scripted behaviours (success, bot check, no format, private, silent stall, never-ending, unmerged leftover, junk file, partial playlist), a stub pytubefix package, a local HTTP server for the mirror downloads (including redirects to private addresses), a fake Drive permissions API, temporary folders and databases. **No YouTube, no Drive, no AI calls, no trades, no paid APIs.**

| Suite | Tests | Result |
|---|---|---|
| v83 Cortex · v84 Atlas · v85 Steward · v86 Candor | 571 | pass (2 v86 structural tests now stop at the v87 layer marker) |
| **v87 Relay** (`tests/test_relay87.py`) | 147 | pass |
| **Total** | **718** | **OK** (1 slow test skipped by default) |
| Slow gate: v85 sandbox update gate run on the real v87 file | 1 | pass (73 s) |

Relay tests cover: classification table (23 real-looking messages) and safe text; the generated yt-dlp command (every mode and client profile) **accepted by the installed real yt-dlp 2026.8.19** and every client name checked against its client list; one attempt against the fake yt-dlp (success, classification, stall, attempt cap, process killed, unmerged leftovers, junk file removed, playlist warning, cancel); the video check on real files; the chain (order, first success wins, definitive answers, raised exceptions, empty successes, cancellation, environment limits, time limit, preference ledger and its expiry, rejected cookies, progress, failure text with no links/paths); automatic update (when, once, cool-down, not for a bot check, pip form, nightly fallback); pytubefix via the stub (merge, progressive, audio/mp3, client fallback, missing package, symlinked worker, hung worker); mirrors/Cobalt/YouTube.js and the fetcher (HTML pages, 403, tiny files, size limit, cancel, redirects checked before they are requested); the front door (cookie copy deleted, lock released, symlinked folder, extended host list); Drive sharing against the fake permissions API (default link, idempotent, Google not confirming, refusal, private, one account, share-last); the whole job end to end (queue → chain → verify → upload → shared link → card), including **the real step list with a fake yt-dlp executable** that only lets the "embedded player" profile through, and the update-then-retry path; the natural-language controls (phrasing tables, 16 look-alike sentences that must *not* be hijacked, owner-only); the self-test and set-up reports; structural checks (no shell/eval, no secrets, directory removal only in the self-test's own temp folder, cookie copying only in two places); and **mutation checks** — remove the classification, the video check, the failure-text cleaning, the ledger, the definitive classes, the update rule, the extra sources, the Google confirmation, or trust redirects, and the matching test goes red (all do).

Other gates: `py_compile` OK; pyflakes 158 findings in v86 and the same 158 in v87; secret-pattern scan of the diff clean; `_update_cred_changes` v86→v87: no changed or removed credentials. Diff outside the appended layer is limited to `_n77_command`, `_n77_media`, `_n76_archive`, `_n78_work_once` (one branch), the host list, the version/doc line and the self-edit protection prefix.

Same scenario on both files (fake yt-dlp where only the embedded-player profile gets through): v86 → **FAILED**, one attempt, "…Diagnose YouTube before resuming"; v87 → **DONE** after three profiles, `Source: yt-dlp · embedded player`, shared link. *This is a simulation of the mechanics, not a claim that YouTube lets any profile through.*

## 5. Offline-tested vs not verified live

**Offline-tested:** everything listed above, plus the yt-dlp command line against the real yt-dlp's option parser.

**Not verified live — treat as unproven until you run "test youtube download":**
* That any source actually gets a video from YouTube **from your VPS**. My machine cannot reach YouTube, so no real YouTube request was made; whether it works depends on your server's IP, cookies, yt-dlp/Deno/Node versions and YouTube's current defences.
* The real pytubefix API (tested against a stub; I installed the real package in my sandbox only to read its client names), YouTube.js, the public Piped/Invidious instances (often unreliable or dead), and Cobalt.
* The Drive permission call on your Google account (a fake API was used): Workspace/organisation policies can forbid public links.
* The yt-dlp self-update and the Deno installer on your server, and the new yt-dlp options on whatever yt-dlp version is installed there (a too-old yt-dlp is recognised and updated, but that path was only simulated).
* Telegram message flow. No live trades and no paid API tests were run.

## 6. Privacy, limits and rules

* Piped/Invidious mirrors learn which video ID you asked for and your server's IP; no cookies or credentials are sent to them. Turn them off with `media_public_resolvers` = `0` in `bot_secrets.json`/environment (existing switch).
* Nemo does not bypass DRM, private/members-only videos, paywalls, CAPTCHAs, or age/login gates except with **your own** session cookies or proxy. YouTube's terms generally do not allow downloading except through features it offers; use this for content you have the right to download.
* "Anyone with the link" means exactly that for whoever receives the link; switch to private or one account if that is not what you want.
* `/ytdl`, `/dl`, `/video`, `/ytmp3` keep using the older Telegram-delivery engine; the Drive path is the natural-language "download <link>".

## 7. Installing and rolling back

Upload `nemotron_bot.py` to Nemo on Telegram and send `/update` (v85 pre-flight: compile, credential comparison, sandbox import and regression run), then **Apply & restart**; `/rollback` restores the previous file. Nothing else to configure. Then, in this order: `download sources` → `set up download sources` (if it reports a missing runtime/package) → `test youtube download` → `download <your link>`.
