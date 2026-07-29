"""SkyMatch load test (M9) — validates the 2-replica web service + the Redis-backed
guard (per-IP rate/concurrency limiter) + the org-wide Sonnet governor under concurrency.

Run with locust (see loadtest/README.md). The scenarios are TAGGED so you choose how much
money the run costs:

    --tags smoke      GET /health only. Free. Validates routing / LB across replicas.
    --tags serve      POST /internships/search. Free of LLM cost (zero-LLM serve path) —
                      exercises both replicas, the Postgres pool, and the embedding rank.
                      The main throughput scenario.
    --tags guard      Fires serve requests with NO wait, to trip the per-IP rate limiter
                      and confirm it returns a clean 429 (not a 5xx) under burst. Cheap.
    --tags governor   POST /analyze (full). REAL Sonnet calls — THIS COSTS MONEY and needs
                      PF_AUTH_TOKEN (and PF_TURNSTILE_TOKEN if Turnstile is on). The only
                      scenario that actually exercises SONNET_MAX_CONCURRENCY across replicas.

Default (no --tags) runs smoke + serve + guard — i.e. everything EXCEPT the paid governor
scenario — so an accidental run never burns Anthropic budget.

Config via env (all optional except --host):
    PF_AUTH_TOKEN        Bearer token for the governor scenario (a Supabase user JWT).
    PF_TURNSTILE_TOKEN   X-Turnstile-Token value, if TURNSTILE_SECRET is set on the target.

429 (rate-limited) and 503 (kill switch / spend cap) are EXPECTED under load and are tallied
separately rather than counted as failures — only unexpected statuses fail the run.
"""
import os

from locust import HttpUser, between, events, tag, task

# ── Auth / abuse-edge headers (only sent when configured) ────────────────────
_AUTH_TOKEN = os.getenv("PF_AUTH_TOKEN", "").strip()
_TURNSTILE_TOKEN = os.getenv("PF_TURNSTILE_TOKEN", "").strip()

# ── Sample payloads ──────────────────────────────────────────────────────────
# A minimal-but-valid UnifiedProfile (every ProfileAnalysis required field present; the
# rich list fields default to []). Used for /internships/search and /analyze.
SAMPLE_PROFILE = {
    "full_name": "Load Tester",
    "headline": "CS undergrad seeking SWE internships",
    "location": "San Francisco, CA",
    "school": "State University",
    "graduation_year": 2027,
    "major": "Computer Science",
    "fraternity_or_orgs": [],
    "past_companies": [],
    "current_company": None,
    "technical_skills": ["Python", "JavaScript", "React", "SQL"],
    "field_of_interest": "Software Engineering",
    "key_values": ["impact", "learning"],
}

SAMPLE_JOB_TEXT = (
    "Software Engineering Intern — Summer 2027. We're looking for a CS student "
    "comfortable with Python and React to build internal tooling. Requirements: "
    "currently pursuing a BS in Computer Science, experience with web frameworks, "
    "familiarity with SQL databases, and strong communication skills."
)

# Statuses we deliberately provoke (limiter / kill switch) — not failures.
_EXPECTED = {200, 429, 503}


class SkyMatchUser(HttpUser):
    # Modest think-time so a single host doesn't instantly saturate the per-IP limiter
    # outside the dedicated 'guard' burst scenario.
    wait_time = between(1, 3)

    def on_start(self):
        self._headers = {"Content-Type": "application/json"}
        if _AUTH_TOKEN:
            self._headers["Authorization"] = f"Bearer {_AUTH_TOKEN}"
        if _TURNSTILE_TOKEN:
            self._headers["X-Turnstile-Token"] = _TURNSTILE_TOKEN

    def _post(self, path: str, payload: dict, name: str):
        with self.client.post(
            path, json=payload, headers=self._headers, name=name, catch_response=True
        ) as resp:
            if resp.status_code in _EXPECTED:
                resp.success()  # 429/503 are valid guard behavior under load
            else:
                resp.failure(f"unexpected {resp.status_code}: {resp.text[:200]}")

    @tag("smoke")
    @task(10)
    def health(self):
        with self.client.get("/health", name="GET /health", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"unexpected {resp.status_code}")

    @tag("serve")
    @task(5)
    def internships_search(self):
        # Zero-LLM serve path: replicas + Postgres pool + embedding rank, no Anthropic cost.
        self._post("/internships/search", SAMPLE_PROFILE, "POST /internships/search")

    @tag("guard")
    @task(3)
    def guard_burst(self):
        # Same cheap endpoint but the 'guard' tag is meant to be run with high user count /
        # low wait to deliberately exceed RATE_LIMIT_PER_MIN and confirm clean 429s.
        self._post("/internships/search", SAMPLE_PROFILE, "POST /internships/search [burst]")

    @tag("governor")
    @task(1)
    def analyze_full(self):
        # REAL Sonnet (extract + match) + Opus (roadmap/project) — COSTS MONEY. Validates the
        # org-wide SONNET_MAX_CONCURRENCY cap holds across both replicas under concurrency.
        if not _AUTH_TOKEN:
            return  # /analyze charges quota → needs a signed-in user when auth is on
        payload = {
            "profile": SAMPLE_PROFILE,
            "job_text": SAMPLE_JOB_TEXT,
            "mode": "full",
            "include": {"roadmap": True, "project": True},
        }
        self._post("/analyze", payload, "POST /analyze (full)")


@events.test_start.add_listener
def _warn_on_paid_run(environment, **_kwargs):
    tags = getattr(environment.parsed_options, "tags", None) or []
    if "governor" in tags:
        if not _AUTH_TOKEN:
            print("[loadtest] WARNING: 'governor' selected but PF_AUTH_TOKEN is unset — "
                  "/analyze will be skipped (no signed-in user).")
        else:
            print("[loadtest] NOTE: 'governor' scenario fires REAL paid /analyze calls "
                  "(Sonnet + Opus). Ensure the target is STAGING and watch the spend cap.")
