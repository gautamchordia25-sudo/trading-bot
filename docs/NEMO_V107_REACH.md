# Nemo v107.0 "Reach": search that doesn't break, feeds, topic watches, long videos and fact-checks

After v106 was installed you said "build next version". The plan's next step was **Reach**, the second web step. Nemo already had several pieces: quote-checked research (v85), page-change watchers (v85), a Google News reader (v93) and a YouTube summary. Reach fixes what held them back and adds what was missing.

Evidence tags: **[code]** = read in Nemo's code; **[tested]** = covered by the offline tests; **[source]** = from the web pages listed in section 10; **[not verified]** = not checked live.

## 0. Read this first (the honest version)

* **Built and tested offline only.** The test machine cannot reach any search engine, Wikipedia, Google News, YouTube, SEBI, RBI, NSE or PIB (its network blocks them). Every engine, page, feed and AI answer in the tests is a stand-in. **Nothing in Reach has run against the real services yet.** The first real runs will be on your server.
* **Feed addresses:**
  * **SEBI's** address comes from SEBI's own RSS page [source].
  * **RBI's** two addresses come from a feed directory, not from RBI's site [source].
  * **NSE's** and **PIB's** are my best guesses [not verified]; NSE often refuses servers.
  * Send **`feeds test`** after installing: Nemo reads each feed from your server and tells you which work. You can add the correct address yourself (`add feed nse https://…`).
* **Search engines in order:**
  1. your own SearXNG, if you set one up;
  2. DuckDuckGo (the same library as before);
  3. Brave, if you add a key;
  4. Google's programmable search, if `/gcloud` was set up;
  5. DuckDuckGo's plain page;
  6. Wikipedia.

  An engine that refuses rests for 10 minutes, and answers are remembered for 10 minutes. **Brave** costs money beyond a monthly credit, and sources disagree on whether a free plan still exists [source]; it is optional.
* **YouTube captions:** YouTube often refuses to give captions to cloud servers. Nemo then tries the downloader with your imported cookies. For **you only**, it then downloads the sound and listens to it.
* **Audio needs speech-to-text:**
  * **With your Groq key**, a long recording is cut into ten-minute parts, about 2.4 MB each, because Groq takes at most 25 MB per file on the free plan [source]. Groq's free plan also limits how many hours of audio it takes per hour [not verified for your account]. If two parts in a row fail, Nemo stops and says how far it got.
  * **Without a Groq key**, only the local speech model is used, and only for the first 20 minutes, because it is slow on your server.
* **Fact-checks are help, not a court.** A verdict counts only when the exact words that decide it are found on the source page by code. Otherwise the answer is "❓ Could not verify". Pages and fact-checkers can still be wrong.
* **No order, no trade, no message to anyone, no change outside the chat.** The trading agent, guards, owner lock and credentials are untouched. Topic and feed routines are **read-only** Autopilot routines: practice first, receipts, pause, "stop everything".

## 1. What you can say

| You say | What happens |
|---|---|
| (nothing new) | **Every web search in Nemo now has backup engines.** Answers, research, news follow, Scout and trade ideas all benefit at once [code] |
| `search status` | Each engine: working, resting (and why), or not set up |
| `use searxng http://127.0.0.1:8888` · `searxng off` | Your own SearXNG search (section 2); tested before it is switched on |
| `brave key <key>` · `forget brave key` | Brave Search as an extra engine. Delete your message afterwards; Nemo never shows a key |
| `feeds` · `feeds test` | The feeds and whether each worked from your server · read every feed now and report |
| `feed sebi` · `what's new from rbi` · `latest from pib` | The 8 latest items, 🆕 on the ones you have not seen before |
| `add feed gst-council https://…/feed.xml` · `remove feed gst-council` | Any RSS or Atom feed, checked before it is added |
| `follow feed sebi` | Every evening at 7 pm, only new items (a routine you can pause, move or delete in `routines`) |
| `news about GST rates` | The last four days' stories, newest first, one line per story; the same story from several outlets is counted once |
| `watch topic GST rates` | Every morning at 8, only stories you have not seen. The first run shows the latest 5 |
| `routine every day at 7 pm topic crude oil` · `routine every weekday at 6 pm feed nse` | The same, at your times (v104 routines) |
| `my topics` | Your topic and feed routines |
| `summarise <YouTube link>` (as before) · `read video <link>` | The **whole** video, read in parts: TL;DR, sections with timestamps, and **5 claims worth checking**, with a 🔎 **Fact-check these claims** button |
| `listen to <podcast or audio link>` · `summarise this podcast <link>` | Downloaded (400 MB at most), cut into ten-minute parts, transcribed and read the same way (3 hours at most) |
| An audio or video file with the caption `summarise` | The same for a file up to 20 MB (Telegram's limit for bots) |
| `fact check: <the forwarded text>` · reply `fact check` to a message | The checkable claims (up to 4), each looked up with fact-checkers and official sites first, a verdict tied to a quote, warning signs, advice |
| `fact check key <key>` | Optional: published fact-checkers' ratings through Google's Fact Check Tools |
| `my research` · `report RR-1A2B3C` | The fact-checks, readings, topic digests and verified research Nemo kept for you |
| `/research85 <question>` (as before) | Quote-checked research; now each source shows its own date, plus the newest and oldest |
| `/reach` | All of the above and the search status |

## 2. Your own search engine (optional)

SearXNG is a free search engine you run yourself. It asks Google, Bing, Brave, DuckDuckGo and others for you, with no key and no quota. It needs memory: one Docker image reports about 500 MB at rest [source]. Your server already runs short of memory at times (v106), so I'd **wait until you upgrade the server**. If you run it, its JSON answers must be switched on (`formats: [html, json]` in its `settings.yml`); then say `use searxng http://127.0.0.1:8888`. Nemo tests it and makes it the first engine only if the test works. Without SearXNG, Reach still has five other engines.

## 3. How a fact-check is decided

1. The AI lists up to 4 **checkable** claims: events, numbers, dates, rules, quotes, health or money facts. Opinions are not claims. If the AI is busy, the sentences with a number or a name are used.
2. Each claim is searched twice: once with "fact check" added, once plain. Fact-checkers come first: PIB Fact Check, Factly, Alt News, BOOM, Vishvas News, Newschecker, The Quint, India Today, AFP, Reuters and others. Official sites (gov.in, RBI, SEBI, NSE, BSE, WHO) come next. Up to 3 pages are read.
3. A second AI call, with no tools, reads only those pages and must answer with the **exact words** that decide it. **Code then checks those words are on the page.** If they are not, the verdict is dropped and the claim is "❓ Could not verify".
4. With a Fact Check Tools key, published ratings ("PIB Fact Check rated a similar claim False") are shown and given to the judge as evidence.
5. Warning signs found by plain rules (no AI), in English and Hindi:
   * "forward to all", "before it is deleted", "100% true";
   * alarm words, "free recharge", shortened links;
   * requests for a link, OTP or PIN;
   * an authority quoted without a link;
   * "last date today".

## 4. What a long video reading looks like

```
🎬 Monetary policy explained (1:12:30)

TL;DR: …

WHAT IT COVERS
[00:00] Why rates matter
  • …
[18:40] What the RBI did in October
  • …

5 CLAIMS WORTH CHECKING
1. [19:05] The RBI cut the repo rate by 25 basis points
…
Read from: YouTube's captions.
(RR-3F2A1C)      [🔎 Fact-check these claims]
```

The transcript is read in parts of about 11,000 characters, up to 16 parts (about 3 hours of talk). Before, only the first 16,000 characters were read. A timestamp the AI gives that falls outside its part is replaced by the part's start time. Nemo's YouTube study notes and playlist guides also get captions the new way first. Their old way used a function that version 1.2 of the caption library removed [source], so the first step failed on a current install.

## 5. What I did not do

* No new paid service is switched on; Brave and Fact Check Tools only work if you add a key.
* No SearXNG install on your server; the memory doesn't fit yet (section 2).
* Family members don't get the new commands. Family access to these features would be added through Circle (v89) when you ask.
* A Telegram file larger than 20 MB can't be read; Telegram doesn't let bots download it. Send the link instead.
* Nothing is posted, forwarded or replied to anywhere; the fact-check answer comes only to you.

## 6. Verified and not verified

| Claim | Status |
|---|---|
| Engines are tried in order; a refusing engine rests 10 minutes; answers are remembered 10 minutes; results are merged without duplicates; the old answer shape is kept | **[tested]** with stand-in engines |
| DuckDuckGo's plain page is read correctly, and its robot check counts as a failure | **[tested]** on a page shaped like theirs; the real page **[not verified]** |
| Brave and SearXNG answers are read; the key goes only in Brave's header | **[tested]** with stand-in answers; real services **[not verified]** |
| RSS and Atom are read; feeds with DOCTYPE/entities are refused; 🆕 marks only new items; the working address is remembered | **[tested]** |
| SEBI/RBI/NSE/PIB addresses work on your server | **[not verified]**: send `feeds test` |
| Topic watch tells only new stories; a reworded headline of an old story is not new; "18 percent" vs "28 percent" is new | **[tested]** |
| Long transcripts are read in parts with timestamps; audio is cut into ten-minute parts under 25 MB | **[tested]** (the audio part with real ffmpeg on a generated tone) |
| YouTube gives captions to your server | **[not verified]**: YouTube often refuses servers |
| A fact-check verdict needs its quote on the page | **[tested]** |
| Fact-checkers publish ratings that Google's Fact Check Tools return for Indian claims | **[not verified]** |

## 7. Commands that changed meaning

* `summarise <YouTube link>` gives the new whole-video reading. If it fails unexpectedly, the old summary runs.
* `news about …` / `news on …` now gives a list of stories from news engines, not an AI chat answer.
* `fact check …`, `is this true: …` (with text) and `check this forward: …` start a fact-check. "is this true?" on its own, without text or a replied-to message, is still ordinary chat.

## 8. Test results (offline, on the test machine)

- **New tests: 58** in `tests/test_reach107.py`, all passing. They use stand-in engines, pages, feeds and AI answers. The audio tests cut a generated 25- and 35-minute tone with the real ffmpeg.
- **Planted bugs:** I broke the new rules on purpose 31 times, one at a time, and **the tests failed for every one**. The first round let four through (a reworded headline, impossible timestamps, the stop after two failed parts, a key-less fact-check call). I made those tests stricter. Doing that exposed a real flaw, which I fixed: "cuts rates to 18 percent" and "cuts rates to 28 percent" were treated as the same story. Headlines with different numbers are now different news.
- **Bugs found while building, fixed:** a reworded headline ("18 per cent" vs "18 percent", "rate" vs "rates") counted as a new story; a fact-check started on any message beginning "check it"; the search cache could be pruned while another thread wrote to it.
- **Pyflakes:** the same 158 messages as v106, none new. A scan of the added code for keys, tokens or passwords found none.
- **Whole suite on the exact file delivered (the slow gate switched on): 3,771 tests, 7 skipped, 0 failures, 0 errors.**
- Nothing here placed an order, called a real AI, search engine, feed, YouTube or Google, or used a paid service.

## 9. What changed in older code (everything else is in the new layer, marker `# NEMO 107 - REACH`)

* **Changed lines in older code:** the docstring's first line, and the protected-names list for live self-edit (`_n107_` added).
* **Wrapped by the layer:**
  * search and research: `web_search`, `_n85_fetch` (it remembers each page's date), `_n85_research` (dates added to the report);
  * YouTube: `_yt_transcript`, `youtube_summary`;
  * Autopilot: `_n104_pick_kind`, `_n104_add_routine`;
  * entry points and registries: `handle`, `handle_callback`, `_n82_capabilities`, `prime_regression_suite`, `main`.
* **Extended:** `_N85_TEXT_TYPES` (RSS/Atom content types); `_N104_KINDS` and `_N104_RUNNERS` get `topic` and `feed`; `_N86_STORES` gets `reach107`, so "forget" covers reports, your feeds and remembered headlines.
* **Older tests changed:** v104's routine-kind list allows the two new read-only kinds; v99.1's docstring test looks in the first 6,000 characters (each new version puts its own line first).

## 10. Sources

* youtube-transcript-api releases (v1.2.0 removed `get_transcript`; use `YouTubeTranscriptApi().fetch(...)`): https://github.com/jdepoix/youtube-transcript-api/releases
* Groq speech-to-text (25 MB free tier, 100 MB dev tier; larger files by URL or split): https://console.groq.com/docs/speech-to-text
* SEBI RSS (address `https://www.sebi.gov.in/sebirss.xml`): https://www.sebi.gov.in/rss.html
* RBI feeds as listed by a feed directory: https://feeder.co/discover/site/rbi.org.in ; NSE's RSS page (addresses not readable from here): https://www.nseindia.com/rss-feed
* ddgs (the search library Nemo uses; it can use several backends): https://github.com/deedy5/ddgs ; Open WebUI's notes on it: https://docs.openwebui.com/features/chat-conversations/web-search/providers/ddgs
* Brave Search API pricing (sources disagree; check before adding a key): https://api-docs.search.brave.software/pricing ; https://costbench.com/software/ai-search-apis/brave-search-api/
* SearXNG memory (one image reports about 500 MB at rest): https://hub.docker.com/r/ronxldwilson/searxng-slim
* Google Fact Check Tools API (`claims:search`, needs an API key): https://developers.google.com/fact-check/tools/api
