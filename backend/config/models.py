"""Central model-ID constants for Anthropic calls.

All call sites import from here so a model upgrade is a one-line change.
This pass migrates only routes/analyze.py; other routes still use inline
strings and will be migrated in a follow-up.
"""

MODEL_FULL = "claude-opus-4-8"
# Mid tier — Sonnet. Used for listing-annotation/selection tasks (pick the best of N
# already-scraped real listings + write fit_explanations) where Opus latency (~25s/call)
# isn't justified by the reasoning depth. See routes/internships.py stage-2 Claude calls.
MODEL_MID = "claude-sonnet-4-6"
MODEL_QUICK = "claude-haiku-4-5"
