# -*- coding: utf-8 -*-
"""
Reference Implementation for `autonomous-whatsapp-commerce-closer`.

Provides:
  1. `WhatsAppCommerceStateMachine`: Deterministic 11-tool `boletos-la-ventas-mcp` booking FSM
     with strict NSA prohibition, station resolution, 10-minute seat lock TTL, automatic
     `release_seats` on change/cancellation, and 2PC `rollback_payment` on GDS emission failure.
  2. `render_whatsapp_seat_grid()`: Double-deck ASCII/Emoji bus seat map formatter for WhatsApp.
  3. `validate_passenger_document()`: Paraguayan CI and Chilean RUT (Mod-11) validator.
  4. `format_guaranies()`: Canonical `Gs. XXX.XXX` currency formatter.
  5. `run_self_tests()`: 10 deterministic unit & edge-case tests verifying the full lifecycle.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import re
from dataclasses import dataclass, field
from typing import Any

INTEGRATED_OPERATORS: dict[str, str] = {
    "LSN": "La Santaniana",
    "LSP": "La Sampedrana",
    "LSA": "La Santaniana Internacional",
}

ALLOWED_OPERATORS: tuple[str, ...] = tuple(INTEGRATED_OPERATORS.values())

FORBIDDEN_OPERATOR_TOKENS: tuple[str, ...] = (
    "nsa",
    "nuestra señora de la asuncion",
    "nuestra senora de la asuncion",
    "nuestra señora de la asunción",
    "nasa",
    "nasa golondrina",
    "sol del paraguay",
    "expreso paraguay",
    "rysa",
    "golondrina",
    "canindeyu",
    "canindeyú",
    "stel turismo",
    "guaireña",
    "guairena",
    "crucero del norte",
    "yacyreta",
    "yacyretá",
    "cometa del amambay",
    "la ovetense",
    "ciudad de concepcion",
    "ciudad de concepción",
    "crucero del este",
    "beato roque gonzalez",
    "beato roque gonzález",
)

STATION_DIRECTORY: dict[str, tuple[str, str]] = {
    "asuncion": ("184", "Asunción"),
    "asu": ("184", "Asunción"),
    "terminal de asuncion": ("184", "Asunción"),
    "cde": ("218", "Ciudad del Este"),
    "ciudad del este": ("218", "Ciudad del Este"),
    "oviedo": ("173", "Coronel Oviedo"),
    "coronel oviedo": ("173", "Coronel Oviedo"),
    "encarnacion": ("200", "Encarnación"),
    "encarnación": ("200", "Encarnación"),
    "enc": ("200", "Encarnación"),
}

HOLD_TTL_SECONDS = 600


def format_guaranies(amount: int) -> str:
    """Formats an integer amount in Paraguayan Guaraníes as 'Gs. 120.000'."""
    if not isinstance(amount, int) or amount < 0:
        raise ValueError(f"Amount in Guaraníes must be a non-negative integer, got: {amount!r}")
    return f"Gs. {amount:,}".replace(",", ".")


def is_forbidden_operator(name: str) -> bool:
    """Returns True if the carrier name matches any forbidden or unintegrated operator."""
    norm = re.sub(r"\s+", " ", (name or "").strip().lower())
    for token in FORBIDDEN_OPERATOR_TOKENS:
        if re.search(rf"\b{re.escape(token)}\b", norm):
            return True
    return False


def normalize_operator_code(name_or_code: str) -> str | None:
    """
    Normalizes an operator name or code strictly to its 3-letter Delta Bus GDS code ('LSN', 'LSP', 'LSA').
    Returns None for any unintegrated, unknown, or forbidden carrier (01_anti_nsa_policy).
    """
    raw = re.sub(r"\s+", " ", (name_or_code or "").strip())
    if not raw or is_forbidden_operator(raw):
        return None
    upper = raw.upper()
    if upper in INTEGRATED_OPERATORS:
        return upper
    lower = raw.lower()
    if lower in ("la santaniana internacional", "santaniana internacional"):
        return "LSA"
    if lower in ("la sampedrana", "sampedrana", "la santaniana premier"):
        return "LSP"
    if lower in ("la santaniana", "santaniana"):
        return "LSN"
    return None


def is_allowed_operator(name_or_code: str) -> bool:
    """Strict positive allowlist check: True ONLY for LSN, LSP, and LSA."""
    return normalize_operator_code(name_or_code) is not None


def map_delta_seat_status(raw_status: str) -> str:
    """
    Maps Delta Bus GDS seat states strictly per 03_two_phase_commit_bancard_gds:
    'B' (Bloqueado), 'R' (Reservado), 'T' (Tomado), 'blocked', and 'occupied' -> 'occupied'.
    Only 'L' (Libre) or 'available' -> 'available'.
    """
    norm = (raw_status or "").strip().upper()
    if norm in ("L", "AVAILABLE"):
        return "available"
    return "occupied"


def validate_paraguayan_ci(raw_ci: str) -> tuple[bool, str]:
    """
    Validates a Paraguayan Cédula de Identidad (CI).
    Accepts 5 to 8 digits (non-zero start), optionally with dots/spaces and an optional single trailing letter.
    Returns (is_valid, normalized_ci).
    """
    cleaned = re.sub(r"[.\s-]", "", (raw_ci or "").strip().upper())
    if re.fullmatch(r"[1-9]\d{4,7}[A-Z]?", cleaned):
        return True, cleaned
    return False, cleaned


def validate_chilean_rut(raw_rut: str) -> tuple[bool, str]:
    """
    Validates a Chilean RUT using Modulo-11 check digit verification.
    Returns (is_valid, normalized_rut_with_hyphen).
    """
    cleaned = re.sub(r"[.\s]", "", (raw_rut or "").strip().upper())
    if "-" in cleaned:
        parts = cleaned.split("-")
        if len(parts) != 2:
            return False, cleaned
        body, dv = parts
    else:
        if len(cleaned) < 8:
            return False, cleaned
        body, dv = cleaned[:-1], cleaned[-1]

    if not re.fullmatch(r"[1-9]\d{6,7}", body) or not re.fullmatch(r"[0-9K]", dv):
        return False, cleaned

    factors = [2, 3, 4, 5, 6, 7]
    total = 0
    for idx, ch in enumerate(reversed(body)):
        total += int(ch) * factors[idx % len(factors)]
    remainder = 11 - (total % 11)
    expected_dv = "0" if remainder == 11 else ("K" if remainder == 10 else str(remainder))
    normalized = f"{body}-{dv}"
    return (dv == expected_dv), normalized


def validate_passenger_document(doc_type: str, doc_number: str) -> tuple[bool, str, str]:
    """
    Validates passenger document by type ('C'/'CI' for Paraguayan CI, 'RUT' for Chilean RUT).
    Returns (is_valid, canonical_doc_type, normalized_doc_number).
    """
    dtype = (doc_type or "C").strip().upper()
    if dtype in ("C", "CI", "PY"):
        ok, norm = validate_paraguayan_ci(doc_number)
        return ok, "C", norm
    if dtype in ("RUT", "CL"):
        ok, norm = validate_chilean_rut(doc_number)
        return ok, "RUT", norm
    return False, dtype, (doc_number or "").strip()


def render_whatsapp_seat_grid(seat_map_payload: dict[str, Any]) -> str:
    """
    Renders a double-deck ASCII/Emoji bus seat layout formatted for WhatsApp.
    Uses 🟩 for available seats, 🟥 for occupied seats, and || for the center aisle.
    """
    service_id = seat_map_payload.get("service_id", "N/A")
    company = seat_map_payload.get("company", "Flota Aliada")
    lines: list[str] = [
        f"🚌 *Mapa de Asientos — {company} (Servicio #{service_id})*",
        "🟩 Disponible | 🟥 Ocupado | `||` Pasillo",
        "",
    ]

    floors = seat_map_payload.get("floors", [])
    for floor in floors:
        floor_num = floor.get("floor_number", 1)
        quality = floor.get("quality_code", "SC")
        quality_label = floor.get("quality_label", "Semi Cama")
        price_gs = int(floor.get("price_gs", 100000))
        lines.append(f"*PISO {floor_num} — {quality_label} ({quality}) — {format_guaranies(price_gs)}*")

        seats = floor.get("seats", [])
        for idx in range(0, len(seats), 4):
            row_chunk = seats[idx : idx + 4]
            left_pair = " ".join(
                f"[{int(s['number']):02d}{'🟩' if s.get('status') == 'available' else '🟥'}]"
                for s in row_chunk[:2]
            )
            right_pair = " ".join(
                f"[{int(s['number']):02d}{'🟩' if s.get('status') == 'available' else '🟥'}]"
                for s in row_chunk[2:4]
            )
            if right_pair:
                lines.append(f"`{left_pair}  ||  {right_pair}`")
            else:
                lines.append(f"`{left_pair}`")
        lines.append("")

    return "\n".join(lines).strip()


class MockBoletosVentasMCP:
    """
    Deterministic in-memory implementation of the 11 tools in `boletos-la-ventas-mcp`
    for testing the complete WhatsApp commerce state machine and 2PC rollback flows.
    """

    def __init__(self) -> None:
        self.tool_call_log: list[tuple[str, dict[str, Any]]] = []
        self.active_holds: dict[str, dict[str, Any]] = {}
        self.payments: dict[str, dict[str, Any]] = {}
        self.seat_inventory: dict[str, dict[str, str]] = {
            "SRV-901": {
                "1": "available",
                "2": "occupied",
                "3": "available",
                "4": "available",
                "11": "available",
                "12": "available",
                "13": "occupied",
                "14": "available",
            }
        }
        self.simulate_gds_failure: bool = False
        self._hold_seq: int = 100
        self._payment_seq: int = 5000

    def get_allowed_operators(self) -> dict[str, Any]:
        self.tool_call_log.append(("get_allowed_operators", {}))
        return {
            "allowed_operators": list(ALLOWED_OPERATORS),
            "integrated_operator_codes": dict(INTEGRATED_OPERATORS),
            "strict_integrated_allowlist_only": True,
        }

    def resolve_station(self, query: str) -> dict[str, Any]:
        self.tool_call_log.append(("resolve_station", {"query": query}))
        norm = (query or "").strip().lower()
        if norm not in STATION_DIRECTORY:
            raise ValueError(f"Unrecognized station alias: {query!r}")
        station_id, canonical_name = STATION_DIRECTORY[norm]
        return {"station_id": station_id, "name": canonical_name, "query": query}

    def search_bus_trips(self, origin: str, destination: str, travel_date: str) -> list[dict[str, Any]]:
        self.tool_call_log.append(
            ("search_bus_trips", {"origin": origin, "destination": destination, "travel_date": travel_date})
        )
        # Positive integrated services + negative-assertion upstream records that MUST be blocked
        raw_catalog = [
            {
                "service_id": "SRV-901",
                "company": "La Santaniana",
                "operator_code": "LSN",
                "origin": origin,
                "destination": destination,
                "travel_date": travel_date,
                "departure_time": "22:30",
                "price_gs": 120000,
                "quality_code": "CA",
            },
            {
                "service_id": "SRV-902",
                "company": "La Sampedrana",
                "operator_code": "LSP",
                "origin": origin,
                "destination": destination,
                "travel_date": travel_date,
                "departure_time": "23:15",
                "price_gs": 110000,
                "quality_code": "SC",
            },
            {
                "service_id": "SRV-999-NSA",
                "company": "NSA - Nuestra Señora de la Asunción",
                "origin": origin,
                "destination": destination,
                "travel_date": travel_date,
                "departure_time": "23:00",
                "price_gs": 115000,
                "quality_code": "CA",
            },
            {
                "service_id": "SRV-998-UNINT",
                "company": "Sol del Paraguay",
                "origin": origin,
                "destination": destination,
                "travel_date": travel_date,
                "departure_time": "21:00",
                "price_gs": 115000,
                "quality_code": "CA",
            },
            {
                "service_id": "SRV-997-UNINT",
                "company": "RYSA",
                "origin": origin,
                "destination": destination,
                "travel_date": travel_date,
                "departure_time": "20:00",
                "price_gs": 105000,
                "quality_code": "SC",
            },
        ]
        # Strict Integrated-Only Allowlist Filter (01_anti_nsa_policy)
        return [t for t in raw_catalog if is_allowed_operator(t["company"])]

    def get_seat_map(self, service_id: str, origin: str, destination: str) -> dict[str, Any]:
        self.tool_call_log.append(
            ("get_seat_map", {"service_id": service_id, "origin": origin, "destination": destination})
        )
        inv = self.seat_inventory.get(service_id, {})
        return {
            "service_id": service_id,
            "company": "La Santaniana",
            "operator_code": "LSN",
            "origin": origin,
            "destination": destination,
            "floors": [
                {
                    "floor_number": 1,
                    "quality_code": "CA",
                    "quality_label": "Salón Cama",
                    "price_gs": 120000,
                    "seats": [
                        {"number": s, "status": map_delta_seat_status(inv.get(s, "occupied")), "qualityCode": "CA"}
                        for s in ("1", "2", "3", "4")
                    ],
                },
                {
                    "floor_number": 2,
                    "quality_code": "SC",
                    "quality_label": "Semi Cama",
                    "price_gs": 95000,
                    "seats": [
                        {"number": s, "status": map_delta_seat_status(inv.get(s, "occupied")), "qualityCode": "SC"}
                        for s in ("11", "12", "13", "14")
                    ],
                },
            ],
        }

    def hold_seats(
        self,
        service_id: str,
        origin: str,
        destination: str,
        seats: str,
        connection_id: str | None = None,
    ) -> dict[str, Any]:
        self.tool_call_log.append(
            (
                "hold_seats",
                {
                    "service_id": service_id,
                    "origin": origin,
                    "destination": destination,
                    "seats": seats,
                    "connection_id": connection_id,
                },
            )
        )
        seat_list = [s.strip() for s in seats.split(",") if s.strip()]
        inv = self.seat_inventory.setdefault(service_id, {})
        for s in seat_list:
            if map_delta_seat_status(inv.get(s, "occupied")) != "available":
                raise RuntimeError(f"Seat {s} on service {service_id} is not available")
        for s in seat_list:
            inv[s] = "occupied"

        self._hold_seq += 1
        conn_id = connection_id or f"CONN-{self._hold_seq}"
        self.active_holds[conn_id] = {
            "service_id": service_id,
            "seats": seat_list,
            "origin": origin,
            "destination": destination,
            "active": True,
        }
        return {"connection_id": conn_id, "seats": seat_list, "ttl_seconds": HOLD_TTL_SECONDS}

    def release_seats(self, connection_id: str) -> dict[str, Any]:
        self.tool_call_log.append(("release_seats", {"connection_id": connection_id}))
        hold = self.active_holds.get(connection_id)
        if hold and hold.get("active"):
            inv = self.seat_inventory.setdefault(hold["service_id"], {})
            for s in hold["seats"]:
                inv[s] = "available"
            hold["active"] = False
        return {"released": True, "connection_id": connection_id}

    def create_payment_link_and_notify_whatsapp(self, amount: int, phone: str, description: str) -> dict[str, Any]:
        self.tool_call_log.append(
            (
                "create_payment_link_and_notify_whatsapp",
                {"amount": amount, "phone": phone, "description": description},
            )
        )
        self._payment_seq += 1
        shop_process_id = self._payment_seq
        process_id = f"BANCARD-PROC-{shop_process_id}"
        self.payments[process_id] = {
            "process_id": process_id,
            "shop_process_id": shop_process_id,
            "amount": amount,
            "bancard_wire_amount": f"{amount:.2f}",
            "is_paid": False,
            "authorization_number": None,
            "rolled_back": False,
        }
        return {
            "process_id": process_id,
            "shop_process_id": shop_process_id,
            "payment_url": f"https://vpos.infonet.com.py/checkout/{process_id}",
            "whatsapp_notified": True,
            "formatted_amount": format_guaranies(amount),
            "bancard_wire_amount": f"{amount:.2f}",
        }

    def mark_payment_approved(self, process_id: str, authorization_number: str = "AUTH-884210") -> None:
        self.payments[process_id]["is_paid"] = True
        self.payments[process_id]["authorization_number"] = authorization_number

    def check_payment_status(
        self,
        process_id: str,
        shop_process_id: int | None = None,
        amount: int | None = None,
    ) -> dict[str, Any]:
        self.tool_call_log.append(
            (
                "check_payment_status",
                {"process_id": process_id, "shop_process_id": shop_process_id, "amount": amount},
            )
        )
        payment = self.payments.get(process_id)
        if not payment:
            raise KeyError(f"Unknown payment process_id: {process_id}")
        return {
            "process_id": process_id,
            "shop_process_id": payment["shop_process_id"],
            "amount": payment["amount"],
            "is_paid": payment["is_paid"],
            "authorization_number": payment["authorization_number"],
        }

    def emit_tickets(
        self,
        service_id: str,
        origin: str,
        destination: str,
        company: str,
        connection_id: str | None,
        authorization_number: str,
        seats_and_passengers: list[dict[str, Any]],
        total_amount: int,
    ) -> dict[str, Any]:
        company_code = normalize_operator_code(company)
        self.tool_call_log.append(
            (
                "emit_tickets",
                {
                    "service_id": service_id,
                    "origin": origin,
                    "destination": destination,
                    "company": company_code or company,
                    "connection_id": connection_id,
                    "authorization_number": authorization_number,
                    "seats_and_passengers": seats_and_passengers,
                    "total_amount": total_amount,
                },
            )
        )
        if company_code is None:
            raise PermissionError(
                f"PROHIBICIÓN ESTRICTA (01_anti_nsa_policy): Operador no integrado o prohibido: {company!r}. "
                "Solo se permiten LSN, LSP y LSA."
            )
        for p in seats_and_passengers:
            if re.search(r"[.\-\s]", str(p.get("docNumber", ""))):
                raise ValueError("Delta Venta3 invariant violated (CodigoError 335): docNumber contains dots/hyphens/spaces")
        if self.simulate_gds_failure:
            raise RuntimeError("Delta Bus GDS timeout while committing ticket emission")
        if not connection_id or not self.active_holds.get(connection_id, {}).get("active"):
            raise RuntimeError("Invalid or expired connection_id for ticket emission")

        booking_code = f"BL-{authorization_number[-4:]}"
        ticket_numbers = [f"TKT-{service_id}-{p['seat']}" for p in seats_and_passengers]
        return {
            "booking_code": booking_code,
            "operator_code": company_code,
            "ticket_numbers": ticket_numbers,
            "total_amount": total_amount,
        }

    def send_ticket_to_whatsapp(
        self,
        phone: str,
        passenger_name: str,
        origin: str,
        destination: str,
        company: str,
        departure_date: str,
        departure_time: str,
        seat_numbers: str,
        booking_code: str,
        ticket_numbers: list[str] | None = None,
        total_amount: int | None = None,
    ) -> dict[str, Any]:
        self.tool_call_log.append(
            (
                "send_ticket_to_whatsapp",
                {
                    "phone": phone,
                    "passenger_name": passenger_name,
                    "origin": origin,
                    "destination": destination,
                    "company": company,
                    "departure_date": departure_date,
                    "departure_time": departure_time,
                    "seat_numbers": seat_numbers,
                    "booking_code": booking_code,
                    "ticket_numbers": ticket_numbers,
                    "total_amount": total_amount,
                },
            )
        )
        return {
            "delivered": True,
            "phone": phone,
            "booking_code": booking_code,
            "qr_boarding_url": f"https://boletos.la/qr/{booking_code}",
        }

    def rollback_payment(self, shop_process_id: int) -> dict[str, Any]:
        self.tool_call_log.append(("rollback_payment", {"shop_process_id": shop_process_id}))
        for payment in self.payments.values():
            if payment["shop_process_id"] == shop_process_id:
                payment["rolled_back"] = True
                payment["is_paid"] = False
                return {"rolled_back": True, "shop_process_id": shop_process_id}
        raise KeyError(f"Unknown shop_process_id for rollback: {shop_process_id}")


@dataclass
class WhatsAppCommerceStateMachine:
    """
    Deterministic 2PC conversational sales state machine for `boletos-la-ventas-mcp`.
    """

    mcp: MockBoletosVentasMCP
    phone: str
    state: str = "INIT"
    allowed_operators: list[str] = field(default_factory=list)
    origin_id: str = ""
    origin_name: str = ""
    destination_id: str = ""
    destination_name: str = ""
    travel_date: str = ""
    service_id: str = ""
    company: str = ""
    operator_code: str = ""
    departure_time: str = ""
    connection_id: str | None = None
    hold_created_at: float = 0.0
    held_seats: list[str] = field(default_factory=list)
    seats_and_passengers: list[dict[str, Any]] = field(default_factory=list)
    primary_passenger_name: str = ""
    total_amount_gs: int = 0
    process_id: str = ""
    shop_process_id: int = 0
    booking_code: str = ""
    ticket_numbers: list[str] = field(default_factory=list)

    def initialize_and_resolve_route(
        self,
        origin_query: str,
        destination_query: str,
        travel_date: str,
        requested_operator: str | None = None,
    ) -> dict[str, Any]:
        ops = self.mcp.get_allowed_operators()
        self.allowed_operators = ops["allowed_operators"]

        if requested_operator and not is_allowed_operator(requested_operator):
            self.state = "REJECTED_FORBIDDEN_OPERATOR"
            return {
                "status": "BLOCKED_OPERATOR",
                "message": (
                    "Boletos.la opera exclusivamente con empresas integradas oficialmente en su plataforma "
                    "(Grupo La Santaniana: "
                    + ", ".join(self.allowed_operators)
                    + "). ¿Deseás consultar las salidas disponibles de nuestras flotas integradas?"
                ),
            }

        orig = self.mcp.resolve_station(origin_query)
        dest = self.mcp.resolve_station(destination_query)
        self.origin_id, self.origin_name = orig["station_id"], orig["name"]
        self.destination_id, self.destination_name = dest["station_id"], dest["name"]
        self.travel_date = travel_date
        self.state = "STATION_RESOLVED"
        return {
            "status": "OK",
            "origin_id": self.origin_id,
            "destination_id": self.destination_id,
        }

    def search_and_render_seat_map(self, chosen_service_id: str | None = None) -> dict[str, Any]:
        trips = self.mcp.search_bus_trips(self.origin_id, self.destination_id, self.travel_date)
        if not trips:
            self.state = "NO_TRIPS"
            return {"status": "NO_TRIPS", "trips": []}

        self.state = "TRIPS_LISTED"
        selected = next(
            (t for t in trips if t["service_id"] == (chosen_service_id or trips[0]["service_id"])),
            trips[0],
        )
        self.service_id = selected["service_id"]
        self.company = selected["company"]
        self.operator_code = normalize_operator_code(self.company) or "LSN"
        self.departure_time = selected["departure_time"]

        seat_map = self.mcp.get_seat_map(self.service_id, self.origin_id, self.destination_id)
        rendered_grid = render_whatsapp_seat_grid(seat_map)
        self.state = "SEAT_MAP_RENDERED"
        return {
            "status": "OK",
            "trips": trips,
            "selected_trip": selected,
            "seat_map_whatsapp": rendered_grid,
        }

    def lock_seats_for_passengers(
        self,
        passengers: list[dict[str, Any]],
        now_ts: float = 1000.0,
    ) -> dict[str, Any]:
        """
        Validates passenger documents (Paraguayan CI / Chilean RUT), sanitizes docNumber by
        stripping dots/hyphens/spaces per Delta Venta3 (CodigoError 335 prevention), releases any
        prior active hold, and locks the requested seats in the GDS for 10 minutes (600s TTL).
        """
        validated_payload: list[dict[str, Any]] = []
        total_gs = 0
        for p in passengers:
            ok, norm_type, norm_doc = validate_passenger_document(p.get("docType", "C"), p.get("docNumber", ""))
            if not ok:
                return {
                    "status": "INVALID_DOCUMENT",
                    "seat": p.get("seat"),
                    "docNumber": p.get("docNumber"),
                }
            sanitized_doc = re.sub(r"[.\-\s]", "", norm_doc)
            amount = int(p["amount"])
            total_gs += amount
            validated_payload.append(
                {
                    "seat": str(p["seat"]),
                    "docType": norm_type,
                    "docNumber": sanitized_doc,
                    "amount": amount,
                    "qualityCode": p.get("qualityCode", "CA"),
                }
            )

        # If a previous hold exists on this session, release it first before creating a new lock
        if self.connection_id:
            self.mcp.release_seats(self.connection_id)
            self.connection_id = None

        seat_csv = ",".join(item["seat"] for item in validated_payload)
        hold_res = self.mcp.hold_seats(
            service_id=self.service_id,
            origin=self.origin_id,
            destination=self.destination_id,
            seats=seat_csv,
        )
        self.connection_id = hold_res["connection_id"]
        self.hold_created_at = now_ts
        self.held_seats = hold_res["seats"]
        self.seats_and_passengers = validated_payload
        self.primary_passenger_name = passengers[0].get("name", "Pasajero Boletos.la")
        self.total_amount_gs = total_gs
        self.state = "SEATS_HELD"
        return {
            "status": "SEATS_HELD",
            "connection_id": self.connection_id,
            "total_formatted": format_guaranies(self.total_amount_gs),
            "expires_at": self.hold_created_at + HOLD_TTL_SECONDS,
        }

    def cancel_or_release_hold(self) -> dict[str, Any]:
        if self.connection_id:
            cid = self.connection_id
            self.mcp.release_seats(cid)
            self.connection_id = None
            self.held_seats = []
            self.state = "CANCELLED"
            return {"status": "RELEASED", "connection_id": cid}
        self.state = "CANCELLED"
        return {"status": "NO_ACTIVE_HOLD"}

    def dispatch_payment_link(self, now_ts: float = 1060.0) -> dict[str, Any]:
        if not self.connection_id or (now_ts - self.hold_created_at) >= HOLD_TTL_SECONDS:
            if self.connection_id:
                self.mcp.release_seats(self.connection_id)
                self.connection_id = None
            self.state = "HOLD_EXPIRED"
            return {"status": "HOLD_EXPIRED"}

        pay_res = self.mcp.create_payment_link_and_notify_whatsapp(
            amount=self.total_amount_gs,
            phone=self.phone,
            description=f"{self.company} {self.origin_name}->{self.destination_name}",
        )
        self.process_id = pay_res["process_id"]
        self.shop_process_id = int(pay_res["shop_process_id"])
        self.state = "PAYMENT_PENDING"
        return pay_res

    def verify_payment_and_finalize(self, now_ts: float = 1120.0) -> dict[str, Any]:
        """
        Polls `check_payment_status`. Once `is_paid == True`, executes 2PC `emit_tickets` (passing
        3-letter Delta operator code LSN/LSP/LSA) -> `send_ticket_to_whatsapp`. Automatically triggers
        `rollback_payment` + `release_seats` if GDS emission fails or seat hold TTL expired.
        """
        status = self.mcp.check_payment_status(
            process_id=self.process_id,
            shop_process_id=self.shop_process_id,
            amount=self.total_amount_gs,
        )
        if not status.get("is_paid") or not status.get("authorization_number"):
            if (now_ts - self.hold_created_at) >= HOLD_TTL_SECONDS and self.connection_id:
                self.mcp.release_seats(self.connection_id)
                self.connection_id = None
                self.state = "HOLD_EXPIRED"
                return {"status": "HOLD_EXPIRED"}
            return {"status": "PAYMENT_PENDING", "process_id": self.process_id}

        self.state = "PAYMENT_CONFIRMED"
        auth_num = str(status["authorization_number"])

        try:
            if (now_ts - self.hold_created_at) >= HOLD_TTL_SECONDS:
                raise RuntimeError("Seat hold 10-minute TTL expired prior to GDS emission")

            operator_3letter = normalize_operator_code(self.operator_code or self.company)
            if not operator_3letter:
                raise PermissionError(f"Unintegrated operator blocked prior to GDS Venta3: {self.company!r}")

            emission = self.mcp.emit_tickets(
                service_id=self.service_id,
                origin=self.origin_id,
                destination=self.destination_id,
                company=operator_3letter,
                connection_id=self.connection_id,
                authorization_number=auth_num,
                seats_and_passengers=self.seats_and_passengers,
                total_amount=self.total_amount_gs,
            )
            if not emission.get("booking_code"):
                raise RuntimeError("GDS returned empty booking_code")
        except Exception as exc:
            rb = self.mcp.rollback_payment(shop_process_id=self.shop_process_id)
            if self.connection_id:
                self.mcp.release_seats(connection_id=self.connection_id)
                self.connection_id = None
            self.state = "ROLLED_BACK"
            return {
                "status": "ROLLED_BACK",
                "error": str(exc),
                "rolled_back": rb.get("rolled_back", False),
                "shop_process_id": self.shop_process_id,
                "refunded_formatted": format_guaranies(self.total_amount_gs),
            }

        self.booking_code = emission["booking_code"]
        self.ticket_numbers = emission.get("ticket_numbers", [])
        self.state = "TICKET_EMITTED"

        wa_delivery = self.mcp.send_ticket_to_whatsapp(
            phone=self.phone,
            passenger_name=self.primary_passenger_name,
            origin=self.origin_name,
            destination=self.destination_name,
            company=self.company,
            departure_date=self.travel_date,
            departure_time=self.departure_time,
            seat_numbers=",".join(p["seat"] for p in self.seats_and_passengers),
            booking_code=self.booking_code,
            ticket_numbers=self.ticket_numbers,
            total_amount=self.total_amount_gs,
        )
        self.state = "COMPLETED"
        return {
            "status": "COMPLETED",
            "booking_code": self.booking_code,
            "operator_code": emission["operator_code"],
            "ticket_numbers": self.ticket_numbers,
            "qr_boarding_url": wa_delivery["qr_boarding_url"],
            "total_formatted": format_guaranies(self.total_amount_gs),
        }


def run_self_tests() -> dict[str, Any]:
    """Runs 11 deterministic edge-case unit tests covering all 11 MCP tools, 01_anti_nsa_policy, and 2PC invariants."""
    passed = 0

    # Test 1: Strict Integrated-Only Allowlist (LSN, LSP, LSA) & Unintegrated Carrier Blocklist (01_anti_nsa_policy)
    mcp = MockBoletosVentasMCP()
    fsm = WhatsAppCommerceStateMachine(mcp=mcp, phone="595981123456")
    for unintegrated in (
        "NSA",
        "Nuestra Señora de la Asunción",
        "NASA",
        "Sol del Paraguay",
        "RYSA",
        "Expreso Paraguay",
        "Golondrina",
        "Canindeyú",
        "Crucero del Norte",
        "Stel Turismo",
        "Guaireña",
    ):
        assert is_allowed_operator(unintegrated) is False, f"Unintegrated carrier leaked: {unintegrated}"
        assert normalize_operator_code(unintegrated) is None
        blocked = fsm.initialize_and_resolve_route("asuncion", "cde", "2026-11-15", requested_operator=unintegrated)
        assert blocked["status"] == "BLOCKED_OPERATOR"
        assert fsm.state == "REJECTED_FORBIDDEN_OPERATOR"

    assert normalize_operator_code("La Santaniana") == "LSN"
    assert normalize_operator_code("La Sampedrana") == "LSP"
    assert normalize_operator_code("La Santaniana Internacional") == "LSA"
    assert ALLOWED_OPERATORS == ("La Santaniana", "La Sampedrana", "La Santaniana Internacional")
    passed += 1

    # Test 2: Colloquial station resolution ('asu' -> 184, 'cde' -> 218, 'oviedo' -> 173, 'encarnacion' -> 200)
    ok_res = fsm.initialize_and_resolve_route("asu", "cde", "2026-11-15")
    assert ok_res["origin_id"] == "184" and ok_res["destination_id"] == "218"
    assert mcp.resolve_station("oviedo")["station_id"] == "173"
    assert mcp.resolve_station("encarnacion")["station_id"] == "200"
    passed += 1

    # Test 3: Trip search enforces integrated allowlist (LSN/LSP/LSA) & maps Delta B/R/T seat states
    assert map_delta_seat_status("B") == "occupied"
    assert map_delta_seat_status("R") == "occupied"
    assert map_delta_seat_status("T") == "occupied"
    assert map_delta_seat_status("L") == "available"
    map_res = fsm.search_and_render_seat_map()
    assert len(map_res["trips"]) == 2
    assert all(is_allowed_operator(t["company"]) for t in map_res["trips"])
    grid_text = map_res["seat_map_whatsapp"]
    assert "PISO 1" in grid_text and "PISO 2" in grid_text
    assert "[01🟩]" in grid_text and "[02🟥]" in grid_text and "||" in grid_text
    assert "Gs. 120.000" in grid_text
    passed += 1

    # Test 4: Paraguayan CI and Chilean RUT (Modulo-11) passenger validation
    assert validate_passenger_document("C", "4.567.890")[0] is True
    assert validate_passenger_document("C", "123")[0] is False
    assert validate_passenger_document("RUT", "12.345.678-5")[0] is True
    assert validate_passenger_document("RUT", "12.345.678-9")[0] is False
    passed += 1

    # Test 5: Invalid passenger document prevents seat locking in GDS
    bad_lock = fsm.lock_seats_for_passengers(
        [{"name": "Juan Perez", "seat": "1", "docType": "RUT", "docNumber": "12345678-0", "amount": 120000}]
    )
    assert bad_lock["status"] == "INVALID_DOCUMENT"
    assert fsm.connection_id is None
    passed += 1

    # Test 6: Atomic seat lock, sanitized docNumber, & automatic `release_seats` on seat change
    lock1 = fsm.lock_seats_for_passengers(
        [{"name": "Juan Perez", "seat": "1", "docType": "RUT", "docNumber": "12.345.678-5", "amount": 120000}],
        now_ts=1000.0,
    )
    first_conn = lock1["connection_id"]
    assert fsm.seats_and_passengers[0]["docNumber"] == "123456785"
    assert mcp.seat_inventory["SRV-901"]["1"] == "occupied"

    lock2 = fsm.lock_seats_for_passengers(
        [{"name": "Juan Perez", "seat": "3", "docType": "C", "docNumber": "4.567.890", "amount": 120000}],
        now_ts=1030.0,
    )
    second_conn = lock2["connection_id"]
    assert first_conn != second_conn
    assert fsm.seats_and_passengers[0]["docNumber"] == "4567890"
    assert mcp.seat_inventory["SRV-901"]["1"] == "available"
    assert mcp.seat_inventory["SRV-901"]["3"] == "occupied"
    passed += 1

    # Test 7: Happy-path payment link (.2f wire format), polling, 3-letter LSN emission & WhatsApp QR delivery
    pay_link = fsm.dispatch_payment_link(now_ts=1050.0)
    assert pay_link["whatsapp_notified"] is True
    assert pay_link["bancard_wire_amount"] == "120000.00"
    pending_check = fsm.verify_payment_and_finalize(now_ts=1080.0)
    assert pending_check["status"] == "PAYMENT_PENDING"

    mcp.mark_payment_approved(fsm.process_id, authorization_number="AUTH-990123")
    final_res = fsm.verify_payment_and_finalize(now_ts=1100.0)
    assert final_res["status"] == "COMPLETED"
    assert final_res["operator_code"] == "LSN"
    assert final_res["booking_code"] == "BL-0123"
    assert fsm.state == "COMPLETED"
    passed += 1

    # Test 8: Direct emit_tickets blocks unintegrated carrier even if called bypassing search
    try:
        mcp.emit_tickets(
            service_id="SRV-901",
            origin="184",
            destination="218",
            company="Sol del Paraguay",
            connection_id=second_conn,
            authorization_number="AUTH-000111",
            seats_and_passengers=[{"seat": "3", "docType": "C", "docNumber": "4567890", "amount": 120000}],
            total_amount=120000,
        )
        raise AssertionError("emit_tickets failed to block unintegrated carrier Sol del Paraguay")
    except PermissionError:
        passed += 1

    # Test 9: Automatic `rollback_payment` & `release_seats` when GDS `emit_tickets` fails after payment capture
    mcp_fail = MockBoletosVentasMCP()
    mcp_fail.simulate_gds_failure = True
    fsm_fail = WhatsAppCommerceStateMachine(mcp=mcp_fail, phone="595981999888")
    fsm_fail.initialize_and_resolve_route("asuncion", "encarnacion", "2026-11-20")
    fsm_fail.search_and_render_seat_map()
    fsm_fail.lock_seats_for_passengers(
        [{"name": "Maria Gomez", "seat": "11", "docType": "C", "docNumber": "5678901", "amount": 95000}],
        now_ts=2000.0,
    )
    fsm_fail.dispatch_payment_link(now_ts=2050.0)
    mcp_fail.mark_payment_approved(fsm_fail.process_id, authorization_number="AUTH-777000")

    rb_res = fsm_fail.verify_payment_and_finalize(now_ts=2100.0)
    assert rb_res["status"] == "ROLLED_BACK"
    assert rb_res["rolled_back"] is True
    assert fsm_fail.state == "ROLLED_BACK"
    assert mcp_fail.seat_inventory["SRV-901"]["11"] == "available"
    passed += 1

    # Test 10: Seat hold 10-minute TTL expiration triggers automatic rollback if paid after TTL expiry
    mcp_ttl = MockBoletosVentasMCP()
    fsm_ttl = WhatsAppCommerceStateMachine(mcp=mcp_ttl, phone="595981777666")
    fsm_ttl.initialize_and_resolve_route("cde", "asuncion", "2026-11-22")
    fsm_ttl.search_and_render_seat_map()
    fsm_ttl.lock_seats_for_passengers(
        [{"name": "Carlos Ruiz", "seat": "12", "docType": "RUT", "docNumber": "12.345.678-5", "amount": 95000}],
        now_ts=3000.0,
    )
    fsm_ttl.dispatch_payment_link(now_ts=3100.0)
    mcp_ttl.mark_payment_approved(fsm_ttl.process_id, authorization_number="AUTH-555111")
    ttl_res = fsm_ttl.verify_payment_and_finalize(now_ts=3000.0 + HOLD_TTL_SECONDS + 5.0)
    assert ttl_res["status"] == "ROLLED_BACK"
    assert mcp_ttl.seat_inventory["SRV-901"]["12"] == "available"
    passed += 1

    # Test 11: Verify all 11 tools in `boletos-la-ventas-mcp` were exercised across the test suite
    called_tools = {name for name, _ in mcp.tool_call_log} | {name for name, _ in mcp_fail.tool_call_log}
    expected_11_tools = {
        "get_allowed_operators",
        "resolve_station",
        "search_bus_trips",
        "get_seat_map",
        "hold_seats",
        "release_seats",
        "create_payment_link_and_notify_whatsapp",
        "check_payment_status",
        "emit_tickets",
        "send_ticket_to_whatsapp",
        "rollback_payment",
    }
    assert called_tools == expected_11_tools, f"Missing tools: {expected_11_tools - called_tools}"
    passed += 1

    return {
        "status": "ok",
        "tests_passed": passed,
        "tools_verified": sorted(called_tools),
    }


if __name__ == "__main__":
    result = run_self_tests()
    print(f"[PASS] reference_implementation.py: {result['tests_passed']} tests passed ({len(result['tools_verified'])}/11 MCP tools verified).")
