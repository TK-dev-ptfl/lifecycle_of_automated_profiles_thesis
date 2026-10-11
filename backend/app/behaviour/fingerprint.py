"""The browser an identity appears to use, and how to make a real browser present it.

A BehaviourProfile is how a person moves; a Fingerprint is what their machine
says about itself - browser, screen, GPU, language, time zone. Both are derived
from the identity key, so the same identity always shows up on the same machine
and two identities do not share one.

Two rules decide everything below:

1. Coherent beats random. A fingerprint whose parts disagree - a macOS user
   agent next to a Win32 platform, an Apple GPU on Windows, 16 GB of memory in a
   browser that caps the value at 8 - is worse than the host's real one,
   because the disagreement itself is the signal. The pools are the ones the
   Identities page draws from, but combinations are picked to fit together,
   and values are written the way the real browser on that OS reports them.

2. Only claim what the engine can back up everywhere. A page sees the
   browser through the main frame, every iframe (including cross-origin ones
   like reCAPTCHA's) and every worker, and checking that they agree is cheap.
   That leads to three choices:

   - The browser is real. An Edge identity runs in installed Edge and a Chrome
     identity in installed Chrome, so brands, version and engine quirks are
     genuine instead of re-labelled.
   - The OS, core count and memory are the host's. A worker reports them
     natively and DevTools cannot override them there, so a different value in
     the page would contradict the worker. The same goes for the fonts, which
     give the real OS away regardless.
   - Everything else - screen, scale, viewport, GPU strings, colour depth,
     canvas noise, languages, time zone - is varied per identity, through
     launch flags and Playwright's emulation where those exist, or else through
     a page patch that installs in every frame and replaces nothing visibly
     (Proxies around the native functions still stringify as native code).
"""
from __future__ import annotations

import hashlib
import json
import platform as host_platform
import random
from dataclasses import asdict, dataclass, replace
from typing import Any, Optional

# --- pools -----------------------------------------------------------------

# Country -> (locale, languages, IANA zone). Mirrors COUNTRIES on the
# Identities page; the locale is the first language with its region attached,
# which is what a browser installed in that country sends first.
COUNTRIES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "SK": ("sk-SK", ("sk", "cs", "en"), "Europe/Bratislava"),
    "CZ": ("cs-CZ", ("cs", "sk", "en"), "Europe/Prague"),
    "DE": ("de-DE", ("de", "en"), "Europe/Berlin"),
    "US": ("en-US", ("en",), "America/New_York"),
    "GB": ("en-GB", ("en",), "Europe/London"),
    "FR": ("fr-FR", ("fr", "en"), "Europe/Paris"),
    "PL": ("pl-PL", ("pl", "en"), "Europe/Warsaw"),
    "AT": ("de-AT", ("de", "en"), "Europe/Vienna"),
    "HU": ("hu-HU", ("hu", "en"), "Europe/Budapest"),
    "NL": ("nl-NL", ("nl", "en"), "Europe/Amsterdam"),
}

# (browser, Playwright channel, weight) per OS. The Chromium-family rows of the
# Identities page's HW_COMBOS: Firefox and Safari are left out because the
# driver is Chromium-only here, and claiming them from Blink fails every engine
# check there is.
_BROWSERS: dict[str, list[tuple[str, str, int]]] = {
    "Windows": [("Chrome", "chrome", 7), ("Edge", "msedge", 3)],
    "macOS": [("Chrome", "chrome", 9), ("Edge", "msedge", 1)],
    "Linux": [("Chrome", "chrome", 1)],
}

# Physical resolution and the scale factor that goes with it. CSS screen size
# is physical / scale, which is what screen.width reports on a real machine:
# a 1920x1080 laptop at 125% says 1536x864, not 1920x1080.
_SCREENS: dict[str, list[tuple[int, int, float]]] = {
    "Windows": [
        (1920, 1080, 1.0), (1920, 1080, 1.0), (1920, 1080, 1.25), (2560, 1440, 1.0),
        (2560, 1440, 1.25), (1366, 768, 1.0), (1440, 900, 1.0), (1680, 1050, 1.0),
        (1920, 1200, 1.0), (1280, 800, 1.0),
    ],
    "macOS": [(2560, 1600, 2.0), (2880, 1800, 2.0), (3024, 1964, 2.0), (2560, 1440, 2.0)],
    "Linux": [(1920, 1080, 1.0), (2560, 1440, 1.0), (1920, 1200, 1.0), (1366, 768, 1.0)],
}

# GPUs from the Identities page's WEBGL pool, in the form Chrome's ANGLE
# backend reports them on each OS. Chrome on Windows never reports the bare
# "NVIDIA GeForce RTX 3060/PCIe/SSE2" form; that is a Linux GL driver string.
_GPUS: dict[str, list[tuple[str, str]]] = {
    "Windows": [
        ("Google Inc. (Intel)",
         "ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00005917) Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (Intel)",
         "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x00009A49) Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (NVIDIA)",
         "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (AMD)",
         "ANGLE (AMD, AMD Radeon RX 6600 XT (0x000073FF) Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (Intel)",
         "ANGLE (Intel, Intel(R) HD Graphics 4000 (0x00000166) Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ],
    "macOS": [
        ("Google Inc. (Apple)", "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)"),
        ("Google Inc. (Apple)", "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)"),
    ],
    "Linux": [
        ("Google Inc. (Intel)", "ANGLE (Intel, Mesa Intel(R) UHD Graphics 620 (KBL GT2), OpenGL 4.6)"),
        ("Google Inc. (NVIDIA Corporation)",
         "ANGLE (NVIDIA Corporation, NVIDIA GeForce RTX 3060/PCIe/SSE2, OpenGL 4.5.0)"),
    ],
}

# What each OS takes from the screen before the browser gets it, and what the
# browser's own toolbars take from the window. Together they turn a screen size
# into a believable window and viewport: a viewport as tall as the screen is a
# browser with no tabs, no address bar and no taskbar underneath it.
_TASKBAR_PX = {"Windows": 48, "macOS": 25, "Linux": 32}
_BROWSER_UI_PX = (85, 125)


def host_os() -> str:
    """The OS family of the machine the browser will actually run on."""
    system = host_platform.system()
    return {"Windows": "Windows", "Darwin": "macOS"}.get(system, "Linux")


@dataclass(frozen=True)
class Fingerprint:
    """One machine and browser, as an identity presents it."""

    os: str
    browser: str
    channel: str
    # Physical pixels and scale; screen_* are what the page sees, in CSS px.
    physical_width: int
    physical_height: int
    pixel_ratio: float
    screen_width: int
    screen_height: int
    viewport_width: int
    viewport_height: int
    color_depth: int
    webgl_vendor: str
    webgl_renderer: str
    canvas_seed: int
    country_code: str
    locale: str
    languages: tuple[str, ...]
    timezone: str
    # Filled in by bind() from the browser actually launched. Cores and memory
    # are the host's: see the module docstring for why they cannot be varied.
    user_agent: str = ""
    browser_version: str = ""
    hardware_concurrency: int = 0
    device_memory: float = 0

    # --- derived -----------------------------------------------------------
    @property
    def language_tags(self) -> tuple[str, ...]:
        """['sk-SK', 'sk', 'cs', 'en-US', 'en'] from sk-SK and (sk, cs, en): the
        shape Chrome builds from its language settings."""
        tags: list[str] = [self.locale]
        for lang in self.languages:
            if lang == "en" and "en-US" not in tags and not self.locale.startswith("en"):
                tags.append("en-US")
            if lang not in tags:
                tags.append(lang)
        return tuple(tags)

    @property
    def window_size(self) -> tuple[int, int]:
        """Outer window size for a headed browser: the viewport plus toolbars,
        so outerHeight - innerHeight looks like a real browser frame."""
        chrome_ui = self.screen_height - _TASKBAR_PX[self.os] - self.viewport_height
        return self.viewport_width, self.viewport_height + max(chrome_ui, 0)

    def summary(self) -> dict:
        """What the dashboard shows: the parts a person would recognise."""
        major = self.browser_version.split(".")[0]
        summary = {
            "browser": f"{self.browser} {major}".strip(),
            "os": self.os,
            "screen": f"{self.screen_width}x{self.screen_height} @{self.pixel_ratio:g}x",
            "viewport": f"{self.viewport_width}x{self.viewport_height}",
            "gpu": self.webgl_renderer,
            "cores": self.hardware_concurrency or None,
            "memory_gb": self.device_memory or None,
            "languages": list(self.language_tags),
            "timezone": self.timezone,
            "user_agent": self.user_agent or None,
        }
        # Unknowns are left out rather than shown as None: deviceMemory, for
        # one, is only exposed to secure pages and may not have been readable.
        return {k: v for k, v in summary.items() if v is not None}

    def as_dict(self) -> dict:
        return asdict(self)

    def bind(self, real: dict) -> "Fingerprint":
        """This fingerprint completed with what the launched browser really is.

        The user agent is the browser's own, with the one word headless mode
        adds removed - nothing else about it is invented, so it can never drift
        from the engine's actual version.
        """
        return replace(
            self,
            user_agent=(real.get("ua") or "").replace("HeadlessChrome/", "Chrome/"),
            browser_version=real.get("version") or "",
            hardware_concurrency=int(real.get("cores") or 0),
            device_memory=float(real.get("memory") or 0),
        )

    def page_script(self) -> str:
        """JS run in every frame before the page's own scripts: the values no
        launch flag or emulation setting reaches. See _PAGE_SCRIPT."""
        config = {
            "webglVendor": self.webgl_vendor,
            "webglRenderer": self.webgl_renderer,
            "canvasSeed": self.canvas_seed,
            "colorDepth": self.color_depth,
        }
        return _PAGE_SCRIPT.replace("__CONFIG__", json.dumps(config))


def fingerprint_for(
    identity_key: str,
    country_code: Optional[str] = None,
    os_name: Optional[str] = None,
) -> Fingerprint:
    """A stable, distinct, internally consistent fingerprint for one identity.

    Seeded from the identity key the way derive_for() seeds the behaviour
    profile, but salted so the two are not correlated: the same identity always
    gets the same machine, and its typing speed says nothing about its screen.
    """
    digest = hashlib.sha256(f"fingerprint:{identity_key}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))

    os_name = os_name or host_os()
    browsers = _BROWSERS[os_name]
    browser, channel, _ = rng.choices(browsers, weights=[b[2] for b in browsers])[0]
    cc = (country_code or rng.choice(sorted(COUNTRIES))).upper()
    locale, languages, timezone = COUNTRIES.get(cc, COUNTRIES["US"])

    phys_w, phys_h, dpr = rng.choice(_SCREENS[os_name])
    screen_w, screen_h = round(phys_w / dpr), round(phys_h / dpr)
    viewport_h = screen_h - _TASKBAR_PX[os_name] - rng.randint(*_BROWSER_UI_PX)
    # Most people run the browser maximised; some leave it a little narrower.
    viewport_w = screen_w if rng.random() < 0.7 else screen_w - rng.randint(40, 220)
    vendor, renderer = rng.choice(_GPUS[os_name])

    return Fingerprint(
        os=os_name,
        browser=browser,
        channel=channel,
        physical_width=phys_w,
        physical_height=phys_h,
        pixel_ratio=dpr,
        screen_width=screen_w,
        screen_height=screen_h,
        viewport_width=viewport_w,
        viewport_height=viewport_h,
        # Chrome reports 24 for nearly every display and 30 on Apple's
        # wide-gamut panels; 32, which the Identities page can pick, is a
        # Firefox value Chrome never reports.
        color_depth=30 if os_name == "macOS" else 24,
        webgl_vendor=vendor,
        webgl_renderer=renderer,
        canvas_seed=int.from_bytes(digest[8:12], "big"),
        country_code=cc,
        locale=locale,
        languages=languages,
        timezone=timezone,
    )


# --- applying it -------------------------------------------------------------

# Playwright adds --enable-automation, which shows the "controlled by automated
# test software" bar and switches on automation-only behaviour.
IGNORE_DEFAULT_ARGS = ["--enable-automation"]


def launch_args(fp: Fingerprint, headless: bool) -> list[str]:
    """Browser flags for this fingerprint.

    AutomationControlled is what sets navigator.webdriver: turning the feature
    off removes the flag natively, where overriding the getter would itself be
    detectable. Languages go in as flags rather than Playwright's `locale`,
    because the flag is the browser's own setting and so reaches workers too;
    `locale` only reaches documents, leaving workers on en-US.
    """
    args = [
        "--disable-blink-features=AutomationControlled",
        f"--lang={fp.locale}",
        f"--accept-lang={','.join(fp.language_tags)}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if not headless:
        w, h = fp.window_size
        args.append(f"--window-size={w},{h}")
    return args


def context_options(fp: Fingerprint) -> dict[str, Any]:
    """Playwright new_context() options: viewport, screen, scale, zone, agent."""
    options: dict[str, Any] = {
        "viewport": {"width": fp.viewport_width, "height": fp.viewport_height},
        "screen": {"width": fp.screen_width, "height": fp.screen_height},
        "device_scale_factor": fp.pixel_ratio,
        "timezone_id": fp.timezone,
        "color_scheme": "light",
    }
    if fp.user_agent:
        options["user_agent"] = fp.user_agent
    return options


async def launch(pw, fp: Fingerprint, *, headless: bool, log=lambda _m: None):
    """Launches the browser this fingerprint claims, falling back to Playwright's
    bundled Chromium when that browser is not installed - in which case the
    fingerprint is re-labelled Chrome, since Chromium cannot pass for Edge."""
    kwargs = {
        "headless": headless,
        "args": launch_args(fp, headless),
        "ignore_default_args": IGNORE_DEFAULT_ARGS,
    }
    try:
        return await pw.chromium.launch(channel=fp.channel, **kwargs), fp
    except Exception as exc:
        log(f"{fp.browser} not available ({type(exc).__name__}); using bundled Chromium")
        fp = replace(fp, browser="Chrome", channel="chromium")
        return await pw.chromium.launch(**kwargs), fp


async def read_real_browser(browser) -> dict:
    """The launched browser's own user agent, version, cores and memory, read
    from a scratch context with no overrides in it."""
    context = await browser.new_context()
    try:
        page = await context.new_page()
        real = await page.evaluate(
            """async () => {
                const d = navigator.userAgentData;
                const hi = d ? await d.getHighEntropyValues(['uaFullVersion']) : {};
                return { ua: navigator.userAgent, version: hi.uaFullVersion || '',
                         cores: navigator.hardwareConcurrency, memory: navigator.deviceMemory };
            }"""
        )
    finally:
        await context.close()
    real["version"] = real.get("version") or browser.version
    return real


async def new_context(browser, fp: Fingerprint, *, show_cursor: bool = False):
    """A context presenting `fp` (already bound), with the page patch installed
    in every frame of every page it will open.

    show_cursor draws the simulated pointer, which is otherwise invisible: input
    sent through DevTools reaches the page but never moves the OS cursor. It is
    for watching a run, never for real targets - the overlay is an element in
    the page, which any site can find.
    """
    context = await browser.new_context(**context_options(fp))
    await context.add_init_script(fp.page_script())
    if show_cursor:
        await context.add_init_script(CURSOR_OVERLAY_SCRIPT)
    return context


# Debug overlay: a dot that follows the pointer, a fading trail behind it, and
# a ring on each press. Driven by the page's own mouse events, so it shows
# exactly what the page received. Top frame only, and pointer-events: none, so
# it can never be what a click lands on.
CURSOR_OVERLAY_SCRIPT = r"""
(() => {
  if (window.top !== window) return;
  const start = () => {
    const host = document.createElement('div');
    host.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647';
    const root = host.attachShadow({ mode: 'closed' });
    root.innerHTML = `<style>
      canvas{position:fixed;inset:0;width:100vw;height:100vh}
      .dot{position:fixed;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;
           background:rgba(239,68,68,.9);box-shadow:0 0 0 2px #fff,0 1px 6px rgba(0,0,0,.4);
           transition:transform .08s;left:-50px;top:-50px}
      .dot.down{transform:scale(.6);background:rgba(37,99,235,.95)}
      .ring{position:fixed;width:30px;height:30px;margin:-15px 0 0 -15px;border-radius:50%;
            border:2px solid rgba(37,99,235,.9);animation:r .5s ease-out forwards}
      @keyframes r{from{transform:scale(.3);opacity:1}to{transform:scale(1.6);opacity:0}}
    </style><canvas></canvas><div class="dot"></div>`;
    document.documentElement.appendChild(host);
    const canvas = root.querySelector('canvas'), dot = root.querySelector('.dot');
    const ctx = canvas.getContext('2d');
    const trail = [];
    const TRAIL_MS = 1500;
    addEventListener('mousemove', e => {
      dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px';
      trail.push({ x: e.clientX, y: e.clientY, t: performance.now() });
    }, { capture: true, passive: true });
    addEventListener('mousedown', e => {
      dot.classList.add('down');
      const ring = document.createElement('div'); ring.className = 'ring';
      ring.style.left = e.clientX + 'px'; ring.style.top = e.clientY + 'px';
      root.appendChild(ring); setTimeout(() => ring.remove(), 600);
    }, { capture: true, passive: true });
    addEventListener('mouseup', () => dot.classList.remove('down'), { capture: true, passive: true });
    addEventListener('scroll', () => { trail.length = 0; }, { capture: true, passive: true });
    const draw = now => {
      const dpr = devicePixelRatio || 1;
      if (canvas.width !== innerWidth * dpr) { canvas.width = innerWidth * dpr; canvas.height = innerHeight * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      while (trail.length && now - trail[0].t > TRAIL_MS) trail.shift();
      ctx.lineWidth = 2; ctx.lineCap = 'round';
      for (let i = 1; i < trail.length; i++) {
        ctx.strokeStyle = `rgba(239,68,68,${(1 - (now - trail[i].t) / TRAIL_MS) * 0.7})`;
        ctx.beginPath(); ctx.moveTo(trail[i - 1].x, trail[i - 1].y); ctx.lineTo(trail[i].x, trail[i].y); ctx.stroke();
      }
      requestAnimationFrame(draw);
    };
    requestAnimationFrame(draw);
  };
  if (document.documentElement) start();
  else document.addEventListener('DOMContentLoaded', start, { once: true });
})();
"""


# The page patch. Every replacement is a Proxy around the original native
# function, so Function.prototype.toString still reports native code, and
# .name, .length and `instanceof` keep working. Canvas noise is seeded per
# identity and keyed on pixel position, so the same drawing always reads back
# the same: a randomiser that changes between two identical drawings is its
# own tell.
_PAGE_SCRIPT = r"""
(() => {
  const C = __CONFIG__;
  const wrap = (obj, key, apply) => {
    const desc = obj && Object.getOwnPropertyDescriptor(obj, key);
    if (!desc || typeof desc.value !== 'function') return;
    Object.defineProperty(obj, key, { ...desc, value: new Proxy(desc.value, { apply }) });
  };
  const wrapGetter = (obj, key, get) => {
    const desc = obj && Object.getOwnPropertyDescriptor(obj, key);
    if (!desc || !desc.get) return;
    Object.defineProperty(obj, key, { ...desc, get: new Proxy(desc.get, { apply: get }) });
  };

  if (self.Screen) {
    wrapGetter(Screen.prototype, 'colorDepth', () => C.colorDepth);
    wrapGetter(Screen.prototype, 'pixelDepth', () => C.colorDepth);
  }

  // WebGL: only the two unmasked strings change. Everything else the context
  // reports stays the real GPU's, because invented limits are how spoofers get
  // caught.
  const UNMASKED_VENDOR = 0x9245, UNMASKED_RENDERER = 0x9246;
  for (const ctor of [self.WebGLRenderingContext, self.WebGL2RenderingContext]) {
    if (!ctor) continue;
    wrap(ctor.prototype, 'getParameter', (orig, ctx, args) => {
      if (args[0] === UNMASKED_VENDOR) return C.webglVendor;
      if (args[0] === UNMASKED_RENDERER) return C.webglRenderer;
      return Reflect.apply(orig, ctx, args);
    });
  }

  // Canvas: deterministic per-identity noise when a 2D canvas is read back.
  // Keyed on absolute pixel position and colour, so reading a sub-region gives
  // the same pixels as reading the whole canvas and cropping it.
  const seed = C.canvasSeed >>> 0;
  const touched = (x, y, v) => {
    let h = (Math.imul((x * 65599 + y) ^ seed, 2654435761) ^ v) >>> 0;
    h = Math.imul(h ^ (h >>> 15), 2246822519) >>> 0;
    return (h % 53) === 0;
  };
  const noise = (img, x0, y0) => {
    const data = img.data, w = img.width;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] === 0) continue;
      const k = i >> 2, x = x0 + (k % w), y = y0 + Math.floor(k / w);
      if (touched(x, y, data[i] + data[i + 1] + data[i + 2])) data[i + (x + y) % 3] ^= 1;
    }
  };
  const twoD = new WeakSet();
  const proto2d = self.CanvasRenderingContext2D && CanvasRenderingContext2D.prototype;
  const origGetImageData = proto2d && proto2d.getImageData;
  if (self.HTMLCanvasElement && proto2d) {
    wrap(HTMLCanvasElement.prototype, 'getContext', (orig, canvas, args) => {
      const ctx = Reflect.apply(orig, canvas, args);
      if (ctx && args[0] === '2d') twoD.add(canvas);
      return ctx;
    });
    const noisyCopy = (canvas) => {
      if (!twoD.has(canvas) || !canvas.width || !canvas.height || canvas.width * canvas.height > 4e6) return null;
      const copy = document.createElement('canvas');
      copy.width = canvas.width; copy.height = canvas.height;
      const cx = copy.getContext('2d');
      cx.drawImage(canvas, 0, 0);
      const img = Reflect.apply(origGetImageData, cx, [0, 0, copy.width, copy.height]);
      noise(img, 0, 0);
      cx.putImageData(img, 0, 0);
      return copy;
    };
    for (const key of ['toDataURL', 'toBlob']) {
      wrap(HTMLCanvasElement.prototype, key, (orig, canvas, args) => {
        let copy = null; try { copy = noisyCopy(canvas); } catch (e) {}
        return Reflect.apply(orig, copy || canvas, args);
      });
    }
    wrap(proto2d, 'getImageData', (orig, ctx, args) => {
      const img = Reflect.apply(orig, ctx, args);
      try { if (twoD.has(ctx.canvas)) noise(img, Math.round(args[0]) || 0, Math.round(args[1]) || 0); } catch (e) {}
      return img;
    });
  }
})();
"""
