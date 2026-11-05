#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Installer for AGY CFO Tools (Plugin, 87 Finance & CFO Skills, Skill-Finder, Sidecar & Rules)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True


def main() -> int:
    print("=" * 72)
    print("  AGY CFO & Finance Suite Installer (Antigravity 2.0)")
    print("=" * 72)

    home = Path.home()
    config_root = home / ".gemini" / "config"
    target_plugin_dir = config_root / "plugins" / "agy-cfo-tools"
    target_skill_finder_dir = config_root / "skills" / "skill-finder"
    target_sidecar_dir = config_root / "sidecars" / "cfo-cockpit"
    source_dir = Path(__file__).resolve().parent

    # 1. Install Plugin bundle
    print(f"\n[1/4] Installing plugin bundle to: {target_plugin_dir}")
    target_plugin_dir.mkdir(parents=True, exist_ok=True)

    for item in ("plugin.json", "CATALOG.json", "INDEX.md", "AGENTS.md", "README.md", "hooks.json", "mcp_config.json"):
        src_file = source_dir / item
        if src_file.is_file():
            shutil.copy2(src_file, target_plugin_dir / item)

    for folder in (".gemini-plugin", "assets", "agents", "rules", "scripts", "skills", "sidecars", "watcher"):
        src_folder = source_dir / folder
        dest_folder = target_plugin_dir / folder
        if src_folder.is_dir():
            if dest_folder.exists():
                shutil.rmtree(dest_folder)
            shutil.copytree(src_folder, dest_folder)
            print(f"  - Installed {folder}/")

    # 2. Install standalone skill-finder in ~/.gemini/config/skills/skill-finder (if not already present or update)
    print(f"\n[2/4] Configuring 'skill-finder' in: {target_skill_finder_dir}")
    target_skill_finder_dir.mkdir(parents=True, exist_ok=True)
    src_sf = source_dir / "skills" / "skill-finder"
    if src_sf.is_dir():
        for item in os.listdir(src_sf):
            s = src_sf / item
            d = target_skill_finder_dir / item
            if s.is_dir():
                if d.exists():
                    shutil.rmtree(d)
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)
        print("  - Installed skill-finder/SKILL.md, CATALOG.json, and scripts/find_skills.py")

    # 3. Install CFO Cockpit Sidecar in ~/.gemini/config/sidecars/cfo-cockpit
    print(f"\n[3/4] Installing 'cfo-cockpit' sidecar to: {target_sidecar_dir}")
    src_sc = source_dir / "sidecars" / "cfo-cockpit"
    if src_sc.is_dir():
        if target_sidecar_dir.exists():
            shutil.rmtree(target_sidecar_dir)
        shutil.copytree(src_sc, target_sidecar_dir)
        # Ensure sidecar.json points to the installed server script
        sidecar_json_path = target_sidecar_dir / "sidecar.json"
        if sidecar_json_path.is_file():
            sc_data = json.loads(sidecar_json_path.read_text(encoding="utf-8"))
            sc_data["args"] = ["-B", str(target_sidecar_dir / "cfo_cockpit_server.py")]
            sidecar_json_path.write_text(json.dumps(sc_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("  - Installed sidecar 'AGY CFO & Finance Cockpit' (Port 8496)")

    # 4. Run deterministic verification suite
    print("\n[4/4] Running deterministic verification checks...")
    validator = source_dir / "scripts" / "validate_repo.py"
    if validator.is_file():
        res = subprocess.run([sys.executable, "-B", str(validator)], capture_output=True, text=True)
        if res.returncode == 0:
            print("  [OK] All plugin, skill-finder, catalog (87 skills), and sidecar checks PASSED!")
        else:
            print(f"  [WARN] Validator output: {res.stdout}\n{res.stderr}")

    print("\n" + "=" * 72)
    print("  INSTALLATION COMPLETE!")
    print("  - Plugin:       ~/.gemini/config/plugins/agy-cfo-tools")
    print("  - Skill Finder: ~/.gemini/config/skills/skill-finder")
    print("  - Sidecar HUD:  ~/.gemini/config/sidecars/cfo-cockpit")
    print("  - Total Skills: 87 curated Finance, CFO, Tax, ERP, BI & Spreadsheet skills")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
