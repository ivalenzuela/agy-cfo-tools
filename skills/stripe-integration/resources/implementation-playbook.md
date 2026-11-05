# Stripe PaymentIntents, Checkout, Billing & Webhook Security Playbook

Production engineering playbook for **Stripe API** integrations (`Checkout Sessions`, `PaymentIntents`, `SetupIntents`, `Stripe Billing`, `Stripe Connect`, and `Webhooks`) with strict idempotency, `t=/v1=` cryptographic verification, and PCI DSS v4.0.1 SAQ A compliance.

---

## 1. Core Stripe Primitives & Selection Matrix

| Primitive | Endpoint | PCI Scope | Primary Use Case & Contract Invariants |
| :--- | :--- | :--- | :--- |
| **Checkout Session** | `POST /v1/checkout/sessions` | **SAQ A** | Hosted or embedded Stripe Checkout (`mode: "payment" \| "subscription" \| "setup"`). Always fulfill via `checkout.session.completed` / `payment_intent.succeeded` webhooks, never solely via `success_url` redirect. |
| **PaymentIntent** | `POST /v1/payment_intents` | **SAQ A** *(with Elements)* | Custom checkout UI with `automatic_payment_methods[enabled]=true` and dynamic 3DS2 / SCA challenge handling via `stripe.confirmPayment()`. |
| **SetupIntent** | `POST /v1/setup_intents` | **SAQ A** *(with Elements)* | Tokenizes and vaults off-session payment methods (`pm_*`) with 3DS authentication without placing an immediate charge. |
| **Subscriptions** | `POST /v1/subscriptions` | **SAQ A** | Create with `payment_behavior="default_incomplete"`, `payment_settings={"save_default_payment_method": "on_subscription"}`, and reconcile via `invoice.paid` & `invoice.payment_failed`. |
| **Refunds** | `POST /v1/refunds` | N/A | Pass `payment_intent: "pi_..."` and optional minor-unit `amount` (`cents`; integer unit for zero-decimal currencies like `PYG`, `CLP`, `JPY`). |

---

## 2. Minor Units & Zero-Decimal Currency Rules

Stripe expects `amount` / `unit_amount` as a positive integer in the **smallest currency unit**:
- **2-Decimal Currencies (`USD`, `EUR`, `BRL`, `ARS`)**: Multiply by `100` (`$25.00 USD` -> `2500`).
- **Zero-Decimal Currencies (`PYG`, `CLP`, `JPY`, `KRW`)**: Pass the exact integer amount **without** multiplying by `100` (`Gs. 150.000 PYG` -> `150000`, `$15.000 CLP` -> `15000`). Multiplying zero-decimal currencies by 100 overcharges customers 100x.

---

## 3. Cryptographic Webhook Verification (`Stripe-Signature`) & Idempotency

1. **Preserve Raw Request Bytes**:
   - In Express (`express.raw({ type: 'application/json' })`), Next.js App Router (`await req.text()`), or Flask (`request.get_data()`), pass the **exact unparsed raw bytes** to `stripe.Webhook.construct_event(raw_body, sig_header, STRIPE_WEBHOOK_SECRET)`.
2. **Exact Wire Formula (`Stripe-Signature: t=<ts>,v1=<hex>`)**:
   - Parse `t` (Unix timestamp) and all `v1` hex digests (multiple `v1` values appear during endpoint secret rotation).
   - Reject timestamps where `|now - t| > 300` seconds (replay protection).
   - Compute `expected = HMAC_SHA256(whsec_secret, f"{t}.{raw_body_utf8}")` and match against `v1` list using constant-time `hmac.compare_digest` / `crypto.timingSafeEqual`.
3. **Idempotency Keys (Outbound & Inbound)**:
   - **Outbound**: Pass `Idempotency-Key: <deterministic-uuid-per-order-step>` on every `POST /v1/*` mutation (`24h` Stripe retention window) so network retries never double-charge.
   - **Inbound**: Record `event.id` (`evt_...`) in a unique DB constraint before side effects; handle out-of-order delivery (`payment_intent.succeeded` arriving before `checkout.session.completed`) gracefully by keying fulfillment on `payment_intent_id` / `order_id`.

---

## 4. Production Readiness Checklist

- [ ] `STRIPE_SECRET_KEY` (`sk_live_...` / `rk_live_...`) and `STRIPE_WEBHOOK_SECRET` (`whsec_...`) loaded strictly from server environment variables; only `pk_...` exposed to client bundles.
- [ ] Zero-decimal currencies (`PYG`, `CLP`, `JPY`) normalized without `x100` scaling.
- [ ] Webhook handler reads raw request bytes, verifies `Stripe-Signature` (`t=` + `v1=`), deduplicates `evt_*`, and returns `HTTP 200` within `< 3s`.
- [ ] Two-Phase Commit (2PC) compensation invokes `stripe.Refund.create(payment_intent=pi_id)` automatically if downstream inventory or ticket issuance fails after capture.
- [ ] Checkout page enforces PCI DSS v4.0.1 **Req. 6.4.3** CSP (`script-src https://js.stripe.com; frame-src https://js.stripe.com https://hooks.stripe.com; connect-src https://api.stripe.com`).
