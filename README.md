# Startup Signal Pipeline

An automated data pipeline that discovers startups that have recently raised funding and are actively hiring in tech roles. It fetches data from news feeds, enriches it with an LLM, finds each company’s careers page, and publishes qualified leads to Google Sheets while sending instant Telegram alerts.

### 📊 Live Demo Output

https://docs.google.com/spreadsheets/d/1DmddsH39He3GXLs31ty-kTQznLH9t3fUb3VkqAlhSPg/edit?usp=sharing

---

### 🏛️ High-Level Architecture

The `run_pipeline()` orchestrator in `main.py` wires together six stages that run every time the job executes: ingest → enrich → resolve → hiring intelligence → persistence → publish.

```32:101:main.py
print("\n=== STEP 1: Fetch Recent Funding Articles ===")
all_articles = fetch_recent_articles(days_back=7)
...
save_to_sheet(final_output)
```

1. **Ingest** new funding articles via RSS (`fetch_recent_articles`).
2. **Pre-filter** out already-processed URLs with the DB-driven pre-flight check.
3. **Enrich** the remaining articles with Gemini (`enrich_articles`).
4. **Resolve** official company domains via LLM output → article crawl → DuckDuckGo → smart guessing.
5. **Detect hiring signals** on careers pages, store tiered intelligence, and alert via Telegram.
6. **Publish** the curated list to Google Sheets for the go-to-market team.

---

### 🧠 Key Design Decisions & Problems Solved

#### 1. Efficiency & Cost: The “Pre-Flight Check”
**Problem:** Calling the LLM on previously processed articles wasted time and money.  
**Solution:** `main.py` now collects the last 7 days of URLs, then asks `check_articles_exist()` which ones are already in SQLite before it spends tokens. Only unseen URLs move forward, and we still cap each run at 20 items for safety.

```32:58:main.py
article_urls = [a.get("url") for a in all_articles if a.get("url")]
existing_urls = check_articles_exist(article_urls)
new_articles = [a for a in all_articles if a.get("url") not in existing_urls]
```

```42:66:app/store/upsert.py
query = (
    f"SELECT source_url FROM funded_companies "
    f"WHERE source_url IN ({placeholders})"
)
...
return {row[0] for row in cur.fetchall()}
```

#### 2. Reliability: LLM Extraction (vs. Brittle Regex)
**Problem:** Headlines alone are inconsistent; regex melts down on phrases like “extends its Series A.”  
**Solution:** We fetch the full article body, pass it with the headline into Gemini, and demand strict JSON. The prompt guards against hallucinations (e.g., “Do not infer website_url”) while the parser cleans any stray markdown fences.

```37:126:app/extract/llm_parse.py
PROMPT = """
You are a precise financial data extraction model.
Return ONLY valid JSON. No commentary.
...
"investors": list,
"lead_investor": string or null,
...
"""
...
response = MODEL.generate_content(prompt_text)
raw = response.text.strip().replace("```json", "").replace("```", "").strip()
return json.loads(raw)
```

#### 3. Compliance & Signal Quality: ATS Probing (vs. LinkedIn Scraping)
**Problem:** Scraping LinkedIn violates ToS and yields noisy results; we needed durable, legal signals.  
**Solution:** `app/hiring/detect_ats.py` executes a “Crawl → Find → Probe” strategy. It first finds the careers link on the homepage, prioritizing known ATS hosts like Greenhouse and Lever, then calls their public JSON endpoints before falling back to internal pages.

```90:118:app/hiring/detect_ats.py
# Priority 1: direct link to known ATS
for a in home.find_all("a", href=True):
    ...
    for pattern, provider in ATS_PATTERNS.items():
        if pattern in host:
            return {"url": abs_href, "provider": provider}
# Priority 2: internal careers links
...
# Priority 3: text matches
```

```120:197:app/hiring/detect_ats.py
api = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
resp = _safe_get(api)
...
return fetch_internal_jobs(careers_url)
```

#### 4. Accuracy: Eliminating “Hiring Hallucinations”
**Problem:** Our first pass counted keywords anywhere on the site, confusing “Meet the Team” pages for job boards.  
**Solution:** After probing the careers endpoint, we parse structured job data (JSON-LD, API payloads) and classify tech roles explicitly. Tiering depends on recency via `RECENT_DAYS`, not raw counts, preventing stale listings from triggering Tier A.

```23:78:app/hiring/detect_ats.py
TECH_TITLE_KEYWORDS = {...}
RECENT_DAYS = 14
...
def _is_tech_title(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in TECH_TITLE_KEYWORDS)
```

```302:336:app/hiring/detect_ats.py
recent_cutoff = _now_utc() - timedelta(days=RECENT_DAYS)
recent_jobs = [j for j in tech_jobs if j.get("posted_dt") and j["posted_dt"] >= recent_cutoff]
...
return {
    "hiring_tier": tier,
    "careers_url": careers_url,
    "ats_provider": provider,
    "tech_roles": tech_roles,
    "details": details,
}
```

#### 5. Coverage: Multi-Stage Domain Resolution
**Problem:** New startups often lack obvious domains; simple guesses (“company.com”) fail on names like Fastbreak AI.  
**Solution:** `resolve_company_domain()` falls back gracefully: trust the LLM-extracted URL when we have it, crawl the press release for outbound links, search DuckDuckGo for “Company official site,” then smart-guess high-signal TLDs while stripping legal suffixes.

```64:168:app/resolve/domain_resolver.py
def resolve_from_press_release(article_url: str):
    ...
    if clean:
        return clean, 0.92
...
def resolve_company_domain(company_name: str, article_url: str):
    domain, conf = resolve_from_press_release(article_url)
    if domain:
        return {"domain": domain, "confidence": conf, "source": "press_release"}
    domain, conf = resolve_via_duckduckgo(company_name)
    ...
    domain, conf = resolve_via_guessing(company_name)
```

#### 6. Data Integrity: Correct Deduplication
**Problem:** A simple `UNIQUE(company_name)` fails when the same startup raises multiple rounds.  
**Solution:** The schema defines `UNIQUE(company_name, funding_round, announcement_date)` and `upsert_company()` honors it. We store every funding event separately while still preventing true duplicates.

```77:104:app/store/upsert.py
INSERT INTO funded_companies (
    ...
    tech_roles,
    source_url,
    last_seen
)
...
ON CONFLICT(company_name, funding_round, announcement_date)
DO UPDATE SET
    amount_raised_usd = COALESCE(...)
```

```1:26:app/store/schema.sql
CREATE TABLE IF NOT EXISTS funded_companies (
    ...
    UNIQUE(company_name, funding_round, announcement_date)
);
```

---

### 🛠️ Tech Stack

- Python 3.x with `requests`, `BeautifulSoup`, `gspread`, `google-generativeai`, and `sqlite3`
- Gemini LLM for structured enrichment
- SQLite for lightweight persistence
- Google Sheets + Telegram Bot API for outbound publishing
- GitHub Actions (`.github/workflows/run.yml`) for scheduled, serverless execution

---

### 🔧 Local Setup

1. **Clone & create a virtual environment**
   ```bash
   git clone <repo-url>
   cd startup-signal-pipeline
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**  
   Copy `.env.example` (or create `.env`) with:
   - `GEMINI_API_KEY` for enrichment  
   - `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for alerts  
   - `OPENAI_API_KEY` (optional if you test alternative models)

4. **Google Sheets credentials**
   - Place your service-account JSON at the repo root as `google_creds.json`, or set `GOOGLE_CREDS_JSON` to another filename referenced in `app/publish/to_gsheet.py`.

5. **Run a smoke test**
   - Validate Telegram creds: `python scripts/test_telegram_alert.py --message "Pipeline check"`  
   - Boot the pipeline: `python main.py`  
   - The first run seeds the SQLite DB (`data/companies.db`) and appends rows to your sheet.

---

### 📡 Rate Limits & Compliance

- **Gemini 2.5 Flash (GCP)** – running on free credits. Quota is ~15 requests/minute and ~1,000 per day. Each execution processes ≤20 fresh articles, so we stay well below the cap. Usage is monitored through the GCP console.
- **RSS feeds & press releases** – one polite HTTP request per source each run; no aggressive crawling.
- **DuckDuckGo LinkedIn fallback** – optional and disabled by default (`ENABLE_LINKEDIN_FALLBACK`). When enabled it throttles to ≤1 query/sec and handles Bing/DDG timeouts gracefully.
- **Google Sheets API** – default limit is ~60 requests/minute. We append ≤20 rows per execution.
- **Telegram Bot API** – only a handful of alerts per run; non-200 responses are logged.
- **No LinkedIn scraping** – to respect LinkedIn’s ToS we probe ATS APIs and careers pages instead. The “Crawl → Find → Probe” logic hits public job boards (Greenhouse, Lever, Ashby, etc.) or internal career pages to detect real openings.

---

### ☁️ Automation & Deployment

A lightweight GitHub Actions workflow (`.github/workflows/run.yml`) keeps the system serverless: it checks out the repo on a schedule, sets up Python, installs dependencies, and runs `python main.py`. Secrets (LLM keys, Telegram token, Google credentials) are injected from GitHub Repository Secrets, so no credentials live in the workflow definition. Logs capture each stage’s timing, and because the pipeline is fully stateful, repeated runs stay inexpensive—GitHub only pays for new articles while the workflow itself remains container-free (no Docker required).

