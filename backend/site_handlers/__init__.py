from .base import JobPosting, SiteHandler, dispatch, register
from . import microsoft  # noqa: F401 — import-for-side-effect: registers MicrosoftHandler

__all__ = ["JobPosting", "SiteHandler", "dispatch", "register"]
