---
name: paypal-integration
description: "Master PayPal payment integration including Express Checkout, IPN handling, recurring billing, and refund workflows."
risk: critical
source: community
date_added: "2026-02-27"
---

# PayPal Integration

Master PayPal payment integration including Express Checkout, IPN handling, recurring billing, and refund workflows.

## Do not use this skill when

- The task is unrelated to paypal integration
- You need a different domain or tool outside this scope

## Instructions

- Clarify goals, constraints, and required inputs.
- Apply relevant best practices and validate outcomes.
- Provide actionable steps and verification.
- If detailed examples are required, open `resources/implementation-playbook.md`.

## Use this skill when

- Integrating PayPal as a payment option
- Implementing express checkout flows
- Setting up recurring billing with PayPal
- Processing refunds and payment disputes
- Handling PayPal webhooks (IPN)
- Supporting international payments
- Implementing PayPal subscriptions

## Core Concepts

### 1. Payment Products
**PayPal Checkout**
- One-time payments
- Express checkout experience
- Guest and PayPal account payments

**PayPal Subscriptions**
- Recurring billing
- Subscription plans
- Automatic renewals

**PayPal Payouts**
- Send money to multiple recipients
- Marketplace and platform payments

### 2. Integration Methods
**Client-Side (JavaScript SDK)**
- Smart Payment Buttons
- Hosted payment flow
- Minimal backend code

**Server-Side (REST API)**
- Full control over payment flow
- Custom checkout UI
- Advanced features

### 3. IPN (Instant Payment Notification)
- Webhook-like payment notifications
- Asynchronous payment updates
- Verification required

## Quick Start

```javascript
// Frontend - PayPal Smart Buttons
<div id="paypal-button-container"></div>

<script src="https://www.paypal.com/sdk/js?client-id=YOUR_CLIENT_ID&currency=USD"></script>
<script>
  paypal.Buttons({
    createOrder: function(data, actions) {
      return actions.order.create({
        purchase_units: [{
          amount: {
            value: '25.00'
          }
        }]
      });
    },
    onApprove: function(data, actions) {
      return actions.order.capture().then(function(details) {
        // Payment successful
        console.log('Transaction completed by ' + details.payer.name.given_name);

        // Send to backend for verification
        fetch('/api/paypal/capture', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({orderID: data.orderID})
        });
      });
    }
  }).render('#paypal-button-container');
</script>
```

```python
# Backend — PayPal Orders v2 Capture & Cryptographic Webhook Signature Verification
import os
import requests

PAYPAL_BASE_URL = (
    "https://api-m.paypal.com"
    if os.environ.get("PAYPAL_MODE") == "live"
    else "https://api-m.sandbox.paypal.com"
)


def get_paypal_access_token() -> str:
    resp = requests.post(
        f"{PAYPAL_BASE_URL}/v1/oauth2/token",
        headers={"Accept": "application/json"},
        data={"grant_type": "client_credentials"},
        auth=(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_CLIENT_SECRET"]),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def capture_paypal_order_v2(order_id: str, idempotency_key: str) -> dict:
    """Captures an approved PayPal v2 Order idempotently via PayPal-Request-Id."""
    token = get_paypal_access_token()
    resp = requests.post(
        f"{PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/capture",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "PayPal-Request-Id": idempotency_key,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def verify_paypal_webhook_signature(headers: dict, webhook_event: dict) -> bool:
    """Verifies PayPal REST Webhook authenticity via /v1/notifications/verify-webhook-signature."""
    token = get_paypal_access_token()
    verify_payload = {
        "auth_algo": headers.get("PAYPAL-AUTH-ALGO"),
        "cert_url": headers.get("PAYPAL-CERT-URL"),
        "transmission_id": headers.get("PAYPAL-TRANSMISSION-ID"),
        "transmission_sig": headers.get("PAYPAL-TRANSMISSION-SIG"),
        "transmission_time": headers.get("PAYPAL-TRANSMISSION-TIME"),
        "webhook_id": os.environ["PAYPAL_WEBHOOK_ID"],
        "webhook_event": webhook_event,
    }
    resp = requests.post(
        f"{PAYPAL_BASE_URL}/v1/notifications/verify-webhook-signature",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        json=verify_payload,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("verification_status") == "SUCCESS"
```

## Express Checkout Implementation

### Server-Side Order Creation
```python
import requests
import json

class PayPalClient:
    def __init__(self, client_id, client_secret, mode='sandbox'):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = 'https://api-m.sandbox.paypal.com' if mode == 'sandbox' else 'https://api-m.paypal.com'
        self.access_token = self.get_access_token()

    def get_access_token(self):
        """Get OAuth access token."""
        url = f"{self.base_url}/v1/oauth2/token"
        headers = {"Accept": "application/json", "Accept-Language": "en_US"}

        response = requests.post(
            url,
            headers=headers,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=15,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def create_order(self, amount, currency="USD", request_id=None):
        """Create a PayPal order with optional PayPal-Request-Id idempotency header."""
        url = f"{self.base_url}/v2/checkout/orders"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }
        if request_id:
            headers["PayPal-Request-Id"] = str(request_id)

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": currency,
                    "value": str(amount),
                }
            }],
        }

        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    def capture_order(self, order_id, request_id=None):
        """Capture payment for an order with optional PayPal-Request-Id idempotency header."""
        url = f"{self.base_url}/v2/checkout/orders/{order_id}/capture"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }
        if request_id:
            headers["PayPal-Request-Id"] = str(request_id)

        response = requests.post(url, headers=headers, json={}, timeout=15)
        response.raise_for_status()
        return response.json()

    def get_order_details(self, order_id):
        """Get order details."""
        url = f"{self.base_url}/v2/checkout/orders/{order_id}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }

        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
```

## IPN (Instant Payment Notification) Handling

### IPN Verification and Processing
```python
from flask import Flask, request
import requests
from urllib.parse import parse_qs

app = Flask(__name__)

@app.route('/ipn', methods=['POST'])
def handle_ipn():
    """Handle PayPal IPN notifications."""
    # Get IPN message
    ipn_data = request.form.to_dict()

    # Verify IPN with PayPal
    if not verify_ipn(ipn_data):
        return 'IPN verification failed', 400

    # Process IPN based on transaction type
    payment_status = ipn_data.get('payment_status')
    txn_type = ipn_data.get('txn_type')

    if payment_status == 'Completed':
        handle_payment_completed(ipn_data)
    elif payment_status == 'Refunded':
        handle_refund(ipn_data)
    elif payment_status == 'Reversed':
        handle_chargeback(ipn_data)

    return 'IPN processed', 200

def verify_ipn(ipn_data):
    """Verify IPN message authenticity."""
    # Add 'cmd' parameter
    verify_data = ipn_data.copy()
    verify_data['cmd'] = '_notify-validate'

    # Send back to PayPal for verification
    paypal_url = 'https://ipnpb.sandbox.paypal.com/cgi-bin/webscr'  # or production URL

    response = requests.post(paypal_url, data=verify_data)

    return response.text == 'VERIFIED'

def handle_payment_completed(ipn_data):
    """Process completed payment."""
    txn_id = ipn_data.get('txn_id')
    payer_email = ipn_data.get('payer_email')
    mc_gross = ipn_data.get('mc_gross')
    item_name = ipn_data.get('item_name')

    # Check if already processed (prevent duplicates)
    if is_transaction_processed(txn_id):
        return

    # Update database
    # Send confirmation email
    # Fulfill order
    print(f"Payment completed: {txn_id}, Amount: ${mc_gross}")

def handle_refund(ipn_data):
    """Handle refund."""
    parent_txn_id = ipn_data.get('parent_txn_id')
    mc_gross = ipn_data.get('mc_gross')

    # Process refund in your system
    print(f"Refund processed: {parent_txn_id}, Amount: ${mc_gross}")

def handle_chargeback(ipn_data):
    """Handle payment reversal/chargeback."""
    txn_id = ipn_data.get('txn_id')
    reason_code = ipn_data.get('reason_code')

    # Handle chargeback
    print(f"Chargeback: {txn_id}, Reason: {reason_code}")
```

## Subscription/Recurring Billing

### Create Subscription Plan
```python
def create_subscription_plan(name, amount, interval='MONTH'):
    """Create a subscription plan."""
    client = PayPalClient(CLIENT_ID, CLIENT_SECRET)

    url = f"{client.base_url}/v1/billing/plans"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {client.access_token}"
    }

    payload = {
        "product_id": "PRODUCT_ID",  # Create product first
        "name": name,
        "billing_cycles": [{
            "frequency": {
                "interval_unit": interval,
                "interval_count": 1
            },
            "tenure_type": "REGULAR",
            "sequence": 1,
            "total_cycles": 0,  # Infinite
            "pricing_scheme": {
                "fixed_price": {
                    "value": str(amount),
                    "currency_code": "USD"
                }
            }
        }],
        "payment_preferences": {
            "auto_bill_outstanding": True,
            "setup_fee": {
                "value": "0",
                "currency_code": "USD"
            },
            "setup_fee_failure_action": "CONTINUE",
            "payment_failure_threshold": 3
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    return response.json()

def create_subscription(plan_id, subscriber_email):
    """Create a subscription for a customer."""
    client = PayPalClient(CLIENT_ID, CLIENT_SECRET)

    url = f"{client.base_url}/v1/billing/subscriptions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {client.access_token}"
    }

    payload = {
        "plan_id": plan_id,
        "subscriber": {
            "email_address": subscriber_email
        },
        "application_context": {
            "return_url": "https://yourdomain.com/subscription/success",
            "cancel_url": "https://yourdomain.com/subscription/cancel"
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    subscription = response.json()

    # Get approval URL
    for link in subscription.get('links', []):
        if link['rel'] == 'approve':
            return {
                'subscription_id': subscription['id'],
                'approval_url': link['href']
            }
```

## Refund Workflows

```python
def create_refund(capture_id, amount=None, note=None):
    """Create a refund for a captured payment."""
    client = PayPalClient(CLIENT_ID, CLIENT_SECRET)

    url = f"{client.base_url}/v2/payments/captures/{capture_id}/refund"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {client.access_token}"
    }

    payload = {}
    if amount:
        payload["amount"] = {
            "value": str(amount),
            "currency_code": "USD"
        }

    if note:
        payload["note_to_payer"] = note

    response = requests.post(url, headers=headers, json=payload)
    return response.json()

def get_refund_details(refund_id):
    """Get refund details."""
    client = PayPalClient(CLIENT_ID, CLIENT_SECRET)

    url = f"{client.base_url}/v2/payments/refunds/{refund_id}"
    headers = {
        "Authorization": f"Bearer {client.access_token}"
    }

    response = requests.get(url, headers=headers)
    return response.json()
```

## Error Handling

```python
class PayPalError(Exception):
    """Custom PayPal error."""
    pass

def handle_paypal_api_call(api_function):
    """Wrapper for PayPal API calls with error handling."""
    try:
        result = api_function()
        return result
    except requests.exceptions.RequestException as e:
        # Network error
        raise PayPalError(f"Network error: {str(e)}")
    except Exception as e:
        # Other errors
        raise PayPalError(f"PayPal API error: {str(e)}")

# Usage
try:
    order = handle_paypal_api_call(lambda: client.create_order(25.00))
except PayPalError as e:
    # Handle error appropriately
    log_error(e)
```

## Testing

```python
import os

# Load sandbox credentials exclusively from environment variables
SANDBOX_CLIENT_ID = os.environ["PAYPAL_SANDBOX_CLIENT_ID"]
SANDBOX_SECRET = os.environ["PAYPAL_SANDBOX_CLIENT_SECRET"]

def test_payment_flow():
    """Test complete Orders v2 create -> approve -> capture flow in sandbox."""
    client = PayPalClient(SANDBOX_CLIENT_ID, SANDBOX_SECRET, mode="sandbox")

    # Create order (string decimal amount, PayPal-Request-Id idempotency)
    order = client.create_order("10.00", currency="USD", request_id="test-order-001")
    assert "id" in order

    # Get payer approval URL
    approval_url = next((link["href"] for link in order.get("links", []) if link.get("rel") == "approve"), None)
    assert approval_url is not None
```

## Resources

- **[resources/implementation-playbook.md](./resources/implementation-playbook.md)**: PayPal Orders v2, Webhook Certificate Verification (`/v1/notifications/verify-webhook-signature`), Billing Subscriptions, Refunds & 2PC Playbook

## Best Practices

1. **Always Verify Webhooks & IPNs**: Verify REST webhooks via `/v1/notifications/verify-webhook-signature` and legacy IPNs via `cmd=_notify-validate` (`VERIFIED`).
2. **Idempotent Processing**: Pass `PayPal-Request-Id` on mutating POST calls and deduplicate inbound `event.id` / `txn_id`.
3. **Decimal String Amounts**: Format wire amounts strictly as 2-decimal strings (`"25.00"`) or integer strings for zero-decimal currencies (`JPY`, `HUF`, `TWD`).
4. **Structured Audit Logging**: Log PayPal `order_id`, `capture_id`, and `debug_id` without logging raw bearer tokens or client secrets.
5. **Server-Side Authoritative Capture**: Never fulfill inventory from client-side `onApprove` alone; confirm `COMPLETED` capture status on the backend.

## Common Pitfalls

- **Accepting Unverified Webhooks**: Trusting payload bodies without `verification_status == "SUCCESS"`.
- **Float Formatting Drift**: Passing binary floats (`25.0`) instead of exact 2-decimal strings (`"25.00"`).
- **Duplicate Fulfillment**: Re-emitting downstream tickets/orders when PayPal retries webhook delivery.
- **Environment Mismatch**: Mixing `api-m.sandbox.paypal.com` tokens with `api-m.paypal.com` endpoints.
- **Hardcoded Credentials**: Never commit `CLIENT_ID` or `CLIENT_SECRET` literals in source files.

## Limitations
- Use this skill only when the task clearly matches the scope described above.
- Do not treat the output as a substitute for environment-specific validation, testing, or expert review.
- Stop and ask for clarification if required inputs, permissions, safety boundaries, or success criteria are missing.
