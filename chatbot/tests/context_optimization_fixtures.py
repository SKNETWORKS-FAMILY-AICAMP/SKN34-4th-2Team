"""Synthetic policy/calendar fixtures; no production DB or personal records."""
from copy import deepcopy
from datetime import date
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from chatbot.tests.test_active_policy_rules import uploaded
from chatbot.firebase_student_context import load_unit_period_context
from chatbot.attendance import enrich_unit_period_context


def fixture(threshold=80, conversion=3, missing=False):
    cohort = 'cohort_34' if threshold == 80 else 'cohort_40'
    snapshot = uploaded(cohort, threshold, conversion)
    # 14 past scheduled days and four future days, matching a known scenario.
    dates = [date(2026, 9, d) for d in (16,17,18,21,22,23,24,25,28,29,30)]
    dates += [date(2026, 10, d) for d in (1,2,9,12,13,14,15)]
    records = [{'attendance_date': d, 'status': 'late' if i < 5 else 'present'}
               for i, d in enumerate(dates[:14])]
    if missing:
        records.pop()
    cur = MagicMock()
    def execute(sql, args):
        result = MagicMock()
        if 'start_date, end_date' in sql:
            result.fetchone.return_value = {'start_date':date(2026,6,16), 'end_date':date(2026,12,8)}
        elif 'curriculum_sheets' in sql:
            result.fetchone.return_value = {'id':1}
        elif 'curriculum_rows' in sql:
            return [{'date_label':d.isoformat()} for d in dates]
        elif 'FROM attendances' in sql:
            return deepcopy(records)
        else:
            raise AssertionError(sql)
        return result
    cur.execute.side_effect = execute
    with patch('chatbot.firebase_student_context._connect') as conn, \
         patch('chatbot.firebase_student_context._cohort_ids',return_value=(1,cohort)), \
         patch('chatbot.firebase_student_context._user_id',return_value=1), \
         patch('chatbot.active_policy_rules.load_active_snapshot',return_value=snapshot):
        conn.return_value.__enter__.return_value.cursor.return_value = cur
        session = {'uid':'synthetic-only','cohort':cohort}
        shared = load_unit_period_context(session,today=date(2026,10,10),include_attendance=False)
        private = enrich_unit_period_context(load_unit_period_context(session,today=date(2026,10,10),include_record_details=True))
    question = '이번 단위기간 출석 어때? 앞으로 며칠 더 정상 출석해야 해? 다음 수업에 지각하면 어떻게 돼?'
    documents = [Document(page_content=c['evidence'],metadata={'_namespace':'policy',
        'doc_id':str(i), 'cohort':cohort,'document_hash':c['document_hash'],
        'storage_key':snapshot['storage_key'],'approval_status':'unverified'})
        for i,c in enumerate(snapshot['criteria'].values())]
    return {'cohort':cohort,'question':question,'messages':[HumanMessage(content=question)],
        'unit_period_context':shared,'student_context':{'requested_scopes':['student_attendance'],
        'data':{'student_attendance':{'unit_period_context':private}}},'documents':documents}
