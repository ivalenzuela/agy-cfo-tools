# AGY CFO & Finance Suite (`agy-cfo-tools`)

Suite oficial de herramientas financieras, contables, modelamiento en Excel/Google Sheets, pasarelas de pago FinTech LATAM, facturación electrónica (**DNIT SIFEN v150** / **SII DTE** / **CFDI**), **ERP Odoo**, Business Intelligence Ejecutivo, **Sidecar CFO Cockpit**, **Subagentes Especializados** y **JIT Skill Finder** para **Google Antigravity 2.0**.

---

## 1. Instalación Rápida (1-Click en Antigravity)

### Opción A: Prompt Directo para Pegar en Antigravity (Recomendado)

Copia y pega el siguiente prompt directamente en el chat de tu **Antigravity**:

```text
Clona e instala la suite financiera oficial desde https://github.com/boletos-la/agy-cfo-tools ejecutando su instalador `python install.py` para configurar el plugin `agy-cfo-tools` en `~/.gemini/config/plugins/agy-cfo-tools`, la skill `skill-finder` en `~/.gemini/config/skills/skill-finder`, el sidecar `cfo-cockpit` en `~/.gemini/config/sidecars/cfo-cockpit` y las 87 skills de Finanzas, Contabilidad, BI, Excel/Sheets, Odoo ERP y Facturación Electrónica. Finalmente ejecuta `python scripts/validate_repo.py` para verificar que todo esté operativo.
```

### Opción B: Instalación Manual por Terminal (Git + Python / PowerShell)

```bash
git clone https://github.com/boletos-la/agy-cfo-tools.git
cd agy-cfo-tools
python install.py
```

*(En Windows PowerShell también puedes ejecutar `.\install.ps1`)*

---

## 2. Arquitectura del Ecosistema `agy-cfo-tools`

El repositorio empaqueta todos los componentes estándar del sistema de personalización de **Antigravity 2.0**:

| Componente | Ubicación en el Repo | Destino de Instalación | Descripción |
| :--- | :--- | :--- | :--- |
| **Plugin Principal** | `plugin.json` / `.gemini-plugin/` | `~/.gemini/config/plugins/agy-cfo-tools` | Bundle unificado de 87 skills financieras, reglas, subagentes, hooks y MCP. |
| **Skill Finder (JIT)** | `skills/skill-finder/` + `CATALOG.json` | `~/.gemini/config/skills/skill-finder` | Motor de búsqueda `< 10ms` que genera bloques `.agents/skills.json` (`include_only`) sin clonar carpetas masivas. |
| **87 Skills de Finanzas** | `skills/<skill-name>/SKILL.md` | `~/.gemini/config/plugins/agy-cfo-tools/skills` | Modelamiento `.xlsx`, Google Sheets, LibreOffice Calc, FinTech LATAM, SIFEN v150, Stripe, PayPal, Odoo Accounting, Quant, BI y D3.js. |
| **Sidecar CFO Cockpit** | `sidecars/cfo-cockpit/` | `~/.gemini/config/sidecars/cfo-cockpit` | Panel auxiliar web (`:8496`) con buscador interactivo `skill-finder`, generador `.agents/skills.json` y calculadora de Unit Economics / Runway / ARR. |
| **Subagentes CFO** | `agents/*.md` | `~/.gemini/config/plugins/agy-cfo-tools/agents` | `cfo-financial-strategist` (FP&A, Excel/Sheets, DCF, BI) y `fintech-tax-auditor` (Pasarelas 2PC, SIFEN/DTE, ERP, PCI-DSS). |
| **Reglas y Hooks** | `rules/` + `hooks.json` | `~/.gemini/config/plugins/agy-cfo-tools/rules` | Estándares de precisión monetaria sin decimales (`PYG`/`CLP`), validación de fórmulas Excel y bloqueo de comandos destructivos. |
| **Auto-Watcher** | `watcher/` | `~/.gemini/config/plugins/agy-cfo-tools/watcher` | Aprovisionador automático de `.agents/skills.json` al abrir proyectos financieros en Antigravity IDE. |

---

## 3. Cómo Usar `skill-finder` para Configurar Cualquier Proyecto Financiero

La skill **`skill-finder`** permite buscar entre las **87 skills especializadas** en menos de `10ms` y generar la configuración exacta para `.agents/skills.json` bajo la regla **Zero Clone-Bombing** (`include_only`):

```powershell
# Buscar skills por palabras clave (ej. Excel, facturación SIFEN, Bancard, BI, Odoo):
python ~/.gemini/config/skills/skill-finder/scripts/find_skills.py cfo xlsx billing sifen --top 6

# Filtrar por categoría o exportar en JSON:
python ~/.gemini/config/skills/skill-finder/scripts/find_skills.py odoo accounting tax --json
```

Ejemplo de bloque `.agents/skills.json` generado automáticamente para la raíz de tu proyecto:

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
        "odoo-accounting-setup",
        "skill-finder",
        "startup-financial-modeling",
        "xlsx"
      ]
    }
  ]
}
```

---

## 4. Skills Destacadas por Dominio Financiero (87 Skills Incluidas)

### A. Modelamiento Financiero, Excel (`.xlsx`), Google Sheets & Calc
- **`xlsx`** / **`xlsx-official`**: Creación, edición y auditoría programática de modelos financieros en Microsoft Excel (`.xlsx`, `.xlsm`), con verificación obligatoria de fórmulas (`recalc.py`, cero `#REF!` / `#NAME?`).
- **`gsheets`** / **`googlesheets-automation`**: Lectura, escritura, tablas dinámicas, reglas condicionales y sincronización de reportes financieros en Google Sheets.
- **`calc`** / **`bilig-workpaper`**: Hojas de cálculo estructuradas en LibreOffice Calc (`.ods`/`.xlsx`/`.csv`) y WorkPapers respaldados por fórmulas.
- **`startup-financial-modeling`**: Modelos financieros integrales a 3–5 años (P&L, Flujo de Caja, Balance, Unit Economics, Burn Rate y análisis de sensibilidad).
- **`quant-analyst`** / **`risk-manager`** / **`options-flow-analyzer`**: Modelamiento cuantitativo, gestión de riesgo de portafolio/tesorería, cobertura cambiaria y métricas ajustadas por riesgo.
- **`alpha-vantage`**: Acceso a más de 20 años de datos financieros globales (acciones, tasas de cambio FX, commodities e indicadores macroeconómicos).

### B. Pasarelas de Pago FinTech, Facturación Electrónica (SIFEN / DTE) & Cobranza
- **`latam-fintech-payments-invoicing`**: Integración y auditoría de pasarelas de pago e impuestos en Paraguay y Chile: **Bancard vPOS v1.23.1** (11 operaciones oficiales + 2PC rollback), **VentasQR**, **Caja POS Android v1.7**, **Pagopar 2.0/3.0**, **BCP SIPAP / PY-QR** (`CRC-16/CCITT-FALSE 0x1021`), **DNIT SIFEN v150** (CDC de 44 dígitos Módulo 11 pesos `2..11`, IVA Ley 6380/2019) y **Transbank Webpay Plus**.
- **`payment-integration`** / **`stripe-integration`** / **`stripe-automation`** / **`paypal-integration`**: Orquestación multi-pasarela idempotente, verificación criptográfica de webhooks y conciliación de cobros.
- **`billing-automation`**: Facturación recurrente, gestión de morosidad (*dunning*), prorrateos y cálculo automatizado de impuestos.
- **`pci-compliance`** / **`fsi-compliance-checker`**: Cumplimiento normativo **PCI-DSS v4.0.1** y controles regulatorios del sector financiero.

### C. ERP Odoo, Contabilidad, Compras, Nómina & Inventario
- **`odoo-accounting-setup`**: Configuración maestra de Odoo Contabilidad (plan de cuentas, diarios, posiciones fiscales, impuestos, términos de pago y conciliación bancaria).
- **`odoo-l10n-compliance`**: Localización contable y facturación electrónica por país (`CFDI`, `SIFEN`, `DTE`, `SAF-T`).
- **`odoo-purchase-workflow`**: Flujo completo de compras y cuentas por pagar (*3-Way Matching*: `RFQ -> Orden de Compra -> Recepción -> Factura de Proveedor`).
- **`odoo-hr-payroll-setup`**: Estructuras salariales, reglas de liquidación de sueldos y asientos contables de nómina.
- **`odoo-inventory-optimizer`**: Valoración de inventario (`FIFO` / Costo Promedio `AVCO`) y reglas de reabastecimiento.
- **`odoo-edi-connector`** / **`odoo-sales-crm-expert`** / **`odoo-automated-tests`**.

### D. Business Intelligence (BI), FinOps, Pricing & Gobierno Corporativo
- **`boletos-executive-bi-anomaly-narrator`**: Auditoría de KPIs financieros ejecutivos y detección estadística de anomalías (`Z-score` + `Tukey IQR`) en series de recaudación multimoneda.
- **`kpi-dashboard-design`** / **`claude-d3js-skill`**: Diseño de tableros de control financiero y visualizaciones interactivas en D3.js.
- **`aws-cost-operations`** / **`sql-sentinel`**: Optimización de costos Cloud FinOps (AWS) y auditoría de costos de consultas SQL en Data Warehouses.
- **`cro-advisor`** / **`pricing-strategy`** / **`usage-based-pricing`** / **`monetization`** / **`revops`**: Estrategia de precios, empaquetamiento, retención neta de ingresos (`NRR`) y operaciones de ingresos.
- **`latex-document-skill`** / **`docusign-automation`** / **`general-counsel-advisor`** / **`employment-contract-templates`**: Generación de informes financieros en PDF/LaTeX, firma electrónica en DocuSign y revisión de contratos comerciales (`MSA`, `NDA`, `DPA`, *Term Sheets*).

> Consulta el catálogo completo de las 87 skills en **[INDEX.md](./INDEX.md)**.

---

## 5. Verificación y Auditoría Determinista

Para verificar la integridad del plugin, las 87 skills, el buscador `skill-finder` y el sidecar `cfo-cockpit`:

```powershell
python scripts/validate_repo.py
```

---

## Licencia

© 2026 Boletos.la & BNW Corporate Group — Uso Institucional para Finanzas, Contabilidad y Operaciones CFO en Antigravity.
