"""Security primitives: rate limiting by path prefix, OAuth state storage.

This package contains security-hardening building blocks that sit between
the ASGI layer and the domain/application code.  They are deliberately kept
framework-agnostic where possible so they can be unit-tested without spinning
up a FastAPI TestClient.
"""

from adcopilot.security.rate_limiting import (
    PathPrefixRateLimitMiddleware,
    PrefixRateLimitConfig,
    build_default_prefix_rate_limits,
)

__all__ = [
    "PathPrefixRateLimitMiddleware",
    "PrefixRateLimitConfig",
    "build_default_prefix_rate_limits",
]
