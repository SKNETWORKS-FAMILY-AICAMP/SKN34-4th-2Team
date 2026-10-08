"""Local B only: existing review HTTP routes with a v2 service adapter."""
import os
from fastapi import FastAPI, HTTPException
from app import main
from app import resume_apply
from app.local_resume_site_adapter import LocalGateway, LocalReviewService, require_local

require_local()
# Scoped to this standalone process. Production app.main is never modified on disk.
main.build_resume_review_service = lambda: LocalReviewService(main.get_settings(), LocalGateway(main.get_settings()))
main.app.dependency_overrides[main.get_context_gateway] = lambda: LocalGateway(main.get_settings())
main.app.dependency_overrides[resume_apply.gateway_dependency] = lambda: LocalGateway(main.get_settings())
resume_apply.gateway_dependency = lambda: LocalGateway(main.get_settings())
app = FastAPI(title='Local B — Resume Review v2')

@app.post('/resume-review/api/v1/resumes/job-requirements/proxy')
def existing_requirements(request: main.ProxyJobRequirementsRequest):
    from app.matching_handoff import load_selected_job
    from app.job_requirements import load_or_extract_requirements
    from app.review_workflow import ReviewConflict, ReviewInputError
    settings = main.get_settings()
    try:
        job = load_selected_job(settings.matching_job_store_path, request.job_id)
        rows = load_or_extract_requirements(LocalGateway(settings), None, job['text'], job['source'])
        return {'job_id': request.job_id, 'requirements': [r.model_dump() for r in rows]}
    except ReviewConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ReviewInputError as exc:
        raise HTTPException(422, str(exc)) from exc

app.mount('/resume-review', main.app)

# Existing recommendation implementation; no new matching algorithm.
from job_matching_bot.api.main import app as matching_app
app.mount('/', matching_app)
