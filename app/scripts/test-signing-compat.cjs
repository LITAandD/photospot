const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const req = createRequire(path.resolve(__dirname, '../package.json'));
const signing = req('@expo/code-signing-certificates');
const signingReq = createRequire(req.resolve('@expo/code-signing-certificates'));
const reader = req('node-forge');
const x509 = signingReq('@peculiar/x509');
const { AsnConvert } = signingReq('@peculiar/asn1-schema');
const { Certificate } = signingReq('@peculiar/asn1-x509');
const expoReq = createRequire(req.resolve('expo/package.json'));
const cliRoot = path.dirname(expoReq.resolve('@expo/cli/package.json'));
const cli = require(path.join(cliRoot, 'build/src/utils/codesigning.js'));
x509.cryptoProvider.set(crypto.webcrypto);
const algorithm = { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256', publicExponent: new Uint8Array([1, 0, 1]), modulusLength: 2048 };
async function webKeys(pair) {
  return {
    privateKey: await crypto.webcrypto.subtle.importKey('pkcs8', pair.privateKey.export({ type: 'pkcs8', format: 'der' }), algorithm, true, ['sign']),
    publicKey: await crypto.webcrypto.subtle.importKey('spki', pair.publicKey.export({ type: 'spki', format: 'der' }), algorithm, true, ['verify']),
  };
}
function usages() { return [new x509.KeyUsagesExtension(x509.KeyUsageFlags.digitalSignature, true),
  new x509.ExtendedKeyUsageExtension(['1.3.6.1.5.5.7.3.3'], true)]; }
async function main() {
  const pair = signing.generateKeyPair(), other = signing.generateKeyPair();
  const keys = await webKeys(pair);
  const base = { serialNumber: '01', name: [{ CN: ['PhotoSpot 한글, Test'] }, { O: ['PhotoSpot'] }, { OU: ['TESTTEAM01'] }],
    notBefore: new Date(Date.now() - 3600000), notAfter: new Date(Date.now() + 3600000), keys, signingAlgorithm: algorithm, extensions: usages() };
  const cert = await x509.X509CertificateGenerator.createSelfSigned(base);
  const pem = cert.toString('pem'), parsed = signing.convertCertificatePEMToCertificate(pem);
  signing.validateSelfSignedCertificate(parsed, pair);
  const pems = signing.convertKeyPairToPEM(pair);
  assert.ok(signing.convertPrivateKeyPEMToPrivateKey(pems.privateKeyPEM).equals(pair.privateKey));
  const pkcs8 = pair.privateKey.export({ type: 'pkcs8', format: 'pem' });
  assert.ok(signing.convertPrivateKeyPEMToPrivateKey(pkcs8).equals(pair.privateKey));
  assert.equal(parsed.validity.notAfter.getTime(), cert.notAfter.getTime());
  assert.throws(() => signing.validateSelfSignedCertificate(parsed, other), /do not match/);
  assert.throws(() => signing.signBufferRSASHA256AndVerify(other.privateKey, parsed, Buffer.from('x')), /does not match/);
  for (const bad of [null, '', 'not a certificate', 'x'.repeat(65537)]) {
    assert.throws(() => signing.convertCertificatePEMToCertificate(bad));
    assert.throws(() => reader.pki.certificateFromPem(bad));
  }
  for (const options of [
    { notBefore: new Date(Date.now() - 7200000), notAfter: new Date(Date.now() - 3600000) },
    { notBefore: new Date(Date.now() + 7200000), notAfter: new Date(Date.now() + 10800000) },
    { extensions: [] },
    { extensions: [new x509.KeyUsagesExtension(x509.KeyUsageFlags.keyEncipherment, true)] },
    { extensions: [new x509.KeyUsagesExtension(x509.KeyUsageFlags.digitalSignature, true)] },
    { extensions: [new x509.KeyUsagesExtension(x509.KeyUsageFlags.digitalSignature, true), new x509.ExtendedKeyUsageExtension(['1.3.6.1.5.5.7.3.1'], true)] },
  ]) {
    const invalid = await x509.X509CertificateGenerator.createSelfSigned({ ...base, ...options });
    assert.throws(() => signing.validateSelfSignedCertificate(signing.convertCertificatePEMToCertificate(invalid.toString('pem')), pair));
  }
  const read = reader.pki.certificateFromPem(pem);
  assert.equal(read.subject.getField('CN').value, 'PhotoSpot 한글, Test');
  assert.equal(read.subject.getField('O').value, 'PhotoSpot');
  assert.equal(read.subject.getField('OU').value, 'TESTTEAM01');
  assert.equal(read.subject.getField('missing'), null);
  // Actual Expo iOS selection code, with only the macOS security command mocked.
  const securityFile = path.join(cliRoot, 'build/src/run/ios/codeSigning/Security.js');
  const nativeReq = createRequire(securityFile), mod = { exports: {} };
  vm.runInNewContext(fs.readFileSync(securityFile, 'utf8'), { module: mod, exports: mod.exports,
    require: name => name === '@expo/spawn-async' ? async (cmd, args) => {
      assert.equal(cmd, 'security'); assert.equal(args[0], 'find-certificate'); return { stdout: pem };
    } : nativeReq(name) }, { filename: securityFile });
  const identity = await mod.exports.resolveCertificateSigningInfoAsync('TESTTEAM01');
  assert.equal(identity.appleTeamId, 'TESTTEAM01');
  assert.equal(identity.appleTeamName, 'PhotoSpot');
  assert.equal(identity.codeSigningInfo, 'PhotoSpot 한글, Test');
  // CSR stays synchronous for the unmodified CLI and is independently verified.
  const cn = '한글, CN=literal + OU=literal';
  const csr = signing.generateCSR(pair, cn);
  assert.equal(csr.then, undefined);
  const decodedCSR = new x509.Pkcs10CertificateRequest(signing.convertCSRToCSRPEM(csr));
  assert.deepEqual(decodedCSR.subjectName.getField('CN'), [cn]);
  assert.deepEqual(decodedCSR.subjectName.getField('OU'), []);
  assert.equal(await decodedCSR.verify(), true);
  assert.throws(() => signing.generateCSR({ publicKey: pair.publicKey, privateKey: other.privateKey }, 'bad'), /does not match/);
  const tamperedCSR = Buffer.from(csr.rawData); tamperedCSR[tamperedCSR.length - 1] ^= 1;
  assert.equal(await new x509.Pkcs10CertificateRequest(tamperedCSR).verify(), false);

  const parent = fs.realpathSync(os.tmpdir()), dir = fs.mkdtempSync(path.join(parent, 'photospot-signing-'));
  try {
    const certPath = path.join(dir, 'cert.pem'), keyPath = path.join(dir, 'key.pem');
    fs.writeFileSync(certPath, pem); fs.writeFileSync(keyPath, pems.privateKeyPEM, { mode: 0o600 });
    const config = { updates: { codeSigningCertificate: certPath, codeSigningMetadata: { keyid: 'test', alg: 'rsa-v1_5-sha256' } } };
    const info = await cli.getCodeSigningInfoAsync(config, 'keyid="test", alg="rsa-v1_5-sha256"', keyPath);
    const payload = 'PhotoSpot manifest 한글 📷';
    const signature = Buffer.from(cli.signManifestString(payload, info), 'base64');
    assert.ok(crypto.verify('RSA-SHA256', Buffer.from(payload), pair.publicKey, signature));
    assert.ok(!crypto.verify('RSA-SHA256', Buffer.from(payload + 'tampered'), pair.publicKey, signature));
    assert.deepEqual(signature, crypto.sign('RSA-SHA256', Buffer.from(payload), pair.privateKey));
    await assert.rejects(cli.getCodeSigningInfoAsync(config, 'keyid="wrong"', keyPath), /keyid mismatch/);
    fs.writeFileSync(keyPath, signing.convertKeyPairToPEM(other).privateKeyPEM);
    await assert.rejects(cli.getCodeSigningInfoAsync(config, 'keyid="test"', keyPath), /do not match/);

    // Exercise the actual Expo Go online CSR exchange and offline cache paths.
    // External account/certificate services are test doubles, never contacted.
    const rootCert = await x509.X509CertificateGenerator.createSelfSigned({ ...base, name: 'CN=Test Root',
      extensions: [new x509.BasicConstraintsExtension(true, undefined, true),
        new x509.KeyUsagesExtension(x509.KeyUsageFlags.keyCertSign, true)] });
    const projectId = '00000000-0000-4000-8000-000000000001', scopeKey = '@test/photospot';
    const env = { EXPO_OFFLINE: false };
    let exchanges = 0;
    const signingFile = path.join(cliRoot, 'build/src/utils/codesigning.js');
    const localRequire = createRequire(signingFile), testModule = { exports: {} };
    const substitutes = {
      './env': { env },
      '../api/user/UserSettings': { getExpoHomeDirectory: () => dir },
      '../api/user/actions': { tryGetUserAsync: async () => ({ __typename: 'User', primaryAccount: { id: 'test-account' }, accounts: [] }) },
      '../api/graphql/queries/AppQuery': { AppQuery: { byIdAsync: async id => {
        assert.equal(id, projectId); return { ownerAccount: { id: 'test-account' }, scopeKey };
      } } },
      '../api/getProjectDevelopmentCertificate': { getProjectDevelopmentCertificateAsync: async (id, csrPEM) => {
        assert.equal(id, projectId); exchanges++;
        const request = new x509.Pkcs10CertificateRequest(csrPEM);
        assert.equal(await request.verify(), true);
        const leaf = await x509.X509CertificateGenerator.create({ subject: request.subject, issuer: rootCert.subject,
          publicKey: request.publicKey, signingKey: keys.privateKey, signingAlgorithm: algorithm,
          notBefore: base.notBefore, notAfter: base.notAfter, serialNumber: '02', extensions: usages() });
        return leaf.toString('pem');
      } },
      '../api/getExpoGoIntermediateCertificate': { getExpoGoIntermediateCertificateAsync: async () => rootCert.toString('pem') },
    };
    vm.runInNewContext(fs.readFileSync(signingFile, 'utf8'), { module: testModule, exports: testModule.exports,
      Buffer, require: name => substitutes[name] || localRequire(name) }, { filename: signingFile });
    const developmentCli = testModule.exports;
    const exp = { extra: { eas: { projectId } } };
    const online = await developmentCli.getCodeSigningInfoAsync(exp, 'keyid="expo-root"');
    assert.equal(exchanges, 1); assert.equal(online.scopeKey, scopeKey);
    assert.equal(online.certificateChainForResponse.length, 2);
    const leaf = new crypto.X509Certificate(online.certificateForPrivateKey);
    assert.equal(leaf.verify(pair.publicKey), true);
    assert.equal(leaf.verify(other.publicKey), false);
    assert.equal(crypto.verify('RSA-SHA256', Buffer.from('development'), leaf.publicKey,
      Buffer.from(developmentCli.signManifestString('development', online), 'base64')), true);
    env.EXPO_OFFLINE = true;
    const cached = await developmentCli.getCodeSigningInfoAsync(exp, 'keyid="expo-root"');
    assert.equal(cached.privateKey, online.privateKey); assert.equal(exchanges, 1);
    const expired = await x509.X509CertificateGenerator.createSelfSigned({ ...base,
      notBefore: new Date(Date.now() - 7200000), notAfter: new Date(Date.now() - 3600000) });
    await developmentCli.DevelopmentCodeSigningInfoFile.setAsync(projectId, { certificateChain: [expired.toString('pem'), rootCert.toString('pem')] });
    assert.equal(await developmentCli.getCodeSigningInfoAsync(exp, 'keyid="expo-root"'), null);
  } finally {
    const target = fs.realpathSync(dir);
    assert.equal(path.dirname(target), parent); assert.ok(path.basename(target).startsWith('photospot-signing-'));
    fs.rmSync(target, { recursive: true, force: true });
  }
  // Regression for the removed verifier's advisory: a mathematically signed but
  // malformed DigestAlgorithm (extra SEQUENCE child) must not verify as a cert.
  const asn = AsnConvert.parse(cert.rawData, Certificate);
  const digest = crypto.createHash('sha256').update(Buffer.from(AsnConvert.serialize(asn.tbsCertificate))).digest();
  const digestInfo = Buffer.concat([Buffer.from('3033300f0609608648016503040201050030000420', 'hex'), digest]);
  const encoded = Buffer.concat([Buffer.from([0, 1]), Buffer.alloc(256 - digestInfo.length - 3, 255), Buffer.from([0]), digestInfo]);
  asn.signatureValue = Uint8Array.from(crypto.privateEncrypt({ key: pair.privateKey, padding: crypto.constants.RSA_NO_PADDING }, encoded)).buffer;
  const malformed = x509.PemConverter.encode(AsnConvert.serialize(asn), 'CERTIFICATE');
  const badCertificate = signing.convertCertificatePEMToCertificate(malformed);
  assert.equal(badCertificate.native.verify(pair.publicKey), false);
  assert.throws(() => signing.validateSelfSignedCertificate(badCertificate, pair), /self-signed/);
  console.log('Expo manifest/CSR/iOS identity integration, key formats, validity/usages, mismatched keys, tampering and malformed RSA DigestAlgorithm rejection passed.');
}
main().catch(e => { console.error(e); process.exitCode = 1; });
