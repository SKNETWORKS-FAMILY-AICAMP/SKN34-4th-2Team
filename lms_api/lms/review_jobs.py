"""Short HTTP polling over the existing Celery/Redis deployment and v2 checkpoints."""
import hashlib
import json
import time
import uuid

import redis
from celery import shared_task
from django.conf import settings
from ninja.responses import Response

TTL = 3600


def store():
    return redis.Redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True,
                               socket_connect_timeout=2, socket_timeout=2)


def job_key(payload, attempt):
    # Includes the authenticated identity, owning resume and complete request.
    encoded = json.dumps([payload, attempt], sort_keys=True, ensure_ascii=False)
    return 'resume-review:async:' + hashlib.sha256(encoded.encode()).hexdigest()


def submit_or_poll(payload, attempt):
    key = job_key(payload, attempt)
    db = store()
    queued = json.dumps({'state': 'queued', 'stage': 'analyze', 'started': time.time()})
    if db.set(key, queued, nx=True, ex=TTL):
        try:
            run_review_job.apply_async(args=[key, payload])
        except Exception:
            db.delete(key)
            return Response({'detail': '첨삭 작업을 접수하지 못했습니다. 잠시 후 다시 시도해 주세요.'}, status=503)
    row = json.loads(db.get(key) or queued)
    if row['state'] == 'complete':
        return row['response']
    if row['state'] == 'failed':
        return Response({'detail': row['detail']}, status=row.get('status', 503))
    elapsed = max(0, int(time.time() - row['started']))
    if elapsed > 1800:
        return Response({'detail': '첨삭 작업 응답을 확인하지 못했습니다. 저장된 처리 재개를 눌러 주세요.'}, status=503)
    return {'async_job': {'state': row['state'], 'stage': row.get('stage'), 'elapsed_seconds': elapsed}}


@shared_task(bind=True, max_retries=70, ignore_result=True, acks_late=True, reject_on_worker_lost=True,
             soft_time_limit=1800, time_limit=1860)
def run_review_job(self, key, payload):
    from lms.api import _review_call
    db = store()
    token = uuid.uuid4().hex
    # A redelivered Celery message cannot run alongside its original worker.
    lease = key + ':worker'
    if not db.set(lease, token, nx=True, ex=1900):
        raise self.retry(countdown=30)
    row = json.loads(db.get(key) or '{}')
    if not row or row.get('state') == 'complete':
        db.delete(lease)
        return
    started = row.get('started', time.time())
    def save(**data):
        db.set(key, json.dumps({'started': started, **data}, ensure_ascii=False), ex=TTL)
    try:
        payload = dict(row.get('continuation') or payload)
        save(state='running', stage=row.get('stage', 'analyze'), continuation=payload)
        busy_retries = 0
        for _ in range(8):
            while True:
                response = _review_call('/api/v1/resumes/reviews/proxy', payload, timeout=600)
                if isinstance(response, Response):
                    detail = json.loads(response.content).get('detail', '첨삭 처리 실패')
                    if response.status_code == 409 and detail == 'review_stage_busy' and busy_retries < 60:
                        busy_retries += 1
                        time.sleep(5)
                        continue
                    save(state='failed', status=response.status_code, detail=detail)
                    return
                break
            execution = (response.get('telemetry') or {}).get('execution')
            if not execution or execution.get('state') == 'verified':
                save(state='complete', response=response)
                return
            if execution.get('retryable_error'):
                # Return the existing validation-pending contract; never approve it.
                save(state='complete', response=response)
                return
            payload['request_id'] = response['review_id']
            save(state='running', stage=execution.get('stage', 'write'), continuation=payload)
        save(state='failed', status=503, detail='저장된 단계부터 처리를 재개해 주세요.')
    except Exception:
        save(state='failed', status=503, detail='첨삭 작업이 중단됐습니다. 저장된 단계부터 재개해 주세요.')
    finally:
        db.eval("if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) end return 0", 1, lease, token)
