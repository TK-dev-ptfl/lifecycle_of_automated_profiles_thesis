"""Third-party browser detectors, run against the same browser after a session.

Each opens its own tab in the run's context - same fingerprint, same proxy, same
profile - and reports what it concluded. None of them was written with this
project in mind, which is the point: they are judges the fingerprint was not
tuned against.

  rebrowser   rebrowser-bot-detector, vendored in the feed lab. Leaks specific
              to Puppeteer/Playwright: Runtime.enable, source URLs, main-world
              execution, __pwInitScripts, exposeFunction, viewport, user agent.
  creepjs     CreepJS, vendored in the feed lab. Headless / like-headless /
              stealth ratings, and "lies": APIs whose behaviour shows they were
              tampered with.
  public      Public test pages (bot.sannysoft.com, BrowserScan, Pixelscan,
              BrowserLeaks). Opt-in, proxy only: they record their visitors. Only
              sannysoft's table is parsed into a verdict; the others change
              layout too often to parse reliably, so a screenshot and the lines
              around their verdict keywords are kept instead.

Vendored detectors are served by the feed lab server under /vendor/, so they
need it running (and recent enough to have that route).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Optional

Logger = Callable[[str], None]

# rebrowser rates each test: -1 clean, 0 / 0.5 could not tell, 1 detected.
_REBROWSER_STATE = {-1: "pass", 0: "warn", 0.5: "warn", 1: "fail"}


async def _shot(page, out_dir: Optional[Path], name: str) -> Optional[str]:
    if out_dir is None:
        return None
    path = out_dir / f"{name}.png"
    try:
        await page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        return None


async def vendor_available(context, origin: str) -> bool:
    """Whether the lab server serves the vendored detectors.

    Asked with a real page load, not context.request: Playwright's request API
    sends through the proxy and ignores the browser's loopback bypass, so a
    local lab would look unreachable.
    """
    page = await context.new_page()
    try:
        response = await page.goto(f"{origin}/vendor/rebrowser/index.css", timeout=10_000)
        return bool(response and response.ok)
    except Exception:
        return False
    finally:
        await page.close()


async def run_rebrowser(context, origin: str, out_dir: Optional[Path] = None) -> dict:
    """Opens rebrowser-bot-detector and makes the calls it asks automation to
    make, so every test actually runs.

    Those calls are page.evaluate() in the page's main world - exactly what this
    runner itself does to read the lab's score and trace, so the sourceUrlLeak
    and mainWorldExecution results describe the runner, not a contrived case.
    exposeFunction is not called: nothing in this project uses it, so that test
    stays "not triggered" rather than reporting a leak the runs never have.
    """
    page = await context.new_page()
    try:
        await page.goto(f"{origin}/vendor/rebrowser/", wait_until="load", timeout=30_000)
        await page.wait_for_timeout(1500)
        await page.evaluate("() => window.dummyFn()")
        await page.evaluate("() => document.getElementById('detections-json')")
        await page.evaluate("() => document.getElementsByClassName('div')")
        await page.wait_for_timeout(2500)
        detections = json.loads(await page.input_value("#detections-json") or "[]")
        checks = [{
            "name": d.get("type", "?"),
            "state": _REBROWSER_STATE.get(d.get("rating"), "warn"),
            "detail": re.sub(r"<[^>]+>", "", d.get("note", "")).strip()[:300],
        } for d in detections]
        return {
            "detected": [c["name"] for c in checks if c["state"] == "fail"],
            "checks": checks,
            "screenshot": await _shot(page, out_dir, "rebrowser"),
        }
    finally:
        await page.close()


async def run_creepjs(context, origin: str, out_dir: Optional[Path] = None) -> dict:
    """Opens CreepJS and reads its own result object (window.Fingerprint)."""
    page = await context.new_page()
    try:
        await page.goto(f"{origin}/vendor/creepjs/", wait_until="load", timeout=30_000)
        await page.wait_for_function(
            "() => window.Fingerprint && window.Fingerprint.headless && window.Fingerprint.lies",
            timeout=60_000,
        )
        result = await page.evaluate("""() => {
            const F = window.Fingerprint, h = F.headless || {};
            const flags = group => Object.entries(h[group] || {}).filter(([, v]) => v === true).map(([k]) => k);
            const lies = (F.lies && F.lies.data) || {};
            const ws = F.workerScope || {};
            return {
                headless: h.headlessRating, like_headless: h.likeHeadlessRating, stealth: h.stealthRating,
                headless_flags: flags('headless'), like_headless_flags: flags('likeHeadless'),
                stealth_flags: flags('stealth'),
                lies: Object.fromEntries(Object.entries(lies).map(([k, v]) => [k, Array.isArray(v) ? v.slice(0, 3) : v])),
                lie_count: Object.keys(lies).length,
                worker_lied: !!ws.lied,
                worker_user_agent: ws.userAgent || null,
                worker_gpu: ws.webglRenderer || null,
                trash: ((F.trash && F.trash.trashBin) || []).length,
            };
        }""")
        result["screenshot"] = await _shot(page, out_dir, "creepjs")
        return result
    finally:
        await page.close()


# --- public pages --------------------------------------------------------------

PUBLIC_PAGES = [
    ("sannysoft", "https://bot.sannysoft.com/"),
    ("browserscan", "https://www.browserscan.net/bot-detection"),
    ("pixelscan", "https://pixelscan.net/"),
    ("browserleaks-webrtc", "https://browserleaks.com/webrtc"),
    ("browserleaks-ip", "https://browserleaks.com/ip"),
]
_KEYWORDS = re.compile(
    r"(bot|robot|automat|headless|consistent|inconsistent|authentic|mask|spoof|leak|webrtc|proxy|"
    r"passed|failed|normal|detected|public ip|local ip|your ip)",
    re.I,
)


async def run_public(context, out_dir: Optional[Path], log: Logger = lambda _m: None) -> list[dict]:
    results = []
    for name, url in PUBLIC_PAGES:
        page = await context.new_page()
        entry: dict = {"name": name, "url": url}
        try:
            await page.goto(url, wait_until="load", timeout=45_000)
            await page.wait_for_timeout(8000)
            if name == "sannysoft":
                entry.update(await page.evaluate("""() => {
                    const rows = [...document.querySelectorAll('tr')].map(tr => {
                        const cells = [...tr.querySelectorAll('td')];
                        const res = cells.find(td => /\\b(passed|failed|warn)\\b/.test(td.className));
                        return res ? { name: cells[0].innerText.trim().slice(0, 60),
                                       state: (res.className.match(/passed|failed|warn/) || ['?'])[0] } : null;
                    }).filter(Boolean);
                    return { passed: rows.filter(r => r.state === 'passed').length,
                             failed: rows.filter(r => r.state === 'failed').map(r => r.name),
                             warned: rows.filter(r => r.state === 'warn').map(r => r.name) };
                }"""))
            text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            lines = [l.strip() for l in text.splitlines() if l.strip() and _KEYWORDS.search(l) and len(l.strip()) < 160]
            entry["highlights"] = lines[:25]
            entry["screenshot"] = await _shot(page, out_dir, name)
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        finally:
            await page.close()
        log(f"public check {name}: " + (entry.get("error") or "done"))
        results.append(entry)
    return results
