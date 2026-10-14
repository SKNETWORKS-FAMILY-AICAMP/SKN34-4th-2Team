"""SSM entry point on the existing EC2 hosts. Never print runtime secrets."""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BASE = Path('/opt/skn34-lms')
REGISTRY = '711425439897.dkr.ecr.us-east-1.amazonaws.com'


def validate(service, image, release):
    if service not in ('api', 'ai') or not re.fullmatch(r'[a-f0-9]{40}-[0-9]+-[0-9]+', release):
        raise ValueError('Invalid release identity')
    if not re.fullmatch(re.escape(REGISTRY + '/lms-' + service) + r'@sha256:[a-f0-9]{64}', image):
        raise ValueError('Only immutable images from the project ECR are accepted')


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def inspect(service):
    return json.loads(subprocess.check_output(['docker', 'inspect', 'deploy-' + service + '-1']))[0]


def atomic_write(path, data):
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def set_image(data, key, image):
    lines = [s for s in data.splitlines() if s.split('=', 1)[0].strip() != key]
    return '\n'.join(lines + [key + '=' + image]) + '\n'


def docker_python(service, code):
    return subprocess.check_output(['docker', 'exec', 'deploy-' + service + '-1', 'python', '-c', code], text=True)


def consumer(enable):
    operation = 'add_consumer' if enable else 'cancel_consumer'
    docker_python('worker', "from lms_server.celery import app; assert app.control." + operation + "('celery',reply=True,timeout=5)")


def drain():
    consumer(False)
    try:
        for _ in range(50):
            code = "from lms_server.celery import app; import json; i=app.control.inspect(timeout=3); a=i.active();r=i.reserved();assert a is not None and r is not None;print(json.dumps(sum(len(x) for x in a.values())+sum(len(x) for x in r.values())))"
            if json.loads(docker_python('api', code)) == 0:
                return
            time.sleep(10)
        raise RuntimeError('Worker did not drain; retry later')
    except BaseException:
        consumer(True)
        raise


def ready(service):
    path = '/api/bootstrap' if service == 'api' else '/resume-review/health'
    expected = 401 if service == 'api' else 200
    code = "import urllib.request,urllib.error\ntry:\n r=urllib.request.urlopen('http://127.0.0.1:8000" + path + "',timeout=3); status=r.status\nexcept urllib.error.HTTPError as e: status=e.code\nassert status==" + str(expected)
    for _ in range(60):
        p = subprocess.run(['docker', 'exec', 'deploy-' + service + '-1', 'python', '-c', code], capture_output=True)
        if p.returncode == 0:
            if service == 'api':
                run(['docker', 'exec', 'deploy-nginx-1', 'nginx', '-s', 'reload'])
                consumer(True)
                code = "from lms_server.celery import app; r=app.control.inspect(timeout=5).registered();assert r and any('lms.review_jobs.run_review_job' in t for t in r.values())"
                docker_python('api', code)
            return
        time.sleep(2)
    raise RuntimeError('Service readiness failed: ' + service)


def main(service, image, release, phase):
    validate(service, image, release)
    folder = BASE / 'releases' / release / service
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = BASE / '.env'
    record = folder / 'before.json'
    if phase == 'prepare':
        if record.exists():
            raise RuntimeError('Release was already prepared; use a new run attempt')
        current = inspect(service)
        atomic_write(folder / 'runtime.env', env.read_bytes())
        files = current['Config']['Labels']['com.docker.compose.project.config_files'].split(',')
        if any(not Path(p).resolve().is_relative_to(BASE) for p in files):
            raise RuntimeError('Unexpected Compose location')
        atomic_write(record, json.dumps({'image': current['Config']['Image'], 'id': current['Image'], 'files': files}).encode())
        # EC2 role supplies ECR read credentials; no long-lived key or token in SSM.
        auth = json.loads(docker_python(service, "import boto3,json;print(json.dumps(boto3.client('ecr',region_name='us-east-1').get_authorization_token()['authorizationData'][0]))"))
        password = base64.b64decode(auth['authorizationToken']).decode().split(':', 1)[1]
        with tempfile.TemporaryDirectory(prefix='ecr-', dir=folder) as config:
            run(['docker', '--config', config, 'login', '--username', 'AWS', '--password-stdin', REGISTRY], input=password, text=True, capture_output=True)
            run(['docker', '--config', config, 'pull', image])
        if service == 'api':
            # Docker --env-file does not implement Compose quoting: use the already parsed environment.
            fd, filename = tempfile.mkstemp(dir=folder)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, 'w') as f:
                    f.write('\n'.join(current['Config']['Env']) + '\n')
                network = next(iter(current['NetworkSettings']['Networks']))
                args = ['docker', 'run', '--rm', '--network', network, '--env-file', filename,
                        '-e', 'LMS_INLINE_PUBLISH=0', '-e', 'DJANGO_SETTINGS_MODULE=production_settings',
                        '-v', str(BASE / 'deploy/production_settings.py') + ':/app/production_settings.py:ro', image]
                # Fail closed: schema changes require a separately reviewed operation.
                run(args + ['python', 'manage.py', 'migrate', '--check'])
            finally:
                os.unlink(filename)
        return
    if not record.exists():
        if phase == 'rollback':
            return
        raise RuntimeError('Missing prepared snapshot')
    before = json.loads(record.read_text())
    compose = ['docker', 'compose', '--env-file', str(env)]
    for path in before['files']:
        compose += ['-f', path]
    services = ['api', 'worker'] if service == 'api' else ['ai']
    if phase == 'drain':
        if service != 'api':
            raise ValueError('Only API owns worker')
        drain()
        return
    if phase == 'apply':
        if inspect(service)['Image'] != before['id']:
            raise RuntimeError('Concurrent deployment detected')
        key = 'ECR_IMAGE' if service == 'api' else 'ECR_AI_IMAGE'
        atomic_write(env, set_image(env.read_text(), key, image).encode())
        atomic_write(folder / 'changed', b'1')
    elif phase == 'rollback':
        if not (folder / 'changed').exists():
            if service == 'api':
                consumer(True)
            return
        try:
            running_image = inspect(service)['Config']['Image']
        except subprocess.CalledProcessError:
            running_image = image  # Recreate can fail after removing the old container.
        if running_image not in (image, before['image']):
            raise RuntimeError('Another release is running; refusing to overwrite it')
        # Restore only our image setting; preserve unrelated operational edits.
        key = 'ECR_IMAGE' if service == 'api' else 'ECR_AI_IMAGE'
        atomic_write(env, set_image(env.read_text(), key, before['image']).encode())
    else:
        raise ValueError('Unknown operation')
    run(compose + ['config', '--quiet'], cwd=BASE)
    run(compose + ['up', '-d', '--no-deps', '--timeout', '600', *services], cwd=BASE)
    ready(service)
    print(json.dumps({'service': service, 'phase': phase, 'release': release, 'ready': True}))


if __name__ == '__main__':
    main(*sys.argv[1:])
