# -*- coding: utf-8 -*-
"""
Deterministic static, cryptographic, and cross-language validator for latam-fintech-payments-invoicing.
Verifies:
1. Canonical 5-component skill layout (SKILL.md, references/, resources/, examples/, scripts/) and zero
   hallucinated endpoints (explicitly asserts '/vpos/api/0.3/qr/generate' is never promoted as a real endpoint).
2. YAML frontmatter validity, progressive disclosure links, and documented CDC examples.
3. JSON schema of resources/config-template.json (Bancard v1.23, VentasQR, Caja POS Android v1.7 17 IssuerIds &
   5 wallets, Infonet, Pagopar 3.0 uPay, AdamsPay, Tigo Money, BCP PY-QR, SIFEN v150, Transbank) & XML template.
4. Cryptographic test vectors & edge cases for:
   - Bancard vPOS v1.23 (all 10+ MD5 tokens, 2PC rollback omitting currency, forged token, amount/currency
     mismatch, late webhook on EXPIRED order, PaymentAlreadyConfirmedError escalation).
   - Bancard VentasQR Basic Auth ('apps/{pub}:{priv}') & Caja POS Android v1.7 (cuotas=1 rejection, 12-digit
     nroBoleta, leading-zero wallet cuenta).
   - Pagopar (SHA-1 order init, FORMA-PAGO, PAGO-RECURRENTE & webhook verification) & AdamsPay raw-body MD5.
   - BCP SIPAP / SPI EMVCo PY-QR (CRC-16/CCITT-FALSE 0x1021 standard vector '123456789' == '29B1', ISO 4217
     '600' PYG, MCC '4131', and SPI Gs. 10.000.000 instant limit enforcement).
   - SIFEN DNIT v150 (44-digit CDC, Mod-11 weights 2..11, Ley 6380/2019 Art. 100 Num. 3 Inc. h transport IVA
     <=100km Exento vs >100km 10% and never 5%, multi-item 10%+5%+Exenta with discounts, non-taxpayer iNatRec=2
     QR, real X.509 PKCS#12 RSA-SHA256 XMLDSig over xml-exc-c14n# <DE>, tamper detection, and %PDF-1.4 KuDE).
   - Transbank (Webpay Plus 4 return scenarios & POS LRC).
5. Native Node.js TypeScript execution of examples/typescript_gateway_orchestrator.ts and cross-language
   vector parity between Python and TypeScript.

Run with:
    python scripts/validate_skill_domain.py
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from decimal import Decimal

sys.dont_write_bytecode = True

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_reference_module():
    ref_path = os.path.join(SKILL_ROOT, "examples", "reference_implementation.py")
    spec = importlib.util.spec_from_file_location("reference_implementation", ref_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {ref_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["reference_implementation"] = mod
    spec.loader.exec_module(mod)
    return mod


def validate_structure_and_frontmatter() -> list[str]:
    errors: list[str] = []
    required_files = [
        os.path.join(SKILL_ROOT, "SKILL.md"),
        os.path.join(SKILL_ROOT, "references", "architecture-and-patterns.md"),
        os.path.join(SKILL_ROOT, "references", "sifen-ekuatia-v150-xml-and-kude.md"),
        os.path.join(SKILL_ROOT, "references", "bancard-pagopar-transbank-webhooks.md"),
        os.path.join(SKILL_ROOT, "resources", "config-template.json"),
        os.path.join(SKILL_ROOT, "resources", "sifen-de-v150-template.xml"),
        os.path.join(SKILL_ROOT, "examples", "reference_implementation.py"),
        os.path.join(SKILL_ROOT, "examples", "typescript_gateway_orchestrator.ts"),
        os.path.join(SKILL_ROOT, "scripts", "validate_skill_domain.py"),
    ]
    for path in required_files:
        if not os.path.isfile(path):
            errors.append(f"Missing required file: {path}")
        elif os.path.getsize(path) < 300:
            errors.append(f"File too small (<300 bytes): {path}")

    skill_md_path = os.path.join(SKILL_ROOT, "SKILL.md")
    if os.path.isfile(skill_md_path):
        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.startswith("---"):
            errors.append("SKILL.md missing YAML frontmatter delimiter '---'")
        if "name: latam-fintech-payments-invoicing" not in content:
            errors.append("SKILL.md missing exact 'name: latam-fintech-payments-invoicing'")
        if "generate-qr-express" not in content:
            errors.append("SKILL.md missing official Bancard VentasQR generate-qr-express endpoint")
        for rel_link in re.findall(r"\]\(\./([^)]+)\)", content):
            target = os.path.join(SKILL_ROOT, rel_link.replace("/", os.sep))
            if not os.path.exists(target):
                errors.append(f"Broken relative link in SKILL.md: ./{rel_link}")

    return errors


def validate_resources() -> list[str]:
    errors: list[str] = []
    cfg_path = os.path.join(SKILL_ROOT, "resources", "config-template.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for key in (
            "bancard_endpoints",
            "bancard_vpos",
            "bancard_caja_pos_android",
            "infonet_cobranzas",
            "pagopar",
            "adamspay",
            "tigo_money_mfs",
            "bcp_sipap_py_qr",
            "sifen_dnit",
            "transbank",
        ):
            if key not in cfg:
                errors.append(f"config-template.json missing required section: {key}")
        cfg_dump = json.dumps(cfg)
        for hallucinated_path in (
            "/vpos/api/0.3/qr/generate",
            "/vpos/api/0.3/single_buy/charge_back",
            "/vpos/api/0.3/preauthorizations/abort",
        ):
            if hallucinated_path in cfg_dump:
                errors.append(f"config-template.json still contains hallucinated {hallucinated_path} path")
        if len(cfg.get("bancard_caja_pos_android", {}).get("card_issuer_ids", [])) != 17:
            errors.append("bancard_caja_pos_android.card_issuer_ids must list all 17 ICP v1.7 IssuerIds")
        if set(cfg.get("bancard_caja_pos_android", {}).get("wallets", {}).keys()) != {"ZIM", "WPJ", "VBV", "BPI", "BBF"}:
            errors.append("bancard_caja_pos_android.wallets must map ZIM, WPJ, VBV, BPI, BBF")
        if cfg.get("sifen_cdc_length") != 44 or cfg.get("sifen_dnit", {}).get("mod11_max_weight") != 11:
            errors.append("config-template.json SIFEN CDC length must be 44 and mod11_max_weight must be 11")
        pos_cmds = cfg.get("transbank", {}).get("pos_integrado", {}).get("commands", {})
        if pos_cmds.get("poll_status") != "0100" or pos_cmds.get("load_keys") != "0800":
            errors.append(f"Transbank POS commands invalid in config-template.json: {pos_cmds}")
    except Exception as exc:
        errors.append(f"Invalid config-template.json: {exc}")

    xml_path = os.path.join(SKILL_ROOT, "resources", "sifen-de-v150-template.xml")
    try:
        ET.parse(xml_path)
    except Exception as exc:
        errors.append(f"Malformed XML in sifen-de-v150-template.xml: {exc}")

    return errors


def validate_cryptographic_and_edge_cases() -> list[str]:
    errors: list[str] = []
    mod = load_reference_module()

    # 1. Bancard vPOS v1.23.1 formatting & complete official MD5 vectors (zero non-existent charge_back/abort)
    if hasattr(mod, "generate_bancard_charge_back_token"):
        errors.append("reference_implementation.py still exposes non-existent generate_bancard_charge_back_token")
    if mod.format_bancard_amount(150000) != "150000.00":
        errors.append("format_bancard_amount(150000) did not produce '150000.00'")

    for bad_val in (0, -500, "abc", float("nan"), float("inf"), True, False):
        try:
            mod.format_bancard_amount(bad_val)
            errors.append(f"format_bancard_amount failed to reject invalid input: {bad_val!r}")
        except ValueError:
            pass

    try:
        mod.generate_bancard_single_buy_token("priv", 101, "150000", "PYG")
        errors.append("generate_bancard_single_buy_token failed to reject amount without .00")
    except ValueError:
        pass

    expected_vectors = [
        (mod.generate_bancard_rollback_token("my_priv_key", 998877), b"my_priv_key998877rollback0.00"),
        (mod.generate_bancard_get_confirmation_token("my_priv_key", 998877), b"my_priv_key998877get_confirmation"),
        (mod.generate_bancard_cards_new_token("my_priv_key", 12, 4455), b"my_priv_key124455request_new_card"),
        (mod.generate_bancard_list_cards_token("my_priv_key", 4455), b"my_priv_key4455request_user_cards"),
        (
            mod.generate_bancard_charge_token("my_priv_key", 998877, "150000.00", "PYG", "alias_tok_15m"),
            b"my_priv_key998877charge150000.00PYGalias_tok_15m",
        ),
        (
            mod.generate_bancard_delete_card_token("my_priv_key", 4455, "alias_tok_15m"),
            b"my_priv_keydelete_card4455alias_tok_15m",
        ),
        (
            mod.generate_bancard_preauth_confirm_token("my_priv_key", 998877),
            b"my_priv_key998877pre-authorization-confirm",
        ),
        (mod.generate_bancard_billing_client_info_token("my_priv_key"), b"my_priv_keybilling_client_info"),
        (mod.generate_bancard_billing_cancel_token("my_priv_key", 998877), b"my_priv_key998877billing_cancel"),
    ]
    for actual, raw_bytes in expected_vectors:
        if actual != hashlib.md5(raw_bytes).hexdigest():
            errors.append(f"Bancard MD5 vector mismatch for {raw_bytes!r}: got {actual}")

    # 1b. Bancard VentasQR Basic Auth & Caja POS Android 2.0 v1.7 (ICP v1.7) edge cases
    expected_vqr = "Basic " + base64.b64encode(b"apps/pub_k:priv_k").decode("ascii")
    if mod.build_bancard_ventas_qr_basic_auth("pub_k", "priv_k") != expected_vqr:
        errors.append("Bancard VentasQR Basic Auth header mismatch")

    ux_ok = mod.validate_bancard_pos_venta_ux_request(1765432109876, monto=150000, cuotas=0, plan=0)
    if ux_ok["cuotas"] != 0 or ux_ok["facturaNro"] != 1765432109876 or ux_ok["monto"] != 150000:
        errors.append(f"Caja POS Android venta-ux failed valid int(15) facturaNro request: {ux_ok}")
    try:
        mod.validate_bancard_pos_venta_ux_request(1_000_000_000_000_000, monto=150000, cuotas=0, plan=0)
        errors.append("Caja POS Android venta-ux failed to reject >15-digit facturaNro")
    except ValueError:
        pass
    try:
        mod.validate_bancard_pos_venta_ux_request(1024, monto=150000, cuotas=1, plan=0)
        errors.append("Caja POS Android venta-ux failed to reject forbidden cuotas=1")
    except ValueError:
        pass
    try:
        mod.validate_bancard_pos_anulacion_request("12345")
        errors.append("Caja POS Android anulacion failed to reject non-12-digit nroBoleta")
    except ValueError:
        pass
    w_req = mod.validate_bancard_pos_billetera_request(1765432109876, 150000, "ZIM", "0981123456")
    if w_req["expected_issuer_id"] != "ZM" or w_req.get("billetera") != "ZIM" or "codigoBilletera" in w_req:
        errors.append(f"Caja POS Android venta-billetera must emit 'billetera' key and map ZIM -> ZM: {w_req}")
    ca_req = mod.validate_bancard_pos_consulta_anulacion_request("", 15)
    if ca_req != {"nroBoleta": "", "cantRegistro": 15}:
        errors.append(f"Caja POS Android consulta/anulacion payload mismatch: {ca_req}")

    # 1c. AdamsPay v1 MD5 webhook & BCP SIPAP EMVCo PY-QR CRC-16/CCITT-FALSE (0x1021)
    adams_raw = '{"notify":{"type":"debt","id":"ORD-99"}}'
    adams_expected = hashlib.md5(f"adams{adams_raw}sec_1".encode("utf-8")).hexdigest()
    if not mod.verify_adamspay_webhook_signature(adams_raw, "sec_1", adams_expected):
        errors.append("AdamsPay webhook verification failed valid signature")
    if mod.verify_adamspay_webhook_signature(adams_raw + " ", "sec_1", adams_expected):
        errors.append("AdamsPay webhook verification failed to detect rawBody mutation")

    # Standard ISO/IEC 13239 CRC-16/CCITT-FALSE check value for "123456789" is 0x29B1
    if mod.compute_emvco_crc16_ccitt_false("123456789") != "29B1":
        errors.append(
            f"EMVCo CRC-16/CCITT-FALSE failed standard check vector '123456789' -> expected '29B1', got {mod.compute_emvco_crc16_ccitt_false('123456789')}"
        )
    py_qr = mod.build_paraguay_emvco_py_qr("py.com.bancard", "BOLETOS01", 150000, "ORD-99")
    if "52044131530360054061500005802PY" not in py_qr:
        errors.append(f"EMVCo PY-QR missing MCC 4131, ISO 600 PYG, or amount TLV: {py_qr}")
    try:
        mod.build_paraguay_emvco_py_qr("py.com.bancard", "BOLETOS01", 10_000_001, "ORD-CAP")
        errors.append("build_paraguay_emvco_py_qr failed to enforce SPI Gs. 10.000.000 instant limit")
    except ValueError:
        pass

    # 2. Bancard 2PC State Machine
    orch = mod.Bancard2PCOrchestrator("pub_test", "priv_test")
    orch.register_locked_order(5001, 125000, "PYG")
    valid_tok = hashlib.md5(b"priv_test5001confirm125000.00PYG").hexdigest()

    forged_res = orch.handle_webhook_or_poll(
        {"shop_process_id": 5001, "amount": "125000.00", "currency": "PYG", "response": "S", "response_code": "00", "token": "0" * 32},
        gds_issue_callback=lambda o: "TKT-5001",
    )
    if forged_res["http_status"] != 401:
        errors.append("Bancard2PCOrchestrator did not reject forged token with 401")

    tampered_amt_tok = hashlib.md5(b"priv_test5001confirm100.00PYG").hexdigest()
    tampered_amt_res = orch.handle_webhook_or_poll(
        {"shop_process_id": 5001, "amount": "100.00", "currency": "PYG", "response": "S", "response_code": "00", "token": tampered_amt_tok},
        gds_issue_callback=lambda o: "TKT-5001",
    )
    if tampered_amt_res["http_status"] != 400 or tampered_amt_res.get("reason") != "AMOUNT_OR_CURRENCY_MISMATCH":
        errors.append("Bancard2PCOrchestrator did not reject tampered webhook amount with 400")

    ok_res = orch.handle_webhook_or_poll(
        {"shop_process_id": 5001, "amount": "125000.00", "currency": "PYG", "response": "S", "response_code": "00", "token": valid_tok},
        gds_issue_callback=lambda o: "TKT-5001",
    )
    if ok_res["order_status"] != "TICKET_ISSUED":
        errors.append("Bancard2PCOrchestrator failed happy-path ticket emission")

    replay_res = orch.handle_webhook_or_poll(
        {"shop_process_id": 5001, "amount": "125000.00", "currency": "PYG", "response": "S", "response_code": "00", "token": valid_tok},
        gds_issue_callback=lambda o: (_ for _ in ()).throw(RuntimeError("Should not be called on replay")),
    )
    if not replay_res.get("idempotent"):
        errors.append("Bancard2PCOrchestrator failed idempotent webhook replay guard")

    orch.register_locked_order(5002, 125000, "PYG")
    valid_tok_2 = hashlib.md5(b"priv_test5002confirm125000.00PYG").hexdigest()
    rb_res = orch.handle_webhook_or_poll(
        {"shop_process_id": 5002, "amount": "125000.00", "currency": "PYG", "response": "S", "response_code": "00", "token": valid_tok_2},
        gds_issue_callback=lambda o: (_ for _ in ()).throw(TimeoutError("GDS timeout")),
    )
    if rb_res["order_status"] != "PAYMENT_REVERSED" or "rollback_payload" not in rb_res:
        errors.append("Bancard2PCOrchestrator failed to trigger 2PC rollback on GDS timeout")

    orch.register_locked_order(5003, 125000, "PYG")
    orch.mark_order_expired(5003)
    valid_tok_3 = hashlib.md5(b"priv_test5003confirm125000.00PYG").hexdigest()
    late_res = orch.handle_webhook_or_poll(
        {"shop_process_id": 5003, "amount": "125000.00", "currency": "PYG", "response": "S", "response_code": "00", "token": valid_tok_3},
        gds_issue_callback=lambda o: (_ for _ in ()).throw(RuntimeError("GDS must not be called on EXPIRED order")),
    )
    if late_res["order_status"] != "PAYMENT_REVERSED_LATE_WEBHOOK":
        errors.append(f"Late webhook on EXPIRED order did not transition to PAYMENT_REVERSED_LATE_WEBHOOK: {late_res}")

    for idx_offset, err_key in enumerate(("TransactionAlreadyConfirmed", "PaymentAlreadyConfirmedError")):
        pid = 5004 + idx_offset
        orch.register_locked_order(pid, 125000, "PYG")
        valid_tok_err = hashlib.md5(f"priv_test{pid}confirm125000.00PYG".encode("utf-8")).hexdigest()
        manual_rb_res = orch.handle_webhook_or_poll(
            {"shop_process_id": pid, "amount": "125000.00", "currency": "PYG", "response": "S", "response_code": "00", "token": valid_tok_err},
            gds_issue_callback=lambda o: (_ for _ in ()).throw(TimeoutError("GDS timeout")),
            rollback_gateway_callback=lambda payload, k=err_key: {
                "status": "error",
                "messages": [{"key": k, "level": "error"}],
            },
        )
        if manual_rb_res["order_status"] != "ROLLBACK_MANUAL_REQUIRED":
            errors.append(f"Failed to transition to ROLLBACK_MANUAL_REQUIRED on {err_key}")

    # 3. Pagopar SHA-1 vectors (2.0 init integer/float/Decimal PYG without .0, 1.1 FORMA-PAGO, 3.0 PAGO-RECURRENTE, webhook)
    expected_pp_init = hashlib.sha1(b"pp_privORD-77150000").hexdigest()
    for pp_amt in (150000, 150000.0, Decimal("150000.00"), "150000.0"):
        if mod.generate_pagopar_init_token("pp_priv", "ORD-77", pp_amt) != expected_pp_init:
            errors.append(f"Pagopar init token SHA-1 mismatch for whole PYG amount {pp_amt!r}")
    if mod.generate_pagopar_action_token("pp_priv", "PAGO-RECURRENTE") != hashlib.sha1(b"pp_privPAGO-RECURRENTE").hexdigest():
        errors.append("Pagopar 3.0 PAGO-RECURRENTE token SHA-1 mismatch")
    if mod.generate_pagopar_action_token("pp_priv", "FORMA-PAGO") != hashlib.sha1(b"pp_privFORMA-PAGO").hexdigest():
        errors.append("Pagopar 1.1 FORMA-PAGO token SHA-1 mismatch")
    if not mod.verify_pagopar_webhook_token("pp_priv", "hash_abc", hashlib.sha1(b"pp_privhash_abc").hexdigest()):
        errors.append("Pagopar webhook verification failed")

    # 4. SIFEN 44-digit CDC (Mod-11 weights 2..11), Ley 6380/2019 transport IVA, Attack Vector 1 (<gDatRec>), XMLDSig & KuDE PDF
    if mod.resolve_paraguay_transport_iva_rate(85, is_international=False) != 0:
        errors.append("Ley 6380/2019 transport <= 100 km must be Exento (0%)")
    if mod.resolve_paraguay_transport_iva_rate(320, is_international=False) != 10:
        errors.append("Ley 6380/2019 domestic transport > 100 km must be 10% (never 5%)")
    if mod.resolve_paraguay_transport_iva_rate(1350, is_international=True) != 0:
        errors.append("Ley 6380/2019 international transport must be Exento (0%)")

    dv = mod.calculate_sifen_mod11("80171570")
    if dv != 9:
        errors.append(f"BOLETOS.LA E.A.S. RUC 80171570 expected Mod-11 DV 9, got {dv}")
    cdc = mod.generate_sifen_cdc_44("01", "80171570", dv, "001", "004", "0015420", "2", "20261019", "1", "482910374")
    if len(cdc) != 44 or not mod.verify_sifen_cdc_44(cdc):
        errors.append(f"Invalid 44-digit SIFEN CDC generated: {cdc}")

    kude_ref_path = os.path.join(SKILL_ROOT, "references", "sifen-ekuatia-v150-xml-and-kude.md")
    with open(kude_ref_path, "r", encoding="utf-8") as f:
        kude_ref_text = f.read()
    if " ".join(cdc[i : i + 4] for i in range(0, 44, 4)) not in kude_ref_text:
        errors.append("Documented 44-digit CDC in references/sifen-ekuatia-v150-xml-and-kude.md does not match valid Mod-11 CDC")

    tampered_cdc = cdc[:-1] + str((int(cdc[-1]) + 1) % 10)
    if mod.verify_sifen_cdc_44(tampered_cdc):
        errors.append("verify_sifen_cdc_44 failed to reject tampered check digit")

    iva10 = mod.liquidate_pyg_iva(110000, 10)
    if iva10["iva"] != 10000 or iva10["base_gravada"] != 100000:
        errors.append(f"Incorrect PYG 10% IVA liquidation: {iva10}")

    iva5 = mod.liquidate_pyg_iva(105000, 5)
    if iva5["iva"] != 5000 or iva5["base_gravada"] != 100000:
        errors.append(f"Incorrect PYG 5% IVA liquidation: {iva5}")

    # 4a. Attack Vector 1: Non-taxpayer iNatRec=2 (Cédula 4.567.890) mixed invoice (<=100km Exento + >100km 10% + 5%)
    mixed_bundle = mod.generate_signed_sifen_de_xml(
        cdc_44=cdc,
        fecha_emision_iso="2026-10-19T14:30:00",
        ruc_emisor="80171570",
        dv_emisor=dv,
        nombre_emisor="BOLETOS.LA E.A.S.",
        ruc_receptor="4.567.890",
        dv_receptor=0,
        nombre_receptor="JUAN PEREZ",
        nat_receptor=2,  # Non-taxpayer -> dNumIDRec in XML <gDatRec> AND QR, zero <dRucRec>/<dDVRec>/<iTiContRec>
        items=[
            {"codigo": "TR-320", "descripcion": "Pasaje Interurbano >100km Asuncion-CDE 10%", "unit_price": 120000, "quantity": 1, "rate": 10, "discount": 10000},
            {"codigo": "ARR-05", "descripcion": "Locacion / Canasta Basica Gravada 5%", "unit_price": 105000, "quantity": 1, "rate": 5, "discount": 0},
            {"codigo": "TR-065", "descripcion": "Pasaje Corta Distancia <=100km Exento", "unit_price": 50000, "quantity": 1, "rate": 0, "discount": 0},
        ],
    )
    if "&dNumIDRec=4567890&" not in mixed_bundle["qr_url"]:
        errors.append("build_sifen_qr_url failed to emit sanitized dNumIDRec=4567890 for nat_receptor=2")
    for required_rec_tag in ("<iNatRec>2</iNatRec>", "<iTipIDRec>1</iTipIDRec>", "<dNumIDRec>4567890</dNumIDRec>"):
        if required_rec_tag not in mixed_bundle["xml"]:
            errors.append(f"iNatRec=2 SIFEN DE XML missing required DE_v150.xsd tag: {required_rec_tag}")
    for forbidden_rec_tag in ("<iTiContRec>", "<dRucRec>", "<dDVRec>"):
        if forbidden_rec_tag in mixed_bundle["xml"]:
            errors.append(f"iNatRec=2 SIFEN DE XML violated DE_v150.xsd mutual exclusivity by emitting {forbidden_rec_tag}")
    if "<iAfecIVA>3</iAfecIVA>" not in mixed_bundle["xml"] or "<dDesAfecIVA>Exento</dDesAfecIVA>" not in mixed_bundle["xml"]:
        errors.append("Mixed SIFEN DE XML failed to emit iAfecIVA=3 and dDesAfecIVA=Exento for rate=0 item")
    if (
        mixed_bundle["tax_summary"]["sub_10"] != 110000
        or mixed_bundle["tax_summary"]["iva_10"] != 10000
        or mixed_bundle["tax_summary"]["sub_5"] != 105000
        or mixed_bundle["tax_summary"]["iva_5"] != 5000
        or mixed_bundle["tax_summary"]["sub_exenta"] != 50000
        or mixed_bundle["tax_summary"]["tot_iva"] != 15000
        or mixed_bundle["tax_summary"]["tot_gral_ope"] != 265000
        or mixed_bundle["tax_summary"]["tot_desc"] != 10000
    ):
        errors.append(f"Mixed multi-item tax summary calculation mismatch: {mixed_bundle['tax_summary']}")

    sig_check = mod.verify_sifen_xmldsig(mixed_bundle["xml"])
    if not sig_check["valid"]:
        errors.append(f"Real X.509 RSA-SHA256 XMLDSig verification failed: {sig_check}")

    mutated_xml = mixed_bundle["xml"].replace("JUAN PEREZ", "JUAN PEREZ TAMPERED")
    if mod.verify_sifen_xmldsig(mutated_xml)["valid"]:
        errors.append("verify_sifen_xmldsig failed to detect post-signature XML tampering inside <DE>")

    pdf_bytes = mixed_bundle["kude_pdf_bytes"]
    if (
        not pdf_bytes.startswith(b"%PDF-1.4")
        or not pdf_bytes.endswith(b"%%EOF\n")
        or b"0180 1715 7090" not in pdf_bytes
        or b"19019949" not in pdf_bytes
    ):
        errors.append("Generated KuDE PDF is missing valid %PDF-1.4 framing, formatted CDC 0180 1715 7090, or Timbrado 19019949")

    # 4b. Test Taxpayer iNatRec=1 multi-currency USD SIFEN DE with exchange rate dTiCam
    usd_bundle = mod.generate_signed_sifen_de_xml(
        cdc_44=cdc,
        fecha_emision_iso="2026-10-19T14:30:00",
        ruc_emisor="80171570",
        dv_emisor=dv,
        nombre_emisor="BOLETOS.LA E.A.S.",
        ruc_receptor="80012345",
        dv_receptor=mod.calculate_sifen_mod11("80012345"),
        nombre_receptor="CORPORACION LOGISTICA S.A.",
        nat_receptor=1,
        currency="USD",
        exchange_rate=Decimal("7850.00"),
        items=[{"codigo": "USD-01", "descripcion": "Servicio Logistico Gravado", "unit_price": "110.00", "quantity": 1, "rate": 10}],
    )
    if "<cMoneOpe>USD</cMoneOpe>" not in usd_bundle["xml"] or "<dTiCam>7850.00</dTiCam>" not in usd_bundle["xml"]:
        errors.append("USD SIFEN DE XML missing cMoneOpe=USD or dTiCam=7850.00")
    if "<iTiContRec>2</iTiContRec>" not in usd_bundle["xml"] or "<dRucRec>80012345</dRucRec>" not in usd_bundle["xml"] or "<dNumIDRec>" in usd_bundle["xml"]:
        errors.append("iNatRec=1 Taxpayer SIFEN DE XML failed DE_v150.xsd <gDatRec> structure")
    if not mod.verify_sifen_xmldsig(usd_bundle["xml"])["valid"]:
        errors.append("USD SIFEN DE XML failed X.509 RSA-SHA256 XMLDSig verification")

    # 5. Transbank Webpay Plus 4 return scenarios & POS LRC
    s_norm = mod.evaluate_transbank_return_callback({"token_ws": "tok_123"})
    s_abort = mod.evaluate_transbank_return_callback({"TBK_TOKEN": "tbk_99", "TBK_ORDEN_COMPRA": "O1"})
    s_timeout = mod.evaluate_transbank_return_callback({"TBK_ORDEN_COMPRA": "O1", "TBK_ID_SESION": "S1"})
    s_double = mod.evaluate_transbank_return_callback({"token_ws": "tok_123", "TBK_TOKEN": "tbk_99"})
    if (
        s_norm["scenario"] != "NORMAL_RETURN"
        or s_abort["scenario"] != "ABORTED_BY_USER"
        or s_timeout["scenario"] != "FORM_TIMEOUT_EXPIRED"
        or s_double["scenario"] != "ANOMALOUS_DOUBLE_TOKEN"
    ):
        errors.append("Transbank return callback scenario classification failed")

    frame = mod.build_transbank_pos_frame("0200|15990|9001||0")
    if not mod.verify_transbank_pos_frame(frame)["valid"]:
        errors.append("Transbank POS frame failed LRC verification")
    corrupted_frame = frame[:-1] + bytes([frame[-1] ^ 0xFF])
    if mod.verify_transbank_pos_frame(corrupted_frame)["valid"]:
        errors.append("Transbank POS frame failed to detect corrupted LRC byte")

    # 6. Execute TypeScript orchestrator via Node.js and verify cross-language vector equality
    ts_path = os.path.join(SKILL_ROOT, "examples", "typescript_gateway_orchestrator.ts")
    try:
        proc = subprocess.run(
            ["node", ts_path],
            cwd=SKILL_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            errors.append(f"Node TypeScript execution failed (exit {proc.returncode}): {proc.stderr.strip()}")
        else:
            ts_out = json.loads(proc.stdout.strip())
            py_demo = mod.run_demo()
            for shared_key in (
                "bancard_ventas_qr_auth",
                "adamspay_webhook_hash",
                "emvco_py_qr",
                "sifen_cdc_44",
                "sifen_iva_10_pyg",
            ):
                if ts_out.get(shared_key) != py_demo.get(shared_key):
                    errors.append(
                        f"Cross-language {shared_key} mismatch: TS={ts_out.get(shared_key)} vs PY={py_demo.get(shared_key)}"
                    )
            if ts_out.get("transbank_pos_frame_hex") != mod.build_transbank_pos_frame("0200|25900|100501||0").hex():
                errors.append("Cross-language Transbank POS frame hex mismatch between TS and Python")
    except Exception as exc:
        errors.append(f"Failed to run TypeScript cross-language verification: {exc}")

    return errors


def validate() -> int:
    all_errors = (
        validate_structure_and_frontmatter()
        + validate_resources()
        + validate_cryptographic_and_edge_cases()
    )
    if all_errors:
        for err in all_errors:
            print(f"[FAIL] {err}")
        return 1
    print(
        f"[PASS] latam-fintech-payments-invoicing domain structure, PY gateways, EMVCo CRC-16, X.509 XMLDSig, KuDE PDF & TS/PY suite verified at {SKILL_ROOT}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(validate())
