"""Compositions of primitives that add up to a recognisable behaviour.

    cursor  - Cursor (tracks pointer position across a session), idle_drags,
              approach_and_click
    forms   - fill_field

These are what pipelines call. A pipeline step should read as a sentence about
intent ("approach the signup button and click it"), with every decision about how
a hand actually moves living here and in the primitives - so changing how human
the whole system behaves never means editing a pipeline.
"""
from app.behaviour.algorithms.cursor import Cursor, approach_and_click, idle_drags
from app.behaviour.algorithms.forms import fill_field

__all__ = ["Cursor", "approach_and_click", "idle_drags", "fill_field"]
