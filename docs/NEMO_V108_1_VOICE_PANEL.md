# Nemo v108.1 "Voice panel": real voice notes on iPhone, and voice options you can see

Evidence tags: **[code]** = read in Nemo's code; **[tested]** = covered by the offline tests; **[source]** = from the pages in section 7; **[not verified]** = not checked live.

## 0. Honest status

* **Built and tested offline only.** The test machine cannot reach Telegram or Microsoft's voice service. Every Telegram call is a stand-in. Two things are real in the tests:
  * ffmpeg turning speech into an OGG/Opus voice note (the test checks it is a real Ogg/Opus file);
  * reading its length.
* **Not checked on a real iPhone.** I could not see your phone. What a voice note looks like on iPhone comes from other developers' reports [source], not from me.
* No live trades, no paid AI calls. Trading, the guards, the owner lock and credentials are not touched by this layer [code].

## 1. Why you could not see the voice options

I found five causes in the code:

1. **Voice replies went out as MP3 first** [code]. Telegram accepts MP3 as a voice note, but developers report that MP3 voice notes show **without the waveform and without the speed button**; Telegram's own voice notes are OGG/Opus [source]. On an iPhone that looks like a plain sound file, with none of the voice-message controls.
2. **"voice settings" answered with a block of text and no buttons** [code].
3. **The older speakers sent a music file, not a voice note** [code]: `/say`, the old `/voice` mode, narrated pictures and lessons, `/talk` hello and bye, and research answers used `sendAudio` ("Nemo • Girl Voice"). That shows as a music track.
4. **Nothing about voice was in Telegram's menu** [code]: Nemo never set its command list.
5. **Possible:** if you have Telegram Premium and limit who can send you voice messages, Telegram refuses voice notes from bots with `VOICE_MESSAGES_FORBIDDEN` [source]. v108 then silently sent a music file. I cannot tell from here whether this applies to you [not verified].

## 2. Real voice notes

* **OGG/Opus first** [tested], the format Telegram's own voice notes use: mono, 48 kHz, speech mode, 32 kbit/s (16 kbit/s for notes over about 3 minutes, so the file stays small; an old report says Telegram drops the waveform on big files [source]).
* **The length goes with it** [tested], so the bubble shows "0:12" at once.
* **MP3 only when the server has no ffmpeg** (or the OGG was refused) [tested]. Then Nemo says so and how to fix it: "install ffmpeg on the server" goes through Nemo's installer with your approval (v91 Forge has ffmpeg on its list) [code].
* **If Telegram blocks voice notes** (your privacy setting) [tested]:
  * Nemo tells you once a day how to allow them: Telegram → Settings → Privacy and Security → Voice Messages → Everybody, or add Nemo as an exception;
  * whether a bot can be added as an exception is [not verified];
  * meanwhile replies come as audio files;
  * family members' settings are never reported to anyone.
* **Every older speaker now sends a real voice note** with the 🐢 ⚡ 📝 buttons [tested]. The music file stays only as the last resort. One voice note per answer: an older speaker and the voice layer never both speak the same reply [tested].

## 3. The voice options card

Say **voice settings**, **voice options**, **/voice**, or just ask "I can not see the voice options". You get a card with buttons [tested]:

* **Voice replies:** 🎤 When I speak · 🗣 Always · 🔇 Off
* **Voice and text** or **voice only**
* **Speed:** 🐢 Slow · Normal · ⚡ Fast
* **👩 Female voice** · **👨 Male voice**
* **🔊 Listen button** on/off · **👪 Family voice** on/off
* **▶️ Test my voice** · **📖 Read my last answer**
* **📱 Voice notes on iPhone** (how to record one, and what to do if nothing records)

Details:
* The current choice has a ✓. A tap changes it and **redraws the same card** (no new message) [tested].
* Only you can use the card, in your own chat. A tap from anyone else changes nothing [tested].
* `voice status` shows the full status with the same buttons [tested].
* `/voice off` turns voice replies off, and also the oldest "speak every answer" switch. `/voice on` means "always" [tested].
* Other talk about voice ("the voice of the customer", "send the voice note to Riya") is left alone [tested].
* **After the update**, one card arrives by itself: "🆕 Your voice options are now buttons" [tested]. It comes once only.

## 4. 🔊 Listen under longer answers

* Under a longer typed answer in your chat (about three lines or more) there is a **🔊 Listen** button. Tap it and **that** answer comes as a voice note [tested].
* Not under:
  * short answers or progress messages;
  * cards that have their own buttons;
  * messages Nemo sends on its own (not replies);
  * answers that are spoken anyway (the reply to a voice note, or "always" mode);
  * other people's chats.
* `listen button off` / `show listen buttons`, or the button on the card.
* The last 200 answers are kept for these buttons, in memory only. "Forget" clears them like everything else [tested].

## 5. Test voice, and /voice in the menu

* **`test voice`** (or ▶️ on the card) sends a short sample voice note and then says exactly how it went [tested]:
  * ✅ a real voice note (with its length);
  * ⚠ MP3 because the server has no ffmpeg, with the fix;
  * 🔇 blocked by your privacy setting, with where to change it;
  * ⚠ Telegram stored it as a file;
  * ❌ no voice engine installed, or the voice service did not answer;
  * ❌ Telegram refused it, with Telegram's reason.
* **/voice in your Telegram menu:**
  * after the update, Nemo adds `/voice` to **your own** command menu, once [tested];
  * it keeps the commands already there; nobody else's menu changes [tested];
  * on iPhone, type "/" in Nemo's chat (or tap Menu) to see it;
  * `remove voice from the menu` takes it out, and it is not added back [tested];
  * if you change the command list in BotFather later, say `add voice to my menu` again: your own menu was copied once and does not follow BotFather by itself [code].

## 6. Tests (offline)

* `tests/test_voicepanel1081.py`: **38 tests, all pass.** They cover the OGG/Opus upload (a real Ogg/Opus file with its length), the format settings, no ffmpeg, a refused OGG, a blocked voice note (told once, never for family), "stored as a file", the older speakers (including `/say` through every layer), one voice note per answer, the card and its buttons, your own words, what is left alone, owner only, redrawing, a card that cannot be edited, `/voice on/off`, quiet hours never holding the card, status, iPhone help, read last answer, test voice and its reports, 🔊 Listen and where it does not appear, the menu (merge, already there, remove, Telegram refusing, bad entries), the card once after start, version and hooks, and no orders or secrets in the layer.
* `tests/test_voice108.py`: 66 tests, all pass. 3 were changed on purpose, because v108.1 changes what they tested:
  * the version check;
  * the reply's format is now OGG;
  * the fallback order is now OGG → MP3 → audio file.
* **Mutation check:** 41 deliberate bugs put into the layer one at a time. The tests catch all 41.
* **pyflakes:** the same 158 messages as v108.0, none new.
* **Nemo's own regression suite:** 1093 pass. The same 3 fail as before, because this machine has no internet or bot config.
* **Full test suite:** still running when this was committed; the result follows in the next commit.

## 7. Sources

* Telegram Bot API `sendVoice` (as copied into aiogram 3.31): OGG/Opus, MP3 or M4A; other formats go as audio or document.
* MP3 through `sendVoice` plays but shows without the waveform and speed control; OGG/Opus with libopus in speech (voip) mode fixes it. DEV Community, "Your Telegram bot's voice messages are missing speed control", https://dev.to/turtleand/your-telegram-bots-voice-messages-are-missing-speed-control-heres-the-fix-13hm. This is a search summary only: dev.to is blocked from this machine.
* Hermes Agent Telegram docs:
  * without ffmpeg, Edge TTS audio arrives as a regular audio file, not a voice bubble;
  * voice bubbles use Opus/OGG;
  * `VOICE_MESSAGES_FORBIDDEN` comes from the user's voice-message privacy setting.
  * https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram (search summary).
* Telegram's privacy key for voice messages (Premium users): https://core.telegram.org/constructor/inputPrivacyKeyVoiceMessages
* A bot that falls back to text on `VOICE_MESSAGES_FORBIDDEN`, pointing users to Settings → Privacy → Voice Messages: Moltbot/OpenClaw commit "fall back to text when voice messages forbidden (#1725)".
* Waveform only for small files: an old Stack Overflow answer, "how convert ogg file to telegram voice format" (it may be out of date).
* iPhone microphone: a square icon tapped once switches to the microphone; Telegram needs Microphone access in iPhone Settings. https://www.guidingtech.com/fixes-for-telegram-voice-messages-not-working-on-android-and-iphone/

## 8. Simple checks to run through Nemo (after updating)

1. After the restart, the card "🆕 Your voice options are now buttons" arrives. If not, send `voice settings`.
2. Tap **▶️ Test my voice**. You should get a voice bubble with a waveform and "✅ Sent as a real voice note".
   * If it says **MP3 because the server has no ffmpeg**: send `install ffmpeg on the server`, approve, then `test voice` again.
   * If it says **blocked**: change Telegram → Settings → Privacy and Security → Voice Messages, then test again.
3. Send a **voice note** ("what is the time in London?"). The reply is a voice bubble. Play it and look for the speed control.
4. Type a longer question ("explain how SIPs work"). Tap **🔊 Listen** under the answer.
5. Type **/** in Nemo's chat (or tap Menu): **/voice** is in the list.
6. Tap **📱 Voice notes on iPhone** on the card.
