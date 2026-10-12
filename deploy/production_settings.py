"""Deployment-only settings, mounted into /app; TLS terminates at CloudFront.

Nginx overwrites X-Forwarded-Proto and the EC2 security group restricts HTTP
ingress to the CloudFront VPC origin. Do not use this trust configuration with
an unrestricted public origin.
"""
from lms_server.settings import *  # noqa: F403

DEBUG = False
# Validate pooled PostgreSQL connections before handing them to a request.
# Idle connections may have been closed by RDS or the intervening network.
DATABASES['default']['CONN_HEALTH_CHECKS'] = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
# CloudFront redirects viewers to HTTPS; the private origin also has local probes.
SECURE_SSL_REDIRECT = False
MIDDLEWARE = [*MIDDLEWARE, 'django.middleware.clickjacking.XFrameOptionsMiddleware']  # noqa: F405
