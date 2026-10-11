"""Host and same-origin protection for the opt-in local v2 deployment."""
from __future__ import annotations
import ipaddress
import os
from urllib.parse import urlsplit
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from module.v2_runtime import enabled

class V2OriginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not enabled():
            return await call_next(request)
        host = request.url.hostname or ''
        allowed = {h.strip().lower() for h in os.getenv('LAR_ALLOWED_HOSTS', 'localhost,127.0.0.1,::1').split(',') if h.strip()}
        host_ok = host.lower() in allowed
        try:
            host_ok = host_ok or ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass
        if not host_ok:
            return JSONResponse({'code': 'INVALID_HOST', 'message': 'Host is not allowed', 'retryable': False, 'details': {}}, status_code=400)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('origin')
            if request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'code': 'CROSS_ORIGIN', 'message': 'Cross-site changes are blocked', 'retryable': False, 'details': {}}, status_code=403)
            if origin:
                source = urlsplit(origin)
                current = urlsplit(str(request.url))
                if origin == 'null' or source.scheme not in {'http', 'https'} or (source.scheme, source.netloc.lower()) != (current.scheme, current.netloc.lower()):
                    return JSONResponse({'code': 'CROSS_ORIGIN', 'message': 'Origin does not match this recorder', 'retryable': False, 'details': {}}, status_code=403)
        return await call_next(request)
