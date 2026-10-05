"""Semantic value is judged with extraction; code enforces ownership and sources.

Empty rhetorical/profile slots are diagnostics, never permission to ask a user.
One candidate per experience avoids queuing questions before hearing the answer.
"""
import re
from .project_planning import active_facts


def approved_question(question, evidence):
    active = active_facts(evidence)
    if not question.question.strip() or not question.why_needed.strip() or not question.dedupe_key.strip():
        return False
    if any(f.experience_id != question.experience_id for f in evidence.values()):
        return False
    if any(eid not in active for eid in question.evidence_basis):
        return False
    if question.gap_type == 'clarification' and not question.evidence_basis:
        return False
    for premise in question.presuppositions:
        if not premise.evidence_ids or any(eid not in question.evidence_basis for eid in premise.evidence_ids):
            return False
        if not any(premise.fact == active[eid].normalized_fact for eid in premise.evidence_ids):
            return False
    return True


def select_question(request, candidate, evidence):
    if candidate is None or candidate.experience_id != request.experience.experience_id:
        return []
    if not approved_question(candidate, evidence) or candidate.target_slot in request.unavailable_slots:
        return []
    question = candidate.model_copy(deep=True)
    prefix = request.experience.experience_id + ':value:'
    if not question.dedupe_key.startswith(prefix):
        question.dedupe_key = prefix + question.dedupe_key
    # This is only an exact-repeat backstop. Semantic repetition/value is judged
    # over original text and answer history in the existing analysis call.
    normalize = lambda text: re.sub(r'\W+', '', text).casefold()
    if question.dedupe_key in request.previous_question_keys or any(
            normalize(question.question) == normalize(old) for old in request.question_history):
        return []
    question.experience_title = request.experience.title
    return [question]
