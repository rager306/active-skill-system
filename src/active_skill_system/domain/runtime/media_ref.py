"""L1 Domain - MediaRef value-object (M008).

A typed reference to a media resource (image, future: video) that an
Evidence-узел can carry. Anti-fancy invariant: the domain stays text-only
for reasoning; ``MediaRef`` is a URL anchor, NOT the media bytes. Vision
extraction lives in the application layer and projects media to structured
text facts before they enter the domain.

Pure domain. NO I/O, NO infrastructure imports (R002). Frozen dataclass
with ``__post_init__`` validation. stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass

# Whitelisted media types for the project (M008+). Vision is the current
# surface; video will be added in M008+ when the gateway path stabilises.
ALLOWED_MEDIA_TYPES: frozenset[str] = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)

# Allowed URL schemes. We only accept http(s) here because the vision path
# (M007 verified) needs a real fetchable URL.
_ALLOWED_URL_SCHEMES: frozenset[str] = frozenset({"http", "https"})


def _validate_url(url: str) -> None:
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"MediaRef.url must be a non-empty string (got {url!r})")
    lowered = url.lower()
    if not any(
        lowered.startswith(f"{scheme}://") for scheme in _ALLOWED_URL_SCHEMES
    ):
        raise ValueError(
            f"MediaRef.url must start with http:// or https:// (got {url!r})"
        )


def _validate_media_type(media_type: str) -> None:
    if not isinstance(media_type, str) or not media_type.strip():
        raise ValueError(
            f"MediaRef.media_type must be a non-empty string (got {media_type!r})"
        )
    if media_type not in ALLOWED_MEDIA_TYPES:
        raise ValueError(
            f"MediaRef.media_type must be one of {sorted(ALLOWED_MEDIA_TYPES)} "
            f"(got {media_type!r})"
        )


@dataclass(frozen=True)
class MediaRef:
    """A typed reference to a media resource (URL + media_type).

    ``url`` is a fetchable HTTP(S) URL. ``media_type`` is one of
    ``ALLOWED_MEDIA_TYPES`` (whitelisted to keep the surface small until
    the vision path is stable).

    Carries NO bytes, NO content. The reasoning domain treats this as an
    anchor for grounding; the actual media fetch + extraction lives in
    application-layer use-cases (see ``application/use_cases/extract_facts.py``).
    """

    url: str
    media_type: str

    def __post_init__(self) -> None:
        _validate_url(self.url)
        _validate_media_type(self.media_type)
