# Financial Security, Audit & Operational Hygiene Guidelines

- **Zero-Plaintext Secrets**: Never log, print, or commit `.env`, `.env.credentials`, API tokens, bank credentials, or X.509 `.p12` private keys into source files or `mcp_config.json`.
- **PCI-DSS v4.0.1 & PII Hygiene**: Never expose raw PANs, CVVs, `authorization_number`, `security_information`, or unmasked personal tax/phone identifiers in public logs or client error screens.
- **Destructive Command Protection**: Block unverified destructive SQL DDL or unbacked ledger mutations in production databases.
- **Audit Trail & Ledger Immutability**: Preserve double-entry accounting invariants (`Debits == Credits`) and cryptographic hash chains (`SHA-256`) on financial approval and reconciliation records.
