#!/usr/bin/env python3
"""
Skill-Finder CLI entrypoint (`skills/skill-finder/scripts/find_skills.py`).
Delegates to `scripts/find_template_skill.py` (or local `find_template_skill.py`)
to search the curated CFO & Finance skills in `CATALOG.json` (<10ms) and emit
Zero-Copy `.agents/skills.json` (`include_only`) snippets.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
CANDIDATE_DIRS = [
    HERE,
    HERE.parent.parent.parent / "scripts",
    Path.home() / ".gemini" / "config" / "plugins" / "agy-cfo-tools" / "scripts",
]
for d in CANDIDATE_DIRS:
    if d.is_dir() and str(d) not in sys.path:
        sys.path.insert(0, str(d))

from find_template_skill import (  # noqa: E402
    DEFAULT_CATALOG,
    QUERY_ALIASES,
    build_skills_json_snippet,
    expand_keywords,
    main,
    score_entry,
)

__all__ = [
    "DEFAULT_CATALOG",
    "QUERY_ALIASES",
    "build_skills_json_snippet",
    "expand_keywords",
    "main",
    "score_entry",
]

if __name__ == "__main__":
    raise SystemExit(main())
