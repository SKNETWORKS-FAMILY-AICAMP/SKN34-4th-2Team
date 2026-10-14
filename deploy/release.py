"""GitHub runner release coordinator for the existing two EC2 hosts and CDN."""
import argparse
import base64
import hashlib
import json
import mimetypes
import shlex
import signal
import time
import urllib.error
import urllib.request
from pathlib import Path

INSTANCES = {'api': 'i-09af311c959d14cc4', 'ai': 'i-07856cc9d2859e4e8'}
BUCKET = 'skn34-lxp-web-711425439897-us-east-1'
DISTRIBUTION = 'E79A6UM0WDCG3'
URL = 'https://d1zqs4mfabqpqs.cloudfront.net'


class RemoteOutcomeUnknown(RuntimeError):
    pass


def wait_command(ssm, command, instance, sleep=time.sleep):
    # Longer than the remote command limit: never roll back while it is still applying.
    for _ in range(250):
        try:
            result = ssm.get_command_invocation(CommandId=command, InstanceId=instance)
        except ssm.exceptions.InvocationDoesNotExist:
            sleep(5)
            continue
        if result['Status'] == 'Success':
            return
        if result['Status'] in ('Failed', 'Cancelled', 'TimedOut'):
            # Remote scripts never print env values; retain diagnostics on the private SSM command.
            raise RuntimeError('SSM command failed: ' + command + ' (' + result['Status'] + ')')
        sleep(5)
    raise RemoteOutcomeUnknown('SSM result unknown; inspect command ' + command + ' before manual recovery')


class Release:
    def __init__(self, session, args):
        self.ssm = session.client('ssm')
        self.s3 = session.client('s3')
        self.cf = session.client('cloudfront')
        self.args = args
        self.previous = {}
        self.modified = []
        self.commands = []

    def remote(self, service, phase):
        source = Path(__file__).with_name('remote_release.py').read_bytes()
        code = 'import base64;exec(compile(base64.b64decode(' + repr(base64.b64encode(source).decode()) + "),'<release>','exec'))"
        argv = ['python3', '-c', code, service, getattr(self.args, service + '_image'), self.args.release, phase]
        result = self.ssm.send_command(InstanceIds=[INSTANCES[service]], DocumentName='AWS-RunShellScript',
            Parameters={'commands':[shlex.join(argv)], 'executionTimeout':['1200']},
            Comment='main deployment ' + phase + ' ' + self.args.release[:40])
        command = result['Command']['CommandId']
        self.commands.append({'service':service, 'phase':phase, 'id':command})
        print(json.dumps(self.commands[-1]), flush=True)
        try:
            wait_command(self.ssm, command, INSTANCES[service])
        except RuntimeError:
            raise
        except Exception as error:
            raise RemoteOutcomeUnknown('Cannot read SSM outcome: ' + command) from error

    def invalidate(self):
        result = self.cf.create_invalidation(DistributionId=DISTRIBUTION, InvalidationBatch={
            'Paths': {'Quantity':1,'Items':['/*']},
            'CallerReference':self.args.release + '-' + str(time.time_ns())})
        self.cf.get_waiter('invalidation_completed').wait(DistributionId=DISTRIBUTION,
            Id=result['Invalidation']['Id'], WaiterConfig={'Delay':10,'MaxAttempts':60})

    def upload_web(self):
        root = Path(self.args.web)
        if not (root / 'index.html').is_file():
            raise RuntimeError('Missing verified frontend artifact')
        paths = sorted(p for p in root.rglob('*') if p.is_file() and p.name != 'index.html') + [root/'index.html']
        for path in paths:
            key = path.relative_to(root).as_posix()
            # Hashed assets remain available for old open tabs and rollbacks.
            if not key.startswith('assets/'):
                try:
                    old = self.s3.get_object(Bucket=BUCKET, Key=key)
                    self.previous[key] = {'Body':old['Body'].read(), 'ContentType':old.get('ContentType','application/octet-stream'), 'CacheControl':old.get('CacheControl','no-cache')}
                except self.s3.exceptions.NoSuchKey:
                    pass
            self.modified.append(key)
            content_type = {'.js':'application/javascript','.css':'text/css'}.get(path.suffix) or mimetypes.guess_type(key)[0] or 'application/octet-stream'
            self.s3.put_object(Bucket=BUCKET, Key=key, Body=path.read_bytes(), ContentType=content_type,
                CacheControl='public,max-age=31536000,immutable' if key.startswith('assets/') else 'no-cache')
        self.invalidate()

    def smoke(self):
        expected = hashlib.sha256((Path(self.args.web)/'index.html').read_bytes()).hexdigest()
        for path in ('/', '/login'):
            with urllib.request.urlopen(URL+path, timeout=30) as response:
                assert response.status == 200
                assert hashlib.sha256(response.read()).hexdigest() == expected, 'CDN index differs'
        try:
            urllib.request.urlopen(URL+'/api/bootstrap', timeout=20)
        except urllib.error.HTTPError as error:
            if error.code == 401:
                return
            raise
        raise RuntimeError('Anonymous API access unexpectedly succeeded')

    def execute(self):
        attempted = []
        try:
            for service in ('ai','api'):
                attempted.append(service)
                self.remote(service, 'prepare')
            self.remote('api', 'drain')
            self.remote('ai', 'apply')
            self.remote('api', 'apply')
            self.upload_web()
            self.smoke()
        except RemoteOutcomeUnknown as error:
            self.record('requires-manual-recovery', [str(error)])
            raise
        except BaseException:
            errors = []
            # Both backends are restored even if one rollback fails.
            for service in attempted:
                try:
                    self.remote(service, 'rollback')
                except Exception as error:
                    errors.append(str(error))
            if self.modified:
                for key, old in self.previous.items():
                    try:
                        self.s3.put_object(Bucket=BUCKET, Key=key, **old)
                    except Exception as error:
                        errors.append(type(error).__name__ + ': restore ' + key)
                try:
                    self.invalidate()
                except Exception as error:
                    errors.append(type(error).__name__ + ': rollback invalidation')
            self.record('failed', errors)
            raise
        self.record('deployed', [])

    def record(self, status, errors):
        Path('release-result.json').write_text(json.dumps({'status':status,'release':self.args.release,
            'api_image':self.args.api_image,'ai_image':self.args.ai_image,'ssm_commands':self.commands,
            'rollback_errors':errors}, indent=2))


def main():
    import boto3
    from remote_release import validate
    parser = argparse.ArgumentParser()
    for name in ('api-image','ai-image','release','web'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    for service in ('api','ai'):
        validate(service, getattr(args,service+'_image'), args.release)
    def interrupted(signum, frame):
        raise RuntimeError('Deployment interrupted; attempting rollback')
    signal.signal(signal.SIGTERM, interrupted)
    Release(boto3.Session(region_name='us-east-1'), args).execute()


if __name__ == '__main__':
    main()
