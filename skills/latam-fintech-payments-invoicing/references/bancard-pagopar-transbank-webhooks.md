# Deep Reference: Webhook Idempotency, Timeout Recovery, 2PC Compensation & PCI DSS v4.0.1

Production resilience patterns for handling asynchronous webhooks, network partitions, inventory race conditions, and payment page script integrity across **Bancard vPOS / VentasQR**, **Pagopar**, **AdamsPay**, and **Transbank Webpay Plus**.

---

## 1. Idempotent Webhook Processing & Timeout SLAs

### 1.1. Constant-Time Signature Verification First
- Reject forged callbacks (`HTTP 401` / `HTTP 403`) before acquiring DB locks:
  - **Bancard vPOS**: `md5(private_key + shop_process_id + "confirm" + amount + currency)` verified via `crypto.timingSafeEqual` / `hmac.compare_digest` + exact `amount` & `currency` match against persisted order.
  - **Pagopar**: `sha1(private_key + resultado[0].hash_pedido)`.
  - **AdamsPay v1**: Header `x-adams-notify-hash` vs `md5("adams" + raw_body_utf8 + webhook_secret)` (preserve raw body bytes prior to JSON parsing).

### 1.2. Pessimistic Locking & Gateway Timeout Budgets
- Acquire row-level lock (`SELECT ... FOR UPDATE` on `shop_process_id` / `hash_pedido` / `docId` / `buy_order`). If already in a terminal state (`TICKET_ISSUED`, `PAYMENT_REVERSED`, `PAYMENT_REJECTED`), return `HTTP 200 {"status": "success"}` immediately.
- **Bancard Webhook Timeout**: Bancard enforces a hard **30-second HTTP timeout** on merchant confirmation webhooks, with a recommended merchant target SLA of **`< 5 seconds`**. Cap downstream GDS `Venta3` calls so that slow/hung GDS calls trigger deterministic recovery rather than unacknowledged socket drops.

---

## 2. 10-Minute Timeout Polling & Orphaned Payment Recovery

Passengers frequently close mobile browsers after scanning PY-QR or approving Zimple/Tigo Money USSD prompts. Never expire a 10-minute (`600s`) GDS seat lock without polling the gateway first:
- **Polling Schedule**: `T + 15s`, `T + 45s`, `T + 120s`, `T + 300s`, and `T + 540s` (`60s` prior to seat lock expiry).
- **Bancard vPOS**: `POST /vpos/api/0.3/single_buy/confirmations` (`token = md5(priv + shop_process_id + "get_confirmation")`). If `confirmation.response === "S" && confirmation.response_code === "00"`, feed into the exact same 2PC commit/rollback handler.
- **Pagopar**: `POST /api/pedidos/1.1/traer` (`token = sha1(priv + "CONSULTA")`).
- **Transbank Webpay Plus (HTTP 422 Double-Commit Recovery)**: Browser refresh or double redirect on `/api/webpay/commit` causes `PUT /rswebpaytransaction/api/webpay/v1.2/transactions/{token}` to return **HTTP 422** (*transaction already locked/processed*). Always catch HTTP 422 and fall back to `GET /rswebpaytransaction/api/webpay/v1.2/transactions/{token}`: if `status === "AUTHORIZED" && response_code === 0`, return the already-emitted tickets idempotently.

---

## 3. Two-Phase Commit (2PC) Rollback & Post-Cuponado Escalation

1. **Same-Day Pre-Cuponado Rollback**:
   - On GDS ticket emission failure or late webhook arriving after `order.status === "EXPIRED"`, immediately call `POST /vpos/api/0.3/single_buy/rollback` (`token = md5(priv + shop_process_id + "rollback" + "0.00")` — **no currency** in token; also cancels unconfirmed/confirmed preauthorizations), VentasQR `PUT .../selling/payments/revert/{hook_alias}`, Caja POS Android `POST /pos/anulacion`, or Transbank `POST .../refunds` (when paid via Webpay).
2. **Post-Cuponado / `TransactionAlreadyConfirmed` Escalation (`v1.23.1` pp. 51, 54)**:
   - If Bancard returns `messages[0].key === "TransactionAlreadyConfirmed"` (*"El pago ya fue confirmado"*; also check `"PaymentAlreadyConfirmedError"` defensively), the transaction has already been couponed/settled and **cannot** be rolled back via vPOS REST (note: `/vpos/api/0.3/single_buy/charge_back` does not exist in the official Bancard vPOS v1.23.1 specification). Immediately flag `ROLLBACK_MANUAL_REQUIRED` for commercial annulment in the Bancard Merchant Portal (`https://comercios.bancard.com.py` -> *Soporte / Anulaciones*), invoke `POST /vpos/api/0.3/billing/cancel` (`md5(priv + shop_process_id + "billing_cancel")`) if Bancard electronic billing was attached within `< 24h`, and cancel the SIFEN `iTiDE=01` invoice via `evento.wsdl` (`< 48h`) or emit a SIFEN Credit Note (`iTiDE=05`) thereafter.

---

## 4. PCI DSS v4.0.1 Payment Page Script Integrity (Req. 6.4.3 & 11.6.1)

Even under **SAQ A / SAQ A-EP** using hosted iframes (`bancard-checkout-4.0.0.js` / legacy `2.0.0.js`, Pagopar, Stripe.js, PayPal SDK), **PCI DSS v4.0.1** enforces two mandatory technical controls on the parent checkout page:
1. **Requirement 6.4.3 (Script Authorization & Integrity)**: Maintain a written inventory and business justification for every script loaded on `/checkout`, enforce strict Content Security Policy (`script-src`, `frame-src`, `connect-src` allowlisting only `https://vpos.infonet.com.py`), and apply Subresource Integrity (`integrity="sha384-..."`) on static scripts.
2. **Requirement 11.6.1 (Tamper & Change Detection)**: Deploy automated HTTP header (`Content-Security-Policy`, `X-Frame-Options`) and DOM script-hash monitoring on the live payment page to alert within minutes on unauthorized script injection (Magecart / e-skimming defense).
