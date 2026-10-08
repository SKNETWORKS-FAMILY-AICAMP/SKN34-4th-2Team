"""Local B safety wrapper around the same runtime used by the production API."""
import os
from app.resume_review_runtime import (
    PostgresReviewGateway, ResumeReviewV2Service, public_gap_question,
    answer_question_context, experience_outcomes, historical_source_proof,
    targets, experience_sources,
)


def require_local():
    if os.environ.get('RESUME_REVIEW_ENGINE') != 'v2-local' or os.environ.get('DB_HOST') not in ('127.0.0.1', 'localhost'):
        raise RuntimeError('Local B refuses non-loopback DB / non-v2 configuration')


class LocalGateway(PostgresReviewGateway):
    def __init__(self, settings):
        require_local()
        super().__init__(settings)

    def _pg(self):
        require_local()
        return super()._pg()


class LocalReviewService(ResumeReviewV2Service):
    allow_requirement_extraction = False

    def __init__(self, settings, gateway, engine=None):
        require_local()
        super().__init__(settings, gateway, engine)

    def _review_as(self, uid, request):
        require_local()
        return super()._review_as(uid, request)
