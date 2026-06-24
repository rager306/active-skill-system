"""L3 adapters for the RuntimePort.

This package provides infrastructure-specific implementations of
`active_skill_system.application.ports.runtime.RuntimePort`. Currently the
only adapter is the activegraph-backed one in `activegraph.py`; future
adapters (e.g. an in-memory test fake, a DuckDB-backed deterministic
runtime) can live alongside it.
"""
