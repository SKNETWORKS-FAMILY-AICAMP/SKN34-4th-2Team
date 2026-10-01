"""Isolated, disposable DB for the v2 persistence tests; never loads RDS."""

from .settings import *  # noqa: F401,F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
MIGRATION_MODULES = {'lms': None}
