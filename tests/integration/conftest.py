"""
Integration tests: these check the real data in data/, the Chroma index, Groq or the SEC website.
They need a local build (see README) and, for some, a GROQ_API_KEY. CI does not run them.

The files here are still script-style (they run checks at import time), so pytest must not
import them. Run each one by hand from the project root, for example:

    python tests/integration/test_indexer.py

Converting them into proper pytest functions with skip guards is future work.
"""

collect_ignore_glob = ["test_*.py"]
