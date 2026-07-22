"""Puts this component's directory (one level up from tests/) on sys.path
so `import secret_store` resolves to the co-located drop-in module — this
component is a standalone single-file drop-in with no package/__init__.py,
matching how a scaffolded project consumes it (a bare file copied into
app/core/security/). Named `secret_store.py`, not `secrets.py`, precisely
so it never shadows the stdlib `secrets` module once this directory is on
sys.path.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
