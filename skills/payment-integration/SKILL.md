---
name: payment-integration
description: >-
  Integrates multi-gateway payment processors (Stripe, PayPal, Bancard vPOS, Pagopar, Transbank Webpay) with idempotent checkout orchestration, raw-body cryptographic webhook verification, zero-decimal currency normalization, PCI DSS v4.0.1 SAQ A controls, and Two-Phase Commit (2PC) rollback compensation. Use when implementing payments, billing, or checkout webhooks.
risk: critical
source: workspace-verified
date_added: '2026-02-27'
---

# Multi-Gateway Payment Integration & 2PC Checkout Orchestration

Production patterns for integrating global and LATAM payment processors (**Stripe**, **PayPal**, **Bancard vPOS**, **Pagopar**, **Transbank Webpay**) with strict webhook signature verification, idempotency, currency unit safety, and PCI DSS v4.0.1 SAQ A scope isolation.

---

## 1. Multi-Gateway Contract & Currency Matrix

| Gateway | Primary Init Endpoint | Wire Amount Rule (`PYG` / `CLP` / `USD`) | Webhook Signature & Auth Mechanism | Compensating Reversal (2PC) |
| :--- | :--- | :--- | :--- | :--- |
| **Stripe** | `POST /v1/payment_intents` / `checkout/sessions` | Integer minor units (`2500` = `$25.00 USD`; **zero-decimal** `150000` = `Gs. 150.000 PYG`) | `Stripe-Signature: t=<ts>,v1=<HMAC-SHA256(secret, t + "." + rawBody)>` (`<= 300s` skew) | `POST /v1/refunds` (`payment_intent`) |
| **PayPal** | `POST /v2/checkout/orders` | Decimal string (`"25.00"` USD) + `currency_code` | `POST /v1/notifications/verify-webhook-signature` -> `verification_status == "SUCCESS"` | `POST /v2/payments/captures/{capture_id}/refund` |
| **Bancard vPOS (`v1.23.1`)** | `POST /vpos/api/0.3/single_buy` | **Always `.2f` decimal string** (`"150000.00"` even for `PYG`) | `MD5(private_key + shop_process_id + "confirm" + amount_2dec + currency)` + `response=="S" && response_code=="00"` | `POST /vpos/api/0.3/single_buy/rollback` *(pre-cuponado only; omits currency/amount; post-cuponado returns `TransactionAlreadyConfirmed`)* |
| **Pagopar** | `POST /api/comercios/2.0/iniciar-transaccion` | Integer/numeric `monto_total` in `PYG` *(serialize whole `PYG` without `.0`, e.g. `"150000"` in SHA-1)* | **Order init**: `SHA1(private_key + str(id_pedido_comercio) + str(monto_total))`; **Incoming webhook**: `SHA1(private_key + str(resultado[0]["hash_pedido"]))` + `POST /api/pedidos/1.1/traer` (`SHA1(private_key + "CONSULTA")`) | `POST /api/pedidos/1.1/reversar` |
| **Transbank Webpay** | `POST /rswebpaytransaction/api/webpay/v1.2/transactions` | Integer `CLP` (`15000`) | Server-to-server `PUT /transactions/{token}` (`Tbk-Api-Key-Id` + `Tbk-Api-Key-Secret`); catch `HTTP 422` -> `GET` status | `POST /transactions/{token}/refunds` |

---

## 2. Canonical Implementation Patterns

### 2.1. Unified Strategy Interface & Outbound Idempotency

```typescript
export interface CreatePaymentInput {
  orderId: string;
  amountMajor: number;
  currency: 'USD' | 'PYG' | 'CLP';
  idempotencyKey: string;
  returnUrl: string;
}

export function formatGatewayWireAmount(
  gateway: 'stripe' | 'paypal' | 'bancard' | 'pagopar' | 'transbank',
  amountMajor: number,
  currency: 'USD' | 'PYG' | 'CLP'
): string | number {
  const zeroDecimal = currency === 'PYG' || currency === 'CLP';
  if (gateway === 'bancard') {
    // Bancard vPOS v1.23.1 mandates .00 even for PYG
    return amountMajor.toFixed(2);
  }
  if (gateway === 'pagopar') {
    // Pagopar PYG must be integer without trailing .0 so SHA1(priv + id + str(monto_total)) matches
    return zeroDecimal ? Math.round(amountMajor) : Number(amountMajor.toFixed(2));
  }
  if (gateway === 'paypal') {
    return zeroDecimal ? String(Math.round(amountMajor)) : amountMajor.toFixed(2);
  }
  if (gateway === 'transbank') {
    return Math.round(amountMajor);
  }
  // Stripe: zero-decimal currencies pass integer as-is; 2-decimal currencies scale x100
  return zeroDecimal ? Math.round(amountMajor) : Math.round(amountMajor * 100);
}
```

### 2.2. Raw-Body Webhook Verification & Atomic Idempotency Lock

Never run JSON body-parsing middleware before verifying HMAC/raw-body signatures, and always lock `(gateway, event_or_order_id)` atomically before executing fulfillment:

```python
import hashlib
import hmac
import time


def verify_hmac_timestamped_webhook(
    raw_body: bytes,
    timestamp_str: str,
    received_hex_sig: str,
    secret: str,
    max_skew_seconds: int = 300,
) -> bool:
    if not timestamp_str.isdigit():
        return False
    if abs(time.time() - int(timestamp_str)) > max_skew_seconds:
        return False
    msg = f"{timestamp_str}.".encode("utf-8") + raw_body
    expected = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received_hex_sig, expected)
```

### 2.3. Two-Phase Commit (2PC) Fulfillment & Automatic Reversal

Whenever a payment webhook or commit confirms funds (`PAID`), wrap downstream inventory/ticket issuance in a compensating transaction block so customers are never left with a captured charge and an unfulfilled order:

```python
def commit_order_2pc(gateway_adapter, fulfillment_service, tx_record) -> dict:
    if tx_record.status == "FULFILLED":
        return {"status": "IDEMPOTENT_OK", "order_id": tx_record.order_id}

    try:
        fulfillment = fulfillment_service.issue_items(tx_record.order_id)
        tx_record.mark_fulfilled(fulfillment.reference_code)
        return {"status": "FULFILLED", "reference": fulfillment.reference_code}
    except Exception as exc:
        reversal = gateway_adapter.reverse_or_refund(tx_record.gateway_tx_id, tx_record.amount)
        fulfillment_service.release_held_inventory(tx_record.hold_id)
        tx_record.mark_rolled_back(reason=str(exc), reversal_id=reversal.id)
        return {"status": "ROLLED_BACK", "order_id": tx_record.order_id, "reversal_id": reversal.id}
```

---

## 3. Progressive Disclosure & Checklist

Consult **[resources/implementation-playbook.md](./resources/implementation-playbook.md)** for database ledger schemas (`payment_transactions` & `webhook_events`), retry/polling state machines, and PCI DSS v4.0.1 Req. 6.4.3 / 11.6.1 checkout hardening.

- **Never Handle Raw Cards**: Keep PAN/CVV strictly inside provider iframes (`Stripe Elements`, `Bancard Checkout JS`, `PayPal SDK`); never log Sensitive Authentication Data (`CVV`, `PIN`, magnetic track).
- **Constant-Time Digest Comparison**: Always use `crypto.timingSafeEqual` / `hmac.compare_digest` on webhook tokens.
- **Environment Isolation**: Reject sandbox/test credentials in production builds at startup.
