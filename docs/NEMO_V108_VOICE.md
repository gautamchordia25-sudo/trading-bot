# Nemo v108.0 "Voice": answers you can watch being written, voice notes that are a real conversation, and a Nemo that knows when to stay quiet

After v107.1 was installed you said "build next version". The plan's next step was **v108 Voice** (master list items V1, V2, V7, X1, X2 and V6): *Nemo feels alive and the family can use it by voice.*

Evidence tags: **[code]** = read in Nemo's code; **[tested]** = covered by the offline tests; **[source]** = from the pages in section 9; **[not verified]** = not checked live.

## 0. Read this first (the honest version)

* **Built and tested offline only.** The test machine cannot reach Telegram, Microsoft's voice service or any AI provider. Every Telegram call, every provider stream and every voice in the tests is a stand-in. Two things are real:
  * ffmpeg turning a sound into an OGG voice note;
  * ffmpeg turning a picture and a sound into a round video note.
* **Live drafts use a new Telegram feature, `sendMessageDraft`.** I read its rules in a current Telegram library (aiogram 3.31, Bot API 10.3) [source]:
  * private chats only;
  * the draft is a short preview that disappears when the real message arrives;
  * a stop button is possible.

  I could not open Telegram's own pages from here, and an older library note said only bots in "forum topic mode" could use it [not verified]. **If Telegram refuses a draft, Nemo turns drafts off for an hour and answers exactly as before.** `voice status` shows that, with Telegram's reason.
* **The stop button** sends a new kind of update (`stopped_message_generation`). Nemo's update loop now passes it on [code]. Whether Telegram sends it without asking for it specially is [not verified]. If it does not arrive, typing "stop working" still stops the answer.
* **Voice notes are sent as MP3**, which Telegram now accepts for voice messages [source]. If Telegram refuses, Nemo converts to OGG/Opus with ffmpeg, then falls back to the old audio file.
* **Gujarati voices** (Dhwani, female; Niranjan, male) are listed by voice sites [source], but I could not list Microsoft's voices from here [not verified]. If they fail, Google's voice (gTTS) speaks Gujarati: it lists Gujarati as a language [tested].
* **Quiet hours, snooze and the daily digest are off until you turn them on.** Even then they hold only messages Nemo sends **on its own**, and never these:
  * a reply to you (anything within 20 minutes of your last message or button);
  * anything about trading, orders, money, security, failures, updates, reminders, alarms, OTPs, approvals or your calendar.
* **No order, no trade, no change to the trading agent, guards, owner lock or credentials.**

## 1. What was found [code]

* **Voice notes were cut off from today's Nemo.** A voice note was transcribed and then sent to the old **v13 `answer()` path**. That path skips everything built since:
  * memory;
  * the router;
  * the Pine engine;
  * Reach research;
  * tone;
  * receipts.

  A voice note asking for a Pine Script got a chat reply, not the file. The `/talk` session had the same problem: it used the message handler as it was in v37.
* **Voice replies were music files.** `speak()` sent `sendAudio` (an MP3 with a player bar), not a voice-note bubble. The speed was fixed and there was no Gujarati voice.
* **No streaming.** The gateway gets each answer in one piece (`stream: false`), so a long answer arrived only after it was finished.
* **Quiet hours existed only for the v38 "attention" nudges** (22:30–07:30). Everything else (routines, watchers, reports, topic news) came at any hour. There was no snooze and no digest.
* **Tone was one dial for one chat** (language and detail level), not per person or situation.
* **Nemo reacted only with 👀**, and answered "thanks" with a full AI reply.
* **No polls, quiz polls or video notes.**

## 2. V1: the answer appears while it is written

* For your own private chat, the moment you send a question you see Telegram's **"Thinking…"**.
* As the model writes the answer, the draft grows about once a second.
* A **stop button** under the draft stops the answer (and the model call): Nemo replies "⏹ Stopped. Tell me what you meant, or ask again."
* The checked answer then arrives as the normal message and replaces the draft. Cortex's fact and date check still runs on the full draft, so the final message can differ a little from what you watched.
* **Only the answer call streams** [tested]:
  * helper calls (scout, memory clerk, critic), repairs after the check, other providers, and the local brain (v102 Hearth, when it answers first or Nemo is offline) are unchanged;
  * streaming covers **Anthropic and OpenRouter**, the first two answer models in Nemo's list.
* **Any fault falls back** to the **unchanged gateway** [tested]:
  * if the model's own answer fails (HTTP error, cut-off or rejected answer), that model rests for 45 seconds exactly as before;
  * if only the stream broke (a dropped connection, garbled events), nothing rests and the gateway may ask the same model again;
  * if the reply comes back whole instead of streamed, it is read exactly as the gateway reads it;
  * a streamed answer goes through the same output check as before;
  * a refusal or a stop inside the stream is handled exactly as Nemo's non-streaming check handles it.
* `streaming off` / `streaming on`.

## 3. V2: voice-note conversation

* **Your voice note is now a message for the whole of Nemo** [tested]:
  * it is transcribed (Groq Whisper, then the local model);
  * you see "🎤 *what you said*";
  * then it goes through exactly the same path as typed text: memory, router, Pine, Reach, reminders, everything.
* **The voice note itself still passes every older layer first** [tested], as before: Argus logs it in the activity record and Scout passes it on. Today's voice reader takes it only at the end, where the old reader used to.

  The test sends a voice note saying "create a pine script with your survival logic" and gets the `.pine` file and a spoken reply.
* **The reply comes back as a real voice-note bubble** in the reply's language:
  * English (Neerja/Prabhat), Hindi (Swara/Madhur) or Gujarati (Dhwani/Niranjan);
  * at your speed;
  * with three buttons: **🐢 Slower · ⚡ Faster · 📝 Text**.

  Progress messages ("I am working on it…") are never spoken, only the answer [tested].
* **Text twin:** by default you get voice **and** text. `voice only` sends the voice note alone, but text still comes for:
  * links, code, tables or long numbers;
  * long answers.

  Tap 📝 Text to read it.
* **Family members** who send Nemo a voice note get a voice note back (`family voice off` stops that).
* **`/talk` sessions** now go through the whole of Nemo too, and are spoken. Voice notes inside a `/talk` session keep the session's own reader, so "bye" still ends it [tested]. Audio files and captioned voice notes also keep the older readers.
* Settings in words:
  * `voice replies on/off`;
  * `always reply in voice` (while you are talking to it);
  * `voice only`, `voice and text`;
  * `speak slower/faster`, `use a male/female voice`;
  * `read that out`, `say that again slower`;
  * `voice status`.
* Limits: 15 minutes or 20 MB per voice note (Telegram's own download limit is 20 MB).

## 4. V7: notification manners

| You say | What happens |
|---|---|
| `quiet hours 11 to 7` | 23:00–07:00 IST. A bare evening start is read as pm, and the v38 attention nudges use the same window. In that time Nemo **holds** what it would send on its own (routine reports, topic news, digests, nudges, other unprompted messages). |
| `snooze Nemo 2 hours`, `mute Nemo for 30 minutes` | The same, until then. `unsnooze` ends it and gives back what was held. |
| `daily digest at 8 am` | Routine updates (news, topic watches, feeds, routine reports, tips) wait for **one** message a day at 08:00; everything else comes as before. `daily digest off`. |
| `what did I miss` / `show held messages` | Everything held, in full. |
| `notification settings` | What is on. |

* **When the quiet or snooze ends**, you get **one summary**: "🌅 While you were away: 3 messages", with the time and first line of each. Messages that had buttons (approval cards) come again whole, so the buttons still work [tested].
* **Never held** [tested]:
  * replies to you (20 minutes after your last message or button press, so long jobs count as replies);
  * messages to anyone else (family, guests);
  * anything that mentions trading, orders, positions, stop-losses, the broker, payments, debits, UPI, security, logins, failures, errors, updates, restarts, reminders, alarms, emergencies, the calendar, deadlines, OTPs or approvals;
  * anything sent when a fault in this layer occurs: the message simply goes out.
* **Not covered:** messages some older parts of Nemo send straight to Telegram, without the shared sender, are not held [code]. Most alerts use the shared sender.

## 5. X1: tone dials

* **Settings in words:**
  * `be shorter`, `be more detailed`, `normal length`;
  * `be more formal`, `be casual`, `be warmer`, `be more direct`;
  * `no emojis`, `use emojis`;
  * each one with `… with customers`, `… with staff`, `… with family`, `… with friends` or `… with <name>`;
  * `tone settings`, `reset tone`.
* **One-off wishes are not dials** [tested]: "keep it short" or a bare "formal" is a request for this one answer, and is answered as before.
* **Where the dials apply:**
  * your own dial goes to the answer model on every reply, and `be shorter` also sets the older detail preference;
  * when you ask Nemo to **write something for** customers, staff, family or a named person ("draft a reply to the customer…"), that dial is added for that message;
  * when a family member chats with Nemo, the dial for their name, or for family, is added to their chat [tested].

## 6. X2: expressive voice and reactions

* **Voice mood** comes from what is being said (`expressive voice off` turns it off):

  | Mood | When | Delivery |
  |---|---|---|
  | excited | congratulations, a target hit | a little faster and brighter |
  | calm | someone unwell, a loss, "don't worry" | a little slower and lower |
  | serious | warnings, failures | slower and lower |
  | warm | thanks, greetings | slightly slower |

  edge-tts no longer accepts custom voice styles [source], so mood is done with speed and pitch only.
* **Reactions** (`reactions off` turns them off):
  * "thanks", "shukriya" or ❤ get **❤ or 🙏 as a reaction, and no message**;
  * "ok", "done", "theek hai" or 👍 get **👍**;
  * good news ("I got the order") gets 🎉, and sad news gets 🙏, and both are still answered;
  * "haha" gets 😁.
* **"ok" is never swallowed when it may be an answer** [tested]: a pending confirmation, an open card, a question Nemo asked (anything ending in "?"), a quiz, or a voice session.

## 7. V6: richer messages

* **Polls:**
  * `poll: Where for dinner? Pizza, Thali, Chinese` sends a native Telegram poll, with 2–12 choices separated by commas, "/" or "or";
  * `multiple choice poll: …` allows several answers;
  * you can also start one in a **family group** (votes are visible there);
  * nobody else can make Nemo start one.
* **Quiz polls:**
  * `quiz poll` turns your study cards (v95) into a native Telegram **quiz**: the due card's question, its answer, and up to three other answers from your cards as choices;
  * no AI is used;
  * Telegram changed the quiz field in April 2026, and Nemo falls back to the older one if refused [source, tested].
* **Round video notes:** `send that as a video note` turns the last answer into a round video note (Nemo's picture and the spoken answer). It needs ffmpeg on your server [tested with real ffmpeg here].
* **Buttons under voice notes:** 🐢 Slower, ⚡ Faster, 📝 Text. Only the person the voice note was for can use them.
* **Not built:** "only-you messages in groups". Telegram added ephemeral messages for this in August 2026 (Bot API 10.2/10.3) [source], but I could not read its rules, so I left it out rather than guess.

## 8. Tests (offline)

`tests/test_voice108.py`, **66 tests, all pass**. Covered:
* a voice note reaching the Pine engine and the voice reply;
* the voice mark on the transcript, progress not spoken, a voice turn expiring, voice off, always, and voice only;
* the older layers seeing the voice note first; `/talk`, audio files and unseen notes keeping the older readers; the note list never growing past 50;
* too long or unclear notes, captioned notes, family voice, the old `/talk` path and its loop guard;
* languages, voices, the spoken text, mood and speed;
* the MP3 → OGG → audio fallback (real ffmpeg), no voice engine, buttons, settings in words, read-it-out, a real video note, and the no-ffmpeg message;
* streaming:
  * Anthropic and OpenRouter;
  * helpers not streaming;
  * a refusal in the stream, a cut-off stream and an HTTP error each falling back;
  * a whole (non-streamed) reply, a broken stream that leaves the model usable, and the output check on a streamed answer;
  * the stop button, and someone else's stop;
  * Telegram refusing drafts;
  * streaming off, groups and the local brain;
  * the update loop passing on the stop update;
* manners: off by default, quiet hours in words, holding and not holding, one summary with buttons kept, snooze, the daily digest once a day, "what did I miss", what is urgent, and a fault not blocking a message;
* tone parsing including one-off wishes, the dials reaching the answer model and the family chat, and show/reset;
* reactions: thanks, ok after a question, pending confirmations, good and sad news, reactions off or refused, a spoken thanks;
* polls in words, native polls, group polls by the owner only, quiz polls including the older field, and no cards;
* version, regression rows, forgetting, the sender's contract, and no orders or secrets in the layer.

Other checks:
* **Mutation check:** 55 deliberate bugs put into the layer one at a time; the tests catch all 55.
* **pyflakes:** the same 158 messages as v107.1, none new.
* **Nemo's own regression suite:** 1087 pass; the same 3 fail as on v107.1, because this machine has no internet and no bot config.
* **Full test suite:** the first run found 6 problems (5 caused by v108, now fixed: voice notes skipped Argus and Scout, and a broken stream rested the model). A rerun on this file was still going when this was written.

## 9. Sources

* Telegram Bot API method and field descriptions, as copied into aiogram 3.31.0 (`__api_version__ = "10.3"`), downloaded from PyPI and read as text: `sendMessageDraft`, `MessageGenerationStopped`, `sendVoice` (OGG/Opus, MP3 or M4A; 50 MB), `setMessageReaction` (one reaction for bots; the list of allowed emoji), `sendPoll` (1–12 options; `correct_option_ids`, with `correct_option_id` deprecated on 3 April 2026), `sendVideoNote` (up to 1 minute), ephemeral messages (`receiver_user_id`, Bot API changelog 24 August 2026).
* aiogram's documentation pages (docs.aiogram.dev); search summary only, the site is blocked here.
* Habr, on throttling draft updates: https://habr.com/ru/articles/1019836 (search summary).
* edge-tts on PyPI: custom SSML removed since 5.0.0; rate, volume and pitch options. https://pypi.org/project/edge-tts/
* Gujarati Azure voices: https://json2video.com/ai-voices/azure/voices/gu-in-dhwanineural, https://json2video.com/ai-voices/azure/voices/gu-in-niranjanneural/, https://fliki.ai/voices/gujarati
* gTTS 2.5.4 language list (installed here): Gujarati, Hindi, English.
* OpenRouter streaming: SSE comments, and mid-stream errors arriving with `finish_reason: "error"`. https://openrouter.ai/docs/api-reference/streaming, https://openrouter.ai/docs/api/reference/errors-and-debugging
* Anthropic Messages API streaming event types (message_start, content_block_delta/text_delta, message_delta/stop_reason, message_stop, ping, error, refusal): the Claude API reference.

## 10. Simple checks to run through Nemo (after installing)

1. Send a **voice note**: "what is the time in London?". You see "🎤 …", then a text answer **and a voice-note bubble** with 🐢 ⚡ 📝 under it.
2. Send a voice note: "create a pine script with your survival logic". The `.pine` file arrives and the explanation is spoken.
3. Ask something long in text ("explain how SIPs work in detail"). You should see "Thinking…" and then the answer growing. Press the stop button once to try it. If nothing grows, send `voice status`: it says whether Telegram refused drafts and why.
4. `quiet hours 11 to 7`, then `notification settings`. `snooze Nemo 30 minutes`, then `unsnooze`.
5. `be more formal with customers`, then "draft a reply to a customer asking for the delivery date": the draft is formal. `tone settings` shows it.
6. Send "thanks": you get a ❤ on your message and no reply.
7. `poll: Where for dinner? Pizza, Thali, Chinese`.
8. `send that as a video note` (if the server has ffmpeg).
