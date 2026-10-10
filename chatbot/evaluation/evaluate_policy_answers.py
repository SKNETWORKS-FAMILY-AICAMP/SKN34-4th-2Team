"""Paired supervisor/policy-answer experiment. Default is preparation only.

Uses production supervisor middleware, query selection, retrieval orchestration,
reference expansion and answer formatting, with local policy retrieval adapters.
Notice and personal records are unavailable fixtures, not production data.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import random
import time

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from chatbot import student_chatbot as production
from chatbot.cohort_document_rag import document_namespace, expand_policy_context
from chatbot.evaluation.evaluate_policy_hybrid import load_inputs, rank_case, sha
from chatbot.evaluation.evaluate_policy_rag import LocalIndex, embed_texts, score_evidence, write_json


def cases_for_review(baseline):
    selected = []
    paraphrases = {
        'completion': '수료 출석 기준이 궁금해. 필요한 출석 일수와 비율을 같이 알려줘.',
        'refund': '리소스 비용 환급에 결제 문자만 제출해도 될까? 구독 해지를 놓쳐 초과 결제된 금액도 돌려받을 수 있어?',
    }
    for case in baseline:
        slug = case['id'].split('-', 1)[1]
        if slug not in ('mileage_attendance', 'completion', 'refund'):
            continue
        item = deepcopy(case)
        item['question_origin'] = 'existing'
        if slug in paraphrases:
            item['question'] = paraphrases[slug]
            item['question_origin'] = 'new_paraphrase_existing_topic'
        selected.append(item)
    if len(selected) != 6:
        raise ValueError('Expected exactly six review cases')
    return selected


def build_bot(model):
    # Bypass production constructor: no Pinecone, graph, DB or student loader.
    from langchain_openai import ChatOpenAI
    bot = object.__new__(production.LmsStudentChatbot)
    bot.k = 4
    llm = ChatOpenAI(model=model, use_responses_api=True, max_retries=0,
                     timeout=60, max_tokens=1600, streaming=False)
    bot.supervisor_chain = ChatPromptTemplate.from_messages([
        ('system', production.SUPERVISOR_PROMPT), MessagesPlaceholder('messages'),
    ]) | llm.with_structured_output(production.SupervisorDecision)
    bot.supervisor_middleware = production.RoutingGuardrailMiddleware(production.SupervisorGuardrailMiddleware())
    bot.answer_chain = ChatPromptTemplate.from_messages([
        ('system', production.ANSWER_PROMPT), MessagesPlaceholder('history'),
        ('human', '검색 문맥:\n{context}\n\n학생 질문: {question}'),
    ]) | llm
    return bot


class LocalRetriever:
    def __init__(self, namespace, cohort, rows, embeddings, variant, k):
        self.namespace, self.cohort = namespace, cohort
        self.rows, self.embeddings, self.variant, self.k = rows, embeddings, variant, k

    def invoke(self, query):
        if self.namespace == 'notice':
            return []
        if self.namespace != 'policy':
            raise ValueError('Only policy and empty notice fixtures are supported')
        case = {'id': 'query', 'question': query, 'cohort': self.cohort,
                'expected_behavior': 'abstain', 'required_articles': [], 'evidence': []}
        results = rank_case(case, self.rows, self.embeddings, k=self.k, candidates=max(12, self.k))
        selected = next(r['retrieved'] for r in results if r['variant'] == self.variant)
        docs = [Document(id=r['id'], page_content=r['page_content'], metadata=deepcopy(r['metadata'])) for r in selected]
        namespace = document_namespace(self.rows[0]['metadata']['storage_key'])
        return expand_policy_context(LocalIndex(self.rows, namespace), namespace, self.cohort, docs,
                                     max_extra=8, max_chars=6000)


def run(args):
    # Explicit context overrides tracing enabled by the repository's .env.
    # ThreadPoolExecutor retrieval inherits LangChain context; local adapters
    # make no model calls. All model invocations stay inside this context.
    from langsmith import tracing_context
    with tracing_context(enabled=False):
        return _run(args)


def _run(args):
    out = Path(args.output)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Choose a new empty directory; no automatic resume or retry')
    baseline, corpora, embeddings, source, _ = load_inputs(args.baseline_run, args.cases)
    cases = cases_for_review(baseline)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {'status': 'prepared', 'completed': False, 'case_count': 6,
        'maximum_calls': {'supervisor': 6, 'embedding_batches': 1, 'answers': 12, 'total': 19},
        'attempted_calls': {'supervisor': 0, 'embedding_batches': 0, 'answers': 0},
        'automatic_retries': 0, 'model': args.model, 'max_output_tokens': 1600,
        'source_manifest_sha256': sha(Path(args.baseline_run)/'manifest.json'),
        'implementation_sha256': {str(p): sha(p) for p in (
            Path(__file__), Path(production.__file__), Path(__file__).with_name('evaluate_policy_hybrid.py'),
            Path(__file__).with_name('policy_hybrid.py'))},
        'limitations': ['Local exact search, not Pinecone latency or a deployed end-to-end test.',
            'Notice fixture empty; private records and schedules unavailable, not queried.',
            'Four new phrasings reuse existing topics and are not an independent held-out set.',
            'Shared supervisor decision; production namespace-dependent k and expansion preserved.',
            'Draft documents are not approved operational policy.']}
    write_json(out/'manifest.json', manifest)
    write_json(out/'cases.json', cases)
    if not args.execute:
        return manifest
    states, results, blind, keys = [], [], [], []
    def before_call(kind):
        manifest['attempted_calls'][kind] += 1
        if manifest['attempted_calls'][kind] > manifest['maximum_calls'][kind]:
            raise ValueError('Approved call budget exceeded')
        write_json(out/'manifest.json', manifest)
    try:
        bot = build_bot(args.model)
        for case in cases:
            state = {'question': case['question'], 'cohort': case['cohort'],
                     'messages': [HumanMessage(content=case['question'])]}
            before_call('supervisor')
            state.update(bot._supervisor(state))
            states.append(state)
            write_json(out/'supervisor.json', [
                {k: v for k, v in s.items() if k != 'messages'} for s in states])
            if state['route'] != 'lms' or 'policy' not in state['namespaces'] or 'project_reference' in state['namespaces']:
                raise ValueError('Unsupported routing; preserve decision and stop for review')
        queries = sorted({q for state in states for q in bot._queries_for_namespace(state, 'policy')})
        if len(queries) > 24:
            raise ValueError('More than 24 query texts; stop before embedding call')
        # Dedicated cache copy; never change the approved baseline cache.
        cache = out/'embedding-cache.json'
        cache.write_bytes((Path(args.baseline_run)/'embedding-cache.json').read_bytes())
        missing = [q for q in queries if q not in embeddings]
        if missing:
            before_call('embedding_batches')
            new, usage = embed_texts(missing, source['embedding_model'], cache, source['embedding_dimensions'])
            embeddings.update(new)
            manifest['embedding_usage'] = usage
        for case, base in zip(cases, states):
            # Alternate first arm to reduce systematic execution-order effects.
            order = ['vector', 'hybrid'] if len(results) % 4 == 0 else ['hybrid', 'vector']
            for variant in order:
                state = deepcopy(base)
                state['student_context'] = {'errors': {'evaluation': '공지·개인 기록·확정 일정 미제공. 개인 결과를 확정할 수 없음.'}}
                bot._retriever = lambda namespace, cohort, query, k, on_query=None: LocalRetriever(
                    namespace, cohort, corpora[cohort]['B'], embeddings, variant, k)
                started = time.perf_counter()
                state.update(bot._policy_notice_retrieve(state))
                docs = state['documents']
                before_call('answers')
                answer = bot._answer(state)
                result = {'case_id': case['id'], 'variant': variant,
                    'answer': answer['answer'], 'sources': answer['sources'],
                    'metrics': score_evidence(case, docs), 'answer_model_ms': answer['answer_model_ms'],
                    'retrieval_ms_local_only': state['retrieval_ms'],
                    'paired_arm_seconds': time.perf_counter()-started,
                    'token_in': answer.get('token_in'), 'token_out': answer.get('token_out'),
                    'retrieved': [{'id': d.id, 'page_content': d.page_content, 'metadata': d.metadata} for d in docs]}
                results.append(result)
                review_id = f'review-{len(results):02d}'
                blind.append({'review_id': review_id, 'question': case['question'], 'cohort': case['cohort'],
                    'answer': answer['answer'], 'evidence': result['retrieved'],
                    'checks': case['answer_checks'], 'human_review': {'correct': None,
                    'conditions_exceptions_complete': None, 'grounded': None, 'notes': ''}})
                keys.append({'review_id': review_id, 'case_id': case['id'], 'variant': variant})
                write_json(out/'results.json', results)
                write_json(out/'blind-review-key.json', keys)
                shuffled = deepcopy(blind)
                random.Random(20261010).shuffle(shuffled)
                write_json(out/'blind-review.json', shuffled)
        manifest.update(status='pending_human_review', completed=True)
    except BaseException as exc:
        manifest.update(status='stopped', error_type=type(exc).__name__)
        raise
    finally:
        write_json(out/'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-run', required=True)
    parser.add_argument('--cases', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--model', default='gpt-6-luna')
    parser.add_argument('--execute', action='store_true', help='Requires prior approval for up to 19 API calls')
    print(json.dumps(run(parser.parse_args()), ensure_ascii=False))
