"""Unit tests for MediaRef + TaskNode.media (M008 S01)."""

from __future__ import annotations

import pytest

from active_skill_system.domain.runtime import (
    ALLOWED_MEDIA_TYPES,
    MediaRef,
    NodeKind,
    TaskNode,
    TaskNodeId,
)


# ── MediaRef construction ─────────────────────────────────────────────────


def test_media_ref_constructs_with_valid_inputs() -> None:
    m = MediaRef(url="https://placehold.co/1x1.png", media_type="image/png")
    assert m.url == "https://placehold.co/1x1.png"
    assert m.media_type == "image/png"


@pytest.mark.parametrize("media_type", sorted(ALLOWED_MEDIA_TYPES))
def test_media_ref_accepts_all_whitelisted_media_types(media_type: str) -> None:
    m = MediaRef(url="https://example.com/x", media_type=media_type)
    assert m.media_type == media_type


def test_media_ref_rejects_empty_url() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        MediaRef(url="", media_type="image/png")


def test_media_ref_rejects_whitespace_url() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        MediaRef(url="   ", media_type="image/png")


def test_media_ref_rejects_non_http_url() -> None:
    with pytest.raises(ValueError, match="http:// or https://"):
        MediaRef(url="ftp://example.com/x.png", media_type="image/png")
    with pytest.raises(ValueError, match="http:// or https://"):
        MediaRef(url="data:image/png;base64,xxx", media_type="image/png")
    with pytest.raises(ValueError, match="http:// or https://"):
        MediaRef(url="file:///tmp/x.png", media_type="image/png")


def test_media_ref_rejects_empty_media_type() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        MediaRef(url="https://example.com/x", media_type="")


def test_media_ref_rejects_unsupported_media_type() -> None:
    for bad in ("image/bmp", "image/tiff", "image/svg+xml", "video/mp4", "text/plain"):
        with pytest.raises(ValueError, match="must be one of"):
            MediaRef(url="https://example.com/x", media_type=bad)


# ── TaskNode.media integration ───────────────────────────────────────────


def test_task_node_default_media_is_none() -> None:
    n = TaskNode(id=TaskNodeId("g1"), kind=NodeKind.GOAL, text="G")
    assert n.media is None


def test_task_node_accepts_media_on_evidence() -> None:
    m = MediaRef(url="https://placehold.co/1x1.png", media_type="image/png")
    n = TaskNode(id=TaskNodeId("e1"), kind=NodeKind.EVIDENCE, media=m)
    assert n.media is m


@pytest.mark.parametrize(
    "kind",
    [
        NodeKind.GOAL,
        NodeKind.FACT,
        NodeKind.CONSTRAINT,
        NodeKind.CLAIM,
        NodeKind.HYPOTHESIS,
        NodeKind.MECHANISM,
        NodeKind.DECISION,
        NodeKind.ACTION,
        NodeKind.RESULT,
        NodeKind.GAP,
    ],
)
def test_task_node_rejects_media_on_non_evidence(kind: NodeKind) -> None:
    m = MediaRef(url="https://placehold.co/1x1.png", media_type="image/png")
    with pytest.raises(ValueError, match="only EVIDENCE nodes do"):
        TaskNode(id=TaskNodeId("n1"), kind=kind, text="x", media=m)


def test_task_node_evidence_with_empty_text_still_works_when_media_attached() -> None:
    """Evidence may have empty text (its content is the media)."""
    m = MediaRef(url="https://placehold.co/1x1.png", media_type="image/png")
    n = TaskNode(id=TaskNodeId("e1"), kind=NodeKind.EVIDENCE, media=m)
    assert n.text == ""
    assert n.media is m


# ── R002: domain infra-free ───────────────────────────────────────────────


def test_media_ref_module_is_infra_free() -> None:
    import importlib
    from pathlib import Path

    mod = importlib.import_module("active_skill_system.domain.runtime.media_ref")
    src = Path(mod.__file__).read_text()
    for forbidden in (
        "import activegraph",
        "from activegraph",
        "import anthropic",
        "import openai",
    ):
        assert forbidden not in src, f"media_ref.py must not contain '{forbidden}' (R002)"
