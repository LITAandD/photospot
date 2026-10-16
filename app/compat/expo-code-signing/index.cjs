'use strict';
// Scoped to Expo CLI 55.0.36's reviewed API, not the whole node-forge API.
// All key generation, signatures and signature verification use Node/OpenSSL.
// Peculiar schemas encode the CSR; no RSA or ASN.1 algorithm is vendored here.
require('reflect-metadata');
const crypto = require('node:crypto');
const x509 = require('@peculiar/x509');
const { AsnConvert } = require('@peculiar/asn1-schema');
const { CertificationRequest, CertificationRequestInfo } = require('@peculiar/asn1-csr');
const { Name, SubjectPublicKeyInfo, AlgorithmIdentifier } = require('@peculiar/asn1-x509');
const SHA256_WITH_RSA = '1.2.840.113549.1.1.11';
const CODE_SIGNING = '1.3.6.1.5.5.7.3.3';
const LIMIT = 65536;

function rsa(key, type) {
  if (!(key instanceof crypto.KeyObject) || key.type !== type || key.asymmetricKeyType !== 'rsa') {
    throw new TypeError(`Expected an RSA ${type} key`);
  }
  return key;
}
function boundedPEM(pem) {
  if (typeof pem !== 'string' || Buffer.byteLength(pem) > LIMIT) throw new TypeError('Invalid or oversized PEM');
  return pem;
}
function generateKeyPair() { return crypto.generateKeyPairSync('rsa', { modulusLength: 2048, publicExponent: 65537 }); }
function convertPrivateKeyPEMToPrivateKey(pem) { return rsa(crypto.createPrivateKey(boundedPEM(pem)), 'private'); }
function convertKeyPairToPEM(pair) {
  return { privateKeyPEM: rsa(pair.privateKey, 'private').export({ type: 'pkcs1', format: 'pem' }),
    publicKeyPEM: rsa(pair.publicKey, 'public').export({ type: 'spki', format: 'pem' }) };
}
function convertCertificatePEMToCertificate(pem) {
  boundedPEM(pem);
  const native = new crypto.X509Certificate(pem);
  const parsed = new x509.X509Certificate(native.raw);
  return {
    native, parsed, publicKey: native.publicKey,
    validity: { notBefore: native.validFromDate, notAfter: native.validToDate },
  };
}
function validateSelfSignedCertificate(certificate, pair) {
  const { native, parsed, validity } = certificate;
  const now = new Date();
  // checkIssued() also applies CA key-usage rules; Expo's self-signed leaf is
  // intentionally digitalSignature-only. Compare DNs and verify its signature.
  if (!Buffer.from(parsed.issuerName.toArrayBuffer()).equals(Buffer.from(parsed.subjectName.toArrayBuffer())) ||
      !native.verify(native.publicKey)) throw new Error('Certificate is not validly self-signed');
  if (validity.notBefore > now || validity.notAfter < now) throw new Error('Certificate validity expired');
  const keyUsage = parsed.getExtension(x509.KeyUsagesExtension);
  const extKeyUsage = parsed.getExtension(x509.ExtendedKeyUsageExtension);
  if (!keyUsage || !(keyUsage.usages & x509.KeyUsageFlags.digitalSignature)) throw new Error('Digital Signature key usage missing');
  if (!extKeyUsage || !extKeyUsage.usages.includes(CODE_SIGNING)) throw new Error('Code Signing extended key usage missing');
  rsa(native.publicKey, 'public');
  if (!native.publicKey.equals(rsa(pair.publicKey, 'public')) || !native.checkPrivateKey(rsa(pair.privateKey, 'private'))) {
    throw new Error('Certificate and key pair do not match');
  }
}
function signBufferRSASHA256AndVerify(privateKey, certificate, buffer) {
  rsa(privateKey, 'private');
  rsa(certificate.publicKey, 'public');
  if (!Buffer.isBuffer(buffer)) throw new TypeError('Expected a Buffer to sign');
  const signature = crypto.sign('RSA-SHA256', buffer, { key: privateKey, padding: crypto.constants.RSA_PKCS1_PADDING });
  if (!crypto.verify('RSA-SHA256', buffer, { key: certificate.publicKey, padding: crypto.constants.RSA_PKCS1_PADDING }, signature)) {
    throw new Error('Signature does not match certificate');
  }
  return signature.toString('base64');
}
function generateCSR(pair, commonName) {
  rsa(pair.publicKey, 'public'); rsa(pair.privateKey, 'private');
  if (typeof commonName !== 'string' || commonName.length > 1024) throw new TypeError('Invalid CSR common name');
  if (!crypto.createPublicKey(pair.privateKey).equals(pair.publicKey)) throw new Error('CSR key pair does not match');
  // Structured DN input prevents commas/equals in the CN becoming extra fields.
  const subject = new x509.Name([{ CN: [commonName] }]);
  const info = new CertificationRequestInfo({
    subject: AsnConvert.parse(subject.toArrayBuffer(), Name),
    subjectPKInfo: AsnConvert.parse(pair.publicKey.export({ type: 'spki', format: 'der' }), SubjectPublicKeyInfo),
  });
  const bytes = Buffer.from(AsnConvert.serialize(info));
  const signature = crypto.sign('RSA-SHA256', bytes, { key: pair.privateKey, padding: crypto.constants.RSA_PKCS1_PADDING });
  const csr = new CertificationRequest({ certificationRequestInfo: info,
    signatureAlgorithm: new AlgorithmIdentifier({ algorithm: SHA256_WITH_RSA, parameters: null }),
    signature: Uint8Array.from(signature).buffer });
  return new x509.Pkcs10CertificateRequest(AsnConvert.serialize(csr));
}
function convertCSRToCSRPEM(csr) {
  if (!(csr instanceof x509.Pkcs10CertificateRequest)) throw new TypeError('Expected a certificate request');
  return csr.toString('pem');
}
module.exports = Object.freeze({ generateKeyPair, convertKeyPairToPEM, convertPrivateKeyPEMToPrivateKey,
  convertCertificatePEMToCertificate, validateSelfSignedCertificate, signBufferRSASHA256AndVerify,
  generateCSR, convertCSRToCSRPEM });
