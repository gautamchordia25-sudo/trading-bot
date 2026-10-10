# Giving Nemo its own address, database and identity, open to everyone, and an honest path to earning from it

You asked: *"I want to give Nemo its own web address, its own database, a separate identity, open to all and usable, and if all works well then some day monetise it and give me a return on the investment and time, in terms of the server and system I would give to Nemo."*

This page is the research and the plan. **Nothing in it is built yet.** I wrote it so you can decide, with the real numbers and the real risks in front of you, whether to start and how much to risk.

Evidence tags: **[code]** I read it in `nemotron_bot.py` this session; **[web]** a web-search result (blogs, vendor pages, news: weak evidence, treat every number as "reported"; links at the end); **[mine]** my own judgement or arithmetic; **[gap]** I looked and could not confirm it. My sandbox could not open official sites (Cloudflare, AWS, Telegram, IP India, RBI): every price and rule below comes from search summaries and must be checked on the official page before you spend money or sign anything.

---

## 1. The short answer

1. **Yes, it can be done, and it should be a separate product, not your Nemo with the door opened.** Your Nemo is built as one person's assistant (section 2). The public one should be a **new, small service** ("Nemo Public" is only a working label) with its own domain, own database, own model keys, own bot and own brand. Your personal Nemo stays private, exactly as it is now.
2. **The safest public assistant is one that cannot do anything dangerous.** Chat, memory per user, voice and pictures, reports, Indian-language help, office helpers. **No** server tools, no mail or Drive, no downloads, no broker, no self-editing. A public bot that can only talk has very little for an attacker to steal.
3. **Trading signals should not be in the public product.** Paid buy/sell signals need SEBI registration in India, and an "educational" or "AI" label does not change that [web]. World-market *knowledge* (hours, calendar, glossary: the Globe layer) is fine as education; Sigma-style signals are not.
4. **Money: it can earn, but a general "AI chat for everyone" app in India is a hard business** [web]: free giants, low willingness to pay, and AI apps lose subscribers faster than other apps. My arithmetic (section 8) shows a free tier can cost more than the paying minority brings in unless the free tier is capped tightly. A **narrow product for a defined group** (shops and showrooms, Gujarati/Hindi family assistant, students) has a much better chance than a general assistant.
5. **Do it in stages with money gates** (section 9): a private beta for about 30 people costing roughly ₹1,000-2,000 a month, then open sign-up with caps, then payments. At each gate there is a plain "stop or continue" test, so a failed idea costs a few thousand rupees and a few weekends, not a year.
6. **Before any of it: the name.** "Nemo" and "Nemotron" collide with NVIDIA's NeMo/Nemotron AI names, and "Nemo" is a very common name. I found no reported dispute between NVIDIA and a small "Nemo" product [web], but I also could not search the Indian trademark register [gap]. For a public, paid product you want a name you have checked and can own (section 5.6).

My honest view of the return: **do not plan on the money**. Plan on a small, controlled experiment that costs little, teaches you whether anybody wants this, and, at best, becomes a modest income. If you also use the same work to give your own showroom a customer assistant, the return on your time is much more certain.

---

## 2. What I found in the code, and why I would not simply open the current Nemo **[code]**

| Fact | What it means for going public |
|---|---|
| `nemotron_bot.py` is **104,533 lines**. About **677 lines** mention the owner and **569** call `OWNER.get('id')`. | The program assumes one boss. Every tool, setting and permission answers to that one id. Making that safe for strangers means proving all 677 places correct; one miss leaks your data or powers. |
| About **330 tables** across roughly **a dozen database files**, with paths fixed to `/root/nemo*.db`, `/root/nemo_prime.db` and others. | There is no "tenant" concept. Memory (`facts`, `turns`) is keyed by `chat_id`, which is a good start for per-person memory, but settings, learning, jobs, devices, secrets and the rest are one person's. |
| `web_ai` (used by the website chat and the Twilio WhatsApp/voice hooks) runs the **owner's** memory and persona. The earlier doors review already found it has no per-sender check on WhatsApp. | Opening the website to others today would give them a chat that reads and writes **your** memory. |
| Website login is "log in with Telegram" (`_n95_tglogin`); there is no sign-up, no email login, no plans, no payments, no per-user quota (Circle's limits exist but each person is approved by you by hand). | All of the public product's front office (accounts, billing, quotas, abuse tools) does not exist and is the real work. |
| The same server also runs **another app** (`quantumfx_bot`) and holds your broker, mail, Drive and AI keys; it has about 3.8 GB RAM and 2 cores. | A public product on this box puts strangers' traffic, and any break-in, next to your money and your credentials. It also would not fit in memory at any real load. |
| Telegram sending is spread over **2,660** `send_text` calls, **144** `tg` calls and about **10** direct file posts. | Adding a second door to the same code is invasive; a new service with one clean "send" function is easier. |

So the plan below does **not** try to make the 104,000-line program multi-user. It builds a **new, thin service** and reuses *ideas and small pieces* from Nemo (persona prompts, the plain-words layer, office helpers such as GSTIN/PAN checks and amount-in-words, report/PDF code, the study helper, the Globe knowledge tables) by copying the parts that have no owner-dependent code. Anything that touches your server, mail, Drive, broker or settings stays behind.

Two fixes are worth making in the personal Nemo **regardless** (they were found in the earlier doors review): the WhatsApp/voice hooks must check who is calling, and the website must not depend on Telegram alone. They do not belong to this project but they are cheap and close real holes.

---

## 3. What "separate" means, item by item

| | Your personal Nemo (stays as is) | Nemo Public (new) |
|---|---|---|
| Server | Your current VPS (shared with `quantumfx_bot`) | **A different, small server**, nothing else on it, no route to your VPS |
| Web address | Private link/ Tailscale / current site | **Its own domain** (for example a `.in` or `.com`) behind Cloudflare |
| Database | The `/root/nemo*.db` files | **Its own database** (section 5.3); nothing shared, nothing copied from yours |
| AI keys | Your keys | **Separate keys with a hard monthly spending cap**, one set per environment |
| Bot / chat identity | Your Telegram bot and its token | A **new bot** (new token and username), a new website, a new support email |
| Login | Telegram, owner lock | Email or Google sign-in, passkeys later; Telegram as an optional door |
| Powers | Everything | Chat, memory, voice, pictures, reports, office/study helpers; **no** server, mail, Drive, broker, downloads or self-edit |
| Trading | Sigma, Scout, Globe, paper agent | **None.** Globe knowledge pages as education only |
| Admin | You, in Telegram | A small admin page for you plus alerts; a kill switch |
| Brand and legal | Personal | A **business identity** (proprietorship or company), its own policies, grievance contact, payment account |
| Code | `nemotron_bot.py` | **A new private repository** (section 9: I can only touch `trading-bot` unless you add another) |

---

## 4. What Nemo Public is, and what it is not

### 4.1 Do not aim at "everyone"

A general assistant competes with ChatGPT, Gemini and Perplexity, which have been given away free or nearly free in India: ChatGPT Go free for 12 months from 4 Nov 2025 (normally ₹399 a month, with auto-renewal for those who claimed it starting early Nov 2026), Gemini's paid tier free for 18 months through Jio [web]. Indians use these tools heavily and pay little: Sensor Tower data, as reported, put Indian spending on ChatGPT subscriptions since 2023 at about $8M against about $330M from Americans [web]. When Perplexity's free Airtel year ended, its Indian downloads were estimated to have fallen by more than 90% against the six months before [web, Sensor Tower estimate]: people who arrive for "free" mostly do not stay to pay. A new general chatbot has nothing to offer that those do not.

What a small team *can* offer is **fit**. Candidate wedges, with my honest read **[mine]**:

| Wedge | Who pays | Why Nemo has an edge | Main worry |
|---|---|---|---|
| **A. Shop / showroom assistant** (customer questions in Gujarati/Hindi/English, price and stock answers, invoices, GST helpers, follow-up reminders) | Shop owners, ₹1,000-3,000 a month | You already run a showroom, and Nemo already has the showroom copilot and the office helpers; B2B converts better [web: a 2026 study puts the B2B SaaS median around 8%, against a reported 2.18% median for mobile freemium apps] | Needs the official WhatsApp Business API for customer chat (allowed for customer support, unlike a general assistant [web]); more setup per shop |
| **B. Family / elders' assistant in Gujarati and Hindi** (voice-first, simple, reminders, forms, letters, bills explained) | Families; maybe a children-pay-for-parents plan | Voice and regional language are weak spots of the big apps for many users **[mine, unverified]** | Hard to reach the buyers; low price; elders need a phone-call door |
| **C. Student / exam helper** (explain, quiz, study plan, in regional languages) | Students and parents | The study and quiz helper already exists | Many free competitors; under-18 users trigger the strictest data rules (section 7) |
| **D. General AI assistant** | Anyone | Nothing special | Crowded, free, high churn [web] |

My recommendation is **A first** (it also pays back your own showroom), with the shared core built so B can follow. This is your call and your market knowledge; I only know what is in the code and the search results.

### 4.2 What goes in, what stays out

**In:** chat in English/Hindi/Gujarati, per-user memory (with "forget me"), voice notes in and out, picture questions, simple reports/PDFs, office helpers (GSTIN/PAN format checks, amount in words, letter/invoice drafts), study helper, world-market *education* (hours, holidays, glossary, how options work).

**Out, permanently, for the public product:** anything that runs commands on a server or a computer, reads someone's mail or Drive, installs software, edits code, downloads videos (copyright and cookie problems), touches a broker, or posts to the outside world for the user. These are exactly the abilities that make "prompt injection" dangerous. The sources I found describe the risky combination as private data plus untrusted content plus the ability to act; remove the last one and most attacks lose their point [web].

**Out, for now:** buy/sell signals, option ideas, "tips". Section 7 explains why.

---

## 5. How it would be built

### 5.1 Picture

```
 people ──► Cloudflare (DNS, proxy, bot check, rate limit)
                │
                ▼
        Nemo Public server (small VPS, Mumbai)
        ├─ web app + API (installable on phones)      ◄── also: new Telegram bot (webhook)
        ├─ one "turn" function: who → limits → memory → model → answer
        ├─ per-user store (database, section 5.3)
        ├─ quota + spend manager  (daily/monthly caps, global kill switch)
        ├─ model gateway (two providers, automatic fallback, hard caps)
        ├─ payments webhook (later)
        └─ admin page (you only)
        │
        ├──► backups to object storage (daily, tested restore)
        └──► alerts to you (a private Telegram chat) 
 (no link to your personal VPS; at most a one-way health ping)
```

### 5.2 Web address and hosting

- **Domain:** a `.com` costs about ₹1,000 a year; a `.in` varies by seller, with renewal prices far higher than first-year offers at some registrars, so compare the *renewal* price [web]. Add privacy protection, and register it to the **business** identity, not your home address **[mine]**.
- **Cloudflare (free plan)** in front: DNS, TLS, caching, a bot challenge (Turnstile) on sign-up and sign-in, basic WAF and a rate-limit rule. Turnstile's free plan is reported as free and unmetered, but sources disagree on how many rate-limiting rules the free plan allows (1 against 5) **[gap: check Cloudflare's page]**.
- **Server:** a separate small VPS in Mumbai. One vendor blog reports entry plans (1 vCPU, 1-2 GB, 20-30 GB) from about $5-7 a month [web, a seller's blog]; I could not read AWS, DigitalOcean or Vultr pricing pages **[gap]** and I believe Hetzner has no Indian region (unconfirmed). Begin with **2 GB RAM, 2 vCPU** and only the public service on it.
- **Never** run it on the box that holds your broker, mail, Drive or AI keys, and never give it a login to that box.

### 5.3 Database

Two sensible choices, both [web] opinion-level:

| Option | How it works | Good | Watch out |
|---|---|---|---|
| **A. A small control database plus one SQLite file per user** (backup with a replication tool such as Litestream to object storage) | Accounts, plans and usage in one control file; each person's chats and memory in their **own file** | Strongest isolation (a bug cannot read another file); nearly free; same technology you already run; simple backups | One writer at a time per file (fine per user); cross-user reports need the control file; rule of thumb quoted for single-server SQLite: below about 10,000 daily users |
| **B. One managed Postgres with row-level security** | One shared database; each table has a tenant column; the database itself refuses rows from other tenants | Standard for SaaS; many users and heavy reporting; managed backups | About $20-25 a month for a managed one [web]; **isolation depends on getting the setup right** (the app's database role must not own the tables, row security must be forced, the tenant id must be set per transaction and come from the logged-in session, never from the model's output) |

**Recommendation [mine]: start with A**, because for the first few thousand users it is cheaper and gives the strongest boundary, and move to B only when one of these happens: more than about 5,000 daily users, backups or write contention hurt, or you need cross-user analytics. Memory search (full-text and, later, embeddings) lives **inside each user's file**, so retrieval can never cross users.

Backups: daily snapshot plus continuous replication to object storage in a different provider or region; **a restore is tested monthly**, otherwise it is not a backup.

### 5.4 Identity and login

- Sign in with **email link or Google** first (no SMS codes: Indian SMS needs registered templates and costs money per message **[gap]**); passkeys next; a Telegram login as an optional door.
- Each person gets a random user id; the **server session** carries it; the model never sees or chooses it.
- A visible **"Delete my data"** and **"Download my data"** button from day one (section 7).
- Age gate: **18+ only in the first release**, stated in the terms and asked at sign-up. This avoids the parental-consent machinery for children's data (section 7).

### 5.5 Models and cost control

- **Two providers** behind one internal gateway with automatic fallback (the personal Nemo already does this with its own gateway; the idea can be copied).
- Separate API keys, each with a **hard monthly spending limit set in the provider's console**, plus an in-app daily cap per user and a **global daily budget**: when it is spent, Nemo Public says so and stops, instead of spending more.
- Use the **cheapest model that answers well** for most turns; keep the larger one for the few that need it.
- Read each provider's usage policy before launch; several restrict use by minors and require telling users they are talking to an AI **[mine, general knowledge, not checked this session]**.

### 5.6 Name and brand

- "Nemo"/"Nemotron" are NVIDIA's AI product names [web]. NVIDIA has previously renamed a product after a naming dispute (the Modulus case [web]) and Indian AI naming fights are active [web]. I found **no** reported dispute with a small "Nemo" product, but that is absence of news, not clearance.
- Process: pick 3 names you like; check the Indian trade-mark register, domain, app stores and Telegram username; take one trade-mark attorney's advice before printing anything. I can do the online checks I am allowed to; I cannot clear a mark.
- Do not name the new product or its files after the personal Nemo. The personal bot can keep its private name.

### 5.7 Doors

First the **web app** (installable on phones; the personal Nemo's `/app` is the model for the screens), second a **new Telegram bot** (webhook, not polling), later **WhatsApp**. WhatsApp's business terms bar general-purpose AI assistants from 15 Jan 2026 [web, from the earlier doors research], so on WhatsApp the *only* sensible use is a **customer-support assistant for a business** (wedge A), through the official API, not a public assistant.

### 5.8 What I can reuse and what I would write new

| Reuse (copy small pieces) | Write new |
|---|---|
| Persona and plain-words prompts; office helpers; report/PDF builder; study/quiz helper; Globe knowledge tables (education); the idea of Circle-style limits; the fallback gateway idea | Accounts and sessions; per-user store; quota and budget manager; abuse tools; admin page; payment webhooks; terms/privacy pages; moderation hooks; deployment and backup scripts; a **cross-user isolation test suite** |

Size estimate **[mine]**: the first private-beta release is about 3,000-5,000 lines of new Python plus a small web front end, with tests. It is a new project, not a v102.

---

## 6. Open to everyone without getting burned

| Threat | What it looks like | What stops it |
|---|---|---|
| **Cost abuse** | Bots sign up, ask long questions all day; one user drains the budget | Turnstile and email check on sign-up; per-user daily message and token caps; maximum message length; global daily budget with auto-stop; provider-side hard caps; no unlimited plan |
| **Data leaking between users** | A bug returns someone else's memory | Per-user database file (option A) or forced row-level security (B); user id only from the session; no shared caches without the user id in the key; **tests that deliberately try to read another user's data** |
| **Prompt injection / jailbreak** | A web page or document tells the bot to reveal data or act | The bot has **no actions**; documents and web text are treated as data, not instructions; system prompt holds no secrets; outputs filtered for key-like strings |
| **Harmful content** | Requests for illegal or abusive material; synthetic images used to deceive | Provider moderation plus your own refusal list; a "report" button; for any image or audio the bot creates, a visible AI label [web: the 2026 IT Rules amendments require labels on synthetic content and fast takedown] |
| **Account takeover** | Stolen logins | Email links with short expiry; passkeys; rate limits on sign-in; sign-out everywhere |
| **Over-reach by Nemo itself** | The bot gives medical, legal or financial advice with confidence | Standing disclaimers; refuse to give personal investment advice; honest "I'm not sure" behaviour (already a Nemo principle) |
| **Outage and surprise bills** | Provider down; traffic spike | Two providers with fallback; alerts to you; kill switch you can flip from Telegram |
| **Your time** | Support messages, takedown requests, payment disputes | A support email and a one-page help site; canned answers; limit sign-ups (invite codes) until you can cope |

---

## 7. India: the rules to plan around

I am not a lawyer and these are search summaries (blogs, law-firm notes). **Have a lawyer or CA review before taking money or opening sign-up.**

| Topic | What I found | What to do |
|---|---|---|
| **SEBI (investment advice)** | Paid stock tips, buy/sell signals or trade recommendations, including a paid tier or course, need registration as a Research Analyst or Investment Adviser; "AI" or "algo" branding does not change that [web]. I did not find specific penalty amounts **[gap]**. | **No signals, tips or option ideas in the public product.** Education and calendars only. If you ever want signals, that is a separate regulated business. |
| **DPDP Act and Rules** | Rules notified 13 Nov 2025; most duties (notice and consent, security, breach reporting, children's data, deletion rights) apply from about **13 May 2027** [web]. Under 18 means verifiable parental consent; no tracking or targeted ads aimed at children [web]. | Build now what is cheap: a clear notice, purpose-limited data, delete/export buttons, retention limits, breach plan, and a contact. **18+ only** in the first release. Treat the AI model providers as processors and sign their data terms. |
| **IT Rules (2026 amendments)** | In force 20 Feb 2026 [web]: synthetic content must be labelled (visible label on images, spoken prefix on audio); orders to take content down must be acted on within 3 hours (it was 36) [web]; tools that create synthetic media carry duties for what they produce. The heavier duties target large social platforms. Grievance-officer and privacy-policy requirements were not covered by what I found **[gap]**. | Label every generated image and audio; keep a takedown route that someone watches; publish a **grievance contact**; have a lawyer say which category a small chatbot falls in. |
| **Payments** | Razorpay's published domestic fee is 2% + 18% GST (about 2.36%); small-merchant UPI is reported at zero merchant discount, though one post mentions 0.4% **[conflict: check]**. RBI's e-mandate framework allows recurring debits up to ₹15,000 without an extra OTP, with pre-debit notice rules whose details differ between sources **[gap]** [web]. | Start with a payment link / one-time packs; add subscriptions once the pre-debit and cancellation flow is checked. Never store card or UPI details yourself. |
| **GST and tax** | Services providers register for GST above a ₹20 lakh turnover threshold; SaaS is taxed at 18% [web, secondary]. Income from this is business income. | A CA decides when to register; register early if you want to claim input credit. Issue proper invoices. |
| **Consumer rules** | Clear pricing, easy cancellation and refunds are expected **[mine, general]**. | Terms, privacy policy and refund/cancellation page, written plainly, from day one. |
| **Telegram payments** | Digital goods in a Telegram bot go through Telegram Stars; reports say the effective payout is roughly 1 cent per Star after app-store fees [web, a vendor blog] **[gap: read Telegram's current terms]**. | If you sell inside Telegram, price in Stars; otherwise sell on the website. |
| **WhatsApp** | General-purpose AI assistants are barred from the official business API since 15 Jan 2026 [web, earlier research]; business customer-support bots are allowed. Unofficial libraries risk a ban of the number. | Wedge A only, through the official API, under the shop's own business account. |

---

## 8. The money: costs, price, and an honest break-even

All numbers use **₹90 = US$1** (an assumption; use the day's rate). Prices below are *reported*; confirm them before relying on them.

### 8.1 What it costs to run

| Item | Stage 1 (about 30 testers) | Stage 2 (a few thousand users) | Source |
|---|---|---|---|
| Server | about ₹500-1,000 / month | ₹1,500-4,000 | [web, one seller]; check AWS/DO/Vultr |
| Domain | about ₹1,000 / year (≈ ₹85 / month) | same | [web] |
| Cloudflare, Turnstile | ₹0 | ₹0 (Pro only if needed) | [web] |
| Database | ₹0 (SQLite files) | ₹0 or about ₹2,000 (managed Postgres) | [web] |
| Backups, object storage | about ₹100-300 | ₹300-1,000 | [mine] |
| Email sending, monitoring | ₹0 (free tiers) | ₹500-2,000 | [mine] |
| **Fixed total** | **about ₹1,000-2,000 / month** | **about ₹5,000-10,000 / month** | |
| AI model use | see below; grows with users | | |
| One-off: lawyer review of terms and privacy, trade-mark search/filing | **₹10,000-40,000 is a normal range** | | **[mine, unverified]** |

### 8.2 The cost per user is the number that decides everything

For one chat turn of about 1,500 input tokens (history plus memory) and 300 output tokens, at reported list prices **[mine arithmetic on web prices]**:

| Model tier (reported price per million tokens, in / out) | Cost per turn | Per 100 turns |
|---|---|---|
| Cheapest small tier ($0.10 / $0.50; reported by one outlet only) | $0.0003 | about ₹2.7 |
| Mid small tier ($0.25 / $2.00) | $0.001 | about ₹8.8 |
| Older small tier ($1 / $5) | $0.003 | about ₹27 |

A light user (30 turns a month) therefore costs about **₹1-8**; a heavy one with long documents, voice or images costs **10-50 times** more (voice and image costs were not researched **[gap]**).

### 8.3 Break-even for a subscription app

Assumptions **[mine]**: a paid plan at **₹199 a month**; payment fee 2.36%; a paying user costs ₹25 a month in model use; fixed costs ₹3,000 / 6,000 / 15,000 a month at 1,000 / 5,000 / 20,000 monthly active users (MAU).

*Share of users who must pay just to break even:*

| MAU | free user costs ₹1 | free user costs ₹4 | free user costs ₹8 |
|---|---|---|---|
| 1,000 | 2.3% | 4.0% | 6.2% |
| 5,000 | 1.3% | 3.0% | 5.2% |
| 20,000 | 1.0% | 2.7% | 4.9% |

*Monthly result at 5,000 MAU:*

| Free user cost → | ₹1 | ₹4 | ₹8 |
|---|---|---|---|
| **1% pay** | −₹2,500 | −₹17,300 | −₹37,100 |
| **2% pay** (reported median for mobile freemium is 2.18% [web]) | **+₹6,000** | −₹8,700 | −₹28,300 |
| **4% pay** | +₹23,100 | +₹8,700 | −₹10,500 |

**What this says:** with a typical 2% conversion, the app only makes money if each free user costs about **₹1 a month or less**. So the design rule is: *the free tier must be small and cheap* (a few messages a day on the cheapest model, no free voice or images, short memory), and the paid tier must be clearly better. And these are the friendly numbers: AI apps reportedly lose annual subscribers about 30% faster than non-AI apps (RevenueCat, as summarised by TechCrunch), though the same data says they earn more per paying user [web], and Indian users pay less than American ones [web].

### 8.4 Ways to earn, ranked by how likely they are to work for a one-person project **[mine]**

| Model | Notes |
|---|---|
| **1. Business plan for shops** (wedge A) | Example: 10 shops at ₹1,500 a month is ₹15,000 revenue and roughly ₹10,000 after costs; 20 shops about ₹23,000; 50 shops about ₹63,000. Fewer customers, higher price, more support per customer. This is the most realistic first income. |
| **2. Credit packs** (pay ₹99 for a block of messages or reports) | No subscription mandate to manage, no churn problem, matches irregular use; works well with a payment link |
| **3. Subscription ₹149-299** | Needs the free tier controlled (8.3); competes with free giants |
| **4. Family plan** (one payer, several members) | Fits wedge B |
| **5. Ads or selling data** | **Not recommended**: privacy rules, children's-data rules, and trust |
| **6. Telegram Stars** | Possible for bot users; the payout is lower and rules need checking |

### 8.5 Your "return on investment and time"

Count three things from the first day, in a simple monthly sheet: **cash out** (server, domain, model use, fees, legal), **hours** (yours and mine), and **cash in**. A reasonable stop rule is set *before* you start: for example, a total cash budget you are happy to lose (my suggestion for stages 1-2 is **₹30,000-50,000**, but this is your decision) and a date by which the gates in section 9 must be met. If they are missed, stop or leave it as a free hobby project; that is a good result, because you learned it cheaply.

---

## 9. The staged plan, with go / no-go gates

| Stage | What | Time | Cash | Gate to continue |
|---|---|---|---|---|
| **0. Decide** | Choose the wedge, the audience, the name shortlist, the budget cap; open a business identity if you want one; check names (domains, Telegram, app stores); read the provider and Telegram terms | 1 week | ≈ ₹0-2,000 | You can say in one sentence who it is for and why they would pay |
| **1. Private beta** | New server, domain, Cloudflare; **Nemo Public v0**: accounts, chat in 3 languages, per-user memory, quotas and spend caps, kill switch, admin page, terms and privacy drafts, isolation tests; invite 20-50 people (family, friends, shop customers) | 3-5 weeks of build | ≈ ₹1,000-2,000 / month + legal ₹10,000-40,000 | ≥ 30% of invitees still active in week 4; measured cost per active user known and under your cap; **zero** cross-user leaks in tests; at least 5 people say they would pay and 2 actually do on a ₹99 pack |
| **2. Open sign-up, capped** | Public sign-up with Turnstile; free tier on the cheapest model; payments (links first, subscriptions later); grievance contact; takedown routine; DPDP notice and delete/export | 3-4 weeks | ≈ ₹5,000-10,000 / month | Free cost per user at or below ₹1-2; paying share at or above the break-even in 8.3 for your actual numbers; support load you can handle |
| **3. Grow or pivot** | Wedge A tooling for shops (official WhatsApp Business API for support, per-shop settings); Hindi/Gujarati voice; more doors; maybe the family plan | open | funded by revenue | Revenue covers all costs and some of your time |

**Kill criteria, decided now:** after stage 1, if fewer than 10 people are using it in week 4, stop. After stage 2, if you are still losing money after three months at a cost you set, cap it, make it invite-only, or stop.

---

## 10. Risks, ranked **[mine]**

| # | Risk | How bad | Mitigation |
|---|---|---|---|
| 1 | **Nobody pays** (free giants, low spend, fast churn) | Very likely for a general assistant | Narrow wedge, B2B first, tiny free tier, kill criteria |
| 2 | **Free-tier cost drain** | High | Caps in 6; cheapest model; no free voice/images |
| 3 | **Name conflict** with NVIDIA's NeMo/Nemotron or others | Medium | New name, attorney check (5.6) |
| 4 | **Legal slip** (SEBI, DPDP, IT Rules) | High if ignored | No signals; 18+; labels; lawyer review before taking money |
| 5 | **Data leak between users** | Severe for trust | Separate file per user, tests, no actions |
| 6 | **Your time**: support, abuse reports, takedowns | Medium, constant | Invite codes, canned replies, help page, strict stage gates |
| 7 | **Provider change** (price, terms, outage) | Medium | Two providers, cost sheet updated monthly |
| 8 | **Account bans** (Telegram or WhatsApp) | Medium | Official APIs only, no spam, no unofficial WhatsApp libraries |
| 9 | **Tax and invoices** done late | Low-medium | CA from stage 2 |
| 10 | **Mixing public and personal** (shared server, keys or repo) | Severe | Everything in sections 3 and 5 stays separate |

---

## 11. What this changes in your current plan

- **Nothing in your personal Nemo has to change** for this project. The two holes in section 2 are worth fixing anyway.
- **The "I want all" feature list** (Mind, Voice, Heart, Routines, Hands, Reach) is still the plan for *your* Nemo. Some of it (memory quality, voice, Hindi/Gujarati) will be built once and could later be reused by the public product; the "Hands" features (typing and clicking on your computer) never go public.
- **"All VPS changes must go through Nemo."** The new server is a new machine. Decide whether it is managed through your personal Nemo (convenient, but it creates a link between the two) or separately with step-by-step instructions I write and you run. My advice: **separate**, with at most a one-way health ping.
- **My access.** In this session I can only change the `trading-bot` repository. The public project belongs in its **own private repository**; you would create it and add it, or tell me to put it in a sub-folder here for now (faster, but it mixes the two projects, which I would not recommend).

---

## 12. What I could not verify

- Any current price: servers (AWS, DigitalOcean, Vultr), Cloudflare's rate-limit allowance, Razorpay's subscription fee, `.in` renewals, the "cheapest small tier" model price (one outlet only), voice/image costs.
- Whether a small chatbot is an "intermediary" with a grievance officer duty, and exactly which IT Rules duties apply.
- SEBI penalty amounts for unregistered signals.
- Indian trade-mark search for any name, including "Nemo".
- Telegram's current terms for paid bots; Telegram Stars payout numbers.
- RBI e-mandate pre-debit details (sources conflict).
- Any claim about your target users' willingness to pay: that needs real people, which is what stage 1 is for.
- Everything here is **offline research and arithmetic**; no server, domain, payment or live service was touched.

---

## 13. Questions for you

1. **Who is it for?** Shops (wedge A), families (B), students (C), or everyone? My advice: A, then B.
2. **How much cash are you willing to lose** over stages 1-2, and **how many hours a week** can you give it?
3. **A separate small server**: agreed? (I would not use the current box.)
4. **Name:** give me 3 names you like (not "Nemo" or "Nemotron" for the public product) and I will run every online check I can.
5. **Business identity:** do you have, or want, a proprietorship / GST / Udyam registration for this, or do you start free-only until it earns?
6. **Invite-only first** (my advice) or open to all from the start?
7. **Telegram bot too**, or website only at first?
8. **18+ only** at launch (my advice)?
9. **Languages:** English + Hindi + Gujarati from day one?
10. **Repository:** a new private repo that you create and add, or a folder here for now?
11. **Server management:** through personal Nemo, or separate (my advice)?

When you answer these, I start stage 0 (a one-page product brief, the name checks, the terms and privacy drafts for a lawyer, and the stage-1 build plan). I do not start building until you say so.

---

## 14. Sources

Search summaries, secondary sources; verify on the official pages.

- SEBI and signals: [SEBI algo trading rules 2026 (Sahi)](https://www.sahi.com/blogs/sebi-algo-trading-rules-2026-what-every-retail-trader-must-know-before-april), [Is AI trading legal in India? (Sahi)](https://www.sahi.com/blogs/is-ai-trading-legal-in-india), [Telegram stock tips vs SEBI research (Sahi)](https://www.sahi.com/blogs/telegram-stock-tips-vs-sebi-registered-research-india), [SEBI digital compliance rules 2026 (Aarna Law)](https://www.aarnalaw.com/insights/sebis-new-digital-compliance-rules-what-investment-advisers-must-know-in-2026), [SEBI: AI alerts are not findings (MediaNama)](https://www.medianama.com/2026/09/223-sebi-ai-enforcement-adjudication/)
- DPDP: [DPDP Rules 2025 (EY)](https://www.ey.com/en_in/insights/cybersecurity/transforming-data-privacy-digital-personal-data-protection-rules-2025), [Implementation timeline (Consently)](https://www.consently.in/blog/dpdp-rules-2025-implementation-timeline-india), [Age 18 and parental consent (Xident)](https://xident.io/blog/india-dpdp-age-verification-verifiable-parental-consent-childrens-data-2026/), [DPDP for AI chatbots (Consently)](https://www.consently.in/blog/dpdp-compliance-ai-chatbots-llm-apps-india)
- IT Rules 2026: [Labelling and 3-hour takedown (Hogan Lovells)](https://www.hoganlovells.com/en/publications/india-introduces-mandatory-labelling-for-ai-and-3hour-takedown-for-illegal-content), [Synthetic media rules (Mondaq)](https://www.mondaq.com/india/social-media/1746136/indias-2026-it-rules-on-synthetic-media-a-structural-shift-in-intermediary-liability), [Labelling mandate (exchange4media)](https://www.exchange4media.com/digital-news/new-rule-mandates-clear-labelling-of-synthetic-content-on-digital-platforms-151874.html)
- Free AI in India and willingness to pay: [Free AI tools in India 2026 (DQ India)](https://www.dqindia.com/data-and-ai/free-ai-tools-in-india-are-gemini-chatgpt-perplexity-really-free-in-2026-10965188), [Free AI trials about to expire (AI Insider)](https://aiinsider.in/ai-updates/ai-news/india-free-ai-trials-expiry-2026-chatgpt-gemini-perplexity/), [Free AI deals: Jio, Airtel, ChatGPT Go](https://neelsworld.in/posts/free-ai-deals-india.html), [Perplexity's free offer in India (TechCrunch)](https://techcrunch.com/2026/08/18/perplexitys-free-ai-offer-left-it-with-millions-more-users-in-india/), [AI apps struggle with retention (TechCrunch)](https://techcrunch.com/2026/03/10/ai-powered-apps-struggle-with-long-term-retention-new-report-shows)
- Conversion benchmarks: [Freemium to premium (Adapty)](https://adapty.io/blog/freemium-to-premium-conversion-techniques), [Conversion report (ChartMogul)](https://chartmogul.com/reports/saas-conversion-report/), [State of subscription apps (SaaStr on RevenueCat)](https://saastr.com/the-top-10-learnings-from-revenuecats-state-of-subscription-apps-how-115000-mobile-apps-deliver-16b-in-revenue-whats-working-whats-quietly-killing-growth)
- Model prices: [LLM API pricing 2026 (IntuitionLabs)](https://intuitionlabs.ai/articles/llm-api-pricing-cost-per-task-comparison), [Low-cost LLM comparison](https://intuitionlabs.ai/articles/low-cost-llm-comparison), [Anthropic API pricing overview (Finout)](https://finout.io/blog/anthropic-api-pricing). The $0.10 / $0.50 tier figure came from one outlet only and is deliberately not linked here: treat it as unconfirmed
- Payments and tax: [RBI e-mandate framework 2026 (Outlook Business)](https://www.outlookbusiness.com/ampstories/news/rbi-e-mandate-framework-2026-new-rules-for-auto-pay-upi-cards-wallets), [OTP-free up to ₹15,000 (Shoonya)](https://blog.shoonya.com/e-mandate-norms/), [Razorpay subscriptions for SaaS](https://razorpay.com/learn/payment-solutions-subscriptions-saas-india/), [Razorpay pricing posts](https://razorpay.com/blog/?p=27895), [GST threshold for services (Tally)](https://tallysolutions.com/gst/gst-limit-registration-threshold-india/), [SaaS billing in India (Codingclave)](https://codingclave.com/blog/saas-billing-india-stripe-razorpay-2026)
- Telegram monetisation: [Telegram bot monetisation 2026 (ExitBid)](https://exitbid.io/blog/telegram-bot-monetization-2026), [Telegram Stars (Telegram)](https://telegram.org/blog/telegram-stars/pl)
- Naming: [NVIDIA settles the "Modulus" naming dispute](https://www.newsbytesapp.com/news/business/nvidia-settles-trademark-dispute-with-modulus-financial-engineering-over-name/tldr), [India's AI trademark wars (Outlook Business)](https://www.outlookbusiness.com/deeptech/artificial-intelligence/inside-indias-ai-trademark-wars-gemini-chatgpt-grok-and-the-legal-fights-over-naming-rights), [Global AI names in India (Storyboard18)](https://www.storyboard18.com/digital/global-ai-giants-face-trademark-turbulence-in-india-as-homegrown-claims-take-precedence-66883.htm)
- Multi-user isolation: [Multi-tenant data isolation with Postgres row-level security (AWS)](https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security), [Why isolation starts at the database (Cockroach Labs)](https://cockroachlabs.com/blog/multi-tenant-ai-agents-why-data-isolation-starts-at-the-database), [Multi-tenant isolation for AI agents (Blaxel)](https://blaxel.ai/blog/multi-tenant-isolation-ai-agents), [Multi-tenant memory tools (Mem0)](https://mem0.ai/guide/ai-memory-tools-multi-tenant-data-isolation), [Shared vector DBs leak across tenants](https://aiweekly.co/alerts/shared-vector-dbs-leak-user-data-across-ai-agent-tenants)
- Infrastructure: [Cheap VPS in Mumbai, 2026 (Valebyte, a seller)](https://valebyte.com/en/blog/cheap-vps-in-india-mumbai-2026-price-comparison/), [Turnstile pricing (Prosopo, a competitor)](https://prosopo.io/tools/cloudflare-turnstile-pricing/), [Cloudflare free plan limits (CostBench)](https://costbench.com/software/cdn-edge/cloudflare/free-plan/), [.IN registry tariff](https://registry.in/tariff), [.COM price notice (DomainIndia)](https://www.domainindia.com/client/announcements/50), [SQLite vs PostgreSQL 2026](https://www.kunalganglani.com/blog/sqlite-vs-postgresql-for-apps), [SQLite in production](https://jacar.es/en/sqlite-in-production-not-just-for-mobile/)
