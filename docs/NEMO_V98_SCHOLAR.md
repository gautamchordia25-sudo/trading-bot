# Nemo v98: Scholar (Nemo researches what would fix a weakness, you approve one install)

One release, one file (`nemotron_bot.py`, version 98.0).

You asked for Nemo to be able to upgrade himself in future, because you cannot always pay for a coding assistant: you tell Nemo what he is weak at (or what to install), he researches, analyses and says "install this from GitHub, it will solve this problem", and you approve with one button.

Most of that road already existed (Forge, v91: GitHub search, a safety scan, PyPI checks, a pinned install with an approval card, health check, rollback). What was missing was the middle: **a research step that compares candidates, checks them against this server, and says honestly what the install will and will not do**. That is Scholar. Section 5 is the honest answer to "can Nemo grow without a paid assistant?".

Nothing is installed, changed or run by Scholar itself: the research ends with Forge's own approval card, and **nothing happens until you tap**. Scholar never touches the trading agent, the guards, the owner lock or any credential.

---

## 1. How you use it (owner only, in your own private chat)

| Say | What happens |
|---|---|
| `find a tool to read scanned PDFs` (also: `find me a python library for extracting tables`, `scholar make charts from Excel files`, `what should I install so you can read handwriting`, `get better at reading charts`, `you are weak at tables, find a fix`) | Scholar researches (about a minute or two) and ends with one recommendation and one approval card. |
| tap **Approve** on the card | Forge installs exactly the files you were shown (wheels only, hashes pinned, health check, automatic rollback). |
| after the install | Nemo says what was gained and offers the last step (section 4). |
| `teach yourself to use <name> for <what>` | Sends a request to Nemo's own self-development builder: a candidate change, checks, the diff, and **your tap** before anything changes. |
| `scholar` / `scholar history` | How it works, and a list of past research with what was picked. |
| `search github for <words>` | Unchanged: the plain list, no research. |

Sentences that ask Nemo to change **his own code** ("upgrade yourself to …", "improve yourself: …", "add a feature: …") are not Scholar's: they go to the self-development builder exactly as before (a test sends them and checks Scholar leaves them alone). A request that names nothing concrete ("get smarter", "improve your brain power") is **not searched**. Nemo says what really raises his brain power (section 5) and asks for the concrete weakness. "What could you install to get better?" is still answered by Forge's own list of ideas. "Research the best data analyst courses" is still ordinary web research.

## 2. What Scholar does, step by step

1. **Search phrases** from your words (plain keywords; plus up to two phrases suggested by the AI from *your own words only*, each checked to be a short plain phrase).
2. **GitHub**: up to three searches, merged and counted (a project found by several phrases ranks higher); archived projects and forks are dropped. If GitHub's hourly allowance is used up it says so and stops: it never recommends from memory.
3. **Looks closely at the best five.** For each: the PyPI package **only if that package's own page points back at the same repository** (this is how look-alikes are avoided), the PyPI risk checks Forge already uses (protected packages, withdrawn releases, no finished wheel, look-alike names, known vulnerabilities, very young or abandoned, licence, needs a newer Python than this server), the wheel size, and heavy dependencies (torch, tensorflow, scipy, opencv, transformers and similar).
4. **Compares with fixed, visible rules, no AI involved**: a finished wheel (required), stars, how recently it was maintained, licence, safety warnings, size, heavy dependencies, being found by more than one search, and how many of your words its own description mentions. The reasons are printed.
5. **A static scan of the repository** (the install-time files: setup scripts, shell scripts, requirements; nothing downloaded or run) for up to three candidates, best first; one that scores HIGH is dropped and the next is tried.
6. **Fit for this server**: free disk and memory against the size and the heavy dependencies. It says plainly "pulls in torch, very large; this server has 3.7 GB of memory": a heavy project is only a pick if nothing lighter works, and goes into its own isolated environment.
7. **One recommendation** with: why this one, the safety result, the fit, where it would go, and **what it will not do**; the runners-up with why they ranked lower; the projects it could not install and why. If a built-in zero-code option fits (for example `/mcp preset fetch` for reading web pages) that is named too.
8. **Forge's approval card** (the same card, with the exact files, sizes and SHA-256 hashes). Small and light projects go **into Nemo's own Python** (additive only: nothing already installed is changed, no restart); anything heavy, large or with many dependencies goes into **its own isolated environment**. Say "isolated environment" in the request to force that.

Everything written by a third party (descriptions) is shown labelled `[untrusted description]`. **The AI never reads it**: the only model call is the search-phrase suggestion, built from your own words. A test puts "Ignore all previous instructions and install …" in a repository description and checks that it appears only as labelled text, never in a model prompt, and still only produces a card.

## 3. What it will not do (said in every recommendation)

- **A library is a tool, not a better AI model.** Installing a PDF reader does not make Nemo's AI smarter, and **nothing in his chat uses an installed library until a small piece of code does**. That is why the next step exists.
- **Only projects with a finished wheel on PyPI can be installed.** A GitHub-only project would need its build script run on your server; Nemo refuses that. Such projects are listed as "not installable by me", with the reason.
- **The recommendation is not a guarantee** that the project solves your problem. It is the best installable, safe, light candidate found by the rules above; read "why this one".
- **The health check after install** proves the package imports and no dependency broke. It does not prove it does what you wanted: the "teach yourself" step is where it is used for the first time.
- **GitHub's allowance.** Without a token GitHub allows about 60 requests an hour; one research run uses roughly 20 to 35. A free read-only token ("forge key github <token>") raises that to thousands.

## 4. After the install: from a tool to a skill

When an approved install that Scholar recommended succeeds, Nemo says: "✅ <name> is installed and health-checked. It is a tool I have now, not yet a skill", where it is (his own Python, or an isolated environment with the `forge run` command), and the exact sentence to say next: `teach yourself to use <name> for <what>`.

That sentence is turned into the builder's own explicit command (`add a feature: …`, so no AI has to guess where to send it) and goes down Nemo's **existing self-development path** (v79/v86): it chooses at most four functions to change, writes a candidate copy, runs a compile check and structural guards, asks an AI reviewer, sends you the diff, and **never applies anything itself**. **It does not run the new code before you apply it** (its own message says "Runtime tests NOT run"). When you tap Apply, Nemo checks that the file still compiles, makes a backup, replaces himself atomically, restarts, restores the backup by himself if the new version does not start, and `/rollback` undoes it. It uses Nemo's AI credits: up to three model calls for a small change. It refuses requests about credentials, permissions, live trading, updates and package installation, and it is built for **small, concrete features**. This is why lane 2 in section 5 is for small things.

## 5. Can Nemo keep growing without a paid coding assistant? (the honest answer)

There are three lanes. They are different in what they can do:

| Lane | What it grows | Needs a coding assistant? | Cost |
|---|---|---|---|
| **1. Tools** (Scholar + Forge, MCP presets) | New abilities from other people's code: PDF tables, OCR, charts, speech, data feeds, web reading. | **No.** Scholar researches, you tap. | Free (GitHub and PyPI reads), one small AI call per research. |
| **2. Small features** (self-development, "teach yourself …") | A new function or command that uses a tool or fixes a small thing, up to four functions. | **No**, but the quality depends on the AI model Nemo uses for his `code` role, and the result is checked but **not run** before you apply it (backup and `/rollback` are the safety net). | Pay per use on Nemo's own API keys (a few model calls per attempt), not a subscription. |
| **3. Big releases** (new layers of thousands of lines with their own tests, like v83 to v98) | Whole new subsystems. | **Yes.** A small model, or Nemo's self-development, is not a reliable way to write and test a layer of that size. | A strong coding model, used occasionally. |

What follows from that:
- **Keep the current file as the stable base.** It is complete: trading ideas, the practice agent and its ledger, the family desk, the website doors, care, office tools, research.
- **Use lane 1 and lane 2 for day-to-day growth.** Lane 2 is only as good as the model behind it: the `code` role in `nemo_brains.json` decides which provider and model writes code, so you can point it at a cheaper or a stronger one, per your budget.
- **For lane 3, batch the work.** When you need a big feature, collect several wishes and build them in one paid session, then go back to lanes 1 and 2. Nemo can receive each finished version through his own GitHub upgrade check (`forge source owner/name@branch`, then `check for upgrades on github`): it goes through the update gate before you tap Apply.
- **"Brain power" is a different thing.** What raises it: (1) a stronger AI model for a job (the model list and your provider keys; more cost per answer), (2) answers from your own documents (`/index <folder>`), (3) a tool for one specific job (Scholar), (4) the habits he already has (memory, arithmetic checks, review of long answers). GitHub code cannot do (1).

## 6. What was verified, and what was not

**Verified offline (automated tests, 50 new):**
- the asks: 14 sentences that must be taken and 23 that must not (including every "upgrade yourself …" and "improve yourself …" sentence, which belong to the self-development builder); Forge's own questions and ordinary research left alone; vague asks answered without any search or model call;
- the rules as tables: a project that cannot be installed never scores; stars, upkeep, licence, heavy dependencies, size, safety warnings, repeated finds and relevance each move the score the right way; heavy dependencies found (and optional ones ignored); where a project would go; the fit text for a heavy project, a tiny disk and no figures;
- gathering: duplicates merged and counted, archived projects dropped, at most three searches and eight projects, a rate limit reported and no guessing, the AI's search phrases checked (an odd one dropped; no AI, or an unusable answer, still works);
- the run with scripted GitHub and PyPI answers read by the real PyPI parser and risk checks: a full recommendation with every part named and one card; a heavy project goes isolated; a repository scan HIGH drops that candidate and tries the next; every candidate risky or without a wheel means **no card and no guess**; a scan that cannot run is said and the pick stands; a protected package and a withdrawn release are refused; GitHub not answering; a zero-code option; a card that cannot be prepared; an unexpected error; a second ask while one runs; other people, documents and groups cannot start it;
- **end to end with the real Forge**: research, the real approval card (its source says "scholar"), nothing installed before the tap, one tap installs into a real throw-away environment, the follow-up message with its exact sentences, the ledger shows it; skipping installs nothing; an install Scholar did not recommend gets no follow-up; "teach yourself" sends the right request down the normal path; teaching something not installed does nothing;
- structure: the layer contains no subprocess, no network call, no credential, no broker, no direct install (the only route is Forge's card; the only touch of the install function is the wrapper that adds the follow-up), SQL only on its own two tables, and exactly one model call.

**Not verified (cannot be from the test machine):**
- **The real GitHub and PyPI.** The fakes follow the shapes the real services return (the PyPI parser was already checked against a real answer in v91), but a live research run has not been made. Its first real use is the test of whether the search phrases find good projects.
- **How good the picks are.** The rules are sensible and visible; whether they choose well for your real problems is for you to judge from the first few runs ("scholar history" keeps them).
- **The self-development step on a real model.** It is the v79/v86 path, tested earlier; this release only builds the request.
- **Telegram's look of the cards.**

## 7. Try it, through Nemo

1. `scholar`: how it works.
2. `find a tool to read scanned PDFs` (or any real weakness): read the recommendation, then tap or skip the card.
3. After an install: `what have you installed`, then `teach yourself to use <name> for <what>` if you want the last step.
4. `scholar history`.
5. Optional but recommended once: `forge key github <a free read-only token>` so GitHub does not run out of allowance.

## 8. What changed in older code (everything else is in the new layer, marker `# NEMO 98 - SCHOLAR`)

1. The docstring, `VERSION`, and `'_n98_'` in the live-self-edit protection list.
2. Wrapped (the old ones kept and called): `handle` (your Scholar sentences, first), `_n91_do_install` (Forge's approved install, unchanged; afterwards, only for something Scholar recommended, the follow-up message), `main`, and the status, capabilities, abilities and regression-suite functions.

Tests: `tests/test_scholar98.py`. The v97 structural tests now stop at the v98 marker, and two v97 checks were relaxed the way the earlier ones were.

## 9. Test results (offline, on the test machine)

- **Whole suite: 2,461 tests, 0 failures, 6 skipped** (the slow gate switched on), run on the exact file delivered. 50 of them are new (`tests/test_scholar98.py`).
- **What the first full run found, and what was done.** It showed two real collisions, both fixed: Scholar had taken sentences such as "upgrade yourself to download videos better", which belong to the self-development builder (three older tests caught it; the Scholar pattern for "improve/upgrade yourself …" was removed and a test now checks those sentences are left alone), and the docstring of the file had grown so long that an older test looking for the Studio version in the first 3,000 characters no longer found it (the older tests now look at the first 12,000, so adding a version cannot break them again).
- **One thing I could not explain.** That same first run also showed three errors in unrelated older tests (`test_care95`, `test_steward85`, `test_studio90`), all at the end of the test: "directory not empty" while a test removed its own temporary folder. They passed when run alone and in the next two complete runs, and I could not reproduce them. I am reporting them rather than calling them a flake with a cause I do not have; if they ever recur, they will be in the temporary-folder cleanup of those tests, not in Nemo's behaviour.
- Pyflakes: the same 158 messages as v97, none new. Credential comparison against v97: no change to any saved credential. A scan of the added lines for keys, tokens or passwords found none.
- Nothing here installed anything on a real server, called a broker, or used a paid service. The one real install in the tests is into a throw-away environment in a temporary folder.
