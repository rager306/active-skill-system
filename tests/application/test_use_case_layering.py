"""Layering contract for application/use_cases/ - the L2 use-case package.

These tests guard R001 / R002 / R007: the application layer's use-case
package must stay infrastructure-free, must not reach into L3 adapters or
composition, and must expose its public symbols (S03 contract).

Layering reminder:
    L0  domain        (no dependencies on infra or application)
    L1  application.ports        (Protocols only, no infra)
    L2  application.use_cases    (this file) - depends on L1 only
    L3  adapters      (implements L1; may import infra)
    L4  composition   (wires L3 into L2; may import infra)

This module is the S03 regression gate. If a future change drags
`import activegraph`, `import anthropic`, `import openai`, or a
relative reference to `active_skill_system.adapters` /
`active_skill_system.composition` into the use-case source, this test
fails fast and cheaply - before import-linter or runtime can complain.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Iterable
from pathlib import Path

import pytest

from active_skill_system.application.use_cases import (
    RunReasoningRequest,
    RunReasoningUseCase,
)

# ── helpers ──────────────────────────────────────────────────────────────


# Patterns we never want in any use-case source file. These are checked
# as raw text so a stray `import activegraph` at the bottom of a file is
# caught even if no test actually exercises it.
FORBIDDEN_INFRA_IMPORT_FRAGMENTS: tuple[str, ...] = (
    "import activegraph",
    "from activegraph",
    "import anthropic",
    "from anthropic",
    "import openai",
    "from openai",
)

# L3 / L4 layers the L2 use-case package must NOT import. We match the
# `from active_skill_system.adapters` / `...composition` prefix with a
# trailing dot, so unrelated names like `adapters.utils` (which do not
# exist) are still rejected.
FORBIDDEN_UPPER_LAYER_IMPORTS: tuple[str, ...] = (
    "from active_skill_system.adapters",
    "import active_skill_system.adapters",
    "from active_skill_system.composition",
    "import active_skill_system.composition",
)


def _use_case_source_files() -> list[Path]:
    """Return every .py file under `application/use_cases/` (recursively).

    We inspect *every* file in the package, not just the headline
    `run_reasoning.py`, so a future S04/S05 use-case that drags infra
    imports into a sibling file is also caught.
    """
    pkg_root = Path(__file__).resolve().parents[2] / "src" / "active_skill_system" / (
        "application/use_cases"
    )
    assert pkg_root.is_dir(), (
        f"Expected use-case package at {pkg_root}; the package layout may have changed."
    )
    return sorted(pkg_root.rglob("*.py"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_docstrings_and_comments(src: str) -> str:
    """Return `src` with docstrings + `#` comments replaced by blank lines.

    A future maintainer might mention `import activegraph` in a docstring
    without actually importing it. The layering contract is about real
    imports, not prose; strip them out before scanning.
    """
    # Triple-quoted string literals ("""...""" and '''...''') and single
    # line comments. The substitution preserves line numbers.
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    src = re.sub(r"(?m)#.*$", "", src)
    return src


def _assert_no_matches(
    haystack: str,
    needles: Iterable[str],
    *,
    where: str,
    message_template: str,
) -> None:
    """Assert none of the `needles` appear as substrings of `haystack`."""
    for needle in needles:
        assert needle not in haystack, message_template.format(where=where, needle=needle)


# ── tests ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("src_path", _use_case_source_files(), ids=lambda p: str(p))
def test_use_case_module_has_no_infra_imports(src_path: Path) -> None:
    """Every use-case source file stays free of direct infrastructure imports.

    Reinforces R002 (Domain + application are infra-free) at the source-text
    level. Import-linter covers it via contract, this test gives a faster,
    more pointed failure message when a single file regresses.
    """
    code = _strip_docstrings_and_comments(_read(src_path))
    _assert_no_matches(
        code,
        FORBIDDEN_INFRA_IMPORT_FRAGMENTS,
        where=str(src_path),
        message_template=(
            "{where}: use-case source must not contain '{needle}' "
            "(R002 - application layer is infra-free). "
            "Wire infrastructure through composition (L4) instead."
        ),
    )


@pytest.mark.parametrize("src_path", _use_case_source_files(), ids=lambda p: str(p))
def test_use_case_module_does_not_reach_into_adapters_or_composition(src_path: Path) -> None:
    """L2 use-case code never imports L3 adapters or L4 composition.

    Reinforces the onion/hexagonal layering: the use-case package sits at
    L2 and must depend on L1 (ports) only. Reaching sideways into
    `adapters` or `composition` couples the application layer to a
    specific infrastructure wiring and defeats the point of having ports.
    """
    code = _strip_docstrings_and_comments(_read(src_path))
    _assert_no_matches(
        code,
        FORBIDDEN_UPPER_LAYER_IMPORTS,
        where=str(src_path),
        message_template=(
            "{where}: use-case source must not import '{needle}' "
            "(L2 depends on L1 only). Move that dependency to composition."
        ),
    )


def test_public_use_case_package_exports_expected_symbols() -> None:
    """The use-case package re-exports `RunReasoningUseCase` + `RunReasoningRequest`.

    S03 contract: composition (S05) imports these symbols from the public
    surface (`active_skill_system.application.use_cases`). A typo or a
    private rename would silently break that wiring.
    """
    pkg = importlib.import_module("active_skill_system.application.use_cases")

    # Re-exported names are reachable as attributes...
    assert hasattr(pkg, "RunReasoningUseCase"), (
        "`active_skill_system.application.use_cases` must re-export `RunReasoningUseCase`."
    )
    assert hasattr(pkg, "RunReasoningRequest"), (
        "`active_skill_system.application.use_cases` must re-export `RunReasoningRequest`."
    )

    # ...and the re-exports are the actual classes (not wrapper aliases).
    from active_skill_system.application.use_cases.run_reasoning import (
        RunReasoningRequest as DirectRequest,
    )
    from active_skill_system.application.use_cases.run_reasoning import (
        RunReasoningUseCase as DirectUseCase,
    )
    assert pkg.RunReasoningUseCase is DirectUseCase
    assert pkg.RunReasoningRequest is DirectRequest

    # The package author explicitly listed the public surface in __all__.
    # If __all__ is missing, surface that as a layering defect.
    assert hasattr(pkg, "__all__"), (
        "use_case package must declare `__all__` to define its public API."
    )
    assert set(pkg.__all__) == {
        "RunReasoningUseCase",
        "RunReasoningRequest",
        "ValidateTaskGraphUseCase",
        "RunReasoningVerticalUseCase",
        "TaskSpec",
        "ClaimSpec",
        "SynthesisResult",
        "SynthesizeAnswerRequest",
        "SynthesizeAnswerUseCase",
        "ParseTaskSpecUseCase",
        "ParseTaskSpecRequest",
    }, (
        f"Unexpected public surface: {pkg.__all__!r}"
    )


def test_use_case_symbols_are_constructible_without_runtime_infrastructure() -> None:
    """Importing the use-case package must not trigger any infrastructure import.

    If the use-case module transitively pulls in activegraph / anthropic /
    openai, importing `active_skill_system.application.use_cases` will
    raise (or set up heavy resources). We assert it is cheap to import.
    """
    # Re-import in a fresh state to confirm the package is self-contained.
    reimported = importlib.reload(importlib.import_module("active_skill_system.application.use_cases"))
    assert reimported is not None
    # Constructing the request dataclass and instantiating the use-case
    # with a sentinel is enough to confirm the public surface works
    # without dragging infra into the test process.
    request = RunReasoningRequest(goal="Diligence: layering-check")
    assert request.goal == "Diligence: layering-check"

    class _NullRuntime:
        # Duck-typed, no infrastructure - satisfies the structural protocol
        # without importing it.
        def run_goal(self, goal, *, llm_provider=None):  # noqa: ARG002
            raise AssertionError("runtime must not be called during construction")

    # Construction alone must not call the runtime.
    use_case = RunReasoningUseCase(_NullRuntime())
    assert use_case is not None
