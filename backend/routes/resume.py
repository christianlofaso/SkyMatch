import io
import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile

from cache import get_profile_cache, set_profile_cache, text_cache_key
from lib.cost import cost_session
from routes.profile import analyze_profile, extract_rich_fields
from schemas import RunRequest, UnifiedProfile

router = APIRouter()

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_ALLOWED_EXTENSIONS = {".pdf", ".docx"}


def _extract_text_pdf(data: bytes) -> str:
    import pdfplumber
    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def _extract_text_docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


@router.post("/profile/from-resume")
async def from_resume(file: UploadFile = File(...)) -> dict:
    # --- Validate file type ---
    filename = file.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Only PDF and DOCX files are accepted.")

    # --- Read + size check ---
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=422, detail="File exceeds the 5 MB limit.")

    # --- Check cache before any parsing ---
    cache_key = text_cache_key(data.hex()[:500])
    cached = await asyncio.to_thread(get_profile_cache, cache_key)
    if cached:
        return {"profile_id": cache_key, "profile": cached}

    # --- Extract text ---
    try:
        if ext == ".pdf":
            resume_text = await asyncio.to_thread(_extract_text_pdf, data)
        else:
            resume_text = await asyncio.to_thread(_extract_text_docx, data)
    except Exception as e:
        print(f"[profile/from-resume] text extraction failed for {filename!r}: {e!r}")
        raise HTTPException(status_code=422, detail="Couldn't read that file — it may be corrupt or password-protected. Try re-exporting it as a PDF.")

    if not resume_text.strip():
        raise HTTPException(status_code=422, detail="That file looks empty or image-only — we couldn't find any text to read. Try a text-based PDF or DOCX.")

    print(f"[profile/from-resume] extracted {len(resume_text)} chars from {filename!r}")
    truncated = resume_text[:12000]

    # --- Run ProfileAnalysis + rich extraction in parallel ---
    base_req = RunRequest(text=truncated)
    try:
        with cost_session("/profile/from-resume"):
            base_profile, rich_data = await asyncio.gather(
                analyze_profile(base_req),
                extract_rich_fields(truncated),
            )
    except HTTPException:
        raise  # friendly mapped error — pass through
    except Exception as e:
        print(f"[profile/from-resume] profile extraction failed: {e!r}")
        raise HTTPException(status_code=500, detail="Couldn't build a profile from that resume. Please try again.")

    # --- Merge into UnifiedProfile ---
    profile = UnifiedProfile(
        **base_profile.model_dump(),
        sources=["resume"],
        skills_with_context=rich_data.get("skills_with_context", []),
        education=rich_data.get("education", []),
        work_experience=rich_data.get("work_experience", []),
        projects=rich_data.get("projects", []),
        certifications=rich_data.get("certifications", []),
    )

    await asyncio.to_thread(set_profile_cache, cache_key, profile.model_dump())
    return {"profile_id": cache_key, "profile": profile.model_dump()}
