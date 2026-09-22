from lms.jwt_auth import AuthError, user_from_access


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
