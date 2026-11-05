# Domain Engineering Standards — `agy-cfo-tools` (`business_finance`)

- **Scope & Stack**: Financial modeling (`.xlsx`, Google Sheets, LibreOffice Calc), unit economics (`CAC`, `LTV`, `Payback`, `NRR`, `Burn Multiple`), B2B proposals, KPI reporting, multi-gateway billing reconciliation (`Bancard vPOS`, `Transbank Webpay`, `Stripe`, `PayPal`, `Pagopar`), ERP accounting (`Odoo`), and electronic tax compliance (`DNIT SIFEN v150` / `SII DTE`).
- **Currency & Formula Integrity**:
  - Zero-decimal currencies (`PYG`, `CLP`, `JPY`) must be formatted and aggregated as exact integers without floating-point rounding drift.
  - When generating `.xlsx` or Google Sheets financial models, always write live formulas (`=SUM(...)`, `=INDEX(..., MATCH(...))`, `=SUMIFS(...)`) rather than hardcoded calculated literals, and verify zero `#REF!`, `#NAME?`, `#VALUE!`, or `#DIV/0!` errors.
- **Progressive Disclosure**: Use `skill-finder` (`skills/skill-finder/scripts/find_skills.py`) or `INDEX.md` to activate specialized skills in `skills/<skill-name>/SKILL.md` only when relevant to the active task.
- **Verification First**: Always validate financial calculations, tax check digits (Modulo 11), and ledger balances with deterministic scripts before reporting completion.
