# -*- coding: utf-8 -*-
"""
Deterministic validator and 10-case unit test suite for `boletos-executive-bi-anomaly-narrator`.
Verifies:
1. Canonical 5-directory skill layout (`SKILL.md`, `references/`, `resources/`, `examples/`, `scripts/`).
2. Third-person YAML `description` between 120 and 440 characters, `# Core Implementation & Verification Checklist`,
   and valid relative links.
3. `resources/config-template.json` schema and complete 31+1 `boletos-monitoreo` MCP tools catalog.
4. 10 deterministic edge-case unit tests on `examples/reference_implementation.py`:
   - Case 1: Corporate email authorization gatekeeper (`@boletos.la` / `@wit.la` vs unauthorized domains).
   - Case 2: Zero-NSA exposure firewall (`NSA` and `Nuestra Señora de la Asunción` rejection).
   - Case 3: PYG & CLP currency formatting without decimal corruption on Guaraníes (and wire `.00` stripping).
   - Case 4: Rejection of corrupted fractional cents on PYG/CLP (`150000.45`), negative values, NaN, and booleans.
   - Case 5: Parametric Z-score & Tukey IQR critical drop detection (`CRITICAL` / `DROP`).
   - Case 6: Zero-variance (constant baseline) series handling without `ZeroDivisionError`.
   - Case 7: Bancard vPOS SLA evaluator (`HEALTHY`, `WARNING`, `CRITICAL`, and zero-traffic edge case).
   - Case 8: Totem fleet (`room:totem:<id>`) & AWS Lightsail saturation correlator (`RAM > 85%`, `Disk > 90%`).
   - Case 9: Totems Pullman Costa net settlement math (1.0% Transbank + 2.5% WIT fee).
   - Case 10: `<agent-embed>` HTML dashboard & 2-sentence Chilean executive voice briefing (`wait: False`).

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


def load_reference_module():
    ref_path = os.path.join(SKILL_ROOT, "examples", "reference_implementation.py")
    spec = importlib.util.spec_from_file_location("reference_implementation", ref_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load {ref_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["reference_implementation"] = mod
    spec.loader.exec_module(mod)
    return mod


def validate_layout_and_frontmatter() -> list[str]:
    errors: list[str] = []
    required_files = [
        os.path.join(SKILL_ROOT, "SKILL.md"),
        os.path.join(SKILL_ROOT, "references", "architecture-and-patterns.md"),
        os.path.join(SKILL_ROOT, "resources", "config-template.json"),
        os.path.join(SKILL_ROOT, "examples", "reference_implementation.py"),
        os.path.join(SKILL_ROOT, "scripts", "validate_skill_domain.py"),
    ]
    for path in required_files:
        if not os.path.isfile(path):
            errors.append(f"Missing required file: {path}")
        elif os.path.getsize(path) < 300:
            errors.append(f"File too small (<300 bytes): {path}")

    skill_md = os.path.join(SKILL_ROOT, "SKILL.md")
    if os.path.isfile(skill_md):
        with open(skill_md, "r", encoding="utf-8") as f:
            content = f.read()

        m = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n", content, re.DOTALL)
        if not m:
            errors.append("SKILL.md missing valid YAML frontmatter block")
        else:
            fm = m.group(1)
            if "name: boletos-executive-bi-anomaly-narrator" not in fm:
                errors.append("SKILL.md missing exact 'name: boletos-executive-bi-anomaly-narrator'")

            # Extract description
            lines = fm.splitlines()
            desc_parts: list[str] = []
            for idx, line in enumerate(lines):
                dm = re.match(r"^description:\s*(.*)$", line)
                if dm:
                    first = dm.group(1).strip()
                    if first in (">-", ">", "|", "|-"):
                        for sub in lines[idx + 1 :]:
                            if re.match(r"^[a-zA-Z0-9_-]+:\s*", sub):
                                break
                            desc_parts.append(sub.strip())
                    else:
                        desc_parts.append(first.strip("\"'"))
                    break
            desc = " ".join(p for p in desc_parts if p).strip()
            if not (120 <= len(desc) <= 440):
                errors.append(f"YAML description length must be between 120 and 440 chars, got {len(desc)}")

        if "# Core Implementation & Verification Checklist" not in content:
            errors.append("SKILL.md missing required '# Core Implementation & Verification Checklist' heading")

        for rel in re.findall(r"\]\(\./([^)#]+)", content):
            target = os.path.join(SKILL_ROOT, rel.replace("/", os.sep))
            if not os.path.exists(target):
                errors.append(f"Broken relative link in SKILL.md: ./{rel}")

    return errors


def validate_config_schema() -> list[str]:
    errors: list[str] = []
    cfg_path = os.path.join(SKILL_ROOT, "resources", "config-template.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for section in ("access_policy", "currencies", "anomaly_thresholds", "voice_briefing", "bi_platforms_catalog", "mcp_tools_31"):
            if section not in cfg:
                errors.append(f"config-template.json missing section: {section}")
        if len(cfg.get("bi_platforms_catalog", [])) != 7:
            errors.append("config-template.json must catalog all 7 executive BI platforms")
        if len(cfg.get("mcp_tools_31", [])) < 31:
            errors.append("config-template.json must list at least 31 boletos-monitoreo MCP tools")
        if cfg.get("voice_briefing", {}).get("wait") is not False:
            errors.append("config-template.json voice_briefing.wait must be strictly false")
    except Exception as exc:
        errors.append(f"Failed to parse config-template.json: {exc}")
    return errors


def run_edge_case_unit_tests() -> list[str]:
    errors: list[str] = []
    mod = load_reference_module()

    # Case 1: Corporate email authorization gatekeeper
    if mod.validate_corporate_email("  CEO@Boletos.la ") != "ceo@boletos.la":
        errors.append("Case 1a failed: valid @boletos.la email not normalized")
    if mod.validate_corporate_email("ops@wit.la") != "ops@wit.la":
        errors.append("Case 1b failed: valid @wit.la email rejected")
    for bad_email in ("", "   ", "hacker@gmail.com", "user@boletos.la.evil.com", None, 12345):
        try:
            mod.validate_corporate_email(bad_email)
            errors.append(f"Case 1c failed: unauthorized email {bad_email!r} was not rejected")
        except mod.UnauthorizedCorporateEmailError:
            pass

    # Case 2: Zero-NSA exposure firewall
    mod.assert_no_nsa_exposure({"empresa": "LSN", "nombre": "La Santaniana"})
    for forbidden_payload in (
        {"empresa": "NSA", "ventas": 100000},
        "Reporte de Nuestra Señora de la Asunción en terminal",
        [{"operator_name": "Nuestra Senora de la Asuncion"}],
    ):
        try:
            mod.assert_no_nsa_exposure(forbidden_payload)
            errors.append(f"Case 2 failed: NSA payload was not blocked: {forbidden_payload!r}")
        except mod.ForbiddenOperatorExposureError:
            pass

    # Case 3: PYG & CLP currency formatting without decimal corruption on Guaraníes
    if mod.format_executive_currency(150000, "PYG") != "Gs. 150.000":
        errors.append("Case 3a failed: PYG 150000 did not format as 'Gs. 150.000'")
    if mod.format_executive_currency("150000.00", "PYG") != "Gs. 150.000":
        errors.append("Case 3b failed: Bancard wire string '150000.00' did not format cleanly as 'Gs. 150.000'")
    if mod.format_executive_currency(1203450, "CLP") != "$1.203.450 CLP":
        errors.append("Case 3c failed: CLP 1203450 did not format as '$1.203.450 CLP'")

    # Case 4: Reject decimal corruption on Guaraníes/CLP, negative amounts, NaN, booleans
    for invalid_amt in ("150000.45", 99.99, -500, float("nan"), float("inf"), True, False, None, "abc"):
        try:
            mod.format_executive_currency(invalid_amt, "PYG")
            errors.append(f"Case 4 failed: corrupted PYG amount {invalid_amt!r} was not rejected")
        except mod.CurrencyCorruptionError:
            pass

    # Case 5: Parametric Z-score & Tukey IQR critical drop detection
    crit_res = mod.detect_kpi_anomaly(
        metric_name="Recaudación PYG",
        platform_id="boletos_paraguay",
        historical_series=[50000000, 51000000, 49500000, 50200000, 49800000, 50500000],
        current_value=25000000,
        currency="PYG",
    )
    if crit_res.severity != "CRITICAL" or crit_res.direction != "DROP" or not crit_res.is_iqr_outlier:
        errors.append(f"Case 5 failed: expected CRITICAL DROP IQR outlier, got {crit_res}")

    # Case 6: Zero-variance constant baseline handling
    const_same = mod.detect_kpi_anomaly(
        metric_name="Efectividad Minera",
        platform_id="centinela",
        historical_series=[97.5, 97.5, 97.5, 97.5, 97.5],
        current_value=97.5,
        currency="PCT",
    )
    const_drop = mod.detect_kpi_anomaly(
        metric_name="Efectividad Minera",
        platform_id="centinela",
        historical_series=[97.5, 97.5, 97.5, 97.5, 97.5],
        current_value=85.0,
        currency="PCT",
    )
    if const_same.z_score != 0.0 or const_same.severity != "NORMAL":
        errors.append(f"Case 6a failed: zero-variance identical value should be NORMAL (z=0), got {const_same}")
    if const_drop.z_score != -999.0 or const_drop.severity != "CRITICAL":
        errors.append(f"Case 6b failed: zero-variance drop should be CRITICAL (z=-999.0), got {const_drop}")

    # Case 7: Bancard vPOS SLA evaluator
    sla_ok = mod.evaluate_bancard_gateway_sla(total_tx=100, approved_tx=92, rejected_tx=7, timeout_or_rollback_tx=1)
    sla_warn = mod.evaluate_bancard_gateway_sla(total_tx=100, approved_tx=78, rejected_tx=20, timeout_or_rollback_tx=2)
    sla_crit = mod.evaluate_bancard_gateway_sla(total_tx=100, approved_tx=62, rejected_tx=28, timeout_or_rollback_tx=10)
    sla_zero = mod.evaluate_bancard_gateway_sla(total_tx=0, approved_tx=0, rejected_tx=0, timeout_or_rollback_tx=0)
    if (
        sla_ok["status"] != "HEALTHY"
        or sla_warn["status"] != "WARNING"
        or sla_crit["status"] != "CRITICAL"
        or sla_zero["status"] != "WARNING"
    ):
        errors.append("Case 7 failed: Bancard SLA status classification mismatch")

    # Case 8: Totem fleet (`room:totem:<id>`) & AWS Lightsail hardware saturation correlator
    fleet_res = mod.evaluate_totem_and_server_fleet(
        totems=[
            {"totem_id": "vina-02", "online": False, "heartbeat_age_sec": 180, "printer_status": "JAMMED"},
            {"totem_id": "asu-03", "online": True, "heartbeat_age_sec": 5, "printer_status": "OK"},
        ],
        servers=[{"service_id": "pdf", "ram_pct": 89.2, "disk_pct": 93.1, "cpu_pct": 84.0}],
    )
    if (
        fleet_res["offline_totem_rooms"] != ["room:totem:vina-02"]
        or len(fleet_res["peripheral_faults"]) != 1
        or len(fleet_res["saturated_servers"]) != 1
        or not fleet_res["trigger_fleet_audit_recommended"]
    ):
        errors.append(f"Case 8 failed: Totem room or server saturation detection mismatch: {fleet_res}")

    # Case 9: Totems Pullman Costa net settlement math (1.0% Transbank + 2.5% WIT fee)
    liq = mod.calculate_pullman_costa_liquidation(1000000)
    if (
        liq["transbank_fee_clp"] != 10000
        or liq["wit_fee_clp"] != 25000
        or liq["net_liquidated_clp"] != 965000
        or liq["formatted_net"] != "$965.000 CLP"
    ):
        errors.append(f"Case 9 failed: Totems Pullman Costa fee liquidation mismatch: {liq}")

    # Case 10: `<agent-embed>` HTML widget & 2-sentence Chilean executive TTS (`wait: False`)
    demo = mod.run_executive_audit_demo("ejecutivo@wit.la")
    vb = demo["voice_briefing"]
    if vb["arguments"]["wait"] is not False or vb["arguments"]["voice"] != "voice_executive_es":
        errors.append(f"Case 10a failed: voice briefing arguments invalid: {vb}")
    embed = mod.render_agent_embed_kpi_dashboard(
        "ejecutivo@wit.la", [crit_res], sla_crit, fleet_res
    )
    if not embed.startswith("<agent-embed") or "room:totem:vina-02" not in embed or "Gs. 25.000.000" not in embed:
        errors.append("Case 10b failed: <agent-embed> HTML output missing expected KPIs or room telemetry")

    return errors


def main() -> int:
    errors = (
        validate_layout_and_frontmatter()
        + validate_config_schema()
        + run_edge_case_unit_tests()
    )
    if errors:
        for err in errors:
            print(f"[FAIL] {err}")
        return 1
    print(
        f"[PASS] boletos-executive-bi-anomaly-narrator verified (10/10 unit tests, 31+ MCP tools, PYG/CLP integrity) at {SKILL_ROOT}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
