# A local brain for Nemo: which model, what to buy (if anything), and how to install it

You asked: *"make O4 real; the laptop has 16 GB, but I would like to buy 16 GB of RAM cheaply online for Llama so Nemo has its own offline brain and abilities; or an alternative to Llama that we can install in Nemo, tell me how."*

O4 is built: it is **v102.0 "Hearth"** (see `NEMO_V102_HEARTH.md` for what it does and how it was tested). This page answers the rest: what to run, what hardware, and the exact steps.

Evidence tags: **[web]** a web-search result (blogs, vendor pages: weak, treat numbers as "reported"; links at the end); **[code]** I read it in `nemotron_bot.py`; **[mine]** my judgement or arithmetic; **[gap]** I looked and could not confirm it. My sandbox has no internet route to your laptop, so **nothing here was run on your hardware**.

---

## 1. The short answers

1. **Do not buy anything yet.** Your laptop already has 16 GB. An 8-billion-parameter model squeezed to 4 bits is about 5 GB [web: one source gives about 6 GB in use for Qwen3 8B], so it fits beside Windows with room to spare. Try the laptop first; it costs nothing.
2. **You cannot add a RAM stick to the server.** The server is a rented slice of a machine. The cloud equivalent is a bigger rented plan, paid every month. I could not find a verified 16 GB Mumbai plan price (the only source was a seller's own blog, with entry plans of 1 to 2 GB from about $5 to 7 a month) **[gap]**.
3. **RAM only decides which model fits; it does not make the model smarter or faster.** Speed on a CPU depends mostly on memory bandwidth (how fast the memory can be read) **[mine, general knowledge]**: two 8 GB sticks (dual channel) read about twice as fast as one 16 GB stick. A bigger model needs more RAM and is slower, not faster.
4. **Buy hardware only if the laptop is the problem**: it sleeps, you travel with it, or you need it for work while Nemo thinks. Then the sensible purchase is a **refurbished business mini PC with 16 GB or more**, not loose RAM (section 5).
5. **Llama is one choice among several.** For a 16 GB machine the models people report as best are Qwen3 8B, Gemma (12B), Llama 3.1 8B, and, tight on 16 GB, OpenAI's open gpt-oss-20B (section 3). None of them is "Nemo's brain": Hearth uses whichever you install, and you change it with one sentence.
6. **Expect a helper, not a replacement.** A local 8B model is far weaker than the cloud models Nemo normally uses, slower (reported about 8 to 15 tokens a second on a modern CPU for an 8B model **[web]**), has no internet, and may get sums wrong. It is for outages, privacy and simple questions.

---

## 2. Where the model can run, compared

| Option | Cost | Always on? | Privacy | Notes |
|---|---|---|---|---|
| **Your 16 GB laptop (relay)** | ₹0 | Only when awake | Best: questions go to your own machine | Windows may sleep; set "never sleep when plugged in". Nemo falls back to the cloud (or says so) when it is off |
| **A second home PC / mini PC (relay)** | refurbished 16 GB mini PCs listed about ₹20,000 to ₹37,000; a new Intel N150 mini PC with 16 GB about ₹31,999 [web, Smartprix June 2026 and Refurbo; check current prices] | Yes | Best | Same relay file, run on that machine. A low-power N150 is likely slower than your laptop **[mine, not measured]**; prefer an older i5/i7 mini PC with two memory sticks |
| **A bigger rented server (direct address)** | monthly rent [gap: price] | Yes | Your questions go to a company's machine, but it is your private server | Nemo connects with `local brain connect https://…` or a private (Tailscale) address. Never leave the model server open to the internet (see section 6) |
| **Oracle's free ARM server** | ₹0 | Yes | Private server | Reports conflict on the free size (some say cut from 24 GB to 12 GB in June 2026) and free capacity is often unavailable; ARM CPU only [web] **[gap: Mumbai availability]** |
| **Nothing local: Llama in the cloud** | pay per use | Yes | Not private | Nemo already has Llama through Groq and Cerebras as backup cloud brains [code]; reported hosted prices about $0.23 to $0.90 per million tokens for Llama 3.3 70B [web]. It does not make Nemo independent of the internet |

RAM prices: reports say a memory shortage (AI demand) is pushing device prices up by as much as 35 percent in 2026, one Indian report puts a 32 GB kit at ₹25,000 and above (up from ₹8,000 to ₹10,000) **[web, unverified against a primary source]**, and one forum user paid about ₹2,200 for a used 16 GB DDR4 stick **[web, an anecdote]**. So "cheap RAM" is not what the market looks like right now; check live listings.

---

## 3. Which model (Llama and the alternatives)

For a 16 GB Windows laptop. Sizes are for the usual 4-bit builds and are approximate **[web]**. Ollama names are what you type with `ollama pull`; run `ollama list` to see what you have, and check the library page for current names.

| Model (maker) | Ollama name | Size in memory | Good at | Watch out |
|---|---|---|---|---|
| **Qwen3 8B** (Alibaba) | `qwen3:8b` | about 5 to 6 GB | The all-rounder most guides pick at this size; reported 8 to 15 tokens a second on a modern CPU. Hearth adds its "no long thinking" switch for you | I found no Gujarati test of it |
| **Gemma** (Google), 12B size | `gemma3:12b` (a newer Gemma 4 12B is reported at about 7.4 GB; check the library for its name) | about 8 GB | The Gemma family (27B size) led a Hindi function-calling leaderboard I found; the 12B was not on it | Slower; sharing memory with Windows gets tight |
| **Llama 3.1 8B** (Meta) | `llama3.1:8b` | about 5 GB | Steady English; widely supported | Weaker in Hindi; Meta's community licence |
| **Llama 3.2 3B** (Meta) | `llama3.2:3b` | about 2 GB | Fast on a weak or busy machine | Short, simple answers only |
| **Phi-4-mini** (Microsoft) | `phi4-mini` | about 3.5 GB | Small and quick | Positioned for weaker machines, not for capability |
| **gpt-oss-20B** (OpenAI, open weights) | `gpt-oss:20b` | about 12 to 13 GB | Strong reasoning and tool use for its size; only about 3.6 B parameters active per token, so it should be faster per token than a dense 20 B model | **Tight on 16 GB** (OpenAI's own card assumes 16 GB dedicated to the model); reports of very slow results on 16 GB Macs; best with 24 to 32 GB [web] |
| **Sarvam 30B** (Sarvam AI, India) | not confirmed | about 19 GB at 4-bit for the 30B (Q4_K_M file) | Built for 22 Indian languages; 2.4 B parameters active; Apache-2.0 reported | Support in llama.cpp / Ollama was not merged as of March 2026 and I could not confirm it since **[gap]**; too big for 16 GB at good quality. Its small Sarvam-2B is licensed for non-commercial use only |

**Hindi and Gujarati.** I found one public Hindi test (a function-calling leaderboard, where Gemma 3 27B scored highest) and **no public Gujarati test of any of these models** **[web, gap]**. A paper also found that small models often pick the right tool but fill in its arguments in Hindi, which breaks the call **[web]**: another reason Hearth never lets the local brain run tools. So: install Qwen3 8B first, then ask it three Gujarati questions you know the answers to (`test local brain` times it; ask in Gujarati yourself). Change model with "local brain model gemma3:12b".

**Licences.** For you alone, all of them are fine. If you ever make a public product, read each licence: Llama's is a custom Meta community licence (commercial use with conditions), Sarvam-2B is non-commercial, and the others are reported as permissive **[web, check each page]**.

---

## 4. Install, step by step (Windows laptop)

Nothing here needs a router setting, a VPN or a command on the server. **I have not been able to run these steps on your laptop; if a step fails, send me the exact words it prints.**

1. **Python.** Open a terminal and type `python --version`. If it is missing, install Python from python.org (tick "Add to PATH"). The relay uses only Python's built-in libraries.
2. **Ollama.** Install it from ollama.com/download and open it once. It runs in the background and listens only on `127.0.0.1:11434` (this computer) by default; do not change that.
3. **The model.** In a terminal: `ollama pull qwen3:8b` (about 5 GB). Test it: `ollama run qwen3:8b "say hello in one line"`. Type `/bye` to leave.
4. **Ask Nemo for the relay.** In Telegram say: `local brain setup`. Nemo sends a file, `nemo_hearth_relay.py`. (Nemo needs its website on an `https` address first; if it says so, send `/setdomain`.)
5. **Run it.** Save the file somewhere permanent (for example your user folder) and run `python nemo_hearth_relay.py`. It prints that it is running and which models it sees. Leave the window open. The code inside works once and expires in 15 minutes; after the first run the laptop keeps its own key in `~/.nemo_hearth.json`.
6. **Check.** Say `local brain status`, then `test local brain`. It should answer "42" and give a speed.
7. **Keep it running.** To start it when you log in, from a terminal: `schtasks /create /tn NemoHearth /sc onlogon /tr "pythonw %USERPROFILE%\nemo_hearth_relay.py"` (adjust the path). In Windows power settings set "Sleep: never" while plugged in, or the laptop will drop off and Nemo will use the cloud.
8. **Try the three uses.** `private: what should I get my wife for our anniversary` (answered only on your laptop), `go offline` then a question (then `go online`), and, to see the fallback, nothing to do: it happens by itself when the cloud brains fail, with one notice.

To stop it for good: say `local brain remove laptop` (this cancels its key) and close the window.

**If you later rent a bigger server for the model** (or put a mini PC on a Tailscale address): install Ollama there, make it listen on the private address only, and in Telegram say `local brain connect http://100.x.y.z:11434` (plain http is accepted only for your own network; a public address must be `https://`). Do not publish the port to the internet (next section).

---

## 5. If you do decide to buy

- **Check the laptop first** with `test local brain` for a week. If the answer speed is acceptable and the laptop is on when you need Nemo, you are done.
- **Always-on box:** a refurbished business mini PC (HP EliteDesk / ProDesk Mini, Dell OptiPlex Micro, Lenovo ThinkCentre Tiny) with **16 GB, two sticks if possible**, an SSD, and an 8th-generation Intel i5/i7 or newer. Listed prices I found: about ₹20,000 to ₹37,000 **[web]**. Run Windows or Linux; the relay runs on either. If you may want a bigger model later, choose a model whose memory can be upgraded (and watch the RAM prices above).
- **Do not pay for a graphics card** for this: I did not research GPU prices, and a plain CPU box is enough for a helper that answers a few questions a day **[mine]**.
- **A 32 GB machine** is what makes gpt-oss-20B comfortable; it is not needed for the 8B models.

---

## 6. Safety notes

- **Ollama has no login.** A scan reported about 175,000 Ollama servers exposed to the internet with no protection, being used by strangers [web]. With the relay nothing listens on your laptop except Ollama on `127.0.0.1`, which only that computer can reach. Check: `netstat -ano | findstr 11434` should show `127.0.0.1:11434`, never `0.0.0.0:11434`.
- **The relay file** can do one thing: ask the local model a question and send the answer back. It cannot run a command, open a port or reach another address (a test reads its source for that). Questions and answers pass through the server's memory and are not written to disk.
- **Private means private from the cloud AIs, not from the server.** A `private:` question and its answer are kept in a small table on the server (so a follow-up works) until you say `forget my private chat`. The server is yours.
- **Do not paste secrets** (passwords, card numbers) into any assistant, local or not.

---

## 7. What I could not verify

- Everything on your hardware: the speed of any model on your laptop, whether Python and Ollama are set up, whether Windows sleeps, and whether your website has an `https` address.
- Gujarati quality of every model above, and Hindi quality beyond one function-calling table.
- Current prices of RAM, mini PCs, and any 16 GB cloud plan.
- Whether Ollama or llama.cpp now run Sarvam's models, and the exact Ollama names of the newest Gemma.
- The licence terms in detail.

---

## Sources (web search results; read as "reported")

- Running gpt-oss-20B: [hardware requirements (IntuitionLabs)](https://intuitionlabs.ai/articles/hardware-requirements-gpt-oss-20b), [TechRadar guide](https://www.techradar.com/ai-platforms-assistants/chatgpt/how-to-run-openais-gpt-oss-ai-models-on-your-laptop), [Micro Center](https://www.microcenter.com/site/mc-news/article/can-your-pc-run-gpt-oss-ai.aspx), [Unsloth guide](https://docs.unsloth.ai/basics/gpt-oss)
- Models for 16 GB: [Micro Center guide to local LLMs](https://www.microcenter.com/site/mc-news/article/best-local-llms-8gb-16gb-32gb-memory-guide.aspx), [best local LLM for 16 GB](https://atomic.chat/blog/guides/best-local-llm-16gb), [Gemma 4 vs Llama vs Mistral tool calling](https://machinelearningmastery.com/comparing-local-tool-calling-gemma-4-vs-llama-3-vs-mistral/), [Hindi function-calling leaderboard (BFCL-Hi)](https://www.emergentmind.com/topics/bfcl-hi)
- CPU speed: [local LLMs without a GPU (It's FOSS)](https://itsfoss.com/testing-local-llms-without-gpu), [running llama.cpp](https://computingforgeeks.com/run-local-llm-llama-cpp/), [CPU-only LLM guide](https://www.promptquorum.com/local-llms/best-cpu-only-llm)
- Indian-language models: [Sarvam 30B and 105B](https://www.opensourceforu.com/?p=97113), [Sarvam-2B](https://www.maginative.com/article/sarvam-ai-launches-open-weights-sarvam-2b-model-and-suite-of-ai-products-for-indian-languages/), [Sarvam 30B GGUF](https://huggingface.co/deepak-p-yadav/sarvam-30b-IQ2_M-indic)
- Hardware prices: [mini PC prices (Smartprix)](https://www.smartprix.com/computers/mini-type), [refurbished mini PCs (Refurbo)](https://refurbo.in/collections/buy-refurbished-mini-pcs), [refurbished Dell mini PCs (Edify)](https://edify.club/blog/4-best-refurbished-dell-mini-pcs-in-india/), [device prices and the RAM shortage (Storyboard18)](https://www.storyboard18.com/amp/digital/laptop-desktop-prices-may-rise-up-to-35-as-ram-costs-surge-and-chip-supply-tightens-91832.htm), [why RAM prices are rising in India (CloudPe)](https://www.cloudpe.com/blog/why-is-ram-pricing-increasing-in-india-heres-what-businesses-need-to-know-in-2026/), [cheap VPS in Mumbai (a seller's blog)](https://valebyte.com/en/blog/cheap-vps-in-india-mumbai-2026-price-comparison/)
- Free ARM server: [Oracle free tier cut, 2026](https://braindetox.kr/en/posts/oracle_always_free_tier_reduced_2026.html), [the OCI free tier explained](https://selfhost.it.com/blog/oci-free-tier-breakdown)
- Ollama security: [175,000 exposed Ollama servers (Twingate)](https://www.twingate.com/blog/ollama-server-exposure), [Ollama security guide](https://serverman.co.uk/ai/ollama/ollama-security-guide/), [Ollama over Tailscale](https://www.serverman.co.uk/ollama/ollama-tailscale-remote-access/)
- Hosted Llama prices: [Meta Llama hosted pricing (May 2026)](https://www.aipricing.guru/meta-llama-pricing/)
