# Nemo v91.1 "Forge": Nemo can use GitHub and install the programs he needs, so he can upgrade himself

> **v91.1** (same day): found while researching which programs to recommend (see `NEMO_FORGE_PICKS.md`). Programs that ship as a plain file inside the wheel instead of an entry point (**ruff**, the one I needed first) were installed but could not be run: `forge run` did not know about them. v91.1 reads them, with a test that builds such a wheel, installs it and runs it, and a live check with the real ruff.

You asked for a more powerful Nemo who can reach GitHub and install the programs he needs to upgrade himself.
Everything from v90 (Studio) and earlier is kept. Your credentials, owner lock, trading and holiday guards, existing permissions and approvals, backup and
rollback are untouched (the edits to older code are listed in section 3). Nothing is installed, upgraded or applied without your tap, and no key or token is
ever printed, logged or put in a link.

## 1. What I found first (by reading the v90 file, not by guessing)

1. **GitHub: Nemo could not look at it at all.** No search, no repository card, no README, no file list, no releases, no way to see whether a newer Nemo exists.
2. **Installing was done by two blunt tools.**
   - `auto_install()` pip-installs a missing module into Nemo's own Python by name (core packages are protected). It leaves no record, has no undo, and runs
     whatever the package's build script does.
   - `/toolenv install <name> <package...>` runs `pip install <whatever you typed>` in a side environment: no inspection, no check that it is the package you
     meant (look-alike names are a common attack), it follows every dependency, and it can run the package's own build script on your server.
3. **Nothing pinned what was installed.** What you were told and what pip fetched a minute later could differ; nothing could be taken away again.
4. The v86 self-development guard (rightly) refuses anything about installing, so there was no safe path for Nemo to gain a library on request.

## 2. What v91 adds

### 2.1 GitHub eyes (read-only; a token is optional)

Only you, in your private chat. Plain words work; the slash forms work too.

| You say | What happens |
|---|---|
| `search github for pdf table extraction` | the best-starred matches (archived and forks left out), each with stars, language, licence, last push. Descriptions are marked **untrusted text**. |
| `inspect owner/name` (or `inspect 2` after a search) | repository card: stars, forks, issues, licence ("NO LICENCE STATED" when missing), last push, archived, latest release, start of the README. |
| `scan owner/name` | reads only the install-time files (setup.py, pyproject, requirements, install scripts, package.json…) and the file list, and greps for risky patterns: pipe-to-shell, reading SSH keys, hidden decoded code, cron/start-up edits, shell calls, compiled files, `.pth` files. Reports LOW / MEDIUM / HIGH. **Nothing is downloaded to disk or run.** It says plainly that a scan cannot prove safety. |
| `readme of owner/name`, `files of owner/name` | the README (untrusted) and the top-level file list. |
| `pypi NAME` | the PyPI report and the same risk check the install uses (section 2.2). |

* GitHub is only ever **read**. No write, push, comment or star call exists in the code (a test enforces it).
* Only four named hosts are ever opened, over https only: `api.github.com`, `raw.githubusercontent.com`, `codeload.github.com`, `pypi.org`. A redirect to anything else is refused; the token is sent only to `api.github.com`, never to the other hosts, never through a redirect.
* **Failures are explained in words:** rate limit (with the reset time and the hint to add a token), bad token, not found / private, search not accepted, GitHub trouble, timeout, no route, **and "the network between this server and GitHub blocked it" when the refusal did not come from GitHub itself** (it names the four hosts to allow if your VPS limits outgoing sites).
* Results are cached for two minutes, so a conversation does not spend the allowance twice.
* `forge key github <token>` saves the token in the protected secrets file (any read-only token is enough), **deletes your message**, tests it, and never repeats it. A rejected token is not kept. A network block is not mistaken for a bad token.

### 2.2 Safe installs: what you approve is exactly what is installed

`install NAME` · `install NAME into yourself` · `install NAME as a tool` · `install NAME big` · `pip install NAME` · `install 2` (after a GitHub search).

1. **PyPI risk check** before anything is downloaded: protected packages are refused; a withdrawn (yanked) version; a package with **no finished wheel** (installing it would run its build script on your server, so it is refused); a name **one edit away from a popular package** ("reqeusts", "requestz") unless it is clearly established; known vulnerabilities, very young, long abandoned, few releases, no licence, copyleft licence, an archived GitHub project, a Python version this server does not run.
2. **Wheels only** (`pip download --only-binary=:all:`): no build script ever runs. The files are fetched into a private staging folder, and a plan is made: every file with its size and **SHA-256**, what is already installed and left alone, what the programs it adds are called, the total size (300 MB cap, 1.5 GB with `big`), at most 40 new packages, at least 1 GB of free disk.
3. **An approval card** (the existing v85 cards: Approve / Skip, risk "high") shows all of it. Nothing happens until you tap.
4. **At approval the checks run again against the same files:** the SHA-256 of every file, no other file in the folder, and (for "into yourself") that what was installed when the card was made is still exactly there. pip is then given **only the approved files** with `--no-index --no-deps`, so it cannot fetch or resolve anything else.
5. **Two targets:**
   * **its own isolated environment** (default; `/root/nemo_envs/<name>`, mode 700, always a fresh one): cannot touch Nemo's packages. Programs it adds run with `forge run <name> <program> …`.
   * **into yourself** (a library Nemo's own code imports): **additive only.** The download is pinned to the versions already installed; a package that needs a different version of something installed is refused, and nothing already installed is ever changed. No restart needed.
6. **Health check and automatic rollback:** the new environment must list the package, no dependency problem may appear that was not there before, and the package must import. On any failure what was added is removed again (an isolated environment is deleted) and you are told why.
7. **A ledger** (`forge91_item` in Nemo's database) records what was added, where, with which hashes. `what have you installed` shows it; `remove NAME` takes it away (shared packages another install also added stay); the card's undo does the same.
8. **Never touched, whatever the card says:** `requests`, `urllib3`, `certifi`, `numpy`, `pandas`, `pillow`, `matplotlib`, `cryptography`, `fyers-apiv3`, `python-telegram-bot`, `httpx`, `anthropic`, `yfinance`, `pip`, `setuptools`, `wheel`, `pydantic` and the rest of the protected list (plus everything v82's `CORE_PROTECTED_MODULES` already protected).
9. **One install at a time.** Downloaded files nobody approved are deleted at the next start-up once they are three days old (an approval card expires after three days too).

`forge allow NAME` lets Nemo's own proposals for that one package go through without a tap (never for protected names, never for what you type yourself, and you are told each time). `forge disallow NAME` undoes it.

### 2.3 System programs (apt), root only

`install ffmpeg on the server`. An **allow-list** (ffmpeg, git, tesseract-ocr, poppler-utils, imagemagick, unzip, zip, jq, sqlite3, fonts, ghostscript, pandoc; add more yourself with `forge apt allow NAME`). It **simulates first** (`apt-get -s`), refuses anything that would upgrade or remove an installed package, shows the card with the download/disk size, installs with `--no-install-recommends`, checks with `dpkg`, and records it. Not root → it says so and does nothing. `remove NAME` removes exactly the named packages (no autoremove).

### 2.4 Upgrade Nemo from your GitHub repository

`forge source owner/name@branch:path` once (path defaults to `nemotron_bot.py`), then **`check for upgrades on github`** (or `forge upgrade`, `forge upgrade --force`).
It reads the newest commit, fetches the file, checks that it looks like Nemo and compiles, compares versions numerically, and shows commit, message, author and age. If it is newer it is **staged exactly as if you had dragged the file into the chat and typed /update**, so the existing gate runs: the sandbox pre-flight, the credential comparison, the Apply & restart card, the backup, and `/rollback`. **Forge never applies code itself** (a test checks the layer contains no code that replaces files, restarts or exits).

### 2.5 For the conversation: a read-only "forge" tool

Nemo's tool scout can now search GitHub, look at a repository or a PyPI page, and **propose** an install ("which library does X?" → he can look it up and propose it). Everything it returns is labelled third-party text that is never an instruction. `propose` only creates a card for you; **he cannot install anything himself.** The tool works only for the owner: family and guests never spend the GitHub allowance or start a download.

### 2.6 Everything else in plain words

`forge` (menu + status: token, rate left, upgrade source, installed counts, auto-approved names, waiting cards) · `forge ideas` (things that would make me better: pypdf, openpyxl, rembg, pytesseract, pip-audit, bandit, with ✅ for what is already there) · `forge list` · `forge inbox` (re-send waiting cards) · `forge run <env> <program> <arguments>` (only programs Forge installed, no shell, a clean environment with none of Nemo's keys, tokens or pip settings, 120 s limit, output capped and masked) · `/forge` and a **🧰 Forge** button in the main menu.
Ordinary sentences are left alone ("install it", "install the update", "install it on my phone", "forge ahead with the plan", "show 1", "remove the reminder…" all go to normal chat).

## 3. What changed in older code (all asserted in the build)

* The file's top docstring (v91.0 entry), the version number.
* `_n79_editable`: the prefix `_n91_` joins the protected prefixes (Forge cannot be live-edited by self-development).
* `_N88_SECRET_CMD`: `forge key ` joins the list of commands whose text is never recorded.
* `_N83_TOOLS`, the scout's JSON line, `_n83_validate_needs`, `_n83_run_one`: one new `forge` tool, like v88's `see`.
* The tests `test_studio90.TestStructure` and `test_argus88` were adapted only to stop at the Forge layer / accept a later tool.

Everything else is a new layer appended before the `__main__` guard; later definitions win, as in every earlier version.

## 4. Tests actually run

* `tests/test_forge91.py`: **144 tests**, all passing, and no network: GitHub and PyPI are scripted fakes; the PyPI parser is also run against a **real PyPI answer** saved in `tests/fixtures/pypi_pypdf_sample.json`. The installs are **real**: wheels are built inside the test and installed by the real pip into real virtual environments (isolated tools, and "into yourself" against a throw-away environment), covering dependencies, a failing import, a missing dependency, a tampered file, a stray file, a stale card, additive-only, rollback, removal, `forge run` with secrets in the environment. Plus apt (faked runner), the upgrade staging (the real `/update` entry is replaced by a recorder), the front door (owner only, private chat only, ordinary sentences untouched), the tool wiring, structure tests (one place where programs start, no shell, wheels only, offline install, four hosts, no GitHub write, no code that applies updates, no token in any log call) and mutation tests (take a guard away and the matching check notices).
* Full suite on the final file: **1472 tests, all passing** (1 skipped: the slow gate below, run separately). v90.2 had 1328; the new 144 are the Forge tests. One earlier full run showed a temp-folder clean-up error inside a Studio test's tearDown (a directory that was not empty at that moment); it did not reproduce in three isolated reruns of that class nor in the final full run, so I treat it as an old timing flake, not a Forge fault.
* Slow real-file update gate (`NEMO_SLOW=1`): **passed** (the real file passes its own gate, a deliberately broken copy fails it, a copy missing the regression suite does not pass).
* Pyflakes: no new message against v90 (158 → 158). `py_compile` OK. Credential check against v90: **0 changed, 0 removed.** Secret scan of the diff: clean.

## 5. Offline-tested vs not verified live

**Run for real in this session (free, no key, no trade, no paid call):** a real PyPI read, a real `pip download` of the small package `tabulate`, a real wheel read, a real isolated environment, install, `forge run tabulate tabulate --help`, and removal (the environment was deleted again).

**Not verified live (say so before relying on it):**
1. **GitHub itself.** The sandbox's network refuses `api.github.com`, so the GitHub paths (search, repository card, README, scan, commit, file fetch) are tested only against scripted answers shaped like GitHub's documented replies. The first real `search github for …` on your server is the live test. (If your server limits outgoing sites, Forge will say the network blocked it and which four hosts to allow.)
2. **The real upgrade pull** from your repository (the 5 MB file through GitHub's contents API) and the hand-over to `/update` on your VPS.
3. **apt on your VPS** (only a faked apt runner was used; no system package was installed or removed).
4. **The Telegram cards and buttons** as they look in your chat (the engine and texts are tested, the phone is not).
5. **Real, large or compiled packages** on your VPS's Python and platform. The tests install pure-Python wheels; a package with no ready-made wheel for your server is refused by design, and a very large one needs `install NAME big`.
6. **PyPI's `releases` list** is used for the age/look-alike checks; if PyPI ever stops sending it, the age is unknown and look-alike names are refused more often (the safe side).
No live trade was placed and no paid API was called.

## 6. Quick checks through Nemo (in your private chat)

1. `forge` → the menu and status (token, upgrade source, nothing installed yet).
2. `forge key github <token>` (optional) → "Saved…", and your message is deleted. Without a token GitHub allows about 60 reads an hour.
3. `search github for pdf table extraction` → a list; then `inspect 1` and `scan 1`.
4. `pypi tabulate` → licence, age, risk lines. Then `install tabulate` → a card with file hashes → tap **Approve** → "Installed…". `forge run tabulate tabulate --help`. `what have you installed`. `remove tabulate`.
5. `install pypdf into yourself` → a card saying "nothing already installed is changed" → Approve → it imports at once.
6. `install requests` → "…one of the packages my trading and chat code runs on, so I never install or change it."
7. `forge source owner/name@main` then `check for upgrades on github` → the pre-flight sandbox result and the usual **Apply & restart** card (nothing is applied until you tap).
8. `install ffmpeg on the server` → a card (only if the bot runs as root).
9. Ask in conversation: "which python library can read tables out of PDFs?" → he may search and propose; you still approve.

## 7. Installing and rolling back

Send `nemotron_bot.py` to Nemo and `/update` (the sandbox pre-flight runs, then **Apply & restart**), or use `forge upgrade` once the source is set. `/rollback` returns to the previous file. Forge's own files live in `/root/nemo_forge` (staging, work) and `/root/nemo_envs` (isolated environments); the ledger is the `forge91_item` table. `remove NAME` takes an install away; deleting those two folders and the table removes everything Forge ever added to the isolated side (anything added "into yourself" is listed in the ledger and removed by `remove NAME`).
