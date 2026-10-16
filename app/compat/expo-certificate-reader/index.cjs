'use strict';
const { X509Certificate } = require('node:crypto');
// This is deliberately NOT a general node-forge implementation. The pinned
// Expo iOS Security.js caller only reads CN, O and OU from a PEM certificate.
function certificateFromPem(pem) {
  if (typeof pem !== 'string' || Buffer.byteLength(pem) > 65536) throw new TypeError('Invalid certificate PEM');
  const native = new X509Certificate(pem);
  const fields = native.toLegacyObject().subject;
  return { subject: { getField(name) {
    const value = fields[name];
    return value === undefined ? null : { value: Array.isArray(value) ? value[0] : value };
  } } };
}
module.exports = Object.freeze({ pki: Object.freeze({ certificateFromPem }) });
