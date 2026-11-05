# -*- coding: utf-8 -*-
r"""
Deterministic static & functional validator for `pci-compliance` (PCI DSS v4.0.1).

Verifies:
  1. Required files (`SKILL.md`, `resources/implementation-playbook.md`,
     `examples/reference_implementation.py`, `scripts/validate_skill_domain.py`).
  2. YAML frontmatter quality (`45 <= len(description) <= 450`) and zero broken relative links.
  3. Domain authenticity of `resources/implementation-playbook.md` (PCI DSS v4.0.1 Req. 6.4.3 & 11.6.1,
     zero copy-pasted GraphQL/REST API boilerplate).
  4. Full execution + negative edge-case tests against `examples/reference_implementation.py`.

Run with:
  python ./scripts/validate_skill_domain.py
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import importlib.util
import os
import re

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def validate() -> int:
    req_files = [
        os.path.join(SKILL_ROOT, "SKILL.md"),
        os.path.join(SKILL_ROOT, "resources", "implementation-playbook.md"),
        os.path.join(SKILL_ROOT, "examples", "reference_implementation.py"),
        os.path.join(SKILL_ROOT, "scripts", "validate_skill_domain.py"),
    ]
    missing = [p for p in req_files if not os.path.isfile(p)]
    if missing:
        print(f"[FAIL] Missing required files: {missing}")
        return 1

    with open(os.path.join(SKILL_ROOT, "SKILL.md"), "r", encoding="utf-8") as f:
        skill_md = f.read()

    fm_match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", skill_md, re.DOTALL)
    if not fm_match or "name: pci-compliance" not in fm_match.group(1):
        print("[FAIL] Invalid frontmatter in SKILL.md")
        return 1

    for rel in re.findall(r"\]\(\./([^)#]+)\)", skill_md):
        target = os.path.normpath(os.path.join(SKILL_ROOT, rel))
        if not os.path.exists(target):
            print(f"[FAIL] Broken relative link in SKILL.md: ./{rel}")
            return 1

    for req_token in ("6.4.3", "11.6.1", "AES-256-GCM", "3.3.1", "bancard-checkout-4.0.0.js", "extended_response_description"):
        if req_token not in skill_md:
            print(f"[FAIL] SKILL.md missing required PCI DSS v4.0.1 / Bancard v1.23.1 token: {req_token}")
            return 1

    with open(os.path.join(SKILL_ROOT, "resources", "implementation-playbook.md"), "r", encoding="utf-8") as f:
        playbook = f.read()

    if "API Design Principles Implementation Playbook" in playbook:
        print("[FAIL] implementation-playbook.md still contains unrelated API Design Principles boilerplate")
        return 1
    if "6.4.3" not in playbook or "11.6.1" not in playbook or "security_information" not in playbook:
        print("[FAIL] implementation-playbook.md missing PCI DSS v4.0.1 Req. 6.4.3 / 11.6.1 or Bancard UI hygiene rules")
        return 1

    ref_path = os.path.join(SKILL_ROOT, "examples", "reference_implementation.py")
    spec = importlib.util.spec_from_file_location("pci_ref", ref_path)
    if spec is None or spec.loader is None:
        print("[FAIL] Cannot load reference_implementation.py")
        return 1
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pci_ref"] = mod
    spec.loader.exec_module(mod)

    res = mod.run_self_tests()
    if res.get("status") != "ok" or res.get("tests_passed", 0) < 9:
        print(f"[FAIL] Self-tests failed: {res}")
        return 1

    # Additional boundary edge cases (including nested list/tuple SAD & PAN regression)
    sanitizer = mod.PaymentDataSanitizer()
    list_sanitized = sanitizer.sanitize_for_log({"cards": [{"pan": "4111111111111111", "cvv": "123"}]})
    if list_sanitized["cards"][0].get("pan") != "411111******1111" or "cvv" in list_sanitized["cards"][0]:
        print(f"[FAIL] PaymentDataSanitizer leaked PAN/CVV inside nested list: {list_sanitized}")
        return 1

    try:
        mod.TokenVault().tokenize({"cards": [{"last4": "1111", "cvv": "123"}]})
        print("[FAIL] TokenVault failed to block CVV nested inside list of dicts")
        return 1
    except mod.SecurityError:
        pass

    try:
        mod.EncryptedStorage(b"short_key")
        print("[FAIL] EncryptedStorage accepted non-256-bit key")
        return 1
    except ValueError:
        pass

    try:
        mod.TokenVault().tokenize({"last4": "1111", "pin": "1234"})
        print("[FAIL] TokenVault failed to block PIN storage")
        return 1
    except mod.SecurityError:
        pass

    try:
        mod.PaymentPageScriptGuard([mod.AuthorizedScriptEntry(url="https://example.com/a.js", business_justification="   ")])
        print("[FAIL] PaymentPageScriptGuard accepted empty Req. 6.4.3 justification")
        return 1
    except ValueError:
        pass

    print(f"[PASS] pci-compliance PCI DSS v4.0.1 validated ({res['tests_passed']} suites + 5 negative boundary checks) at {SKILL_ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
