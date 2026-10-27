// Runs in a dedicated worker and in a shared worker. Reports what the browser
// says about itself from a background thread, where page-level overrides
// (DevTools emulation, injected scripts) often do not reach. A disagreement
// with the page is a fingerprint inconsistency (Venugopalan et al. 2024).
const report = () => {
  let gpu = '';
  try {
    const gl = new OffscreenCanvas(1, 1).getContext('webgl');
    const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
    gpu = gl ? (ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)) : '';
  } catch (e) { /* no WebGL in workers here */ }
  return {
    ua: navigator.userAgent, cores: navigator.hardwareConcurrency, memory: navigator.deviceMemory ?? null,
    languages: (navigator.languages || []).join(','), platform: navigator.platform, gpu,
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
  };
};
if (typeof SharedWorkerGlobalScope !== 'undefined' && self instanceof SharedWorkerGlobalScope) {
  self.onconnect = e => e.ports[0].postMessage(report());
} else {
  postMessage(report());
}
