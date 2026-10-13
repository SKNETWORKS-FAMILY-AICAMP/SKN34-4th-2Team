"""Run via stdin inside the built image with docker run --rm -i --network none.

No credentials or production env file should be passed. This checks startup, not
RDS/S3/LLM integration. Temporary server and files live only in the container.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

os.environ.update(SERVER_WARM='0', AWS_EC2_METADATA_DISABLED='true',
                  RESUME_REVIEW_ENGINE='v2')
subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True)
subprocess.run(['node', '--version'], check=True)
with tempfile.TemporaryFile(mode='w+t') as log:
    server = subprocess.Popen([
        sys.executable, '-m', 'uvicorn', 'app.integrated:app',
        '--app-dir', 'cover_letter_rag', '--host', '127.0.0.1', '--port', '18001',
    ], stdout=log, stderr=log)
    try:
        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError('AI server exited during startup')
            try:
                with urllib.request.urlopen('http://127.0.0.1:18001/resume-review/health', timeout=2) as response:
                    result = json.load(response)
                assert result['review_engine'] == 'v2', result
                print('AI HTTP startup passed: resume-review engine v2', flush=True)
                break
            except (OSError, TimeoutError):
                time.sleep(1)
        else:
            raise RuntimeError('AI server did not become ready within the startup window')
    except Exception:
        log.seek(0)
        print(log.read()[-12000:], file=sys.stderr)
        raise
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
