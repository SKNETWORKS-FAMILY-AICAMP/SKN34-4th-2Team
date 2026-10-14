"""Exactly W1/W2/W3, one run each; W2 has zero LLM calls. No Django/DB.

python -m evaluation.application_writing_live --live --env-file ../.env
Existing checkpoints block resampling. Human judgement deliberately empty.
"""
import argparse
import json
import os
import time
from pathlib import Path
from .application_writing_cases import case
from app.application_writing.engine import run_answer, writer_input
from app.application_writing.llm import StructuredWritingClient
from app.application_writing.models import SemanticResult

HERE=Path(__file__).resolve().parent
RESULTS=HERE/'application_writing_phase4b_results'


def save(path,record):
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')


class RecordingModel:
    def __init__(self,model,record,path): self.model,self.record,self.path=model,record,path
    def with_structured_output(self,schema):
        inner=self.model.with_structured_output(schema,include_raw=True)
        outer=self
        class Call:
            def invoke(self,messages):
                stage='validator' if issubclass(schema,SemanticResult) else 'writer'
                if stage=='writer' and any(c['stage'] in {'writer','rewrite'} for c in outer.record['calls']): stage='rewrite'
                entry=dict(stage=stage,status='started',input_tokens=None,output_tokens=None,latency_ms=None)
                outer.record['calls'].append(entry); save(outer.path,outer.record)
                print(outer.record['case']+' '+stage+' started',flush=True)
                start=time.monotonic()
                try:
                    response=inner.invoke(messages); raw=response['raw']; usage=raw.usage_metadata or {}
                    entry.update(status='returned',input_tokens=usage.get('input_tokens'),output_tokens=usage.get('output_tokens'),
                        latency_ms=round(1000*(time.monotonic()-start)),token_details=usage,provider_model=raw.response_metadata.get('model_name'))
                    parsed=response.get('parsed')
                    if response.get('parsing_error') or parsed is None:
                        entry['status']='parse_failure'; entry['raw_content']=raw.content
                        raise ValueError('Structured output parsing failed')
                    entry['output']=parsed.model_dump(mode='json'); save(outer.path,outer.record)
                    print(outer.record['case']+' '+stage+' returned '+str(entry['latency_ms'])+'ms',flush=True)
                    return parsed
                except Exception as exc:
                    entry.update(status='failed' if entry['status']=='started' else entry['status'],
                        latency_ms=round(1000*(time.monotonic()-start)),error_type=type(exc).__name__)
                    if hasattr(exc,'status_code'): entry['http_status']=exc.status_code
                    # Never persist arbitrary authentication/transport exception text.
                    save(outer.path,outer.record)
                    raise
        return Call()


def render(record):
    request=record['request']; result=record.get('result',{})
    row=request['plan']['assignments'][0]
    sections=[('Question',request['questions']),('Application Plan',request['plan']),
        ('Readiness',result.get('readiness')),('Selected Evidence',request['planning_input']['experiences']),
        ('Applicant Intent / Target Source',request['materials']),('Writer Input',record.get('writer_input')),
        ('Writer Sentences + support_refs',(result.get('candidate') or {}).get('sentences')),
        ('Final Answer',record.get('final_text','')),('Validator Result',result.get('validation')),
        ('Attempts',result.get('attempts')),('LLM Calls / Tokens / Latency',record['calls'])]
    parts=['# '+record['case']+' — Phase 4B','Fictional fixture; no RDS or company browsing.']
    for title,value in sections:
        parts.extend(['\n## '+title,'```json',json.dumps(value,ensure_ascii=False,indent=2),'```'])
    parts.append('\n## Human judgement\n\nFactual Accuracy (GOOD | NEEDS_FIX):\n\nWriting Quality:\n\nQuestion Fit:\n\nWould I submit (YES | NO):\n\nReviewer Notes:\n')
    return '\n'.join(parts)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--live',action='store_true'); parser.add_argument('--env-file',type=Path)
    args=parser.parse_args()
    if not args.live or not args.env_file: parser.error('Explicit --live and --env-file required')
    if any((RESULTS/(name+'.json')).exists() for name in ['W1','W2','W3']):
        parser.error('Existing checkpoint: automatic repeats are prohibited')
    from dotenv import dotenv_values
    env=dotenv_values(args.env_file)
    if not env.get('OPENAI_API_KEY'): parser.error('OpenAI key missing (value not printed)')
    os.environ['LANGSMITH_TRACING']='false'; os.environ['LANGCHAIN_TRACING_V2']='false'
    from langchain_openai import ChatOpenAI
    # Same authorized model/effort as Phase 4A.7, not a multi-model benchmark.
    baseline=json.loads((HERE/'application_planning_phase4a7_results/A-attempt1.json').read_text(encoding='utf-8'))
    model,effort=baseline['model'],baseline['reasoning_effort']
    llm=ChatOpenAI(model=model,reasoning_effort=effort,api_key=env['OPENAI_API_KEY'],max_retries=0,timeout=180)
    RESULTS.mkdir(exist_ok=True)
    records=[]
    for name in ['W1','W2','W3']:
        request=case(name); path=RESULTS/(name+'.json')
        record=dict(case=name,model=model,reasoning_effort=effort,request=request.model_dump(mode='json'),calls=[],status='started')
        save(path,record); start=time.monotonic()
        client=StructuredWritingClient(RecordingModel(llm,record,path))
        result=run_answer(request,name+'-Q1',client)
        record.update(status='finished',result=result.model_dump(mode='json'),final_text=result.final_text,
                      total_latency_ms=round(1000*(time.monotonic()-start)))
        if result.readiness.status=='READY': record['writer_input']=writer_input(request,name+'-Q1')
        save(path,record); (RESULTS/(name+'.md')).write_text(render(record),encoding='utf-8')
        records.append(record)
        print(name+' '+result.status+' calls='+str(len(record['calls'])),flush=True)
    totals=[dict(case=r['case'],status=r['result']['status'],calls=len(r['calls']),
        input_tokens=sum(c.get('input_tokens') or 0 for c in r['calls']),output_tokens=sum(c.get('output_tokens') or 0 for c in r['calls']),
        latency_ms=r['total_latency_ms'],usage_missing_calls=sum(c.get('input_tokens') is None for c in r['calls'])) for r in records]
    save(RESULTS/'usage-summary.json',totals); print(json.dumps(totals),flush=True)


if __name__=='__main__': main()
