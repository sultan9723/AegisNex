"""Failsafe decorators and wrappers for AegisNex.

Every integration point is wrapped so that no single service failure
can crash the platform. Unavailable services log a warning and return
a structured error response.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Dict, TypeVar

_logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def failsafe(
    fallback: Any = None,
    message: str = "Service unavailable",
    log_level: int = logging.WARNING,
) -> Callable[[F], F]:
    """Decorator that catches any exception and returns a structured fallback.

    Usage::

        @failsafe(fallback={"status": "unavailable", "error": "Docker not reachable"})
        def get_docker_containers():
            ...
    """
    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                _logger.log(log_level, "%s - %s: %s", message, fn.__name__, exc)
                if callable(fallback):
                    return fallback(exc)
                if fallback is not None:
                    return fallback
                return {"status": "error", "error": str(exc), "message": message}
        return wrapper  # type: ignore
    return decorator


def safe_import(module_name: str, attr: str | None = None) -> Any:
    """Safely import a module or attribute, returning None on failure."""
    try:
        module = __import__(module_name, fromlist=[attr] if attr else [])
        if attr:
            return getattr(module, attr, None)
        return module
    except ImportError:
        _logger.debug("Optional dependency not available: %s", module_name)
        return None


class ServiceUnavailable(Exception):
    """Raised when an external service is not reachable."""
    pass
