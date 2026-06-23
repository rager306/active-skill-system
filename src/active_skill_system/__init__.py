"""active_skill_system — onion/hexagonal package built on ActiveGraph.

Layers (dependency direction: inward):
  domain        (L1) pure Active Skill System
  application   (L2) Cognitive Runtime control + ports
  adapters      (L3) infrastructure adapters (activegraph, MiniMax, ...)
  composition   (L4) driving adapters / composition roots

Enforced by import-linter (see pyproject.toml [tool.importlinter]).
See doc/architecture.md for the full specification.
"""
