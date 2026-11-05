/**
 * TypeScript Reference Orchestrator for LATAM FinTech Gateways & SIFEN Invoicing
 * Compatible with Next.js App Router BFF (/api/bancard/*, /api/pagopar/*, /api/transbank/*),
 * Node.js v22+/v26+ native TypeScript execution (erasableSyntaxOnly compliant), and Bun/Deno.
 */
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

export type SupportedCurrency = 'PYG' | 'USD' | 'CLP';

export interface BancardWebhookOperation {
  token: string;
  shop_process_id: number;
  response: 'S' | 'N';
  response_details: string;
  amount: string;
  currency: 'PYG' | 'USD';
  authorization_number?: string;
  ticket_number?: string;
  response_code: string;
  response_description: string;
}

export interface SifenCdcInput {
  tipoDe: string;
  rucEmisor: string;
  dvEmisor: string | number;
  establecimiento: string;
  puntoExpedicion: string;
  numeroDocumento: string;
  tipoContribuyente: '1' | '2';
  fechaEmision: string;
  tipoEmision: '1' | '2';
  codigoSeguridad: string;
}

export class LatamFintechOrchestrator {
  private readonly bancardPublicKey: string;
  private readonly bancardPrivateKey: string;
  private readonly pagoparPrivateKey: string;
  private readonly sifenIdCsc: string;
  private readonly sifenCscSecret: string;

  constructor(
    bancardPublicKey: string,
    bancardPrivateKey: string,
    pagoparPrivateKey: string,
    sifenIdCsc: string,
    sifenCscSecret: string
  ) {
    this.bancardPublicKey = bancardPublicKey;
    this.bancardPrivateKey = bancardPrivateKey;
    this.pagoparPrivateKey = pagoparPrivateKey;
    this.sifenIdCsc = sifenIdCsc;
    this.sifenCscSecret = sifenCscSecret;
  }

  /**
   * 1. Bancard vPOS Single Buy MD5 Token
   */
  public createBancardSingleBuyToken(
    shopProcessId: number | string,
    amountPyg: number,
    currency: 'PYG' | 'USD' = 'PYG'
  ): {
    amountFormatted: string;
    token: string;
  } {
    if (!Number.isFinite(amountPyg) || amountPyg <= 0) {
      throw new Error(`Invalid Bancard amount: ${amountPyg}`);
    }
    const amountFormatted = amountPyg.toFixed(2);
    const raw = `${this.bancardPrivateKey}${shopProcessId}${amountFormatted}${currency}`;
    const token = crypto.createHash('md5').update(raw, 'utf8').digest('hex');
    return { amountFormatted, token };
  }

  /**
   * 2. Constant-time Bancard Webhook Token Validation
   */
  public verifyBancardWebhook(op: BancardWebhookOperation, expectedAmount?: string, expectedCurrency?: 'PYG' | 'USD'): boolean {
    if (!/^\d+\.\d{2}$/.test(op.amount) || !/^[a-f0-9]{32}$/i.test(op.token)) {
      return false;
    }
    if (expectedAmount !== undefined && op.amount !== expectedAmount) {
      return false;
    }
    if (expectedCurrency !== undefined && op.currency !== expectedCurrency) {
      return false;
    }
    const raw = `${this.bancardPrivateKey}${op.shop_process_id}confirm${op.amount}${op.currency}`;
    const expected = crypto.createHash('md5').update(raw, 'utf8').digest('hex');
    return crypto.timingSafeEqual(Buffer.from(expected, 'utf8'), Buffer.from(op.token.toLowerCase(), 'utf8'));
  }

  /**
   * 3. Bancard 2PC Automatic Rollback & Confirmation Query Payloads
   */
  public buildBancardRollbackPayload(shopProcessId: number | string): {
    public_key: string;
    operation: { token: string; shop_process_id: number };
  } {
    const raw = `${this.bancardPrivateKey}${shopProcessId}rollback0.00`;
    const token = crypto.createHash('md5').update(raw, 'utf8').digest('hex');
    return {
      public_key: this.bancardPublicKey,
      operation: {
        token,
        shop_process_id: Number(shopProcessId),
      },
    };
  }

  public buildBancardGetConfirmationPayload(shopProcessId: number | string): {
    public_key: string;
    operation: { token: string; shop_process_id: number };
  } {
    const raw = `${this.bancardPrivateKey}${shopProcessId}get_confirmation`;
    const token = crypto.createHash('md5').update(raw, 'utf8').digest('hex');
    return {
      public_key: this.bancardPublicKey,
      operation: {
        token,
        shop_process_id: Number(shopProcessId),
      },
    };
  }

  public createBancardPreauthConfirmToken(shopProcessId: number | string): string {
    return crypto
      .createHash('md5')
      .update(`${this.bancardPrivateKey}${shopProcessId}pre-authorization-confirm`, 'utf8')
      .digest('hex');
  }

  public createBancardBillingClientInfoToken(): string {
    return crypto.createHash('md5').update(`${this.bancardPrivateKey}billing_client_info`, 'utf8').digest('hex');
  }

  public createBancardBillingCancelToken(shopProcessId: number | string): string {
    return crypto
      .createHash('md5')
      .update(`${this.bancardPrivateKey}${shopProcessId}billing_cancel`, 'utf8')
      .digest('hex');
  }

  /**
   * 4. Pagopar SHA-1 Order & Webhook Verification
   */
  public createPagoparOrderToken(idPedidoComercio: string | number, montoTotal: number): string {
    if (!Number.isFinite(montoTotal) || montoTotal <= 0) {
      throw new Error(`Invalid Pagopar montoTotal: ${montoTotal}`);
    }
    const montoStr = Number.isInteger(montoTotal) ? String(Math.trunc(montoTotal)) : String(montoTotal);
    const raw = `${this.pagoparPrivateKey}${idPedidoComercio}${montoStr}`;
    return crypto.createHash('sha1').update(raw, 'utf8').digest('hex');
  }

  public verifyPagoparWebhook(hashPedido: string, receivedToken: string): boolean {
    if (!/^[a-f0-9]{40}$/i.test(receivedToken)) {
      return false;
    }
    const expected = crypto.createHash('sha1').update(`${this.pagoparPrivateKey}${hashPedido}`, 'utf8').digest('hex');
    return crypto.timingSafeEqual(Buffer.from(expected, 'utf8'), Buffer.from(receivedToken.toLowerCase(), 'utf8'));
  }

  /**
   * 5. SIFEN / Ekuatia Mod-11, 44-Digit CDC, PYG IVA & Official KuDE QR Generator (v150)
   */
  public calculateSifenMod11(numericChain: string, maxWeight = 11): number {
    if (!/^\d+$/.test(numericChain)) {
      throw new Error(`SIFEN Mod-11 input must contain only digits, got: ${numericChain}`);
    }
    let weight = 2;
    let total = 0;
    for (let i = numericChain.length - 1; i >= 0; i--) {
      total += Number(numericChain[i]) * weight;
      weight = weight >= maxWeight ? 2 : weight + 1;
    }
    const remainder = total % 11;
    return remainder <= 1 ? 0 : 11 - remainder;
  }

  public buildSifenCdc44(input: SifenCdcInput): string {
    const rucPadded = input.rucEmisor.padStart(8, '0');
    const expectedRucDv = this.calculateSifenMod11(rucPadded, 11);
    if (Number(input.dvEmisor) !== expectedRucDv) {
      throw new Error(`RUC DV mismatch: expected ${expectedRucDv}, got ${input.dvEmisor}`);
    }
    if (!/^\d{8}$/.test(input.fechaEmision)) {
      throw new Error(`Invalid fechaEmision YYYYMMDD: ${input.fechaEmision}`);
    }
    const secPadded = input.codigoSeguridad.padStart(9, '0');
    if (!/^\d{9}$/.test(secPadded) || Number(secPadded) === 0) {
      throw new Error(`Invalid 9-digit security code: ${input.codigoSeguridad}`);
    }
    const base43 =
      input.tipoDe.padStart(2, '0') +
      rucPadded +
      String(expectedRucDv) +
      input.establecimiento.padStart(3, '0') +
      input.puntoExpedicion.padStart(3, '0') +
      input.numeroDocumento.padStart(7, '0') +
      input.tipoContribuyente +
      input.fechaEmision +
      input.tipoEmision +
      secPadded;

    if (!/^\d{43}$/.test(base43)) {
      throw new Error(`Invalid 43-digit CDC base: ${base43}`);
    }
    const dv = this.calculateSifenMod11(base43, 11);
    return `${base43}${dv}`;
  }

  public liquidatePygIva(grossAmountPyg: number, rate: 10 | 5 | 0): {
    gross: number;
    baseGravada: number;
    iva: number;
    exenta: number;
  } {
    if (!Number.isInteger(grossAmountPyg) || grossAmountPyg < 0) {
      throw new Error(`PYG amount must be a non-negative integer: ${grossAmountPyg}`);
    }
    if (rate === 10) {
      const iva = Math.round(grossAmountPyg / 11);
      return { gross: grossAmountPyg, baseGravada: grossAmountPyg - iva, iva, exenta: 0 };
    }
    if (rate === 5) {
      const iva = Math.round(grossAmountPyg / 21);
      return { gross: grossAmountPyg, baseGravada: grossAmountPyg - iva, iva, exenta: 0 };
    }
    return { gross: grossAmountPyg, baseGravada: 0, iva: 0, exenta: grossAmountPyg };
  }

  public buildSifenQrUrl(params: {
    baseUrl: string;
    cdc44: string;
    fechaEmisionIso: string;
    natReceptor?: 1 | 2;
    rucReceptor: string;
    totGralOpe: number;
    totIva: number;
    cItems: number;
    digestValueBase64: string;
  }): string {
    const fechaHex = Buffer.from(params.fechaEmisionIso, 'utf8').toString('hex');
    const digestHex = Buffer.from(params.digestValueBase64, 'utf8').toString('hex');
    const idCsc = this.sifenIdCsc.padStart(4, '0');
    const recParam = (params.natReceptor ?? 1) === 2
      ? `dNumIDRec=${params.rucReceptor}`
      : `dRucRec=${params.rucReceptor}`;
    const query =
      `nVersion=150&Id=${params.cdc44}&dFeEmiDE=${fechaHex}` +
      `&${recParam}&dTotGralOpe=${params.totGralOpe}` +
      `&dTotIVA=${params.totIva}&cItems=${params.cItems}` +
      `&DigestValue=${digestHex}&IdCSC=${idCsc}`;

    const cHashQR = crypto
      .createHash('sha256')
      .update(`${query}${this.sifenCscSecret}`, 'utf8')
      .digest('hex');

    const sep = params.baseUrl.endsWith('?') ? '' : '?';
    return `${params.baseUrl}${sep}${query}&cHashQR=${cHashQR}`;
  }

  /**
   * 6. Bancard VentasQR Basic Auth, AdamsPay v1 Webhook & BCP SIPAP EMVCo PY-QR (CRC-16/CCITT-FALSE 0x1021)
   */
  public buildBancardVentasQrBasicAuth(): string {
    const b64 = Buffer.from(`apps/${this.bancardPublicKey}:${this.bancardPrivateKey}`, 'utf8').toString('base64');
    return `Basic ${b64}`;
  }

  public computeAdamsPayWebhookHash(rawBody: string, adamsSecret: string): string {
    return crypto.createHash('md5').update(`adams${rawBody}${adamsSecret}`, 'utf8').digest('hex');
  }

  public computeEmvcoCrc16CcittFalse(payloadThrough6304: string): string {
    let crc = 0xffff;
    for (const b of Buffer.from(payloadThrough6304, 'utf8')) {
      crc ^= b << 8;
      for (let bit = 0; bit < 8; bit++) {
        crc = (crc & 0x8000) !== 0 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
      }
    }
    return crc.toString(16).toUpperCase().padStart(4, '0');
  }

  public buildParaguayEmvcoPyQr(params: {
    merchantGuid: string;
    commerceId: string;
    amountPyg: number;
    referenceId: string;
    merchantName?: string;
    merchantCity?: string;
    mcc?: string;
  }): string {
    if (!Number.isInteger(params.amountPyg) || params.amountPyg <= 0 || params.amountPyg > 10_000_000) {
      throw new Error(`Invalid SPI PY-QR amount: ${params.amountPyg}`);
    }
    const tlv = (tag: string, val: string): string => `${tag}${String(val.length).padStart(2, '0')}${val}`;
    const mai = tlv('00', params.merchantGuid) + tlv('01', params.commerceId);
    const addData = tlv('05', params.referenceId.slice(0, 25));
    const bodyNoCrc =
      tlv('00', '01') +
      tlv('01', '12') +
      tlv('26', mai) +
      tlv('52', params.mcc ?? '4131') +
      tlv('53', '600') +
      tlv('54', String(params.amountPyg)) +
      tlv('58', 'PY') +
      tlv('59', (params.merchantName ?? 'BOLETOS.LA PARAGUAY').slice(0, 25)) +
      tlv('60', (params.merchantCity ?? 'ASUNCION').slice(0, 15)) +
      tlv('62', addData) +
      '6304';
    return `${bodyNoCrc}${this.computeEmvcoCrc16CcittFalse(bodyNoCrc)}`;
  }

  /**
   * 7. Transbank POS Integrado Serial Framing (STX + Payload + ETX + LRC)
   */
  public buildTransbankPosFrame(commandPayload: string): Buffer {
    if (!commandPayload) {
      throw new Error('POS commandPayload cannot be empty');
    }
    const bodyPlusEtx = Buffer.concat([Buffer.from(commandPayload, 'ascii'), Buffer.from([0x03])]);
    let lrc = 0;
    for (const byte of bodyPlusEtx) {
      lrc ^= byte;
    }
    return Buffer.concat([Buffer.from([0x02]), bodyPlusEtx, Buffer.from([lrc])]);
  }
}

// Self-test runner when executed directly via `node examples/typescript_gateway_orchestrator.ts`
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const orch = new LatamFintechOrchestrator(
    'pub_key_demo',
    'priv_key_secret_123',
    'pp_priv',
    '0001',
    'ABCD1234EFGH5678IJKL9012MNOP3456'
  );
  const singleBuy = orch.createBancardSingleBuyToken(100501, 150000, 'PYG');
  const rbPayload = orch.buildBancardRollbackPayload(100502);
  const preauthToken = orch.createBancardPreauthConfirmToken(100503);
  const ventasQrAuth = orch.buildBancardVentasQrBasicAuth();
  const adamsBody = '{"notify":{"type":"debt","id":"ORD-100501"}}';
  const adamsHash = orch.computeAdamsPayWebhookHash(adamsBody, 'adams_secret_demo');
  const pyQr = orch.buildParaguayEmvcoPyQr({
    merchantGuid: 'py.com.bancard',
    commerceId: 'BOLETOS01',
    amountPyg: 150000,
    referenceId: 'ORD-100501',
  });
  const dv = orch.calculateSifenMod11('80171570');
  const cdc44 = orch.buildSifenCdc44({
    tipoDe: '01',
    rucEmisor: '80171570',
    dvEmisor: dv,
    establecimiento: '001',
    puntoExpedicion: '004',
    numeroDocumento: '0015420',
    tipoContribuyente: '2',
    fechaEmision: '20261019',
    tipoEmision: '1',
    codigoSeguridad: '482910374',
  });
  const iva10 = orch.liquidatePygIva(150000, 10);
  const posFrame = orch.buildTransbankPosFrame('0200|25900|100501||0');

  console.log(
    JSON.stringify({
      runtime: 'node_ts_native',
      bancard_single_buy_token: singleBuy.token,
      bancard_rollback_token: rbPayload.operation.token,
      bancard_preauth_confirm_token: preauthToken,
      bancard_ventas_qr_auth: ventasQrAuth,
      adamspay_webhook_hash: adamsHash,
      emvco_py_qr: pyQr,
      sifen_cdc_44: cdc44,
      sifen_iva_10_pyg: iva10.iva,
      transbank_pos_frame_hex: posFrame.toString('hex'),
    })
  );
}
