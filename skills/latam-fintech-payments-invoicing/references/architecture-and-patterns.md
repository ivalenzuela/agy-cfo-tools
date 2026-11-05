# Deep Architecture Reference: Paraguayan & Chilean Payment Gateways, POS & SIFEN DNIT

This reference specifies the verified cryptographic contracts, REST/LAN wire payloads, timeout recovery mechanisms, and 2-Phase Commit (2PC) patterns for Paraguayan and Chilean FinTech integrations.

---

## 1. Bancard vPOS v1.23.1 (Paraguay) — Complete 11-Operation Official Contract

### 1.1. Environments & Official Endpoints
- **Staging**: `https://vpos.infonet.com.py:8888`
- **Production**: `https://vpos.infonet.com.py`
- **JavaScript Checkout Iframe SDK**: `/checkout/javascript/dist/bancard-checkout-4.0.0.js` (`bancard-checkout-2.0.0.js` legacy backward-compatible; container min-width `320px`; subject to **PCI DSS v4.0.1 Req. 6.4.3 & 11.6.1** script inventory, CSP `frame-src`/`script-src`, and header/script tamper monitoring).

| # | Official Operation (`v1.23.1`) | Method & Path | MD5 Token Formula (`UTF-8` lowercase hex) | Key Constraints & Guardrails |
| :---: | :--- | :--- | :--- | :--- |
| 1 | **Compra Ocasional (`single_buy`)** | `POST /vpos/api/0.3/single_buy` | `md5(priv + shop_process_id + amount + currency)` | `amount` strictly `"150000.00"`; supports `zimple: "S"`, `preauthorization: "S"`, `billing` (`total_items: 1` when consolidated). |
| 2 | **Catastro de Tarjeta (`cards/new`)** | `POST /vpos/api/0.3/cards/new` | `md5(priv + card_id + user_id + "request_new_card")` | Max **5 cards** per `user_id`; zero-amount card validation. **Mastercard MAC 03 y 21 (p. 86)**: **7 declines/24h** or **35 declines/30d** block card at merchant for **30 days**. |
| 3 | **Listar Tarjetas (`users/{id}/cards`)** | `POST /vpos/api/0.3/users/{user_id}/cards` | `md5(priv + user_id + "request_user_cards")` | Method is `POST` (not `GET`); returns `alias_token` with **15-minute TTL** rotating on every call. |
| 4 | **Pago con Alias (`charge` + `Charge3DS`)** | `POST /vpos/api/0.3/charge` | `md5(priv + shop_process_id + "charge" + amount + currency + alias_token)` | Pass `"extra_response_attributes": ["confirmation.process_id"]`; when issuer requires 3DS 2.x, mount `Bancard.Charge3DS.createForm(div, confirmation.process_id)`. |
| 5 | **Eliminar Tarjeta (`delete_card`)** | `DELETE /vpos/api/0.3/users/{user_id}/cards` | `md5(priv + "delete_card" + user_id + alias_token)` | JSON body sent on HTTP `DELETE` using a fresh `<15m` `alias_token`. |
| 6 | **Webhook Confirmación (`confirm`)** | Incoming `POST` to merchant URL | `md5(priv + shop_process_id + "confirm" + amount + currency)` | Bancard timeout = **30s** (target `< 5s`); approve iff `response === "S" && response_code === "00"`. |
| 7 | **Consulta Confirmación (`confirmations`)** | `POST /vpos/api/0.3/single_buy/confirmations` | `md5(priv + shop_process_id + "get_confirmation")` | Poll across 10-minute (`600s`) inventory lock window before expiring seats. |
| 8 | **Rollback Pre-Cuponado (`rollback`)** | `POST /vpos/api/0.3/single_buy/rollback` | `md5(priv + shop_process_id + "rollback" + "0.00")` | Literal `"0.00"`, **NO** `currency` appended; cancels `single_buy`, `charge`, and `preauthorizations` pre-couponing. If already couponed, returns `"key": "TransactionAlreadyConfirmed"` (requires manual annulment in `comercios.bancard.com.py`). |
| 9 | **Confirmar Preautorización (`preauthorizations/confirm`)** | `POST /vpos/api/0.3/preauthorizations/confirm` | `md5(priv + shop_process_id + "pre-authorization-confirm")` | **NO** `amount`/`currency` in MD5 (optional `amount` & `billing` in body only). **Single attempt**, 30d expiry, `> USD 1` for **both** Credit & Debit. **Credit (TC)**: hold without movement, allows `<= 120%` (`+20%`), 1 boleta. **Debit (TD)**: immediate debit, `<= 100%`, 2 boletas. |
| 10 | **Factura Electrónica — Datos RUC (`billing/client_info`)** | `POST /vpos/api/0.3/billing/client_info` | `md5(priv + "billing_client_info")` | Electronic invoice op (pp. 67–69): body `operation.client_ruc` -> returns taxpayer `razon_social` and status. |
| 11 | **Factura Electrónica — Anulación (`billing/cancel`)** | `POST /vpos/api/0.3/billing/cancel` | `md5(priv + shop_process_id + "billing_cancel")` | Electronic invoice op (pp. 69–71): body `operation.shop_process_id`, valid **`< 24h`** post-approval. |

### 1.2. Critical Bancard vPOS v1.23.1 Certification Mandates
- **Credit vs Debit Preauthorization (pp. 4, 72–73)**: Both require minimum amount `> USD 1`, allow **1 single confirmation attempt**, and expire after **30 days** (or can be cancelled early via `POST /vpos/api/0.3/single_buy/rollback`). Credit Card (`TC`) freezes credit limit without fund movement, supports confirming up to **`120%`** (`+20%`) of the preauthorized amount, and generates **1 boleta**; Debit Card (`TD`) moves/credits funds immediately, supports confirming at most **`100%`**, and generates **2 separate boletas**.
- **WebView 3rd-Party Cookie Rules (pp. 74–75)**: First-party mobile apps embedding Bancard must enable third-party cookies (`CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)`) and set `baseUrl: 'https://vpos.infonet.com.py'`. Third-party social in-app WebViews (Instagram, Facebook `FBAN`/`FBAV`, TikTok) must trigger native browser escape (Chrome / Safari) prior to 3DS v2 checkout.
- **UI Field Requirements & Prohibitions (pp. 30, 37, 41)**: Response screens MUST display Date/Time, `shop_process_id`, `amount`, `response_description`, and a merchant Contact section, and are **strictly forbidden** on ALL response screens (approved or declined) from rendering `authorization_number`, `response_code`, `extended_response_description`, or `security_information`.

---

## 2. Bancard VentasQR (Commerce REST API) & vPOS Checkout QR

> **Important**: `POST /vpos/api/0.3/qr/generate` does **not** exist. Bancard provides two verified QR integration models:

### 2.1. Model A — Bancard VentasQR Commerce REST API (Standalone Dynamic QR)
- **Authentication**: HTTP Basic Auth header using `apps/{public_key}:{private_key}` encoded in Base64 + `iva-sale: true|false`:
  ```text
  Authorization: Basic base64("apps/" + public_key + ":" + private_key)
  ```
- **Generate Dynamic QR Express**:
  - `POST /commerces/{commerce_code}/branches/{branch_code}/selling/generate-qr-express`
  - Payload: `{"amount": 150000, "description": "Pasaje Asuncion - CDE"}` (integer `PYG`).
  - Returns `qr_express.hook_alias`, `qr_express.url`, `qr_express.qr_data` (EMVCo `PY-QR`), and `supported_clients`.
- **Revert QR Payment**:
  - `PUT /commerces/{commerce_code}/branches/{branch_code}/selling/payments/revert/{hook_alias}`

### 2.2. Model B — Bancard vPOS 2.0 Web Checkout QR
1. Initialize standard `POST /vpos/api/0.3/single_buy` to obtain `process_id`.
2. Request dynamic QR data from checkout host: `GET /checkout/generate_qr?process_id={process_id}` (`X-Requested-With: XMLHttpRequest`, `Accept: application/json`), returning `{ buy_alias, qr_url }` reconciled under the same `shop_process_id` webhook.

---

## 3. Bancard Caja POS Android 2.0 (`ICP v1.7`, Local LAN `POST http://<IP_POS>:3000/pos/*`)

Physical Bancard Android smart-POS terminals expose a local LAN HTTP JSON server on `http://<IP_POS>:3000` (`ICP-Integración CAJA POS - Android 2.0 v1.7`). **ALL** endpoints strictly require HTTP **`POST`** (any `GET` returns `"ERROR AL RECIBIR DATOS DE CAJA"`):

1. **Connectivity Test (`POST /pos/eco`)**: Body `{"eco": 12}` (`int(2)`, `0..99`) $\to$ HTTP 200 `{"eco": 12}`.
2. **2-Step Card Sale (`venta-ux`, `venta/debito`, `venta/credito` + `descuento`)**:
   - **Step 1 (`POST /pos/venta-ux`)**: `{"facturaNro": 1765432109876, "monto": 150000}` for Contado (or `cuotas: 0, plan: 0`), or `{"facturaNro": 1765432109876, "monto": 150000, "cuotas": 6, "plan": 1}` for installments.
     - **Forced Card-Type Step 1**: `POST /pos/venta/debito` (`{"facturaNro": 1765432109876}`) and `POST /pos/venta/credito` (`{"facturaNro": 1765432109876, "cuotas": 6, "plan": 1}`).
     - **Guardrails**: `facturaNro` is **`int(15)` (`0..999999999999999`)**; `monto` is **`int(9)` (`1..999999999`)**; `cuotas` **MUST** be `0`/omitted (Contado) or `> 1` with `plan: 1` (`cuotas: 1` returns an error).
     - Customer taps/inserts card on POS; POS responds with Step-1 JSON `{"bin": "4509790000", "nsu": "001245"}` (`bin` `string(10)`, `nsu` `string(6)`).
   - **Step 2 (`POST /pos/descuento`)**: Cashier/totem validates BIN promotions and posts final amount `{"bin": "4509790000", "nsu": "001245", "monto": 150000}` $\to$ completes EMV authorization and returns `codigoAutorizacion` (`string(6)`), `nroBoleta` (`string(12)`), `issuerId` (`string(2)`), `pan` (`string(4)`), `saldo`, `mensajeDisplay`, `nombreCliente`, `nombreTarjeta`, `nroComercio`.
3. **1-Step QR, Pix, Loyalty & Mobile Wallets**:
   - **QR Nacional (`POST /pos/venta-qr`)**: `{"facturaNro": 1046, "monto": 150000, "montoVuelto": 0, "promotions": [...]}` (`promotions` optional JSON array of `{"bin", "ent_code", "client": "PM"|"ENT", "brand", "product", "affinity"}`, max `9000` chars).
   - **QR Pix Brasil (`POST /pos/venta-qr-pix`)**: `{"facturaNro": 1047, "monto": 150000, "pix_payer_cpf": "12345678909", "pix_payer_phone": "+5511999999999", "pix_payer_email": "pax@example.com"}` (`pix_payer_cpf` and `pix_payer_phone` mandatory) $\to$ returns `issuerId: "PX"` and `montoRs` (BRL converted amount).
   - **Canje Puntos (`POST /pos/venta-canje`)**: `{"facturaNro": 1048, "monto": 150000}`.
   - **Billeteras (`POST /pos/venta-billetera`)**: `{"facturaNro": 1049, "monto": 150000, "billetera": "ZIM", "cuenta": "0981123456"}` (preserve leading `0` in `cuenta`!).
     - Official 5 wallet codes & returned `issuerId`: `ZIM` $\to$ `ZM` (**ZIMPLE**), `WPJ` $\to$ `PJ` (**Paraguayo Japonesa**), `VBV` $\to$ `VB` (**VISION**), `BPI` $\to$ `PI` (**Personal-Itau**), `BBF` $\to$ `BF` (**Billetera Viru**).
4. **Anulación & Mid-Step LAN Timeout Reconciliation (`POST /pos/consulta/anulacion` & `POST /pos/anulacion`)**:
   - Query voidable batch items (max 50): `POST /pos/consulta/anulacion` (`{"nroBoleta": "", "cantRegistro": 20}` or specific 12-digit `"nroBoleta"`) $\to$ `{"listado": [{"nroTarjeta", "nroBoleta", "monto", "fechaHora", "transaccion"}]}`. If `/pos/descuento` or a 1-step sale times out over LAN, **always reconcile via `/pos/consulta/anulacion` first** before releasing GDS seats or voiding.
   - Execute void: `POST /pos/anulacion` (`{"nroBoleta": "000000123456"}` — **strictly 12 digits**).
5. **Exact 17 Official Card `IssuerId` Codes (`ICP v1.7` p. 16)**:
   - `CB` (CABAL Crédito), `CC` (CREDIFIELCO Crédito), `CL` (CARTA CLAVE Crédito), `CP` (PANAL Crédito), `DC` (DINERS CLUB Crédito), `ID` (INFONET Débito), `MC` (MASTERCARD Crédito), `MD` (MASTERCARD Débito), `PC` (CREDICARD Crédito), `UD` (UNICA Débito), `VC` (VISA Crédito), `VD` (VISA Débito), `TD` (TARJETA DEBITO Débito), `TC` (TARJETA CREDITO Crédito), `CD` (DEBITO EN CUENTA Débito), `AC` (AMERICAN EXPRESS Crédito), `BC` (BANCARD Crédito).

---

## 4. Infonet Cobranzas, Pagopar, Dinelco/Bepsa, AdamsPay, Tigo Money & BCP PY-QR

### 4.1. Infonet Cobranzas (Bancard Billers & Cash Collection Network)
Enables cash/debit payment of online reservations across Aqui Pago, Pago Express, Practipago, and home-banking biller menus:
1. **`consulta`**: Bancard queries merchant endpoint with subscriber/booking identifier (`documento` or `codigo_reserva`); merchant returns pending invoices/quotas (`importe` integer PYG, `vencimiento`, `moneda: "PYG"`).
2. **`pago`**: Bancard notifies payment collection with unique `tid` (`transaccion_id`), `importe`, and `fecha_pago`; merchant commits booking idempotently by `tid`.
3. **`reversa`**: Same-day void/annulment referencing original `tid`; merchant voids unpaid/unboarded ticket or rejects if already consumed.

### 4.2. Pagopar (API 2.0 Checkout, 1.1 Operations & 3.0 Recurring `Bancard` / `uPay`)
All Pagopar tokens use lowercase hex `SHA-1`:
- **Init Checkout (`POST /api/comercios/2.0/iniciar-transaccion`)**: `sha1(private_key + id_pedido_comercio + monto_str)` (serialize integer `PYG` without `.0`, e.g., `"150000"` — never Python `str(float(150000))` `"150000.0"`).
- **Payment Methods (`POST /api/forma-pago/1.1/traer`)**: `sha1(private_key + "FORMA-PAGO")`
- **Incoming Webhook**: `sha1(private_key + resultado[0].hash_pedido)` (verify with `hmac.compare_digest` / `timingSafeEqual`)
- **Consult Order (`POST /api/pedidos/1.1/traer`)**: `sha1(private_key + "CONSULTA")`
- **Reverse Order (`POST /api/pedidos/1.1/reversar`)**: `sha1(private_key + "PEDIDO-REVERSAR")`
- **Card-on-File / Recurring (`POST /api/pago-recurrente/3.0/*`)**: `sha1(private_key + "PAGO-RECURRENTE")` across `agregar-cliente`, `agregar-tarjeta`, `listar-tarjeta`, `confirmar-tarjeta`, `eliminar-tarjeta`, and `pagar`, supporting dual acquiring via `proveedor: "Bancard" | "uPay"`.

### 4.3. Dinelco / Bepsa, AdamsPay v1 & Tigo Money MFS v2
- **Dinelco / Bepsa**: Second Paraguayan card/POS switch (BNF, Continental, Sudameris, Familiar, Atlas, Ueno). Supports Dinelco Link de Pagos, Dinelco Web Checkout, physical POS pinpads, and full PY-QR EMVCo interoperability.
- **AdamsPay v1 (`https://api.adamspay.com/api/v1` / `https://staging.adamspay.com/api/v1`)**:
  - Create Debt: `POST /debts` with header `apikey: <API_KEY>` (and optional `x-if-exists: update`), body `{"debt": {"docId": "ORD-501", "amount": {"currency": "PYG", "value": "150000"}, "label": "...", "validPeriod": {"start": "...", "end": "..."}}}`.
  - Webhook Verification: Header `x-adams-notify-hash` equals `md5("adams" + raw_request_body_utf8 + webhook_secret)`.
- **Tigo Money MFS v2**:
  - Step 1: OAuth2 token via `POST /v1/oauth/generate/accesstoken?grant_type=client_credentials` (HTTP Basic Auth `client_id:client_secret`).
  - Step 2: `POST /v2/tigo/mfs/payments/authorizations` with `Bearer <access_token>`, `MasterMerchant`, `Subscriber` (`59598XXXXXXX`), `LocalPayment` (`amount` PYG), `redirectUri`, and `callbackUri` (triggers USSD PIN prompt on subscriber phone).

### 4.4. BCP SIPAP / SPI / PY-QR (Ley N° 7503/2025 & EMVCo CRC-16 `0x1021`)
- **Regulatory Framework**: Governed by Central Bank of Paraguay (**BCP**) under **Ley N° 7503/2025** (*Sistema Nacional de Pagos*).
- **SPI (Sistema de Pagos Instantáneos)**: 24/7/365 real-time interbank settlement in `PYG` with standard instant transfer cap of **Gs. 10.000.000** per operation.
- **EMVCo PY-QR TLV Tags**:
  - `00` = `"01"` (Payload Format Indicator), `01` = `"12"` (Dynamic QR), `26..51` = Merchant Account Info (`py.com.bancard` / `py.com.dinelco` / SPI alias), `52` = `"4131"` (**MCC `4131` Bus Lines / Passenger Transport**), `53` = `"600"` (**ISO 4217 Numeric Currency `600` = `PYG`**), `54` = integer amount string (e.g. `"150000"`), `58` = `"PY"`, `59` = Merchant Name (`<=25` ASCII chars), `60` = Merchant City, `62` = Additional Data (`05` Reference/Order ID), `63` = `"04"` + **4-char uppercase hex CRC-16/CCITT-FALSE** (`poly=0x1021`, `init=0xFFFF`).

---

## 5. SIFEN / Ekuatia (DNIT Paraguay v150) & Transbank (Chile)

### 5.1. SIFEN 44-Digit CDC Composition (`Mod-11` Weights `2..11`)
| Pos (1-based) | Length | XML Tag | Description | Example (`BOLETOS.LA E.A.S.`) |
| :--- | :--- | :--- | :--- | :--- |
| `01–02` | 2 | `iTiDE` | `01` Factura, `04` Autofactura, `05` Nota Crédito, `06` Nota Débito, `07` Remisión | `01` |
| `03–10` | 8 | `dRucEm` | Issuer RUC left-padded with zeros | `80171570` |
| `11` | 1 | `dDVEmi` | Issuer RUC check digit (`Mod-11` weights `2..11`) | `9` |
| `12–14` | 3 | `dEst` | Establishment code | `001` |
| `15–17` | 3 | `dPunExp` | Expedition point (e.g., `004`) | `004` |
| `18–24` | 7 | `dNumDoc` | Sequential document number | `0015420` |
| `25` | 1 | `iTipCont` | `1` Persona Física, `2` Persona Jurídica | `2` |
| `26–33` | 8 | `dFeEmiDE` | Emission date (`YYYYMMDD`) | `20261019` |
| `34` | 1 | `iTipEmi` | `1` Normal, `2` Contingencia | `1` |
| `35–43` | 9 | `dCodSeg` | Non-zero random 9-digit security code (`000000001`–`999999999`) | `482910374` |
| `44` | 1 | `dDVId` | DNIT `Mod-11` check digit over first 43 digits (**weights `2..11` right-to-left**) | `DV` |

### 5.2. Transbank Webpay Plus REST v1.2 & Serial POS Integrado
- **Webpay Plus v1.2**: `POST /rswebpaytransaction/api/webpay/v1.2/transactions` (init), `PUT .../{token}` (commit — catch **HTTP 422** on browser double-redirect and fall back to `GET .../{token}` idempotently), `POST .../{token}/refunds` (`REVERSED` or `NULLIFIED`), plus 4 return callback scenarios (`token_ws`, `TBK_TOKEN` user abort, timeout, anomalous double token).
- **POS Integrado (`115200 8N1`)**: `<STX 0x02><Command|Fields><ETX 0x03><LRC XOR>`.
