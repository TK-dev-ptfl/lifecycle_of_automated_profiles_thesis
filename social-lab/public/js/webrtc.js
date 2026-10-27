// Optional (WEBRTC_CHECK=1): does WebRTC reveal a different public address
// than the one the page was loaded from? A STUN request goes directly to the
// STUN server, not through an HTTP proxy, so a proxied visitor usually shows a
// mismatch. Among human participants this measures how often the signal fires
// for ordinary reasons (VPN users, split tunnelling, IPv4 vs IPv6) - its
// false-positive rate. Addresses never leave the browser: only salted
// HMAC-SHA-256 hashes are sent, and the server stores only the yes/no outcome.

async function hmac(salt, text) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(salt), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(text));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, '0')).join('');
}

export async function webrtcCheck({ salt, endpoint, token }) {
  let status = 'ok';
  const addrs = new Set();
  try {
    const pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] });
    pc.createDataChannel('probe');
    pc.onicecandidate = e => {
      const c = e.candidate && e.candidate.candidate;
      const m = c && c.match(/ ((?:\d{1,3}\.){3}\d{1,3}|[0-9a-f:]+:[0-9a-f:]+) \d+ typ srflx/i);
      if (m) addrs.add(m[1]);
    };
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise(r => setTimeout(r, 3000));
    pc.close();
    if (!addrs.size) status = 'no-srflx-candidate';
  } catch { status = 'unavailable'; }
  const hashes = await Promise.all([...addrs].map(a => hmac(salt, a)));
  await fetch(endpoint, { method: 'POST', headers: { 'content-type': 'application/json', 'x-session-token': token },
    body: JSON.stringify({ hashes, status }) }).catch(() => null);
}
