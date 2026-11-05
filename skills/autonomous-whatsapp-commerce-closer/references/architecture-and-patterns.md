# Architecture & Transactional Patterns — `autonomous-whatsapp-commerce-closer`

Detailed protocol specification for the 11-tool `boletos-la-ventas-mcp` conversational commerce state machine across WhatsApp, Bancard vPOS, Delta Bus GDS, and `boletos-la-analitica` (`Mi Boleto`).

---

## 1. The 11-Tool `boletos-la-ventas-mcp` Contract Catalog

| # | Tool Name | Required Parameters | Optional Parameters | Transactional Role |
| :---: | :--- | :--- | :--- | :--- |
| 1 | `get_allowed_operators` | *(none)* | *(none)* | Returns **ONLY** actively integrated Delta Bus GDS operators (`LSN`: **La Santaniana**, `LSP`: **La Sampedrana**, `LSA`: **La Santaniana Internacional**) and enforces the strict legal/commercial exclusion of all unintegrated carriers (`NSA`, `Sol del Paraguay`, `RYSA`, etc.). |
| 2 | `resolve_station` | `query` (`str`) | *(none)* | Resolves city names, terminals, or Paraguayan colloquial aliases (`"asuncion"` -> `184`, `"cde"` -> `218`, `"oviedo"` -> `173`, `"encarnacion"` -> `200`) to GDS station IDs. |
| 3 | `search_bus_trips` | `origin` (`str`), `destination` (`str`), `travel_date` (`YYYY-MM-DD`) | *(none)* | Queries available departures between two station IDs while enforcing a strict positive allowlist filter (`LSN`, `LSP`, `LSA` only). |
| 4 | `get_seat_map` | `service_id` (`str`), `origin` (`str`), `destination` (`str`) | *(none)* | Retrieves real-time per-deck seat availability (`"available"` or `"occupied"`; Delta states `"B"`, `"R"`, `"T"` map strictly to `"occupied"`) and seat category (`CA`, `SC`, `SU`). |
| 5 | `hold_seats` | `service_id` (`str`), `origin` (`str`), `destination` (`str`), `seats` (`str`) | `connection_id` (`str \| null`) | Temporarily locks one or more seats in the GDS for **10 minutes (600s)** and returns the mandatory `connection_id`. |
| 6 | `release_seats` | `connection_id` (`str`) | *(none)* | Immediately releases a temporary seat hold in the GDS when the passenger modifies their selection, cancels, or hits a rollback. |
| 7 | `create_payment_link_and_notify_whatsapp` | *(contextual session payload)* | *(none)* | Generates a secure Bancard vPOS checkout link (card / QR; backend serializes wire `amount` with `.00` decimals per Bancard vPOS v1.23) and dispatches it directly to the passenger's WhatsApp. |
| 8 | `check_payment_status` | `process_id` (`str`) | `shop_process_id` (`int \| null`), `amount` (`int \| null`) | Verifies whether the Bancard payment link was paid (`is_paid: True`, `response === "S" && response_code === "00"`) and retrieves `authorization_number`. |
| 9 | `emit_tickets` | `service_id`, `origin`, `destination`, `company` (`LSN`\|`LSP`\|`LSA`), `connection_id`, `authorization_number`, `seats_and_passengers` (`list[dict]`), `total_amount` (`int`) | *(none)* | Commits official bus tickets in Delta Bus GDS (`PasajerosAlta` -> `BoletosProximoNumeroLibre` -> `Venta3`) using 3-letter operator code, sanitized `docNumber`, and pure seat tariff. |
| 10 | `send_ticket_to_whatsapp` | `phone`, `passenger_name`, `origin`, `destination`, `company`, `departure_date`, `departure_time`, `seat_numbers`, `booking_code` | `ticket_numbers` (`list[str] \| null`), `total_amount` (`int \| null`) | Sends the confirmed boarding pass with QR download and `/paraguay/mi-boleto?ticket=<N>` verification link to the passenger's WhatsApp. |
| 11 | `rollback_payment` | `shop_process_id` (`int`) | *(none)* | Emergency compensating transaction: calls Bancard `/vpos/api/0.3/single_buy/rollback` (pre-batch) to reverse the charge if GDS ticket emission fails. |

---

## 2. Strict Integrated-Operators-Only Policy & Delta `Venta3` Invariants

1. **Zero Unintegrated Carriers (`01_anti_nsa_policy`)**:
   - In Paraguay, **only** Grupo La Santaniana divisions integrated via Delta Bus GDS (`BO2` Web / `BO1` Tótem) are permitted:
     - `LSN` — **La Santaniana** (Nacional / Matriz)
     - `LSP` — **La Sampedrana** (La Santaniana Premier)
     - `LSA` — **La Santaniana Internacional** (Argentina)
   - If a passenger requests any unintegrated carrier (`NSA`, `Nuestra Señora de la Asunción`, `NASA`, `Sol del Paraguay`, `Expreso Paraguay`, `RYSA`, `Golondrina`, `Canindeyú`, `Stel Turismo`, `Guaireña`, `Crucero del Norte`, `Yacyretá`, `Cometa del Amambay`, `La Ovetense`, `Ciudad de Concepción`, `Crucero del Este`, `Beato Roque González`), the agent must courteously clarify that Boletos.la operates exclusively with officially integrated fleets (**La Santaniana** and **La Sampedrana** / **Grupo La Santaniana**) and offer their available departures.
2. **Delta `Venta3` Wire Invariants (`03_two_phase_commit_bancard_gds`)**:
   - **3-Letter `Empresa` Code**: Normalize `"La Santaniana"` -> `"LSN"`, `"La Sampedrana"` -> `"LSP"`, `"La Santaniana Internacional"` -> `"LSA"`. Passing display names to Delta SOAP causes rejection after payment capture.
   - **Pure Seat Tariff (`seat.amount`)**: Pass only the pure Delta seat tariff (e.g., `120000`), never including a 5% platform fee (`CodigoError: 233`).
   - **Sanitized `NroDocumento`**: Strip all dots, hyphens, and spaces (`replace(/[.\-\s]/g, "")`) identically across `PasajerosAlta` and `StringButacas` (`CodigoError: 335`).

---

## 3. Seat Hold Lifecycle & 10-Minute TTL Discipline

1. **Single Active Hold per Conversation**:
   - Before calling `hold_seats` for a new seat selection or a different `service_id`, check whether the conversation state already holds an active `connection_id`.
   - If `session.connection_id` is non-null and unexpired, invoke `release_seats(connection_id=session.connection_id)` first so GDS inventory is never leaked.
2. **Strict 600-Second Countdown**:
   - Record `hold_expires_at = hold_created_at + 600`.
   - If the passenger attempts to pay or emit tickets after `now >= hold_expires_at`, treat the lock as expired: release the stale `connection_id` (best-effort) and re-verify seat availability via `get_seat_map` before re-locking.

---

## 4. Passenger Document Validation (Paraguayan `CI` & Chilean `RUT`)

The `emit_tickets` tool requires a structured `seats_and_passengers` array where each item specifies:

```json
[
  {
    "seat": "12",
    "docType": "C",
    "docNumber": "4567890",
    "amount": 100000,
    "qualityCode": "CA"
  }
]
```

### 4.1. Validation & Sanitization Rules
- **Paraguayan Cédula de Identidad (`docType = "C"` or `"CI"`)**:
  - Strip dots, spaces, and hyphens (`4.567.890` -> `4567890`).
  - Must be 5 to 8 numeric digits (optionally followed by a single uppercase check letter for alphanumeric series, e.g., `4567890` or `4567890A`), with non-zero leading digit.
- **Chilean RUT (`docType = "RUT"`)**:
  - Validate Modulo-11 check digit (`0-9` or `K`) using cycling weights `[2, 3, 4, 5, 6, 7]`.
  - When transmitting to Delta Bus GDS `NroDocumento`, strip the hyphen as well (`12.345.678-5` -> `123456785`) so `PasajerosAlta` and the 17-char `StringButacas` `N` field match byte-for-byte.

---

## 5. Two-Phase Commit (2PC) & Automatic `rollback_payment` Protocol

Whenever `is_paid == True` and `emit_tickets` raises an exception or returns an invalid/empty `booking_code`:
1. **Step 1 (Financial Reversal)**: Immediately invoke `rollback_payment(shop_process_id=session.shop_process_id)`.
2. **Step 2 (Inventory Cleanup)**: Immediately invoke `release_seats(connection_id=session.connection_id)` so the seat hold is cleared.
3. **Step 3 (Customer Notification)**: Transition state to `ROLLED_BACK` and send a clear WhatsApp notice confirming that the Bancard charge (`shop_process_id`) was automatically reversed in full (`Gs. XXX.XXX`) and offering alternative seats/departures.
