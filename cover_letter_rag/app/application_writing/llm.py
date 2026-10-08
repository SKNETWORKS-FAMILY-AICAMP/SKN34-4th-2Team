"""Injected structured client; never loads environment, keys, DB or production settings."""
import json
from typing import Literal
from pydantic import Field, create_model
from .models import WriterOutput, SemanticResult
from .prompts import WRITER_PROMPT, VALIDATOR_PROMPT


def semantic_schema(payload):
    core=[f['evidence_id'] for f in payload['writer_input']['core']]
    keys=[a['key'] for a in payload['writer_input']['requirements']]
    return create_model('ScopedSemanticResult',__base__=SemanticResult,
        question_id=(Literal[payload['writer_input']['question']['question_id']], ...),
        expressed_core_evidence_ids=(list[Literal[tuple(core)]] if core else list[str],Field(...,max_length=len(core))),
        covered_requirements=(list[Literal[tuple(keys)]], ...))


class StructuredWritingClient:
    def __init__(self, model):
        self.model=model

    def write(self,payload,*,rewrite=None):
        data=dict(material=payload,rewrite=rewrite)
        return self.model.with_structured_output(WriterOutput).invoke([
            ('system',WRITER_PROMPT),('human',json.dumps(data,ensure_ascii=False))])

    def verify(self,payload):
        # The verifier's ID vocabulary is a wire contract, not prose guidance.
        # A result/supporting ID cannot be returned as an expressed CORE ID.
        schema=semantic_schema(payload)
        return self.model.with_structured_output(schema).invoke([
            ('system',VALIDATOR_PROMPT),('human',json.dumps(payload,ensure_ascii=False))])
