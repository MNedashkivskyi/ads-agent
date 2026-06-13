"""Regression: rate-limited endpoints must declare a ``response: Response`` param.

slowapi has ``headers_enabled=True`` (see ``adcopilot.rate_limit``). When a
``@limiter.limit``-decorated endpoint returns a Pydantic model (not a Response),
slowapi injects the X-RateLimit-* headers into ``kwargs["response"]`` — which is
``None`` unless the endpoint declares a ``response: Response`` parameter, raising
``parameter `response` must be an instance of starlette.responses.Response`` and
500-ing the request (this is what broke /api/website/analyze).
"""

from __future__ import annotations

import inspect

from fastapi import Response

from adcopilot.interfaces.api.landing_page import get_landing_page_score
from adcopilot.interfaces.api.qa import ask
from adcopilot.interfaces.api.website import analyze_website

_RATE_LIMITED_ENDPOINTS = [analyze_website, ask, get_landing_page_score]


def test_rate_limited_endpoints_declare_response_param() -> None:
    for endpoint in _RATE_LIMITED_ENDPOINTS:
        params = inspect.signature(endpoint).parameters
        assert "request" in params, f"{endpoint.__name__} missing request param"
        assert "response" in params, (
            f"{endpoint.__name__} must declare a `response: Response` param so "
            f"slowapi can inject rate-limit headers (else it 500s)"
        )
        # ``from __future__ import annotations`` makes annotations strings, so
        # accept either the resolved class or its name.
        annotation = params["response"].annotation
        assert annotation in (Response, "Response"), (
            f"{endpoint.__name__} `response` param must be typed Response, got {annotation!r}"
        )
