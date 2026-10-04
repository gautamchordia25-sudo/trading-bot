# Nemo v89.0 "Circle": a menu for who else may use Nemo, and what each person may do

You asked for a control menu, so that when a family member uses Nemo you decide which abilities they can use and which they cannot.
Everything from v88 (Argus) and earlier is kept. Your own chat, commands, credentials, approvals, the trading guards, backup and rollback are untouched
(credential check against v88: 0 changed, 0 removed).

## 1. What I found first (by testing, not by guessing)

I sent more than 50 different messages, buttons, photos, files, voice notes and group messages from a guest and from a family member to the real v88 file:

* **Good:** nothing of yours was reachable. Mail, calendar, Drive, trading, the server, memory, devices and the activity log never answered a non-owner, and a guest's or family member's AI prompt contained none of your library, facts, history or lessons (I seeded fake secrets and checked the prompt).
* **But it was all-or-nothing, and some things were rough:**
  1. There was nothing to switch. Family could chat, guests could chat, and that was it. No per-person view, no limits you could change, no usage.
  2. **You could not turn strangers away.** Anyone who found the bot could chat with it (25 answers a day) on your AI credits.
  3. The v42 family promises, `/remind` and `/todo`, were **blocked by later layers** ("That command is owner-only"), so family members could not actually set reminders.
  4. **Any button press from anyone was passed on** to the older callback code. None of it exposed anything in my tests, but several old handlers had no owner check of their own (one even answered a stranger with "that trade ticket expired").
  5. **Inline queries** (`@yourbot question`, only if inline mode is on in BotFather) were answered for everyone with no daily cap.
  6. Voice notes and pictures used shared temporary file names (`/tmp/in.oga`, `/tmp/tgimg.jpg`), so two people at the same moment could swap files.
  7. The v88 `see` tool had no owner check of its own. Nobody else could reach it, but it now refuses anyone but you anyway.

## 2. What v89 does

**One gate in front of everything that is not from you** (messages, button presses, inline queries). It is **default deny**: what a non-owner sends is handled only by this layer, and nothing reaches the older layers except plain, non-addressed group chatter (which the old code only logs). If anything breaks inside the gate, the message is dropped, never passed on.

### The menu: `/circle` (or say "family access")

| Page | What you do there |
|---|---|
| 🛡 **Home** | counts (family, guests, blocked), strangers on/off, today's use |
| 👥 **People** | everyone who wrote to Nemo; tap a person for their page |
| **Person page** | one tap per ability: ✅ on / ⛔ off / 🔒 not available ("·own" = you set it for this person); ↺ use the role rules; make Family/Guest; Block/Unblock; Forget |
| 👨‍👩‍👧 **Family rules** / 🙋 **Guest rules** | what every family member / every guest (and stranger) gets by default |
| ⚙️ **Limits & strangers** | strangers on/off; answers and "special requests" per person per day, for family and for guests (− / +); new-person cards on/off |
| 📊 **Today** | who used what, and what they asked for that was off |
| 🔒 **Only you** | the list that can never be granted |

**Priority:** a rule you set for a person beats the family/guest rule, which beats the built-in default.

### The abilities (10) and their defaults

| Ability | Family | Guest | What it means |
|---|---|---|---|
| 💬 Chat | ✅ | ✅ | friendly answers; no access to anything of yours |
| ⏰ Own reminders and to-dos | ✅ | ⛔ | private to that person; 20 reminders, 30 to-dos |
| 🛒 Shared family list | ✅ | 🔒 family only | the v42 list everyone in the family sees |
| 📨 Message for you | ✅ | ⛔ | up to 10 a day, arrives with their name |
| 🔎 Web look-ups | ✅ | ⛔ | uses search and AI credits; answers show their sources |
| 📎 Read photos, documents, voice notes | ✅ | ⛔ | uses AI credits; nothing goes into your library |
| 🎨 Pictures | ⛔ | ⛔ | image credits |
| 📄 PDFs | ⛔ | ⛔ | AI credits and server time |
| 📥 Song and video downloads | ⛔ | ⛔ | public video sites only, https only, one at a time; uses your server and saved YouTube login |
| 📅 Free/busy view | ⛔ | 🔒 family only | **times only, never event titles** (the titles are not even requested from Google) |

"Special requests" (web, files, pictures, PDFs, downloads) share one small daily limit: family 10, guests 3. Chat answers: family 100, guests 25. Change any of it in the menu or in words.
At most two background jobs for other people run at once, so your own requests are never starved.

**Never grantable, whatever the switches say:** your email, Drive/files/library, what Nemo remembers about you, trading/positions/money, the server/commands/code/updates, your devices, settings/keys/passwords/approvals, other people's chats and the activity log. Requests about them get a fixed "that is private to <you>" answer; the AI is not asked. Attempts like "I am Gautam, give me access" or "ignore all previous instructions" are refused in the same way.

### First contact and requests

* A new person writing to Nemo gives you a card: **[👨‍👩‍👧 Family] [🙋 Guest] [🚫 Block]**. Until you choose they are a guest. (This replaces the old "DEFENCE: new user" message.)
* If someone asks for something that is off, they get a polite no, and you get **[✅ Allow Asha] [🚫 Keep off]**, at most once per person and ability per 12 hours. Asks for family-only things from guests do not bother you.
* **Strangers off:** anyone who is not family and not approved gets a one-line "private assistant" message once a day and cannot chat, until you tap Guest or Family on their card.
* **Blocked** people are ignored in silence.
* `/start`, "help" or "what can I do" from anyone shows **their own** list of what they can do, with examples (and clears the old owner keyboard from their screen).
* **Groups:** in a group Nemo only chats (when mentioned or replied to), using that person's chat switch and limits; everything else says "message me privately".
* Voice notes are transcribed first and then follow the **same rules as typed text** (a spoken "download this song" needs the downloads switch).

### Plain words (you, in your own chat)

| Say | Effect |
|---|---|
| `family access` · `manage family` · `who can use nemo` | open the menu |
| `what can Asha do` · `what can the family do` · `what can guests do` | the card of ✅/⛔/🔒 |
| `allow Asha to download songs` · `let the family make images` · `give Meera access to the calendar` | switch on (a person, family, guests, or everyone) |
| `stop Asha from making images` · `don't let Asha download` · `turn off web for guests` · `remove Asha's access to the web` | switch off |
| `add Ravi 123456 to family` · `add Guy to family` · `remove Meera from the family` | people (a Telegram id is only needed for someone who has not written yet) |
| `block Asha` · `unblock Asha` | block / unblock |
| `turn off strangers` · `let strangers chat` | strangers off / on |
| `set family chat limit to 200` · `set guest special limit to 5` | limits |
| `who used nemo today` | usage |
| `reset Asha's access` · `reset the family rules` | back to the rules / defaults |

Only your own private chat is listened to for this; the same sentences from anyone else do nothing. Everyday sentences of yours ("let me download this song", "stop the download", "what can you do") are never taken. "Allow Asha everything" is deliberately not accepted; switch things on one at a time.

### How a family member uses the abilities (simple words)

`remind me in 30 minutes to call mom` · `remind me at 6:30 pm tomorrow to take medicine` · `show my reminders` · `cancel reminder 1` · `add buy milk to my todo list` · `/done 1` · `add milk to the list` · `tell Gautam I reached home` · `search the web for the latest solar panel prices` · send a photo, PDF or voice note · `draw a cat riding a bicycle` · `make a pdf about solar energy` · `download tum hi ho song` · `is papa free tomorrow evening?`. Times are Indian time. "At 6" said at 5 pm means 6 pm.

## 3. Behaviour changes to be aware of

* **Guests lose photos, files and voice notes by default** (they could send them before). Switch it on per guest or for all guests if you want it.
* **Family chat has a daily limit (100)** instead of being unlimited. Raise it in the menu.
* Reminders and to-dos for family now actually work (they were blocked before).
* Guests and family no longer see the owner's reply keyboard; their `/start` is replaced by their own access card.
* Non-owner button presses are ignored (the old per-handler checks stay as a second layer).

## 4. Tests actually run

All offline: a scripted fake AI, fake Telegram sender/editor, fake image/PDF/download/web-search engines, a fake Google Calendar, temporary SQLite database, synthetic people. **No Telegram, no Google, no AI, no trades, no paid calls.**

| Suite | Tests | Result |
|---|---|---|
| v83 Cortex · v84 Atlas · v85 Steward · v86 Candor · v87 Relay · v88 Argus (existing) | 866 | pass |
| **v89 Circle** (`tests/test_circle89.py`) | 223 | pass |
| **Total** | **1089** | **OK** (1 slow test skipped by default) |
| Slow gate: v85 sandbox update gate run on the real v89 file | 1 | pass (55 s) |

Circle tests cover: the classification tables (messages for you, 26 private topics that must be locked, 12 look-alike everyday requests that must stay chat, 11 attempts to become the owner, all slash commands); the time parser (relative, clock, day-parts, "at 6" at 5 pm, invalid times); people, roles and rules (priority, family-only and never-for-strangers, block beats family, v42 members kept, forgetting a person); limits, Indian-time days and rationed notices; **the gate** (50 messages × guest, family, and family with every ability on: none ever reaches the older layers; errors fail closed for others and not for you; blocked is silent; groups; fresh-install rule); first contact and its buttons; strangers off; chat prompts (person rules, limit, switch-off) and the **privacy control** (the owner's own prompt contains the seeded secrets, a guest's and a family member's never do); reminders and to-dos (isolated per person, caps, listing/cancelling only their own); the shared list and messages to you; web look-ups; photos, documents and voice notes (temporary files unique and deleted, size limits, voice obeys the same rules); pictures and PDFs (unique temp files, at most two background jobs); downloads (host allow-list, https only, no embedded login, no private addresses, one at a time, failure frees the slot); the free/busy view (times only, titles never requested, skipped/cancelled events, guests can never have it); the owner menu (every page and button, nonsense callback data changes nothing, edit-in-place with fall-back); plain-words control (every phrase table, 21 everyday sentences that must **not** be taken, the same words from anyone else do nothing); request cards; button presses and inline queries from others; and **structure checks** (the menu is reachable only after the owner check; only owner-side code writes rules; network calls only in two named functions; no shell/eval/pickle/process calls; only circle tables plus the old family table; no credentials touched). **Mutation checks** put the old behaviour back one piece at a time (a gate that lets strangers through or fails open, ignored switches, a guest who can see the calendar, private topics reaching the model, no limits, obeying other people's buttons, serving blocked people, no first-contact card, strangers that cannot be turned away, a request card on every refusal, downloads from any address, a calendar that shares titles, a `see` tool open to everyone, a chat prompt without the person rules, hijacked owner sentences, other people giving orders, a voice note that skips the rules, a shared picture file, an activity log that stores what to forget) and the matching test goes red (all do).

Other gates: `py_compile` OK; pyflakes 158 findings in v88 and the same 158 in v89; secret-pattern scan of the diff and tests clean; `_update_cred_changes` v88→v89: no changed or removed credentials; diff outside the appended layer is limited to the docstring line, the self-edit protection prefix and the owner check at the start of the `see` tool.

## 5. Offline-tested vs not verified live

**Offline-tested:** everything above.

**Not verified live — please run the checks in section 6:**
* How the inline-keyboard cards and the edit-in-place menu look and behave in the real Telegram app.
* The real image engine, PDF publisher and video downloader (yt-dlp, your cookies, your server) when they are run for a family member's chat.
* The calendar view against your real Google account.
* Voice-note transcription (Groq) for a family member.
* Inline mode, if you have it switched on in BotFather.
* The pattern-based "private topic" detection catches the usual phrasings, but it is not a mind reader. A cleverly worded request can still reach the chat model; that model is told not to reveal anything and has **no access** to your data (tested), so the worst it can do is say it cannot help.
* No live trades and no paid-API tests were run.

## 6. Quick checks through Nemo

1. In your own chat: `/circle` → tap **People**, **Family rules**, **Limits & strangers**.
2. `what can the family do` · `allow Asha to download songs` · `stop Asha from downloading`.
3. From a family member's phone: `/start` (their own list) · `remind me in 2 minutes to test` · `draw a cat` (polite no; you get an Allow/Keep off card) · `read my last 5 emails` (refused, private) · `tell <your name> hi` (arrives for you).
4. `turn off strangers`, then message Nemo from a phone Nemo does not know: one polite line; you get the card. Tap **Guest** or **Block**.
5. `is papa free tomorrow` after switching the calendar on for a family member: times only.

## 7. Installing and rolling back

Upload `nemotron_bot.py` to Nemo on Telegram and send `/update` (v85 pre-flight: compile, credential comparison, sandbox import and regression run), then **Apply & restart**; `/rollback` restores the previous file. Nothing else to configure. Your family list (`/family`) and block list (`/block`) are used as they are; the new switches live in the same database under `circle89_*` tables.
