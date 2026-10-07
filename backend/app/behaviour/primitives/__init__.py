"""One physical action each, and nothing about the page they happen on.

    timing    - how long a human waits, as distributions rather than constants
    mouse     - paths, moves, drags, clicks, where on a target to land
    keyboard  - per-key typing rhythm, and typos with corrections
    scroll    - wheel notches, and the overshoot-and-come-back of reading

Each takes a protocol from app.behaviour.protocols rather than a Playwright Page,
so each is testable on its own against a recorder. See app/behaviour/algorithms
for the compositions that make these purposeful.
"""
