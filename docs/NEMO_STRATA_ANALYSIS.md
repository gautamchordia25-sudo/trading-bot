# Strata: what it is, what I found on GitHub, and whether Nemo should add it

You asked: *"what is Strata, search it on GitHub and analyse it, and tell me with research whether we can add it to Nemo."* This page is the research. **Nothing was built, installed or run.**

Evidence tags: **[strata-code]** I read it in a shallow, read-only clone of the repository (commit `45c9f7d`, 2026-06-01; nothing in it was executed); **[nemo-code]** I read it in `nemotron_bot.py` at v102.0; **[web]** a web-search result (vendor pages, blogs, papers: treat numbers as "reported"; links at the end); **[mine]** my judgement; **[gap]** I looked and could not confirm it.

---

## 0. Which Strata?

"Strata" is a common name. These are the GitHub projects I found, and which one I analysed:

| Project | What it is | Relevant to Nemo? |
|---|---|---|
| **Klavis AI's Strata** (`Klavis-AI/klavis`, folder `open-strata`; PyPI `strata-mcp`) | One MCP server that sits in front of many MCP servers and shows an AI only a few tools, revealing the right ones step by step. About 5.3k to 5.8k GitHub stars (varies by source) [web]. Apache-2.0. | **Yes. This is the one I analysed** (it is the best-known "Strata" among AI-agent tools, and Nemo has an MCP client). |
| **OpenGamma Strata** (`opengamma/strata`) | A Java library for market-risk analytics on rates, FX and bond products; Apache-2.0; its 2016 to 2017 product list covers swaps, swaptions, caps/floors, bond and FX options and futures [web]. | No. It runs on Java, targets rates and FX desks, and Nemo's option maths (Sigma) is already in Python. |
| **Stele's Strata** (`Stele-Dev/strata`) | A local, read-only, MIT-licensed tool that turns the session logs of coding agents into one CLI and TypeScript API, for searching past sessions [web]. | Not for Nemo. It could help *you* search your own coding-agent sessions. |
| AgentStrata, strata-repo-intel, a "Strata" memory server | Small unrelated projects [web]. | No. |

**If you meant a different Strata, tell me the link or what it does and I will redo this page.**

---

## 1. The short answer

1. **What it is.** Strata is an MCP "router". Instead of showing an AI hundreds of tools from many servers, it shows five and lets the AI narrow down: pick a server, search its actions, read one action's details, run it. Klavis sells a hosted version with ready-made app logins (OAuth) and publishes a thin open-source version you run yourself.
2. **The idea is sound.** Independent research and Anthropic's own engineering post agree that giving a model too many tools hurts accuracy and wastes tokens, and that searching for tools on demand helps (section 4).
3. **But Nemo does not need the package today, and the package would weaken Nemo's safety.** Nemo has five small MCP presets, so it does not have the problem Strata solves yet. And Strata funnels every action through one generic "execute_action" call, which **hides the real tool from Nemo's read/write approval gate** (section 5). The open-source version also listens on all addresses with no login in HTTP mode, stores tokens in plain files, has a placeholder for its authentication step, and shows no feature changes in the history I could see (section 3).
4. **Recommendation: borrow the idea, not the package.** When you connect many MCP servers, add a small native "tool finder" to Nemo (BM25 search in Nemo's own code, about 200 lines, no new dependency, no extra model calls) in front of the gate that already exists. Use Strata itself only if you want its one-line server configuration, and then only as a local child process with a small adapter (section 6). Do not use Klavis's hosted Strata for your personal accounts.
5. **Not urgent.** This belongs with item C2 ("more MCP tools by tier") of the master list, after Mind, Voice and the safety base.

---

## 2. What Klavis Strata is

**Two products with one name** [web, Klavis's own pages]:
* **Hosted Strata** (strata.klavis.ai): a managed streamable-HTTP MCP endpoint with Klavis's app integrations and OAuth logins (GitHub, Notion, Slack and others). Klavis lists a free tier and paid tiers; the pricing pages I found disagree with each other [gap].
* **Open-source Strata** (`open-strata/`, package `strata-mcp` 1.0.2): a local router you run on your own machine and point at MCP servers you already have. No app logins are included.

**How the progressive discovery works** (Klavis describes four stages for the hosted product: services, categories, actions, then the schema; the open-source code, as I read it, has no category stage) [strata-code `tools.py`]:

| Step | Tool the AI calls | What comes back |
|---|---|---|
| 1 | (the server names are listed inside the tool's description) | which servers exist |
| 2 | `discover_server_actions(user_query, server_names)` | only the **names** of the actions on those servers that match the query (BM25 text search, at most 50) |
| 3 | `get_action_details(server_name, action_name)` | that action's description and input schema |
| 4 | `execute_action(server_name, action_name, path_params, query_params, body_schema)` | the result of running it |
| (extra) | `search_documentation(query, server_name)`, `handle_auth_failure(server_name, intention, auth_data)` | keyword search over an action list; an authentication helper |

Klavis's claims, all **self-reported** [web]: it beats the official GitHub MCP server by 15.2% and the Notion one by 13.4% on the MCPMark benchmark (pass@1), and reaches 83% or more accuracy in human evaluation on over 2,000 real queries. I found no independent test.

---

## 3. What I read in the code (open-strata) [strata-code]

| Fact | Detail |
|---|---|
| **Size and parts** | 3,183 lines of Python in `src/strata` plus 85 tests across 9 files; the 5 tools above, a command-line tool (`strata add/list/enable/disable/remove/run/auth`), and a watcher that reloads the config when it changes. |
| **Dependencies** | Small: `mcp`, `bm25s` (the text search), `pystemmer`, `platformdirs`, `starlette`, `uvicorn`, `watchgod`. Python 3.10 or newer. |
| **Licence** | Apache-2.0 (`LICENSE`, `pyproject.toml`). |
| **How it connects to other servers** | Three kinds: a local program started from the config (`command`, `args`, `env`), plain HTTP/SSE, and OAuth. A tool list is cached per server after the first request (`mcp_proxy/client.py:58-92`). |
| **No approval layer** | `execute_action` calls whichever tool the AI names, with no read/write check, no confirmation and no limit (`tools.py:286`). Safety is left to the AI client. |
| **HTTP mode is open** | `strata run --port` starts the server on **`0.0.0.0`** with Starlette **`debug=True`** and **no login of any kind** (`server.py:188`, `server.py:203`). Anyone who can reach the port can list and run every action on every connected server, using the tokens saved in its config. Only stdio mode (the default) avoids this. |
| **Credentials** | The server list, with any tokens or API keys, is a plain JSON file (`~/.config/strata/servers.json`); OAuth tokens are written as plain JSON under a **relative** `.tokens/<server>/tokens.json` (`auth_provider.py:18-29`), meaning wherever the program was started. No file permissions are set. |
| **A placeholder** | `handle_auth_failure` with `save_auth_data` returns "success" **without saving anything** (`tools.py:343-356`). The real login handling is in the hosted product. |
| **Parameters are flattened** | The three parameter strings are merged into one flat dictionary before the call (`tools.py`, just above line 286): fine for simple tools, awkward for tools with nested arguments. |
| **Maintenance** | The newest commit in the repository is dated 2026-06-01. In the 400 most recent commits (2025-12-05 to 2026-06-01) the `open-strata` folder changed three times, all dependency updates (two by a bot on 2026-01-27, one on 2025-12-05). **No feature work is visible.** The company's effort appears to be in the hosted product (the README itself points to it). A shallow clone cannot show older history. |

---

## 4. Does the idea hold up? [web]

* **The problem is real.** The RAG-MCP paper (arXiv 2505.03275) reports that picking tools by search before the model sees them cut prompt tokens by over half and **more than tripled tool-selection accuracy (43.13% against 13.62%)** on its benchmark. Blog posts quote thresholds (trouble from about 30 to 50 tools, a collapse past roughly 120); I could not trace those to a primary source, and several blogs reverse the paper's numbers.
* **Anthropic agrees, with its own numbers.** Its engineering post on advanced tool use describes a tool-search tool (regex or BM25) that loads tool definitions only when needed: about 85% fewer tokens in its example, and on its internal MCP evaluations accuracy rose from 49% to 74% for one model and from 79.5% to 88.1% for another. These are the company's internal results.
* **The cost of the Strata style:** each step is a model call. An Alpha Vantage document describing the same pattern lists "two additional model round trips" as its main drawback [web]. For Nemo, whose MCP runner (`mcp_run`) stops after six steps, that matters: three discovery calls would eat half of the budget.
* **Strata's own numbers are unproven.** The idea is supported; the specific 15.2-point and 83% claims are the vendor's.

---

## 5. Nemo today, and what Strata would do to it [nemo-code]

* **MCP client.** `MCPClient` speaks to a server over stdio (a program Nemo starts) or HTTP (JSON replies or event streams, and the session header), so it **can** talk to Strata's stdio mode or its `/mcp` HTTP address. Five presets exist (fetch, time, git, filesystem, memory) plus `/mcp add` and `/mcp addhttp`.
* **The catalogue goes into the prompt.** `mcp_run` lists every connected tool, one line each, into every one of up to six model prompts. With five presets that is a few dozen lines, which is fine; with GitHub, Notion, Slack and mail servers added it would be hundreds. That is exactly where tool search starts to pay.
* **A strong approval gate.** Since v85, every MCP call passes one enforcement point (`_n85_mcp_call`): each tool is classified read, write or blocked **by its name, its declared hints and its argument names**; a write needs your tap on a card; arguments are screened for private addresses; every call is logged.
* **The conflict.** Through Strata, the only tool Nemo sees is **`execute_action`**; the real action ("send_message", "delete_page") is hidden inside its arguments. Nemo's gate would see the word "execute", classify it as write, and ask for a card for **every** action, reads included, showing you a card that does not say what will really run. Making it a read-only tool instead would let real writes through without a tap. So Strata cannot sit behind the gate as it is: a small adapter would have to unwrap `execute_action` into the real server, action and arguments, and classify **that**.
* **Memory and install.** The router and its search library are modest, but Nemo's server has little spare memory. Installing it into Nemo's own Python risks version clashes (Nemo pins `mcp<2` for its presets); Forge's isolated environment avoids that.

---

## 6. The options compared

| Option | What it means | Effort | Risk | Benefit | Verdict |
|---|---|---|---|---|---|
| **A. A native tool finder inside Nemo** | When many MCP tools are connected, Nemo ranks them against your request with its own BM25 search, shows the model only the best 6 to 10 (name, one line), and the model picks one; the real tool name stays visible to the gate. No extra model calls, no new dependency, no third party. | about 200 lines and tests (M) | Low | Keeps accuracy as tools grow; keeps every v85 protection | **Recommended, when you connect many servers** |
| **B. Strata as a local sub-router** | Run `strata-mcp` in an isolated environment, stdio only, as Nemo's single MCP server; add the adapter that unwraps `execute_action` for the gate. | M to L | Medium: a second place that holds tokens in plain files, an unmaintained-looking dependency, three model calls per action | One-line configuration of many servers | Only if the native finder is not enough |
| **C. Klavis hosted Strata** | Use Klavis's managed endpoint and its app logins. | S | Higher: your OAuth tokens and data pass through a third party; paid tiers; the security claims I saw (SOC 2, tokens) are unverified | Ready-made logins to dozens of apps | **No** for personal mail, Drive and calendar (Nemo already reads them directly, with your approval rules) |
| **D. Do nothing yet** | Keep the five presets. | none | none | none | Right until you connect more than about 15 to 20 tools |

---

## 7. What I would do, in order

1. **Now: nothing to install.** The need does not exist yet.
2. **When you add your third or fourth MCP server** (or ask for GitHub, Notion, Slack, mail through MCP): build **option A** as a small layer: a pure-Python BM25 over each tool's name, description and argument names; a switch (on automatically above about 25 tools); "show tools for…" so you can see what it would offer; tests that prove the gate still sees real tool names and that a write still needs a card.
3. **Only if you want it later:** a Strata adapter (option B), after measuring what the native finder misses.
4. Add the **write-through-MCP** step (master list C1/C2) behind the same gate. The finder makes that safe to grow.

---

## 8. What I could not verify

* The Launch HN comment thread and any independent test of Strata's accuracy claims (the search did not surface them).
* Klavis's real prices, their security certifications, how the hosted version stores tokens, and what the closed parts do.
* Whether older history shows more activity on `open-strata` (a shallow clone only shows recent commits), and the current PyPI release date.
* Memory use of `strata-mcp` on your server. I did not run it.
* Whether you meant this Strata.

---

## 9. Questions for you

1. **Is this the Strata you meant** (Klavis AI's MCP tool router)? If not, send the link.
2. **Which services do you want Nemo to reach through MCP** (GitHub, Notion, Slack, mail, Drive, others)? The list decides whether tool search is needed soon.
3. **Do you want me to build option A when you answer question 2,** or only after Mind and Voice as planned?

---

## Sources (web search results; read as "reported")

* Klavis Strata: [Introducing Strata (Klavis blog)](https://www.klavis.ai/blog/introducing-strata-one-mcp-server-for-thousands-of-tools), [Launch HN: Strata](https://news.ycombinator.com/item?id=45347914), [Klavis docs](https://eu.klavis.ai/docs/quickstart), [review summary (Revuo)](https://www.revuo.ai/category/mcp-ai-ml/klavis-ai), [pricing listing (G2)](https://www.g2.com/products/klavis-ai/pricing), [pricing listing (Toolradar)](https://toolradar.com/tools/klavis-ai/pricing)
* The repository: [Klavis-AI/klavis](https://github.com/Klavis-AI/klavis) (the `open-strata` folder)
* Evidence for the idea: [RAG-MCP (arXiv 2505.03275)](https://arxiv.org/html/2505.03275v1), [Anthropic: advanced tool use](https://anthropic.com/engineering/advanced-tool-use), [Anthropic: tool search tool docs](https://platform.claude.com/docs/id/agents-and-tools/tool-use/tool-search-tool), [MCP tool overload (Unblocked)](https://getunblocked.com/blog/mcp-tool-overload/), [progressive disclosure benchmark (Kruczek)](https://matthewkruczek.ai/blog/progressive-disclosure-mcp-servers.html), [Alpha Vantage progressive discovery notes](https://github.com/alphavantage/alpha_vantage_mcp/blob/main/docs/progressive-discovery.md)
* Other Stratas: [OpenGamma Strata](https://strata.opengamma.io/introduction/), [Stele's Strata launch post (dev.to)](https://dev.to/feed/stele), [AgentStrata](https://github.com/Ling-ye/AgentStrata)
