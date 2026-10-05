"""Reconcile turn-local extraction IDs before the unchanged source validators."""
import hashlib
from .validation import ContractError


def reconcile_extraction(request, extraction):
    result = extraction.model_copy(deep=True)
    scope = hashlib.sha256((request.experience.experience_id + '\n' +
        request.answer_source_id + '\n' + request.answer).encode()).hexdigest()[:16]

    def reconcile(rows, previous, id_field, applicant=False):
        old = {getattr(r, id_field): r for r in previous}
        ids = [getattr(r, id_field) for r in rows]
        if len(ids) != len(set(ids)):
            raise ContractError('duplicate extraction ID within one turn')
        kept, mapping = [], {}
        occupied = set(old) | set(ids)
        for row in rows:
            key = getattr(row, id_field)
            prior = old.get(key)
            if prior is not None:
                if row.model_dump(exclude={'created_at', 'updated_at'}) == prior.model_dump(exclude={'created_at', 'updated_at'}):
                    continue  # A verbatim echo adds no claim; preserve the canonical object.
                if applicant and not (row.source_type == 'user_answer'
                        and row.source_id == request.answer_source_id):
                    # Never overwrite/revive a prior source claim using a changed paraphrase.
                    raise ContractError('conflicting reuse of persisted claim ID')
                replacement = f'turn:{scope}:{key}'
                while replacement in occupied:
                    replacement += ':new'
                occupied.add(replacement)
                mapping[key] = replacement
                setattr(row, id_field, replacement)
            kept.append(row)
        return kept, mapping

    result.extracted_evidence, facts = reconcile(result.extracted_evidence,
        request.experience.existing_evidence, 'evidence_id', True)
    result.intent_claims, intents = reconcile(result.intent_claims, request.existing_intents, 'id', True)
    for facet in result.facets:
        facet.evidence_id = facts.get(facet.evidence_id, facet.evidence_id)
    for unit in result.semantic_units:
        for ref in unit.source_refs:
            mapping = facts if ref.type == 'applicant_evidence' else intents if ref.type == 'applicant_intent' else {}
            ref.id = mapping.get(ref.id, ref.id)
    result.semantic_units, _ = reconcile(result.semantic_units, request.previous_semantic_units, 'id')
    if result.question:
        result.question.evidence_basis = [facts.get(i, i) for i in result.question.evidence_basis]
        for premise in result.question.presuppositions:
            premise.evidence_ids = [facts.get(i, i) for i in premise.evidence_ids]
    # supersedes/conflicts point to persisted claims, not this turn's local IDs.
    return result
