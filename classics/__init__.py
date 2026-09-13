"""open-classics-api — a dependency-free open API for classical Chinese literature.

The package is intentionally small: a single in-memory store that loads a JSON
corpus and answers search / filter / aggregate queries.

Design goals
------------
1. Zero third-party dependencies. The whole service runs on the Python standard
   library, so anyone can clone the repo and run it with a bare `python app.py`.
2. Deterministic ranking. Relevance is computed with explicit, readable weights
   rather than an opaque scoring library, so the behaviour can be reviewed and
   argued about in a pull request.
3. Boring on purpose. No database, no cache layer, no background workers. The
   corpus fits in memory many times over, and simple code is easier to audit.
"""

from .store import ClassicsStore, DEFAULT_DATA_PATH, __version__

__all__ = ["ClassicsStore", "DEFAULT_DATA_PATH", "__version__"]
