---
name: skill-finder
description: >-
  Search the curated CFO, Finance, Accounting, Tax, BI, ERP, and Spreadsheet skills in
  CATALOG.json in under 10ms and generate ready-to-paste Antigravity 2.0 .agents/skills.json
  entries with include_only allowlists. Use whenever setting up a workspace .agents/skills.json
  or locating a specialized financial/business template skill without copying bulk folders.
---

# JIT Template Skill Finder (`agy-cfo-tools`)

Use `find_skills.py` (or `scripts/find_template_skill.py`) to search all curated Finance, CFO, Accounting, FinTech, Tax/SIFEN/DTE, ERP (Odoo), Spreadsheet (`xlsx`/`gsheets`/`calc`), and Executive BI skills in `< 10ms`.

## 1. Search by Keyword(s) or Category

Execute via terminal or PowerShell:

```powershell
python ~/.gemini/config/plugins/agy-cfo-tools/scripts/find_template_skill.py billing sifen bancard xlsx --limit 6
python ~/.gemini/config/skills/skill-finder/scripts/find_skills.py odoo accounting tax excel bi --top 8
```

Filter to a single category or emit structured JSON:

```powershell
python ~/.gemini/config/skills/skill-finder/scripts/find_skills.py stripe payment -c business_finance --limit 5
python ~/.gemini/config/skills/skill-finder/scripts/find_skills.py financial modeling kpi --json
```

### Canonical CFO & Finance Skills Included
- `latam-fintech-payments-invoicing` (`business_finance`): Bancard vPOS v1.23.1, VentasQR, Caja POS Android, Pagopar, BCP SIPAP/PY-QR, DNIT SIFEN v150 (44-digit CDC Mod-11), and Transbank Webpay Plus.
- `boletos-executive-bi-anomaly-narrator` (`business_finance`): Executive BI KPIs, Z-score & Tukey IQR revenue anomaly detection, and multi-currency (`PYG`/`CLP`/`USD`) scorecards.
- `xlsx` & `xlsx-official` (`business_finance` / `design_ux`): Programmatic Excel (`.xlsx`) financial modeling, formula verification (`recalc.py`), and audit-grade formatting.
- `gsheets` & `googlesheets-automation` (`business_finance` / `databases`): Google Sheets financial automation, pivot tables, and live KPI synchronization.
- `startup-financial-modeling` & `quant-analyst` (`design_ux` / `ai_ml`): 3-5 year financial projections, cash flow, burn rate, unit economics, and quantitative risk modeling.
- `odoo-accounting-setup` & `odoo-l10n-compliance` (`design_ux` / `business_finance`): Chart of accounts, journals, fiscal positions, 3-way PO matching, and LATAM/EU e-invoicing.
- `billing-automation` & `payment-integration` (`business_finance`): Recurring billing, dunning workflows, proration, tax calculation, and PCI-DSS v4.0.1 compliance.

## 2. Mount via `.agents/skills.json` (Zero Clone-Bombing Rule)

1. **Never bulk-copy** all 87 skills into `<workspace>/.agents/skills/`.
2. For one-off tasks, read the returned `SKILL.md` path directly with `read_file`.
3. For persistent workspace availability, paste the generated `entries` + `include_only` block (3 to 6 relevant skills maximum) into `<workspace>/.agents/skills.json`:

```json
{
  "entries": [
    {
      "path": "skills"
    },
    {
      "path": "~/.gemini/config/plugins/agy-cfo-tools/skills",
      "include_only": [
        "billing-automation",
        "latam-fintech-payments-invoicing",
        "startup-financial-modeling",
        "xlsx"
      ]
    }
  ]
}
```
