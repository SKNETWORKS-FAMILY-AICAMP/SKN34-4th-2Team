from app.models import TailoredResumeCreateRequest
from app.tailored_resumes import TailoredResumeService
from app.firebase_gateway import tailored_resume_title


class Gateway:
    def __init__(self):
        self.items = {}

    def create_tailored_resume(self, cohort_id, resume_id, uid, source):
        key = (cohort_id, resume_id, source['job_id'], source['snapshot_hash'])
        if key not in self.items:
            self.items[key] = {
                'tailored_resume_id': 'tailored-1', 'baseResumeId': resume_id,
                'jobId': source['job_id'], 'companyName': source['company'], 'jobTitle': source['title'],
                'sourceResumeHash': 'resume-hash', 'jobSnapshotHash': source['snapshot_hash'],
                'status': 'draft', 'title': 'A사 맞춤 이력서',
                'content': {'projects': [{'description': '원본 경험'}]},
                'reviewSession': {},
            }
        return self.items[key]

    def list_tailored_resumes(self, cohort_id, resume_id, uid):
        return list(self.items.values())

    def get_owned_tailored_resume(self, cohort_id, resume_id, tailored_resume_id, uid):
        return next(
            item for item in self.items.values()
            if item['tailored_resume_id'] == tailored_resume_id
        )

    def delete_tailored_resume(self, cohort_id, resume_id, tailored_resume_id, uid):
        self.get_owned_tailored_resume(cohort_id, resume_id, tailored_resume_id, uid)
        key = next(
            key for key, item in self.items.items()
            if item['tailored_resume_id'] == tailored_resume_id
        )
        del self.items[key]


def test_creates_idempotent_job_specific_resume_draft():
    calls = []
    def load(job_id):
        calls.append(job_id)
        return {'source': {'job_id': job_id, 'company': 'A사', 'title': '백엔드 개발자', 'snapshot_hash': 'job-hash'}}

    service = TailoredResumeService(Gateway(), load)
    request = TailoredResumeCreateRequest(cohort_id='cohort-1', resume_id='resume-1', selected_job_id='job-1')
    first, second = service.create('user-1', request), service.create('user-1', request)

    assert first.tailored_resume_id == second.tailored_resume_id
    assert first.base_resume_id == 'resume-1'
    assert first.company_name == 'A사'
    assert first.content['projects'][0]['description'] == '원본 경험'
    assert calls == ['job-1', 'job-1']


def test_lists_only_saved_tailored_resume_metadata():
    service = TailoredResumeService(Gateway(), lambda job_id: {'source': {'job_id': job_id, 'company': 'A사', 'title': '개발자', 'snapshot_hash': 'job-hash'}})
    service.create('user-1', TailoredResumeCreateRequest(cohort_id='c', resume_id='r', selected_job_id='job'))
    item = service.list('user-1', 'c', 'r')[0]
    assert item.job_id == 'job'
    assert item.status == 'draft'
    assert item.review_progress == 'not_started'


def test_restores_saved_tailored_review_session():
    gateway = Gateway()
    service = TailoredResumeService(gateway, lambda job_id: {'source': {'job_id': job_id, 'company': 'A사', 'title': '개발자', 'snapshot_hash': 'job-hash'}})
    created = service.create('user-1', TailoredResumeCreateRequest(cohort_id='c', resume_id='r', selected_job_id='job'))
    gateway.items[('c', 'r', 'job', 'job-hash')]['reviewSession'] = {
        'version': 1, 'result': {'review_id': 'review-1'}, 'completed': False,
    }

    restored = service.get('user-1', 'c', 'r', created.tailored_resume_id)

    assert restored.review_session['result']['review_id'] == 'review-1'
    assert service.list('user-1', 'c', 'r')[0].review_progress == 'in_progress'


def test_tailored_title_uses_company_value():
    base = {
        'title': '백엔드 기본 이력서',
        'content': {'basicInfo': {'name': '김민준'}},
    }

    assert tailored_resume_title(base, '토마토에이아이') == (
        '토마토에이아이 맞춤 이력서'
    )
    assert tailored_resume_title(base, '') == '백엔드 기본 이력서'


def test_tailored_title_does_not_invent_missing_student_name():
    base = {'title': '기본 이력서', 'content': {'basicInfo': {'name': ''}}}

    assert tailored_resume_title(base, '토마토에이아이') == (
        '토마토에이아이 맞춤 이력서'
    )


def test_deletes_only_the_selected_tailored_resume():
    gateway = Gateway()
    service = TailoredResumeService(gateway, lambda job_id: {
        'source': {'job_id': job_id, 'company': 'A사', 'title': '개발자', 'snapshot_hash': job_id},
    })
    first = service.create('user-1', TailoredResumeCreateRequest(cohort_id='c', resume_id='r', selected_job_id='job-1'))
    service.create('user-1', TailoredResumeCreateRequest(cohort_id='c', resume_id='r', selected_job_id='job-2'))

    gateway.delete_tailored_resume('c', 'r', first.tailored_resume_id, 'user-1')

    remaining = service.list('user-1', 'c', 'r')
    assert len(remaining) == 1
    assert remaining[0].job_id == 'job-2'
