# -*- coding: utf-8 -*-
"""
Deterministic Executive BI Anomaly Detector, Multi-Country Currency Formatter (PYG/CLP),
Bancard vPOS SLA Evaluator, Totem Hardware Correlator (`room:totem:<id>`), and Multimodal
Briefing Synthesizer (`<agent-embed>` HTML + Chilean Executive TTS) for `boletos-executive-bi-anomaly-narrator`.

Run with:
    python examples/reference_implementation.py
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import html
import json
import math
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Sequence, Tuple

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(SKILL_ROOT, "resources", "config-template.json")

ALLOWED_EMAIL_DOMAINS = ("@boletos.la", "@wit.la")
FORBIDDEN_NSA_PATTERNS = (
    r"\bnsa\b",
    r"nuestra\s+se[ñn]ora\s+de\s+la\s+asunci[óo]n",
)
STREET_SLANG_FORBIDDEN = ("wena", "compa", "cachái", "cachai", "no más po", "sí po", "si po")


class UnauthorizedCorporateEmailError(PermissionError):
    """Raised when `user_email` is missing or outside @boletos.la / @wit.la."""


class ForbiddenOperatorExposureError(ValueError):
    """Raised when NSA (Nuestra Señora de la Asunción) appears in any input or output payload."""


class CurrencyCorruptionError(ValueError):
    """Raised when PYG or CLP amounts contain invalid types, negative numbers, or non-zero fractional cents."""


def load_skill_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# 1. GOVERNANCE GATEKEEPERS: CORPORATE EMAIL & ZERO-NSA EXPOSURE
# ============================================================================

def validate_corporate_email(user_email: Any) -> str:
    """Enforce `instructions.md` Rule 1 & 2: mandatory @boletos.la or @wit.la email."""
    if not isinstance(user_email, str) or not user_email.strip():
        raise UnauthorizedCorporateEmailError("Missing mandatory corporate user_email (@boletos.la or @wit.la).")
    cleaned = user_email.strip().lower()
    if not re.match(r"^[a-z0-9._%+-]+@(boletos\.la|wit\.la)$", cleaned):
        raise UnauthorizedCorporateEmailError(
            f"Unauthorized user_email '{user_email}'. Only @boletos.la and @wit.la are permitted."
        )
    return cleaned


def assert_no_nsa_exposure(payload: Any) -> None:
    """Enforce `instructions.md` Rule 4: NEVER display, associate, or mock NSA data."""
    serialized = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
    for pattern in FORBIDDEN_NSA_PATTERNS:
        if re.search(pattern, serialized, flags=re.IGNORECASE):
            raise ForbiddenOperatorExposureError(
                "CRITICAL POLICY VIOLATION: Detected forbidden reference to NSA (Nuestra Señora de la Asunción)."
            )


def sanitize_paraguay_operators(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter out any record referencing NSA and validate allowed operators (LSN, LSP, LSA)."""
    sanitized: List[Dict[str, Any]] = []
    for row in records:
        op_code = str(row.get("empresa", row.get("operator", ""))).strip().upper()
        op_name = str(row.get("nombre_empresa", row.get("operator_name", ""))).strip()
        if op_code == "NSA" or any(re.search(p, op_name, re.IGNORECASE) for p in FORBIDDEN_NSA_PATTERNS):
            raise ForbiddenOperatorExposureError(f"Forbidden operator record detected: {row!r}")
        sanitized.append(dict(row))
    return sanitized


# ============================================================================
# 2. DETERMINISTIC CURRENCY FORMATTING (PYG & CLP WITHOUT DECIMAL CORRUPTION)
# ============================================================================

def parse_strict_integer_currency(amount: Any, currency: str) -> int:
    """
    Parse PYG or CLP amount into an exact non-negative integer.
    - Rejects booleans, NaN, Infinity, negative numbers, and non-zero fractional cents (e.g. 150000.50).
    - Accepts integer-equivalent Bancard wire strings like '150000.00' and converts safely to int 150000.
    """
    if isinstance(amount, bool) or amount is None:
        raise CurrencyCorruptionError(f"Invalid {currency} amount type: {amount!r}")
    if isinstance(amount, float) and (math.isnan(amount) or math.isinf(amount)):
        raise CurrencyCorruptionError(f"Non-finite {currency} float amount: {amount!r}")

    raw_str = str(amount).strip()
    if not raw_str:
        raise CurrencyCorruptionError(f"Empty {currency} amount string")

    try:
        dec = Decimal(raw_str)
    except InvalidOperation as exc:
        raise CurrencyCorruptionError(f"Unparseable {currency} numeric value: {amount!r}") from exc

    if not dec.is_finite() or dec < 0:
        raise CurrencyCorruptionError(f"{currency} amount must be finite and non-negative, got: {amount!r}")

    integral = dec.to_integral_value(rounding=ROUND_HALF_UP)
    if dec != integral:
        raise CurrencyCorruptionError(
            f"Decimal corruption detected for integer currency {currency}: {amount!r} has non-zero cents"
        )
    return int(integral)


def format_executive_currency(amount: Any, currency: str = "PYG") -> str:
    """
    Format PYG or CLP for C-level executive dashboards without decimal corruption:
    - PYG -> 'Gs. 150.000'
    - CLP -> '$1.203.450 CLP'
    """
    curr = currency.strip().upper()
    if curr not in ("PYG", "CLP"):
        raise CurrencyCorruptionError(f"Unsupported BI currency: {currency!r}. Expected 'PYG' or 'CLP'.")
    val = parse_strict_integer_currency(amount, curr)
    grouped = f"{val:,}".replace(",", ".")
    if curr == "PYG":
        return f"Gs. {grouped}"
    return f"${grouped} CLP"


def calculate_pullman_costa_liquidation(gross_clp: Any) -> Dict[str, Any]:
    """
    Compute Totems Pullman Costa net settlement:
    - Transbank commission: 1.0%
    - WIT technology fee: 2.5%
    - Net liquidated to Pullman Costa: 96.5%
    """
    gross = parse_strict_integer_currency(gross_clp, "CLP")
    tbk_fee = int((Decimal(gross) * Decimal("0.01")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    wit_fee = int((Decimal(gross) * Decimal("0.025")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    net_amount = gross - tbk_fee - wit_fee
    return {
        "gross_clp": gross,
        "transbank_fee_clp": tbk_fee,
        "wit_fee_clp": wit_fee,
        "net_liquidated_clp": net_amount,
        "formatted_gross": format_executive_currency(gross, "CLP"),
        "formatted_net": format_executive_currency(net_amount, "CLP"),
    }


# ============================================================================
# 3. STATISTICAL KPI ANOMALY DETECTOR (Z-SCORE & TUKEY IQR)
# ============================================================================

@dataclass
class AnomalyResult:
    metric_name: str
    platform_id: str
    currency: str
    current_value: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    q1: float
    q3: float
    iqr: float
    is_iqr_outlier: bool
    delta_pct: float
    severity: str  # NORMAL | WARNING | CRITICAL
    direction: str  # SPIKE | DROP | STABLE
    formatted_current: str
    formatted_mean: str


def _quantile(sorted_vals: Sequence[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * q
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return float(sorted_vals[low])
    weight = pos - low
    return float(sorted_vals[low] * (1.0 - weight) + sorted_vals[high] * weight)


def detect_kpi_anomaly(
    metric_name: str,
    platform_id: str,
    historical_series: Sequence[float | int],
    current_value: float | int,
    currency: str = "PYG",
    z_warning: float = 2.0,
    z_critical: float = 3.0,
    iqr_multiplier: float = 1.5,
) -> AnomalyResult:
    """
    Deterministic parametric (Z-score) + non-parametric (Tukey IQR) anomaly detector.
    Handles constant-series (zero standard deviation) without ZeroDivisionError.
    """
    if len(historical_series) < 3:
        raise ValueError(f"historical_series requires at least 3 data points, got {len(historical_series)}")
    clean_hist = [float(x) for x in historical_series]
    curr = float(current_value)

    n = len(clean_hist)
    mean = sum(clean_hist) / n
    variance = sum((x - mean) ** 2 for x in clean_hist) / n
    std = math.sqrt(variance)

    if std == 0.0:
        if math.isclose(curr, mean, rel_tol=1e-9, abs_tol=1e-9):
            z_score = 0.0
        else:
            z_score = 999.0 if curr > mean else -999.0
    else:
        z_score = (curr - mean) / std

    sorted_hist = sorted(clean_hist)
    q1 = _quantile(sorted_hist, 0.25)
    q3 = _quantile(sorted_hist, 0.75)
    iqr = q3 - q1
    lower_bound = q1 - iqr_multiplier * iqr
    upper_bound = q3 + iqr_multiplier * iqr
    is_iqr_outlier = curr < lower_bound or curr > upper_bound

    delta_pct = ((curr - mean) / mean * 100.0) if mean != 0 else 0.0
    abs_z = abs(z_score)

    if abs_z >= z_critical or (abs_z >= z_warning and is_iqr_outlier and delta_pct <= -25.0):
        severity = "CRITICAL"
    elif abs_z >= z_warning or is_iqr_outlier:
        severity = "WARNING"
    else:
        severity = "NORMAL"

    if z_score >= z_warning or (is_iqr_outlier and curr > mean):
        direction = "SPIKE"
    elif z_score <= -z_warning or (is_iqr_outlier and curr < mean):
        direction = "DROP"
    else:
        direction = "STABLE"

    if currency in ("PYG", "CLP"):
        fmt_curr = format_executive_currency(int(round(curr)), currency)
        fmt_mean = format_executive_currency(int(round(mean)), currency)
    else:
        fmt_curr = f"{curr:.2f}%"
        fmt_mean = f"{mean:.2f}%"

    return AnomalyResult(
        metric_name=metric_name,
        platform_id=platform_id,
        currency=currency,
        current_value=curr,
        baseline_mean=round(mean, 2),
        baseline_std=round(std, 2),
        z_score=round(z_score, 2),
        q1=round(q1, 2),
        q3=round(q3, 2),
        iqr=round(iqr, 2),
        is_iqr_outlier=is_iqr_outlier,
        delta_pct=round(delta_pct, 2),
        severity=severity,
        direction=direction,
        formatted_current=fmt_curr,
        formatted_mean=fmt_mean,
    )


# ============================================================================
# 4. BANCARD GATEWAY SLA, CART FUNNEL & TOTEM FLEET HARDWARE CORRELATOR
# ============================================================================

def evaluate_bancard_gateway_sla(
    total_tx: int,
    approved_tx: int,
    rejected_tx: int,
    timeout_or_rollback_tx: int = 0,
    healthy_min_pct: float = 85.0,
    critical_max_pct: float = 70.0,
) -> Dict[str, Any]:
    """Evaluate Bancard vPOS health and trigger 2PC rollback / SLA alerts."""
    if total_tx < 0 or approved_tx < 0 or rejected_tx < 0 or timeout_or_rollback_tx < 0:
        raise ValueError("Transaction counters cannot be negative")
    if total_tx == 0:
        return {
            "status": "WARNING",
            "approval_rate_pct": 0.0,
            "rejection_rate_pct": 0.0,
            "rollback_rate_pct": 0.0,
            "recommended_action": "ZERO_TRAFFIC_DETECTED: Verify Bancard vPOS webhook endpoint and GDS checkout lock.",
        }
    approval_rate = round((approved_tx / total_tx) * 100.0, 2)
    rejection_rate = round((rejected_tx / total_tx) * 100.0, 2)
    rollback_rate = round((timeout_or_rollback_tx / total_tx) * 100.0, 2)

    if approval_rate < critical_max_pct or rollback_rate >= 8.0:
        status = "CRITICAL"
        action = "IMMEDIATE_SRE_ESCALATION: Inspect get_service_logs(service_id='bancard') and verify timeout polling."
    elif approval_rate < healthy_min_pct or rollback_rate >= 3.0:
        status = "WARNING"
        action = "MONITOR_GATEWAY: Elevated rejection or 2PC rollback rate on Bancard vPOS."
    else:
        status = "HEALTHY"
        action = "NOMINAL: Bancard vPOS operating within SLA."

    return {
        "status": status,
        "total_tx": total_tx,
        "approved_tx": approved_tx,
        "rejected_tx": rejected_tx,
        "timeout_or_rollback_tx": timeout_or_rollback_tx,
        "approval_rate_pct": approval_rate,
        "rejection_rate_pct": rejection_rate,
        "rollback_rate_pct": rollback_rate,
        "recommended_action": action,
    }


def evaluate_totem_and_server_fleet(
    totems: Sequence[Dict[str, Any]],
    servers: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Audit self-service kiosks (`room:totem:<id>`) and AWS Lightsail VPS nodes
    (RAM > 85%, Disk > 90%, CPU > 80%).
    """
    offline_rooms: List[str] = []
    peripheral_faults: List[Dict[str, str]] = []

    for t in totems:
        totem_id = str(t.get("totem_id", t.get("id", "unknown")))
        room = f"room:totem:{totem_id}"
        online = bool(t.get("online", True))
        heartbeat_age = float(t.get("heartbeat_age_sec", 0))
        printer_status = str(t.get("printer_status", "OK")).upper()
        pos_status = str(t.get("pos_status", "OK")).upper()

        if not online or heartbeat_age > 90:
            offline_rooms.append(room)
        if printer_status not in ("OK", "ONLINE", "READY") or pos_status not in ("OK", "ONLINE", "READY"):
            peripheral_faults.append(
                {"room": room, "printer_status": printer_status, "pos_status": pos_status}
            )

    saturated_servers: List[Dict[str, Any]] = []
    for srv in servers:
        srv_id = str(srv.get("service_id", srv.get("name", "unknown")))
        ram_pct = float(srv.get("ram_pct", 0.0))
        disk_pct = float(srv.get("disk_pct", 0.0))
        cpu_pct = float(srv.get("cpu_pct", 0.0))
        if ram_pct > 85.0 or disk_pct > 90.0 or cpu_pct > 80.0:
            saturated_servers.append(
                {
                    "service_id": srv_id,
                    "ram_pct": ram_pct,
                    "disk_pct": disk_pct,
                    "cpu_pct": cpu_pct,
                }
            )

    requires_fleet_audit = bool(offline_rooms or peripheral_faults or saturated_servers)
    return {
        "total_totems": len(totems),
        "offline_totem_rooms": offline_rooms,
        "peripheral_faults": peripheral_faults,
        "saturated_servers": saturated_servers,
        "trigger_fleet_audit_recommended": requires_fleet_audit,
    }


# ============================================================================
# 5. MULTIMODAL BRIEFING SYNTHESIZER (<agent-embed> HTML + CHILEAN VOICE TTS)
# ============================================================================

def build_chilean_executive_voice_briefing(
    anomalies: Sequence[AnomalyResult],
    bancard_sla: Dict[str, Any],
    fleet_health: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate a 2-sentence Chilean executive voice notification payload for `gemini-tts` (`speak`).
    Enforces:
    - `wait: False` (mandatory non-blocking fire-and-forget)
    - `voice: "voice_executive_es"`, `speed: 1.15`, `lang: "es"`
    - Maximum 2 sentences, crisp executive diction, zero street slang.
    """
    critical_list = [a for a in anomalies if a.severity == "CRITICAL"]
    warning_list = [a for a in anomalies if a.severity == "WARNING"]

    if critical_list:
        top = critical_list[0]
        s1 = (
            f"Te informo al tiro que detectamos una anomalía crítica en {top.platform_id} "
            f"con {top.formatted_current} y un desvío Z de {top.z_score:+.1f}."
        )
    elif warning_list:
        top = warning_list[0]
        s1 = (
            f"Revisamos al tiro los tableros ejecutivos y observamos una variación moderada en {top.platform_id} "
            f"situada en {top.formatted_current}."
        )
    else:
        s1 = "Revisamos al tiro los siete tableros ejecutivos de Chile y Paraguay, manteniendo la recaudación dentro del rango esperado."

    offline_cnt = len(fleet_health.get("offline_totem_rooms", []))
    sat_cnt = len(fleet_health.get("saturated_servers", []))
    s2 = (
        f"La pasarela Bancard registra {bancard_sla['approval_rate_pct']:.1f}% de aprobación "
        f"con {offline_cnt} tótems desconectados y {sat_cnt} servidores en alerta de recursos."
    )

    full_text = f"{s1} {s2}"
    # Verify zero street slang and max 2 sentences
    for slang in STREET_SLANG_FORBIDDEN:
        if slang in full_text.lower():
            raise ValueError(f"Forbidden street slang detected in executive voice briefing: {slang}")

    return {
        "mcp_server": "gemini-tts",
        "tool": "speak",
        "arguments": {
            "text": full_text,
            "voice": "voice_executive_es",
            "speed": 1.15,
            "lang": "es",
            "wait": False,
        },
        "sentence_count": 2,
    }


def render_agent_embed_kpi_dashboard(
    user_email: str,
    anomalies: Sequence[AnomalyResult],
    bancard_sla: Dict[str, Any],
    fleet_health: Dict[str, Any],
) -> str:
    """
    Render a self-contained interactive `<agent-embed>` HTML widget (`generative_ui` pattern)
    comparing PYG and CLP KPIs, Z-score badges, Bancard SLA, and Totem room statuses.
    """
    validated_email = validate_corporate_email(user_email)
    rows_html = []
    for a in anomalies:
        assert_no_nsa_exposure(a.platform_id)
        badge_color = (
            "#dc2626" if a.severity == "CRITICAL" else ("#d97706" if a.severity == "WARNING" else "#16a34a")
        )
        rows_html.append(
            f"<tr>"
            f"<td><strong>{html.escape(a.platform_id)}</strong></td>"
            f"<td>{html.escape(a.metric_name)}</td>"
            f"<td>{html.escape(a.formatted_current)}</td>"
            f"<td>{html.escape(a.formatted_mean)}</td>"
            f"<td><code>{a.z_score:+.2f}σ</code> ({a.delta_pct:+.1f}%)</td>"
            f"<td><span style='background:{badge_color};color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;'>"
            f"{html.escape(a.severity)}</span></td>"
            f"</tr>"
        )

    offline_str = ", ".join(fleet_health.get("offline_totem_rooms", [])) or "Ninguno (100% Online)"
    widget_html = f"""<agent-embed title="Boletos.la &amp; Grupo Pullman — Executive BI Anomaly Matrix">
<div style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;padding:16px;border-radius:12px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
    <h3 style="margin:0;font-size:16px;">Auditoría Ejecutiva BI (PYG / CLP)</h3>
    <span style="font-size:12px;color:#94a3b8;">Autorizado: {html.escape(validated_email)}</span>
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px;">
    <div style="background:#1e293b;padding:10px;border-radius:8px;">
      <div style="font-size:11px;color:#94a3b8;">Bancard vPOS SLA</div>
      <div style="font-size:18px;font-weight:700;">{bancard_sla['approval_rate_pct']:.1f}% ({html.escape(bancard_sla['status'])})</div>
    </div>
    <div style="background:#1e293b;padding:10px;border-radius:8px;">
      <div style="font-size:11px;color:#94a3b8;">Tótems Offline (WebSocket)</div>
      <div style="font-size:13px;font-weight:600;">{html.escape(offline_str)}</div>
    </div>
    <div style="background:#1e293b;padding:10px;border-radius:8px;">
      <div style="font-size:11px;color:#94a3b8;">Servidores Saturados</div>
      <div style="font-size:18px;font-weight:700;">{len(fleet_health.get('saturated_servers', []))} VPS</div>
    </div>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:13px;text-align:left;">
    <thead>
      <tr style="border-bottom:1px solid #334155;color:#94a3b8;">
        <th style="padding:6px;">Plataforma</th>
        <th style="padding:6px;">Métrica</th>
        <th style="padding:6px;">Actual</th>
        <th style="padding:6px;">Media Base</th>
        <th style="padding:6px;">Z-Score (Δ%)</th>
        <th style="padding:6px;">Estado</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</div>
</agent-embed>"""
    assert_no_nsa_exposure(widget_html)
    return widget_html


def run_executive_audit_demo(user_email: str = "finanzas@boletos.la") -> Dict[str, Any]:
    """Run a complete deterministic C-level multi-country audit simulation."""
    validated_email = validate_corporate_email(user_email)

    pyg_anom = detect_kpi_anomaly(
        metric_name="Recaudación Diaria Interurbana",
        platform_id="boletos_paraguay",
        historical_series=[45000000, 47200000, 46100000, 45800000, 46900000, 45500000, 46400000],
        current_value=31200000,
        currency="PYG",
    )
    clp_anom = detect_kpi_anomaly(
        metric_name="Ventas Convenios Corporativos",
        platform_id="pullman_convenios",
        historical_series=[18500000, 19100000, 18800000, 19200000, 18750000, 19050000, 18900000],
        current_value=19000000,
        currency="CLP",
    )
    costa_liq = calculate_pullman_costa_liquidation(1203450000)
    bancard_sla = evaluate_bancard_gateway_sla(
        total_tx=420, approved_tx=315, rejected_tx=85, timeout_or_rollback_tx=20
    )
    fleet_health = evaluate_totem_and_server_fleet(
        totems=[
            {"totem_id": "asu-01", "online": False, "heartbeat_age_sec": 240, "printer_status": "PAPER_EMPTY"},
            {"totem_id": "alameda-04", "online": True, "heartbeat_age_sec": 12, "printer_status": "OK"},
        ],
        servers=[
            {"service_id": "bancard", "ram_pct": 88.5, "disk_pct": 62.0, "cpu_pct": 74.0},
            {"service_id": "gds", "ram_pct": 64.0, "disk_pct": 55.0, "cpu_pct": 41.0},
        ],
    )
    voice_payload = build_chilean_executive_voice_briefing([pyg_anom, clp_anom], bancard_sla, fleet_health)
    embed_html = render_agent_embed_kpi_dashboard(validated_email, [pyg_anom, clp_anom], bancard_sla, fleet_health)

    return {
        "authorized_user": validated_email,
        "anomalies": [pyg_anom.__dict__, clp_anom.__dict__],
        "pullman_costa_settlement": costa_liq,
        "bancard_sla": bancard_sla,
        "fleet_health": fleet_health,
        "voice_briefing": voice_payload,
        "agent_embed_length": len(embed_html),
    }


if __name__ == "__main__":
    demo_output = run_executive_audit_demo()
    print(json.dumps(demo_output, indent=2, ensure_ascii=False))
