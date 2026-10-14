"""Select one review storage implementation for review, context and apply/undo."""
from app.firebase_gateway import FirebaseGateway


def build_review_gateway(settings):
    if settings.resume_review_engine == 'v1':
        return FirebaseGateway(settings)
    if settings.resume_review_engine == 'v2-local':
        from app.local_resume_site_adapter import LocalGateway
        return LocalGateway(settings)
    from app.resume_review_runtime import PostgresReviewGateway
    return PostgresReviewGateway(settings)


def build_review_service(settings):
    gateway = build_review_gateway(settings)
    if settings.resume_review_engine == 'v1':
        from app.resume_review import ResumeReviewService
        return ResumeReviewService(settings, gateway)
    if settings.resume_review_engine == 'v2-local':
        from app.local_resume_site_adapter import LocalReviewService
        return LocalReviewService(settings, gateway)
    from app.resume_review_runtime import ResumeReviewV2Service
    return ResumeReviewV2Service(settings, gateway)
