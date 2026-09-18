import unittest

from chatbot_lab.main import app


class FlutterRouteTest(unittest.TestCase):
    def test_lab_keeps_isolated_and_flutter_compatible_routes(self) -> None:
        paths = set(app.openapi()["paths"])
        for suffix in ("health", "init", "stream"):
            self.assertIn(f"/api/v1/student-chatbot-lab/{suffix}", paths)
            self.assertIn(f"/api/v1/student-chatbot/{suffix}", paths)


if __name__ == "__main__":
    unittest.main()
