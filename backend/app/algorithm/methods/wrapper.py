from __future__ import annotations

import inspect
from importlib import import_module
from types import ModuleType
from typing import Callable

_METHOD_TYPE_ALIASES = {
    "official": "official_api",
    "unofficial": "unofficial_api",
    "requests": "http_requests",
    "http": "http_requests",
    "headless": "headless_browser",
    "classical": "classical_browser",
}


class MethodWrapper:
    """Injects method implementations from a selected method-type package.

    Example:
        actions = MethodWrapper("official")
        actions.get_data("python")
    """

    def __init__(self, method_type: str):
        self.method_type = self._normalize(method_type)
        self._module = self._load_module(self.method_type)
        self._context = self._build_context()
        self._inject_methods()

    def _normalize(self, method_type: str) -> str:
        normalized = method_type.strip().lower()
        return _METHOD_TYPE_ALIASES.get(normalized, normalized)

    def _load_module(self, method_type: str) -> ModuleType:
        try:
            return import_module(f"app.algorithm.methods.{method_type}")
        except ModuleNotFoundError as exc:
            raise ValueError(f"Unsupported method type: {method_type}") from exc

    def _inject_methods(self) -> None:
        method_names = getattr(self._module, "__all__", [])
        for method_name in method_names:
            fn = getattr(self._module, method_name, None)
            if callable(fn):
                setattr(self, method_name, self._bind(fn))

    def _build_context(self):
        builder = getattr(self._module, "build_context", None)
        if callable(builder):
            return builder()
        return None

    def _bind(self, fn: Callable):
        params = list(inspect.signature(fn).parameters.values())
        expects_context = bool(params) and params[0].name == "context"

        def _bound(*args, **kwargs):
            if expects_context:
                return fn(self._context, *args, **kwargs)
            return fn(*args, **kwargs)

        _bound.__name__ = fn.__name__
        return _bound
