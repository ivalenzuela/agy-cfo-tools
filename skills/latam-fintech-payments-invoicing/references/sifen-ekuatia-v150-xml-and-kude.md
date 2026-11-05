# Deep Reference: SIFEN / Ekuatia DNIT Paraguay v150 XML, mTLS WSDLs, X.509 Signature & KuDE PDF

Complete implementation guide for Paraguayan Electronic Invoicing (`SIFEN` / `Ekuatia` Manual Técnico v150, Dirección Nacional de Ingresos Tributarios - DNIT, and **Ley N° 6380/2019**).

---

## 1. Tax Liquidation Rules in Guaraníes (`PYG`) & Passenger Transport IVA (Ley 6380/2019)

Paraguayan Guaraníes (`PYG`) do not use decimals in SIFEN tax totals (`dSub10`, `dSub5`, `dIVA10`, `dIVA5`, `dBaseGrav10`, `dBaseGrav5`). Floating-point discrepancies trigger DNIT rejection code `1303` (*"El total de liquidación del IVA no coincide con la sumatoria de los ítems"*).

### 1.1. Passenger Transport Tax Regime (`Ley N° 6380/2019 Art. 100 Num. 3 Inc. h`)
- **Short-Distance Domestic (`<= 100 km`) & International Segments**: **Exento (`0%` IVA)** — `<iAfecIVA>3</iAfecIVA>`, `<dDesAfecIVA>Exento</dDesAfecIVA>`, `<dPropIVA>0</dPropIVA>`, `<dTasaIVA>0</dTasaIVA>`, `<dBasGravIVA>0</dBasGravIVA>`, `<dLiqIVAItem>0</dLiqIVAItem>`.
- **Long-Distance Domestic Interurban (`> 100 km`) & Parcels (`Encomiendas`)**: **Gravado 10% IVA** — `<iAfecIVA>1</iAfecIVA>`, `<dDesAfecIVA>Gravado IVA</dDesAfecIVA>`, `<dPropIVA>100</dPropIVA>`, `<dTasaIVA>10</dTasaIVA>`.
- **Strict Prohibition**: Public passenger bus tickets in Paraguay are **NEVER** taxed at `5%` IVA (`5%` applies strictly to basic food basket, pharmaceuticals, and residential rentals).

### 1.2. Per-Item & Global IVA Formulas (Tax-Inclusive Prices)
- **IVA 10% (`iAfecIVA = 1`, `dTasaIVA = 10`, `dPropIVA = 100`) — e.g., domestic bus ticket `> 100 km`, encomiendas, platform fee**:
  - `dLiqIVAItem = round(dTotOpeItem / 11)`
  - `dBasGravIVA = dTotOpeItem - dLiqIVAItem`
- **IVA 5% (`iAfecIVA = 1`, `dTasaIVA = 5`, `dPropIVA = 100`) — e.g., residential rental / basic food basket / pharmaceuticals**:
  - `dLiqIVAItem = round(dTotOpeItem / 21)`
  - `dBasGravIVA = dTotOpeItem - dLiqIVAItem`
- **Exenta (`iAfecIVA = 3`, `dPropIVA = 0`, `dTasaIVA = 0`) — e.g., urban/short-distance bus ticket `<= 100 km` or international route**:
  - `dLiqIVAItem = 0`, `dBasGravIVA = 0` -> accumulates into **`<dSubExe>`** (`<dSubExo>` is strictly `0` unless `iAfecIVA = 2` Exonerado).
- **Subtotals (`<gTotSub>`) & `<gDatRec>` (`DE_v150.xsd` `D200–D299`)**:
  - `dSubExe = sum(item.dTotOpeItem for item in items_exempt)` (`iAfecIVA = 3`), `dSubExo = 0`
  - `dIVA10 = sum(item.dLiqIVAItem for item in items_10)`, `dIVA5 = sum(item.dLiqIVAItem for item in items_5)`
  - `dBaseGrav10 = sum(item.dBasGravIVA for item in items_10)`, `dBaseGrav5 = sum(item.dBasGravIVA for item in items_5)`
  - `dTotIVA = dIVA10 + dIVA5`, `dTBasGraIVA = dBaseGrav10 + dBaseGrav5`
  - **`<gDatRec>` XSD Mutual Exclusivity**: When `<iNatRec>1</iNatRec>` (Taxpayer), emit `<iTiContRec>`, `<dRucRec>`, and `<dDVRec>` (omit `<iTipIDRec>`/`<dNumIDRec>`). When `<iNatRec>2</iNatRec>` (Non-Taxpayer with Cédula/Passport), **strictly omit** `<iTiContRec>`, `<dRucRec>`, and `<dDVRec>`, and emit `<iTipIDRec>1</iTipIDRec><dDTipIDRec>Cédula paraguaya</dDTipIDRec><dNumIDRec>{ci}</dNumIDRec>`.

---

## 2. Official SIFEN v150 SOAP Web Services (6 mTLS `.p12` WSDLs)

All SOAP requests to DNIT SIFEN require **Mutual TLS (mTLS)** authenticated with the taxpayer's accredited Paraguayan X.509 certificate (`.p12` / `.pfx`, TLS 1.2+):

| Web Service | Homologación (`sifen-test.set.gov.py`) | Producción (`sifen.set.gov.py`) | Purpose & Operational Limit |
| :--- | :--- | :--- | :--- |
| **Recepción Síncrona** | `/de/ws/sync/recibe.wsdl` | `/de/ws/sync/recibe.wsdl` | Single `rDE` synchronous submission. |
| **Recepción Lote Asíncrona** | `/de/ws/async/recibe-lote.wsdl` | `/de/ws/async/recibe-lote.wsdl` | Batch ZIP/XML submission (up to **50 DEs** per `rLoteDE`). |
| **Consulta de Lote** | `/de/ws/consultas/consulta-lote.wsdl` | `/de/ws/consultas/consulta-lote.wsdl` | Poll asynchronous batch processing result by `dProtConsLote`. |
| **Consulta de DE (CDC)** | `/de/ws/consultas/consulta.wsdl` | `/de/ws/consultas/consulta.wsdl` | Verify live status and XML of a 44-digit CDC. |
| **Consulta de RUC** | `/de/ws/consultas/consulta-ruc.wsdl` | `/de/ws/consultas/consulta-ruc.wsdl` | Validate taxpayer RUC, legal name, and active status. |
| **Recepción de Eventos** | `/de/ws/eventos/evento.wsdl` | `/de/ws/eventos/evento.wsdl` | Cancellation (`< 48h` for `iTiDE=01`; after 48h emit Nota de Crédito `iTiDE=05`), Inutilización, Conformidad/Disconformidad. |

---

## 3. X.509 Digital Signature (`XMLDSig` Over `<DE Id="...">`)

SIFEN requires an **Enveloped / Detached sibling signature** inside `<rDE>` immediately following `</DE>` and preceding `<gCamFuFD>`:
1. **Certificate Type**: PKCS#12 (`.p12` / `.pfx`) issued by an accredited Paraguayan CA (EFirma / Code100 / Documenta) with the taxpayer's RUC in `Subject.serialNumber`.
2. **Target Node**: `<DE Id="{44_digit_CDC}">` referenced via `<Reference URI="#{44_digit_CDC}">`.
3. **Transforms & Algorithms**: `enveloped-signature` + `http://www.w3.org/2001/10/xml-exc-c14n#`, `DigestMethod` `sha256`, `SignatureMethod` `rsa-sha256`.
4. **Whitespace Invariant**: Never pretty-print or re-indent the XML after computing `<DigestValue>` and `<SignatureValue>` (prevents DNIT error `0160`).

---

## 4. Official KuDE Tax QR (`<dCarQR>`) & PDF Layout

The `<dCarQR>` element inside `<gCamFuFD>` MUST be generated **after** signing `<DE>` so it embeds the real `<DigestValue>`:
1. Exact query parameter order (unencoded keys):
   `nVersion=150&Id=<44_digit_CDC>&dFeEmiDE=<hex_utf8(dFeEmiDE)>&<dRucRec_or_dNumIDRec>&dTotGralOpe=<total>&dTotIVA=<iva>&cItems=<count>&DigestValue=<hex_utf8(base64_digest_value)>&IdCSC=<4_digit_id>`
   *(Use `dRucRec=<ruc>` when `iNatRec == 1` taxpayer; use `dNumIDRec=<doc>` when `iNatRec == 2` non-taxpayer individual, or `dNumIDRec=0` if innominado `iTipIDRec == 5`)*.
2. Append secret 32-char `CSC` (`raw = query + csc_secret`), hash with `SHA-256` (64 lowercase hex chars), and append `&cHashQR=<hash>` (escaped as `&amp;` inside XML `<dCarQR>`, unescaped inside QR barcode image).
3. **KuDE Footer**: Render QR at `>= 2.5cm x 2.5cm` (`ECC Level M`), print the 44-digit CDC in 11 groups of 4 digits:
   `0180 1715 7090 0100 4001 5420 2202 6101 9148 2910 3740`
   and include the mandatory e-Kuatia verification legend (`https://ekuatia.set.gov.py/consultas/`).

---

## 5. Common DNIT SIFEN Status & Rejection Codes

| Code | DNIT Message | Meaning / Root Cause & Fix |
| :--- | :--- | :--- |
| `0260` | Autorización del DE satisfactoria | **Approved** ( fiscal document accepted and registered by DNIT SIFEN; `0261` = Approved with observation). |
| `0141` | El CDC no corresponde a los campos del DE | Mismatch between 44-digit `<DE Id="...">` (or Mod-11 weights `2..11`) and internal XML tags. Build both from one immutable struct. |
| `0142` / `0162` | Certificado electrónico no vigente, revocado o RUC no coincide | `.p12` expired, CRL-revoked, or certificate RUC mismatch with `<dRucEm>`. Monitor `notAfter`. |
| `0160` | Mal formado el XML / Firma digital inválida | XSD violation (e.g., emitting `<dRucRec>` when `iNatRec=2`), XML mutated after signing, or `xml-exc-c14n#` omitted. |
| `1303` | Liquidación de IVA incorrecta | `dIVA10`/`dIVA5` mismatch with item sums, fractional decimals in `PYG`, or invalid tax rate for item category. |
| `4002` | Hash del Código QR inválido (`cHashQR`) | Placeholder `DigestValue` used instead of real XMLDSig digest, missing UTF-8 hex encoding on `dFeEmiDE`/`DigestValue`, or `&amp;` hashed instead of `&`. |
