"""The deployed Django proxy must work without importing the legacy Firebase SDK."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_integrated_proxy_boundary_without_firebase_sdk():
    root = Path(__file__).resolve().parents[2]
    code = textwrap.dedent('''
        import importlib.abc
        import sys
        from unittest.mock import patch

        class NoFirebase(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == 'firebase_admin' or fullname.startswith('firebase_admin.'):
                    raise AssertionError('Django proxy imported legacy Firebase SDK: ' + fullname)
        sys.meta_path.insert(0, NoFirebase())

        # No production I/O or paid model calls are permitted in this regression.
        with patch('psycopg.connect', side_effect=AssertionError('database I/O forbidden')), \
             patch('httpx.HTTPTransport.handle_request', side_effect=AssertionError('network I/O forbidden')):
            from fastapi.testclient import TestClient
            from app.integrated import app
            from app import main, resume_apply
            from app.config import Settings, get_settings
            from app.firebase_gateway import FirebaseAuthenticationError
            from app.review_runtime_factory import build_review_gateway
            from app.resume_review_runtime import PostgresReviewGateway
            settings = Settings(_env_file=None, openai_api_key='synthetic-test',
                                firebase_project_id=None, resume_review_engine='v2')
            with patch.object(main, 'get_settings', return_value=settings), \
                 patch.object(resume_apply, 'get_settings', return_value=settings):
                for gateway in (build_review_gateway(settings), main.get_context_gateway(),
                                resume_apply.gateway_dependency()):
                    assert isinstance(gateway, PostgresReviewGateway)
                    try:
                        gateway.verify_id_token('untrusted')
                    except FirebaseAuthenticationError:
                        pass
                    else:
                        raise AssertionError('Direct token accepted without Firebase configuration')
            main.app.dependency_overrides[get_settings] = lambda: settings
            client = TestClient(app)
            response = client.get('/resume-review/health')
            assert response.status_code == 200
            assert response.json()['review_engine'] == 'v2'
            assert response.json()['firebase_auth'] == 'not_configured'
            payload = {'cohortId': 'c', 'source': {'id': 's', 'title': 'test',
                       'repoUrl': 'https://github.com/example/test', 'branch': 'main'}}
            with patch('study_notes.api.service.source_tree', return_value={'files': []}) as tree:
                response = client.post('/api/v1/study-notes/proxy/tree', json=payload)
                assert response.status_code == 401, response.text
                tree.assert_not_called()
                response = client.post('/api/v1/study-notes/proxy/tree', json=payload,
                                       headers={'X-LMS-AI-Token': 'synthetic-proxy-token'})
                assert response.status_code == 200, response.text
                tree.assert_called_once()
            assert not any(m == 'firebase_admin' or m.startswith('firebase_admin.') for m in sys.modules)
    ''')
    env = {**os.environ, 'FIREBASE_PROJECT_ID': '', 'GOOGLE_CLOUD_PROJECT': '',
           'OPENAI_API_KEY': 'synthetic-test', 'LMS_AI_SHARED_TOKEN': 'synthetic-proxy-token',
           'LANGSMITH_TRACING': 'false', 'LANGCHAIN_TRACING_V2': 'false',
           'SERVER_WARM': '0', 'RESUME_REVIEW_ENGINE': 'v2'}
    result = subprocess.run([sys.executable, '-c', code], cwd=root, env=env,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_token_verification_still_checks_firebase():
    from unittest.mock import patch
    from app.config import Settings
    from app.firebase_gateway import FirebaseGateway
    from firebase_admin import auth

    settings = Settings(_env_file=None, firebase_project_id='synthetic-legacy')
    sentinel = object()
    with patch.object(FirebaseGateway, '_initialize_app', return_value=sentinel), \
         patch.object(auth, 'verify_id_token', return_value={'uid': 'legacy-student'}) as verify:
        gateway = FirebaseGateway(settings)
        assert gateway.verify_id_token('test-token') == 'legacy-student'
        verify.assert_called_once_with('test-token', app=sentinel)
