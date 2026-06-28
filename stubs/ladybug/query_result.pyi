"""Minimal type stub for LadybugDB QueryResult.

LadybugDB has no type stubs, so pyrefly/ty cannot resolve QueryResult.has_next()
and QueryResult.get_next(). This stub provides the minimal surface we use.
"""


class QueryResult:
    """LadybugDB Cypher query result iterator."""

    def has_next(self) -> bool: ...
    def get_next(self) -> tuple: ...
