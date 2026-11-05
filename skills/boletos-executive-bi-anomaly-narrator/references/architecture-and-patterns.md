# Deep Architecture & Operational Patterns: `boletos-executive-bi-anomaly-narrator`

This reference defines the parallel MCP orchestration topology, statistical anomaly detection formulas, currency integrity rules (`PYG` vs `CLP`), hardware room telemetry (`room:totem:<id>`), and multimodal output pipelines (`generative_ui`, Google Workspace export, and non-blocking Chilean executive TTS) for the 31 tools exposed by `boletos-monitoreo`.

---

## 1. Complete 31+1 Tool Taxonomy (`boletos-monitoreo` MCP)

Every call to `boletos-monitoreo` **MUST** include a validated corporate `user_email` (`@boletos.la` or `@wit.la`) and operate in strictly read-only mode.

| Domain | MCP Tool Name | Key Parameters | Primary Audit Output |
| :--- | :--- | :--- | :--- |
| **C-Level & Catalog** | `get_executive_financial_kpis` | `user_email`, `period` (`all`, `today`, `last_7_days`, `last_30_days`) | Consolidated `PYG` revenue, approval rate, average ticket |
| **C-Level & Catalog** | `get_executive_bi_catalog` | `user_email`, `formato` (`markdown`, `json`) | Master matrix of all 7 BI platforms across Chile & Paraguay |
| **C-Level & Catalog** | `get_top_commercial_routes` | `user_email`, `limit` (`10`) | Top origin-destination corridors by ticket volume and revenue |
| **C-Level & Catalog** | `install_graphs` | `user_email`, `target_dashboard`, `destination_dir`, `formato` | Mermaid, SVG, and Unicode chart templates for the 7 dashboards |
| **Paraguay BI (PYG)** | `get_boletos_paraguay_sales_dashboard` | `user_email`, `view`, `empresa` (`LSN`, `LSP`, `LSA`), `canal`, `formato` | Interurban PYG sales (Web 75% vs Totem 23.5%); zero NSA exposure |
| **Paraguay BI (PYG)** | `get_custodia_asuncion_dashboard` | `user_email`, `view`, `tamano` (`S`, `M`, `L`, `XL`), `metodo_pago` | Asunción Terminal smart lockers revenue (`Efectivo` vs `Tarjeta`) |
| **Chile BI (CLP)** | `get_pullman_convenios_dashboard` | `user_email`, `view`, `convenio`, `fecha_inicio`, `fecha_fin`, `formato` | B2B corporate agreements (`convenios.vista_reporte_eventos`) |
| **Chile BI (CLP)** | `get_pullman_cuentas_corrientes_dashboard` | `user_email`, `view`, `empresa`, `limite`, `formato` | 154 corporate credit accounts (`multiempresa_db`: Sodexo, Aramark) |
| **Chile BI (CLP)** | `get_pullman_commercial_sales` | `user_email`, `category` (`all`, `convenios`, `cuentas_corrientes`) | Combined commercial B2B sales synthesis for Pullman Bus |
| **Chile BI (CLP)** | `get_centinela_sales_dashboard` | `user_email`, `view`, `servicio`, `fecha_inicio`, `fecha_fin`, `formato` | Mining transport KPIs (97.5% effectiveness, 2.5% refund rate) |
| **Chile BI (CLP)** | `get_terminal_sur_management_dashboard` | `user_email`, `view`, `subsistema` (`all`, `cajas`, `totems`, `custodia`) | Consolidated Santiago Terminal Sur ($557M Cajas, $44M Totems, $45M Custodia) |
| **Chile BI (CLP)** | `get_totems_pullman_costa_dashboard` | `user_email`, `view`, `terminal` (`all`, `alameda`, `vina`), `formato` | 12 self-service totems ($1.203M CLP, 1.0% Transbank fee, 2.5% WIT fee) |
| **FinTech & Funnel** | `get_bancard_gateway_health` | `user_email` | Real-time Bancard vPOS approval/rejection ratio and error codes |
| **FinTech & Funnel** | `get_cart_abandonment_metrics` | `user_email` | Checkout drop-off rate, abandoned carts, remarketing recovery |
| **FinTech & Funnel** | `get_meta_campaign_telemetry` | `user_email` | Meta Pixel & Conversions API (CAPI) ROAS and event match quality |
| **FinTech & Funnel** | `get_whatsapp_support_telemetry` | `user_email` | Evolution API / n8n concierge response SLA and ticket resolution |
| **Passenger Forensics** | `search_passenger_tickets` | `user_email`, `query` (RUT/CI, PNR, ticket ID, auth code, phone) | Cross-references payment gateway, GDS PNR, SIFEN invoice, and Convenios |
| **Totems & Terminals** | `get_totems_fleet_status` | `user_email`, `country` (`all`, `paraguay`, `chile`) | Self-service kiosk heartbeat (`room:totem:<id>`), peripherals, online ratio |
| **Totems & Terminals** | `get_totems_advertising_summary` | `user_email`, `country` (`all`, `paraguay`, `chile`) | Ad screens, active campaign spots, and DOOH playback telemetry |
| **Totems & Terminals** | `get_terminal_sur_services_summary` | `user_email`, `service_type` (`all`, `banos`, `custodia`) | Live turnstile and baggage custody tariff/operational status |
| **Totems & Terminals** | `get_gps_telemetry_services` | `user_email`, `region` (`all`, `chile`, `paraguay`) | Fleet GPS tracking daemon health across Chile and Paraguay |
| **SRE & Lightsail** | `get_monitoring_status` | `user_email` | Monitoring API health and telemetry cache freshness |
| **SRE & Lightsail** | `list_services` | `user_email` | Status of the 9 AWS Lightsail microservices (`gds`, `bancard`, `pdf`, etc.) |
| **SRE & Lightsail** | `get_service_detail` | `user_email`, `service_id` | VPS CPU/RAM/Disk, PM2/Docker runtime, and DB connection pool |
| **SRE & Lightsail** | `get_service_logs` | `user_email`, `service_id`, `log_type` (`error`, `out`), `max_lines` | Tail stdout/stderr logs from any of the 9 Lightsail microservices |
| **SRE & Lightsail** | `get_database_traceability` | `user_email`, `target` (`all`, `bancard`, `gds`, `convenios`, `n8n`) | Live row audit across PostgreSQL RDS, MySQL RDS, and GDS MongoDB |
| **SRE & Lightsail** | `get_aws_infrastructure_catalog` | `user_email` | Consolidated inventory of AWS accounts, Lightsail VPS, and RDS instances |
| **SRE & Lightsail** | `get_fleet_hardware_alerts` | `user_email` | Alerts on servers exceeding RAM > 85%, Disk > 90%, or high CPU load |
| **SRE & Lightsail** | `get_fleet_error_digest` | `user_email` | Aggregated error digest across all 9 microservices |
| **SRE & Lightsail** | `get_fleet_summary` | `user_email`, `report_type` (`current`, `last`) | Executive Markdown infrastructure comparison (`current` vs `last`) |
| **SRE & Lightsail** | `get_full_report` | `user_email` | Complete raw JSON infrastructure and BI telemetry snapshot |
| **SRE & Lightsail** | `trigger_fleet_audit` | `user_email` | Triggers immediate 360-degree background re-inspection of all servers |

---

## 2. Statistical Anomaly Detection Math (Z-Score + IQR Hybrid)

Daily and hourly ticket revenue exhibits strong day-of-week seasonality and occasional corporate bulk purchases. To avoid false positives while catching genuine gateway or GDS outages within minutes, the anomaly engine computes both parametric (**Z-score**) and non-parametric (**Tukey IQR**) bounds:

1. **Parametric Z-Score**:
   $$z = \frac{x_t - \mu}{\sigma}, \quad \mu = \frac{1}{N}\sum_{i=1}^{N} x_i, \quad \sigma = \sqrt{\frac{1}{N}\sum_{i=1}^{N}(x_i - \mu)^2}$$
   - `|z| >= 3.0`: **CRITICAL** anomaly (e.g., sudden revenue collapse due to Bancard vPOS webhook timeout or GDS seat-lock failure).
   - `2.0 <= |z| < 3.0`: **WARNING** drift.
   - **Zero-Variance Guardrail**: When $\sigma = 0$ (constant baseline series), if $x_t \neq \mu$, assign deterministic $|z| = \infty$ (`999.0` sentinel) and flag as anomaly; if $x_t = \mu$, $z = 0.0$.

2. **Non-Parametric Interquartile Range (IQR)**:
   $$\text{IQR} = Q_3 - Q_1, \quad \text{Lower Bound} = Q_1 - 1.5 \times \text{IQR}, \quad \text{Upper Bound} = Q_3 + 1.5 \times \text{IQR}$$
   - An observation $x_t$ is flagged as an **IQR Outlier** whenever $x_t < \text{Lower Bound}$ or $x_t > \text{Upper Bound}$.

3. **Composite Severity Classification**:
   - **CRITICAL**: $|z| \ge 3.0$ OR ($|z| \ge 2.0$ and $x_t$ is an IQR outlier with negative revenue delta $\Delta < -25\%$).
   - **WARNING**: $2.0 \le |z| < 3.0$ OR IQR outlier alone.
   - **NORMAL**: $|z| < 2.0$ and within IQR bounds.

---

## 3. Currency Integrity Protocol (`PYG` vs `CLP`)

- **Paraguayan Guaraní (`PYG`)**:
  - Circulating currency is strictly integer (`decimals = 0`).
  - **Executive Display Format**: `Gs. 150.000` or `Gs. 48.250.000` (dot thousands separator, **never** append `,00` or `.00` in human-facing BI tables or charts, as adding two zeros inflates perceived Guaraní figures by $100\times$).
  - **Bancard vPOS Wire Exception**: Only when generating raw Bancard API payloads does the wire protocol require `"150000.00"`. The BI Anomaly Narrator strips `.00` wire suffixes before aggregating PYG revenue and raises a `CurrencyCorruptionError` if non-zero fractional cents (e.g., `150000.45`) appear in a `PYG` ledger.
- **Chilean Peso (`CLP`)**:
  - Circulating currency is strictly integer (`decimals = 0`).
  - **Executive Display Format**: `$1.203.450 CLP` (prefix `$`, dot thousands separator, suffix `CLP`).
  - **Totem Pullman Costa Net Settlement**:
    - Gross Revenue ($G$), Transbank Fee ($1.0\%$), WIT Technological Fee ($2.5\%$):
    - $\text{Fee}_{\text{TBK}} = \text{round}(G \times 0.01)$, $\text{Fee}_{\text{WIT}} = \text{round}(G \times 0.025)$, $\text{Net}_{\text{Pullman}} = G - \text{Fee}_{\text{TBK}} - \text{Fee}_{\text{WIT}}$.

---

## 4. Totem Fleet & Microservice Root-Cause Correlation

When `get_executive_financial_kpis` or `get_totems_pullman_costa_dashboard` shows a negative sales anomaly ($z \le -2.0$), automatically correlate with:
1. **Bancard Gateway Health (`get_bancard_gateway_health`)**:
   - Check if approval rate dropped below `85.0%` (`WARNING`) or `70.0%` (`CRITICAL`), or if `response_code != "00"` rejections spiked.
2. **Self-Service Totem Fleet (`get_totems_fleet_status`)**:
   - Inspect WebSocket room heartbeats (`room:totem:<id>`). Any totem missing heartbeats for $> 90\text{s}$ or reporting thermal printer `PAPER_EMPTY` / `PRinter_OFFLINE` or Transbank POS serial (`COM` / `115200 8N1`) `NAK` errors directly explains localized terminal revenue drops.
3. **Lightsail VPS Saturation (`get_fleet_hardware_alerts` & `get_fleet_error_digest`)**:
   - Check if `gds`, `bancard`, `convenios`, or `pdf` microservices exceed `RAM > 85%` or `Disk > 90%`. If stale telemetry is suspected, invoke `trigger_fleet_audit(user_email=...)`.
