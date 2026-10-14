"""Synthetic source-shaped fixtures ONLY. Never import a real person's resume."""
import json
import uuid
from copy import deepcopy
from unittest.mock import patch
from django.test import TestCase, override_settings
from .local_resume_e2e_fixture import seed, EMAIL, PASSWORD
from .local_resume_e2e_data import import_bundle, import_jobs, META, digest as import_digest
from .models import Resumes, ResumeEvidence, ResumeExperiences, ResumeExperienceBindings, Applications
from .application_question_store import digest
from app.job_requirements import requirement_cache_key

ROOT='/api/local/resume-e2e'

class SyntheticReplayClient:
    """Recorded outputs only; NOT heuristic planning or a substitute engine."""
    def __init__(self, user_id, application_id):
        from .application_workspace import open_application
        from .local_resume_e2e_data import META, digest
        from .models import ResumeExperienceBindings, ResumeEvidence
        app = open_application(user_id=user_id, application_id=application_id)
        meta = app.base_resume.content[META]
        self.record = meta.get('recordings', {})
        self.mapping = {'question:'+str(i+1): str(q.pk) for i,q in enumerate(app.questions.order_by('order','pk'))}
        for b in ResumeExperienceBindings.objects.filter(resume=app.base_resume):
            section,index = b.field_path.split('[')
            self.mapping['experience:'+section+':'+index.split(']')[0]] = str(b.experience_id)
        # Imported source IDs never become production identities.
        for source_id in self.record.get('evidence_ids', []):
            f = ResumeEvidence.objects.get(experience__user_id=user_id,
                source_id='local-real:'+digest([app.base_resume.legacy_id,source_id]))
            self.mapping['evidence:'+source_id] = str(f.pk)

    def remap(self, value):
        if isinstance(value,str): return self.mapping.get(value,value)
        if isinstance(value,list): return [self.remap(v) for v in value]
        if isinstance(value,dict): return {k:self.remap(v) for k,v in value.items()}
        return value

    def analyze(self, questions, target):
        from app.application_planning.models import AnalysisBatch
        if 'analysis' not in self.record: raise ValueError('Imported Mock requires recorded Analyzer output; select explicit Live for actual analysis')
        return AnalysisBatch.model_validate(self.remap(self.record['analysis']))

    def plan(self,data):
        from app.application_planning.models import ApplicationPlan
        if 'plan' not in self.record: raise ValueError('Imported Mock requires recorded Planner output; no substitute planner')
        return ApplicationPlan.model_validate(self.remap(self.record['plan']))

    def write(self,payload,*,rewrite=None):
        from app.application_writing.models import WriterOutput
        qid=payload['question']['question_id']
        key=next(k for k,v in self.mapping.items() if k.startswith('question:') and v==qid)
        outputs=self.record.get('writer', {}).get(key, [])
        index=1 if rewrite else 0
        if len(outputs)<=index: raise ValueError('No recorded Mock Writer output; no synthetic quality claim')
        return WriterOutput.model_validate(self.remap(outputs[index]['candidate']))

    def verify(self,payload):
        from app.application_writing.models import SemanticResult
        qid=payload['writer_input']['question']['question_id']
        key=next(k for k,v in self.mapping.items() if k.startswith('question:') and v==qid)
        for item in self.record['writer'][key]:
            if self.remap(item['candidate'])==payload['candidate']:
                return SemanticResult.model_validate(self.remap(item['semantic']))
        raise ValueError('No matching recorded verifier result')


def raw_bundle(source):
    return {k: deepcopy(v) for k,v in source.items() if k not in {'jobs','evidence','recordings','intent_answers'}}


def seed_synthetic_recording(source):
    """UNIT TEST setup only. Never used by document registration/runtime Review."""
    from .resume_experience_store import ensure_resume_item_binding
    resume=import_bundle(raw_bundle(source),approved=True)
    resume=import_jobs(resume.pk,source['jobs'],approved=True)
    for fact in source['evidence']:
        b=ensure_resume_item_binding(user_id=resume.user_id,resume_id=resume.pk,section=fact['section'],index=fact['index'])
        ResumeEvidence.objects.create(experience=b.experience,fact_type=fact['fact_type'],
            normalized_fact=fact['normalized_fact'],evidence_quote=fact['evidence_quote'],
            source_type=fact['source_type'],assertion_state=fact['assertion_state'],
            source_id='local-real:'+import_digest([resume.legacy_id,fact['id']]))
    resume.refresh_from_db()
    resume.content[META]['recordings']=source['recordings']
    resume.save(update_fields=['content'])
    return resume


def bundle(result=True, exaggerate=False):
    job={'job_id':'synthetic-J1','snapshot_hash':'s'*64,'company':'합성 테스트 회사','title':'API 개발',
         'description':'Python 경험 우대. API 개발 업무.', 'preferred_skills':['Python'],
         'questions':[{'order':1,'text':'기술 기여와 결과를 설명하세요.'}]}
    job['requirement_profile']={'key':requirement_cache_key(job),'requirements':[
        {'id':'req-1','group':'preferred','label':'Python 경험','posting_quote':'Python 경험 우대','kind':'skill','kind_basis':'기술'}]}
    facts=[{'id':'action','section':'projects','index':0,'fact_type':'implementation',
        'normalized_fact':'FastAPI 기반 API를 구현했습니다.','evidence_quote':'FastAPI 기반 API를 구현했습니다.',
        'source_text':'FastAPI 기반 API를 구현했습니다.','source_type':'resume_text','assertion_state':'resume_stated'}]
    if result: facts.append({'id':'result','section':'projects','index':0,'fact_type':'result',
        'normalized_fact':'응답 시간이 20% 단축됐습니다.','evidence_quote':'응답 시간이 20% 단축됐습니다.',
        'source_text':'응답 시간이 20% 단축됐습니다.','source_type':'user_answer','assertion_state':'user_asserted'})
    exp='experience:projects:0'; action='evidence:action'; rid='evidence:result'
    assignment={'question_id':'question:1','primary_experience_ids':[exp],'story_focus':'FastAPI 구현',
        'core_evidence_ids':[action],'supporting_evidence_ids':[], 'result_evidence_ids':[rid] if result else [],
        'missing_information':[] if result else [{'key':'result','category':'experience_evidence','target_experience_id':exp,
            'importance':'high','reason':'결과 없음','question_proposal':'실제로 무엇이 달라졌나요?'}], 'rationale':'확인 근거',
        'requirement_coverage':[{'requirement':'technical_contribution','status':'satisfied','evidence_ids':[action],'reason':'직접 구현'},
            {'requirement':'result','status':'satisfied' if result else 'missing','evidence_ids':[rid] if result else [],'reason':'확인된 결과' if result else '결과 없음','blocking_missing_information':'' if result else '결과 없음'}]}
    candidate={'question_id':'question:1','sentences':[{'text':'FastAPI 기반 API를 구현했습니다.' if not exaggerate else 'Python 기반 API를 구현했습니다.',
        'claim_types':['evidence'],'support_refs':[{'source_type':'evidence','source_id':action}]}]}
    if result: candidate['sentences'].append({'text':'응답 시간이 20% 단축됐습니다.','claim_types':['evidence'],'support_refs':[{'source_type':'evidence','source_id':rid}]})
    # Ensure target relevance and provenance are exercised without pretending Python is applicant evidence.
    assignment['story_focus']='FastAPI 구현과 Python 경험 우대 직무의 관련성'
    candidate['sentences'].append({'text':'Python 경험이 우대되는 직무입니다.','claim_types':['target_context'],
        'support_refs':[{'source_type':'target_context','source_id':'req-1'}]})
    record={'candidate':candidate,'semantic':{'question_id':'question:1','factual_issues':[],'quality_issues':[],
        'expressed_core_evidence_ids':[action],'covered_requirements':['technical_contribution','result'],'story_focus_preserved':True}}
    return {'version':1,'permission':'sanitized','source_resume_id':'synthetic:'+str(result)+':'+str(exaggerate),
        'resume':{'title':'합성 이력서 (테스트 전용)','content':{'projects':[{'id':'p1','name':'API 프로젝트','description':facts[0]['source_text']}]}},
        'jobs':[job],'evidence':facts,'recordings':{'evidence_ids':[f['id'] for f in facts],
            'analysis':{'questions':[{'question_id':'question:1','constraints':{'character_limit':None,'count_unit':'characters','include_spaces':None},
                'asks_for':[{'key':'technical_contribution','source_quote':'기술 기여','required':True},{'key':'result','source_quote':'결과','required':True}]}]},
            'plan':{'assignments':[assignment]},'writer':{'question:1':[record,deepcopy(record)]}}}


class RealDataE2ETests(TestCase):
    def setUp(self):
        self.user,self.base,self.role=seed()
        auth=self.client.post(ROOT+'/login',json.dumps({'email':EMAIL,'password':PASSWORD}),content_type='application/json').json()
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer '+auth['access']

    def post(self,path,body=None):
        response=self.client.post(ROOT+path,json.dumps(body or {}),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content.decode()); return response.json()

    def prepared(self,source):
        resume=seed_synthetic_recording(source); job=resume.content[META]['jobs'][0]
        # Fake external clients are unit-test dependencies, not runtime imports.
        for target in ('lms.local_resume_e2e_api.planning_client','lms.local_resume_e2e_ai.writing_client'):
            fake=patch(target,side_effect=lambda *args,**kwargs:SyntheticReplayClient(kwargs['user_id'],kwargs['application_id']))
            fake.start(); self.addCleanup(fake.stop)
        app=self.post('/applications/open-or-create',{'role_id':job['role_id'],'base_resume_id':resume.pk,
            'data_mode':'real','idempotency_key':str(uuid.uuid4())})
        prefix='/applications/'+app['id']
        for step in ['tailored-resume','questions','analyze','plan']: app=self.post(prefix+'/'+step)
        return app,prefix

    def test_import_explicit_idempotent_listing_and_owner(self):
        raw=raw_bundle(bundle())
        with self.assertRaises(ValueError): import_bundle(raw)
        copied=import_bundle(raw,approved=True)
        counts=(Resumes.objects.count(),ResumeEvidence.objects.count(),ResumeExperiences.objects.count())
        self.assertEqual(copied.pk,import_bundle(raw,approved=True).pk)
        self.assertEqual(counts,(Resumes.objects.count(),ResumeEvidence.objects.count(),ResumeExperiences.objects.count()))
        catalog=self.client.get(ROOT+'/catalog').json()
        self.assertEqual(len(catalog['real_resumes']),1); self.assertEqual(catalog['real_jobs'],[])
        self.assertEqual(copied.user_id,self.user.pk)
        changed=raw_bundle(bundle()); changed['resume']['title']='다른 제목'
        with self.assertRaises(ValueError): import_bundle(changed,approved=True)

    def test_r1_ready_provenance_draft_and_request_replay(self):
        app,prefix=self.prepared(bundle()); self.assertTrue(app['requirement_profile_linked'])
        gate=self.client.get(ROOT+prefix+'/writer-readiness').json()
        self.assertEqual(gate['questions'][0]['status'],'READY')
        body={'question_id':app['questions'][0]['id'],'ai_mode':'mock','request_id':str(uuid.uuid4())}
        before=(ResumeExperiences.objects.count(),ResumeEvidence.objects.count())
        with patch('langchain_openai.ChatOpenAI',side_effect=AssertionError('No live')):
            result=self.post(prefix+'/write',body)
        self.assertEqual(result['result']['status'],'READY'); self.assertEqual(result['telemetry']['llm_calls'],0)
        self.assertIn('FastAPI',result['final_text']); self.assertEqual(result,self.post(prefix+'/write',body))
        self.assertEqual(before,(ResumeExperiences.objects.count(),ResumeEvidence.objects.count()))
        self.assertEqual(result['materials'][0]['requirement_source']['requirement']['posting_quote'],'Python 경험 우대')
        self.assertEqual(self.client.get(ROOT+prefix).json()['id'],app['id'])

    def test_r2_result_missing_writer_zero(self):
        app,prefix=self.prepared(bundle(result=False))
        with patch('lms.local_resume_e2e_ai.writing_client',side_effect=AssertionError('must not call')):
            result=self.post(prefix+'/write',{'question_id':app['questions'][0]['id']})
        self.assertEqual(result['result']['status'],'NEEDS_INPUT'); self.assertEqual(result['telemetry']['llm_calls'],0)

    def test_r3_no_python_applicant_fabrication(self):
        app,prefix=self.prepared(bundle(exaggerate=True))
        result=self.post(prefix+'/write',{'question_id':app['questions'][0]['id']})
        self.assertEqual(result['result']['status'],'BLOCKED'); self.assertEqual(result['result']['rewrite_count'],1)
        self.assertTrue(any('unsupported technology' in s for s in result['result']['validation']['factual_issues']))

    def test_stale_inactive_blocks_before_writer(self):
        app,prefix=self.prepared(bundle())
        ResumeEvidence.objects.filter(source_id__startswith='local-real:').update(assertion_state='superseded')
        with patch('lms.local_resume_e2e_ai.writing_client',side_effect=AssertionError('must not call')):
            result=self.post(prefix+'/write',{'question_id':app['questions'][0]['id']})
        self.assertEqual(result['result']['status'],'BLOCKED')

    def test_import_remote_guard(self):
        with patch('lms.local_resume_e2e_data.connection.settings_dict',{'HOST':'db.rds.amazonaws.com'}):
            with self.assertRaises(RuntimeError): import_bundle(bundle(),approved=True)

    def test_raw_resume_registers_without_manual_evidence_and_later_job_append_reuses(self):
        source=bundle(); raw=raw_bundle(source); jobs=source['jobs']
        resume=import_bundle(raw,approved=True)
        before=(ResumeExperiences.objects.count(),ResumeEvidence.objects.count())
        self.assertFalse(ResumeEvidence.objects.filter(experience__resume_bindings__resume=resume).exists())
        self.assertFalse(ResumeExperienceBindings.objects.filter(resume=resume).exists())
        self.assertEqual(import_jobs(resume.pk,jobs,approved=True).pk,resume.pk)
        self.assertEqual(before,(ResumeExperiences.objects.count(),ResumeEvidence.objects.count()))
        self.assertEqual(len(import_bundle(raw,approved=True).content[META]['jobs']),1)

    def test_existing_analyst_extracts_raw_resume_only_on_explicit_live_and_checks_quote(self):
        source=bundle(); resume=import_bundle(raw_bundle(source),approved=True)
        self.assertFalse(ResumeExperienceBindings.objects.filter(resume=resume).exists())
        resume=import_jobs(resume.pk,source['jobs'],approved=True); job=resume.content[META]['jobs'][0]
        app=self.post('/applications/open-or-create',{'role_id':job['role_id'],'base_resume_id':resume.pk,'data_mode':'real','idempotency_key':'raw-app'})
        self.assertEqual(app['experiences'],[])
        self.assertFalse(app['registration']['experience_initialized'])
        from app.resume_review_v2.models import AnalystOutput, Evidence, RevisionPlan, Usage
        class Analyst:
            def __init__(self,*args): pass
            def analyze(self,data):
                eid=data.experience.experience_id
                fact=Evidence(evidence_id='extracted',experience_id=eid,fact_type='implementation',
                    normalized_fact=data.experience.current_text,evidence_quote=data.experience.current_text,
                    source_type='resume_text',source_id=eid,assertion_state='resume_stated')
                return AnalystOutput(experience_id=eid,extracted_evidence=[fact],plan=RevisionPlan(
                    objective='source facts',operation='no_change',core_evidence_ids=['extracted'])),Usage(calls=1)
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fake-test-key'}), patch('app.resume_review_v2.llm.LangChainReviewLLM',Analyst):
            result=self.post('/applications/'+app['id']+'/extract-evidence',{'item_key':'projects:p1','ai_mode':'live','request_id':str(uuid.uuid4())})
        self.assertEqual(len(result['experiences'][0]['evidence']),1)
        self.assertEqual(result['experiences'][0]['evidence'][0]['assertion_state'],'resume_stated')
        self.assertTrue(result['registration']['experience_initialized'])
        self.assertEqual(result['review']['usage']['calls'],1)

    def test_semantic_payloads_rejected_before_any_registration(self):
        before=(Resumes.objects.count(),ResumeExperiences.objects.count(),ResumeEvidence.objects.count())
        for field in ('evidence','jobs','recordings','intent_answers','experiences','target_context'):
            raw=raw_bundle(bundle()); raw[field]=['must not import']
            with self.assertRaises(ValueError): import_bundle(raw,approved=True)
        self.assertEqual(before,(Resumes.objects.count(),ResumeExperiences.objects.count(),ResumeEvidence.objects.count()))

    def test_docx_txt_registration_uses_site_fields_without_analysis(self):
        import tempfile
        from pathlib import Path
        from zipfile import ZipFile
        from xml.etree import ElementTree as ET
        from .local_resume_document import W,document_bundle
        lines=['가상 지원자','핵심 역량','Python 활용','기술스택','Python, SQL',
            '프로젝트 1. 사용자 이탈 예측','약 99만 건의 데이터에서 이탈 비율이 약 6.4%였습니다.',
            '자기소개','원문 자기소개입니다.','지원동기','원문 지원동기입니다.']
        before=(ResumeExperiences.objects.count(),ResumeEvidence.objects.count(),ResumeExperienceBindings.objects.count(),Applications.objects.count())
        with tempfile.TemporaryDirectory() as folder:
            for ext in ('txt','docx'):
                path=Path(folder)/('resume.'+ext)
                if ext=='txt': path.write_text('\n'.join(lines),encoding='utf-8')
                else:
                    doc=ET.Element(W+'document'); body=ET.SubElement(doc,W+'body')
                    for line in lines:
                        ET.SubElement(ET.SubElement(ET.SubElement(body,W+'p'),W+'r'),W+'t').text=line
                    with ZipFile(path,'w') as archive: archive.writestr('word/document.xml',ET.tostring(doc))
                data=document_bundle(path,title='일반 등록 이력서',source_id='synthetic-document-'+ext)
                resume=import_bundle(data,approved=True)
                self.assertEqual(resume.content['projects'][0]['description'],lines[6])
                self.assertEqual(resume.content['coreCompetencies']['text'],'Python 활용')
                self.assertEqual(resume.content['selfIntroduction']['intro']['body'],lines[8])
                self.assertEqual(resume.content['selfIntroduction']['motivation']['body'],lines[10])
                self.assertEqual(resume.content['techStack'][0]['level'],'')
                self.assertEqual(data['resume']['content'],document_bundle(path,title='일반 등록 이력서',source_id='synthetic-document-'+ext)['resume']['content'])
        self.assertEqual(before,(ResumeExperiences.objects.count(),ResumeEvidence.objects.count(),ResumeExperienceBindings.objects.count(),Applications.objects.count()))
