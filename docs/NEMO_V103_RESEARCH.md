# Research behind v103 "Mind": what I looked at and how far to trust it

Evidence tags used here: **[search summary]** = I read a search engine's summary of the page, not the page or paper itself; **[my own check]** = I tested it myself in this repository; **[not found]** = I looked and found nothing usable. I could not fetch full papers from this environment (outbound web fetch was unavailable), so **no claim below rests on a paper I read in full.**

## 1. Memory that knows *when* a fact was true, and when it has gone stale

* Newer agent-memory systems store, for each fact, a validity window (valid from / invalid from), so a changed fact does not erase its past. A 2026 comparison of Mem0, Zep/Graphiti, Letta and LangMem says only Zep/Graphiti implement this; the others keep timestamps but cannot mark a fact stale **[search summary]** ([comparison](https://medium.com/@wasowski.jarek/i-compared-5-ai-agent-memory-systems-across-6-dimensions-none-wins-6a658335ed0a)).
* The benchmark numbers for these systems contradict each other (one comparison has Zep ahead of Mem0 by about 22 points on LongMemEval, another has Mem0 ahead; the highest scores are self-reported by the vendors) **[search summary]**. I take from this only the *design idea*, not any performance claim.
* There is now a benchmark for exactly the problem I met in Nemo, whether an agent can tell that a stored memory is no longer valid (STALE, arXiv 2605.06527), and work on evidence-grounded and provenance-aware memory (arXiv 2608.08055, 2608.29606) **[search summary]**.
* **What I took:** Nemo's fact table already records when each version was created and which version replaced it, so a bi-temporal-style history ("what did you know on 5 March") needs no new storage. I added evidence (the owner's sentence), "last confirmed", and a half-life per kind of fact. **The half-life numbers are my judgement; I found no source that gives them.**

## 2. Finding Hindi / Gujarati / Hinglish text

* A small GitHub pull request reports that folding Devanagari nukta, chandrabindu/anusvara and joiner variants and converting native digits to ASCII before BM25 raised Hindi/Hinglish Recall@1 on its own tiny test set from 3/12 to 12/12 ([PR 250](https://github.com/basictech01/uniun/pull/250)); the issue behind it lists the same causes **[search summary]**. It is one small project's unreplicated number, so I used it as a checklist of normalisations, not as evidence of a gain.
* Character n-grams are described as tolerant of noisy Devanagari **[search summary]** (a 2026 OCR-correction paper and an authorship study; neither is about memory search).
* Learned transliteration models exist (IndicXlit, 21 languages) **[search summary]**; I did **not** use one (it would add a model download). I wrote rule-based transliteration instead: Gujarati letters sit exactly 0x180 above their Devanagari twins, so one table covers both **[my own check: the table reproduces 15 known words in both scripts in `tests/test_mind103.py`]**.
* Gujarati retrieval: only an old abstract on Soundex-based Gujarati transliteration matching **[search summary]**; **[not found]** for Gujarati + BM25 + n-grams together. So the Gujarati handling is built from general principles and my own tests, and has no outside evidence at all.

## 3. Asking before guessing

* "Knowing but Not Showing" (May 2026) reports that models can often recognise that a question is ambiguous when asked, yet still answer directly instead of asking ([paper page](https://huggingface.co/papers/2605.25284)) **[search summary]**. An older paper (CLAM, arXiv 2212.07769) found default GPT models almost never asked for clarification **[search summary]**.
* Zhang and Choi (NAACL 2025) frame "when to ask" as depending on the user's speed-versus-care preference and on whether one reading clearly dominates **[search summary]**; an enterprise-assistant paper (arXiv 2502.00537) rewrites only queries flagged as unclear, so clear ones are not degraded **[search summary]**.
* **What I took:** the decision to ask is made by code, not left to the model, and it is narrow: only when the message is a question or request, says "my <role>", names nobody, and two or more people of that role are stored. I found **[not found]** a 2026 study on this exact case (pronoun/role reference in a *personal* assistant), so how often it feels helpful is unknown; it can be switched off.

## 4. Proactive memory

* A 2026 study of memory in companion assistants (MemUse, arXiv 2608.24189) is reported to find that proactive callbacks do not earn the satisfaction that reactive recall does and carry timing risk **[search summary]**. Memory-reflection sessions (assistant summarises, user corrects) appear in another benchmark (arXiv 2608.02613) **[search summary]**.
* **What I took:** nothing proactive by default. The one proactive feature is an opt-in, once-a-day, one-line "still right?" after an answer that actually used an old fact. A reflection job that rewrites memories is **not built**.

## 5. What I could not verify

Real-model behaviour on Gujarati and Hindi (extraction, replies), the lexicon against native speakers, the half-lives against real use, and whether "which friend do you mean?" helps or annoys. The built-in `memory eval` measures only the retrieval step, on synthetic data written by the author of the word list; `NEMO_V103_MIND.md` section 5 has its numbers and limits.
