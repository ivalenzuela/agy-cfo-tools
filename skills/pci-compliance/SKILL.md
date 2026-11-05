---
name: pci-compliance
description: >-
  Enforces PCI DSS v4.0.1 compliance across payment gateways (Bancard vPOS 2.0, Stripe, PayPal, Transbank), including SAD prohibition (never store CVV, track data, or PIN), PAN masking, AES-256-GCM and Fernet tokenization, SAQ A/A-EP scope reduction, Req. 6.4.3 payment-page script authorization (CSP/SRI), and Req. 11.6.1 tamper detection. Use when building or auditing payment flows.
risk: critical
source: workspace-verified
date_added: "2026-02-27"
---

# PCI DSS v4.0.1 Compliance & Payment Page Hardening

Production security architecture and verification patterns for **PCI DSS v4.0.1** compliance across web checkouts, payment orchestrators (`boletos-la-backend-bancard`), and unattended kiosks.

---

## 1. PCI DSS v4.0.1 Core Matrix & SAQ Scope Classification

| Scope / Control | PCI DSS v4.0.1 Requirement | Mandatory Technical Enforcement | Gateway / Architecture Impact |
| :--- | :--- | :--- | :--- |
| **SAD Prohibition** | **Req. 3.3.1** | **NEVER** store Sensitive Authentication Data (`CVV`/`CVC`/`CID`, full magnetic track `Track 1`/`Track 2`, or `PIN` block) after authorization — even if encrypted | Strip SAD fields before logging, DB persistence, or error telemetry (`Sentry`/PM2 logs) |
| **PAN Masking & Storage** | **Req. 3.4.1 & 3.5.1** | Mask displayed PANs to at most **First 6 (BIN) and Last 4 digits** (`456789******1234`); encrypt stored PANs with `AES-256-GCM` + KMS key rotation or outsource to gateway tokens | Store Bancard `alias_token` (15m TTL) / `card_id`, Stripe `pm_*`, or Transbank voucher masked PAN only |
| **Transit Cryptography** | **Req. 4.2.1** | Enforce **TLS 1.2 / TLS 1.3** (`Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`), strong AEAD ciphers, and mTLS `.p12` where required | Mandatory across Bancard vPOS (`https://vpos.infonet.com.py`), Transbank, Stripe, and SIFEN |
| **Payment Page Scripts** | **Req. 6.4.3** *(Mandatory)* | Authorize, inventory, and justify every `<script>` loaded on the checkout/iframe host page; enforce strict `Content-Security-Policy` (`CSP`) and `SRI` (`sha384-...`) where static | Required for **SAQ A** & **SAQ A-EP** pages embedding `bancard-checkout-4.0.0.js` (`2.0.0.js` legacy), `js.stripe.com`, or `paypal.com/sdk/js` |
| **Tamper & Skimmer Detection** | **Req. 11.6.1** *(Mandatory)* | Automated tamper-detection mechanism alerting on unauthorized modifications to payment-page HTTP security headers (`CSP`, `HSTS`, `X-Frame-Options`) and DOM script contents | Synthetic Playwright / hash audit at least every 7 days (or per deploy + `CSP report-to`) to block Magecart e-skimming |
| **Gateway Response Hygiene** | **Bancard v1.23.1 / MC MAC 03 & 21** | Never expose `authorization_number`, `response_code`, `extended_response_description`, or `security_information` to public browser UI on **any** response screen; enforce retry throttling (`< 7` declines/24h, `< 35`/30d) | Prevents BIN/card enumeration and Mastercard 30-day card blocks; log securely in server `vpos_audit` |

### SAQ Scope Tiers
- **SAQ A**: Cardholder data handled 100% via hosted redirect or isolated provider `<iframe>` (`Bancard vPOS 2.0 Checkout JS 4.0.0`, `Stripe Checkout / Elements`, `Transbank Webpay Plus`, `PayPal Smart Buttons`). Zero raw PAN touches merchant server. *Note: Under PCI DSS v4.0.1, SAQ A merchants hosting the parent page of a payment iframe must still satisfy Req. 6.4.3 and Req. 11.6.1 (or attested equivalent protection).*
- **SAQ A-EP**: Merchant page renders form controls or JavaScript that directly posts/routes cardholder data to a processor.
- **SAQ D**: Merchant server receives, processes, transmits, or stores raw PANs directly (~300+ controls, quarterly ASV scans, penetration tests). Always architect for **SAQ A** via iframe/redirect tokenization.

---

## 2. Canonical Implementation Patterns

### 2.1. Sensitive Authentication Data (SAD) Guard & PAN Masking (Req. 3.3 & 3.4)

```python
import re
from typing import Any


class SecurityError(Exception):
    """Raised when an operation violates PCI DSS v4.0.1 data handling rules."""


PROHIBITED_SAD_FIELDS = frozenset({
    "cvv", "cvv2", "cvc", "cid", "security_code",
    "pin", "pin_block",
    "full_track_data", "track1", "track2", "magnetic_stripe",
})

PAN_FIELD_NAMES = frozenset({"pan", "card_number", "primary_account_number", "nro_tarjeta"})

BANCARD_PROHIBITED_PUBLIC_UI_FIELDS = frozenset({
    "authorization_number",
    "response_code",
    "extended_response_description",
    "security_information",
})


def mask_pan(raw_pan: str) -> str:
    """Masks a PAN leaving at most First 6 and Last 4 digits (PCI DSS Req. 3.4.1)."""
    digits = re.sub(r"[\s-]", "", str(raw_pan or ""))
    if not digits.isdigit() or len(digits) < 12 or len(digits) > 19:
        return "****"
    return f"{digits[:6]}{'*' * (len(digits) - 10)}{digits[-4:]}"


class PaymentDataSanitizer:
    """Recursively strips prohibited SAD fields and masks PANs across dicts, lists, and tuples."""

    def _sanitize_value(self, value: Any, parent_is_pan_key: bool = False) -> Any:
        if isinstance(value, dict):
            return self.sanitize_for_log(value)
        if isinstance(value, (list, tuple)):
            items = [self._sanitize_value(item, parent_is_pan_key=parent_is_pan_key) for item in value]
            return tuple(items) if isinstance(value, tuple) else items
        if parent_is_pan_key:
            return mask_pan(str(value))
        return value

    def sanitize_for_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for key, value in payload.items():
            norm_key = str(key).strip().lower()
            if norm_key in PROHIBITED_SAD_FIELDS:
                continue
            clean[key] = self._sanitize_value(value, parent_is_pan_key=(norm_key in PAN_FIELD_NAMES))
        return clean

    def validate_no_prohibited_storage(self, payload: Any) -> None:
        if isinstance(payload, dict):
            for key, value in payload.items():
                norm_key = str(key).strip().lower()
                if norm_key in PROHIBITED_SAD_FIELDS:
                    raise SecurityError(f"PCI DSS Req. 3.3.1 violation: prohibited SAD field '{key}' cannot be stored")
                self.validate_no_prohibited_storage(value)
        elif isinstance(payload, (list, tuple)):
            for item in payload:
                self.validate_no_prohibited_storage(item)
```

### 2.2. PCI DSS v4.0.1 Req. 6.4.3 & 11.6.1 — Payment Page CSP, Script Inventory & Tamper Monitor

Every checkout page hosting an embedded iframe (`bancard-checkout-4.0.0.js`, `js.stripe.com/v3/`, `www.paypal.com/sdk/js`) must maintain a signed inventory of authorized script sources with explicit business justification and detect header/script tampering:

```python
import hashlib
import base64
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthorizedPaymentScript:
    src_origin_or_url: str
    justification: str
    expected_sha384_sri: str | None = None  # Required for static self-hosted bundles


AUTHORIZED_CHECKOUT_INVENTORY = (
    AuthorizedPaymentScript(
        src_origin_or_url="https://vpos.infonet.com.py/checkout/javascript/dist/bancard-checkout-4.0.0.js",
        justification="Bancard vPOS 2.0 SDK v4.0.0 isolated iframe tokenizer for PYG card & QR checkout (min width 320px)",
    ),
    AuthorizedPaymentScript(
        src_origin_or_url="https://js.stripe.com/v3/",
        justification="Stripe Elements PCI SAQ-A isolated card input iframe",
    ),
)


def compute_sri_sha384(script_bytes: bytes) -> str:
    digest = hashlib.sha384(script_bytes).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")


def build_checkout_csp_header(nonce: str) -> str:
    """Generates a strict PCI DSS v4.0.1 Req. 6.4.3 Content-Security-Policy header."""
    return (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://vpos.infonet.com.py https://js.stripe.com https://www.paypal.com; "
        "frame-src https://vpos.infonet.com.py https://js.stripe.com https://hooks.stripe.com https://www.paypal.com; "
        "connect-src 'self' https://vpos.infonet.com.py https://api.stripe.com https://www.paypal.com; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
```

### 2.3. Authenticated Encryption at Rest (`AES-256-GCM`) & Token Vault (Req. 3.5.1)

Prefer processor-managed tokens (Bancard `alias_token`, Stripe `pm_*`, Pagopar card token) so zero PANs reside in your database. If you operate a certified SAQ D vault, use `AES-256-GCM` with unique 96-bit nonces and strict SAD rejection:

```python
import json
import os
import secrets
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptedStorage:
    """AES-256-GCM authenticated encryption for sensitive payment identifiers."""

    def __init__(self, key_32_bytes: bytes) -> None:
        if not isinstance(key_32_bytes, (bytes, bytearray)) or len(key_32_bytes) != 32:
            raise ValueError("AES-256-GCM key must be exactly 32 bytes (256 bits)")
        self._aesgcm = AESGCM(bytes(key_32_bytes))

    def encrypt(self, plaintext: str, aad: bytes | None = None) -> bytes:
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)
        return nonce + ciphertext

    def decrypt(self, blob: bytes, aad: bytes | None = None) -> str:
        if len(blob) < 28:
            raise ValueError("Truncated AES-256-GCM ciphertext")
        nonce, ciphertext = blob[:12], blob[12:]
        return self._aesgcm.decrypt(nonce, ciphertext, aad).decode("utf-8")


class TokenVault:
    """In-memory demonstration of a SAD-guarded Fernet token vault."""

    def __init__(self, fernet_key: bytes) -> None:
        self._cipher = Fernet(fernet_key)
        self._sanitizer = PaymentDataSanitizer()
        self._vault: dict[str, bytes] = {}

    def tokenize(self, card_metadata: dict[str, str]) -> str:
        self._sanitizer.validate_no_prohibited_storage(card_metadata)
        token = f"tok_{secrets.token_urlsafe(24)}"
        self._vault[token] = self._cipher.encrypt(json.dumps(card_metadata).encode("utf-8"))
        return token

    def detokenize(self, token: str) -> dict[str, str]:
        encrypted = self._vault.get(token)
        if not encrypted:
            raise KeyError("Unknown vault token")
        return json.loads(self._cipher.decrypt(encrypted).decode("utf-8"))
```

### 2.4. Append-Only PCI Audit Logging (Req. 10.2) & Luhn Validation

```python
import json
import logging
import re
from datetime import datetime, timezone


class PCIAuditLogger:
    """PCI DSS Req. 10.2 structured audit trail with UTC timestamps (zero PAN/SAD leakage)."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("pci_audit")

    def log_access(self, user_id: str, resource: str, action: str, result: str, ip_address: str) -> dict[str, str]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": str(user_id),
            "resource": resource,
            "action": action,
            "result": result,
            "ip_address": ip_address,
        }
        self.logger.info(json.dumps(entry, sort_keys=True))
        return entry


def validate_luhn(card_number: str) -> bool:
    """Validates a 12..19 digit PAN using the ISO/IEC 7812-1 Luhn check-digit algorithm."""
    cleaned = re.sub(r"[\s-]", "", str(card_number or ""))
    if not cleaned.isdigit() or not (12 <= len(cleaned) <= 19):
        return False
    digits = [int(ch) for ch in cleaned]
    checksum = sum(digits[-1::-2])
    for d in digits[-2::-2]:
        doubled = d * 2
        checksum += doubled - 9 if doubled > 9 else doubled
    return checksum % 10 == 0
```

---

## 3. Progressive Disclosure & Verification Suite

1. **Deep Implementation Playbook**: Read **[resources/implementation-playbook.md](./resources/implementation-playbook.md)** for the complete PCI DSS v4.0.1 12-requirement engineering checklist, SAQ A / A-EP architecture diagrams, Req. 6.4.3 & 11.6.1 browser skimmer controls, and Bancard / Transbank / Stripe webhook security rules.
2. **Executable Security Reference**: Run **[examples/reference_implementation.py](./examples/reference_implementation.py)** to execute SAD sanitization, PAN masking, `AES-256-GCM` authenticated encryption, `Fernet` vaulting, Luhn verification, and Req. 6.4.3/11.6.1 tamper detection:

```powershell
python ./examples/reference_implementation.py
```

3. **Deterministic Domain Validator**: Run **[scripts/validate_skill_domain.py](./scripts/validate_skill_domain.py)** to verify frontmatter, markdown links, playbook integrity, and 10+ security edge cases:

```powershell
python ./scripts/validate_skill_domain.py
```
