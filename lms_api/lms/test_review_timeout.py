import json
import os
import urllib.error
from unittest.mock import patch
from django.test import SimpleTestCase
from lms.api import _review_call


class ReviewTimeoutTests(SimpleTestCase):
    def test_only_upstream_timeouts_are_retryable(self):
        for error, status, detail in [
            (TimeoutError(), 504, 'review_upstream_timeout'),
            (urllib.error.URLError(TimeoutError()), 504, 'review_upstream_timeout'),
            (urllib.error.URLError('connection refused'), 503, None),
        ]:
            with self.subTest(error=error), patch.dict(os.environ, {'RESUME_REVIEW_URL': 'http://example.invalid'}), patch('urllib.request.urlopen', side_effect=error):
                response = _review_call('/review', {})
                self.assertEqual(response.status_code, status)
                if detail:
                    self.assertEqual(json.loads(response.content)['detail'], detail)
