#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGY CFO & Finance Cockpit — Antigravity 2.0 Auxiliary Pane Sidecar Server.

Zero external web framework required (stdlib `http.server.ThreadingHTTPServer`).
Binds strictly to `127.0.0.1` on `int(os.environ.get("ANTIGRAVITY_SIDECAR_WEB_PORT", "8496"))`.
Provides:
  - `/health`: Sidecar health check
  - `/api/catalog`: Full JSON catalog of all 87 CFO & Finance skills
  - `/api/search?q=...`: Fast (<5ms) Skill-Finder query + `.agents/skills.json` snippet
  - `/`: Interactive CFO Cockpit UI (Skill Finder + Unit Economics / DCF / Tax Mod-11 Calculators)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
UI_ROOT = HERE / "ui"
CANDIDATE_CATALOGS = [
    HERE.parent.parent / "CATALOG.json",
    Path.home() / ".gemini" / "config" / "plugins" / "agy-cfo-tools" / "CATALOG.json",
    Path.home() / ".gemini" / "config" / "skills" / "skill-finder" / "CATALOG.json",
]


def load_catalog() -> list[dict]:
    for cand in CANDIDATE_CATALOGS:
        if cand.is_file():
            try:
                return json.loads(cand.read_text(encoding="utf-8"))
            except Exception:
                pass
    return []


class CfoCockpitServer(ThreadingHTTPServer):
    daemon_threads = True


class CfoCockpitHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _send_json(self, status_code: int, payload: dict | list) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/health":
            catalog = load_catalog()
            self._send_json(
                200,
                {
                    "ok": True,
                    "sidecar": "agy-cfo-cockpit",
                    "skillsCount": len(catalog),
                },
            )
            return

        if path == "/api/catalog":
            catalog = load_catalog()
            self._send_json(200, {"ok": True, "total": len(catalog), "skills": catalog})
            return

        if path == "/api/search":
            qs = urllib.parse.parse_qs(parsed.query)
            q = (qs.get("q", [""])[0] or "").strip().lower()
            cat_filter = (qs.get("category", [""])[0] or "").strip().lower()
            catalog = load_catalog()
            tokens = [t for t in q.split() if t]
            results = []
            for item in catalog:
                if cat_filter and item.get("category", "").lower() != cat_filter:
                    continue
                if not tokens:
                    results.append(item)
                    continue
                hay = f"{item.get('name','')} {item.get('category','')} {item.get('subcategory','')} {item.get('description','')}".lower()
                if all(t in hay for t in tokens):
                    results.append(item)
            snippet = {
                "entries": [
                    {"path": "skills"},
                    {
                        "path": "~/.gemini/config/plugins/agy-cfo-tools/skills",
                        "include_only": [r["name"] for r in results[:6]],
                    },
                ]
            }
            self._send_json(
                200,
                {
                    "ok": True,
                    "query": q,
                    "total": len(results),
                    "results": results[:25],
                    "skills_json": snippet,
                },
            )
            return

        index_file = UI_ROOT / "index.html"
        if index_file.is_file():
            data = index_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(404, "UI asset not found")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AGY CFO & Finance Cockpit Sidecar")
    parser.add_argument("--host", default=os.environ.get("ANTIGRAVITY_SIDECAR_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ANTIGRAVITY_SIDECAR_WEB_PORT", "8496")))
    parser.add_argument("--self-test", action="store_true", help="Verify UI and catalog and exit 0")
    args, _ = parser.parse_known_args(argv)

    if args.self_test:
        cat = load_catalog()
        ok = (UI_ROOT / "index.html").is_file() and len(cat) >= 80
        print(json.dumps({"ok": ok, "skillsCount": len(cat), "uiExists": (UI_ROOT / "index.html").is_file()}))
        return 0 if ok else 1

    server = CfoCockpitServer((args.host, args.port), CfoCockpitHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
