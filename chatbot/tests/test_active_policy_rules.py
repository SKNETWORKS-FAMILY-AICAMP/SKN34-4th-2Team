import json
from datetime import date, timedelta
from unittest import TestCase
from unittest.mock import MagicMock, patch

from chatbot.tests.test_regulation_ingestion import regulation_bytes, upload_records
from chatbot.active_policy_rules import criteria_snapshot, allowance_rules, load_active_snapshot, completion_progress
from chatbot.firebase_student_context import load_unit_period_context
from chatbot.attendance import enrich_unit_period_context


def uploaded(cohort='cohort_34', threshold=80, conversion=3, upload='a'):
    data = regulation_bytes([
        ('제5조(단위기간의 산정)', [
            '단위기간은 훈련 시작일을 기준으로 매월 같은 일자부터 다음 달 같은 일자의 전날까지로 한다.',
            '마지막 단위기간은 훈련 종료일에 종료한다.',
            '단위기간 내 실제 수업일수는 해당 기수의 수업 일정에 따라 산정한다.',
        ]),
        ('제6조(출결)',[f'단위기간 내 지각·조퇴·외출 누적 {conversion}회는 결석 1일로 환산한다.']),
        ('제13조(수료)', ['108일 이상(90% 이상) 이수하면 수료 기준을 충족한다. 전체 훈련기간의 출석률.']),
        ('제16조(장려금)', [f'단위기간 출석률 {threshold}% 이상이면 훈련장려금 지급 대상이다.']),
    ])
    records = upload_records(data,cohort,upload)
    snapshot=json.loads(records[0].metadata['calculation_criteria_json'])
    return snapshot


class ActivePolicyRulesTests(TestCase):
    def test_upload_produces_scoped_criteria_and_distinct_values(self):
        a,b=uploaded(),uploaded('cohort_40',90,2,'b')
        self.assertEqual(allowance_rules(a).attendance_threshold_percent,80)
        self.assertEqual(allowance_rules(b).attendance_threshold_percent,90)
        self.assertEqual(allowance_rules(b).exceptions_per_absence,2)
        self.assertEqual(b['criteria']['completion']['value'],'90')
        self.assertNotEqual(a['storage_key'],b['storage_key'])

    def test_missing_criteria_never_uses_common_values(self):
        records=upload_records(regulation_bytes())
        snapshot=json.loads(records[0].metadata['calculation_criteria_json'])
        with self.assertRaises(ValueError): allowance_rules(snapshot)
        self.assertEqual(snapshot['issues']['allowance'],'missing')

    def test_active_pointer_replacement_reads_new_key(self):
        a,b=uploaded(),uploaded(threshold=90,upload='b')
        cur=MagicMock()
        cur.execute.return_value.fetchone.side_effect=[None,{'storage_key':a['storage_key'],'source_name':'rules.docx'},
                                                       None,{'storage_key':b['storage_key'],'source_name':'rules.docx'}]
        with patch('chatbot.active_policy_rules._read_snapshot',side_effect=[a,b]) as reader:
            self.assertEqual(allowance_rules(load_active_snapshot(cur,'cohort_34')).attendance_threshold_percent,80)
            self.assertEqual(allowance_rules(load_active_snapshot(cur,'cohort_34')).attendance_threshold_percent,90)
            self.assertNotEqual(reader.call_args_list[0].args[1],reader.call_args_list[1].args[1])

    def test_cross_cohort_path_and_deleted_cohort_stop(self):
        for replies in ([{'exists':1}], [None,{'storage_key':uploaded('cohort_40')['storage_key'],'source_name':'rules.docx'}]):
            cur=MagicMock(); cur.execute.return_value.fetchone.side_effect=replies
            with patch('chatbot.active_policy_rules._read_snapshot') as reader, self.assertRaises(ValueError):
                load_active_snapshot(cur,'cohort_34')
            reader.assert_not_called()

    def runtime(self,snapshot,cohort='cohort_34'):
        start=date(2026,1,1)
        days=[start+timedelta(days=i) for i in range(10)]
        cur=MagicMock()
        def execute(sql,args):
            result=MagicMock()
            if 'start_date, end_date' in sql: result.fetchone.return_value={'start_date':start,'end_date':date(2026,1,31)}
            elif 'curriculum_sheets' in sql: result.fetchone.return_value={'id':1}
            elif 'curriculum_rows' in sql: return [{'date_label':d.isoformat()} for d in days]
            elif 'FROM attendances' in sql: return [{'attendance_date':d,'status':'late' if i<4 else 'present'} for i,d in enumerate(days)]
            else: raise AssertionError(sql)
            return result
        cur.execute.side_effect=execute
        with patch('chatbot.firebase_student_context._connect') as conn, \
             patch('chatbot.firebase_student_context._cohort_ids',return_value=(1,'cohort_34')), \
             patch('chatbot.firebase_student_context._user_id',return_value=1), \
             patch('chatbot.active_policy_rules.load_active_snapshot',side_effect=ValueError('missing') if snapshot is None else None,return_value=snapshot) as reader:
            conn.return_value.__enter__.return_value.cursor.return_value=cur
            result = enrich_unit_period_context(load_unit_period_context({'uid':'fixture','cohort':cohort},today=date(2026,1,10)))
            reader.assert_called_once_with(cur, 'cohort_34')
            return result

    def test_private_loader_numeric_cohort_id_resolves_to_policy_code(self):
        result=self.runtime(uploaded(threshold=90),cohort='1')
        self.assertEqual(result['calculation_rules']['attendance_threshold_percent'],90)

    def test_authenticated_runtime_uses_uploaded_values(self):
        a=self.runtime(uploaded(threshold=80,conversion=3))
        b=self.runtime(uploaded(threshold=90,conversion=2,upload='b'))
        self.assertTrue(a['periods'][0]['requirement_met'])
        self.assertFalse(b['periods'][0]['requirement_met'])
        self.assertEqual(b['calculation_rules']['attendance_threshold_percent'],90)
        self.assertEqual(b['periods'][0]['absence_equivalent_days'],2)

    def test_runtime_missing_policy_retains_raw_records_only(self):
        context=self.runtime(None)
        self.assertIsNone(context['calculation_rules'])
        self.assertEqual(context['periods'], [])
        self.assertIsNone(context['current_unit_period'])
        self.assertEqual(context['schedule_status'], 'unavailable')
        self.assertTrue(context['calendar_unavailable_reason'])

    def test_completion_and_allowance_have_separate_denominators(self):
        s=uploaded(threshold=80)
        start=date(2026,1,1); days=[start+timedelta(days=i) for i in range(10)]
        result=completion_progress(s,start,date(2026,1,31),days[-1],days,dict(zip(days,['present']*8+['absent']*2)))
        self.assertEqual(result['required_recognized_days'],9)
        self.assertEqual(result['additional_normal_attendance_days_needed'],1)
        self.assertTrue(allowance_rules(s).requirement_met(8,10))
