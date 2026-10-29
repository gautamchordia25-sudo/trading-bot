# How to bring Nemo out of Telegram

You asked, before any of the feature list is built: how can Nemo live outside Telegram? This page is the research. It is a plan, not a build: **nothing in it is built yet.**

Evidence tags: **[code]** I read it in `nemotron_bot.py` this session; **[web]** a web-search result (blogs, vendor pages, news: weak, treat numbers as "reported"; links at the end); **[mine]** my judgement; **[gap]** I looked and could not confirm it.

---

## 1. The short answer

Nemo does not have to leave Telegram. It needs **more doors**, all opening onto the same brain, the same memory and the same permission rules, with Telegram kept as the admin door and the fallback. The doors, in the order I would build them:

1. **An installable app on every phone and PC (the "Nemo app")**: the website Nemo already serves, made into a full Nemo, with its own login (no Telegram needed), family accounts, voice, pictures, approval buttons and push notifications.
2. **Voice doors**: "Hey Siri, ask Nemo" and the iPhone Action Button; a phone number you can call from any phone; push-to-talk on the laptop.
3. **A Windows desktop app** (tray icon, hotkey, dictation, and later the typing and clicking you asked about).
4. **Other doors for you**: a browser side panel, an OpenAI-compatible address so other chat apps can use Nemo, Nemo as a tool for Claude Desktop, email-in, a smart-home voice speaker.
5. **WhatsApp last, and carefully.** It is where your family already is, but Meta has shut the official door to general-purpose AI assistants (section 4), and the unofficial door risks the phone number.

## 2. What Nemo already has outside Telegram, and what is wrong with it **[code]**

| Door | What exists | The problem |
|---|---|---|
| **Website / phone app** | A Flask site on port 8090: an installable web app (manifest and service worker), `/app` chat page, `/api/chat`, a dashboard, a "cockpit", file upload, a browser-screenshot view, many voice endpoints (`voice3`, `voice6`, `voice9`, `voice18`: a laptop voice agent with screen-aware helpers), Telegram login (v95). | **`/api/chat` answers with `web_ai`: a plain chat with your memory, "chat-only (no destructive actions from a remote channel)". It does not run Nemo's commands**: no Sigma, Globe, Scout, ledger, Studio, Forge, approvals. So today the web door is a smaller Nemo. **The login works only by opening the page from Telegram** (it checks Telegram's Mini App `initData`): the web door still depends on Telegram. |
| **Phone call** | `/twilio/<secret>/voice` + `/gather`: you call a Twilio number, speech is turned into text (`en-IN`), `web_ai` answers, text is spoken back. | English only; again the plain chat; **no check of who is calling**. |
| **WhatsApp** | `/twilio/<secret>/whatsapp` (Twilio sandbox style). | **It does not look at the sender at all.** Whoever can message that number gets `web_ai`, which runs on **your** memory (`oid = OWNER id`). The URL secret protects the webhook, not the conversation. Also the plain chat only. |
| **Laptop** | An enrolled device that reports and runs **read-only** diagnostic jobs. | By design it cannot type or click. |
| **Output side** | `send_text` is called 2,660 times and `tg` 144 times; about 10 places post straight to Telegram's file endpoints; **about 610 lines refer to the owner's id** (most of them checks that the chat is the owner's). | Nemo's code assumes "the chat is a Telegram chat". Every new door must either pretend to be the owner's Telegram chat, or the code must learn about channels. See section 5. |

So: the doors exist in rough form, but each one gives a weaker Nemo and two have a gap in who is allowed in. **That is the first thing to fix, before adding any new door.**

## 3. The doors, compared

"Family-friendly" = a non-technical relative can use it. Effort: S = hours, M = a day or two, L = several days.

| # | Door | What it is | Evidence | Family-friendly | Effort / risk | Verdict |
|---|---|---|---|---|---|---|
| 1 | **Nemo app (installable web app)** | The existing site, upgraded to a full client: streaming replies, voice notes, pictures, charts, approval buttons, family accounts, push notifications. Installs from the browser on Android, iPhone and PC, no app store. | [code] site and manifest exist. [web] iOS supports web push **only for apps installed to the Home Screen**, since iOS 16.4, with the install-then-ask-permission order; reports say iOS push subscriptions can silently vanish, so reliability lags Android; no real background sync on iOS (queue and flush on open). Android shows an icon badge automatically when a notification is unread. | High | M / low-medium | **Build first** |
| 2a | **Siri / Action Button (iPhone)** | A Shortcut that dictates, sends the text to a Nemo address, and speaks the answer. "Hey Siri, ask Nemo"; Action Button or Back Tap. No app. | [web] Shortcuts can POST to any HTTPS endpoint and speak or show the reply; hobby projects do exactly this; the key sits in plain text inside the shortcut and long answers can be clipped in Siri's pop-up. | Medium (needs a one-time set-up per phone) | S / low-medium | **Build with door 1** |
| 2b | **Phone call line** | Call a number from any phone, even a basic one, and talk. Good for elders. | [code] Twilio voice hook exists. [gap] I did not check whether an Indian number is available on Twilio and under what rules. | **Highest** (no app at all) | M / medium (calls cost money; privacy; legal rules; add caller allow-list) | Build after door 1 |
| 2c | **Android** | A home-screen widget or the installed web app. A true "default assistant" app is possible (apps declare a `VoiceInteractionService`; the user picks one default; it can take the power-button long-press), but needs a real Android app. | [web] Gemini has replaced Google Assistant on Android in 2026; in the EU, a July 2026 Commission decision obliges Google to open assistant hooks to rival AIs (full replacement not before 2027); that does not apply to India. [gap] Tasker's role is unconfirmed. | Medium | L / medium | **Later**; the web app first |
| 2d | **Smart speaker / home voice** | Alexa custom skills still work but Alexa+ "bring your own model" status is unclear; Google Assistant is retired in favour of Gemini with no clear third-party route; **Home Assistant voice satellites** (an ESP32 or Raspberry Pi with a microphone, wake word, Whisper and a text-to-speech engine) are the open route. | [web] [gap] custom wake words on the stock Home Assistant device are awkward; openWakeWord on a Pi Zero performed poorly for one user. | Medium | L / medium | **Later**, only if you want a speaker at home or the showroom |
| 3 | **Windows desktop app** | A tray program: chat window, a global push-to-talk hotkey, notifications, dictation anywhere, and the later "Hands". | [web] Tauri 2 (Rust, small) reported about 40 MB idle against Electron's 170-300 MB; Tauri's global-shortcut plugin reports key press and release, which push-to-talk needs; both numbers are from blogs. [mine] Nemo's laptop agent is already a Python script: the quickest first version is that same program showing the web app in a window (a thin shell), moving to Tauri if it is worth it. | You and a few relatives | M-L / medium (it controls a PC: see the typing plan in `NEMO_ADVANCED_AI_FEATURES.md` G3/G4) | **Build third** |
| 4a | **Browser side panel** | A Chrome/Edge extension: chat beside any page, "summarise this", "ask about the selection", form help. | [web] Chrome's Side Panel API (stable since Chrome 114, Manifest V3) keeps the panel open across tabs; the panel cannot read the page directly (use the scripting API); keep API keys on the server, never in the extension. | You | M / low-medium | Later |
| 4b | **OpenAI-compatible address** | A `/v1/chat/completions` and `/v1/models` address, so Open WebUI and similar chat apps can use Nemo as their "model". | [web] Open WebUI adds any such provider by base URL; discovery uses `/models`, chat uses `/chat/completions`. [gap] I did not confirm LobeChat or Chatbox from the search. [code] roadmap item A6. | You | S-M / medium (anything on this address must run with the same permissions as a signed-in person) | Later |
| 4c | **Nemo as an MCP server** | Claude Desktop, Cursor and similar tools can call Nemo's tools (Globe, Sigma stats, ledger, reminders). | [web] MCP clients take a `url` for a remote server or a `command` for a local one. | You | M / medium | Later, read-only tools first |
| 4d | **Email-in** | Mail a question to an address you own; Nemo replies, only to allowed senders. | [mine] Sender spoofing is easy: accept only mail that passes your provider's checks and from a pre-approved list; never act on instructions inside the mail beyond answering. SMS is a poor fit in India: DLT registration is mandatory for commercial SMS, and Twilio's own pages disagree about two-way SMS there **[web]**. | You | S / medium | Optional |
| 5a | **WhatsApp: official Business API** | Meta's cloud API through a provider (Twilio and others). | [web] Meta's terms (section 4.7), enforced from 15 January 2026, bar AI providers whose **main product is a general-purpose assistant**; businesses may still use AI for their **own customers** (support, orders, bookings). The EU said in April 2026 it intends to order access restored; a September 2026 report says Meta is testing limited third-party agents (up to five, personal use, **no end-to-end encryption**, no groups). One vendor blog gives India's reply price from 1 October 2026 as about ₹0.115 each after 1,000 free a month (unverified). | Highest (it is where the family is) | M / **policy risk** | **Use only for the showroom's customer questions** (allowed use); not as your personal assistant |
| 5b | **WhatsApp: unofficial library** (Baileys, whatsapp-web.js) | A bot that logs in like WhatsApp Web. | [web] Violates WhatsApp's terms; accounts get banned; a vendor-run bot shop reports reply-only bots rarely banned (under 2% a year) and bots that message new people 15-30% (self-interested figures); advice: **use a dedicated number you can afford to lose**. | Highest | M / **high** (you can lose the number; the library breaks when WhatsApp changes) | **Not recommended** for your own or the family's main numbers |
| 6 | **Other messengers** | Signal (a bot through `signal-cli`, needs its own phone number), Matrix (`matrix-nio`, encrypted rooms), Discord. | [web] guides exist; Signal and Matrix are end-to-end encrypted, Discord is not. Telegram's ordinary bot chats are not end-to-end encrypted either **[text: Telegram's end-to-end "secret chats" exclude bots]**. [gap] no 2026 comparison found. | Low in India | M / low-medium | Only if you want a private channel for yourself |
| 7 | **Wearables** | A watch or earbuds via Shortcuts (Apple) or a phone app. | [mine] Comes free with 2a; no separate work. | Low | - | Skip |

## 4. Why WhatsApp is the hard one

Nemo's family lives on WhatsApp (estimates of India's users range from about 535 to over 850 million; Telegram's India base is reported around 84-104 million; the figures are vendor-blog level, directional only **[web]**). So "bring Nemo to WhatsApp" is the obvious wish, and the two roads are bad for a general assistant:

* **The official road is closed to assistants.** Meta's rule targets exactly this case. It may reopen (the EU pressure, the reported test), so **design for it but do not depend on it**.
* **The unofficial road risks the number and breaks without warning.**
* What **is** allowed and valuable: **a showroom WhatsApp for your customers** (price, stock, opening hours, order status) through the official API: a business use. Nemo already has the showroom copilot **[code]**. That one is worth doing when you want it.

## 5. How to build it without rewriting Nemo: "one brain, many doors" **[mine]**

**The problem.** Nemo's brain takes a Telegram-shaped message and answers by calling `send_text`; permissions are decided by comparing the chat id with the owner's Telegram id (about 610 lines). A web or phone request has no Telegram chat.

**The design.**

1. **Identity first (the "pairing").** Every door signs a person in once, and the sign-in ties that device to a Nemo person (you, or a family member) with a one-time pairing code that you approve in Telegram, a passkey on the device, and a revocable token. Family get their own. Nobody is "the owner" because a message arrived on a channel. **Nemo's existing roles (Circle), limits, locked tier and approvals apply identically on every door**: one permission engine, not one per door.
2. **One turn function.** A single internal call `run_turn(person, text, attachments, channel)` runs the *real* Nemo handler as that person (not the plain `web_ai` chat) and returns a stream of events: text as it is written, pictures, files, buttons, approval cards, "done". Telegram, the app, Siri, the desktop app and the call line all call it.
3. **An outbox.** Every message Nemo sends is written once and delivered to the doors that person is using: the app if it is open, a push notification if not, Telegram as the fallback; urgent things to all. The same conversation shows on every device. The hooks exist at a few choke points (the top of the `send_text` chain, `tg`, the ten direct posts) **[code]**; a first version can simply mirror what is sent to Telegram to the app, without touching the 2,660 call sites.
4. **Approval cards as buttons.** Nemo's approval cards come from a channel-neutral registry (Steward 85) **[code]**, so they can appear as buttons in the app, on the desktop and (as text with a reply code) on the phone line.
5. **Security stays outside the model.** Every door is another way in, so: no raw port on the internet (reach the site only over a private network such as Tailscale, or behind Cloudflare Access); passkeys with at least two registered per person and a recovery that does not rely on email or SMS; short-lived sessions; per-device tokens that you can list and cancel; per-door rate limits; and the same rule as before: nothing consequential without your tap **[web]** (passkeys resist phishing because the signature is tied to the domain; recovery by email or SMS is their weak point).

**Staging.**

| Stage | What | Why now |
|---|---|---|
| 0 | **Fix what exists**: a sender allow-list on the phone and WhatsApp webhooks; route the website, the call line and WhatsApp through the real handler as an identified person (not `web_ai` on your memory); a login that does not need Telegram (pairing code + passkey); the site private (Tailscale or Cloudflare Access), bound to localhost. | Closes two real holes and removes the dependence on Telegram. |
| 1 | **The Nemo app**: streaming, voice notes, pictures and charts (Globe and Sigma pictures), approval buttons, family accounts, push, install prompts, an offline queue. | The door every relative can use. |
| 2 | **Voice doors**: the Siri/Action Button recipe, the call line (allow-listed callers, Hindi/Gujarati), push-to-talk. | Hands-free and elder-friendly. |
| 3 | **Nemo Desktop**: the tray app with chat, hotkey and dictation; the typing and clicking (Hands) in stages with approvals and a stop key. | The "typing automatically" part. |
| 4 | **Other doors**: browser side panel, OpenAI-compatible address, MCP server, email-in, optional home speaker. | Reach. |
| 5 | **WhatsApp**, showroom customers only, via the official API. A personal-assistant WhatsApp only if Meta's policy changes. | Policy-bound. |

## 6. Costs, risks and what I could not check

* **More doors, more attack surface.** The biggest risk is not any one door but a door that is weaker than the others. Section 2's webhook with no sender check is the example.
* **Server memory.** The doors are light (a few connections and small messages); the heavy parts (speech, vision, local voices) stay on API calls or on the laptop.
* **Privacy.** Your family's messages would pass through your server on every door; keep each person's memory separate (already true for abilities, not yet for retention) and give them export and delete.
* **Cost.** The app, Siri recipe, desktop app, extension and API door cost nothing beyond the server; calls and WhatsApp messages cost money.
* **Not verified:** Telegram's, Meta's and Twilio's own current pages (the sandbox could not reach them; the sources are secondary); Twilio availability, rules and pricing for an Indian voice number; the iPhone shortcut steps beyond what hobby projects describe; whether a Siri call to a self-hosted address works away from home without a tunnel (it does not on the local network alone); Tasker and Android assistant-role behaviour on your phones; Cloudflare Access and passkeys; every number quoted above.
* Nothing here was run.

## 7. What I need from you

1. **What phones and PCs do the family use** (iPhone, Android, Windows, which)? This decides the door order.
2. **Do the elders need a phone-call line** (talk to Nemo with no app)?
3. **Are you happy to keep Nemo on a private network** (Tailscale on each device) **or do you own a domain** (Cloudflare Access)? Either closes the open port.
4. **Should Telegram stay as your admin channel** (approvals, install cards) while the family use the app? I recommend yes.
5. **Do you want a showroom WhatsApp for customers** (official API; allowed use)?

## Sources (web search results; read as "reported")

* WhatsApp AI policy: [Meta's Business Platform terms](https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform), [respond.io explainer](https://respond.io/blog/whatsapp-general-purpose-chatbots-ban), [dig.watch](https://dig.watch/updates/meta-changes-whatsapp-terms-to-block-third-party-ai-assistants), [EU News (April 2026)](https://www.eunews.it/en/2026/04/15/the-eu-calls-on-meta-to-reinstate-third-party-ai-assistants-on-whatsapp/), [MediaNama (September 2026)](https://www.medianama.com/2026/09/223-meta-ai-agent-whatsapp/), [Chatmitra on India pricing](https://chatmitra.com/blog/whatsapp-ai-agent/)
* Unofficial WhatsApp libraries and bans: [Zylos research](https://zylos.ai/research/2026-01-26-whatsapp-api-automation), [bot.space risk analysis](https://www.bot.space/blog/whatsapp-api-vs-unofficial-tools-a-complete-risk-reward-analysis-for-2025)
* iPhone Shortcuts and Siri: [Shortcuts and a custom endpoint](https://community.rapyd.net/t/making-an-api-request-from-your-iphone-using-siri-shortcuts/44426), [SiriLLama](https://github.com/h2oai/SiriLLama), [Action Button examples](https://matthewcassinelli.com/replace-siri-gemini-action-button-shortcuts)
* PWA push: [MagicBell on iOS limits](https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide), [Chrome Badging API](https://developer.chrome.com/docs/capabilities/web-apis/badging-api)
* Android assistants: [Gemini replaces Assistant](https://9to5google.com/2026/09/28/google-assistant-gemini-android/), [EU opens Android to rival AI](https://www.popularai.org/p/replace-gemini-on-android-eu-rules), [changing the default assistant](https://maketecheasier.com/change-default-digital-assistant-android)
* Desktop apps: [Tauri vs Electron 2026](https://tech-insider.org/tauri-vs-electron-2026/), [Tauri global-shortcut plugin](https://v2.tauri.app/plugin/global-shortcut/)
* Gateways and bridges: [OpenClaw docs](https://docs.openclaw.ai/index), [mautrix](https://pypi.org/project/mautrix)
* Home voice: [Home Assistant Voice PE and wake words](https://community.home-assistant.io/t/how-can-i-use-a-custom-openwakeword-model-with-home-assistant-voice-preview-edition/1019895), [Wyoming voice pipelines](https://botmonster.com/smart-home/home-assistant-voice-pipelines-local-wake-word-wyoming/)
* Alexa and Google: [Alexa deprecations](https://developer.amazon.com/en-US/docs/alexa/ask-overviews/deprecated-features.html), [Gemini for Home](https://9to5google.com/2025/12/08/gemini-for-home-third-party-google-assistant-speakers/)
* Other messengers: [Signal bot with signal-cli](https://www.fast.io/resources/hermes-agent-signal-bot-encrypted-messaging.md), [matrix-nio bots](https://pypi.org/project/simplematrixbotlib/1.6.0)
* APIs: [Open WebUI connections](https://docs.openwebui.com/ecosystem/computer/ai/connect-a-model), [MCP server for Claude Desktop](https://agentgateway.dev/docs/kubernetes/main/integrations/mcp/clients/claude-desktop/)
* Login: [passkeys for self-hosted apps](https://slightfuture.com/security/passwordless-authentication-passkeys-webauthn-2026/), [Tailscale passkeys](https://www.tailscale.com/docs/integrations/identity/passkeys)
* Browser extension: [Chrome Side Panel API guide](https://dev.to/extensionbooster/chrome-side-panel-api-build-a-sidebar-extension-2026-extensionbooster-5gfc)
* India: [Twilio India SMS guidelines](https://www.twilio.com/en-us/guidelines/in/sms), [WhatsApp users in India](https://hyperleap.ai/blog/whatsapp-statistics-india-2026), [Telegram statistics](https://www.grabon.in/indulge/telegram-users-statistics/)
