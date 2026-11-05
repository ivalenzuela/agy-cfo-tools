# PCI DSS v4.0.1 Implementation Playbook

Authoritative engineering playbook for achieving and maintaining **PCI DSS v4.0.1** compliance across web checkouts (`Next.js` App Router / AWS Amplify), payment orchestrators (`boletos-la-backend-bancard`), and unattended terminal kiosks (`Bancard Caja POS Android 2.0` / `Transbank POS`).

---

## 1. Architecture Pattern: Isolating the Cardholder Data Environment (CDE) for SAQ A

To minimize PCI DSS scope from ~300 controls (**SAQ D**) to **SAQ A**, enforce strict CDE isolation:

1. **Zero Raw Card Data on Merchant Servers**:
   - **Bancard vPOS 2.0**: Backend calls `POST /vpos/api/0.3/single_buy` or `POST /vpos/api/0.3/cards/new` and returns only `process_id`. The browser renders `Bancard.Checkout.createForm('iframe-container', process_id)` (`bancard-checkout-4.0.0.js`, min width `320px`; `2.0.0.js` legacy) inside an isolated `https://vpos.infonet.com.py` `<iframe>`.
   - **Saved Cards (Bancard Tokenization)**: Backend fetches short-lived `alias_token` (**15-minute TTL**, max 5 cards per user) via `POST /vpos/api/0.3/users/{user_id}/cards` and charges via `POST /vpos/api/0.3/charge` (including `"extra_response_attributes": ["confirmation.process_id"]` for `Charge3DS`) — never storing PAN or CVV.
   - **Transbank Webpay Plus**: Browser redirects directly to `url` + `token_ws` hosted on `webpay3g.transbank.cl`.
   - **Stripe / PayPal**: Card inputs stay strictly inside Stripe Elements (`js.stripe.com/v3/`) or PayPal Smart Payment Buttons (`www.paypal.com/sdk/js`).
2. **Prohibited Sensitive Authentication Data (SAD — Req. 3.3.1)**:
   - Never log, cache in Redis, store in MySQL (`vpos_audit`), or send to error trackers (`Sentry`) any `CVV2`/`CVC2`/`CID`, full magnetic stripe track data, or PIN blocks.
   - Even in **SAQ D** vaults, storing `CVV` after transaction authorization is an automatic critical audit failure.

---

## 2. PCI DSS v4.0.1 Requirements 6.4.3 & 11.6.1 (Anti-Skimming / Magecart Controls)

Effective March 31, 2025, **PCI DSS v4.0.1** mandates explicit browser-side script governance and tamper detection on any merchant page that hosts or frames a payment form:

### 2.1. Requirement 6.4.3 — Payment Page Script Management
Every script executing in the checkout page context (`/checkout`, `/paraguay/pago`) must satisfy three controls:
1. **Explicit Authorization & Written Justification**:
   - Maintain a version-controlled manifest (`checkout-script-inventory.json`) listing every first-party and third-party `<script>` allowed on the payment route, its owner, and why it is necessary for payment execution.
   - **Strip Marketing Pixels from `/checkout`**: Never load third-party ad trackers, session-replay injectors, or unverified tag-manager custom HTML tags inside the payment frame host page.
2. **Script Integrity Assurance**:
   - Apply **Subresource Integrity (`integrity="sha384-..." crossorigin="anonymous"`)** to all versioned static scripts.
   - For dynamic gateway loaders (`bancard-checkout-4.0.0.js`, `js.stripe.com/v3/`), enforce strict origin pinning + per-request cryptographic CSP `nonce-<random128bit>`.
3. **Strict `Content-Security-Policy` (CSP)**:
   ```http
   Content-Security-Policy:
     default-src 'self';
     script-src 'self' 'nonce-{RANDOM_NONCE}' https://vpos.infonet.com.py https://js.stripe.com https://www.paypal.com;
     frame-src https://vpos.infonet.com.py https://js.stripe.com https://hooks.stripe.com https://www.paypal.com https://webpay3g.transbank.cl;
     connect-src 'self' https://vpos.infonet.com.py https://api.stripe.com https://www.paypal.com;
     object-src 'none';
     base-uri 'self';
     frame-ancestors 'none';
     report-uri /api/security/csp-violations;
   ```

### 2.2. Requirement 11.6.1 — Change-and-Tamper-Detection Mechanism
1. **Automated Inspection Cadence**: Run an automated headless browser check (or synthetic monitor) **at least once every 7 days** (recommended: hourly + on every CI/CD deployment) against the live `/checkout` URL.
2. **Evaluated Artifacts**:
   - **HTTP Response Headers**: Assert exact presence and policy directives of `Content-Security-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, and `X-Frame-Options: DENY`.
   - **Evaluated DOM Scripts**: Hash every inline `<script>` body and compare every external `<script src="...">` against the authorized Req. 6.4.3 inventory.
3. **Alerting**: Immediately page security operations if an unknown `<script src>` appears, an inline script hash drifts without a signed release, or `Content-Security-Policy` is weakened/stripped.

---

## 3. Cryptographic & Webhook Verification Standards

| Control Area | Mandatory Implementation Standard | Common Anti-Pattern to Reject |
| :--- | :--- | :--- |
| **Webhook Signature Comparison** | Constant-time `crypto.timingSafeEqual` (Node.js) / `hmac.compare_digest` (Python) over exact wire-protocol digest (`MD5` for Bancard vPOS, `SHA-1` for Pagopar, `HMAC-SHA256` with `t=` timestamp for Stripe) | Using `===` or `==` string comparison (timing oracle) or skipping token check |
| **Encryption at Rest (Req. 3.5.1)** | `AES-256-GCM` with unique 12-byte (`96-bit`) cryptographic random nonce per record and envelope key encryption via AWS KMS / Vault | `AES-ECB`, static IVs, hardcoded keys in source code, or plain `SHA-256` without salt/key |
| **PAN Display Masking (Req. 3.4.1)** | Truncate/mask to at most `BIN (first 6)` + `Last 4` (`456789******1234`); prefer `**** 1234` in customer-facing receipts and emails | Logging full 16-digit `card_number` in Express request body middleware |
| **Bancard Public UI Hygiene & MC MAC 03/21** | Strip all **4 prohibited Bancard fields** (`authorization_number`, `response_code`, `extended_response_description`, `security_information`) from **all** public browser responses (approved & declined), storing them strictly in `vpos_audit`; throttle retries (`7` declines/24h or `35`/30d blocks Mastercard for 30 days) | Returning `authorization_number`, `response_code`, `extended_response_description`, or `security_information` in public JSON payloads |
| **Physical POS Terminals (Req. 9.5)** | Maintain serial number inventory of Android SmartPOS / Pinpad devices, restrict LAN port `:3000` (`/pos/*`) to the kiosk VLAN, and verify physical tamper seals | Exposing SmartPOS `:3000/pos/*` HTTP endpoints on public Wi-Fi networks |

---

## 4. Complete 12-Requirement Verification Checklist

- [ ] **Req. 1 & 2 (Network & Hardening)**: Payment backend (`backend-vpos`) and RDS (`vpos_audit`) isolated in private VPC/security groups; zero vendor default credentials.
- [ ] **Req. 3 (Stored Account Data)**: Zero `CVV`, `PIN`, or magnetic track storage anywhere; PANs masked (`first 6 / last 4`) in logs and UI.
- [ ] **Req. 4 (Transit Security)**: TLS 1.2+ enforced with HSTS; mTLS `.p12` certificates stored outside git (`chmod 600`).
- [ ] **Req. 5 & 6 (Secure Software & Scripts)**: Dependency vulnerability scanning enabled; **Req. 6.4.3** checkout script inventory + strict CSP active.
- [ ] **Req. 7 & 8 (Access & MFA)**: Least-privilege RBAC on `vpos_audit` and merchant portals; MFA mandatory for administrative access.
- [ ] **Req. 9 (Physical Security)**: Terminal kiosk enclosures locked; SmartPOS devices inventoried and VLAN-isolated.
- [ ] **Req. 10 (Audit Trails)**: Immutable UTC audit logs (`vpos_audit`) capturing `shop_process_id`, user/actor, timestamp, action, and status without leaking SAD/PAN.
- [ ] **Req. 11 (Testing & Tamper Detection)**: Quarterly vulnerability scans + **Req. 11.6.1** automated checkout header/script tamper detection active.
- [ ] **Req. 12 (Governance & Incident Response)**: Documented incident response runbook covering key rotation, webhook secret compromise, and acquirer notification.
