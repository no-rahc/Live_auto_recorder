"""Compatibility helpers for Starlette/Jinja template rendering.

The legacy recorder core still has a number of ``TemplateResponse(name, context)``
call sites. Starlette 1.x removed that positional calling convention and expects
``TemplateResponse(request, name, context=...)`` instead. Install this shim
before importing the legacy core so old calls remain safe while newer code can
use Starlette's current API directly.
"""
from __future__ import annotations

from functools import wraps
from typing import Any

from starlette.templating import Jinja2Templates as StarletteJinja2Templates


_PATCH_MARKER = "_lar_template_response_compat"
_OLD_POSITIONAL_FIELDS = ("status_code", "headers", "media_type", "background")


def _patch_template_class(template_class: type[Any]) -> None:
    current = template_class.TemplateResponse
    if getattr(current, _PATCH_MARKER, False):
        return

    original = current

    @wraps(original)
    def template_response(self: Any, *args: Any, **kwargs: Any):
        # Starlette < 1.0 accepted TemplateResponse(name, context, ...).
        # A legacy call is unambiguous because the first argument is a template
        # name string instead of a Request instance.
        if args and isinstance(args[0], str):
            name = args[0]
            context = args[1] if len(args) >= 2 else kwargs.pop("context", None)
            if context is None:
                context = {}
            if not isinstance(context, dict):
                raise TypeError("legacy TemplateResponse context must be a dict")

            request_from_kwargs = kwargs.pop("request", None)
            request = context.get("request")
            if request is None:
                request = request_from_kwargs
            if request is None:
                raise TypeError("legacy TemplateResponse context must contain 'request'")

            positional_tail = args[2:]
            if len(positional_tail) > len(_OLD_POSITIONAL_FIELDS):
                raise TypeError("too many positional arguments for TemplateResponse")
            for field, value in zip(_OLD_POSITIONAL_FIELDS, positional_tail):
                if field in kwargs:
                    raise TypeError(f"TemplateResponse got multiple values for {field!r}")
                kwargs[field] = value

            return original(
                self,
                request=request,
                name=name,
                context=context,
                **kwargs,
            )

        return original(self, *args, **kwargs)

    setattr(template_response, _PATCH_MARKER, True)
    template_class.TemplateResponse = template_response


def install_template_response_compat() -> None:
    """Install the legacy TemplateResponse adapter once per process."""

    _patch_template_class(StarletteJinja2Templates)

    # FastAPI currently re-exports Starlette's class, but patch the reference as
    # well in case that implementation detail changes in a future release.
    try:
        from fastapi.templating import Jinja2Templates as FastAPIJinja2Templates
    except Exception:
        return
    if FastAPIJinja2Templates is not StarletteJinja2Templates:
        _patch_template_class(FastAPIJinja2Templates)
