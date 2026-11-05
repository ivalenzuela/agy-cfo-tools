#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Portable Auto-Agents Finance Workspace Provisioner for Antigravity IDE.
Automatically provisions `.agents/skills.json` and `.agents/rules/AGENTS.md`
for CFO, Finance, Accounting, ERP, and BI workspaces.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent


def provision_workspace(workspace_dir: Path) -> bool:
    if not workspace_dir.is_dir():
        return False
    agents_dir = workspace_dir / ".agents"
    skills_json = agents_dir / "skills.json"
    if skills_json.is_file():
        return False

    agents_dir.mkdir(parents=True, exist_ok=True)
    rules_dir = agents_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    default_skills = {
        "entries": [
            {"path": "skills"},
            {
                "path": "~/.gemini/config/plugins/agy-cfo-tools/skills",
                "include_only": [
                    "skill-finder",
                    "xlsx",
                    "gsheets",
                    "startup-financial-modeling",
                    "billing-automation",
                    "latam-fintech-payments-invoicing",
                ],
            },
        ]
    }
    skills_json.write_text(json.dumps(default_skills, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    src_rules = PLUGIN_ROOT / "rules"
    if src_rules.is_dir():
        for fn in ("AGENTS.md", "domain_standards.md", "security_guidelines.md"):
            sp = src_rules / fn
            if sp.is_file():
                shutil.copy2(sp, rules_dir / fn)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AGY CFO Tools Workspace Provisioner")
    parser.add_argument("--workspace", help="Target workspace path to provision")
    parser.add_argument("--self-test", action="store_true", help="Verify config.json and exit 0")
    args = parser.parse_args(argv)

    if args.self_test:
        cfg_ok = (HERE / "config.json").is_file()
        print(json.dumps({"ok": cfg_ok, "watcher": str(HERE / "auto_agents_watcher.py")}))
        return 0 if cfg_ok else 1

    if args.workspace:
        ws = Path(args.workspace).expanduser().resolve()
        created = provision_workspace(ws)
        print(json.dumps({"ok": True, "workspace": str(ws), "provisioned": created}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
