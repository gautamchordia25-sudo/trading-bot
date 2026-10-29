# Nemo v99.1: Answer (a fix for "Trade Lab stopped: _N73Error", and a real answer to "how would you survive with ₹20,000")

One small release on top of v99.0, one file (`nemotron_bot.py`, version 99.1). It is a fix, not a new feature set, because of what you showed me.

## 1. What went wrong (your screenshot)

You asked: *"nemo suppose you have 20000 rupees … trading in options in indian stock market, how will you survive and what 1 year return you can make … deeply analyse how and tell me"*. Nemo answered **"Trade Lab stopped: _N73Error. No real broker order was sent."** and nothing else.

I read the code path of that message. There were **three separate faults**, and any one of them alone would have made a bad answer:

1. **Wrong tool.** Nemo's first step is an AI "intent router" (`_n72_decide`). It sent your question to **Trade Lab**, the tool for market research and paper plans ("research NIFTY option chain", "paper trade plan with entry, stop, target"). Trade Lab cannot answer a strategy question: its own instructions forbid inventing anything and tell it to ask for a symbol and prices.
2. **No second chance.** Trade Lab then made its own AI call. For you, the owner, every AI call goes first to the **direct brain gateway** (the OpenAI, Anthropic, Gemini, OpenRouter keys). When that gateway fails (a provider's rate limit, an empty credit balance, an error, everything cooling down) there is deliberately **no fallback to the older free brains** (Groq, Gemini, Cerebras, the free models): the code says *"No recursive legacy-provider cascade after a direct gateway attempt"*. So one failing provider was a dead end for every request that asks the gateway for a structured answer, which is what the routers and tools do.
3. **A message that hides the reason, and a lost question.** The error text shows only the **name of the error class** (`_N73Error`), not its code (for example `http_429` or `providers_cooling_down`), and nothing kept your question.

I do **not** know which code the gateway returned that evening: the message did not say, and I cannot see your server. Section 6 says how to find out.

## 2. What v99.1 changes

| Fault | Fix |
|---|---|
| Wrong tool | A hypothetical or strategy question about trading ("suppose you had…", "how would you survive", "what return in a year") is never handed to Trade Lab: the router's choice is changed to the ordinary conversation. A real market request ("research the NIFTY option chain, OI and PCR", "paper trade plan … entry … stop … target", "show my paper journal") still goes to Trade Lab, exactly as before (tested both ways). |
| No second chance | When the direct gateway fails, the call **falls through to the older brains** instead of ending. It does **not** after a refusal by a provider (content filter), a cancellation, a used-up time budget or an oversize input. It can be switched off: say **`brain fallback off`** (and `brain fallback on`, or just `brain fallback` for the status and the last time it was needed). |
| Dead end | If Trade Lab still stops because the AI could not be reached or understood, the message is **handed to the ordinary conversation** and you get an answer, not "Trade Lab stopped". Real Trade Lab problems (for example the broker's data request failing) keep their message, and an explicit paper plan or P75 plan id is never rescued. |

And the question itself is now answered **without any AI**, from Nemo's own record and a simulation (section 3), so it works even when every brain is down.

## 3. The answer Nemo now gives to "₹20,000 in options for a year"

Any message that has an amount of money (₹20,000, Rs 50000, 20000 rupees, 2 lakh rupees, 20k rupees), trading words, a "how will you survive / what return" question and a hypothetical, is answered in three messages, in seconds, with the numbers worked out and nothing invented:

1. **What the money can actually do.** NIFTY lot size (65), the typical premium (the middle of your own practice trades, or an assumed ₹100 when there are too few), the cost of one lot, how many lots the money buys, what a -30% stop loses on one lot as a share of the money (about 9.8% of ₹20,000), and what premium a prudent 1-2% risk per trade would allow (only options under about ₹10-20: contracts that rarely pay). **The first honest finding: ₹20,000 is too small to follow a sensible risk rule on index options.**
2. **What your own record says**: trades, wins, the range the true win rate could really be in with that few trades, result after charges, worst dip, and the break-even win rate for the agent's -30% / +50% structure (about 37% before costs, about 40% after charges and the spread).
3. **A year of simulated trades** (2,000 random years per line, one lot per trade, at the pace the agent has really kept, or 100 a year when there are too few days of record), for 30%, 35%, 40% and 45% win rates and for "like my record" (its own results reused at random): how many years end below the start, lose half or more, or run out of money for a lot, with the middle year and the 1-in-10 good and bad years.

Then four honest paragraphs: how to try to survive (one lot, no averaging down, a daily loss limit of about 3%, stop after two losses, trade only on strong signals, treat the money as money you can lose, prove it with virtual money first and check `lab ready`), and **what return to expect**: plan on losing money; a year of +50% needs a proven edge that the record does not show; SEBI's FY25 study (published July 2025) found about 91% of individual F&O traders lost money, an average loss of about ₹1.1 lakh (the figure is from press reports of the study, which I found by web search; I could not read SEBI's own page).

An example of what the simulation says (from a made-up 22-trade record, **not yours**): a trader who wins about 40% of the time (break-even here) is **ruined in about 62% of years**, because each loss costs about 9% of the money and an ordinary run of bad luck is enough. The years that end far ahead are luck; that luck is how people come to believe they have skill. Your own numbers will come from your own ledger.

## 4. What I did not do

- I did not change the agent, the trading guards, the owner lock or any credential.
- I did not change which provider is tried first, or the model lists.
- The capital analysis is **not a forecast**: it assumes one lot per trade, the agent's -30% stop and +50% target met exactly, and costs of about 2% per trade. Real exits overshoot, real traders do not repeat one rule for a year, and 22 trades say little about skill. It is built to show how fast a small account is exposed to ruin, which does not depend on the exact numbers.
- English only: a Hindi or Hinglish version of the question is not recognised by the new rule (it goes the old way, now with the fixes above).

## 5. A trade-off you should know about

Falling through to the older brains means your question can go to the free providers (Groq, Gemini, Cerebras, OpenRouter's free models) that Nemo used before the direct gateway existed, and their answers are usually weaker than a paid model's. That was the reason for the earlier "no cascade" rule, I think (it is not written down). If you prefer a failure to a weaker answer, say `brain fallback off`.

## 6. What to do to find the real cause (your decision, not mine)

- `which ai brains are available` (free) shows which provider keys exist.
- `test my ai connections` makes **up to two small paid API calls** (Claude and OpenRouter). I did not run it and will not without your say-so.
- After this release, `brain fallback` tells you when the fallback was last needed and **what the gateway said** (for example `http_429` is a rate limit, `http_402` is no credit, `http_401` is a bad key). If it is a bad key or no credit, the real fix is the key or the balance, and no code can replace that.
- The fallback only helps if the older brains have keys too (Groq, Gemini, Cerebras or an OpenRouter key). If none of them works either, the answer will still fail, and this time the message will say that the brains are all busy.

## 7. Verified and not verified

**Verified offline (68 new tests):**
- the classifier on the screenshot's own sentence, five more hypotheticals, six market or paper requests that must stay with Trade Lab, and a list of sentences that are not about trading or not hypothetical;
- amounts: ₹20,000, Rs 50000, 20k rupees, 2 lakh rupees, 1 crore rupees accepted; 20 rupees, a bare number, "a 1 year return" refused;
- the router change in isolation and **through the real task**: a general question reaches the conversation and never Trade Lab, a market request still reaches Trade Lab;
- the gateway fall-through for 12 failure codes, not for 7 others, for the polite failure text of a normal call, with the switch off, for a guest, with the arguments unchanged, and **end to end through the real `ask_ai` chain** (the gateway failing with a rate limit, a scripted older brain answering);
- the Trade Lab rescue (three AI-caused stops rescued, real problems and paper plan ids untouched, a failing rescue does not raise);
- the simulation (a sure win, a sure loss, repeatability, ordering of percentiles, a better win rate is never worse) and the report (lot size, premium, stop loss share, win-rate range, break-even rates, every table line, other amounts, virtual trades only, deterministic);
- the front door: the owner's exact question answered with no AI call and no broker call; a guest, a file, a picture, a group, and all other trading sentences are not taken;
- structure: the layer calls no AI and no network, never writes the agent's state, writes one setting only, contains no secret-shaped text.

**Not verified:**
- **The real failure that evening** (see section 1): not reproducible from here.
- **Real brains.** All AI calls in the tests are scripted. Whether your free-tier keys are configured and answering is not something I can see.
- The wording of the capital analysis was judged by reading it, not by anyone in your position.

## 8. Try it, through Nemo

1. Send the same question again. You should get four messages within seconds, with your own record in them.
2. `brain fallback` to see the status.
3. Ask a general question that does not name an amount, for example "how do option traders survive?": it should be answered in conversation (by a brain), not by Trade Lab.
4. Ask a market question, "research the NIFTY option chain": Trade Lab should still handle it.

## 9. What changed in older code (everything else is in the new layer, marker `# NEMO 99.1 - ANSWER`)

1. The docstring, `VERSION`, and `'_n991_'` in the live-self-edit protection list.
2. Wrapped (the old function kept and called): `_n72_decide` (the router), `_n73_core_reply` (the brain gateway), `_n75_trade_task` (Trade Lab), `handle` (the capital question and the `brain fallback` switch, owner only), `_n82_capabilities`, `_n83_status_text`, `prime_regression_suite` (6 more rows).
3. Tests: `tests/test_answer991.py`. The v99 structural tests now stop at the v99.1 marker.

## 10. About "smarter and more powerful"

You said Nemo has no use for you if he cannot answer a simple question like this. I agree that this one should have been answered, and this release fixes the path that failed. It would be dishonest to promise more than that. How good Nemo's answers are depends on which brains are behind him; I can make him fail less, tell you why when he fails, and answer from his own data when the AI is down, but I cannot make a free model smarter than it is. The next planned release (Offline: a "pulse" that tells you when the brains have been failing, questions that failed being kept and answered by themselves, and an offline encyclopaedia that needs no AI) is designed for exactly this problem and is written but not finished or tested yet; I have parked it until you say to go on.

## 11. Test results (offline, on the test machine)

- **Whole suite on the exact file delivered (the slow gate switched on): 2,715 tests, 6 skipped, 0 failures.** 68 of them are new (`tests/test_answer991.py`); the earlier 2,647 all pass unchanged except that the v99 structural tests now stop at the v99.1 marker, as the earlier layers' did.
- Pyflakes: the same 158 messages as v99, none new. Credential comparison against v99: no change to any saved credential. A scan of the 362 added lines for keys, tokens or passwords found none. Only two lines of older code were edited (the docstring's first line and the protection list); the layer is appended.
- Nothing here placed, changed or simulated an order, called a broker, called an AI, or used a paid service. The AI calls in the tests are scripted.
- I also ran the new answer on a made-up 22-trade record to read it: it takes about a quarter of a second and the text is in section 3.
