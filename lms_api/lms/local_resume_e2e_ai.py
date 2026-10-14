"""Replay Phase 4A.7 through existing validators, not a second Planner."""
import json
import os
from django.conf import settings
from .local_resume_e2e_fixture import ROOT, fixture
from . import application_question_store  # establishes existing core module path
from app.application_planning.models import AnalysisBatch, ApplicationPlan


class RecordedMockClient:
    def __init__(self):
        self.record = json.loads((ROOT / 'cover_letter_rag/evaluation/local_mock_planning.json').read_text(encoding='utf-8'))
        self.mapping = {}

    def remap(self, value):
        if isinstance(value, str): return self.mapping.get(value, value)
        if isinstance(value, list): return [self.remap(x) for x in value]
        if isinstance(value, dict): return {k: self.remap(v) for k, v in value.items()}
        return value

    def analyze(self, questions, target_context):
        if [q.raw_text for q in questions] != fixture()['questions']:
            raise ValueError('Mock supports only the seeded A questions; use explicit live mode for other content')
        self.mapping.update({f'A-Q{i+1}': q.question_id for i, q in enumerate(questions)})
        return AnalysisBatch.model_validate(self.remap(self.record['raw_analyzer_output']))

    def plan(self, data):
        self.mapping.update({f'A-Q{i+1}': q.question_id for i, q in enumerate(data.questions)})
        for source in fixture()['experiences']:
            current = next((e for e in data.experiences if e.title == source['title']), None)
            if current is None: raise ValueError('Mock fixture Experience is missing')
            self.mapping[source['experience_id']] = current.experience_id
            for fact in source['evidence']:
                actual = next((f for f in current.evidence if f.normalized_fact == fact['normalized_fact']), None)
                if actual is None: raise ValueError('Mock fixture Evidence changed; mock cannot fabricate it')
                self.mapping[fact['evidence_id']] = actual.evidence_id
        return ApplicationPlan.model_validate(self.remap(self.record['raw_planner_output']))




def execution_mode(mode=None):
    mode=mode or settings.LOCAL_AI_MODE
    if mode not in {'mock','live'}: raise ValueError('Explicit mock/live mode required')
    return mode


def live_model():
    if not os.environ.get('OPENAI_API_KEY'): raise ValueError('Live mode requires explicit OPENAI_API_KEY')
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=os.environ.get('LOCAL_AI_MODEL', 'gpt-6-luna'),
        reasoning_effort=os.environ.get('LOCAL_AI_REASONING_EFFORT', 'medium'), max_retries=0, timeout=180)


def planning_client(mode=None, *, user_id=None, application_id=None):
    if execution_mode(mode) == 'mock':
        if application_id:
            from .application_workspace import open_application
            from .local_resume_e2e_data import META
            app=open_application(user_id=user_id,application_id=application_id)
            if META in app.base_resume.content:
                raise ValueError('Real resume requires explicit Live analysis; no injected Mock matching results')
        return RecordedMockClient()
    # No root .env loading, no implicit paid fallback. Existing production client.
    from app.application_planning.engine import StructuredPlanningClient
    return StructuredPlanningClient(live_model())


def writing_client(mode, *, user_id, application_id):
    if execution_mode(mode)=='mock':
        from .application_workspace import open_application
        from .local_resume_e2e_data import META
        if META in open_application(user_id=user_id,application_id=application_id).base_resume.content:
            raise ValueError('Real resume requires explicit Live Writer; no preselected fixture evidence')
        return FixtureWritingReplay(user_id,application_id)
    from app.application_writing.llm import StructuredWritingClient
    return StructuredWritingClient(live_model())


class FixtureWritingReplay:
    def __init__(self,user_id,application_id):
        self.mock=RecordedMockClient()
        data,_=application_question_store.planning_input(user_id=user_id,application_id=application_id)
        self.mock.plan(data)  # Establish the SAME fixture->owned DB remapping; no new plan saved.
        self.record=json.loads((ROOT/'cover_letter_rag/evaluation/local_mock_writer.json').read_text(encoding='utf-8'))
        self.current=None

    def write(self,payload,*,rewrite=None):
        from app.application_writing.models import WriterOutput
        key=next((k for k,v in self.mock.mapping.items() if k.startswith('A-Q') and v==payload['question']['question_id']),None)
        if key not in self.record: raise ValueError('No recorded Writer for this fictional question')
        self.current=self.record[key]
        return WriterOutput.model_validate(self.mock.remap(self.current['candidate']))

    def verify(self,payload):
        from app.application_writing.models import SemanticResult
        if self.mock.remap(self.current['candidate'])!=payload['candidate']: raise ValueError('Recorded candidate mismatch')
        return SemanticResult.model_validate(self.mock.remap(self.current['semantic']))
