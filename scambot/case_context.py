from __future__ import annotations

from pathlib import Path

from .config import Settings


REPO_ROOT = Path(__file__).resolve().parent.parent


def load_case_context(settings: Settings) -> str:
    """Load static background memory for the case.

    Relative paths are resolved from the repository root so this works the same
    locally, in GitHub Actions, and on Render. CASE_CONTEXT_EXTRA can be used
    for private notes kept in an environment variable/GitHub Secret rather
    than committed to a public repository.
    """

    chunks: list[str] = []

    if settings.case_context_path:
        path = Path(settings.case_context_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                chunks.append(text)
        else:
            print(f"Warning: case context file not found: {path}")

    if settings.case_context_extra.strip():
        chunks.append(
            "# Private extra case notes\n\n"
            + settings.case_context_extra.strip()
        )

    return "\n\n---\n\n".join(chunks).strip()
