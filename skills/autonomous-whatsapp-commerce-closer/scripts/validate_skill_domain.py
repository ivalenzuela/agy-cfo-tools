# -*- coding: utf-8 -*-
r"""
Deterministic static & functional validator for `autonomous-whatsapp-commerce-closer`.

Verifies:
  1. Canonical 5-directory layout (`SKILL.md`, `references/architecture-and-patterns.md`,
     `resources/config-template.json`, `examples/reference_implementation.py`,
     `scripts/validate_skill_domain.py`).
  2. YAML frontmatter validity & third-person `description` length between 120 and 440 chars.
  3. Presence of `# Core Implementation & Verification Checklist` and all 11 MCP tool names in `SKILL.md`.
  4. Relative markdown link integrity inside `SKILL.md`.
  5. Execution of all 10 unit and edge-case tests in `examples/reference_implementation.py`.

Run with:
  python scripts/validate_skill_domain.py
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import importlib.util
import json
import os
import re

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

EXPECTED_11_TOOLS = (
    "get_allowed_operators",
    "resolve_station",
    "search_bus_trips",
    "get_seat_map",
    "hold_seats",
    "release_seats",
    "create_payment_link_and_notify_whatsapp",
    "check_payment_status",
    "emit_tickets",
    "send_ticket_to_whatsapp",
    "rollback_payment",
)


def parse_frontmatter(content: str) -> tuple[str, str, str]:
    m = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", content, re.DOTALL)
    if not m:
        return "", "", content
    fm = m.group(1)
    body = content[m.end() :]

    name_m = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
    name = name_m.group(1).strip().strip("\"'") if name_m else ""

    desc = ""
    lines = fm.splitlines()
    for i, line in enumerate(lines):
        dm = re.match(r"^description:\s*(.*)$", line)
        if dm:
            first = dm.group(1).strip()
            if first in (">-", ">", "|", "|-"):
                collected = []
                for sub in lines[i + 1 :]:
                    if re.match(r"^[a-zA-Z0-9_-]+:\s*", sub):
                        break
                    collected.append(sub.strip())
                desc = " ".join(c for c in collected if c)
            else:
                desc = first.strip("\"'")
            break
    return name, desc.strip(), body


def check_skill_md(skill_md_path: str) -> list[str]:
    errors: list[str] = []
    with open(skill_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    name, desc, body = parse_frontmatter(content)
    if name != "autonomous-whatsapp-commerce-closer":
        errors.append(f"SKILL.md name must be 'autonomous-whatsapp-commerce-closer', got {name!r}")

    if not (120 <= len(desc) <= 440):
        errors.append(f"SKILL.md description length must be between 120 and 440 chars, got {len(desc)}")

    if "# Core Implementation & Verification Checklist" not in body:
        errors.append("SKILL.md must include '# Core Implementation & Verification Checklist'")

    for tool_name in EXPECTED_11_TOOLS:
        if tool_name not in body:
            errors.append(f"SKILL.md is missing MCP tool reference: {tool_name}")

    for match in re.finditer(r"\]\((\./[^)#]+)\)", body):
        rel_target = match.group(1)
        abs_target = os.path.normpath(os.path.join(SKILL_ROOT, rel_target))
        if not os.path.exists(abs_target):
            errors.append(f"Broken relative link in SKILL.md: {rel_target} -> {abs_target}")

    return errors


def validate() -> int:
    required_files = [
        os.path.join(SKILL_ROOT, "SKILL.md"),
        os.path.join(SKILL_ROOT, "references", "architecture-and-patterns.md"),
        os.path.join(SKILL_ROOT, "resources", "config-template.json"),
        os.path.join(SKILL_ROOT, "examples", "reference_implementation.py"),
        os.path.join(SKILL_ROOT, "scripts", "validate_skill_domain.py"),
    ]
    missing = [p for p in required_files if not os.path.isfile(p)]
    if missing:
        print(f"[FAIL] Missing required skill files: {missing}")
        return 1

    md_errors = check_skill_md(os.path.join(SKILL_ROOT, "SKILL.md"))
    if md_errors:
        for err in md_errors:
            print(f"[FAIL] {err}")
        return 1

    with open(os.path.join(SKILL_ROOT, "resources", "config-template.json"), "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if set(cfg.get("mcp_tools_contract", [])) != set(EXPECTED_11_TOOLS):
        print("[FAIL] config-template.json mcp_tools_contract does not match the 11 boletos-la-ventas-mcp tools")
        return 1

    if cfg.get("seat_hold_policy", {}).get("ttl_seconds") != 600:
        print("[FAIL] config-template.json seat_hold_policy.ttl_seconds must be 600")
        return 1

    op_policy = cfg.get("operator_policy", {})
    if not op_policy.get("strict_exclude_nsa") or not op_policy.get("strict_integrated_allowlist_only"):
        print("[FAIL] config-template.json operator_policy must enable strict_exclude_nsa and strict_integrated_allowlist_only")
        return 1

    expected_allowed = ["La Santaniana", "La Sampedrana", "La Santaniana Internacional"]
    if op_policy.get("allowed_operators") != expected_allowed:
        print(f"[FAIL] config-template.json allowed_operators must strictly equal {expected_allowed} (01_anti_nsa_policy)")
        return 1

    if set(op_policy.get("integrated_operator_codes", {}).keys()) != {"LSN", "LSP", "LSA"}:
        print("[FAIL] config-template.json integrated_operator_codes must strictly equal {'LSN', 'LSP', 'LSA'}")
        return 1

    example_path = os.path.join(SKILL_ROOT, "examples", "reference_implementation.py")
    spec = importlib.util.spec_from_file_location("reference_implementation", example_path)
    if spec is None or spec.loader is None:
        print("[FAIL] Unable to load examples/reference_implementation.py")
        return 1
    mod = importlib.util.module_from_spec(spec)
    sys.modules["reference_implementation"] = mod
    spec.loader.exec_module(mod)
    test_result = mod.run_self_tests()
    if test_result.get("status") != "ok" or test_result.get("tests_passed", 0) < 9:
        print(f"[FAIL] Self-tests failed or < 9 tests passed: {test_result}")
        return 1

    print(
        f"[PASS] autonomous-whatsapp-commerce-closer validated "
        f"({test_result['tests_passed']} tests passed, 11/11 MCP tools verified) at {SKILL_ROOT}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(validate())
