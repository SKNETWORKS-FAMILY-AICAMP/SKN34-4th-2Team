"""Check preserved live records against final contracts without any LLM/network/DB."""
import json
from .application_writing_live import RESULTS, save
from app.application_writing.models import WriteRequest, WriterOutput
from app.application_writing.engine import readiness,writer_input,deterministic_validation,merge_semantic
from app.application_writing.llm import semantic_schema


def main():
    results=[]
    for name in ['W1','W2','W3']:
        record=json.loads((RESULTS/(name+'.json')).read_text(encoding='utf-8'))
        request=WriteRequest.model_validate(record['request']); qid=name+'-Q1'
        row=dict(case=name,readiness=readiness(request,qid).model_dump(),attempts=[])
        for original in record['result']['attempts']:
            candidate=WriterOutput.model_validate(original['candidate'])
            checked=deterministic_validation(request,qid,candidate)
            semantic=original.get('semantic'); contract='not_called'
            if semantic:
                try:
                    value=semantic_schema(dict(writer_input=writer_input(request,qid))).model_validate(semantic)
                    checked=merge_semantic(request,qid,checked,value); contract='valid'
                except ValueError:
                    contract='INVALID_VERIFIER_CONTRACT'
            row['attempts'].append(dict(deterministic_and_semantic=checked.model_dump(),semantic_contract=contract))
        results.append(row)
    save(RESULTS/'offline-recheck.json',dict(note='No new generation. Historical live results not overwritten.',cases=results))
    print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
