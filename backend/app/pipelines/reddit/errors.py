"""Failure naming for Reddit pipeline steps.

Same shape as the email pipeline's _step_error: a RuntimeError whose message
starts with the step name, so identity_service's "{type}: {message}" lands on the
dashboard already saying which step broke. A bare "element not found" three
abstraction layers down tells nobody anything.
"""
from __future__ import annotations


def step_error(step_name: str, message: str) -> RuntimeError:
    return RuntimeError(f"{step_name}: {message}")
