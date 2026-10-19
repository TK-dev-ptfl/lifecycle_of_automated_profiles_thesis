"""The fingerprint an identity presents: stable, distinct, and self-consistent.

What a browser check looks for is disagreement - between the user agent and the
platform, the GPU and the OS, the window and the screen, the language and the
place. These tests pin that every derived fingerprint agrees with itself.
"""
from __future__ import annotations

import pytest

from app.behaviour import fingerprint as fp_mod
from app.behaviour.fingerprint import COUNTRIES, fingerprint_for

REAL = {
    "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "HeadlessChrome/154.0.0.0 Safari/537.36",
    "version": "154.0.8037.99",
    "cores": 12,
    "memory": 8,
}


def test_same_identity_same_machine_different_identity_different_machine():
    assert fingerprint_for("identity-a") == fingerprint_for("identity-a")
    prints = {fingerprint_for(f"identity-{i}") for i in range(40)}
    assert len(prints) == 40


@pytest.mark.parametrize("os_name", ["Windows", "macOS", "Linux"])
def test_every_fingerprint_is_internally_consistent(os_name):
    for i in range(200):
        fp = fingerprint_for(f"identity-{i}", os_name=os_name)
        # The window fits on the screen, and the viewport leaves room for the
        # taskbar and the browser's own toolbars.
        assert fp.viewport_width <= fp.screen_width
        assert fp.viewport_height < fp.screen_height - 80
        assert fp.window_size[1] <= fp.screen_height
        # CSS screen size is physical size over the scale factor.
        assert fp.screen_width == round(fp.physical_width / fp.pixel_ratio)
        # The GPU string is the one Chrome reports on that OS.
        if os_name == "Windows":
            assert "Direct3D11" in fp.webgl_renderer
        if os_name == "macOS":
            assert "Apple" in fp.webgl_renderer and fp.pixel_ratio == 2.0
        # Edge does not ship on Linux; and only browsers Chromium can back up.
        assert fp.browser in ("Chrome", "Edge")
        assert not (os_name == "Linux" and fp.browser == "Edge")
        # Language and zone come from the same country.
        locale, languages, timezone = COUNTRIES[fp.country_code]
        assert (fp.locale, fp.timezone) == (locale, timezone)
        assert fp.language_tags[0] == fp.locale


def test_language_tags_take_the_shape_chrome_builds():
    fp = fingerprint_for("x", country_code="SK")
    assert fp.language_tags == ("sk-SK", "sk", "cs", "en-US", "en")
    assert fingerprint_for("x", country_code="US").language_tags == ("en-US", "en")


def test_a_proxy_moves_the_place_but_not_the_machine():
    """Behind a proxy, language and clock follow the exit; the screen, GPU and
    browser stay the identity's own."""
    home = fingerprint_for("identity-a")
    away = fingerprint_for("identity-a", country_code="GB", timezone="Europe/London")
    assert (away.locale, away.timezone) == ("en-GB", "Europe/London")
    for attr in ("browser", "screen_width", "screen_height", "viewport_width", "webgl_renderer", "canvas_seed"):
        assert getattr(home, attr) == getattr(away, attr)


def test_the_exit_zone_wins_over_the_countrys_default():
    fp = fingerprint_for("identity-a", country_code="US", timezone="America/Los_Angeles")
    assert fp.timezone == "America/Los_Angeles" and fp.locale == "en-US"


def test_an_unlisted_exit_country_still_gets_a_coherent_place():
    assert fingerprint_for("x", country_code="JP", timezone="Asia/Tokyo").language_tags[0] == "ja-JP"
    unknown = fingerprint_for("x", country_code="ZZ", timezone="Africa/Lagos")
    assert (unknown.locale, unknown.timezone) == ("en-US", "Africa/Lagos")


def test_a_proxied_launch_keeps_webrtc_on_the_proxy():
    fp = fingerprint_for("identity-a")
    flag = "--webrtc-ip-handling-policy=disable_non_proxied_udp"
    assert flag in fp_mod.launch_args(fp, headless=True, proxied=True)
    assert flag not in fp_mod.launch_args(fp, headless=True)


def test_binding_takes_the_real_browser_and_drops_the_headless_marker():
    fp = fingerprint_for("identity-a").bind(REAL)
    assert "Headless" not in fp.user_agent
    assert "Chrome/154.0.0.0" in fp.user_agent
    assert fp.browser_version == "154.0.8037.99"
    # Cores and memory are the host's: a worker reports them natively.
    assert (fp.hardware_concurrency, fp.device_memory) == (12, 8)


def test_launch_flags_switch_off_the_webdriver_flag_and_set_languages():
    fp = fingerprint_for("identity-a", country_code="DE")
    args = fp_mod.launch_args(fp, headless=False)
    assert "--disable-blink-features=AutomationControlled" in args
    assert "--accept-lang=de-DE,de,en-US,en" in args
    assert any(a.startswith("--window-size=") for a in args)
    assert not any(a.startswith("--window-size=") for a in fp_mod.launch_args(fp, headless=True))


def test_context_options_carry_screen_scale_and_zone():
    fp = fingerprint_for("identity-a").bind(REAL)
    options = fp_mod.context_options(fp)
    assert options["screen"] == {"width": fp.screen_width, "height": fp.screen_height}
    assert options["viewport"] == {"width": fp.viewport_width, "height": fp.viewport_height}
    assert options["device_scale_factor"] == fp.pixel_ratio
    assert options["timezone_id"] == fp.timezone
    assert options["user_agent"] == fp.user_agent
    # Locale is set by flag instead, so that workers get it too.
    assert "locale" not in options


def test_page_script_carries_this_identitys_values():
    fp = fingerprint_for("identity-a")
    script = fp.page_script()
    assert fp.webgl_renderer in script
    assert str(fp.canvas_seed) in script
    assert "__CONFIG__" not in script
