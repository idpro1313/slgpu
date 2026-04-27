"""HTTP-middleware slgpu-web."""

from app.middleware.request_log import AppHttpRequestLogMiddleware

__all__ = ["AppHttpRequestLogMiddleware"]
