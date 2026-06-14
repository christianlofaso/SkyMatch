import asyncio
import hashlib
import json
import os
import re

import numpy as np
from fastapi import APIRouter, Depends, HTTPException

from lib.auth import User, optional_user, require_user
from lib.turnstile import verify_turnstile
from fastapi.responses import StreamingResponse

from cache import (
    ONE_DAY, add_rotation_metro, annotate_cache_key, get_annotate_cache,
    get_listing_by_url, get_listings, get_rotation_metros, set_annotate_cache,
    upsert_listing,
)
from config.models import MODEL_MID
from config.niches import NATIONAL_NICHE_KEY, REACH_NICHE_KEY
from lib import embeddings
from lib.anthropic_client import client as ai, sonnet_slot
from lib.cost import cost_session, record_cache_hit, record_usage
from lib.jsonparse import parse_json_with_context, strip_fences
from lib.listing_parser import company_from_url
from lib.logos import logo_url_for
from lib.precompute import parse_and_embed_rows
from lib.timing import timed
from schemas import (
    AnnotateEnvelope, AnnotateError, AnnotateRequest,
    Internship, InternshipBuckets, ProfileAnalysis,
)
# The local live-fetch fallback (uncovered metros) reuses the profile-independent
# scrape/validate helpers from lib.ingest_core (the same ones the ingestion worker uses).
from lib.ingest_core import _scrape_local_listings, _parse_metro, validate_job_url, _is_us_location

router = APIRouter()
# The Anthropic client (shared, max_retries raised) AND the global Sonnet concurrency
# governor both live in lib/anthropic_client.py now. The per-role fan-out below grazes the org's
# Sonnet input-tokens / requests-per-minute limits; sonnet_slot() staggers the burst across 2-3
# minutes and the SDK's Retry-After backoff recovers any residual 429 instead of dropping a role.


def _profile_brief(profile: ProfileAnalysis) -> str:
    """Compact profile text for per-call prompts. The full model_dump(indent=2) re-sent on
    EVERY fan-out call multiplies input tokens ~Nx and blows the org's input-tokens-per-minute
    limit; this keeps only the fields the selector/annotator actually use, as terse text."""
    p = profile
    parts = [
        f"Name: {p.full_name}",
        f"Headline: {p.headline}" if p.headline else "",
        f"School: {p.school or '?'} | Major: {p.major or '?'} | Grad year: {p.graduation_year or '?'}",
        f"Field of interest: {p.field_of_interest or '?'}",
        f"Skills: {', '.join(p.technical_skills) if p.technical_skills else '?'}",
        f"Orgs: {', '.join(p.fraternity_or_orgs) if p.fraternity_or_orgs else '?'}",
        f"Past companies: {', '.join(p.past_companies) if p.past_companies else '?'}",
        f"Current company: {p.current_company}" if p.current_company else "",
    ]
    return "\n".join(p for p in parts if p)


# ── Serving model ────────────────────────────────────────────────────────────
# Serving a user's feed is now ZERO-LLM on the /run path:
#   RANK (embed + cosine) → SELECT+BUILD (deterministic: hard filters already applied in
#   rank, then company-diversity trim) → cards assembled straight from the precomputed
#   display fields. No SELECT/ANNOTATE Sonnet calls block the feed.
# The personalized "why you fit" text (fit_explanation / reach_gap) is deferred: the
# results page fans the served URLs out to POST /internships/annotate, which streams the
# per-role fit text back (the slim fit-only Sonnet call below) — same lazy pattern the
# score badge uses via /analyze/batch.


def _annotate_fit_system(bucket: str, city: str | None = None) -> str:
    """Slim system prompt for the deferred fit-only annotate: the listing's display fields
    (title/company/location/description) are already known, so the call only writes the
    per-user fit text (+reach_gap). The out-of-field/closed skip rule is kept as a per-user
    backstop on top of the deterministic pre-filter applied at serve time."""
    if bucket == "reach":
        gap_rule = (
            '- reach_gap: REQUIRED and non-null — ONE short sentence (~25 words) on the '
            'credential gap and how to close it.\n'
            '  BAD: "You are not qualified."  '
            'GOOD: "This role prefers 1-2 prior SWE internships; close the gap by shipping a '
            'Python/C++ project and reapplying sophomore year."'
        )
        skip_rule = (
            'If this listing is clearly OUTSIDE the student\'s software / engineering / data / ML '
            'field (e.g. finance, audit, sales, recruiting, marketing) OR is a full-time or '
            'closed/filled position, respond with exactly: null'
        )
        bucket_intro = ('This is an aspirational REACH role — be concrete about what makes it a '
                        'stretch-but-plausible target.')
    else:
        gap_rule = '- reach_gap: always null.'
        # No skip-to-null rule for the national buckets: non-internships are already removed at
        # ingestion (is_internship + the serve pre-filter), so a served role is always valid —
        # re-litigating "is this full-time?" here only false-declines real interns (blanking
        # their "why you fit"). reach keeps its off-field/closed rule (those are aspirational).
        skip_rule = ''
        bucket_intro = ''
    near = (f' This role is already verified to be in or near {city}.'
            if (bucket == "local" and city) else '')

    return f"""You are a career advisor writing ONE personalized internship recommendation for a student from ONE real, already-verified, pre-parsed open listing.

{bucket_intro}
{skip_rule}

You are given the student profile and the listing's ALREADY-EXTRACTED fields (title, company, location, description, skills). Do NOT re-output those fields. Respond with ONLY a single JSON object (no array, no markdown, no commentary) with exactly these fields:
- fit_explanation: AT MOST 2 short sentences (~30 words total). MUST name a specific profile detail (a skill, major, school, org, or past company) and connect it to this role. Concrete and scannable — not a paragraph.{near}
- why: an array of 2-3 SHORT bullet strings (each ~12 words, no trailing period) expanding on the fit — each names a concrete profile detail tied to this role. These are the drawer's "why you fit" bullets; do not just restate fit_explanation verbatim.
- have: an array of the skills (short labels) the student ALREADY demonstrably brings that this role wants — drawn from the listing's skills where they overlap the profile's skills/experience. [] if none clearly overlap.
- need: an array of the skills (short labels) this posting wants that the profile does NOT yet show — the honest gaps to shore up. Keep it grounded in the listing's skills; [] if the profile covers everything.
{gap_rule}"""


def _fit_fields(listing: dict) -> dict:
    """The listing fields the slim fit-only annotate prompt reads. Prefers the trusted
    ingestion-time parse; for an unparsed row (warming index OR the local live-fetch fallback,
    which upserts without parsing) it falls back to the raw scraped columns so the deferred
    annotate still has something to reason over."""
    parsed = listing.get("parsed")
    if parsed:
        return {k: parsed.get(k) for k in
                ("title", "company", "location", "company_description", "skills", "seniority")}
    title, company = _parse_title_company(listing.get("search_title"))
    return {
        "title": title,
        "company": company or company_from_url(listing.get("url") or "") or listing.get("company"),
        "location": listing.get("verified_location"),
        "company_description": " ".join((listing.get("snippet") or "").split())[:200] or None,
        "skills": None,
        "seniority": None,
    }


# Job-board search titles for unparsed (live-fetched) rows arrive in two shapes:
#   "{Role} @ {Company} - Jobs"        (workatastartup / Built In)
#   "{Role} - {Company} - {Board}"     (Lever/Greenhouse/Ashby DDG page titles)
# Until the worker (or the inline live-fetch parse) parses the row, recover a clean title +
# company deterministically so the card isn't a raw string with an "Unknown" company — and so
# the company-diversity trim in _select_and_build doesn't collapse the whole bucket. The "@"
# split is always safe; the " - Company" split is ONLY taken after stripping a known ATS board
# suffix (so a title like "… Intern - Fall" doesn't mistake "Fall" for a company).
_TITLE_BOARD_SUFFIXES = (" - Jobs", " | Jobs", " - jobs")
_ATS_BOARD_SUFFIXES = (" - Lever", " - Greenhouse", " - Ashby")


def _parse_title_company(search_title: str | None) -> tuple[str, str | None]:
    """(clean_title, company|None) parsed from a raw board search_title. Best-effort, zero-LLM;
    a Haiku parse (worker or inline live-fetch) supersedes it once the row is parsed."""
    s = (search_title or "").strip()
    ats = False
    for suf in _ATS_BOARD_SUFFIXES:
        if s.lower().endswith(suf.lower()):
            s = s[: -len(suf)].strip()
            ats = True
            break
    else:
        for suf in _TITLE_BOARD_SUFFIXES:
            if s.lower().endswith(suf.lower()):
                s = s[: -len(suf)].strip()
                break
    company: str | None = None
    if " @ " in s:
        s, company = s.rsplit(" @ ", 1)
        s = s.strip()
        company = company.strip() or None
    elif ats and " - " in s:
        # "{Role} - {Company}" left after stripping the board suffix.
        s, company = s.rsplit(" - ", 1)
        s = s.strip()
        company = company.strip() or None
    return (s or "Internship"), company


def _annotate_fit_sync(
    profile: ProfileAnalysis, fields: dict, bucket: str, city: str | None = None,
) -> dict | None:
    """Slim fit-only Claude call for the DEFERRED annotate pass: given the listing's
    already-known display fields, write the per-user fit text — fit_explanation (collapsed-card
    one-liner) + why[] bullets + have[]/need[] skill chips (+reach_gap for reach). Returns
    {"fit_explanation", "why", "have", "need", "reach_gap"} or None when the model declines /
    errors (the card simply keeps its empty fit text). Called via asyncio.to_thread under
    sonnet_slot()."""
    try:
        msg = ai.messages.create(
            model=MODEL_MID,
            max_tokens=400,  # fit_explanation + why[]/have[]/need[] (+reach_gap); headroom
            system=_annotate_fit_system(bucket, city),
            messages=[{
                "role": "user",
                "content": (
                    f"Student profile:\n{_profile_brief(profile)}\n\n"
                    f"Listing fields:\n{json.dumps(fields)}"
                ),
            }],
        )
        record_usage(f"annotate-fit:{bucket}", MODEL_MID, msg.usage)
        raw = strip_fences(msg.content[0].text)
        if not raw.strip() or raw.strip().lower() == "null":
            return None
        out = parse_json_with_context(raw, f"annotate-fit:{bucket}")
        if isinstance(out, list):
            out = out[0] if out else None
        if not isinstance(out, dict):
            return None
        fit = out.get("fit_explanation")
        if not isinstance(fit, str) or not fit.strip():
            return None

        def _str_list(v) -> list[str]:
            if not isinstance(v, list):
                return []
            return [s.strip() for s in v if isinstance(s, str) and s.strip()]

        return {
            "fit_explanation": fit.strip(),
            "why": _str_list(out.get("why")),
            "have": _str_list(out.get("have")),
            "need": _str_list(out.get("need")),
            "reach_gap": (out.get("reach_gap") if bucket == "reach" else None),
        }
    except Exception as e:
        print(f"[annotate-fit:{bucket}] ERROR: {e}")
        return None


_SEASON_FIX = {"autumn": "Fall"}
_POSTED_PREFIX_RE = re.compile(r"^\s*(?:re)?posted[\s:\-]*", re.I)
# Model/extract stand-ins for "no date" — Firecrawl sometimes returns "N/A" literally.
_POSTED_JUNK = {"n/a", "na", "none", "null", "unknown", "-", "—", "not specified", "not available", "tbd"}


def _clean_posted(v: str | None) -> str | None:
    """Strip a leading 'Posted:'/'Reposted' prefix from a captured posted date so the drawer's
    'Posted' box reads just '4 weeks ago' (not 'Posted: 4 weeks ago'); drop junk placeholders
    ('N/A', etc.). None when empty/junk."""
    if not isinstance(v, str):
        return None
    cleaned = _POSTED_PREFIX_RE.sub("", v).strip()
    return cleaned if cleaned and cleaned.lower() not in _POSTED_JUNK else None


def _term_from_text(*texts: str | None) -> str | None:
    """Deterministically recover a role term from RAW listing text (search_title/snippet/title/
    URL). The Haiku parse strips the season from the cleaned `title` (e.g. "...RF (Fall 2026)" →
    "...RF"), and the stored search_title is often truncated ("...Intern ..."), but the season
    usually survives in the URL SLUG ("...software-intern-fall-2026"). So serving recovers it
    here with zero LLM, covering every already-parsed row without a re-parse. The separator class
    allows '-'/'_' so slug forms like "fall-2026" match. Prefers a season+year, then a bare
    season, then an employment type. None when the text states no term."""
    hay = " ".join(t for t in texts if t)
    m = re.search(r"\b(spring|summer|fall|autumn|winter)\b[\s.,'’_-]*((?:20)?\d{2})\b", hay, re.I)
    if m:
        season = _SEASON_FIX.get(m.group(1).lower(), m.group(1).capitalize())
        yr = m.group(2)
        return f"{season} {yr if len(yr) == 4 else '20' + yr}"
    m = re.search(r"\b(spring|summer|fall|autumn|winter)\b", hay, re.I)
    if m:
        return _SEASON_FIX.get(m.group(1).lower(), m.group(1).capitalize())
    if re.search(r"\bco-?op\b", hay, re.I):
        return "Co-op"
    if re.search(r"\bpart[-\s]?time\b", hay, re.I):
        return "Part-time"
    if re.search(r"\bfull[-\s]?time\b", hay, re.I):
        return "Full-time"
    if re.search(r"\bseasonal\b", hay, re.I):
        return "Seasonal"
    return None


def _build_internship(listing: dict, bucket: str) -> Internship:
    """Assemble a feed card from a listing row with ZERO LLM. Display fields come from the
    ingestion-time parse when present, else the raw scraped columns (warming index / local
    live-fetch). fit_explanation is left empty — the results page fills it lazily via
    /internships/annotate. application_url and bucket are forced from our trusted row."""
    parsed = listing.get("parsed") or {}
    # Unparsed rows (warming index / live-fetch) carry only the raw board search_title —
    # recover a clean title + company from it; parsed rows use the trusted Haiku fields.
    # Company resolution order: Haiku parse → title "@/-" company → URL slug (lever/greenhouse/
    # ashby/amazon, via company_from_url) → stored column → "Unknown". The URL-slug step is the
    # belt-and-suspenders that keeps an ATS-board URL from ever showing "Unknown" even with no
    # Haiku key. (workatastartup has no slug → relies on the title "@" company instead.)
    raw_title, raw_company = _parse_title_company(listing.get("search_title"))
    title = parsed.get("title") or raw_title
    company = (parsed.get("company") or raw_company
               or company_from_url(listing.get("url") or "")
               or listing.get("company") or "Unknown")
    location = parsed.get("location") or listing.get("verified_location") or "Remote / Various"
    desc = parsed.get("company_description")
    if not desc:
        desc = " ".join((listing.get("snippet") or "").split())[:160]
    return Internship(
        title=title,
        company=company,
        location=location,
        company_description=desc or "",
        fit_explanation="",  # deferred — see /internships/annotate
        application_url=listing.get("url"),
        bucket=bucket,
        reach_gap=None,
        # Logo resolved + stored at ingestion (lib/logo_resolver: extracted/curated domain or a
        # logo.dev name search → logo.dev image or Google favicon). For an unparsed row (no stored
        # value), the curated/host map is the zero-network fallback; else the frontend letter avatar.
        logo_url=(parsed.get("logo_url") or logo_url_for(company, listing.get("url"))),
        # Drawer fact-grid fields ("" from the parse → None so the frontend treats them as absent).
        company_size=(parsed.get("company_size") or None),
        # Term: prefer the parse's value (new rows); else recover deterministically from the raw
        # search_title/snippet/URL (covers every pre-existing parsed row — the title was stripped
        # and the search_title is often truncated, but the season survives in the URL slug).
        term=(parsed.get("term") or _term_from_text(
            parsed.get("title"), listing.get("search_title"), listing.get("snippet"), listing.get("url"),
        )),
        # Posted date captured at ingestion (snippet parse or SPA render); strip a leading
        # "Posted:" so the box (already labeled "Posted") shows just "4 weeks ago". The drawer
        # falls back to the per-request fetch's date when this is absent.
        posted_at=_clean_posted(parsed.get("posted_at")),
    )


def _select_and_build(
    rows: list[dict], bucket: str, *, per_bucket: int = 5, per_company: int = 2,
) -> list[Internship]:
    """Deterministic replacement for the old Sonnet SELECT + _cap: walk the cosine-ranked
    rows in order, build each card, and keep the top `per_bucket` while enforcing
    company-diversity (<= per_company per company — mirrors the dropped SELECT 'prefer
    VARIETY' instruction) and dropping exact-duplicate (company, title) roles. No LLM."""
    company_counts: dict[str, int] = {}
    seen_roles: set[tuple[str, str]] = set()
    out: list[Internship] = []
    for row in rows:
        # Per-row isolation: a single malformed/unexpectedly-typed row (e.g. a non-str
        # company from a bad parse) must not break the whole bucket — skip it and continue.
        try:
            item = _build_internship(row, bucket)
        except Exception as e:
            print(f"[serve] skipped malformed {bucket} row ({row.get('url', '?')}): {e!r}")
            continue
        key = item.company.lower()
        # Skip an exact repeat of the same role at the same company (same title posted under
        # multiple URLs) — the per-company cap alone would otherwise show it twice.
        role = (key, item.title.strip().lower())
        if role in seen_roles:
            continue
        # Diversity cap, but NOT for unresolved companies: many distinct "Unknown" listings
        # are different companies, so capping them at per_company would wrongly collapse the
        # bucket (the live-fetch-unparsed case). Resolved companies still cap at per_company.
        if key not in ("", "unknown") and company_counts.get(key, 0) >= per_company:
            continue
        company_counts[key] = company_counts.get(key, 0) + 1
        seen_roles.add(role)
        out.append(item)
        if len(out) >= per_bucket:
            break
    return out


# ── Index-serving constants ────────────────────────────────────────────────
# Don't serve listings the worker hasn't re-validated within this window. Tightened from
# 72h → 48h (env SERVE_MAX_AGE_HOURS) so served links are fresher; the worker runs ~every
# 8h, so 48h is a ~6x margin. If the worker LAGS past this, a national bucket could go
# empty — _serve_bucket_rows falls back to _SERVE_MAX_AGE_FALLBACK (env
# SERVE_MAX_AGE_FALLBACK_HOURS, default 96h) for that bucket rather than show nothing.
# (Reliability: keep SERVE_MAX_AGE_HOURS comfortably above the real worker cadence.)
_SERVE_MAX_AGE = int(os.getenv("SERVE_MAX_AGE_HOURS", "48")) * 3600
_SERVE_MAX_AGE_FALLBACK = int(os.getenv("SERVE_MAX_AGE_FALLBACK_HOURS", "96")) * 3600


def _serve_national_rows(niche_key: str, bucket: str) -> list[dict]:
    """Read a national/reach bucket at the tight freshness window; if it comes back empty
    (worker lagged past _SERVE_MAX_AGE), retry once at the looser fallback window so the
    bucket degrades to slightly-staler rather than empty. (Local has its own live-fetch
    fallback, so it doesn't use this.)"""
    rows = get_listings(niche_key, bucket, max_age=_SERVE_MAX_AGE)
    if not rows and _SERVE_MAX_AGE_FALLBACK > _SERVE_MAX_AGE:
        rows = get_listings(niche_key, bucket, max_age=_SERVE_MAX_AGE_FALLBACK)
        if rows:
            print(f"[serve] bucket {bucket} empty at {_SERVE_MAX_AGE//3600}h window -> "
                  f"fell back to {_SERVE_MAX_AGE_FALLBACK//3600}h ({len(rows)} rows)")
    return rows
# Bound the on-request local scrape for an uncovered metro so a slow/rate-limited DDG can't
# hang /run; on timeout we serve an empty local bucket (the worker backfills next run).
_LIVE_LOCAL_BUDGET = 35  # seconds
# Embedding pre-rank: each bucket pool is cosine-ranked against the profile embedding and
# narrowed to this many. _select_and_build then trims to the final per-bucket cap (5) with
# company-diversity. Kept comfortably above 5 so the diversity trim has candidates to fill 5.
_PRESELECT = 18
# Off-field pre-filter: precomputed role_category values that are out-of-field for this
# product's CS/eng audience (NATIONAL_FIELDS). Applied to BOTH reach and local — reach
# (elite companies have plenty of these roles) and local (the live-fetch scrapes ATS boards
# broadly for "intern <city>", so a CS student can get a Marketing/Sales intern). National
# startup/big_tech pools are pre-curated by field, so they're unaffected. Mirrors the prose
# exclusion in _annotate_fit_system (a backstop when Haiku's role_category is wrong). Keep in
# sync with listing_parser.ROLE_CATEGORIES.
_OFF_FIELD_CATEGORIES = {"finance", "sales", "marketing", "recruiting", "audit"}
_OFF_FIELD_BUCKETS = {"reach", "local"}
# US-location gate: big_tech is a national pool served to US students, but its Workday/ATS
# feeds return plenty of overseas intern roles (Intel Costa-Rica/Malaysia, ADI Philippines/
# Thailand) — genuine non-fits that score below 50. Drop them at serve time on the resolved
# location (see lib.ingest_core._is_us_location — permissive, drops only on an explicit non-US
# token). Serve-time placement catches rows already in the index + ATS-sourced rows, not just
# the ones the ingestion gate stops going forward. startup is left out (curated by hand) and
# reach is intentionally global; only big_tech needs this.
_US_LOCATION_BUCKETS = {"big_tech"}
# Deterministic title backstop for the off-field gate — catches UNPARSED rows (a metro's
# index still warming, before the worker's parse pass sets role_category) + parse misses,
# exactly like _PHD_TITLE_RE does for the PhD gate. Without it, an unparsed Marketing/Sales
# row in a warming local pool bypasses the role_category filter entirely and leaks through.
# Word-boundaried so it won't false-positive on CS titles (e.g. "Salesforce Engineer" —
# no boundary after "sales"; "Market Data" — not "marketing"). Keep the matched words in
# sync with the intent of _OFF_FIELD_CATEGORIES.
_OFF_FIELD_TITLE_RE = re.compile(
    r"\b(?:marketing|sales|recruit\w*|audit\w*|financ\w*)\b", re.IGNORECASE,
)
# PhD-eligibility gate: this product serves UNDERGRAD interns, so a role that mandates PhD
# enrollment is never applicable. Dropped in every bucket on the parsed `requires_phd` flag
# OR a "PhD"/"Ph.D" title match (the deterministic backstop that catches unparsed rows + any
# parse miss, e.g. "Software Engineering PhD Intern", "PhD Data Scientist").
_PHD_TITLE_RE = re.compile(r"\bph\.?\s?d\b", re.IGNORECASE)
# Per-process cache of profile-query embeddings (key includes EMBED_MODEL — a model swap
# must not reuse a wrong-dim vector). Bounded by a coarse clear when it grows.
_profile_vec_cache: dict[str, np.ndarray] = {}


def _to_listings(rows: list[dict]) -> list[dict]:
    """Map listing_store rows to the shape the serving pipeline consumes — the ingestion-time
    precompute (parsed fields + embedding) used by the pre-filter, cosine rank, and card
    builder, PLUS the raw scraped columns used as a fallback when a row is unparsed. Keeps
    raw_json / timestamps / status out of memory."""
    out: list[dict] = []
    for r in rows:
        parsed = None
        if r.get("parsed_json"):
            try:
                parsed = json.loads(r["parsed_json"])
            except (TypeError, ValueError):
                parsed = None
        emb = None
        if r.get("embedding") is not None:
            try:
                emb = embeddings.from_bytes(r["embedding"])
            except Exception:
                emb = None
        out.append({
            "url": r["url"],
            "search_title": r.get("search_title") or "",
            "snippet": r.get("snippet") or "",
            "verified_location": r.get("verified_location"),
            "company": r.get("company"),
            "parsed": parsed,
            "embedding": emb,
            "embedding_model": r.get("embedding_model"),
            "embedding_dim": r.get("embedding_dim"),
        })
    return out


async def _embed_profile(profile: ProfileAnalysis) -> np.ndarray | None:
    """Embed the profile brief once per request (input_type='query'), cached per-process by
    (EMBED_MODEL, brief). None when Voyage is unavailable or the call fails — callers then
    skip cosine ranking and select from the unranked pool in DB order."""
    if not embeddings.is_available():
        return None
    brief = _profile_brief(profile)
    key = f"{embeddings.EMBED_MODEL}:{hashlib.sha256(brief.encode()).hexdigest()}"
    cached = _profile_vec_cache.get(key)
    if cached is not None:
        return cached
    try:
        vec = await asyncio.to_thread(embeddings.embed_query, brief)
    except Exception as e:
        print(f"[serve] profile embed failed: {e} — ranking disabled this request")
        return None
    if vec is not None:
        if len(_profile_vec_cache) > 256:
            _profile_vec_cache.clear()
        _profile_vec_cache[key] = vec
    return vec


def _prefilter_and_rank(
    bucket: str, listings: list[dict], q_vec: np.ndarray | None,
) -> list[dict]:
    """Narrow a bucket pool for serving: drop precomputed-ineligible rows, then cosine-rank
    embeddable rows against the profile and keep the top _PRESELECT (+ any rows that can't be
    ranked, so a warming/partly-embedded index never loses candidates)."""
    # 1. Deterministic pre-filter.
    kept: list[dict] = []
    for l in listings:
        p = l.get("parsed")
        # PhD-eligibility gate (ALL buckets, parsed or not): drop on the parsed requires_phd
        # flag or a "PhD" title match — undergrad interns can't apply to PhD-mandatory roles.
        title = (p.get("title") if p else None) or l.get("search_title") or ""
        if (p and p.get("requires_phd") is True) or _PHD_TITLE_RE.search(title):
            continue
        if p and p.get("is_internship") is False:
            continue
        # Off-field gate (local/reach): parsed role_category is the precise primary; the
        # title regex is the backstop for unparsed rows + parse misses (mirrors the PhD gate
        # above), so a Marketing/Sales/etc. role never leaks while a metro's index is warming.
        if bucket in _OFF_FIELD_BUCKETS and (
            (p and p.get("role_category") in _OFF_FIELD_CATEGORIES)
            or _OFF_FIELD_TITLE_RE.search(title)
        ):
            continue
        # US-location gate (big_tech): drop overseas roles. Location source, in order of
        # fidelity: parsed.location → verified_location → snippet (Workday's locationsText
        # lands in snippet for unparsed rows). Permissive — keeps ambiguous/missing locations.
        if bucket in _US_LOCATION_BUCKETS:
            loc = (p.get("location") if p else None) or l.get("verified_location") or l.get("snippet")
            if not _is_us_location(loc):
                continue
        kept.append(l)

    # 2. Cosine rank when we have a query vector; otherwise leave order unchanged.
    if q_vec is None:
        return kept
    dim = len(q_vec)
    rankable, unranked = [], []
    for l in kept:
        emb = l.get("embedding")
        if (emb is not None and l.get("embedding_model") == embeddings.EMBED_MODEL
                and l.get("embedding_dim") == dim):
            rankable.append(l)
        else:
            unranked.append(l)
    if rankable:
        mat = np.stack([l["embedding"] for l in rankable])  # normalized rows
        scores = mat @ q_vec                                 # cosine == dot (both unit)
        order = np.argsort(-scores)[:_PRESELECT]
        rankable = [rankable[i] for i in order]
    # Ranked top-K first, then the unrankable remainder (_select_and_build trims the set).
    return rankable + unranked


def _safe_rank(bucket: str, listings: list[dict], q_vec: np.ndarray | None) -> list[dict]:
    """_prefilter_and_rank guarded so a ranking/numpy error never 500s the request."""
    try:
        return _prefilter_and_rank(bucket, listings, q_vec)
    except Exception as e:
        print(f"[serve] rank/prefilter failed for {bucket}: {e} — using unranked pool")
        return listings


async def _live_local_fetch(profile: ProfileAnalysis, metro: str) -> list[dict]:
    """Uncovered metro: scrape + validate the local bucket once, run the SAME parse precompute
    the worker does (Haiku company/role_category + Voyage embedding) INLINE so this request
    serves clean, field-filtered, ranked rows, cache it all, and promote the metro into the
    rotation so the next user + next worker run get it from the index.

    Why parse inline: the live-fetch is request-time mini-ingestion, and a row that's only
    scraped (no parse) has no resolved company (→ "Unknown"), no role_category (→ off-field
    Marketing roles slip through the local filter) and no embedding (→ no relevance ranking).
    Parsing it here closes all three at the source. Bounded by _LIVE_LOCAL_BUDGET; on
    timeout/error we still return whatever upserted (parsed or not — serving's fallback covers
    unparsed rows), never []."""
    async def _do() -> None:
        scraped = await _scrape_local_listings(profile)   # enriches + metro-filters internally
        sem = asyncio.Semaphore(10)

        async def _check(listing: dict) -> tuple[dict, bool, str]:
            async with sem:
                ok, reason = await validate_job_url(listing.get("url"), listing.get("search_title", ""))
            return listing, ok, reason

        results = await asyncio.gather(*[_check(l) for l in scraped])
        kept: list[dict] = []
        for listing, ok, reason in results:
            if ok:
                await asyncio.to_thread(upsert_listing, listing, bucket="local", niche_key=metro,
                                        status="valid", validation_reason=reason)
                kept.append({**listing, "niche_key": metro, "bucket": "local"})
        if kept:
            # firecrawl_company=False: local hits only ATS boards (greenhouse/lever/ashby),
            # where the URL slug / Haiku already resolve company — skip the render to stay
            # inside the budget.
            stats = await parse_and_embed_rows(kept, firecrawl_company=False)
            print(f"[serve] live-local parse: {stats}")

    try:
        async with timed(f"internships/live-local:{metro}"):
            await asyncio.wait_for(_do(), timeout=_LIVE_LOCAL_BUDGET)
    except (asyncio.TimeoutError, Exception) as e:
        print(f"[serve] live-local fetch for metro={metro!r} failed/timeout: {e}")
    await asyncio.to_thread(add_rotation_metro, metro, "serving")   # promote regardless — worker backfills next run
    # Return the freshly-persisted rows (parsed+embedded where the inline parse succeeded) so
    # rank+build use the precompute THIS request; unparsed survivors fall back gracefully.
    rows = await asyncio.to_thread(get_listings, metro, "local", max_age=_SERVE_MAX_AGE)
    print(f"[serve] metro={metro!r} NOT in rotation — live-fetched, serving {len(rows)} local rows, promoted")
    return rows


async def search_internships(profile: ProfileAnalysis) -> InternshipBuckets:
    """Serve the internship feed from the pre-ingested index (worker/ingest.py) with ZERO LLM.

    The three national buckets (startup, big_tech, reach) come from the metro-independent
    pool and are served to everyone. local comes from the per-metro pool if the metro is in
    rotation; otherwise it's live-fetched once (bounded), cached, and the metro is promoted.

    URLs were found + validated at ingest and (in steady state) parsed + embedded there too,
    so per-request work is now purely:
      1. RANK (no LLM) — embed the profile once, drop precomputed-ineligible rows, and
         cosine-rank each bucket to _PRESELECT candidates. Skipped per-bucket on any error;
         skipped entirely when Voyage is unavailable (pools pass through unranked, DB order).
      2. SELECT + BUILD (no LLM) — _select_and_build walks the ranked rows, enforces
         company-diversity, and assembles up to 5 cards per bucket straight from the
         precomputed display fields (raw-column fallback for unparsed rows).
    The per-user "why you fit" text is filled lazily afterward via POST /internships/annotate.
    """
    metro = _parse_metro(profile.location)

    # ── 1. Read the index (national pools are metro-independent; reach is its own pool)
    # _serve_national_rows does blocking get_listings reads — run each off the event loop.
    nat_startup = await asyncio.to_thread(_serve_national_rows, NATIONAL_NICHE_KEY, "startup")
    nat_bigtech = await asyncio.to_thread(_serve_national_rows, NATIONAL_NICHE_KEY, "big_tech")
    reach_rows  = await asyncio.to_thread(_serve_national_rows, REACH_NICHE_KEY,    "reach")

    local_rows: list[dict] = []
    if metro in await asyncio.to_thread(get_rotation_metros):
        local_rows = await asyncio.to_thread(get_listings, metro, "local", max_age=_SERVE_MAX_AGE)
        print(f"[serve] metro={metro!r} in rotation — local from index ({len(local_rows)} rows)")
    # Fall back to a live fetch when the metro is NOT in rotation OR is seeded-but-not-yet-
    # ingested (empty/stale index) — so seeding a metro can never serve an empty local bucket.
    # Once the worker has populated the 30 seeded metros, this never fires for them.
    if not local_rows:
        local_rows = await _live_local_fetch(profile, metro)

    print(f"[serve] index sizes: startup={len(nat_startup)} big_tech={len(nat_bigtech)} "
          f"reach={len(reach_rows)} local={len(local_rows)}")

    # bucket -> candidate rows in minimal serving shape
    pools: dict[str, list[dict]] = {
        "startup":  _to_listings(nat_startup),
        "big_tech": _to_listings(nat_bigtech),
        "reach":    _to_listings(reach_rows),
        "local":    _to_listings(local_rows),
    }

    # ── 2. RANK (no LLM): embed the profile once, pre-filter ineligible rows, and
    #        cosine-narrow each bucket to _PRESELECT. Degrades to the unranked pool (DB
    #        order) when Voyage is off or a bucket can't be ranked.
    async with timed("internships/rank (embed + cosine)"):
        q_vec = await _embed_profile(profile)
        if q_vec is not None:
            pools = {b: _safe_rank(b, rows, q_vec) for b, rows in pools.items()}
            print(f"[serve] ranked pools (dim={len(q_vec)}): "
                  + ", ".join(f"{b}={len(rows)}" for b, rows in pools.items()))
        else:
            print("[serve] profile embedding unavailable — serving unranked pools (DB order)")

    # ── 3. SELECT + BUILD (no LLM): company-diversity trim → cards from precomputed fields.
    buckets = {b: _select_and_build(rows, b) for b, rows in pools.items()}
    print("[serve] feed sizes: " + ", ".join(f"{b}={len(items)}" for b, items in buckets.items()))

    return InternshipBuckets(
        startup=buckets["startup"],
        big_tech=buckets["big_tech"],
        reach=buckets["reach"],
        local=buckets["local"],
    )


@router.post("/internships/search", response_model=InternshipBuckets)
async def internships_search_route(profile: ProfileAnalysis):
    try:
        return await search_internships(profile)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ── Deferred per-role annotation ─────────────────────────────────────────────
# The /run feed is zero-LLM; the results page fans the served URLs out here to fill in the
# personalized "why you fit" text one role at a time (streamed ndjson, mirrors /analyze/batch).

async def _annotate_one(
    i: int, profile: ProfileAnalysis, profile_json: str, url: str, bucket: str, city: str | None,
) -> AnnotateEnvelope:
    """Return one served listing's per-user fit envelope. Served from annotate_cache when present
    (no sonnet_slot(), no Claude — the near-free path); otherwise runs the slim fit-only Sonnet call
    and caches the result. A missing row → error; a model decline/error → ok with empty fit (card
    just keeps its blank 'why you fit' rather than spinning forever)."""
    try:
        row = await asyncio.to_thread(get_listing_by_url, url)
        if not row:
            return AnnotateEnvelope(
                index=i, status="error",
                error=AnnotateError(message="listing not found", code="NOT_FOUND"),
            )
        # Key on the listing's content_hash (a re-parse → new hash → fresh reasoning), else url.
        key = annotate_cache_key(profile_json, bucket, row.get("content_hash") or url)
        cached = await asyncio.to_thread(get_annotate_cache, key)
        if cached is not None:
            record_cache_hit("annotate", MODEL_MID)
            # .get(..., []) defaults: entries cached before the why/have/need enrichment lack
            # those keys, so an old hit degrades to empty lists rather than KeyError-ing.
            return AnnotateEnvelope(
                index=i, status="ok",
                fit_explanation=cached.get("fit_explanation") or "",
                why=cached.get("why") or [],
                have=cached.get("have") or [],
                need=cached.get("need") or [],
                reach_gap=cached.get("reach_gap"),
            )
        listing = _to_listings([row])[0]
        fields = _fit_fields(listing)
        # sonnet_slot(): global Sonnet concurrency cap (Redis-distributed — lib/anthropic_client.py).
        async with sonnet_slot():
            out = await asyncio.to_thread(_annotate_fit_sync, profile, fields, bucket, city)
        if out:  # cache only a real, non-empty result — declines/errors re-attempt next time
            await asyncio.to_thread(set_annotate_cache, key, out)
        out = out or {}
        return AnnotateEnvelope(
            index=i, status="ok",
            fit_explanation=out.get("fit_explanation") or "",
            why=out.get("why") or [],
            have=out.get("have") or [],
            need=out.get("need") or [],
            reach_gap=out.get("reach_gap"),
        )
    except Exception as exc:
        print(f"[annotate-route] job[{i}] url={url!r} failed: {exc}")
        return AnnotateEnvelope(
            index=i, status="error",
            error=AnnotateError(message=str(exc)[:200], code="ANNOTATE_FAILED"),
        )


# Part of the matcher results-reveal gate: REQUIRES sign-in (require_user). NOT separately
# quota'd — one results page expands many cards (the matcher run is charged once on
# /analyze/batch). verify_turnstile no-ops until configured; both no-op when auth is off (dev).
@router.post(
    "/internships/annotate",
    dependencies=[Depends(require_user), Depends(verify_turnstile)],
)
async def internships_annotate_route(req: AnnotateRequest, user: User | None = Depends(optional_user)):
    """Streams ndjson: one AnnotateEnvelope per line, in completion order. Each job is a
    served (url, bucket); we write its per-user fit_explanation (+reach_gap for reach).
    In-flight Sonnet calls are bounded by the global sonnet_slot() governor."""
    uid = user.id if user else None
    city = _parse_metro(req.profile.location)
    profile_json = req.profile.model_dump_json()  # serialize once; reused for every job's cache key
    queue: asyncio.Queue[AnnotateEnvelope] = asyncio.Queue()

    async def _one(i: int, job) -> None:
        bucket_city = city if job.bucket == "local" else None
        env = await _annotate_one(i, req.profile, profile_json, job.url, job.bucket, bucket_city)
        await queue.put(env)

    async def _gen():
        # cost_session must wrap the whole drain loop so each task inherits the contextvar
        # binding and its record_usage()/record_cache_hit() calls aggregate + persist under
        # this search's name (mirrors /analyze/batch).
        with cost_session(f"/internships/annotate ({len(req.jobs)} roles)", user_id=uid):
            tasks = [asyncio.create_task(_one(i, j)) for i, j in enumerate(req.jobs)]
            pending = len(tasks)
            try:
                while pending:
                    env = await queue.get()
                    yield env.model_dump_json(exclude_none=True) + "\n"
                    pending -= 1
            finally:
                for t in tasks:
                    if not t.done():
                        t.cancel()

    return StreamingResponse(
        _gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
