# Multi-Gateway Payment Orchestration, Idempotency & 2PC Playbook

Architectural reference for production payment orchestration across global (**Stripe**, **PayPal**) and Latin American (**Bancard vPOS**, **Pagopar**, **Transbank Webpay Plus**) gateways.

---

## 1. Transactional Payment State Machine & Database Schema

Every payment lifecycle must follow a deterministic state machine backed by ACID row-level locking (`SELECT ... FOR UPDATE`) and an immutable audit ledger:

```text
CREATED -> PENDING_USER_ACTION -> AUTHORIZED_OR_PAID -> FULFILLED
                                         |                  |
                                  (2PC Failure)       (Customer Refund)
                                         v                  v
                                    ROLLED_BACK         REFUNDED
```

### Canonical SQL Ledger Schema (`payment_transactions` & `webhook_events`)

```sql
CREATE TABLE payment_transactions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    gateway VARCHAR(32) NOT NULL,               -- 'bancard' | 'transbank' | 'stripe' | 'paypal' | 'pagopar'
    shop_process_id BIGINT UNSIGNED NULL UNIQUE,-- Bancard numeric shop_process_id
    gateway_tx_id VARCHAR(128) NULL,            -- Stripe pi_*, PayPal capture_id, Transbank token_ws
    currency CHAR(3) NOT NULL,                  -- 'PYG' | 'CLP' | 'USD'
    amount_minor BIGINT NOT NULL,               -- Exact integer minor units / Gs.
    wire_amount VARCHAR(32) NOT NULL,           -- Exact string sent on wire (e.g. '150000.00' for Bancard)
    status VARCHAR(32) NOT NULL DEFAULT 'CREATED',
    authorization_code VARCHAR(32) NULL,        -- Stored server-side ONLY; never leaked on declined UI
    response_code VARCHAR(16) NULL,
    hold_id VARCHAR(64) NULL,                   -- Downstream inventory / GDS seat hold reference
    fulfillment_ref VARCHAR(128) NULL,          -- Emitted ticket / invoice CDC
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_gateway_order (gateway, order_id)
);

CREATE TABLE webhook_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    gateway VARCHAR(32) NOT NULL,
    external_event_id VARCHAR(128) NOT NULL,    -- Stripe evt_*, PayPal WH-*, or deterministic hash
    raw_payload JSON NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_gateway_event (gateway, external_event_id)
);
```

---

## 2. Critical Cross-Gateway Edge Cases

1. **Currency Formatting & Signature Mismatches**:
   - **Bancard vPOS (`v1.23.1`)**: Even though Paraguayan Guaraní (`PYG`) has zero circulating subunits, Bancard vPOS mandates 2 decimal places (`"150000.00"`) in `single_buy`, `charge`, and `confirm` MD5 token calculation, whereas `single_buy/rollback` omits `currency` and `amount` (`md5(private_key + shop_process_id + "rollback" + "0.00")`, pre-cuponado only; post-cuponado returns `"TransactionAlreadyConfirmed"`) and `preauthorizations/confirm` omits `amount`/`currency` from its MD5 token (`md5(private_key + shop_process_id + "pre-authorization-confirm")`).
   - **Pagopar**: Outbound `2.0/iniciar-transaccion` signs `SHA1(private_key + str(id_pedido_comercio) + str(monto_total))` (whole `PYG` floats like `150000.0` MUST serialize without `.0` as `"150000"`), whereas incoming webhooks sign **`SHA1(private_key + str(resultado[0]["hash_pedido"]))`** and server-to-server `1.1/traer` confirmation signs `SHA1(private_key + "CONSULTA")`.
   - **Stripe**: Treats `PYG` and `CLP` as zero-decimal currencies (`150000`), while `USD` and `BRL` are 2-decimal (`2500` = `$25.00`).
2. **Double-Redirect & Concurrent Webhook Races**:
   - In **Transbank Webpay Plus**, a user refreshing the return URL triggers a second `PUT /transactions/{token}`, causing Transbank to return **HTTP 422**. Catch `HTTP 422`, fall back to `GET /transactions/{token}`, and if `status === "AUTHORIZED"` (`response_code === 0`), return the already-fulfilled order idempotently.
   - In **Stripe / Bancard / PayPal**, the browser return redirect and the asynchronous webhook often arrive within milliseconds of each other. Acquire a DB row lock (`FOR UPDATE`) on `payment_transactions` before invoking downstream fulfillment so items/tickets are never emitted twice.
3. **In-App Browser (WebView) 3DS2 Failures**:
   - Instagram, Facebook, and TikTok embedded WebViews frequently block cross-domain 3DS2 challenge cookies/popups (`Charge3DS` / `hooks.stripe.com`). Detect embedded WebViews on checkout entry and prompt escape to native Safari/Chrome (or offer interoperable QR / Apple Pay / Google Pay).

---

## 3. PCI DSS v4.0.1 & Security Checklist

- [ ] **SAQ A Scope Isolation**: Card inputs rendered exclusively inside provider iframes or hosted redirects.
- [ ] **Req. 6.4.3 & 11.6.1**: Checkout route serves strict `Content-Security-Policy`, maintains an authorized script inventory with written justification, and runs automated tamper detection on HTTP headers and DOM `<script>` tags.
- [ ] **Zero Plaintext Secrets**: All API keys, private keys, and webhook secrets injected via environment variables (`process.env` / `os.environ`).
- [ ] **Fast Webhook ACK**: Verify cryptographic signature against raw bytes, persist/lock idempotently, and respond within gateway timeout SLAs (`< 3s` Stripe/PayPal, `< 5s` Bancard vPOS).
