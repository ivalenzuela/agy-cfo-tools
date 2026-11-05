# AGENTS.md — AGY CFO Tools Governance Rules

This consolidated rule file defines workspace constraints loaded when `agy-cfo-tools` is enabled.
Per the Antigravity Rules specification, standalone `AGENTS.md` files do not use YAML frontmatter and remain under `24,000` bytes after expanding `@[label](path)` includes.

## 1. Core CFO & Finance Directives
- Use `skill-finder` (`python ~/.gemini/config/skills/skill-finder/scripts/find_skills.py <keywords>`) to locate the optimal 3-6 domain skills from `CATALOG.json` and mount them via `.agents/skills.json` (`include_only`).
- Prefer progressive disclosure: load reference manuals from `skills/<skill_name>/references/` only when needed.
- Enforce strict numeric, tax, and currency precision across all spreadsheets, BI dashboards, and ERP/FinTech integrations.

## 2. Included Modular Rules
@[domain_standards](./domain_standards.md)
@[security_guidelines](./security_guidelines.md)
