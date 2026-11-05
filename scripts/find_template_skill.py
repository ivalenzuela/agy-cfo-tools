#!/usr/bin/env python3
"""
Fast (<10ms) JIT Skill Search CLI for AGY CFO Tools (CATALOG.json).
Searches all bundled Finance, CFO, Accounting, ERP, FinTech, and BI skills
(with automatic fallback to global catalogs if present) and outputs a
ready-to-paste Antigravity 2.0 `.agents/skills.json` snippet with `include_only`.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

sys.dont_write_bytecode = True

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
CANDIDATE_CATALOGS = [
    HERE.parent / "CATALOG.json",
    Path.home() / ".gemini" / "config" / "plugins" / "agy-cfo-tools" / "CATALOG.json",
    Path.home() / ".gemini" / "config" / "skills" / "skill-finder" / "CATALOG.json",
]

QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "cfo": ("financial", "modeling", "xlsx", "billing", "kpi", "risk-manager", "cro-advisor"),
    "finanzas": ("financial", "billing", "xlsx", "gsheets", "payment", "latam-fintech-payments-invoicing"),
    "contabilidad": ("accounting", "odoo-accounting-setup", "odoo-l10n-compliance", "xlsx"),
    "excel": ("xlsx", "xlsx-official", "calc", "bilig-workpaper"),
    "sheets": ("gsheets", "googlesheets-automation", "xlsx"),
    "sifen": ("latam-fintech-payments-invoicing", "odoo-l10n-compliance"),
    "bancard": ("latam-fintech-payments-invoicing", "payment-integration"),
    "impuestos": ("tax", "latam-fintech-payments-invoicing", "odoo-l10n-compliance", "billing-automation"),
    "tax": ("latam-fintech-payments-invoicing", "odoo-l10n-compliance", "billing-automation"),
    "erp": ("odoo-accounting-setup", "odoo-l10n-compliance", "odoo-purchase-workflow"),
    "bi": ("boletos-executive-bi-anomaly-narrator", "kpi-dashboard-design", "claude-d3js-skill"),
    "d3": ("d3js", "claude-d3js-skill"),
    "d3.js": ("d3js", "claude-d3js-skill"),
    "chart": ("charts", "claude-d3js-skill", "kpi-dashboard-design"),
    "charts": ("chart", "claude-d3js-skill", "kpi-dashboard-design"),
    "graficos": ("chart", "claude-d3js-skill", "kpi-dashboard-design"),
    "pdf": ("latex-document-skill",),
    "latex": ("latex-document-skill",),
}


def resolve_default_catalog() -> str:
    env_cat = os.environ.get("AGY_SKILL_CATALOG")
    if env_cat and os.path.isfile(env_cat):
        return env_cat
    for cand in CANDIDATE_CATALOGS:
        if cand.is_file():
            return str(cand)
    return str(CANDIDATE_CATALOGS[0])


DEFAULT_CATALOG = resolve_default_catalog()


def expand_keywords(raw_tokens: list[str]) -> list[str]:
    expanded: list[str] = []
    for tok in raw_tokens:
        low = tok.strip().lower()
        if not low:
            continue
        if low not in expanded:
            expanded.append(low)
        for alias in QUERY_ALIASES.get(low, ()):
            if alias not in expanded:
                expanded.append(alias)
    return expanded


def score_entry(entry: dict[str, Any], tokens: list[str], full_query: str) -> int:
    name = entry.get("name", "").lower()
    cat = entry.get("category", "").lower()
    desc = entry.get("description", "").lower()

    if not tokens:
        return 1

    expanded_tokens = expand_keywords(tokens)
    score = 0
    if name == full_query:
        score += 200
    elif full_query in name:
        score += 100

    matched_tokens = 0
    segments = [s for s in name.split("-") if s]
    for tok in expanded_tokens:
        tok_hit = False
        if tok == name:
            score += 120
            tok_hit = True
        elif name.startswith(tok + "-") or name.endswith("-" + tok):
            score += 75
            tok_hit = True
        elif tok in segments:
            score += 55
            tok_hit = True
        elif tok in name:
            score += 35
            tok_hit = True

        if tok == cat or tok in cat.split("_"):
            score += 25
            tok_hit = True

        if tok in desc:
            score += 12
            tok_hit = True

        if tok_hit:
            matched_tokens += 1

    if matched_tokens == 0:
        return 0
    if matched_tokens >= len(tokens) and len(tokens) > 1:
        score += 45
    score -= min(len(segments) * 2, 16)
    return max(score, 1)


def build_skills_json_snippet(results: list[dict[str, Any]], max_skills: int = 6) -> dict[str, Any]:
    names = sorted(dict.fromkeys(item["name"] for item in results[:max_skills]))
    entries: list[dict[str, Any]] = [
        {"path": "skills"},
        {
            "path": "~/.gemini/config/plugins/agy-cfo-tools/skills",
            "include_only": names,
        },
    ]
    return {"entries": entries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search AGY CFO Tools CATALOG.json and generate .agents/skills.json include_only snippets."
    )
    parser.add_argument("keywords", nargs="*", help="Search keywords (e.g. cfo billing sifen xlsx odoo bi)")
    parser.add_argument("-c", "--category", help="Filter by exact category (e.g. business_finance, databases, design_ux)")
    parser.add_argument("-n", "--limit", "--top", dest="limit", type=int, default=8, help="Max results to display (default: 8)")
    parser.add_argument("--catalog", default=DEFAULT_CATALOG, help="Path to CATALOG.json")
    parser.add_argument("--json", action="store_true", help="Output raw JSON results + snippet")
    args = parser.parse_args(argv)

    t0 = time.perf_counter()
    if not os.path.isfile(args.catalog):
        print(f"[ERROR] Catalog not found at {args.catalog}", file=sys.stderr)
        return 1

    with open(args.catalog, "r", encoding="utf-8") as f:
        catalog: list[dict[str, Any]] = json.load(f)

    cat_filter = args.category.strip().lower() if args.category else None
    raw_tokens = [t.strip().lower() for kw in args.keywords for t in kw.split() if t.strip()]
    full_query = "-".join(raw_tokens)

    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in catalog:
        if cat_filter and entry.get("category", "").lower() != cat_filter:
            continue
        sc = score_entry(entry, raw_tokens, full_query)
        if sc > 0:
            scored.append((sc, entry))

    scored.sort(
        key=lambda x: (
            -x[0],
            -len(x[1].get("description", "")),
            x[1].get("category", ""),
            x[1].get("name", ""),
        )
    )
    top_entries: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for _, entry in scored:
        ename = str(entry.get("name", "")).lower().strip()
        if not cat_filter and ename in seen_names:
            continue
        seen_names.add(ename)
        top_entries.append(entry)
        if len(top_entries) >= args.limit:
            break

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    snippet = build_skills_json_snippet(top_entries, max_skills=min(args.limit, 6))

    if args.json:
        print(
            json.dumps(
                {
                    "elapsed_ms": round(elapsed_ms, 2),
                    "total_matches": len(scored),
                    "results": top_entries,
                    "skills_json": snippet,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(f"[OK] Found {len(scored)} matching CFO/Finance skills in {elapsed_ms:.2f}ms (showing top {len(top_entries)}):")
    if not top_entries:
        return 0

    for idx, item in enumerate(top_entries, 1):
        desc = item.get("description", "")
        if len(desc) > 110:
            desc = desc[:107] + "..."
        print(f"  {idx}. [{item['category']}/{item['name']}] {desc}")
        print(f"     Path: {item['path']}")

    print("\n--- Ready-to-paste .agents/skills.json ---")
    print(json.dumps(snippet, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
