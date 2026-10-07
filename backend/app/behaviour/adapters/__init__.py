"""Environment implementations.

    simulated   an in-memory world: no browser, no network, a virtual clock.
                Where the behaviour layer is developed and tested.
    playwright  a real page.

Both satisfy app.behaviour.environment.Environment, which is what lets the same
goals and the same profile run against either one unchanged.
"""
