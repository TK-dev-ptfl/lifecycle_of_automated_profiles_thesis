// Device snapshot: what the browser and machine report about themselves, taken
// once per session. Two uses (docs/DATA_DICTIONARY.md, section "Hardware"):
//   1. the real joint distribution of these attributes, so generated
//      fingerprints can be sampled as whole, coherent machines rather than
//      independent random values (Laperdrix et al. 2016; Gomez-Boix et al. 2018);
//   2. the base rate of each consistency check among real people - how often
//      a human trips a check is that check's false-positive rate
//      (Venugopalan et al. 2024).

const safe = async (fn, fallback = null) => { try { return await fn(); } catch { return fallback; } };

function webgl() {
  const c = document.createElement('canvas');
  const gl = c.getContext('webgl');
  if (!gl) return { available: false };
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  return {
    available: true,
    vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
    renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
    max_texture: gl.getParameter(gl.MAX_TEXTURE_SIZE),
    webgl2: !!document.createElement('canvas').getContext('webgl2'),
  };
}

function worker(kind) {
  return new Promise(resolve => {
    let w; const done = v => { try { w && (w.terminate ? w.terminate() : w.port.close()); } catch { /* gone */ } resolve(v); };
    try {
      if (kind === 'shared') {
        if (!window.SharedWorker) return done({ available: false });
        w = new SharedWorker('/js/probe-worker.js', { name: 'probe-' + Math.random() });
        w.port.onmessage = e => done(e.data); w.port.start();
      } else {
        w = new Worker('/js/probe-worker.js');
        w.onmessage = e => done(e.data);
      }
      w.onerror = () => done({ available: false, error: true });
      setTimeout(() => done({ available: false, timeout: true }), 2000);
    } catch { done({ available: false }); }
  });
}

const isNative = f => { try { return /\{\s*\[native code\]\s*\}\s*$/.test(Function.prototype.toString.call(f)); } catch { return false; } };

function canvasDraw() {
  const c = document.createElement('canvas'); c.width = 200; c.height = 40;
  const x = c.getContext('2d'); if (!x) return '';
  x.textBaseline = 'top'; x.font = '15px Arial'; x.fillStyle = '#f60'; x.fillRect(90, 1, 60, 20);
  x.fillStyle = '#069'; x.fillText('Social Lab 1.0 ✓', 2, 15);
  return c.toDataURL();
}

const mq = q => matchMedia(q).matches;

export async function snapshot() {
  const nav = navigator;
  const uaData = nav.userAgentData;
  const high = await safe(() => uaData?.getHighEntropyValues(['platform', 'platformVersion', 'architecture', 'bitness', 'model', 'fullVersionList', 'wow64']));
  const gl = await safe(webgl, { available: false });
  const [dedicated, shared] = await Promise.all([worker('dedicated'), worker('shared')]);
  const langs = [...(nav.languages || [])];

  const iframe = await safe(() => {
    const f = document.createElement('iframe'); f.style.display = 'none'; document.body.appendChild(f);
    const n = f.contentWindow.navigator;
    const out = { ua: n.userAgent === nav.userAgent, languages: (n.languages || []).join() === langs.join(),
      cores: n.hardwareConcurrency === nav.hardwareConcurrency, platform: n.platform === nav.platform, webdriver: !!n.webdriver === !!nav.webdriver };
    f.remove(); return out;
  });

  const leftovers = ['__playwright__binding__', '__pwInitScripts', '_playwrightInstance', '__puppeteer_evaluation_script__',
    'callPhantom', '_phantom', '__nightmare', 'domAutomation', 'domAutomationController', '_selenium', '__selenium_unwrapped',
    '__webdriver_evaluate', '__driver_evaluate', '__webdriver_script_fn', '__fxdriver_unwrapped', 'Cypress']
    .filter(k => { try { return k in window; } catch { return false; } });
  try { for (const k of Object.getOwnPropertyNames(window)) if (/^\$?cdc_|^__pw/i.test(k)) leftovers.push(k); } catch { /* ignore */ }

  const tampered = [];
  if (!isNative(Function.prototype.toString)) tampered.push('Function.prototype.toString');
  for (const p of ['webdriver', 'userAgent', 'platform', 'languages', 'plugins', 'hardwareConcurrency', 'deviceMemory', 'vendor']) {
    const d = Object.getOwnPropertyDescriptor(Navigator.prototype, p);
    if (d && d.get && !isNative(d.get)) tampered.push('navigator.' + p);
  }
  for (const [o, k] of [[HTMLCanvasElement.prototype, 'toDataURL'], [HTMLCanvasElement.prototype, 'getContext'],
    [window.WebGLRenderingContext && WebGLRenderingContext.prototype, 'getParameter']]) if (o && o[k] && !isNative(o[k])) tampered.push(k);

  const permission = await safe(async () => {
    const st = await nav.permissions.query({ name: 'notifications' });
    return { notification: window.Notification ? Notification.permission : null, query: st.state };
  });

  const media = await safe(async () => {
    // Only how many of each kind exist - labels and ids need permission and
    // are not asked for.
    const d = await nav.mediaDevices.enumerateDevices();
    const n = k => d.filter(x => x.kind === k).length;
    return { audioinput: n('audioinput'), audiooutput: n('audiooutput'), videoinput: n('videoinput') };
  });

  let botd = null;
  try {
    const { load } = await import('/vendor/botd/botd.esm.js');
    const b = await load();
    const r = b.detect();
    botd = { bot: r.bot, kind: r.botKind || null,
      detectors: Object.entries(b.getDetections() || {}).filter(([, d]) => d.bot).map(([k]) => k) };
  } catch (e) { botd = { error: String(e && e.message || e).slice(0, 120) }; }

  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const c1 = canvasDraw(), c2 = canvasDraw();
  const conn = nav.connection;

  return {
    taken_at: Date.now(),
    browser: {
      user_agent: nav.userAgent, ua_brands: uaData ? uaData.brands : null, ua_mobile: uaData ? uaData.mobile : null,
      ua_platform: uaData ? uaData.platform : null, ua_high_entropy: high,
      platform: nav.platform, vendor: nav.vendor, languages: langs, language: nav.language,
      cookies: nav.cookieEnabled, pdf_viewer: nav.pdfViewerEnabled ?? null, plugins: nav.plugins ? nav.plugins.length : null,
      do_not_track: nav.doNotTrack ?? null, gpc: nav.globalPrivacyControl ?? null,
    },
    machine: {
      cores: nav.hardwareConcurrency ?? null, memory_gb: nav.deviceMemory ?? null, touch_points: nav.maxTouchPoints ?? 0,
      screen: { w: screen.width, h: screen.height, avail_w: screen.availWidth, avail_h: screen.availHeight,
        color_depth: screen.colorDepth, pixel_depth: screen.pixelDepth, orientation: screen.orientation?.type || null },
      dpr: devicePixelRatio, inner: [innerWidth, innerHeight], outer: [outerWidth, outerHeight],
      webgl: gl, media_devices: media,
    },
    input_capabilities: {
      // Media queries: what kind of pointing device the system reports.
      // "fine + hover" is a mouse or trackpad; "coarse" is touch.
      pointer_fine: mq('(pointer: fine)'), pointer_coarse: mq('(pointer: coarse)'), any_pointer_coarse: mq('(any-pointer: coarse)'),
      hover: mq('(hover: hover)'), any_hover: mq('(any-hover: hover)'),
    },
    preferences: {
      color_scheme_dark: mq('(prefers-color-scheme: dark)'), reduced_motion: mq('(prefers-reduced-motion: reduce)'),
      contrast_more: mq('(prefers-contrast: more)'), forced_colors: mq('(forced-colors: active)'),
    },
    locale: { timezone: tz, utc_offset_min: -new Date().getTimezoneOffset(), number_format: new Intl.NumberFormat().resolvedOptions().locale },
    connection: conn ? { effective_type: conn.effectiveType, rtt: conn.rtt, downlink: conn.downlink, save_data: conn.saveData } : null,
    consistency: {
      worker_dedicated: dedicated, worker_shared: shared, iframe,
      worker_matches: dedicated && dedicated.ua ? {
        ua: dedicated.ua === nav.userAgent, cores: dedicated.cores === nav.hardwareConcurrency,
        languages: dedicated.languages === langs.join(','), platform: dedicated.platform === nav.platform,
        gpu: !dedicated.gpu || !gl.renderer || dedicated.gpu === gl.renderer, tz: dedicated.tz === tz,
      } : null,
      shared_worker_matches: shared && shared.ua ? {
        ua: shared.ua === nav.userAgent, gpu: !shared.gpu || !gl.renderer || shared.gpu === gl.renderer,
      } : null,
      canvas_stable: c1 === c2,
      permission,
    },
    automation: {
      webdriver: !!nav.webdriver, leftovers, tampered,
      headless_ua: /Headless/i.test(nav.userAgent),
      chrome_object: !!window.chrome,
      botd,
    },
  };
}
