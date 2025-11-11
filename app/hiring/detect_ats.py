from __future__ import annotations
import re
import json
import time
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.7",
}

# Strict list of tech-role signals
TECH_TITLE_KEYWORDS = {
    "software", "engineer", "developer", "backend", "front end", "frontend",
    "full stack", "full-stack", "data engineer", "data scientist", "ml",
    "machine learning", "ai", "mle", "platform", "devops", "sre",
    "infra", "infrastructure", "android", "ios", "mobile"
}

RECENT_DAYS = 14

ATS_PATTERNS = {
    "boards.greenhouse.io": "Greenhouse",
    "jobs.lever.co": "Lever",
    "ashbyhq.com": "Ashby",
    "apply.workable.com": "Workable",
    "bamboohr.com": "BambooHR",
}

CAREERS_HINTS = ["/careers", "/jobs", "join-us", "work-with-us"]

# ---------- helpers ----------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _days_ago(dt: datetime) -> int:
    return max(0, int((_now_utc() - dt).days))

def _is_tech_title(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in TECH_TITLE_KEYWORDS)

def _safe_get(url: str, timeout: int = 12) -> Optional[requests.Response]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200 and resp.content:
            return resp
    except requests.RequestException:
        pass
    return None

def _soup(url: str) -> Optional[BeautifulSoup]:
    resp = _safe_get(url)
    if not resp:
        return None
    return BeautifulSoup(resp.content, "html.parser")

def _parse_iso_or_none(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # normalize Z to +00:00 if needed
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None

def _epoch_ms_to_dt(ms: Optional[int]) -> Optional[datetime]:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms/1000, tz=timezone.utc)
    except Exception:
        return None

# ---------- find careers page from homepage ----------

def find_careers_link(domain_url: str) -> Optional[Dict[str, str]]:
    """Return dict: {'url': ..., 'provider': ...} or None"""
    home = _soup(domain_url)
    if not home:
        return None

    # Priority 1: direct link to known ATS
    for a in home.find_all("a", href=True):
        href = a["href"]
        abs_href = urljoin(domain_url, href)
        host = urlparse(abs_href).netloc.lower()
        for pattern, provider in ATS_PATTERNS.items():
            if pattern in host:
                return {"url": abs_href, "provider": provider}

    # Priority 2: internal careers links based on href
    for a in home.find_all("a", href=True):
        href = a["href"].strip().lower()
        if any(h in href for h in ["/careers", "/jobs", "join-us", "work-with-us"]):
            return {"url": urljoin(domain_url, a["href"]), "provider": "Internal"}

    # Priority 3: fallback to exact text matches
    for a in home.find_all("a", href=True):
        text = (a.get_text() or "").strip().lower()
        if text in {"careers", "career", "jobs", "join us", "team"}:
            return {"url": urljoin(domain_url, a["href"]), "provider": "Internal"}

    return None

# ---------- provider handlers ----------

def fetch_greenhouse_jobs(board_url: str) -> List[Dict[str, Any]]:
    # board_url: https://boards.greenhouse.io/<slug>
    slug = urlparse(board_url).path.strip("/").split("/")[0]
    api = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    resp = _safe_get(api)
    if not resp:
        return []
    data = resp.json().get("jobs", [])
    out = []
    for j in data:
        title = j.get("title", "").strip()
        updated = _parse_iso_or_none(j.get("updated_at"))
        out.append({
            "title": title,
            "location": (j.get("location") or {}).get("name"),
            "url": j.get("absolute_url"),
            "posted_dt": updated or _parse_iso_or_none(j.get("created_at")),
        })
    return out

def fetch_lever_jobs(lever_url: str) -> List[Dict[str, Any]]:
    # lever_url: https://jobs.lever.co/<slug>
    slug = urlparse(lever_url).path.strip("/").split("/")[0]
    api = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    resp = _safe_get(api)
    if not resp:
        return []
    postings = resp.json()
    out = []
    for p in postings:
        title = p.get("text", "").strip()
        posted = _epoch_ms_to_dt(p.get("createdAt")) or _epoch_ms_to_dt(p.get("listedAt"))
        out.append({
            "title": title,
            "location": (p.get("categories") or {}).get("location"),
            "url": p.get("hostedUrl") or p.get("applyUrl"),
            "posted_dt": posted,
        })
    return out

def fetch_ashby_jobs(ashby_url: str) -> List[Dict[str, Any]]:
    # No stable public API—parse LD+JSON (JobPosting) or job-card HTML.
    resp = _safe_get(ashby_url)
    if not resp:
        return []
    soup = BeautifulSoup(resp.content, "html.parser")
    out: List[Dict[str, Any]] = []

    # Try JobPosting JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "{}")
        except Exception:
            continue

        # Could be a single JobPosting or a list
        jobs = []
        if isinstance(payload, dict) and payload.get("@type") == "JobPosting":
            jobs = [payload]
        elif isinstance(payload, list):
            jobs = [x for x in payload if isinstance(x, dict) and x.get("@type") == "JobPosting"]

        for j in jobs:
            title = (j.get("title") or "").strip()
            posted = _parse_iso_or_none(j.get("datePosted"))
            url = j.get("hiringOrganization", {}).get("sameAs") or j.get("url") or ashby_url
            out.append({"title": title, "location": None, "url": url, "posted_dt": posted})

    if out:
        return out

    # Fallback: scrape obvious job-card anchors
    for a in soup.find_all("a", href=True):
        txt = (a.get_text() or "").strip()
        if not txt:
            continue
        if any(w in txt.lower() for w in ["engineer", "developer", "data", "ml", "ai"]):
            out.append({"title": txt, "location": None, "url": urljoin(ashby_url, a["href"]), "posted_dt": None})
    return out

def fetch_workable_jobs(workable_url: str) -> List[Dict[str, Any]]:
    # Public board HTML, parse job cards
    soup = _soup(workable_url)
    if not soup:
        return []
    out = []
    for a in soup.select("a[href]"):
        txt = (a.get_text() or "").strip()
        href = a["href"]
        if not txt or not href:
            continue
        # Heuristic: Workable job links look like apply.workable.com/<company>/j/<id>
        if "/j/" in href and "apply.workable.com" in workable_url:
            out.append({"title": txt, "location": None, "url": urljoin(workable_url, href), "posted_dt": None})
    return out

def fetch_bamboohr_jobs(bamboo_url: str) -> List[Dict[str, Any]]:
    soup = _soup(bamboo_url)
    if not soup:
        return []
    out = []
    # BambooHR renders job list in HTML (varies by template). Grab obvious anchors.
    for a in soup.select("a[href]"):
        txt = (a.get_text() or "").strip()
        if not txt:
            continue
        if any(k in txt.lower() for k in ["engineer", "developer", "data", "ml", "ai", "software"]):
            out.append({"title": txt, "location": None, "url": urljoin(bamboo_url, a["href"]), "posted_dt": None})
    return out

def fetch_internal_jobs(internal_url: str) -> List[Dict[str, Any]]:
    soup = _soup(internal_url)
    if not soup:
        return []
    out = []

    # Prefer JSON-LD JobPosting if present (most reliable)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "{}")
        except Exception:
            continue
        jobs = []
        if isinstance(payload, dict) and payload.get("@type") == "JobPosting":
            jobs = [payload]
        elif isinstance(payload, list):
            jobs = [x for x in payload if isinstance(x, dict) and x.get("@type") == "JobPosting"]

        for j in jobs:
            title = (j.get("title") or "").strip()
            posted = _parse_iso_or_none(j.get("datePosted"))
            url = j.get("hiringOrganization", {}).get("sameAs") or j.get("url") or internal_url
            out.append({"title": title, "location": None, "url": url, "posted_dt": posted})

    # If no JSON-LD, fallback to obvious job-card anchors
    if not out:
        for a in soup.select("a[href]"):
            txt = (a.get_text() or "").strip()
            if not txt:
                continue
            if any(w in txt.lower() for w in ["engineer", "developer", "data", "ml", "ai", "software"]):
                out.append({"title": txt, "location": None, "url": urljoin(internal_url, a["href"]), "posted_dt": None})
    return out

# ---------- dispatcher ----------

def _identify_provider(careers_url: str) -> str:
    host = urlparse(careers_url).netloc.lower()
    for pattern, provider in ATS_PATTERNS.items():
        if pattern in host:
            return provider
    return "Internal"

def _fetch_jobs(provider: str, careers_url: str) -> List[Dict[str, Any]]:
    try:
        if provider == "Greenhouse":
            return fetch_greenhouse_jobs(careers_url)
        if provider == "Lever":
            return fetch_lever_jobs(careers_url)
        if provider == "Ashby":
            return fetch_ashby_jobs(careers_url)
        if provider == "Workable":
            return fetch_workable_jobs(careers_url)
        if provider == "BambooHR":
            return fetch_bamboohr_jobs(careers_url)
        return fetch_internal_jobs(careers_url)
    except Exception:
        return []

# ---------- public entrypoint ----------

def detect_hiring_signal(domain_url: Optional[str]) -> Dict[str, Any]:
    """
    1) Find real careers link from homepage
    2) Identify provider
    3) Fetch structured jobs from provider/HTML
    4) Filter to TECH roles
    5) Tier by recency
    """
    if not domain_url:
        return {"hiring_tier": "C", "careers_url": None, "ats_provider": None, "tech_roles": 0, "details": "no_domain"}

    info = find_careers_link(domain_url)
    if not info:
        return {"hiring_tier": "C", "careers_url": None, "ats_provider": None, "tech_roles": 0, "details": "no_careers_link_found"}

    careers_url = info["url"]
    provider = _identify_provider(careers_url)

    jobs = _fetch_jobs(provider, careers_url)

    # Filter to tech roles
    tech_jobs = [j for j in jobs if _is_tech_title(j.get("title", ""))]
    tech_roles = len(tech_jobs)

    # Find most recent posting date (if any)
    recent_cutoff = _now_utc() - timedelta(days=RECENT_DAYS)
    recent_jobs = [j for j in tech_jobs if j.get("posted_dt") and j["posted_dt"] >= recent_cutoff]
    latest_dt = max((j.get("posted_dt") for j in tech_jobs if j.get("posted_dt")), default=None)

    if recent_jobs:
        tier = "A"
        details = f"recent_tech_roles={len(recent_jobs)} (≤{RECENT_DAYS}d)"
    elif tech_roles > 0:
        tier = "B"
        details = "tech_roles_present_but_not_recent"
    else:
        tier = "C"
        details = "no_tech_roles_found"

    return {
        "hiring_tier": tier,
        "careers_url": careers_url,
        "ats_provider": provider,
        "tech_roles": tech_roles,
        "latest_posted_days": (_days_ago(latest_dt) if latest_dt else None),
        "details": details,
    }