# ruvector

Container format for AI agent knowledge graphs.

This is a **Python stub** for the future Rust + PyO3 implementation. The pure-Python fallback
provides the same `RuVectorContainer` API so the active-skill-system can develop and test
without requiring the Rust toolchain. The real Rust implementation will replace this stub
in a future milestone.

## Installation

```bash
# Pure-Python (current):
pip install -e ruvector/

# PyO3 (future, requires Rust toolchain):
pip install -e ruvector/[pyo3]
```

## Usage

```python
from ruvector import RuVectorContainer, __version__

container = RuVectorContainer(path="/tmp/mygraph")
container.add_event(event_id="e1", event_type="thought", payload={"text": "hello"})
events = container.query(event_type="thought")
```

## Architecture

- `ruvector/Container.py` — `RuVectorContainer` class (event-sourced container).
- `ruvector/__init__.py` — public exports.

## License

Apache-2.0.
