# -*- coding: utf-8 -*-
"""
Complete executable reference implementation for latam-fintech-payments-invoicing.
Covers:
1. Bancard vPOS (Paraguay): single_buy MD5, QR/Zimple, constant-time webhook confirm,
   amount/currency tamper check, get_confirmation timeout polling, late-webhook auto-rollback,
   PaymentAlreadyConfirmedError escalation, and 2PC Rollback saga on GDS failure.
2. Pagopar (Paraguay): SHA-1 order initialization, webhook verification, consultation & reversal.
3. SIFEN / Ekuatia (DNIT Paraguay v150): Mod-11 DV, 44-digit CDC, PYG & USD (dTiCam) IVA 10%/5%/Exenta
   liquidation (including multi-item & per-item discounts), real X.509 PKCS#12 (.p12) RSA-SHA256
   XMLDSig over xml-exc-c14n# canonicalized <DE> & <SignedInfo>, official SHA-256 KuDE Tax QR (cHashQR),
   and valid %PDF-1.4 KuDE PDF emission with embedded QR.
4. Transbank (Chile): Webpay Plus v1.2 callback state machine & POS Integrado STX/ETX/LRC framing.

Run with:
    python examples/reference_implementation.py
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(SKILL_ROOT, "resources", "config-template.json")
XML_TEMPLATE_PATH = os.path.join(SKILL_ROOT, "resources", "sifen-de-v150-template.xml")


def load_domain_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# 1. BANCARD vPOS (PARAGUAY) — SINGLE_BUY, QR, ZIMPLE, WEBHOOK & 2PC ROLLBACK
# ============================================================================

def format_bancard_amount(amount: int | float | Decimal | str) -> str:
    """Format amount with exact 2 decimal places (.00) required by Bancard vPOS."""
    if isinstance(amount, bool):
        raise ValueError("Boolean is not a valid numeric amount")
    try:
        dec = Decimal(str(amount))
    except Exception as exc:
        raise ValueError(f"Invalid numeric amount for Bancard: {amount!r}") from exc
    if not dec.is_finite() or dec <= 0:
        raise ValueError(f"Bancard amount must be positive and finite, got: {amount!r}")
    quantized = dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{quantized:.2f}"


def generate_bancard_single_buy_token(
    private_key: str,
    shop_process_id: int | str,
    amount_str: str,
    currency: str = "PYG",
) -> str:
    if not private_key:
        raise ValueError("private_key cannot be empty")
    if not re.match(r"^\d+\.\d{2}$", str(amount_str)):
        raise ValueError(f"Bancard amount_str must match ^\\d+\\.\\d{{2}}$, got: {amount_str!r}")
    if currency not in ("PYG", "USD"):
        raise ValueError(f"Unsupported Bancard currency: {currency!r}")
    raw = f"{private_key}{shop_process_id}{amount_str}{currency}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def verify_bancard_webhook_token(
    private_key: str,
    shop_process_id: int | str,
    amount_str: str,
    currency: str,
    received_token: str,
) -> bool:
    if not private_key or not received_token:
        return False
    if not re.match(r"^\d+\.\d{2}$", str(amount_str)):
        return False
    if not re.match(r"^[a-fA-F0-9]{32}$", received_token):
        return False
    raw = f"{private_key}{shop_process_id}confirm{amount_str}{currency}"
    expected = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, received_token.lower())


def generate_bancard_rollback_token(private_key: str, shop_process_id: int | str) -> str:
    if not private_key:
        raise ValueError("private_key cannot be empty")
    raw = f"{private_key}{shop_process_id}rollback0.00"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_bancard_get_confirmation_token(private_key: str, shop_process_id: int | str) -> str:
    if not private_key:
        raise ValueError("private_key cannot be empty")
    raw = f"{private_key}{shop_process_id}get_confirmation"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_bancard_cards_new_token(private_key: str, card_id: int | str, user_id: int | str) -> str:
    if not private_key:
        raise ValueError("private_key cannot be empty")
    return hashlib.md5(f"{private_key}{card_id}{user_id}request_new_card".encode("utf-8")).hexdigest()


def generate_bancard_list_cards_token(private_key: str, user_id: int | str) -> str:
    if not private_key:
        raise ValueError("private_key cannot be empty")
    return hashlib.md5(f"{private_key}{user_id}request_user_cards".encode("utf-8")).hexdigest()


def generate_bancard_charge_token(
    private_key: str,
    shop_process_id: int | str,
    amount_str: str,
    currency: str,
    alias_token: str,
) -> str:
    if not private_key or not alias_token:
        raise ValueError("private_key and alias_token are required")
    if not re.match(r"^\d+\.\d{2}$", str(amount_str)):
        raise ValueError(f"Bancard amount_str must match ^\\d+\\.\\d{{2}}$, got: {amount_str!r}")
    return hashlib.md5(
        f"{private_key}{shop_process_id}charge{amount_str}{currency}{alias_token}".encode("utf-8")
    ).hexdigest()


def generate_bancard_delete_card_token(private_key: str, user_id: int | str, alias_token: str) -> str:
    if not private_key or not alias_token:
        raise ValueError("private_key and alias_token are required")
    return hashlib.md5(f"{private_key}delete_card{user_id}{alias_token}".encode("utf-8")).hexdigest()


def generate_bancard_preauth_confirm_token(private_key: str, shop_process_id: int | str) -> str:
    if not private_key:
        raise ValueError("private_key cannot be empty")
    return hashlib.md5(f"{private_key}{shop_process_id}pre-authorization-confirm".encode("utf-8")).hexdigest()


def generate_bancard_billing_client_info_token(private_key: str) -> str:
    if not private_key:
        raise ValueError("private_key cannot be empty")
    return hashlib.md5(f"{private_key}billing_client_info".encode("utf-8")).hexdigest()


def generate_bancard_billing_cancel_token(private_key: str, shop_process_id: int | str) -> str:
    if not private_key:
        raise ValueError("private_key cannot be empty")
    return hashlib.md5(f"{private_key}{shop_process_id}billing_cancel".encode("utf-8")).hexdigest()


def build_bancard_ventas_qr_basic_auth(public_key: str, private_key: str) -> str:
    """Official Bancard VentasQR HTTP Basic Auth header: Basic base64('apps/{pub}:{priv}')."""
    if not public_key or not private_key:
        raise ValueError("public_key and private_key are required for VentasQR")
    raw = f"apps/{public_key}:{private_key}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


BANCARD_POS_CARD_ISSUERS = frozenset(
    {"CB", "CC", "CL", "CP", "DC", "ID", "MC", "MD", "PC", "UD", "VC", "VD", "TD", "TC", "CD", "AC", "BC"}
)
BANCARD_POS_WALLET_MAP = {"ZIM": "ZM", "WPJ": "PJ", "VBV": "VB", "BPI": "PI", "BBF": "BF"}


def validate_bancard_pos_venta_ux_request(
    factura_nro: int, monto: int = 150000, cuotas: int = 0, plan: int = 0
) -> Dict[str, int]:
    """Validate Bancard Caja POS Android 2.0 (ICP v1.7) Step-1 POST /pos/venta-ux request."""
    if not isinstance(factura_nro, int) or isinstance(factura_nro, bool) or not (0 <= factura_nro <= 999_999_999_999_999):
        raise ValueError(f"ICP v1.7 facturaNro must be an int(15) in 0..999999999999999, got: {factura_nro!r}")
    if not isinstance(monto, int) or isinstance(monto, bool) or not (1 <= monto <= 999_999_999):
        raise ValueError(f"ICP v1.7 monto must be an int(9) in 1..999999999, got: {monto!r}")
    if not isinstance(cuotas, int) or isinstance(cuotas, bool) or cuotas < 0 or cuotas == 1:
        raise ValueError(
            f"ICP v1.7 /pos/venta-ux forbids cuotas=1 (use 0 for cash/contado or >1 for installments), got: {cuotas!r}"
        )
    if plan not in (0, 1) or (cuotas == 0 and plan != 0) or (cuotas > 1 and plan != 1):
        raise ValueError(f"ICP v1.7 plan must be 0 when cuotas=0 and 1 when cuotas>1, got cuotas={cuotas!r}, plan={plan!r}")
    if cuotas == 0:
        return {"facturaNro": factura_nro, "monto": monto, "cuotas": 0, "plan": 0}
    return {"facturaNro": factura_nro, "monto": monto, "cuotas": cuotas, "plan": plan}


def validate_bancard_pos_billetera_request(
    factura_nro: int, monto: int, billetera: str, cuenta: str
) -> Dict[str, Any]:
    """Validate Bancard Caja POS Android 2.0 (ICP v1.7) 1-step POST /pos/venta-billetera request."""
    validate_bancard_pos_venta_ux_request(factura_nro, monto=monto, cuotas=0, plan=0)
    if billetera not in BANCARD_POS_WALLET_MAP:
        raise ValueError(f"Unsupported ICP v1.7 wallet code: {billetera!r}")
    if not isinstance(cuenta, str) or not re.fullmatch(r"0\d{8,9}", cuenta):
        raise ValueError(f"cuenta must preserve leading '0' as string (e.g. '0981123456'), got: {cuenta!r}")
    return {
        "facturaNro": factura_nro,
        "monto": monto,
        "billetera": billetera,
        "cuenta": cuenta,
        "expected_issuer_id": BANCARD_POS_WALLET_MAP[billetera],
    }


def validate_bancard_pos_consulta_anulacion_request(nro_boleta: str = "", cant_registro: int = 10) -> Dict[str, Any]:
    """Validate Bancard Caja POS Android 2.0 (ICP v1.7) POST /pos/consulta/anulacion request."""
    if not isinstance(nro_boleta, str) or (nro_boleta != "" and not re.fullmatch(r"\d{12}", nro_boleta)):
        raise ValueError(f"nroBoleta must be '' or a 12-digit string, got: {nro_boleta!r}")
    if not isinstance(cant_registro, int) or isinstance(cant_registro, bool) or not (1 <= cant_registro <= 50):
        raise ValueError(f"cantRegistro must be an integer in 1..50, got: {cant_registro!r}")
    return {"nroBoleta": nro_boleta, "cantRegistro": cant_registro}


def validate_bancard_pos_anulacion_request(nro_boleta: str) -> Dict[str, str]:
    """Validate Bancard Caja POS Android 2.0 (ICP v1.7) POST /pos/anulacion 12-digit nroBoleta."""
    if not isinstance(nro_boleta, str) or not re.fullmatch(r"\d{12}", nro_boleta):
        raise ValueError(f"ICP v1.7 /pos/anulacion requires a 12-digit nroBoleta string, got: {nro_boleta!r}")
    return {"nroBoleta": nro_boleta}


def verify_adamspay_webhook_signature(raw_body: str | bytes, secret: str, received_hash: str) -> bool:
    """Verify AdamsPay v1 x-adams-notify-hash = md5('adams' + rawBody + secret)."""
    if not secret or not received_hash or not re.fullmatch(r"[a-fA-F0-9]{32}", received_hash):
        return False
    body_bytes = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    raw = b"adams" + body_bytes + secret.encode("utf-8")
    expected = hashlib.md5(raw).hexdigest()
    return hmac.compare_digest(expected, received_hash.lower())


def compute_emvco_crc16_ccitt_false(payload_through_6304: str) -> str:
    """Compute ISO/IEC 13239 CRC-16/CCITT-FALSE (poly=0x1021, init=0xFFFF) as 4 uppercase hex chars."""
    crc = 0xFFFF
    for b in payload_through_6304.encode("utf-8"):
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def build_paraguay_emvco_py_qr(
    merchant_guid: str,
    commerce_id: str,
    amount_pyg: int,
    reference_id: str,
    merchant_name: str = "BOLETOS.LA PARAGUAY",
    merchant_city: str = "ASUNCION",
    mcc: str = "4131",
) -> str:
    """Build an interoperable BCP SIPAP / SPI EMVCo PY-QR payload (ISO 4217 600 PYG, MCC 4131 Bus Lines)."""
    if not isinstance(amount_pyg, int) or isinstance(amount_pyg, bool) or amount_pyg <= 0:
        raise ValueError(f"PY-QR amount_pyg must be a positive integer, got: {amount_pyg!r}")
    if amount_pyg > 10_000_000:
        raise ValueError(f"Amount {amount_pyg} exceeds BCP SPI standard instant transfer cap of Gs. 10.000.000")
    if not re.fullmatch(r"\d{4}", mcc):
        raise ValueError(f"MCC must be 4 digits, got: {mcc!r}")

    def tlv(tag: str, val: str) -> str:
        return f"{tag}{len(val):02d}{val}"

    mai = tlv("00", merchant_guid) + tlv("01", commerce_id)
    add_data = tlv("05", reference_id[:25])
    body_no_crc = (
        tlv("00", "01")
        + tlv("01", "12")
        + tlv("26", mai)
        + tlv("52", mcc)
        + tlv("53", "600")
        + tlv("54", str(amount_pyg))
        + tlv("58", "PY")
        + tlv("59", merchant_name[:25])
        + tlv("60", merchant_city[:15])
        + tlv("62", add_data)
        + "6304"
    )
    return body_no_crc + compute_emvco_crc16_ccitt_false(body_no_crc)


def resolve_paraguay_transport_iva_rate(distance_km: float | int, is_international: bool = False) -> int:
    """Ley 6380/2019 Art. 100 Num. 3 Inc. h: <= 100 km or international = 0% (Exento); > 100 km = 10% (NEVER 5%)."""
    if distance_km <= 0:
        raise ValueError(f"distance_km must be positive, got: {distance_km!r}")
    if is_international or distance_km <= 100:
        return 0
    return 10


def build_bancard_single_buy_payload(
    public_key: str,
    private_key: str,
    shop_process_id: int | str,
    amount: int | float | Decimal,
    description: str,
    return_url: str,
    cancel_url: str,
    currency: str = "PYG",
    zimple_phone: Optional[str] = None,
) -> Dict[str, Any]:
    amount_str = format_bancard_amount(amount)
    token = generate_bancard_single_buy_token(private_key, shop_process_id, amount_str, currency)
    operation: Dict[str, Any] = {
        "token": token,
        "shop_process_id": int(shop_process_id),
        "amount": amount_str,
        "currency": currency,
        "additional_data": zimple_phone or "",
        "description": description[:20],
        "return_url": return_url,
        "cancel_url": cancel_url,
    }
    if zimple_phone:
        operation["zimple"] = "S"
    return {"public_key": public_key, "operation": operation}


@dataclass
class OrderRecord:
    shop_process_id: int
    amount_str: str
    currency: str = "PYG"
    status: str = "LOCKED_SEAT"
    ticket_id: Optional[str] = None
    rollback_token_sent: Optional[str] = None
    audit_log: List[str] = field(default_factory=list)


class Bancard2PCOrchestrator:
    """Two-Phase Commit (2PC) coordinator between Bancard vPOS and GDS ticketing."""

    TERMINAL_STATES = (
        "TICKET_ISSUED",
        "PAYMENT_REVERSED",
        "PAYMENT_REVERSED_LATE_WEBHOOK",
        "ROLLBACK_MANUAL_REQUIRED",
        "PAYMENT_REJECTED",
    )

    def __init__(self, public_key: str, private_key: str) -> None:
        self.public_key = public_key
        self.private_key = private_key
        self.orders: Dict[int, OrderRecord] = {}

    def register_locked_order(
        self, shop_process_id: int, amount: int | float | Decimal, currency: str = "PYG"
    ) -> OrderRecord:
        amount_str = format_bancard_amount(amount)
        record = OrderRecord(shop_process_id=shop_process_id, amount_str=amount_str, currency=currency)
        record.audit_log.append("SEAT_LOCKED_AND_PAYMENT_INITIATED")
        self.orders[shop_process_id] = record
        return record

    def mark_order_expired(self, shop_process_id: int) -> None:
        order = self.orders.get(shop_process_id)
        if order and order.status == "LOCKED_SEAT":
            order.status = "EXPIRED"
            order.audit_log.append("SEAT_LOCK_TTL_EXPIRED")

    def _execute_rollback(
        self,
        order: OrderRecord,
        reason_tag: str,
        target_status: str,
        rollback_gateway_callback: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        rb_token = generate_bancard_rollback_token(self.private_key, order.shop_process_id)
        order.rollback_token_sent = rb_token
        rollback_payload = {
            "public_key": self.public_key,
            "operation": {"token": rb_token, "shop_process_id": order.shop_process_id},
        }
        if rollback_gateway_callback is not None:
            gw_res = rollback_gateway_callback(rollback_payload)
            messages = gw_res.get("messages", [])
            if any(
                m.get("key") in ("TransactionAlreadyConfirmed", "PaymentAlreadyConfirmedError")
                for m in messages
            ):
                order.status = "ROLLBACK_MANUAL_REQUIRED"
                order.audit_log.append(f"ROLLBACK_FAILED_ALREADY_CONFIRMED:{reason_tag}")
                return {
                    "http_status": 200,
                    "status": "manual_refund_required",
                    "order_status": order.status,
                    "rollback_payload": rollback_payload,
                }
        order.status = target_status
        order.audit_log.append(reason_tag)
        return {
            "http_status": 200,
            "status": "rollback_executed",
            "order_status": order.status,
            "rollback_payload": rollback_payload,
        }

    def handle_webhook_or_poll(
        self,
        operation_payload: Dict[str, Any],
        gds_issue_callback: Callable[[OrderRecord], str],
        rollback_gateway_callback: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        shop_process_id = int(operation_payload["shop_process_id"])
        order = self.orders.get(shop_process_id)
        if order is None:
            return {"http_status": 404, "status": "error", "reason": "ORDER_NOT_FOUND"}

        amount_str = str(operation_payload.get("amount", ""))
        currency = str(operation_payload.get("currency", "PYG"))
        received_token = str(operation_payload.get("token", ""))

        if not verify_bancard_webhook_token(
            self.private_key, shop_process_id, amount_str, currency, received_token
        ):
            order.audit_log.append("INVALID_WEBHOOK_TOKEN_REJECTED")
            return {"http_status": 401, "status": "error", "reason": "INVALID_TOKEN"}

        if amount_str != order.amount_str or currency != order.currency:
            order.audit_log.append(
                f"AMOUNT_OR_CURRENCY_MISMATCH:expected={order.amount_str}_{order.currency}:got={amount_str}_{currency}"
            )
            return {"http_status": 400, "status": "error", "reason": "AMOUNT_OR_CURRENCY_MISMATCH"}

        # Idempotency guard: if already in terminal state, return 200 OK without re-running side effects
        if order.status in self.TERMINAL_STATES:
            order.audit_log.append(f"IDEMPOTENT_REPLAY:{order.status}")
            return {"http_status": 200, "status": "success", "idempotent": True, "order_status": order.status}

        response_flag = operation_payload.get("response")
        response_code = operation_payload.get("response_code")

        if response_flag == "S" and response_code == "00":
            # Edge case 3.1: Late webhook arriving after seat lock TTL already expired
            if order.status == "EXPIRED":
                return self._execute_rollback(
                    order=order,
                    reason_tag="2PC_LATE_WEBHOOK_ON_EXPIRED_ORDER_REVERSED",
                    target_status="PAYMENT_REVERSED_LATE_WEBHOOK",
                    rollback_gateway_callback=rollback_gateway_callback,
                )

            try:
                ticket_id = gds_issue_callback(order)
                order.ticket_id = ticket_id
                order.status = "TICKET_ISSUED"
                order.audit_log.append(f"2PC_COMMIT_OK:{ticket_id}")
                return {"http_status": 200, "status": "success", "order_status": order.status, "ticket_id": ticket_id}
            except Exception as exc:
                # 2PC Compensation: GDS failed after card was charged -> automatic Bancard rollback
                return self._execute_rollback(
                    order=order,
                    reason_tag=f"2PC_ROLLBACK_TRIGGERED:{type(exc).__name__}:{exc}",
                    target_status="PAYMENT_REVERSED",
                    rollback_gateway_callback=rollback_gateway_callback,
                )
        else:
            order.status = "PAYMENT_REJECTED"
            order.audit_log.append(f"PAYMENT_DECLINED:{response_code}")
            return {"http_status": 200, "status": "acknowledged", "order_status": order.status}


# ============================================================================
# 2. PAGOPAR (PARAGUAY) — SHA-1 TOKENS & WEBHOOK VERIFICATION
# ============================================================================

def generate_pagopar_init_token(
    private_key: str, id_pedido_comercio: str | int, monto_total: int | float | Decimal | str
) -> str:
    if not private_key or str(id_pedido_comercio) == "" or isinstance(monto_total, bool):
        raise ValueError("Pagopar private_key, id_pedido_comercio, and numeric monto_total are required")
    try:
        dec = Decimal(str(monto_total))
    except Exception as exc:
        raise ValueError(f"Invalid Pagopar monto_total: {monto_total!r}") from exc
    if not dec.is_finite() or dec <= 0:
        raise ValueError(f"Pagopar monto_total must be positive and finite, got: {monto_total!r}")
    monto_str = str(int(dec)) if dec == dec.to_integral_value() else (
        str(monto_total) if isinstance(monto_total, str) else format(dec, "f")
    )
    raw = f"{private_key}{id_pedido_comercio}{monto_str}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def verify_pagopar_webhook_token(private_key: str, hash_pedido: str, received_token: str) -> bool:
    if not private_key or not hash_pedido or not received_token:
        return False
    expected = hashlib.sha1(f"{private_key}{hash_pedido}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, received_token.lower())


def generate_pagopar_action_token(private_key: str, action_literal: str = "CONSULTA") -> str:
    if not private_key or not action_literal:
        raise ValueError("private_key and action_literal are required")
    return hashlib.sha1(f"{private_key}{action_literal}".encode("utf-8")).hexdigest()


# ============================================================================
# 3. SIFEN / EKUATIA (DNIT PARAGUAY v150) — CDC, IVA, X.509 XMLDSIG & KUDE PDF
# ============================================================================

def calculate_sifen_mod11(numeric_chain: str, max_weight: int = 11) -> int:
    """Official DNIT Paraguay Module-11 check digit calculation."""
    if not re.match(r"^\d+$", str(numeric_chain)):
        raise ValueError(f"SIFEN Mod-11 input must be strictly numeric, got: {numeric_chain!r}")
    weight = 2
    total = 0
    for digit_char in reversed(numeric_chain):
        total += int(digit_char) * weight
        weight = 2 if weight >= max_weight else weight + 1
    remainder = total % 11
    return 0 if remainder <= 1 else 11 - remainder


def generate_sifen_cdc_44(
    tipo_de: int | str,
    ruc_emisor: str,
    dv_emisor: int | str,
    establecimiento: int | str,
    punto_expedicion: int | str,
    numero_documento: int | str,
    tipo_contribuyente: int | str,
    fecha_emision_yyyymmdd: str,
    tipo_emision: int | str,
    codigo_seguridad_9: int | str,
) -> str:
    """Build the 44-digit Código de Control (CDC) per SIFEN Technical Manual v150."""
    expected_ruc_dv = calculate_sifen_mod11(str(ruc_emisor).zfill(8), 11)
    if int(dv_emisor) != expected_ruc_dv:
        raise ValueError(f"RUC DV mismatch: ruc={ruc_emisor} expects DV={expected_ruc_dv}, got {dv_emisor}")

    if not re.match(r"^\d{8}$", str(fecha_emision_yyyymmdd)):
        raise ValueError(f"fecha_emision_yyyymmdd must be 8 digits YYYYMMDD, got: {fecha_emision_yyyymmdd!r}")

    sec_code_str = str(codigo_seguridad_9).zfill(9)
    if not re.match(r"^\d{9}$", sec_code_str) or int(sec_code_str) == 0:
        raise ValueError(f"codigo_seguridad_9 must be a 9-digit non-zero number, got: {codigo_seguridad_9!r}")

    base_43 = (
        str(tipo_de).zfill(2)
        + str(ruc_emisor).zfill(8)
        + str(dv_emisor)
        + str(establecimiento).zfill(3)
        + str(punto_expedicion).zfill(3)
        + str(numero_documento).zfill(7)
        + str(tipo_contribuyente)
        + str(fecha_emision_yyyymmdd)
        + str(tipo_emision)
        + sec_code_str
    )
    if len(base_43) != 43 or not base_43.isdigit():
        raise ValueError(f"Invalid 43-digit CDC base: {base_43!r}")

    dv_id = calculate_sifen_mod11(base_43, 11)
    return f"{base_43}{dv_id}"


def verify_sifen_cdc_44(cdc_44: str) -> bool:
    if not isinstance(cdc_44, str) or not re.match(r"^\d{44}$", cdc_44):
        return False
    expected_dv = calculate_sifen_mod11(cdc_44[:43], 11)
    return int(cdc_44[43]) == expected_dv


def liquidate_pyg_iva(gross_amount_pyg: int, rate: int) -> Dict[str, int]:
    """Calculate integer PYG Base Gravada and Liquidación IVA for 10%, 5%, or 0% (Exenta)."""
    if isinstance(gross_amount_pyg, bool) or not isinstance(gross_amount_pyg, int) or gross_amount_pyg < 0:
        raise ValueError(f"PYG amount must be a non-negative integer, got: {gross_amount_pyg!r}")
    if rate == 10:
        iva = int((Decimal(gross_amount_pyg) / Decimal(11)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        base = gross_amount_pyg - iva
        return {"gross": gross_amount_pyg, "base_gravada": base, "iva": iva, "exenta": 0}
    if rate == 5:
        iva = int((Decimal(gross_amount_pyg) / Decimal(21)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        base = gross_amount_pyg - iva
        return {"gross": gross_amount_pyg, "base_gravada": base, "iva": iva, "exenta": 0}
    if rate == 0:
        return {"gross": gross_amount_pyg, "base_gravada": 0, "iva": 0, "exenta": gross_amount_pyg}
    raise ValueError(f"Unsupported Paraguayan IVA rate: {rate}. Must be 10, 5, or 0.")


def liquidate_sifen_item(
    unit_price: int | float | Decimal,
    quantity: int | float | Decimal = 1,
    rate: int = 10,
    discount: int | float | Decimal = 0,
    currency: str = "PYG",
) -> Dict[str, Any]:
    """Liquidate a single SIFEN item supporting PYG (integer) or USD (2-decimal) and per-item discounts."""
    if rate not in (10, 5, 0):
        raise ValueError(f"Unsupported IVA rate: {rate}")
    quant = Decimal("1") if currency == "PYG" else Decimal("0.01")
    up = Decimal(str(unit_price)).quantize(quant, rounding=ROUND_HALF_UP)
    qty = Decimal(str(quantity))
    disc = Decimal(str(discount)).quantize(quant, rounding=ROUND_HALF_UP)
    gross_subtotal = (up * qty).quantize(quant, rounding=ROUND_HALF_UP)
    if disc < 0 or disc > gross_subtotal:
        raise ValueError(f"Invalid item discount {disc} for gross subtotal {gross_subtotal}")
    net_total = (gross_subtotal - disc).quantize(quant, rounding=ROUND_HALF_UP)

    if rate == 10:
        iva = (net_total / Decimal(11)).quantize(quant, rounding=ROUND_HALF_UP)
        base = (net_total - iva).quantize(quant, rounding=ROUND_HALF_UP)
        exenta = Decimal(0).quantize(quant)
        afec_iva, desc_afec, prop_iva = "1", "Gravado IVA", "100"
    elif rate == 5:
        iva = (net_total / Decimal(21)).quantize(quant, rounding=ROUND_HALF_UP)
        base = (net_total - iva).quantize(quant, rounding=ROUND_HALF_UP)
        exenta = Decimal(0).quantize(quant)
        afec_iva, desc_afec, prop_iva = "1", "Gravado IVA", "100"
    else:
        iva = Decimal(0).quantize(quant)
        base = Decimal(0).quantize(quant)
        exenta = net_total
        afec_iva, desc_afec, prop_iva = "3", "Exento", "0"

    fmt = (lambda d: int(d)) if currency == "PYG" else (lambda d: f"{d:.2f}")
    return {
        "unit_price": fmt(up),
        "quantity": str(qty),
        "gross_subtotal": fmt(gross_subtotal),
        "discount": fmt(disc),
        "net_total": fmt(net_total),
        "rate": rate,
        "base_gravada": fmt(base),
        "iva": fmt(iva),
        "exenta": fmt(exenta),
        "afec_iva": afec_iva,
        "desc_afec_iva": desc_afec,
        "prop_iva": prop_iva,
        "_dec_net": net_total,
        "_dec_disc": disc,
        "_dec_base": base,
        "_dec_iva": iva,
        "_dec_exenta": exenta,
    }


def build_sifen_qr_url(
    base_url: str,
    cdc_44: str,
    fecha_emision_iso: str,
    ruc_receptor: str,
    tot_gral_ope: int | str | Decimal,
    tot_iva: int | str | Decimal,
    c_items: int,
    digest_value_base64: str,
    id_csc: str,
    csc_secret: str,
    nat_receptor: int = 1,
) -> str:
    """Compute the official SIFEN v150 QR URL with SHA-256 cHashQR (supports iNatRec=1 RUC and iNatRec=2 ID)."""
    if not verify_sifen_cdc_44(cdc_44):
        raise ValueError(f"Invalid 44-digit CDC: {cdc_44!r}")
    if not csc_secret or len(csc_secret) < 8:
        raise ValueError("Invalid DNIT CSC secret token")
    if nat_receptor not in (1, 2):
        raise ValueError(f"nat_receptor must be 1 (Contribuyente) or 2 (No Contribuyente), got {nat_receptor}")

    fecha_hex = fecha_emision_iso.encode("utf-8").hex()
    digest_hex = digest_value_base64.encode("utf-8").hex()
    id_csc_padded = str(id_csc).zfill(4)
    rec_param = f"dRucRec={ruc_receptor}" if nat_receptor == 1 else f"dNumIDRec={ruc_receptor}"

    query_params = (
        f"nVersion=150"
        f"&Id={cdc_44}"
        f"&dFeEmiDE={fecha_hex}"
        f"&{rec_param}"
        f"&dTotGralOpe={tot_gral_ope}"
        f"&dTotIVA={tot_iva}"
        f"&cItems={c_items}"
        f"&DigestValue={digest_hex}"
        f"&IdCSC={id_csc_padded}"
    )
    c_hash_qr = hashlib.sha256(f"{query_params}{csc_secret}".encode("utf-8")).hexdigest()
    sep = "" if base_url.endswith("?") else "?"
    return f"{base_url}{sep}{query_params}&cHashQR={c_hash_qr}"


_CACHED_TEST_PKCS12: Optional[Tuple[rsa.RSAPrivateKey, x509.Certificate, bytes]] = None


def generate_or_load_sifen_pkcs12(
    ruc_emisor: str = "80171570",
    dv_emisor: int | str = 9,
    nombre_emisor: str = "BOLETOS.LA E.A.S.",
    p12_bytes: Optional[bytes] = None,
    p12_password: Optional[bytes] = b"sifen-secret-pass",
) -> Tuple[rsa.RSAPrivateKey, x509.Certificate, bytes]:
    """
    Load a taxpayer's PKCS#12 (.p12/.pfx) X.509 certificate and RSA private key,
    or generate an accredited-format X.509 certificate + .p12 bundle in memory for offline testing.
    """
    global _CACHED_TEST_PKCS12
    if p12_bytes is not None:
        priv_key, cert, _ = pkcs12.load_key_and_certificates(p12_bytes, p12_password)
        if not isinstance(priv_key, rsa.RSAPrivateKey) or cert is None:
            raise ValueError("PKCS#12 bundle must contain an RSA private key and X.509 certificate")
        return priv_key, cert, p12_bytes

    if _CACHED_TEST_PKCS12 is not None:
        return _CACHED_TEST_PKCS12

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "PY"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, nombre_emisor),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, f"RUC-{ruc_emisor}-{dv_emisor}"),
            x509.NameAttribute(NameOID.COMMON_NAME, nombre_emisor),
        ]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(private_key, hashes.SHA256())
    )
    serialized_p12 = pkcs12.serialize_key_and_certificates(
        name=b"sifen-taxpayer-key",
        key=private_key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(p12_password)
        if p12_password
        else serialization.NoEncryption(),
    )
    _CACHED_TEST_PKCS12 = (private_key, cert, serialized_p12)
    return _CACHED_TEST_PKCS12


def verify_sifen_xmldsig(signed_xml: str) -> Dict[str, Any]:
    """
    Verify a signed SIFEN v150 rDE XML document:
    1. Canonicalizes <DE Id="..."> with C14N and compares SHA-256 digest against <DigestValue>.
    2. Extracts the X.509 certificate from <X509Certificate>, canonicalizes <SignedInfo>,
       and verifies the RSA-SHA256 signature in <SignatureValue>.
    """
    sifen_ns = "http://ekuatia.set.gov.py/sifen/xsd"
    dsig_ns = "http://www.w3.org/2000/09/xmldsig#"
    root = ET.fromstring(signed_xml)
    de_elem = root.find(f"{{{sifen_ns}}}DE")
    sig_elem = root.find(f"{{{dsig_ns}}}Signature")
    if de_elem is None or sig_elem is None:
        return {"valid": False, "reason": "MISSING_DE_OR_SIGNATURE_NODE"}

    signed_info_elem = sig_elem.find(f"{{{dsig_ns}}}SignedInfo")
    sig_val_elem = sig_elem.find(f"{{{dsig_ns}}}SignatureValue")
    cert_elem = sig_elem.find(f".//{{{dsig_ns}}}X509Certificate")
    digest_elem = sig_elem.find(f".//{{{dsig_ns}}}DigestValue")
    if None in (signed_info_elem, sig_val_elem, cert_elem, digest_elem):
        return {"valid": False, "reason": "INCOMPLETE_SIGNATURE_ELEMENTS"}

    de_c14n = ET.canonicalize(ET.tostring(de_elem, encoding="utf-8"), with_comments=False).encode("utf-8")
    expected_digest_b64 = base64.b64encode(hashlib.sha256(de_c14n).digest()).decode("ascii")
    actual_digest_b64 = (digest_elem.text or "").strip()
    if expected_digest_b64 != actual_digest_b64:
        return {
            "valid": False,
            "reason": "DIGEST_VALUE_MISMATCH",
            "expected": expected_digest_b64,
            "actual": actual_digest_b64,
        }

    signed_info_c14n = ET.canonicalize(
        ET.tostring(signed_info_elem, encoding="utf-8"), with_comments=False
    ).encode("utf-8")
    cert_der = base64.b64decode((cert_elem.text or "").strip())
    cert = x509.load_der_x509_certificate(cert_der)
    pub_key = cert.public_key()
    sig_bytes = base64.b64decode((sig_val_elem.text or "").strip())

    try:
        pub_key.verify(sig_bytes, signed_info_c14n, padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:
        return {"valid": False, "reason": f"RSA_SIGNATURE_INVALID:{exc}"}

    return {
        "valid": True,
        "cdc_44": de_elem.attrib.get("Id", ""),
        "digest_value": actual_digest_b64,
        "cert_subject": cert.subject.rfc4514_string(),
    }


def generate_sifen_kude_pdf(
    cdc_44: str,
    nombre_emisor: str,
    ruc_emisor_full: str,
    timbrado: str,
    nro_documento: str,
    fecha_emision_iso: str,
    nombre_receptor: str,
    doc_receptor: str,
    items: List[Dict[str, Any]],
    tax_summary: Dict[str, Any],
    qr_url: str,
    currency: str = "PYG",
) -> bytes:
    """
    Generate a standards-compliant %PDF-1.4 KuDE (Representación Gráfica del DE) binary document
    including Emitter Header, Timbrado, Receiver Data, Itemized Table, IVA Breakdown,
    44-digit CDC in 11 groups of 4 digits, DNIT legal legend, and embedded Tax QR matrix + URL.
    """
    cdc_formatted = " ".join(cdc_44[i : i + 4] for i in range(0, 44, 4))

    def _pdf_escape(text: str) -> str:
        clean = text.encode("latin-1", errors="replace").decode("latin-1")
        return clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    lines = [
        f"KuDE - FACTURA ELECTRONICA SIFEN DNIT v150 ({currency})",
        f"Emisor: {nombre_emisor} | RUC: {ruc_emisor_full}",
        f"Timbrado Nro: {timbrado} | Factura: {nro_documento}",
        f"Fecha Emision: {fecha_emision_iso}",
        f"Receptor: {nombre_receptor} | Doc/RUC: {doc_receptor}",
        "-" * 68,
        "CANT | DESCRIPCION                       | P.UNIT   | DESC  | SUBTOTAL | IVA",
        "-" * 68,
    ]
    for it in items:
        desc = str(it.get("descripcion", "Item"))[:32].ljust(32)
        qty = str(it.get("quantity", "1")).ljust(4)
        pu = str(it.get("unit_price", 0)).rjust(8)
        disc = str(it.get("discount", 0)).rjust(5)
        sub = str(it.get("net_total", 0)).rjust(8)
        rate_str = f"{it.get('rate', 10)}%" if int(it.get("rate", 10)) > 0 else "EXE"
        lines.append(f"{qty} | {desc} | {pu} | {disc} | {sub} | {rate_str}")

    lines.extend(
        [
            "-" * 68,
            f"Subtotal Exentas: {tax_summary['sub_exenta']} | Gravadas 5%: {tax_summary['sub_5']} | Gravadas 10%: {tax_summary['sub_10']}",
            f"Liquidacion IVA 5%: {tax_summary['iva_5']} | IVA 10%: {tax_summary['iva_10']} | Total IVA: {tax_summary['tot_iva']}",
            f"TOTAL GENERAL DE LA OPERACION ({currency}): {tax_summary['tot_gral_ope']}",
            "-" * 68,
            f"CDC (44 digitos): {cdc_formatted}",
            "Consulte la validez de esta Factura Electronica con el numero de CDC impreso",
            "abajo en: https://ekuatia.set.gov.py/consultas/",
            f"QR Tributario: {qr_url[:82]}",
            f"               {qr_url[82:164]}",
            f"               {qr_url[164:]}",
        ]
    )

    stream_cmds = ["BT", "/F1 9 Tf", "36 790 Td", "12 TL"]
    for idx, line in enumerate(lines):
        escaped = _pdf_escape(line)
        if idx == 0:
            stream_cmds.append(f"({escaped}) Tj")
        else:
            stream_cmds.append(f"T* ({escaped}) Tj")
    stream_cmds.append("ET")

    # Draw a deterministic 21x21 QR finder/data matrix graphic in the lower-left footer (2.5cm x 2.5cm = 72pt x 72pt)
    qr_digest = hashlib.sha256(qr_url.encode("utf-8")).digest()
    cell_size = 3.0
    base_x, base_y = 36.0, 420.0
    stream_cmds.append("0 0 0 rg")
    for r in range(21):
        for c in range(21):
            in_finder = (r < 7 and c < 7) or (r < 7 and c >= 14) or (r >= 14 and c < 7)
            if in_finder:
                r_loc = r if r < 7 else r - 14
                c_loc = c if c < 7 else c - 14
                bit = (
                    r_loc in (0, 6)
                    or c_loc in (0, 6)
                    or (2 <= r_loc <= 4 and 2 <= c_loc <= 4)
                )
            else:
                bit_idx = (r * 21 + c) % (len(qr_digest) * 8)
                bit = bool((qr_digest[bit_idx // 8] >> (bit_idx % 8)) & 1)
            if bit:
                x = base_x + c * cell_size
                y = base_y + (20 - r) * cell_size
                stream_cmds.append(f"{x:.1f} {y:.1f} {cell_size:.1f} {cell_size:.1f} re f")

    content_bytes = "\n".join(stream_cmds).encode("latin-1")

    objects: List[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(content_bytes)} >>\nstream\n".encode("latin-1")
        + content_bytes
        + b"\nendstream\nendobj\n",
    ]

    pdf_body = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: List[int] = []
    for obj in objects:
        offsets.append(len(pdf_body))
        pdf_body.extend(obj)

    xref_offset = len(pdf_body)
    xref_lines = [f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"]
    for off in offsets:
        xref_lines.append(f"{off:010d} 00000 n \n")
    pdf_body.extend("".join(xref_lines).encode("latin-1"))
    pdf_body.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    )
    return bytes(pdf_body)


def generate_signed_sifen_de_xml(
    cdc_44: str,
    fecha_emision_iso: str,
    ruc_emisor: str,
    dv_emisor: int,
    nombre_emisor: str,
    ruc_receptor: str,
    dv_receptor: int,
    nombre_receptor: str,
    item_descripcion: str = "Servicio de transporte",
    amount_pyg: int = 150000,
    tasa_iva: int = 10,
    id_csc: str = "0001",
    csc_secret: str = "ABCD1234EFGH5678IJKL9012MNOP3456",
    qr_base_url: str = "https://ekuatia.set.gov.py/consultas-test/qr?",
    nat_receptor: int = 1,
    currency: str = "PYG",
    exchange_rate: Optional[int | float | Decimal] = None,
    items: Optional[List[Dict[str, Any]]] = None,
    p12_bytes: Optional[bytes] = None,
    p12_password: Optional[bytes] = b"sifen-secret-pass",
    timbrado: str = "19019949",
) -> Dict[str, Any]:
    """
    Render a valid SIFEN v150 rDE XML supporting:
    - Single or multiple items mixing IVA 10%, IVA 5%, and Exenta (0%) + per-item discounts (dDescItem)
    - DE_v150.xsd <gDatRec> mutual exclusivity: iNatRec=1 (<iTiContRec>, <dRucRec>, <dDVRec>) vs
      iNatRec=2 (<iTipIDRec>1</iTipIDRec>, <dDTipIDRec>Cédula paraguaya</dDTipIDRec>, <dNumIDRec>)
    - PYG (integer) and USD (fractional with exchange rate dTiCam)
    - Real XML Exclusive Canonicalization (xml-exc-c14n#) over <DE Id="{CDC}">
    - Real X.509 RSA-SHA256 XMLDSig signature using PKCS#12 (.p12) private key and certificate
    - Official SHA-256 KuDE Tax QR URL (<dCarQR>) and %PDF-1.4 KuDE PDF document bytes
    """
    if currency not in ("PYG", "USD"):
        raise ValueError(f"Unsupported SIFEN currency: {currency}")
    if currency == "USD" and (exchange_rate is None or Decimal(str(exchange_rate)) <= 0):
        raise ValueError("USD SIFEN documents require a positive exchange_rate (dTiCam)")
    if nat_receptor not in (1, 2):
        raise ValueError(f"nat_receptor must be 1 (Contribuyente) or 2 (No Contribuyente), got {nat_receptor!r}")
    timbrado_str = str(timbrado)
    if not re.fullmatch(r"\d{8}", timbrado_str):
        raise ValueError(f"SIFEN dNumTim (timbrado) must be an 8-digit string, got {timbrado!r}")

    with open(XML_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        xml_tpl = f.read()

    raw_items = items if items is not None else [
        {
            "codigo": "BOL-001",
            "descripcion": item_descripcion,
            "unit_price": amount_pyg,
            "quantity": 1,
            "rate": tasa_iva,
            "discount": 0,
        }
    ]
    if not raw_items:
        raise ValueError("SIFEN DE requires at least one item")

    quant = Decimal("1") if currency == "PYG" else Decimal("0.01")
    fmt = (lambda d: int(d)) if currency == "PYG" else (lambda d: f"{d:.2f}")

    liquidated_items: List[Dict[str, Any]] = []
    dec_sub_exenta = Decimal(0).quantize(quant)
    dec_sub_5 = Decimal(0).quantize(quant)
    dec_sub_10 = Decimal(0).quantize(quant)
    dec_iva_5 = Decimal(0).quantize(quant)
    dec_iva_10 = Decimal(0).quantize(quant)
    dec_base_5 = Decimal(0).quantize(quant)
    dec_base_10 = Decimal(0).quantize(quant)
    dec_tot_desc = Decimal(0).quantize(quant)

    for idx, raw_it in enumerate(raw_items, start=1):
        liq = liquidate_sifen_item(
            unit_price=raw_it.get("unit_price", raw_it.get("amount", 0)),
            quantity=raw_it.get("quantity", 1),
            rate=int(raw_it.get("rate", 10)),
            discount=raw_it.get("discount", 0),
            currency=currency,
        )
        liq["codigo"] = str(raw_it.get("codigo", f"ITM-{idx:03d}"))
        liq["descripcion"] = str(raw_it.get("descripcion", f"Item {idx}"))
        liquidated_items.append(liq)

        dec_tot_desc += liq["_dec_disc"]
        if liq["rate"] == 10:
            dec_sub_10 += liq["_dec_net"]
            dec_iva_10 += liq["_dec_iva"]
            dec_base_10 += liq["_dec_base"]
        elif liq["rate"] == 5:
            dec_sub_5 += liq["_dec_net"]
            dec_iva_5 += liq["_dec_iva"]
            dec_base_5 += liq["_dec_base"]
        else:
            dec_sub_exenta += liq["_dec_exenta"]

    dec_tot_ope = (dec_sub_exenta + dec_sub_5 + dec_sub_10).quantize(quant, rounding=ROUND_HALF_UP)
    dec_tot_iva = (dec_iva_5 + dec_iva_10).quantize(quant, rounding=ROUND_HALF_UP)
    dec_tot_base = (dec_base_5 + dec_base_10).quantize(quant, rounding=ROUND_HALF_UP)

    first_item = liquidated_items[0]
    from xml.sax.saxutils import escape as xml_escape

    sanitized_rec_doc = re.sub(r"[.\-\s]", "", str(ruc_receptor))
    tipo_cont_rec = "2" if (sanitized_rec_doc.isdigit() and int(sanitized_rec_doc) >= 80000000) else "1"
    tipo_ope_rec = "1" if (nat_receptor == 1 and tipo_cont_rec == "2") else "2"

    if nat_receptor == 2:
        taxpayer_block = (
            "        <iTiContRec>{{TIPO_CONT_RECEPTOR}}</iTiContRec>\n"
            "        <dRucRec>{{RUC_RECEPTOR}}</dRucRec>\n"
            "        <dDVRec>{{DV_RECEPTOR}}</dDVRec>"
        )
        non_taxpayer_block = (
            "        <iTipIDRec>1</iTipIDRec>\n"
            "        <dDTipIDRec>Cédula paraguaya</dDTipIDRec>\n"
            f"        <dNumIDRec>{xml_escape(sanitized_rec_doc)}</dNumIDRec>"
        )
        if taxpayer_block not in xml_tpl:
            raise RuntimeError("Missing expected <gDatRec> taxpayer placeholders in SIFEN XML template")
        xml_tpl = xml_tpl.replace(taxpayer_block, non_taxpayer_block)

    replacements = {
        "{{CDC_44}}": cdc_44,
        "{{DV_ID}}": cdc_44[-1],
        "{{FECHA_FIRMA_ISO}}": fecha_emision_iso,
        "{{TIPO_EMISION}}": cdc_44[33],
        "{{DESC_TIPO_EMISION}}": "Normal" if cdc_44[33] == "1" else "Contingencia",
        "{{CODIGO_SEGURIDAD_9}}": cdc_44[34:43],
        "{{TIPO_DE}}": str(int(cdc_44[0:2])),
        "{{DESC_TIPO_DE}}": "Factura electrónica",
        "{{NUMERO_TIMBRADO_8}}": timbrado_str,
        "{{ESTABLECIMIENTO_3}}": cdc_44[11:14],
        "{{PUNTO_EXPEDICION_3}}": cdc_44[14:17],
        "{{NUMERO_DOCUMENTO_7}}": cdc_44[17:24],
        "{{FECHA_INICIO_TIMBRADO}}": "2026-01-01",
        "{{FECHA_EMISION_ISO}}": fecha_emision_iso,
        "{{RUC_EMISOR}}": ruc_emisor,
        "{{DV_EMISOR}}": str(dv_emisor),
        "{{TIPO_CONTRIBUYENTE}}": cdc_44[24],
        "{{NOMBRE_EMISOR}}": xml_escape(str(nombre_emisor)),
        "{{DIRECCION_EMISOR}}": "AV. MARISCAL LOPEZ 1234",
        "{{TELEFONO_EMISOR}}": "021456789",
        "{{EMAIL_EMISOR}}": "facturacion@empresa.com.py",
        "{{CODIGO_ACTIVIDAD}}": "49221",
        "{{DESC_ACTIVIDAD}}": "Transporte interurbano de pasajeros",
        "{{NATURALEZA_RECEPTOR}}": str(nat_receptor),
        "{{TIPO_OPERACION_RECEPTOR}}": tipo_ope_rec,
        "{{TIPO_CONT_RECEPTOR}}": tipo_cont_rec,
        "{{RUC_RECEPTOR}}": sanitized_rec_doc,
        "{{DV_RECEPTOR}}": str(dv_receptor),
        "{{NOMBRE_RECEPTOR}}": xml_escape(str(nombre_receptor)),
        "{{TIPO_PAGO_SIFEN}}": "3",
        "{{DESC_TIPO_PAGO_SIFEN}}": "Tarjeta de crédito",
        "{{TOTAL_OPERACION}}": str(fmt(dec_tot_ope)),
        "{{ITEM_CODIGO}}": xml_escape(str(first_item["codigo"])),
        "{{ITEM_DESCRIPCION}}": xml_escape(str(first_item["descripcion"])),
        "{{ITEM_CANTIDAD}}": first_item["quantity"],
        "{{ITEM_PRECIO_UNITARIO}}": str(first_item["unit_price"]),
        "{{ITEM_SUBTOTAL}}": str(first_item["gross_subtotal"]),
        "{{ITEM_DESCUENTO}}": str(first_item["discount"]),
        "{{ITEM_TOTAL_OPERACION}}": str(first_item["net_total"]),
        "{{ITEM_AFEC_IVA}}": first_item["afec_iva"],
        "{{ITEM_DESC_AFEC_IVA}}": first_item["desc_afec_iva"],
        "{{ITEM_PROP_IVA}}": first_item["prop_iva"],
        "{{ITEM_TASA_IVA}}": str(first_item["rate"]),
        "{{ITEM_BASE_GRAVADA}}": str(first_item["base_gravada"]),
        "{{ITEM_LIQ_IVA}}": str(first_item["iva"]),
        "{{SUB_EXENTA}}": str(fmt(dec_sub_exenta)),
        "{{SUB_IVA_5}}": str(fmt(dec_sub_5)),
        "{{SUB_IVA_10}}": str(fmt(dec_sub_10)),
        "{{LIQ_IVA_5}}": str(fmt(dec_iva_5)),
        "{{LIQ_IVA_10}}": str(fmt(dec_iva_10)),
        "{{TOTAL_IVA}}": str(fmt(dec_tot_iva)),
        "{{BASE_GRAV_5}}": str(fmt(dec_base_5)),
        "{{BASE_GRAV_10}}": str(fmt(dec_base_10)),
        "{{TOTAL_BASE_GRAVADA}}": str(fmt(dec_tot_base)),
        "{{DIGEST_VALUE_BASE64}}": "__PENDING_DIGEST__",
        "{{SIGNATURE_VALUE_BASE64}}": "__PENDING_SIG__",
        "{{X509_CERTIFICATE_BASE64}}": "__PENDING_CERT__",
        "{{URL_QR_TRIBUTARIO}}": "__PENDING_QR__",
    }

    rendered_xml = xml_tpl
    for k, v in replacements.items():
        rendered_xml = rendered_xml.replace(k, v)

    if currency == "USD":
        tc_str = str(Decimal(str(exchange_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        rendered_xml = rendered_xml.replace(
            "<cMoneOpe>PYG</cMoneOpe>\n        <dDesMoneOpe>Guarani</dDesMoneOpe>",
            f"<cMoneOpe>USD</cMoneOpe>\n        <dDesMoneOpe>Dolar Estadounidense</dDesMoneOpe>\n        <dCondTiCam>1</dCondTiCam>\n        <dTiCam>{tc_str}</dTiCam>",
        ).replace(
            "<cMoneTiPag>PYG</cMoneTiPag>\n          <dDMoneTiPag>Guarani</dDMoneTiPag>",
            "<cMoneTiPag>USD</cMoneTiPag>\n          <dDMoneTiPag>Dolar Estadounidense</dDMoneTiPag>",
        )

    if dec_tot_desc > 0:
        rendered_xml = rendered_xml.replace(
            "<dTotDesc>0</dTotDesc>", f"<dTotDesc>{fmt(dec_tot_desc)}</dTotDesc>"
        )

    # If multiple items are provided, insert additional <gCamItem> nodes before </gDtipDE>
    if len(liquidated_items) > 1:
        extra_nodes: List[str] = []
        for extra in liquidated_items[1:]:
            extra_nodes.append(
                f"""      <gCamItem>
        <dCodInt>{xml_escape(str(extra['codigo']))}</dCodInt>
        <dDesProSer>{xml_escape(str(extra['descripcion']))}</dDesProSer>
        <cUniMed>77</cUniMed>
        <dDesUniMed>UNI</dDesUniMed>
        <dCantProSer>{extra['quantity']}</dCantProSer>
        <gValorItem>
          <dPUniProSer>{extra['unit_price']}</dPUniProSer>
          <dTotBruOpeItem>{extra['gross_subtotal']}</dTotBruOpeItem>
          <gValorRestaItem>
            <dDescItem>{extra['discount']}</dDescItem>
            <dTotOpeItem>{extra['net_total']}</dTotOpeItem>
          </gValorRestaItem>
        </gValorItem>
        <gCamIVA>
          <iAfecIVA>{extra['afec_iva']}</iAfecIVA>
          <dDesAfecIVA>{extra['desc_afec_iva']}</dDesAfecIVA>
          <dPropIVA>{extra['prop_iva']}</dPropIVA>
          <dTasaIVA>{extra['rate']}</dTasaIVA>
          <dBasGravIVA>{extra['base_gravada']}</dBasGravIVA>
          <dLiqIVAItem>{extra['iva']}</dLiqIVAItem>
        </gCamIVA>
      </gCamItem>"""
            )
        rendered_xml = rendered_xml.replace(
            "    </gDtipDE>", "\n".join(extra_nodes) + "\n    </gDtipDE>"
        )

    # Step 1: Parse XML and compute real C14N SHA-256 DigestValue over <DE Id="{CDC_44}">
    sifen_ns = "http://ekuatia.set.gov.py/sifen/xsd"
    dsig_ns = "http://www.w3.org/2000/09/xmldsig#"
    tree_root = ET.fromstring(rendered_xml)
    de_elem = tree_root.find(f"{{{sifen_ns}}}DE")
    if de_elem is None:
        raise RuntimeError("Missing <DE> element in SIFEN template")

    de_c14n_bytes = ET.canonicalize(ET.tostring(de_elem, encoding="utf-8"), with_comments=False).encode("utf-8")
    digest_b64 = base64.b64encode(hashlib.sha256(de_c14n_bytes).digest()).decode("ascii")
    rendered_xml = rendered_xml.replace("__PENDING_DIGEST__", digest_b64)

    # Step 2: Load or generate PKCS#12 (.p12) RSA-2048 key + X.509 certificate and sign canonical <SignedInfo>
    priv_key, cert, _ = generate_or_load_sifen_pkcs12(
        ruc_emisor=ruc_emisor,
        dv_emisor=dv_emisor,
        nombre_emisor=nombre_emisor,
        p12_bytes=p12_bytes,
        p12_password=p12_password,
    )
    tree_with_digest = ET.fromstring(rendered_xml)
    signed_info_elem = tree_with_digest.find(f".//{{{dsig_ns}}}SignedInfo")
    if signed_info_elem is None:
        raise RuntimeError("Missing <SignedInfo> element in SIFEN template")

    signed_info_c14n_bytes = ET.canonicalize(
        ET.tostring(signed_info_elem, encoding="utf-8"), with_comments=False
    ).encode("utf-8")
    signature_bytes = priv_key.sign(signed_info_c14n_bytes, padding.PKCS1v15(), hashes.SHA256())
    signature_b64 = base64.b64encode(signature_bytes).decode("ascii")
    cert_b64 = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode("ascii")

    # Step 3: Compute official SHA-256 KuDE QR URL using the real XMLDSig DigestValue
    qr_url = build_sifen_qr_url(
        base_url=qr_base_url,
        cdc_44=cdc_44,
        fecha_emision_iso=fecha_emision_iso,
        ruc_receptor=sanitized_rec_doc,
        tot_gral_ope=fmt(dec_tot_ope),
        tot_iva=fmt(dec_tot_iva),
        c_items=len(liquidated_items),
        digest_value_base64=digest_b64,
        id_csc=id_csc,
        csc_secret=csc_secret,
        nat_receptor=nat_receptor,
    )

    rendered_xml = (
        rendered_xml.replace("__PENDING_SIG__", signature_b64)
        .replace("__PENDING_CERT__", cert_b64)
        .replace("__PENDING_QR__", qr_url.replace("&", "&amp;"))
    )

    # Parse final XML to guarantee well-formedness and verify signature
    final_root = ET.fromstring(rendered_xml)
    cdc_formatted = " ".join(cdc_44[i : i + 4] for i in range(0, 44, 4))

    tax_summary = {
        "gross": fmt(dec_tot_ope),
        "base_gravada": fmt(dec_tot_base),
        "iva": fmt(dec_tot_iva),
        "exenta": fmt(dec_sub_exenta),
        "sub_exenta": fmt(dec_sub_exenta),
        "sub_5": fmt(dec_sub_5),
        "sub_10": fmt(dec_sub_10),
        "iva_5": fmt(dec_iva_5),
        "iva_10": fmt(dec_iva_10),
        "tot_iva": fmt(dec_tot_iva),
        "tot_gral_ope": fmt(dec_tot_ope),
        "tot_desc": fmt(dec_tot_desc),
    }

    kude_pdf_bytes = generate_sifen_kude_pdf(
        cdc_44=cdc_44,
        nombre_emisor=nombre_emisor,
        ruc_emisor_full=f"{ruc_emisor}-{dv_emisor}",
        timbrado=timbrado_str,
        nro_documento=f"{cdc_44[11:14]}-{cdc_44[14:17]}-{cdc_44[17:24]}",
        fecha_emision_iso=fecha_emision_iso,
        nombre_receptor=nombre_receptor,
        doc_receptor=f"{sanitized_rec_doc}-{dv_receptor}" if nat_receptor == 1 else sanitized_rec_doc,
        items=liquidated_items,
        tax_summary=tax_summary,
        qr_url=qr_url,
        currency=currency,
    )

    return {
        "cdc_44": cdc_44,
        "cdc_kude_formatted": cdc_formatted,
        "xml": rendered_xml,
        "root_tag": final_root.tag,
        "qr_url": qr_url,
        "tax_summary": tax_summary,
        "digest_value": digest_b64,
        "signature_value": signature_b64,
        "kude_pdf_bytes": kude_pdf_bytes,
    }


# ============================================================================
# 4. TRANSBANK (CHILE WEBPAY PLUS v1.2 & POS INTEGRADO SERIAL LRC)
# ============================================================================

def evaluate_transbank_return_callback(callback_params: Dict[str, Optional[str]]) -> Dict[str, str]:
    """
    Classify the 4 mandatory return callback scenarios for Transbank Webpay Plus v1.2.
    """
    token_ws = callback_params.get("token_ws")
    tbk_token = callback_params.get("TBK_TOKEN")
    tbk_orden = callback_params.get("TBK_ORDEN_COMPRA")
    tbk_sesion = callback_params.get("TBK_ID_SESION")

    if token_ws and tbk_token:
        return {
            "scenario": "ANOMALOUS_DOUBLE_TOKEN",
            "action": "QUERY_STATUS_AND_RELEASE_LOCK",
            "token": token_ws,
        }
    if token_ws and not tbk_token:
        return {
            "scenario": "NORMAL_RETURN",
            "action": "COMMIT_TRANSACTION_PUT",
            "token": token_ws,
        }
    if tbk_token and not token_ws:
        return {
            "scenario": "ABORTED_BY_USER",
            "action": "RELEASE_SEAT_LOCK_IMMEDIATELY",
            "tbk_token": tbk_token,
            "buy_order": tbk_orden or "",
        }
    if not token_ws and not tbk_token and (tbk_orden or tbk_sesion):
        return {
            "scenario": "FORM_TIMEOUT_EXPIRED",
            "action": "MARK_EXPIRED_AND_RELEASE_LOCK",
            "buy_order": tbk_orden or "",
        }
    raise ValueError("Invalid Transbank callback payload: missing all Webpay parameters")


def calculate_transbank_pos_lrc(payload_plus_etx: bytes) -> int:
    """Calculate bitwise XOR Longitudinal Redundancy Check (LRC) over payload + ETX."""
    lrc = 0
    for b in payload_plus_etx:
        lrc ^= b
    return lrc


def build_transbank_pos_frame(command_payload: str) -> bytes:
    """Wrap an ASCII POS command (e.g., '0200|25900|100452||0') in STX + payload + ETX + LRC."""
    if not command_payload:
        raise ValueError("POS command_payload cannot be empty")
    body_plus_etx = command_payload.encode("ascii") + b"\x03"
    lrc = calculate_transbank_pos_lrc(body_plus_etx)
    return b"\x02" + body_plus_etx + bytes([lrc])


def verify_transbank_pos_frame(frame: bytes) -> Dict[str, Any]:
    """Validate STX, ETX, and LRC checksum of a Transbank POS Integrado serial frame."""
    if len(frame) < 4 or frame[0] != 0x02 or frame[-2] != 0x03:
        return {"valid": False, "reason": "INVALID_STX_OR_ETX"}
    expected_lrc = calculate_transbank_pos_lrc(frame[1:-1])
    received_lrc = frame[-1]
    if expected_lrc != received_lrc:
        return {"valid": False, "reason": "LRC_MISMATCH", "expected": expected_lrc, "received": received_lrc}
    ascii_payload = frame[1:-2].decode("ascii", errors="replace")
    return {"valid": True, "payload": ascii_payload, "fields": ascii_payload.split("|")}


def run_demo() -> Dict[str, Any]:
    cfg = load_domain_config()

    # 1. Bancard 2PC Happy Path + GDS Failure Rollback
    orchestrator = Bancard2PCOrchestrator("pub_key_demo", "priv_key_secret_123")
    orchestrator.register_locked_order(100501, 150000, "PYG")
    confirm_token_1 = hashlib.md5(b"priv_key_secret_123100501confirm150000.00PYG").hexdigest()
    commit_res = orchestrator.handle_webhook_or_poll(
        {
            "shop_process_id": 100501,
            "amount": "150000.00",
            "currency": "PYG",
            "response": "S",
            "response_code": "00",
            "token": confirm_token_1,
        },
        gds_issue_callback=lambda o: f"TKT-{o.shop_process_id}",
    )

    orchestrator.register_locked_order(100502, 150000, "PYG")
    confirm_token_2 = hashlib.md5(b"priv_key_secret_123100502confirm150000.00PYG").hexdigest()

    def failing_gds(_order: OrderRecord) -> str:
        raise TimeoutError("GDS Delta Bus Core timeout after 3500ms")

    rollback_res = orchestrator.handle_webhook_or_poll(
        {
            "shop_process_id": 100502,
            "amount": "150000.00",
            "currency": "PYG",
            "response": "S",
            "response_code": "00",
            "token": confirm_token_2,
        },
        gds_issue_callback=failing_gds,
    )

    # 2. SIFEN 44-digit CDC, Real X.509 RSA-SHA256 DE XML & KuDE PDF
    ruc_emisor = "80171570"
    dv_emisor = calculate_sifen_mod11(ruc_emisor.zfill(8))
    cdc = generate_sifen_cdc_44(
        tipo_de="01",
        ruc_emisor=ruc_emisor,
        dv_emisor=dv_emisor,
        establecimiento="001",
        punto_expedicion="004",
        numero_documento="0015420",
        tipo_contribuyente="2",
        fecha_emision_yyyymmdd="20261019",
        tipo_emision="1",
        codigo_seguridad_9="482910374",
    )
    de_bundle = generate_signed_sifen_de_xml(
        cdc_44=cdc,
        fecha_emision_iso="2026-10-19T14:30:00",
        ruc_emisor=ruc_emisor,
        dv_emisor=dv_emisor,
        nombre_emisor="BOLETOS.LA E.A.S.",
        ruc_receptor="4567890",
        dv_receptor=calculate_sifen_mod11("04567890"),
        nombre_receptor="JUAN PEREZ",
        item_descripcion="Pasaje Asunción - Ciudad del Este",
        amount_pyg=150000,
        tasa_iva=10,
        id_csc="0001",
        csc_secret="ABCD1234EFGH5678IJKL9012MNOP3456",
        nat_receptor=2,
    )
    xmldsig_check = verify_sifen_xmldsig(de_bundle["xml"])

    # 3. Transbank POS Frame & Paraguayan PY-QR / VentasQR / AdamsPay vectors
    pos_frame = build_transbank_pos_frame("0200|25900|100501||0")
    pos_verified = verify_transbank_pos_frame(pos_frame)
    py_qr_payload = build_paraguay_emvco_py_qr(
        merchant_guid="py.com.bancard",
        commerce_id="BOLETOS01",
        amount_pyg=150000,
        reference_id="ORD-100501",
    )
    ventas_qr_auth = build_bancard_ventas_qr_basic_auth("pub_key_demo", "priv_key_secret_123")
    adams_body = '{"notify":{"type":"debt","id":"ORD-100501"}}'
    adams_hash = hashlib.md5(f"adams{adams_body}adams_secret_demo".encode("utf-8")).hexdigest()

    return {
        "skill": cfg["skill"],
        "status": "ok",
        "bancard_2pc_commit": commit_res["order_status"],
        "bancard_2pc_rollback": rollback_res["order_status"],
        "bancard_ventas_qr_auth": ventas_qr_auth,
        "adamspay_webhook_valid": verify_adamspay_webhook_signature(adams_body, "adams_secret_demo", adams_hash),
        "adamspay_webhook_hash": adams_hash,
        "emvco_py_qr": py_qr_payload,
        "sifen_cdc_44": de_bundle["cdc_44"],
        "sifen_kude_cdc": de_bundle["cdc_kude_formatted"],
        "sifen_iva_10_pyg": de_bundle["tax_summary"]["iva"],
        "sifen_xmldsig_rsa_valid": xmldsig_check["valid"],
        "sifen_kude_pdf_size_bytes": len(de_bundle["kude_pdf_bytes"]),
        "transbank_pos_lrc_valid": pos_verified["valid"],
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, ensure_ascii=False))
