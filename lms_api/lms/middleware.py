from django.middleware.gzip import GZipMiddleware

from lms.jwt_auth import AuthError, user_from_access


class JsonGZipMiddleware(GZipMiddleware):
    """응답을 gzip 으로 압축한다. 스트리밍(챗봇 SSE)은 압축하면 조각이 모여서 늦게 오므로 그대로 둔다"""

    def process_response(self, request, response):
        if response.streaming:
            return response
        return super().process_response(request, response)


class LmsUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.lms_user = None
        header = request.META.get("HTTP_AUTHORIZATION") or ""
        if header.startswith("Bearer "):
            try:
                request.lms_user = user_from_access(header[7:].strip())
            except AuthError:
                request.lms_user = None
        return self.get_response(request)
