# PayPal Orders v2, Subscriptions v1 & Webhook Verification Playbook

Production implementation playbook for **PayPal REST APIs** (`Orders v2`, `Payments v2`, `Subscriptions v1`, and `Webhooks v1`) with strict idempotency, cryptographic signature verification, and PCI DSS v4.0.1 SAQ A compliance.

---

## 1. Endpoint & Authentication Matrix

| Capability | Method & Endpoint (`api-m.paypal.com` / `api-m.sandbox.paypal.com`) | Idempotency / Auth Header | Key Contract Rules |
| :--- | :--- | :--- | :--- |
| **OAuth 2.0 Token** | `POST /v1/oauth2/token` | HTTP Basic `client_id:client_secret` | Cache `access_token` in memory/Redis for `expires_in - 120` seconds |
| **Create Order** | `POST /v2/checkout/orders` | `Bearer <token>` + `PayPal-Request-Id` | Specify `intent: "CAPTURE"` (or `"AUTHORIZE"`), explicit `currency_code`, and 2-decimal string `value` (`"25.00"`; `"0"` decimals for zero-decimal currencies) |
| **Capture Order** | `POST /v2/checkout/orders/{id}/capture` | `Bearer <token>` + `PayPal-Request-Id` | Assert `status == "COMPLETED"` and extract `purchase_units[0].payments.captures[0].id` (used for refunds, **not** `order.id`) |
| **Refund Capture** | `POST /v2/payments/captures/{capture_id}/refund` | `Bearer <token>` + `PayPal-Request-Id` | Pass `{}` for full refund or `{"amount": {"value": "10.00", "currency_code": "USD"}}` for partial refund |
| **Subscriptions** | `POST /v1/billing/plans` -> `POST /v1/billing/subscriptions` | `Bearer <token>` + `PayPal-Request-Id` | Reconcile lifecycle via `BILLING.SUBSCRIPTION.ACTIVATED`, `PAYMENT.SALE.COMPLETED`, and `BILLING.SUBSCRIPTION.CANCELLED` |
| **Verify Webhook** | `POST /v1/notifications/verify-webhook-signature` | `Bearer <token>` | Must return `{"verification_status": "SUCCESS"}` before mutating order state |

---

## 2. Server-Side Order Creation & Capture Flow (Orders v2)

Never create high-value orders purely client-side (`actions.order.create` in browser JS can be tampered with if amounts are not re-verified server-side). Always create and capture on the backend:

1. **Browser JS SDK** calls `POST /api/paypal/create-order` with `{ cartId }`.
2. **Backend** calculates authoritative price from DB, calls `POST /v2/checkout/orders` with `PayPal-Request-Id: order-init-<cartId>`, and returns `{ id: paypalOrder.id }`.
3. **Buyer** approves inside the isolated PayPal modal/iframe (PCI DSS v4.0.1 SAQ A).
4. **Browser `onApprove`** calls `POST /api/paypal/capture-order` with `{ orderID }`.
5. **Backend** executes `POST /v2/checkout/orders/{orderID}/capture`, verifies `captured_amount == expected_cart_total` and `currency_code == expected_currency`, persists `capture_id` idempotently, and fulfills the order (or executes compensating refund if downstream inventory/GDS emission fails).

---

## 3. Webhook & Legacy IPN Security Invariants

### 3.1. REST Webhooks (Recommended)
1. **Verify Transmission Headers**: Forward `PAYPAL-AUTH-ALGO`, `PAYPAL-CERT-URL`, `PAYPAL-TRANSMISSION-ID`, `PAYPAL-TRANSMISSION-SIG`, `PAYPAL-TRANSMISSION-TIME`, configured `PAYPAL_WEBHOOK_ID`, and the parsed event JSON to `POST /v1/notifications/verify-webhook-signature` (or verify locally via CRC32 of raw body + X.509 cert restricted to `*.paypal.com`).
2. **Deduplicate by `event.id`**: Insert `event.id` (`WH-...`) into an atomic unique index (`webhook_events.event_id`) before fulfillment. Return `HTTP 200` immediately for duplicates.
3. **Core Events to Handle**:
   - `PAYMENT.CAPTURE.COMPLETED` — Mark order paid if browser `onApprove` disconnected.
   - `PAYMENT.CAPTURE.DENIED` / `PAYMENT.CAPTURE.REVERSED` — Revoke entitlement / release inventory.
   - `CUSTOMER.DISPUTE.CREATED` — Alert risk/finance queue with capture metadata.

### 3.2. Legacy IPN (Only for Classic Integrations)
- Post the exact raw form body back to `https://ipnpb.paypal.com/cgi-bin/webscr` (or `ipnpb.sandbox.paypal.com`) prefixed with `cmd=_notify-validate`.
- Require exact response body `"VERIFIED"`, verify `receiver_email` matches your merchant account, check `mc_gross` and `mc_currency`, and deduplicate on `txn_id`.

---

## 4. Production Readiness Checklist

- [ ] Deprecated `paypalrestsdk` (v1 Payments) completely avoided in favor of **Orders v2** (`/v2/checkout/orders`).
- [ ] `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, and `PAYPAL_WEBHOOK_ID` loaded strictly from environment variables (`sandbox` vs `live` isolated).
- [ ] Every mutating `POST` includes a deterministic `PayPal-Request-Id` idempotency header.
- [ ] Refunds target `capture_id` (`/v2/payments/captures/{capture_id}/refund`), never `order_id`.
- [ ] Checkout host page enforces PCI DSS v4.0.1 **Req. 6.4.3** CSP (`script-src https://www.paypal.com https://www.paypalobjects.com; frame-src https://www.paypal.com`).
