# Nemo v102.0 "Hearth": a local brain

You asked for an offline AI brain: an open model (Llama or an alternative) on hardware you own, so Nemo keeps answering when the cloud brains are out of quota or down, so a private question never reaches a cloud AI, and so simple questions cost nothing. This release builds it (item O4 of the master list). Which model to run, whether to buy anything, and the install steps are in `NEMO_LOCAL_BRAIN_GUIDE.md`.

## 0. Read this first (the honest version)

* **Built and tested offline; not yet run on your hardware.** The tests start a small model server inside the test (it speaks Ollama's protocol and the OpenAI-style one), serve the real website on the loopback address, and run the real relay script text you will be sent. Nothing in them touched Ollama, Windows, your laptop, Telegram or the internet.
* **A small local model is not the cloud model.** It is weaker, slower on a CPU (reported 8 to 15 tokens a second for an 8B model on a modern CPU), has no internet and no tools, and can get sums wrong. Hearth tells the model so, shortens the answer to what can arrive in time, and tells you which brain answered.
* **"Offline" here means independent of the cloud AI companies, not of the network.** Nemo itself still reaches your laptop over the internet (the laptop calls out to Nemo's website). If the server has no network at all, Telegram does not work either.
* **While you are offline, Nemo does not learn new facts from your messages** (the memory step is a cloud helper call and is skipped), and tools that need the internet (search, market data, pictures, voice-note transcription) still need it.
* Owner only. The family keep the cloud chain exactly as before.
* No order, no trading agent, no guard, no owner lock, no credential is touched.

## 1. What it does

| Situation | What happens |
|---|---|
| **AUTO** (the default once a computer is connected) | The cloud brains first, exactly as before. When they fail (a provider's limit, an error, everything cooling down, or "my brains are all busy") the local brain answers instead of the request ending, with **one notice per outage** (not one per answer). Not after a refusal, a cancellation, an exhausted time budget, an oversize input or an unsupported input. |
| **`private: <question>`** | Answered by the local brain **alone**. It does not go through the conversation engine, the tools, the memory clerk, a search or any cloud AI, and the answer is not added to the shared conversation history. A follow-up works because private questions have their own small history (`forget my private chat` wipes it). If the local brain cannot answer, Nemo says so and sends nothing anywhere else. |
| **`go offline`** | Every answer to a chat message comes from the local brain; Nemo's JSON helper steps (tool scout, memory clerk, critic) are skipped; no cloud AI is asked. `go online` returns to AUTO. Refused if no local brain is connected. |
| **`local brain for simple questions on`** (off by default) | Short everyday questions (under 280 characters, no live data, mail, files, code, links, figures) go to the local brain first (free, no quota) and to the cloud only if it fails. |
| **Pictures, the code writer, connection tests** | Never touched: they use the cloud as before. |

## 2. What to say

`local brain` (status) · `local brain help` · `local brain setup` (your laptop or any home computer: I send a small file) · `local brain connect http://100.64.0.5:11434 [model]` (a model server I can reach) · `test local brain` (one timed question with an arithmetic check) · `local brain model qwen3:8b` · `which local model should I use` · `private: <question>` · `go offline` / `go online` · `local brain for simple questions on|off` · `local brain fallback on|off` · `local brain notices on|off` · `local brain on|off` · `local brain remove <name>` · `forget my private chat`.

## 3. How it connects

* **Relay (recommended).** `local brain setup` creates a one-time code (15 minutes) and sends `nemo_hearth_relay.py`. The computer runs it; it calls Nemo's website every few seconds ("is there a question for me?"), answers with Ollama on `127.0.0.1`, and posts the answer back. **Nothing listens on the laptop, nothing is installed on the server, no router setting, no VPN.** It needs Nemo's website on an `https` address (`/setdomain`), and refuses to run against plain http to a public address. The script contains no way to run a command, open a port or reach another address (a test reads its source for that), and a job cannot change where it connects.
* **Direct.** `local brain connect <address>` for a model server the server can reach (Ollama, llama.cpp's server, LM Studio). Plain http is accepted only for your own network (this machine, a private range, a Tailscale address, `.local`, `.ts.net`); anything else must be `https://`. Paths, logins inside the address, link-local and cloud-metadata addresses are refused.
* **Safety of the relay.** Only a computer enrolled with a Hearth code can collect questions (an ordinary enrolled device cannot); a removed computer's key is cancelled; questions are sent only over https or inside your own network; a failed key triggers the website's existing block on repeated refusals; at most three long-polls run at once; **questions and answers are held in the server's memory while they travel and are never written to disk** (a test searches every file for them).

## 4. How the choice is made (for the curious)

* The one gateway all chat answers pass through (Brain73's request function) is wrapped, so the Cortex conversation, the older chat path and anything else that asks the gateway behave the same. **`ask_ai` itself is deliberately not wrapped**: an older safety check (v51: an explicit model choice is authoritative) needs it to stay exactly as it is, and the first full test run caught that. The older chain is still covered because the owner's answers reach the gateway first. What this leaves uncovered: if Brain73 is switched off or has no key (so everything goes to the oldest provider chain), neither the fallback nor offline mode applies; Brain73 is on by default. Pictures, the code writer, other people and JSON helper steps are never touched.
* What is sent: the persona, the date, what Nemo remembers about you, live figures if given, the last turns and the question, cut to about 14,000 characters, with a note telling the model what it is and what it cannot know. Qwen3 models get their "no long thinking" switch; reasoning blocks are stripped from answers; an unfinished reasoning block counts as no answer.
* How long: the answer length is limited to what can arrive in time at the measured speed (6 tokens a second until one answer has been timed), so a slow machine gives a shorter answer instead of a timeout. A model that has to be loaded takes longer on the first question after a pause.
* One question at a time per computer; a direct node that fails three times is left alone for a minute; every answer leaves a receipt in the existing brain log (provider "local", model, speed; never the text).

## 5. What I did not do

* No local brain on the VPS (3.8 GB memory, swap nearly full).
* No tools for the local brain, no voice, no pictures.
* No local brain for the family.
* No automatic model download or install on your computer; the relay never runs a command.
* The older `/localnode` and `/hybrid` commands are unchanged and separate.
* The "Offline" release (a provider-health pulse, a queue of questions that failed, local answers from Nemo's own data) is still parked.

## 6. Verified and not verified

**Verified offline (109 new tests, `tests/test_hearth102.py`):** address rules (accepted and refused); prompt fitting (the question always kept, size bounded, newest turns kept, long system text cut in the middle); reasoning-block stripping; which calls may use the local brain; both protocols; speed measurement; model choice; failure handling and the one-minute rest; the busy lock; the relay's two website calls (only a Hearth computer with the right key, https or own-network only, another computer never gets or answers a question, a late second answer ignored, timeouts, nothing on disk); enrolment (one use, expiry, removal cancels the key); the real script end to end against the real website and a fake model server; the script's refusals and its source (no listening, no commands, no evaluation); the gateway in every mode (fallback with one notice and a receipt, no fallback after refusals or when switched off, helpers never local, pictures and the code writer pass through, owner only, offline never asks the cloud, simple questions first); a whole Cortex turn with every cloud call failing, and in offline mode with none made; `ask_ai` left alone (a test and a regression row guard v51's contract) yet still ending in a local answer through the gateway, and answering in offline mode with no cloud call; `private:` with a network **tripwire** (any address but the local model's, the cloud gateway, the older chain, every older AI function and the search fail the test) and its separate history; every phrase and the ordinary sentences that must not match; owner-only and private-chat-only; structure (no order, broker, guard, owner lock, command execution or evaluation; no cloud AI call in the layer; one network call site; only its own three tables).

**Not verified (you will be the first to see):**
* Anything on real hardware: Ollama's real behaviour (the `num_ctx`, `keep_alive` and `/no_think` settings are the documented ones but unproven here), real speed and quality, Hindi and Gujarati answers, Windows, a laptop that sleeps, Python on your laptop.
* The relay through your real https address (a Cloudflare tunnel passes `X-Forwarded-Proto`; the code relies on it) and under the production web server (each long-poll holds one of its threads for up to 15 seconds).
* The wording of the notices on your phone.
* Setups where Brain73 is off: see section 4.

## 7. Try it, through Nemo

1. `local brain help`, then `local brain setup` and follow the six steps it prints (and `NEMO_LOCAL_BRAIN_GUIDE.md`).
2. `local brain status`: the computer should show "online". Then `test local brain`: it should say "42" and give a speed. Tell me the speed and the model.
3. `private: write two lines of thanks to my cousin` and read the footer ("answered on your own computer").
4. `go offline`, ask something simple, then `go online`.
5. Close the laptop lid and ask something: Nemo should use the cloud (or tell you the local brain is not reachable for a `private:` question).
6. To see the fallback, wait for the next time the cloud brains say "busy" (or `local brain for simple questions on` to use it on purpose).
7. Ask a Gujarati question you know the answer to, and tell me how it did.

## 8. What changed in older code (everything else is in the new layer, marker `# NEMO 102 - HEARTH`)

Two lines: the docstring's first line and the protected-names list (`_n102_` added). The layer wraps `handle`, the gateway request function, the web-app builder (two routes), the device-enrolment claim (to mark a Hearth computer), `_n82_capabilities`, `prime_regression_suite` and `main`, and reuses the existing `_N991_REFUSE` set (two more codes). It does **not** wrap `ask_ai`. In the tests: one Globe test now ends its slice of the file at this layer's marker, three Globe assertions about the version and the protected list were loosened as at every release, and the family-download test no longer resolves a real host name (it failed on the unchanged v101 file too once this sandbox lost DNS; it passed in the v101 run).

## 9. Test results (offline, on the test machine)

- **Whole suite on the exact file delivered (the slow gate switched on): 3,186 tests, 7 skipped, 0 failures.** 109 of them are new (`tests/test_hearth102.py`); the earlier 3,077 all pass.
- **What the first full run caught, and what I did about it.** It was not clean the first time: (1) an older safety check (v51: an explicit model choice is authoritative) needs `ask_ai` to stay the v69 function, and my first draft wrapped it, so I removed that wrapper and moved the whole job to the gateway (section 4); (2) a blunt test for 48-bit keys flagged a 48-bit question id, now 64-bit; (3) three Globe assertions pinned the exact version, docstring and protected-names text, now loosened as at every release; (4) the Globe family-download test failed because its link check resolves a real host name and this sandbox has no DNS any more: it fails the same way on the unchanged v101 file, so I made the test stub that one check. The final run above is on the final file.
- Pyflakes: the same 158 messages as v101, none new. A scan of the 1,345 added lines for keys, tokens or passwords found none. Only two lines of older code were edited (the docstring's first line and the protected-names list); the layer is appended.
- Nothing here placed, changed or simulated an order, called a broker, called a cloud AI, ran Ollama, or used a paid service. The AI calls in the tests are scripted and the network tests use only the loopback address.
