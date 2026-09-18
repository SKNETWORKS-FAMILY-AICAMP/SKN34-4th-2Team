"""Create and list company-specific resume drafts without mutating the base resume."""
from collections.abc import Callable

from app.firebase_gateway import FirebaseGateway
from app.models import TailoredResumeCreateRequest, TailoredResumeResponse, TailoredResumeSummary


def _summary(data: dict) -> TailoredResumeSummary:
    session = data.get('reviewSession') or {}
    progress = (
        'completed' if session.get('completed') is True
        else 'in_progress' if session.get('result')
        else 'not_started'
    )
    return TailoredResumeSummary(
        tailored_resume_id=data['tailored_resume_id'],
        base_resume_id=data['baseResumeId'],
        job_id=data['jobId'],
        company_name=data.get('companyName', ''),
        job_title=data.get('jobTitle', ''),
        title=data.get('title', ''),
        source_resume_hash=data['sourceResumeHash'],
        job_snapshot_hash=data['jobSnapshotHash'],
        status=data.get('status', 'draft'),
        review_progress=progress,
        workspace_resume_id=data.get('workspaceResumeId', ''),
    )


class TailoredResumeService:
    def __init__(self, gateway: FirebaseGateway, job_loader: Callable[[str], dict]) -> None:
        self._gateway = gateway
        self._job_loader = job_loader

    def create(self, uid: str, request: TailoredResumeCreateRequest) -> TailoredResumeResponse:
        job = self._job_loader(request.selected_job_id)
        data = self._gateway.create_tailored_resume(request.cohort_id, request.resume_id, uid, job['source'])
        return TailoredResumeResponse(
            **_summary(data).model_dump(),
            content=data.get('content') or {},
            review_session=data.get('reviewSession') or {},
        )

    def list(self, uid: str, cohort_id: str, resume_id: str) -> list[TailoredResumeSummary]:
        return [_summary(data) for data in self._gateway.list_tailored_resumes(cohort_id, resume_id, uid)]

    def get(
        self, uid: str, cohort_id: str, resume_id: str, tailored_resume_id: str,
    ) -> TailoredResumeResponse:
        data = self._gateway.get_owned_tailored_resume(
            cohort_id, resume_id, tailored_resume_id, uid,
        )
        data = {'tailored_resume_id': tailored_resume_id, **data}
        return TailoredResumeResponse(
            **_summary(data).model_dump(),
            content=data.get('content') or {},
            review_session=data.get('reviewSession') or {},
        )
