"""Every Reddit DOM handle the pipeline depends on, in one place.

Collected here because these are the parts most likely to break: Reddit ships UI
changes constantly, and when a step starts failing the question is always "did
this selector move". One file to check and to update, instead of hunting through
the steps.

Notes on choices:
  - #signup-button is Reddit's own id on the header link; stable and unambiguous.
  - The signup dialog is matched by role+modal rather than by class, because its
    classes are generated Tailwind-ish soup that changes between deploys.
  - Reddit's UI is localised, so anything matched by visible text needs every
    language the pipeline might land in. The proxy decides the locale, and the
    proxy is whatever the pool handed over - so this cannot assume Czech or
    Slovak even with a cs-CZ context.
"""
from __future__ import annotations

HOME_URL = "https://www.reddit.com/"

# --- The "Prove your humanity" interstitial ----------------------------------
# Shown on some IPs and not others; a datacenter or heavily-used proxy sees it far
# more often. Matched on the heading the user reported seeing.
HUMANITY_HEADING = "Prove your humanity"
HUMANITY_HEADING_SELECTOR = "h1"

# --- Network-security block --------------------------------------------------
# Reddit refuses the connection outright for an IP it does not like, serving a
# dead-end page with no signup anything on it. Observed live on a Webshare
# datacenter address: the request succeeds at the HTTP level (200, even), and the
# browser still lands here - the decision is made on the session, not just the
# address, so it cannot be predicted from a plain fetch.
#
# This is Reddit's equivalent of Tuta's abuse banner, and gets the same
# treatment: not a step failure, a PROXY failure. The run flags that proxy and
# retries on a different one rather than giving up (see
# identity_service.IP_BLOCKED_MARKER, which matches on the "ip_blocked" prefix
# these raise).
BLOCKED_TEXT = "blocked by network security"
BLOCKED_SELECTOR = "body"

# Reddit also serves a self-solving JS challenge before the real page, which
# redirects to ?js_challenge=1&solution=... once it passes. Landing on that is
# not a failure - it just means the homepage has not arrived yet.
JS_CHALLENGE_MARKER = "js_challenge=1"

# --- Signup entry point ------------------------------------------------------
SIGNUP_BUTTON = "#signup-button"
# Fallback for a layout where the id is absent: the link always points at the
# register route, whatever it is labelled.
SIGNUP_LINK_FALLBACK = 'a[href*="/register"]'

# --- Signup dialog -----------------------------------------------------------
# role=dialog + aria-modal is what the reported markup exposes, and unlike the
# class list it is semantic and localisation-independent.
SIGNUP_DIALOG = '[role="dialog"][aria-modal="true"]'

# Reddit's email field inside that dialog. Tried in order; the first that exists
# and is visible wins, so a renamed id doesn't take the run down on its own.
EMAIL_FIELD_CANDIDATES = (
    '#register-email',
    'input[name="email"]',
    'input[type="email"]',
    'input[autocomplete="email"]',
)

# The dialog's primary action. Reddit puts it in a named slot, which survives
# relabelling and translation better than the button's text does.
CONTINUE_BUTTON_CANDIDATES = (
    '[slot="primaryButton"] button',
    '[role="dialog"] button[type="submit"]',
    'button:has-text("Continue")',
    'button:has-text("Pokračovať")',   # sk
    'button:has-text("Pokračovat")',   # cs
)

# Reddit's inline complaint about the address - wrong format, or already taken.
# Used to tell "the form rejected this" apart from "the form is still thinking".
EMAIL_ERROR_CANDIDATES = (
    '[role="dialog"] [role="alert"]',
    '[role="dialog"] .text-error',
    'inline-banner:not(:empty)',
)
