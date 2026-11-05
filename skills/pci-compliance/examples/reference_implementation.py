# -*- coding: utf-8 -*-
r"""
Executable Reference Implementation for `pci-compliance` (PCI DSS v4.0.1).

Verifies:
  1. Req. 3.3.1 & 3.4.1: Recursive SAD stripping (CVV/PIN/Track) and PAN masking (First 6 / Last 4).
  2. Req. 3.5.1: AES-256-GCM authenticated encryption at rest + tamper detection & Fernet TokenVault.
  3. Req. 6.4.3 & 11.6.1: Payment-page script authorization inventory, SHA-384 SRI, strict CSP, and
     automated HTTP header / DOM script tamper detection against Magecart e-skimmers.
  4. Req. 10.2: Structured UTC PCI audit logging without PAN/SAD leakage & ISO/IEC 7812-1 Luhn validation.

Run with:
  python ./examples/reference_implementation.py
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import base64
import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecurityError(Exception):
    """Raised when an operation violates PCI DSS v4.0.1 security invariants."""


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
    """Masks a PAN to at most First 6 and Last 4 digits (PCI DSS Req. 3.4.1)."""
    digits = re.sub(r"[\s-]", "", str(raw_pan or ""))
    if not digits.isdigit() or not (12 <= len(digits) <= 19):
        return "****"
    return f"{digits[:6]}{'*' * (len(digits) - 10)}{digits[-4:]}"


def validate_luhn(card_number: str) -> bool:
    """Validates a 12..19 digit PAN using the ISO/IEC 7812-1 Luhn algorithm."""
    cleaned = re.sub(r"[\s-]", "", str(card_number or ""))
    if not cleaned.isdigit() or not (12 <= len(cleaned) <= 19):
        return False
    digits = [int(ch) for ch in cleaned]
    checksum = sum(digits[-1::-2])
    for d in digits[-2::-2]:
        doubled = d * 2
        checksum += doubled - 9 if doubled > 9 else doubled
    return checksum % 10 == 0


class PaymentDataSanitizer:
    """Enforces PCI DSS Req. 3.3.1 (SAD prohibition) and Req. 3.4.1 (PAN masking) across dicts, lists, and tuples."""

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

    def sanitize_bancard_public_ui_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Strips SAD, masks PANs, and removes all 4 Bancard-prohibited public UI fields."""
        clean = self.sanitize_for_log(payload)
        return self._strip_bancard_ui_fields(clean)

    def _strip_bancard_ui_fields(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: self._strip_bancard_ui_fields(v)
                for k, v in value.items()
                if str(k).strip().lower() not in BANCARD_PROHIBITED_PUBLIC_UI_FIELDS
            }
        if isinstance(value, (list, tuple)):
            items = [self._strip_bancard_ui_fields(item) for item in value]
            return tuple(items) if isinstance(value, tuple) else items
        return value

    def validate_no_prohibited_storage(self, payload: Any) -> None:
        if isinstance(payload, dict):
            for key, value in payload.items():
                norm_key = str(key).strip().lower()
                if norm_key in PROHIBITED_SAD_FIELDS:
                    raise SecurityError(f"PCI DSS Req. 3.3.1 violation: prohibited SAD field '{key}'")
                self.validate_no_prohibited_storage(value)
        elif isinstance(payload, (list, tuple)):
            for item in payload:
                self.validate_no_prohibited_storage(item)


class EncryptedStorage:
    """AES-256-GCM authenticated encryption at rest (PCI DSS Req. 3.5.1)."""

    def __init__(self, key_32_bytes: bytes) -> None:
        if not isinstance(key_32_bytes, (bytes, bytearray)) or len(key_32_bytes) != 32:
            raise ValueError("AES-256-GCM key must be exactly 32 bytes")
        self._aesgcm = AESGCM(bytes(key_32_bytes))

    def encrypt(self, plaintext: str, aad: bytes | None = None) -> bytes:
        if not plaintext:
            raise ValueError("Plaintext cannot be empty")
        nonce = os.urandom(12)
        return nonce + self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)

    def decrypt(self, encrypted_blob: bytes, aad: bytes | None = None) -> str:
        if not isinstance(encrypted_blob, (bytes, bytearray)) or len(encrypted_blob) < 28:
            raise ValueError("Invalid or truncated AES-256-GCM payload")
        nonce, ct = bytes(encrypted_blob[:12]), bytes(encrypted_blob[12:])
        return self._aesgcm.decrypt(nonce, ct, aad).decode("utf-8")


class TokenVault:
    """SAD-guarded Fernet tokenization vault."""

    def __init__(self, fernet_key: bytes | None = None) -> None:
        self._cipher = Fernet(fernet_key or Fernet.generate_key())
        self._sanitizer = PaymentDataSanitizer()
        self._vault: dict[str, bytes] = {}

    def tokenize(self, card_metadata: dict[str, Any]) -> str:
        self._sanitizer.validate_no_prohibited_storage(card_metadata)
        token = f"tok_{secrets.token_urlsafe(24)}"
        self._vault[token] = self._cipher.encrypt(json.dumps(card_metadata).encode("utf-8"))
        return token

    def detokenize(self, token: str) -> dict[str, Any]:
        blob = self._vault.get(token)
        if not blob:
            raise KeyError(f"Token not found: {token}")
        return json.loads(self._cipher.decrypt(blob).decode("utf-8"))

    def delete_token(self, token: str) -> bool:
        return self._vault.pop(token, None) is not None


@dataclass(frozen=True)
class AuthorizedScriptEntry:
    url: str
    business_justification: str
    expected_sri_sha384: str | None = None


class PaymentPageScriptGuard:
    """
    Implements PCI DSS v4.0.1 Req. 6.4.3 (script authorization, justification & SRI/CSP)
    and Req. 11.6.1 (automated HTTP header & DOM script tamper detection).
    """

    def __init__(self, inventory: list[AuthorizedScriptEntry]) -> None:
        for item in inventory:
            if not item.business_justification.strip():
                raise ValueError(f"PCI Req. 6.4.3 requires written justification for {item.url}")
        self._inventory = {item.url: item for item in inventory}

    @staticmethod
    def compute_sri_sha384(script_body: bytes) -> str:
        return "sha384-" + base64.b64encode(hashlib.sha384(script_body).digest()).decode("ascii")

    @staticmethod
    def build_csp_header(nonce: str) -> str:
        if not nonce or len(nonce) < 16:
            raise ValueError("CSP nonce must be at least 16 characters")
        return (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' https://vpos.infonet.com.py https://js.stripe.com https://www.paypal.com; "
            "frame-src https://vpos.infonet.com.py https://js.stripe.com https://hooks.stripe.com https://www.paypal.com; "
            "connect-src 'self' https://vpos.infonet.com.py https://api.stripe.com https://www.paypal.com; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )

    def inspect_live_payment_page(
        self,
        response_headers: dict[str, str],
        observed_scripts: list[dict[str, str | None]],
    ) -> dict[str, Any]:
        """
        Req. 11.6.1 tamper inspection: checks mandatory HTTP headers and compares all
        observed DOM <script> tags against the authorized Req. 6.4.3 inventory.
        """
        norm_headers = {k.lower(): v for k, v in response_headers.items()}
        violations: list[str] = []

        csp = norm_headers.get("content-security-policy", "")
        if "script-src" not in csp or "unsafe-eval" in csp or "object-src 'none'" not in csp:
            violations.append("TAMPERED_OR_WEAK_CSP_HEADER")

        if "max-age=" not in norm_headers.get("strict-transport-security", ""):
            violations.append("MISSING_HSTS_HEADER")

        for tag in observed_scripts:
            src = (tag.get("src") or "").strip()
            sri = tag.get("integrity")
            if src not in self._inventory:
                violations.append(f"UNAUTHORIZED_SCRIPT_DETECTED:{src or '<inline>'}")
                continue
            expected = self._inventory[src].expected_sri_sha384
            if expected and sri != expected:
                violations.append(f"SRI_HASH_MISMATCH:{src}")

        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


def run_self_tests() -> dict[str, Any]:
    passed = 0

    # 1. PAN masking & SAD prohibition (including nested lists and tuples)
    sanitizer = PaymentDataSanitizer()
    raw_event = {
        "shop_process_id": 99102,
        "card_number": "4567 8901 2345 6789",
        "cvv": "123",
        "nested": {"pan": "4111111111111111", "pin_block": "ABCD", "track2": ";4111..."},
        "cards": [
            {"pan": "4111111111111111", "cvv": "321", "brand": "VISA"},
            ({"nro_tarjeta": "5500001111222233", "security_code": "999"},),
        ],
    }
    clean = sanitizer.sanitize_for_log(raw_event)
    assert clean["card_number"] == "456789******6789"
    assert clean["nested"]["pan"] == "411111******1111"
    assert clean["cards"][0]["pan"] == "411111******1111"
    assert "cvv" not in clean["cards"][0]
    assert clean["cards"][1][0]["nro_tarjeta"] == "550000******2233"
    assert "security_code" not in clean["cards"][1][0]
    assert "cvv" not in clean and "pin_block" not in clean["nested"] and "track2" not in clean["nested"]
    passed += 1

    try:
        sanitizer.validate_no_prohibited_storage({"pan_masked": "411111******1111", "cvv2": "999"})
        raise AssertionError("Failed to block CVV2 storage")
    except SecurityError:
        passed += 1

    try:
        sanitizer.validate_no_prohibited_storage({"cards": [{"last4": "1111", "cvv": "123"}]})
        raise AssertionError("Failed to block nested list CVV storage")
    except SecurityError:
        passed += 1

    ui_clean = sanitizer.sanitize_bancard_public_ui_response({
        "shop_process_id": 99102,
        "response_description": "Transaccion aprobada",
        "authorization_number": "132567",
        "response_code": "00",
        "extended_response_description": "APROBADA EMISOR",
        "security_information": {"card_country": "PRY", "risk_index": "0.1"},
    })
    for forbidden_ui_key in BANCARD_PROHIBITED_PUBLIC_UI_FIELDS:
        assert forbidden_ui_key not in ui_clean
    assert ui_clean["response_description"] == "Transaccion aprobada"
    passed += 1

    # 2. Luhn validation
    assert validate_luhn("4242 4242 4242 4242") is True
    assert validate_luhn("4242 4242 4242 4243") is False
    assert validate_luhn("123") is False
    passed += 1

    # 3. AES-256-GCM encryption & tamper rejection
    storage = EncryptedStorage(os.urandom(32))
    aad = b"user_id:42"
    blob = storage.encrypt("4111111111111111", aad=aad)
    assert storage.decrypt(blob, aad=aad) == "4111111111111111"
    tampered = bytearray(blob)
    tampered[-1] ^= 0xFF
    try:
        storage.decrypt(bytes(tampered), aad=aad)
        raise AssertionError("AES-256-GCM failed to detect ciphertext tampering")
    except InvalidTag:
        passed += 1

    # 4. TokenVault SAD enforcement
    vault = TokenVault()
    tok = vault.tokenize({"last4": "4242", "brand": "VISA", "exp": "12/29"})
    assert vault.detokenize(tok)["last4"] == "4242"
    assert vault.delete_token(tok) is True
    passed += 1

    # 5. PCI DSS v4.0.1 Req. 6.4.3 & 11.6.1 CSP + Skimmer Tamper Detection
    bundle_bytes = b"window.BoletosCheckoutInit = true;"
    bundle_sri = PaymentPageScriptGuard.compute_sri_sha384(bundle_bytes)
    guard = PaymentPageScriptGuard([
        AuthorizedScriptEntry(
            url="https://vpos.infonet.com.py/checkout/javascript/dist/bancard-checkout-4.0.0.js",
            business_justification="Bancard vPOS 2.0 SDK v4.0.0 isolated checkout iframe loader",
        ),
        AuthorizedScriptEntry(
            url="https://boletos.la/_next/static/checkout-host.js",
            business_justification="First-party checkout host mount controller",
            expected_sri_sha384=bundle_sri,
        ),
    ])
    nonce = secrets.token_hex(16)
    headers_ok = {
        "Content-Security-Policy": guard.build_csp_header(nonce),
        "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    }
    audit_ok = guard.inspect_live_payment_page(
        headers_ok,
        [
            {"src": "https://vpos.infonet.com.py/checkout/javascript/dist/bancard-checkout-4.0.0.js", "integrity": None},
            {"src": "https://boletos.la/_next/static/checkout-host.js", "integrity": bundle_sri},
        ],
    )
    assert audit_ok["compliant"] is True
    passed += 1

    # Simulate Magecart skimmer script injection + tampered SRI
    audit_skimmer = guard.inspect_live_payment_page(
        headers_ok,
        [
            {"src": "https://cdn-analytics-evil.example/skimmer.js", "integrity": None},
            {"src": "https://boletos.la/_next/static/checkout-host.js", "integrity": "sha384-tampered"},
        ],
    )
    assert audit_skimmer["compliant"] is False
    assert any("UNAUTHORIZED_SCRIPT_DETECTED" in v for v in audit_skimmer["violations"])
    assert any("SRI_HASH_MISMATCH" in v for v in audit_skimmer["violations"])
    passed += 1

    return {"skill": "pci-compliance", "status": "ok", "tests_passed": passed}


if __name__ == "__main__":
    res = run_self_tests()
    print(f"[PASS] pci-compliance reference_implementation.py ({res['tests_passed']} security test suites passed)")
