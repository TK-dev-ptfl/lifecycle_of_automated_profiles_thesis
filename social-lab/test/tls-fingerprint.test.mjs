import { test } from 'node:test';
import assert from 'node:assert/strict';
import tls from 'node:tls';
import net from 'node:net';
import { extractClientHello, fingerprintHello, ja4, _internal } from '../server/tls-fingerprint.mjs';

test('JA4 cipher hash matches the FoxIO specification example', () => {
  const sorted = '002f,0035,009c,009d,1301,1302,1303,c013,c014,c02b,c02c,c02f,c030,cca8,cca9';
  assert.equal(_internal.sha12(sorted), '8daaf6152771');
});

test('JA4 extension hash matches both FoxIO specification examples', () => {
  const ext = '0005,000a,000b,000d,0012,0015,0017,001b,0023,002b,002d,0033,4469,ff01';
  assert.equal(_internal.sha12(`${ext}_0403,0804,0401,0503,0805,0501,0806,0601`), 'e5627efa2ab1');
  assert.equal(_internal.sha12(ext), '6d807ffa2a79');
});

test('ALPN code follows the specification table, including non-alphanumeric bytes', () => {
  const b = (...x) => [Buffer.from(x)];
  assert.equal(_internal.alpnCode([Buffer.from('h2')]), 'h2');
  assert.equal(_internal.alpnCode([Buffer.from('http/1.1')]), 'h1');
  assert.equal(_internal.alpnCode([]), '00');
  assert.equal(_internal.alpnCode(b(0xab)), 'ab');
  assert.equal(_internal.alpnCode(b(0xab, 0xcd)), 'ad');
  assert.equal(_internal.alpnCode(b(0x30, 0xab)), '3b');
  assert.equal(_internal.alpnCode(b(0x30, 0xab, 0xcd, 0x31)), '01');
});

test('GREASE values are recognised and only those', () => {
  for (const v of [0x0a0a, 0x1a1a, 0xfafa]) assert.ok(_internal.isGrease(v));
  for (const v of [0x0a1a, 0x1301, 0x0000, 0xff01]) assert.ok(!_internal.isGrease(v));
});

test('the specification worked example reproduces from parsed fields', () => {
  const ciphers = [0x1301, 0x1302, 0x1303, 0xc02b, 0xc02f, 0xc02c, 0xc030, 0xcca9, 0xcca8, 0xc013, 0xc014, 0x009c, 0x009d, 0x002f, 0x0035];
  const extensions = [0x0000, 0x0010, 0x0005, 0x000a, 0x000b, 0x000d, 0x0012, 0x0015, 0x0017, 0x001b, 0x0023, 0x002b, 0x002d, 0x0033, 0x4469, 0xff01];
  const fp = ja4({
    legacyVersion: 0x0303, ciphers: [0x0a0a, ...ciphers], extensions: [0x1a1a, ...extensions], sni: 'example.com',
    alpn: [Buffer.from('h2')], supportedVersions: [0x2a2a, 0x0304, 0x0303],
    sigAlgs: [0x0403, 0x0804, 0x0401, 0x0503, 0x0805, 0x0501, 0x0806, 0x0601],
  });
  assert.equal(fp.ja4, 't13d1516h2_8daaf6152771_e5627efa2ab1');
});

test('a real ClientHello from Node is captured whole and fingerprinted', async () => {
  const chunks = [];
  const server = net.createServer(sock => { sock.on('data', d => { chunks.push(d); sock.destroy(); }); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const { port } = server.address();
  await new Promise(resolve => {
    const c = tls.connect({ host: '127.0.0.1', port, servername: 'social-lab.test', ALPNProtocols: ['h2', 'http/1.1'] });
    c.on('error', resolve); c.on('close', resolve);
  });
  server.close();
  const buf = Buffer.concat(chunks);
  const { done, hello } = extractClientHello(buf);
  assert.ok(done && hello, 'ClientHello extracted');
  const fp = fingerprintHello(hello);
  assert.match(fp.ja4, /^t13d\d{4}h2_[0-9a-f]{12}_[0-9a-f]{12}$/);
  assert.match(fp.ja3, /^[0-9a-f]{32}$/);
  assert.deepEqual(fp.alpn, ['h2', 'http/1.1']);
  assert.ok(fp.sni_present);
});

test('a ClientHello split across TCP segments waits for the rest', () => {
  const hello = Buffer.alloc(300); hello[0] = 0x01; hello.writeUIntBE(296, 1, 3);
  const record = Buffer.concat([Buffer.from([0x16, 0x03, 0x01, 0x01, 0x2c]), hello]);
  assert.deepEqual(extractClientHello(record.subarray(0, 100)), { done: false });
  const whole = extractClientHello(record);
  assert.ok(whole.done && whole.hello.length === 300);
});

test('plain HTTP on the TLS port is passed through, not parsed', () => {
  assert.deepEqual(extractClientHello(Buffer.from('GET / HTTP/1.1\r\n')), { done: true, hello: null });
});
