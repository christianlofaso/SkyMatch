import asyncio
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Literal, NamedTuple
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException

from lib.auth import User, optional_user, require_user, quota, enforce_quota
from lib.turnstile import verify_turnstile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from cache import (
    analysis_cache_key,
    get_job_fetch_cache,
    get_listing_by_url,
    get_requirements_cache,
    get_user_analysis_cache,
    job_text_hash,
    set_job_fetch_cache,
    set_requirements_cache,
    set_user_analysis_cache,
)
from config.models import MODEL_FULL, MODEL_MID, MODEL_QUICK
from lib.anthropic_client import client as ai, sonnet_slot
from lib.cost import cost_session, record_cache_hit, record_usage
from lib.firecrawl import (
    API_KEY as _FIRECRAWL_API_KEY,
    PROXY_MODE as _FIRECRAWL_PROXY_MODE,
    scrape as _firecrawl_scrape,
)
from lib.resource_validation import validate_resource_urls
from lib.timing import timed, timed_call, timing_session
from schemas import UnifiedProfile
from site_handlers import dispatch as site_dispatch

router = APIRouter()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_REQUIREMENTS_SYSTEM = (_PROMPTS_DIR / "job_requirements_extraction.txt").read_text()
_EVIDENCE_SYSTEM = (_PROMPTS_DIR / "evidence_matching.txt").read_text()
_QUICK_VERDICT_SYSTEM = (_PROMPTS_DIR / "quick_verdict.txt").read_text()
_ROADMAP_SYSTEM = (_PROMPTS_DIR / "roadmap.txt").read_text()
_PROJECT_SUGGESTION_SYSTEM = (_PROMPTS_DIR / "project_suggestion.txt").read_text()

_ROADMAP_NOTE_NO_GAPS = "You match this role's requirements. No prep roadmap needed."
# Each retry is a full Opus 4096-token roadmap call + URL HEAD validation (~15-20s). Phase 3
# is ~80% of /analyze latency, so capped at 1 retry (was 2): one backfill pass for thin
# resource lists, then ship. Under-filled items still pass through (just fewer resource links).
_ROADMAP_MAX_RETRIES = 1

# Batch endpoint concurrency cap — limits in-flight LLM calls regardless of batch size
_BATCH_LLM_CONCURRENCY = 8
_BATCH_MAX_JOBS = 50

# ── Score weights (soft excluded from fit_score intentionally) ────────────────
CATEGORY_WEIGHTS: dict[str, float] = {
    "technical":  0.35,
    "experience": 0.30,
    "education":  0.20,
    "domain":     0.15,
    # "soft" is present in category_scores but not here → shown in UI, doesn't drag score
}

# ── Fetch config ──────────────────────────────────────────────────────────────
# Firecrawl config (API_KEY / PROXY_MODE / scrape) lives in lib/firecrawl.py and is
# imported above; only the analyze-specific content-length bounds live here.
_MIN_CONTENT_LEN = 200        # chars below this = JS shell, try Firecrawl
_MAX_CONTENT_LEN = 50_000     # chars above this = search/listing page, try Firecrawl

# LinkedIn requires auth even for Firecrawl — fast-fail with paste message
_AUTH_WALL_DOMAINS = frozenset({
    "linkedin.com",
    "www.linkedin.com",
})

# Escape hatch for SPA portals with no scrapable standalone URL and no vendor-specific
# site_handler yet. Prefer adding a site_handlers/<vendor>.py over an entry here.
_SPA_SEARCH_PORTALS: dict[str, str] = {}

# ── Fetch result ──────────────────────────────────────────────────────────────

class _FetchResult(NamedTuple):
    text:      str          # job text to feed into the LLM pipeline
    path:      str          # "direct" | "firecrawl_<proxy>" (auto/basic/enhanced) | "site_handler:<name>"
    extracted: dict | None  # raw Firecrawl extract dict when schema extraction succeeded
    posted_at: str | None = None   # ISO-ish posted date when site_handler returned one
    apply_url: str | None = None   # direct apply URL when site_handler returned one


# ── Request / response schemas ────────────────────────────────────────────────

class IncludeFlags(BaseModel):
    roadmap: bool = True
    project: bool = True


class AnalyzeRequest(BaseModel):
    profile: UnifiedProfile
    job_url: str | None = None
    job_text: str | None = None
    mode: Literal["full", "quick"] = "full"
    include: IncludeFlags = Field(default_factory=IncludeFlags)


class JobSummary(BaseModel):
    title: str
    company: str
    key_requirements: list[str]


class MatchItem(BaseModel):
    requirement: str
    type: Literal["technical", "experience", "education", "domain", "soft"]
    must_have: bool
    match_strength: Literal["strong", "partial"]
    evidence_snippet: str | None
    evidence_source: str | None


class GapItem(BaseModel):
    requirement: str
    type: Literal["technical", "experience", "education", "domain", "soft"]
    must_have: bool
    severity: Literal["critical", "moderate", "minor"]


class Verdict(BaseModel):
    call: Literal["apply_now", "apply_after_prep", "skip"]
    reasoning: str


class RoadmapResource(BaseModel):
    type: Literal["docs", "course", "tutorial", "video", "book", "roadmap"]
    title: str
    url: str
    duration: str
    cost: Literal["free", "paid"]


class RoadmapItem(BaseModel):
    skill: str
    priority: Literal["must_have", "nice_to_have"]
    timeline: str
    why_it_matters: str
    milestone: str
    resources: list[RoadmapResource]


class Roadmap(BaseModel):
    total_timeline: str
    summary: str
    items: list[RoadmapItem]


class ProjectSuggestion(BaseModel):
    title: str
    pitch: str
    why_this_role: str
    mvp_features: list[str]
    tech_stack: list[str]
    estimated_time: str
    stretch_goals: list[str]
    interview_talking_points: list[str]


class AnalysisResponse(BaseModel):
    fit_score: int
    category_scores: dict[str, int]
    matches: list[MatchItem]
    gaps: list[GapItem]
    verdict: Verdict
    job_summary: JobSummary
    roadmap: Roadmap | None = None
    roadmap_note: str | None = None
    project_suggestion: ProjectSuggestion | None = None


# ── /analyze/stream envelopes (full-mode progressive streaming) ───────────────
# Flat shape mirroring BatchEnvelope. `phase` is the discriminator the frontend switches
# on; each phase carries only its own payload fields (the rest are null). Serialized with
# plain model_dump_json() (NOT exclude_none): the nested data models (matches, verdict, …)
# legitimately use null, and exclude_none would DROP those null keys — but the Zod data
# schemas require them present, so it'd fail validation. Off-phase fields arrive as null;
# the Zod wrapper marks them nullable+optional.
# Mirror: frontend/src/types/pathfinder.ts AnalyzeStreamEnvelopeSchema.

class AnalyzeStreamError(BaseModel):
    message: str
    status: int  # advisory: the HTTP status the JSON /analyze would have returned (422/500)


class AnalyzeStreamEnvelope(BaseModel):
    phase: Literal["verdict", "roadmap", "project", "done", "error"]
    # verdict payload (phase == "verdict") — everything available right after matching+scoring
    fit_score: int | None = None
    category_scores: dict[str, int] | None = None
    matches: list[MatchItem] | None = None
    gaps: list[GapItem] | None = None
    verdict: Verdict | None = None
    job_summary: JobSummary | None = None
    # roadmap payload (phase == "roadmap")
    roadmap: Roadmap | None = None
    roadmap_note: str | None = None
    # project payload (phase == "project")
    project_suggestion: ProjectSuggestion | None = None
    # error payload (phase == "error")
    error: AnalyzeStreamError | None = None


# ── Quick-mode + batch models ────────────────────────────────────────────────

class QuickJobSummary(BaseModel):
    title: str
    company: str
    posted_at: str | None = None
    apply_url: str | None = None


class QuickAnalysisResponse(BaseModel):
    fit_score: int
    verdict: Verdict
    job_summary: QuickJobSummary


class BatchJobInput(BaseModel):
    text: str | None = None
    url:  str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "BatchJobInput":
        if bool(self.text) == bool(self.url):
            raise ValueError("Provide exactly one of 'text' or 'url'.")
        return self


class BatchAnalyzeRequest(BaseModel):
    profile: UnifiedProfile
    jobs: list[BatchJobInput] = Field(..., min_length=1, max_length=_BATCH_MAX_JOBS)


class BatchErrorBody(BaseModel):
    message: str
    code: Literal["FETCH_FAILED", "EXTRACTION_FAILED", "VERDICT_FAILED", "INTERNAL"]


class BatchEnvelope(BaseModel):
    index: int
    status: Literal["ok", "error"]
    data: QuickAnalysisResponse | None = None
    error: BatchErrorBody | None = None


# ── Internal LLM intermediates ────────────────────────────────────────────────

class _RequirementItem(BaseModel):
    requirement: str
    type: Literal["technical", "experience", "education", "domain", "soft"]
    must_have: bool


class _EvaluationItem(BaseModel):
    requirement: str
    match_strength: Literal["strong", "partial", "missing"]
    evidence_snippet: str | None = None
    evidence_source: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_fences(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return raw


# Mojibake repair (no external deps). When UTF-8 text is decoded as Windows-1252,
# punctuation turns into telltale lead sequences: U+00E2 U+20AC ("a-hat euro") is
# the start of a corrupted em/en dash, smart quote, apostrophe, or ellipsis (the
# UTF-8 E2 80 xx family); U+00C3 leads corrupted accented Latin (C3 xx, e.g. an
# accented e); U+00C2 leads corrupted C2 xx (copyright, pound, non-breaking space).
# This happens when a source job page mislabels its charset, or when a model echoes
# such corruption from its context. We only attempt the repair when a marker is
# present AND the cp1252 -> utf-8 round trip decodes cleanly, so legitimate text (and
# mixed/partial cases that can't cleanly round-trip) is left untouched. Markers are
# built from chr() codepoints to keep this source file pure ASCII.
_MOJIBAKE_MARKERS = (chr(0xE2) + chr(0x20AC), chr(0xC3), chr(0xC2))


def _fix_mojibake(text: str) -> str:
    if not text or not any(m in text for m in _MOJIBAKE_MARKERS):
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _fix_mojibake_deep(obj):
    """Recursively repair mojibake in every string of a nested dict/list."""
    if isinstance(obj, str):
        return _fix_mojibake(obj)
    if isinstance(obj, list):
        return [_fix_mojibake_deep(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _fix_mojibake_deep(v) for k, v in obj.items()}
    return obj


def _get_user_analysis_cache(cache_key: str):
    """Per-user cache read that also repairs mojibake in rows written before the
    _fix_mojibake guard existed (a cache hit otherwise bypasses output repair)."""
    cached = get_user_analysis_cache(cache_key)
    return _fix_mojibake_deep(cached) if cached else cached


def _scrub_html(html: str) -> str:
    """Strip script/style blocks then all tags; collapse whitespace; repair mojibake."""
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html)
    return _fix_mojibake(html.strip())


def _posting_to_extracted(p) -> dict:
    """Convert a site_handlers.JobPosting → a _JOB_SCHEMA-shaped dict so the
    downstream pipeline treats it identically to a Firecrawl schema extraction."""
    return {
        "job_title":       p.title,
        "company_name":    p.company,
        "location":        p.location or "",
        "employment_type": "",
        "description":     p.description,
        "requirements":    list(p.requirements or []),
        "nice_to_haves":   [],
        "compensation":    "",
    }


def _build_text_from_extraction(ex: dict) -> str:
    """Convert a Firecrawl schema-extracted job object to clean labeled text for Step A."""
    parts: list[str] = []
    if ex.get("job_title"):
        parts.append(f"Job Title: {ex['job_title']}")
    if ex.get("company_name"):
        parts.append(f"Company: {ex['company_name']}")
    if ex.get("location"):
        parts.append(f"Location: {ex['location']}")
    if ex.get("employment_type"):
        parts.append(f"Employment Type: {ex['employment_type']}")
    if ex.get("compensation"):
        parts.append(f"Compensation: {ex['compensation']}")
    if ex.get("description"):
        parts.append(f"\nDescription:\n{ex['description']}")
    if ex.get("requirements"):
        lines = "\n".join(f"- {r}" for r in ex["requirements"])
        parts.append(f"\nRequirements:\n{lines}")
    if ex.get("nice_to_haves"):
        lines = "\n".join(f"- {r}" for r in ex["nice_to_haves"])
        parts.append(f"\nNice to Have:\n{lines}")
    return "\n".join(parts)


def _parse_firecrawl_response(data: dict, proxy_label: str) -> _FetchResult | None:
    """
    Inspect a Firecrawl response dict.
    Returns a _FetchResult if usable content was found, None otherwise.
    """
    if not data.get("success"):
        print(f"[analyze] Firecrawl {proxy_label}: success=False")
        return None

    payload   = data.get("data") or {}
    extracted = payload.get("extract") or {}
    markdown  = (payload.get("markdown") or "").strip()

    # Prefer schema extraction when it has the two required fields
    if extracted.get("job_title") and extracted.get("description"):
        text = _build_text_from_extraction(extracted)
        print(
            f"[analyze] Firecrawl {proxy_label}: extraction=YES "
            f"({len(extracted.get('requirements', []))} reqs), markdown={len(markdown)} chars"
        )
        return _FetchResult(text=text, path=f"firecrawl_{proxy_label}", extracted=extracted)

    # Fall back to markdown if long enough
    if len(markdown) >= _MIN_CONTENT_LEN:
        print(f"[analyze] Firecrawl {proxy_label}: extraction=NO, markdown={len(markdown)} chars")
        return _FetchResult(text=markdown, path=f"firecrawl_{proxy_label}", extracted=None)

    print(
        f"[analyze] Firecrawl {proxy_label}: extraction=NO, "
        f"markdown={len(markdown)} chars (too short)"
    )
    return None



async def _fetch_job_content(url: str) -> _FetchResult:
    """
    Three-tier fetch strategy:
      Attempt 1 — direct httpx GET (fast; works for Greenhouse, Lever, static sites)
      Attempt 2  — Firecrawl with configured proxy (default: "auto", which escalates past
                   Cloudflare / JS shells server-side) + waitFor + schema extraction
    Raises HTTPException(422) only if all attempts fail.
    """
    browser_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    # ── Attempt 0: site handler ──────────────────────────────────────────────
    handler = site_dispatch(url)
    if handler is not None:
        try:
            posting = await handler.fetch(url)
        except Exception as exc:
            print(f"[analyze] site_handler:{handler.name} raised {exc!r}, falling through")
            posting = None
        if posting is not None:
            extracted = _posting_to_extracted(posting)
            text = _build_text_from_extraction(extracted)
            print(f"[analyze] site_handler:{handler.name} success ({len(text)} chars)")
            return _FetchResult(
                text=text,
                path=f"site_handler:{handler.name}",
                extracted=extracted,
                posted_at=posting.posted_at,
                apply_url=posting.apply_url,
            )
        print(f"[analyze] site_handler:{handler.name} matched but returned None — falling through")

    # ── Attempt 1: direct ────────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=browser_headers) as client:
            resp = await client.get(url)
        if resp.status_code < 400:
            candidate = _scrub_html(resp.text)
            if _MIN_CONTENT_LEN <= len(candidate) <= _MAX_CONTENT_LEN:
                print(f"[analyze] direct fetch succeeded ({len(candidate)} chars)")
                return _FetchResult(text=candidate, path="direct", extracted=None)
            elif len(candidate) > _MAX_CONTENT_LEN:
                print(f"[analyze] direct fetch returned {len(candidate)} chars (too large — SPA/search page), trying Firecrawl")
            else:
                print(f"[analyze] direct fetch returned {len(candidate)} chars (JS shell), trying Firecrawl")
        else:
            print(f"[analyze] direct fetch returned HTTP {resp.status_code}, trying Firecrawl")
    except httpx.RequestError as exc:
        print(f"[analyze] direct fetch failed ({exc}), trying Firecrawl")

    # ── Attempt 2: Firecrawl ─────────────────────────────────────────────────
    # Proxy mode defaults to "auto": Firecrawl tries the cheapest proxy and escalates
    # past Cloudflare / JS shells server-side when blocked, so the old manual
    # basic→stealth retry (2a/2b) is no longer needed — one call covers both.
    if not _FIRECRAWL_API_KEY:
        print("[analyze] FIRECRAWL_API_KEY not set, skipping Firecrawl")
    else:
        try:
            async with timed(f"analyze/firecrawl:{_FIRECRAWL_PROXY_MODE}"):
                data = await _firecrawl_scrape(url, _FIRECRAWL_PROXY_MODE)
            result = _parse_firecrawl_response(data, _FIRECRAWL_PROXY_MODE)
            if result:
                return result
        except httpx.RequestError as exc:
            print(f"[analyze] Firecrawl {_FIRECRAWL_PROXY_MODE} network error: {exc}")

    # ── All attempts failed ───────────────────────────────────────────────────
    raise HTTPException(
        status_code=422,
        detail=(
            "Could not fetch the job listing automatically. "
            "Open the page in your browser, copy all the text, and paste it using 'Paste JD'."
        ),
    )


def _lookup_evaluation(
    requirement: str,
    evals: dict[str, "_EvaluationItem"],
) -> "_EvaluationItem | None":
    """Exact match first; fall back to case-insensitive prefix match (first 60 chars)."""
    ev = evals.get(requirement)
    if ev is not None:
        return ev
    key_short = requirement.lower()[:60]
    for k, v in evals.items():
        if k.lower()[:60] == key_short:
            return v
    return None


# ── LLM calls (synchronous — wrapped in asyncio.to_thread by caller) ─────────

def _loads_lenient(raw: str):
    """json.loads, but recover JSON embedded in prose — Sonnet (MODEL_MID) sometimes wraps the
    answer in reasoning text despite a 'JSON only' instruction, which breaks a bare json.loads.
    Scans for the first '['/'{' that raw_decodes. Raises json.JSONDecodeError if nothing
    parseable is found, so existing except-blocks still fire."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for i, ch in enumerate(raw):
            if ch in "[{":
                try:
                    obj, _end = decoder.raw_decode(raw, i)
                except json.JSONDecodeError:
                    continue
                return obj
        raise


def _run_extraction(job_text: str) -> tuple[JobSummary, list[_RequirementItem]]:
    """Raw Sonnet (MODEL_MID) call — caller should prefer extract_requirements() for cache reuse."""
    msg = ai.messages.create(
        model=MODEL_MID,
        # Verbose postings (e.g. Amazon SDE: 18 requirements) need >1024 output
        # tokens for the requirements JSON; at 1024 the JSON truncated mid-field
        # and json.loads failed, surfacing as a "retry" badge. 2048 fits real
        # postings with headroom (~1150 tokens observed for 18 requirements).
        max_tokens=2048,
        system=_REQUIREMENTS_SYSTEM,
        messages=[{"role": "user", "content": f"Job listing:\n\n{job_text}"}],
    )
    record_usage("extract", MODEL_MID, msg.usage)
    raw = _strip_fences(_fix_mojibake(msg.content[0].text))
    try:
        data = _loads_lenient(raw)
    except json.JSONDecodeError:
        raise ValueError(
            "Couldn't read the job requirements from this page — it may not be a specific job "
            "posting, or the listing was too long to process. Open the individual job posting, "
            "copy the full description, and paste it using 'Paste JD'."
        )

    summary = JobSummary(**data["job_summary"])
    requirements = [_RequirementItem(**r) for r in data.get("requirements", [])]
    return summary, requirements


async def extract_requirements(job_text: str) -> tuple[JobSummary, list[_RequirementItem]]:
    """Cached Step A. Both quick and full modes call this so the second run on
    the same job (regardless of user) skips the Opus call."""
    jh = job_text_hash(job_text)
    hit = await asyncio.to_thread(get_requirements_cache, jh)
    if hit:
        print(f"[analyze] requirements_cache=hit job={jh[:8]}")
        summary = JobSummary(**hit["job_summary"])
        requirements = [_RequirementItem(**r) for r in hit["requirements"]]
        return summary, requirements

    print(f"[analyze] requirements_cache=miss job={jh[:8]}")
    # sonnet_slot(): global Sonnet concurrency cap (Redis-distributed — see lib/anthropic_client.py).
    async with sonnet_slot():
        summary, requirements = await asyncio.to_thread(_run_extraction, job_text)
    await asyncio.to_thread(set_requirements_cache, jh, {
        "job_summary": summary.model_dump(),
        "requirements": [r.model_dump() for r in requirements],
    })
    return summary, requirements


def _run_quick_verdict(
    profile: UnifiedProfile,
    requirements: list[_RequirementItem],
) -> tuple[int, Verdict]:
    """One Haiku call — returns fit_score and a Verdict with reasoning."""
    profile_json = json.dumps(profile.model_dump(), indent=2)
    reqs_json = json.dumps([r.model_dump() for r in requirements], indent=2)

    # Prompt caching: in /analyze/batch, every job runs this with the SAME
    # profile and SAME system prompt, only `requirements` differs. We split the
    # user content so the stable (system + profile) prefix carries the
    # cache_control breakpoint and the per-job requirements sit after it. Across
    # a batch, jobs 2..N read the profile from cache instead of resending it.
    # This only engages when system+profile exceeds Haiku's 4096-token cache
    # minimum (resume-heavy profiles); below that it's a silent no-op. The text
    # the model sees is identical to the old single-string form.
    msg = ai.messages.create(
        model=MODEL_QUICK,
        max_tokens=512,
        temperature=0.2,
        system=_QUICK_VERDICT_SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": f"Profile:\n{profile_json}",
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"\n\nRequirements:\n{reqs_json}"},
        ]}],
    )
    record_usage("quick_verdict", MODEL_QUICK, msg.usage)
    raw = _strip_fences(_fix_mojibake(msg.content[0].text))
    try:
        # Haiku sometimes wraps the verdict JSON in a sentence of prose (e.g.
        # "Here's my assessment: {…}") despite the "JSON only" instruction, which
        # breaks a bare json.loads. Because the fetch + requirements are cached and
        # temperature is low, that failure is DETERMINISTIC — the same job fails the
        # same way on every retry (hence a "retry" badge that never clears). Use the
        # same lenient recovery _run_extraction already uses to dig the object out.
        data = _loads_lenient(raw)
    except json.JSONDecodeError:
        raise ValueError("Quick verdict returned invalid output — please try again.")

    fit_score = int(data["fit_score"])
    fit_score = max(0, min(100, fit_score))
    verdict = Verdict(**data["verdict"])
    return fit_score, verdict


def _build_phase3_user_content(
    profile: UnifiedProfile,
    job_summary: JobSummary,
    matches: list[MatchItem],
    gaps: list[GapItem],
    verdict: Verdict,
) -> dict[str, str]:
    """Common interpolation slots for the roadmap + project_suggestion prompts."""
    return {
        "job_title": job_summary.title,
        "company": job_summary.company,
        "key_requirements": "\n".join(f"- {r}" for r in job_summary.key_requirements) or "(none extracted)",
        "profile_summary": json.dumps(profile.model_dump(), indent=2),
        "matched_requirements_json": json.dumps([m.model_dump() for m in matches], indent=2),
        "gaps_json": json.dumps([g.model_dump() for g in gaps], indent=2),
        "verdict": f"{verdict.call} — {verdict.reasoning}",
    }


def _call_roadmap_llm(slots: dict[str, str]) -> Roadmap:
    """One Opus call returning a candidate Roadmap (URLs not yet validated)."""
    system = _ROADMAP_SYSTEM.format(**slots)
    # Prompt caching: _run_roadmap calls this up to 3x per analysis with a
    # byte-identical formatted system prompt (>4096 tokens once slots are
    # interpolated — above Opus 4.8's cache minimum). The cache_control marker
    # lets retries 2-3 read the system from cache instead of reprocessing it.
    # (The small static system prompts elsewhere are <4096 tokens and won't
    # cache; this one only clears the bar because the slots inflate it.)
    msg = ai.messages.create(
        model=MODEL_FULL,
        # Opus 4.8 (no temperature, runs longer than 4.5) needs headroom for a
        # full 5-item roadmap; 2048 truncated the JSON mid-output ~50% of the
        # time, failing the json.loads parse. 4096 gives reliable completion.
        max_tokens=4096,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": "Generate the roadmap JSON now."}],
    )
    record_usage("roadmap", MODEL_FULL, msg.usage)
    raw = _strip_fences(_fix_mojibake(msg.content[0].text))
    try:
        # Lenient parse: recover the JSON even if Opus prepends a sentence of prose.
        data = _loads_lenient(raw)
    except json.JSONDecodeError:
        raise ValueError("Roadmap returned invalid output — please try again.")
    return Roadmap.model_validate(data)


async def _run_roadmap(
    profile: UnifiedProfile,
    job_summary: JobSummary,
    matches: list[MatchItem],
    gaps: list[GapItem],
    verdict: Verdict,
) -> Roadmap:
    """Generate roadmap, then validate resource URLs (allowlist + HEAD).
    Retries (up to _ROADMAP_MAX_RETRIES additional calls) when any item ends
    up with fewer than 2 surviving resources. Resources from each attempt are
    accumulated per skill so later retries can backfill rather than replace.
    """
    slots = _build_phase3_user_content(profile, job_summary, matches, gaps, verdict)

    last_roadmap: Roadmap | None = None
    # skill → deduped list of validated resources, in discovery order
    accumulated: dict[str, list[RoadmapResource]] = {}

    for attempt in range(_ROADMAP_MAX_RETRIES + 1):
        try:
            candidate = await asyncio.to_thread(_call_roadmap_llm, slots)
        except Exception as e:
            if last_roadmap is None and attempt < _ROADMAP_MAX_RETRIES:
                print(f"[analyze] roadmap attempt {attempt + 1} failed: {e}")
                continue
            raise

        all_urls = [r.url for item in candidate.items for r in item.resources]
        validity = await validate_resource_urls(all_urls)
        dropped = sum(1 for u in all_urls if not validity.get(u))
        if dropped:
            print(f"[analyze] roadmap attempt {attempt + 1}: dropped {dropped}/{len(all_urls)} URLs")

        for item in candidate.items:
            bucket = accumulated.setdefault(item.skill, [])
            seen = {r.url for r in bucket}
            for r in item.resources:
                if validity.get(r.url) and r.url not in seen:
                    bucket.append(r)
                    seen.add(r.url)

        last_roadmap = candidate

        under_filled = [
            item for item in candidate.items
            if len(accumulated.get(item.skill, [])) < 2
        ]
        if not under_filled or attempt == _ROADMAP_MAX_RETRIES:
            break
        print(f"[analyze] roadmap: {len(under_filled)} items under 2 valid resources; retrying")

    assert last_roadmap is not None
    final_items = [
        RoadmapItem(
            skill=item.skill,
            priority=item.priority,
            timeline=item.timeline,
            why_it_matters=item.why_it_matters,
            milestone=item.milestone,
            resources=accumulated.get(item.skill, [])[:4],
        )
        for item in last_roadmap.items
    ][:5]

    return Roadmap(
        total_timeline=last_roadmap.total_timeline,
        summary=last_roadmap.summary,
        items=final_items,
    )


def _call_project_llm(slots: dict[str, str]) -> ProjectSuggestion:
    """One Opus call returning a ProjectSuggestion."""
    system = _PROJECT_SUGGESTION_SYSTEM.format(**slots)
    msg = ai.messages.create(
        model=MODEL_FULL,
        max_tokens=1536,
        system=system,
        messages=[{"role": "user", "content": "Generate the project suggestion JSON now."}],
    )
    record_usage("project", MODEL_FULL, msg.usage)
    raw = _strip_fences(_fix_mojibake(msg.content[0].text))
    try:
        # Lenient parse: recover the JSON even if Opus prepends a sentence of prose.
        data = _loads_lenient(raw)
    except json.JSONDecodeError:
        raise ValueError("Project suggestion returned invalid output — please try again.")
    return ProjectSuggestion.model_validate(data)


async def _run_project_suggestion(
    profile: UnifiedProfile,
    job_summary: JobSummary,
    matches: list[MatchItem],
    gaps: list[GapItem],
    verdict: Verdict,
) -> ProjectSuggestion:
    slots = _build_phase3_user_content(profile, job_summary, matches, gaps, verdict)
    return await asyncio.to_thread(_call_project_llm, slots)


def _run_matching(
    profile: UnifiedProfile,
    requirements: list[_RequirementItem],
) -> tuple[list[_EvaluationItem], str]:
    profile_json = json.dumps(profile.model_dump(), indent=2)
    reqs_json = json.dumps([r.model_dump() for r in requirements], indent=2)
    user_content = f"Profile:\n{profile_json}\n\nRequirements:\n{reqs_json}"

    msg = ai.messages.create(
        model=MODEL_MID,
        max_tokens=2048,
        system=_EVIDENCE_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    record_usage("match", MODEL_MID, msg.usage)
    raw = _strip_fences(_fix_mojibake(msg.content[0].text))
    try:
        data = _loads_lenient(raw)
    except json.JSONDecodeError:
        raise ValueError("Evidence matching returned invalid output — please try again.")

    evaluations = [_EvaluationItem(**e) for e in data.get("evaluations", [])]
    reasoning = data.get("verdict_reasoning", "")
    return evaluations, reasoning


# ── Score & verdict computation ───────────────────────────────────────────────

def _compute_scores(
    requirements: list[_RequirementItem],
    evals: dict[str, _EvaluationItem],
) -> dict[str, int]:
    by_type: dict[str, list[tuple[_RequirementItem, _EvaluationItem]]] = defaultdict(list)
    for req in requirements:
        ev = _lookup_evaluation(req.requirement, evals)
        if ev is None:
            ev = _EvaluationItem(requirement=req.requirement, match_strength="missing")
        by_type[req.type].append((req, ev))

    scores: dict[str, int] = {}
    for cat, pairs in by_type.items():
        total_weight = sum(2.0 if r.must_have else 1.0 for r, _ in pairs)
        if total_weight == 0:
            continue
        earned = sum(
            (2.0 if r.must_have else 1.0) * (
                1.0 if e.match_strength == "strong" else
                0.5 if e.match_strength == "partial" else
                0.0
            )
            for r, e in pairs
        )
        scores[cat] = max(0, min(100, round(earned / total_weight * 100)))
    return scores


def _compute_fit_score(category_scores: dict[str, int]) -> int:
    total_weight = sum(w for cat, w in CATEGORY_WEIGHTS.items() if cat in category_scores)
    if total_weight == 0:
        return 0
    weighted_sum = sum(
        CATEGORY_WEIGHTS[cat] * score
        for cat, score in category_scores.items()
        if cat in CATEGORY_WEIGHTS
    )
    return round(weighted_sum / total_weight)


def _classify_gaps(
    requirements: list[_RequirementItem],
    evals: dict[str, _EvaluationItem],
) -> list[GapItem]:
    gaps: list[GapItem] = []
    for req in requirements:
        ev = _lookup_evaluation(req.requirement, evals)
        if ev is None:
            strength = "missing"
        else:
            strength = ev.match_strength

        if req.must_have and strength == "missing":
            severity: Literal["critical", "moderate", "minor"] = (
                "critical" if req.type in ("experience", "education") else "moderate"
            )
        elif req.must_have and strength == "partial":
            severity = "minor"
        elif not req.must_have and strength == "missing":
            severity = "minor"
        else:
            continue  # strong matches and partial nice-to-haves are not gaps

        gaps.append(GapItem(
            requirement=req.requirement,
            type=req.type,
            must_have=req.must_have,
            severity=severity,
        ))
    return gaps


def _compute_verdict_call(fit_score: int, gaps: list[GapItem]) -> Literal["apply_now", "apply_after_prep", "skip"]:
    critical_gaps = [g for g in gaps if g.severity == "critical"]
    must_have_missing = [g for g in gaps if g.must_have and g.severity != "minor"]

    if critical_gaps or fit_score < 40:
        return "skip"
    elif fit_score >= 70 and not must_have_missing:
        return "apply_now"
    else:
        return "apply_after_prep"


# ── Endpoint ──────────────────────────────────────────────────────────────────

def _canonical_url(url: str) -> str:
    """Cheap URL normalization so two requests for the same page hash the same.
    Lowercases scheme+host, strips default port, strips trailing slash, drops fragment.
    Path and query are case-preserved (some routes are case-sensitive)."""
    p = urlparse(url.strip())
    scheme = (p.scheme or "https").lower()
    host = (p.hostname or "").lower()
    netloc = host if not (p.port and p.port not in (80, 443)) else f"{host}:{p.port}"
    path = p.path.rstrip("/") or "/"
    q = f"?{p.query}" if p.query else ""
    return f"{scheme}://{netloc}{path}{q}"


def _compute_job_id(job_url: str | None, job_text: str) -> str:
    """Stable identifier for cache keys. Prefer URL (deterministic) over fetched
    text (varies between fetches of the same page → cache misses)."""
    if job_url and job_url.strip():
        return "url:" + _canonical_url(job_url)
    return "text:" + job_text_hash(job_text)


def _job_text_from_listing(row: dict) -> str | None:
    """Build a compact pseudo-JD from a `listing_store` row so the existing
    extract_requirements + quick-verdict pipeline can score a served internship
    WITHOUT a live page fetch. Used only as a fallback when `_fetch_job_content`
    fails for a URL that's already in the index — a live-fetch failure for a flaky
    SPA listing (Wellfound/Herdora) then degrades to a coarser index-based score
    instead of a dead "retry" badge. Mirrors the field-selection in
    internships._fit_fields (parsed_json first, raw scraped columns as fallback).
    Returns None when there's essentially no usable content (caller re-raises)."""
    parsed: dict = {}
    raw = row.get("parsed_json")
    if raw:
        try:
            parsed = json.loads(raw) or {}
        except (json.JSONDecodeError, TypeError):
            parsed = {}

    if parsed:
        title = parsed.get("title")
        company = parsed.get("company")
        location = parsed.get("location")
        company_desc = parsed.get("company_description")
        skills = parsed.get("skills") or []
        seniority = parsed.get("seniority")
        role_category = parsed.get("role_category")
        is_internship = parsed.get("is_internship")
        requires_phd = parsed.get("requires_phd")
        sponsorship = parsed.get("sponsorship")
    else:
        # Unparsed row (warming index / live-fetch upsert): fall back to raw columns.
        title = row.get("search_title")
        company = row.get("company")
        location = row.get("verified_location")
        company_desc = " ".join((row.get("snippet") or "").split())[:200] or None
        skills = []
        seniority = role_category = sponsorship = None
        is_internship = requires_phd = None

    lines: list[str] = []
    if title:
        lines.append(f"Job title: {title}")
    if company:
        lines.append(f"Company: {company}")
    if location:
        lines.append(f"Location: {location}")
    if role_category:
        lines.append(f"Role category: {role_category}")
    if seniority:
        lines.append(f"Seniority: {seniority}")
    if isinstance(skills, list) and skills:
        lines.append("Relevant skills/technologies: " + ", ".join(str(s) for s in skills))
    if company_desc:
        lines.append(f"About the company: {company_desc}")
    if is_internship is not None:
        lines.append(f"Internship: {'yes' if is_internship else 'no'}")
    if requires_phd is not None:
        lines.append(f"Requires PhD: {'yes' if requires_phd else 'no'}")
    if sponsorship:
        lines.append(f"Visa sponsorship: {sponsorship}")

    # Need more than just a bare company line to be worth scoring on.
    if not lines or (len(lines) == 1 and lines[0].startswith("Company:")):
        return None
    return "\n".join(lines)


async def _resolve_job(
    profile_unused: UnifiedProfile,  # reserved for future per-user URL rewriting
    job_url: str | None,
    job_text: str | None,
) -> tuple[str, _FetchResult | None, str]:
    """Returns (job_text_trimmed, fetch_result_or_None_if_pasted, job_id).
    `job_id` is the cache-stable identifier (URL when present, text-hash otherwise).
    Raises HTTPException on user-facing errors (LinkedIn, SPA blocklist, fetch failure)."""
    has_url = bool(job_url and job_url.strip())
    has_text = bool(job_text and job_text.strip())
    if not has_url and not has_text:
        raise HTTPException(status_code=422, detail="Provide job_url or job_text.")

    if has_url:
        host = urlparse(job_url or "").hostname or ""
        if any(host == d or host.endswith(f".{d}") for d in _AUTH_WALL_DOMAINS):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{host} blocks automated access, so URLs from this site can't be fetched. "
                    "Open the job page in your browser, copy all the text, and paste it using 'Paste JD'."
                ),
            )
        spa_msg = _SPA_SEARCH_PORTALS.get(host)
        if spa_msg:
            raise HTTPException(status_code=422, detail=spa_msg)

        # Per-URL fetch cache: the scrape (esp. Firecrawl JS render) is the expensive,
        # profile-independent part — reuse it so a 2nd analysis of the same URL skips it.
        cached_fetch = await asyncio.to_thread(get_job_fetch_cache, job_url)
        if cached_fetch:
            print(f"[analyze] job_fetch_cache=hit url={job_url[:60]}")
            fr = _FetchResult(
                text=cached_fetch["text"], path="cache", extracted=None,
                posted_at=cached_fetch.get("posted_at"), apply_url=cached_fetch.get("apply_url"),
            )
        else:
            print(f"[analyze] job_fetch_cache=miss url={job_url[:60]}")
            try:
                async with timed("analyze/fetch"):
                    fr = await _fetch_job_content(job_url)  # type: ignore[arg-type]
            except HTTPException as exc:
                # Live fetch failed. For a served internship (URL already in the
                # listing_store index), fall back to scoring from the stored,
                # precomputed listing fields so a flaky SPA fetch (Wellfound/Herdora)
                # degrades to a coarser-but-real score instead of a dead "retry".
                # Not cached (don't block a future good fetch); job_id stays URL-based
                # so the per-user analysis cache key is unchanged.
                row = await asyncio.to_thread(get_listing_by_url, job_url)
                fallback = _job_text_from_listing(row) if row else None
                if fallback is None:
                    raise  # arbitrary URL / nothing usable → preserve today's error
                print(f"[analyze] fetch path=listing_fallback url={job_url[:60]}")
                text = fallback[:8000]
                return text, None, _compute_job_id(job_url, text)
            await asyncio.to_thread(set_job_fetch_cache, job_url, {
                "text": fr.text, "posted_at": fr.posted_at,
                "apply_url": fr.apply_url, "path": fr.path,
            })
        print(f"[analyze] fetch path={fr.path} json_extracted={fr.extracted is not None}")
        text = fr.text[:8000]
        return text, fr, _compute_job_id(job_url, text)

    print("[analyze] fetch path=paste json_extracted=False")
    text = (job_text or "").strip()[:8000]
    return text, None, _compute_job_id(None, text)


# Auth gate (see lib/auth.py): standalone analyzer = "one free, then gate" — the hard
# anonymous gate is enforced frontend-side; the backend counts an 'analysis' against the
# signed-in user's daily quota (full mode only — quick mode is the batch unit). verify_turnstile
# is a no-op until TURNSTILE_SECRET is set. Both no-op entirely when auth is off (dev).
@router.post("/analyze", dependencies=[Depends(verify_turnstile)])
async def analyze(req: AnalyzeRequest, user: User | None = Depends(optional_user)):
    """Thin wrapper: open a timing session so the full pipeline prints a sorted
    [timing] breakdown (fetch vs extract vs match vs phase3), mirroring /run."""
    # Charge the analysis quota for full runs only (Opus Phase 3 is the priced action). A
    # cached hit still counts (one user action = one slot); fine for a daily usage cap.
    if req.mode == "full":
        await enforce_quota(user, "analysis")
    with timing_session(f"/analyze {req.mode}"), cost_session(f"/analyze {req.mode}", user_id=user.id if user else None):
        return await _analyze_impl(req)


async def _analyze_impl(req: AnalyzeRequest):
    job_text, fetch_result, job_id = await _resolve_job(req.profile, req.job_url, req.job_text)
    print(f"[analyze] job_id={job_id[:80]}")

    # ── Per-user cache check (covers both modes) ──────────────────────────────
    profile_json = req.profile.model_dump_json()
    cache_key = analysis_cache_key(req.mode, profile_json, job_id)
    cached = await asyncio.to_thread(_get_user_analysis_cache, cache_key)
    if cached:
        print(f"[analyze] user_cache=hit mode={req.mode} key={cache_key[:24]}…")
        if req.mode == "quick":
            return QuickAnalysisResponse(**cached)
        # For a cached full result, also reconcile its headline against the
        # current quick cache so stale full entries (computed before the
        # headline-reconcile fix) self-heal on the next read.
        quick_key = analysis_cache_key("quick", profile_json, job_id)
        quick_cached = await asyncio.to_thread(_get_user_analysis_cache, quick_key)
        if quick_cached:
            cur_fit  = cached.get("fit_score")
            cur_call = (cached.get("verdict") or {}).get("call")
            new_fit  = int(quick_cached["fit_score"])
            new_call = quick_cached["verdict"]["call"]
            if cur_fit != new_fit or cur_call != new_call:
                print(f"[analyze] self-healing stale full cache: {cur_fit}/{cur_call} -> {new_fit}/{new_call}")
                cached["fit_score"] = new_fit
                cached["verdict"]["call"] = new_call
                await asyncio.to_thread(set_user_analysis_cache, cache_key, "full", cached)
        else:
            print(f"[analyze] no quick cache for this job_id; full headline unreconciled")
        # Phase 3 backfill: older full-mode cache rows predate roadmap/project.
        # Generate only the missing pieces (honoring include flags) and rewrite
        # the row so the next read is a clean hit.
        cached = await _phase3_backfill_cached_row(
            cached, cache_key, req.profile, req.include
        )
        return AnalysisResponse(**cached)
    print(f"[analyze] user_cache=miss mode={req.mode} key={cache_key[:24]}…")

    # ── Step A (cached globally) ──────────────────────────────────────────────
    try:
        job_summary, requirements = await timed_call("analyze/extract", extract_requirements(job_text))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Requirement extraction failed: {e}")

    if not requirements:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not find job requirements in the page. "
                "The site may require login to show the full listing. "
                "Try the 'Paste JD' tab: open the job page, copy the full description, and paste it."
            ),
        )
    print(f"[analyze] extracted {len(requirements)} requirements from job listing")

    # ── Quick branch ──────────────────────────────────────────────────────────
    if req.mode == "quick":
        try:
            fit_score, verdict = await asyncio.to_thread(
                _run_quick_verdict, req.profile, requirements
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Quick verdict failed: {e}")

        quick = QuickAnalysisResponse(
            fit_score=fit_score,
            verdict=verdict,
            job_summary=QuickJobSummary(
                title=job_summary.title,
                company=job_summary.company,
                posted_at=fetch_result.posted_at if fetch_result else None,
                apply_url=fetch_result.apply_url if fetch_result else None,
            ),
        )
        await asyncio.to_thread(set_user_analysis_cache, cache_key, "quick", quick.model_dump())
        print(f"[analyze] quick: fit={fit_score} verdict={verdict.call}")
        return quick

    # ── Full branch (Step B + assembly) ───────────────────────────────────────
    try:
        # sonnet_slot(): global Sonnet concurrency cap (Redis-distributed — see lib/anthropic_client.py).
        async with sonnet_slot():
            evaluations, verdict_reasoning = await timed_call(
                "analyze/match", asyncio.to_thread(_run_matching, req.profile, requirements)
            )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evidence matching failed: {e}")

    evals_by_req = {e.requirement: e for e in evaluations}

    category_scores = _compute_scores(requirements, evals_by_req)
    full_fit_score = _compute_fit_score(category_scores)
    gaps = _classify_gaps(requirements, evals_by_req)
    full_verdict_call = _compute_verdict_call(full_fit_score, gaps)

    # If a quick analysis already exists for this (profile, job), reuse its
    # fit_score + verdict.call so the headline numbers the user saw on the
    # results card don't change when they click through to the full breakdown.
    # Full mode still owns the deeper output (matches, gaps, category_scores,
    # evidence snippets, verdict.reasoning) — only the two visible numbers are
    # taken from the quick cache.
    quick_key = analysis_cache_key("quick", profile_json, job_id)
    quick_cached = await asyncio.to_thread(_get_user_analysis_cache, quick_key)
    if quick_cached:
        fit_score = int(quick_cached["fit_score"])
        verdict_call = quick_cached["verdict"]["call"]
        print(
            f"[analyze] full headline reconciled from quick cache: "
            f"full-computed={full_fit_score}/{full_verdict_call} -> "
            f"quick={fit_score}/{verdict_call}"
        )
    else:
        fit_score = full_fit_score
        verdict_call = full_verdict_call

    matches: list[MatchItem] = []
    for req_item in requirements:
        ev = _lookup_evaluation(req_item.requirement, evals_by_req)
        if ev and ev.match_strength in ("strong", "partial"):
            matches.append(MatchItem(
                requirement=req_item.requirement,
                type=req_item.type,
                must_have=req_item.must_have,
                match_strength=ev.match_strength,  # type: ignore[arg-type]
                evidence_snippet=ev.evidence_snippet,
                evidence_source=ev.evidence_source,
            ))

    print(f"[analyze] step B: {len(matches)} matches, {len(gaps)} gaps, verdict={verdict_call}")

    full_verdict = Verdict(call=verdict_call, reasoning=verdict_reasoning)

    # ── Phase 3: roadmap + project suggestion (parallel, additive) ────────────
    roadmap, roadmap_note, project_suggestion = await timed_call(
        "analyze/phase3",
        _generate_phase3(req.profile, job_summary, matches, gaps, full_verdict, req.include),
    )

    result = AnalysisResponse(
        fit_score=fit_score,
        category_scores=category_scores,
        matches=matches,
        gaps=gaps,
        verdict=full_verdict,
        job_summary=job_summary,
        roadmap=roadmap,
        roadmap_note=roadmap_note,
        project_suggestion=project_suggestion,
    )

    await asyncio.to_thread(set_user_analysis_cache, cache_key, "full", result.model_dump())
    return result


async def _phase3_backfill_cached_row(
    cached: dict,
    cache_key: str,
    profile: UnifiedProfile,
    include: IncludeFlags,
) -> dict:
    """If a cached full-mode row is missing roadmap/project_suggestion and the
    request asks for them, run only the missing LLM calls, write back, and
    return the patched dict. No-op when nothing needs backfilling.

    Phase 3 reads from the cached analysis (gaps/matches/verdict/job_summary)
    plus the live request profile — no job re-fetch or re-extraction.
    """
    needs_roadmap = (
        include.roadmap
        and cached.get("roadmap") is None
        and cached.get("roadmap_note") is None
    )
    needs_project = include.project and cached.get("project_suggestion") is None
    if not needs_roadmap and not needs_project:
        return cached

    try:
        job_summary = JobSummary(**cached["job_summary"])
        matches = [MatchItem(**m) for m in cached.get("matches", [])]
        gaps = [GapItem(**g) for g in cached.get("gaps", [])]
        verdict = Verdict(**cached["verdict"])
    except Exception as e:
        print(f"[analyze] phase3 backfill: failed to rehydrate cached row ({e}); skipping")
        return cached

    # Honor the same include flags during backfill so we only do the work the
    # request actually wants.
    backfill_flags = IncludeFlags(roadmap=needs_roadmap, project=needs_project)
    roadmap, roadmap_note, project = await _generate_phase3(
        profile, job_summary, matches, gaps, verdict, backfill_flags
    )

    patched = dict(cached)
    if needs_roadmap:
        patched["roadmap"] = roadmap.model_dump() if roadmap else None
        patched["roadmap_note"] = roadmap_note
    if needs_project:
        patched["project_suggestion"] = project.model_dump() if project else None
    await asyncio.to_thread(set_user_analysis_cache, cache_key, "full", patched)
    print(
        f"[analyze] phase3 backfill: roadmap={'yes' if needs_roadmap else 'no'} "
        f"project={'yes' if needs_project else 'no'}"
    )
    return patched


async def _generate_phase3(
    profile: UnifiedProfile,
    job_summary: JobSummary,
    matches: list[MatchItem],
    gaps: list[GapItem],
    verdict: Verdict,
    include: IncludeFlags,
) -> tuple[Roadmap | None, str | None, ProjectSuggestion | None]:
    """Fires roadmap + project_suggestion LLM calls in parallel, honoring
    include flags. Roadmap is skipped (None) when gaps is empty; in that case
    roadmap_note is set instead. Failures are logged and swallowed — a Phase 3
    failure must not break the rest of the analysis response."""
    roadmap_task: asyncio.Task[Roadmap] | None = None
    project_task: asyncio.Task[ProjectSuggestion] | None = None

    if include.roadmap and gaps:
        roadmap_task = asyncio.create_task(
            _run_roadmap(profile, job_summary, matches, gaps, verdict)
        )
    if include.project:
        project_task = asyncio.create_task(
            _run_project_suggestion(profile, job_summary, matches, gaps, verdict)
        )

    roadmap: Roadmap | None = None
    roadmap_note: str | None = None
    project: ProjectSuggestion | None = None

    if include.roadmap and not gaps:
        roadmap_note = _ROADMAP_NOTE_NO_GAPS

    if roadmap_task is not None:
        try:
            roadmap = await roadmap_task
        except Exception as e:
            print(f"[analyze] roadmap generation failed: {e}")

    if project_task is not None:
        try:
            project = await project_task
        except Exception as e:
            print(f"[analyze] project_suggestion failed: {e}")

    return roadmap, roadmap_note, project


# ── /analyze/stream (full-mode true streaming) ────────────────────────────────
# Additive sibling of the JSON /analyze: same pipeline, but the verdict ships as
# soon as matching completes and Phase 3 (roadmap, the ~80% latency driver) streams
# in as each piece finishes. The JSON /analyze is untouched.

async def _analyze_stream_prelude(req: AnalyzeRequest):
    """Run the *can-fail* prefix of the full pipeline — resolve → user-cache →
    extract → match → score — and raise HTTPException (422/500) HERE, before any
    StreamingResponse body is constructed, so the JSON endpoint's friendly status
    codes are preserved (a StreamingResponse locks status at 200 the moment it
    starts). Returns one of:
      ("cache_hit", AnalysisResponse)                       — emit all phases from cache
      ("computed", verdict_payload, cache_key, include)     — stream Phase 3 live
    The verdict_payload keys match AnalyzeStreamEnvelope's verdict fields exactly.
    Mirrors _analyze_impl's full-branch prefix (resolve/cache/extract/match/score)."""
    job_text, fetch_result, job_id = await _resolve_job(req.profile, req.job_url, req.job_text)
    print(f"[analyze/stream] job_id={job_id[:80]}")

    profile_json = req.profile.model_dump_json()
    cache_key = analysis_cache_key("full", profile_json, job_id)
    cached = await asyncio.to_thread(_get_user_analysis_cache, cache_key)
    if cached:
        print(f"[analyze/stream] user_cache=hit key={cache_key[:24]}…")
        # Self-heal stale headline from the quick cache (same as _analyze_impl).
        quick_key = analysis_cache_key("quick", profile_json, job_id)
        quick_cached = await asyncio.to_thread(_get_user_analysis_cache, quick_key)
        if quick_cached:
            cur_fit = cached.get("fit_score")
            cur_call = (cached.get("verdict") or {}).get("call")
            new_fit = int(quick_cached["fit_score"])
            new_call = quick_cached["verdict"]["call"]
            if cur_fit != new_fit or cur_call != new_call:
                cached["fit_score"] = new_fit
                cached["verdict"]["call"] = new_call
                await asyncio.to_thread(set_user_analysis_cache, cache_key, "full", cached)
        cached = await _phase3_backfill_cached_row(cached, cache_key, req.profile, req.include)
        return ("cache_hit", AnalysisResponse(**cached))
    print(f"[analyze/stream] user_cache=miss key={cache_key[:24]}…")

    # ── Step A: extraction ────────────────────────────────────────────────────
    try:
        job_summary, requirements = await timed_call("analyze/extract", extract_requirements(job_text))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Requirement extraction failed: {e}")

    if not requirements:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not find job requirements in the page. "
                "The site may require login to show the full listing. "
                "Try the 'Paste JD' tab: open the job page, copy the full description, and paste it."
            ),
        )

    # ── Step B: matching ──────────────────────────────────────────────────────
    try:
        async with sonnet_slot():  # global Sonnet concurrency cap (Redis-distributed)
            evaluations, verdict_reasoning = await timed_call(
                "analyze/match", asyncio.to_thread(_run_matching, req.profile, requirements)
            )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evidence matching failed: {e}")

    evals_by_req = {e.requirement: e for e in evaluations}
    category_scores = _compute_scores(requirements, evals_by_req)
    full_fit_score = _compute_fit_score(category_scores)
    gaps = _classify_gaps(requirements, evals_by_req)
    full_verdict_call = _compute_verdict_call(full_fit_score, gaps)

    # Reconcile the headline (fit_score + verdict.call) from the quick cache if one
    # exists, so the number the user saw on the results card doesn't shift here.
    quick_key = analysis_cache_key("quick", profile_json, job_id)
    quick_cached = await asyncio.to_thread(_get_user_analysis_cache, quick_key)
    if quick_cached:
        fit_score = int(quick_cached["fit_score"])
        verdict_call = quick_cached["verdict"]["call"]
    else:
        fit_score = full_fit_score
        verdict_call = full_verdict_call

    matches: list[MatchItem] = []
    for req_item in requirements:
        ev = _lookup_evaluation(req_item.requirement, evals_by_req)
        if ev and ev.match_strength in ("strong", "partial"):
            matches.append(MatchItem(
                requirement=req_item.requirement,
                type=req_item.type,
                must_have=req_item.must_have,
                match_strength=ev.match_strength,  # type: ignore[arg-type]
                evidence_snippet=ev.evidence_snippet,
                evidence_source=ev.evidence_source,
            ))

    full_verdict = Verdict(call=verdict_call, reasoning=verdict_reasoning)
    print(f"[analyze/stream] step B: {len(matches)} matches, {len(gaps)} gaps, verdict={verdict_call}")

    verdict_payload = {
        "fit_score": fit_score,
        "category_scores": category_scores,
        "matches": matches,
        "gaps": gaps,
        "verdict": full_verdict,
        "job_summary": job_summary,
    }
    return ("computed", verdict_payload, cache_key, req.include)


async def _stream_phase3(
    profile: UnifiedProfile,
    job_summary: JobSummary,
    matches: list[MatchItem],
    gaps: list[GapItem],
    verdict: Verdict,
    include: IncludeFlags,
):
    """Async-generator twin of _generate_phase3: fires the same roadmap + project
    tasks concurrently but yields an AnalyzeStreamEnvelope as EACH completes
    (completion order), so whichever finishes first reaches the client first.
    Same no-gaps roadmap_note + failure-swallow semantics as _generate_phase3."""
    if include.roadmap and not gaps:
        # No gaps → no roadmap call; emit the note immediately (mirrors _generate_phase3).
        yield AnalyzeStreamEnvelope(phase="roadmap", roadmap_note=_ROADMAP_NOTE_NO_GAPS)

    task_kind: dict[asyncio.Task, str] = {}
    if include.roadmap and gaps:
        task_kind[asyncio.create_task(
            _run_roadmap(profile, job_summary, matches, gaps, verdict)
        )] = "roadmap"
    if include.project:
        task_kind[asyncio.create_task(
            _run_project_suggestion(profile, job_summary, matches, gaps, verdict)
        )] = "project"

    pending = set(task_kind.keys())
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            kind = task_kind[t]
            try:
                result = t.result()
            except Exception as e:
                print(f"[analyze/stream] {kind} generation failed: {e}")
                result = None
            if kind == "roadmap":
                yield AnalyzeStreamEnvelope(phase="roadmap", roadmap=result)
            else:
                yield AnalyzeStreamEnvelope(phase="project", project_suggestion=result)


def _cached_stream_envelopes(full: AnalysisResponse) -> list[AnalyzeStreamEnvelope]:
    """Replay a complete (cached) AnalysisResponse as the same phase sequence a
    live run would emit, so the frontend's stream-assembly path is identical for
    hits and misses."""
    return [
        AnalyzeStreamEnvelope(
            phase="verdict",
            fit_score=full.fit_score,
            category_scores=full.category_scores,
            matches=full.matches,
            gaps=full.gaps,
            verdict=full.verdict,
            job_summary=full.job_summary,
        ),
        AnalyzeStreamEnvelope(phase="roadmap", roadmap=full.roadmap, roadmap_note=full.roadmap_note),
        AnalyzeStreamEnvelope(phase="project", project_suggestion=full.project_suggestion),
        AnalyzeStreamEnvelope(phase="done"),
    ]


# Always full mode → charge one 'analysis' per call (quota dep); verify_turnstile no-ops
# until configured. Both no-op when auth is off (dev).
@router.post("/analyze/stream", dependencies=[Depends(quota("analysis")), Depends(verify_turnstile)])
async def analyze_stream(req: AnalyzeRequest, user: User | None = Depends(optional_user)):
    """Full-mode true streaming. The prelude (resolve/extract/match/score) runs
    first and can still raise a proper 422/500; only the verdict-emit + Phase 3
    (which can't fail the request) stream. Emits ndjson AnalyzeStreamEnvelopes:
    verdict → roadmap/project (completion order) → done. The JSON /analyze is
    unchanged. Two [cost] ledgers print by design (prelude + phase3)."""
    uid = user.id if user else None
    # Prelude: opened in its own session so extract/match spend is recorded, and
    # so its HTTPExceptions raise BEFORE the StreamingResponse is constructed.
    with timing_session("/analyze/stream prelude"), cost_session("/analyze/stream prelude", user_id=uid):
        prelude = await _analyze_stream_prelude(req)

    async def _gen():
        # cost_session wraps task creation so the Phase 3 tasks inherit the
        # contextvar binding and their record_usage() calls aggregate (same as batch).
        with timing_session("/analyze/stream phase3"), cost_session("/analyze/stream phase3", user_id=uid):
            if prelude[0] == "cache_hit":
                for env in _cached_stream_envelopes(prelude[1]):
                    yield env.model_dump_json() + "\n"
                return

            _, payload, cache_key, include = prelude
            yield AnalyzeStreamEnvelope(phase="verdict", **payload).model_dump_json() + "\n"

            roadmap: Roadmap | None = None
            roadmap_note: str | None = None
            project: ProjectSuggestion | None = None
            async for env in _stream_phase3(
                req.profile, payload["job_summary"], payload["matches"],
                payload["gaps"], payload["verdict"], include,
            ):
                if env.phase == "roadmap":
                    roadmap, roadmap_note = env.roadmap, env.roadmap_note
                elif env.phase == "project":
                    project = env.project_suggestion
                yield env.model_dump_json() + "\n"

            # Assemble the full result and cache it so a re-open is an instant hit.
            result = AnalysisResponse(
                fit_score=payload["fit_score"],
                category_scores=payload["category_scores"],
                matches=payload["matches"],
                gaps=payload["gaps"],
                verdict=payload["verdict"],
                job_summary=payload["job_summary"],
                roadmap=roadmap,
                roadmap_note=roadmap_note,
                project_suggestion=project,
            )
            await asyncio.to_thread(set_user_analysis_cache, cache_key, "full", result.model_dump())
            yield AnalyzeStreamEnvelope(phase="done").model_dump_json() + "\n"

    return StreamingResponse(
        _gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# ── Batch endpoint ───────────────────────────────────────────────────────────

def _classify_exc(exc: BaseException) -> Literal["FETCH_FAILED", "EXTRACTION_FAILED", "VERDICT_FAILED", "INTERNAL"]:
    if isinstance(exc, HTTPException):
        detail = (exc.detail or "").lower() if isinstance(exc.detail, str) else ""
        if "fetch" in detail or "could not fetch" in detail or "blocks automated" in detail:
            return "FETCH_FAILED"
        if "requirement" in detail or "job requirements" in detail:
            return "EXTRACTION_FAILED"
        if "verdict" in detail:
            return "VERDICT_FAILED"
    return "INTERNAL"


async def _quick_for_one(
    profile: UnifiedProfile,
    job: BatchJobInput,
    sem: asyncio.Semaphore,
) -> QuickAnalysisResponse:
    """Per-job quick analysis used by /analyze/batch.
    Cache hits return without acquiring the LLM semaphore."""
    job_text, fetch_result, job_id = await _resolve_job(profile, job.url, job.text)

    profile_json = profile.model_dump_json()
    cache_key = analysis_cache_key("quick", profile_json, job_id)
    cached = await asyncio.to_thread(_get_user_analysis_cache, cache_key)
    if cached:
        print(f"[batch] user_cache=hit key={cache_key[:24]}…")
        record_cache_hit("analysis:quick", MODEL_QUICK)  # repeat-search score served from SQLite
        return QuickAnalysisResponse(**cached)

    async with sem:
        summary, requirements = await extract_requirements(job_text)
        if not requirements:
            raise HTTPException(status_code=422, detail="Could not find job requirements in the page.")
        fit_score, verdict = await asyncio.to_thread(_run_quick_verdict, profile, requirements)

    quick = QuickAnalysisResponse(
        fit_score=fit_score,
        verdict=verdict,
        job_summary=QuickJobSummary(
            title=summary.title,
            company=summary.company,
            posted_at=fetch_result.posted_at if fetch_result else None,
            apply_url=fetch_result.apply_url if fetch_result else None,
        ),
    )
    await asyncio.to_thread(set_user_analysis_cache, cache_key, "quick", quick.model_dump())
    return quick


# Matcher results-reveal gate: REQUIRES sign-in (require_user) + charges one 'matcher' run;
# verify_turnstile no-ops until configured. All three no-op when auth is off (dev).
@router.post(
    "/analyze/batch",
    dependencies=[Depends(require_user), Depends(quota("matcher")), Depends(verify_turnstile)],
)
async def analyze_batch(req: BatchAnalyzeRequest, user: User | None = Depends(optional_user)):
    """Streams ndjson: one BatchEnvelope per line, in completion order.
    Cap of 50 jobs per batch (enforced by pydantic). Cap of 8 in-flight LLM calls."""
    uid = user.id if user else None
    sem = asyncio.Semaphore(_BATCH_LLM_CONCURRENCY)
    queue: asyncio.Queue[BatchEnvelope] = asyncio.Queue()

    async def _one(i: int, job: BatchJobInput) -> None:
        try:
            quick = await _quick_for_one(req.profile, job, sem)
            await queue.put(BatchEnvelope(index=i, status="ok", data=quick))
        except Exception as exc:
            msg = exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, str) else str(exc)
            code = _classify_exc(exc)
            print(f"[batch] job[{i}] failed code={code} msg={msg[:120]}")
            await queue.put(BatchEnvelope(
                index=i, status="error",
                error=BatchErrorBody(message=msg, code=code),
            ))

    async def _gen():
        # cost_session must wrap task creation so each task inherits the contextvar
        # binding and its record_usage() calls aggregate into one batch breakdown.
        with cost_session(f"/analyze/batch ({len(req.jobs)} jobs)", user_id=uid):
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
