"""Local request journal: persistent duplicate suppression, never retries crash/pending."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from .local_resume_e2e_data import local_guard, digest


def once(user_id, path, body, operation):
    local_guard()
    request_id=body.get('request_id')
    if not isinstance(request_id,str) or not request_id or len(request_id)>128:
        raise ValueError('AI actions require a stable request_id')
    directory=Path(tempfile.gettempdir())/'resume-e2e-request-journal'
    directory.mkdir(exist_ok=True)
    from django.db import connection
    identity=digest([connection.settings_dict['NAME'],user_id,path,request_id])
    pending=directory/(identity+'.pending'); result_path=directory/(identity+'.json')
    fingerprint=digest(body)
    def replay():
        saved=json.loads(result_path.read_text(encoding='utf-8'))
        if saved['fingerprint']!=fingerprint: raise ValueError('Request ID reused with different input')
        return saved['result']
    if result_path.exists(): return replay()
    try:
        with pending.open('x',encoding='utf-8') as handle: handle.write(fingerprint)
    except FileExistsError:
        if result_path.exists(): return replay()
        raise ValueError('Request already running/failed; no implicit retry')
    # On exceptions pending remains: paid execution is never silently repeated.
    result=operation()
    temporary=directory/(identity+'.tmp')
    temporary.write_text(json.dumps({'fingerprint':fingerprint,'result':result},ensure_ascii=False),encoding='utf-8')
    os.replace(temporary,result_path)
    return result
