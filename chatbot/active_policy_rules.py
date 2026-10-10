"""Read calculation criteria from the exact active cohort policy upload."""
from functools import lru_cache
import os

from chatbot.calculation_rules import CalculationRules
from chatbot.document_calculation_rules import extract_candidates


def criteria_snapshot(records, cohort, key):
    rows = [{'page_content': r.page_content, 'metadata': r.metadata} for r in records]
    try:
        candidates = extract_candidates(rows)
    except ValueError:
        return {'cohort': cohort, 'storage_key': key, 'status': 'unavailable',
                'reason': '정책 조문 또는 계산 기준이 중복되거나 유효하지 않습니다.', 'criteria': {}}
    criteria, issues = {}, {}
    for purpose in ('completion', 'allowance', 'absence_conversion'):
        matches = [c for c in candidates if c.purpose == purpose and c.cohort == cohort]
        if len(matches) == 1:
            c = matches[0]
            criteria[purpose] = {k: v for k, v in c.metadata().items() if k != 'article_text'}
        else:
            issues[purpose] = 'missing' if not matches else 'conflicting'
    return {'cohort': cohort, 'storage_key': key, 'status': 'unverified',
            'criteria': criteria, 'issues': issues,
            'application_basis': 'current_active_upload; not an approved effective-date history'}


@lru_cache(maxsize=32)
def _read_snapshot(cohort, key, filename):
    import boto3
    from chatbot.cohort_document_rag import MAX_BYTES, document_records
    client = boto3.client('s3', region_name=os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION'))
    body = client.get_object(Bucket=os.getenv('AWS_S3_BUCKET') or os.getenv('S3_BUCKET'), Key=key)['Body']
    try:
        data = body.read(MAX_BYTES + 1)
    finally:
        body.close()
    records = document_records(data, filename, cohort, 'policy', key)
    return criteria_snapshot(records, cohort, key)


def load_active_snapshot(cur, cohort):
    from copy import deepcopy
    from chatbot.cohort_document_rag import indexed_key, valid_cohort_code
    if not valid_cohort_code(cohort):
        raise ValueError('Invalid cohort')
    deleting = cur.execute('SELECT 1 FROM cohort_deletion_jobs WHERE cohort_code=%s', (cohort,)).fetchone()
    if deleting:
        raise ValueError('Cohort deleting')
    row = cur.execute("""SELECT p.storage_key,p.source_name FROM policy_documents p
        JOIN cohorts c ON p.source_key='cohort:' || c.id::text || ':policy'
        WHERE c.code=%s AND p.source_type='cohort_policy' AND p.is_active=true""", (cohort,)).fetchone()
    if not row:
        raise ValueError('No active cohort policy')
    key, filename = row['storage_key'], row['source_name']
    if not indexed_key(key) or not key.startswith(f'cohorts/{cohort}/policy/'):
        raise ValueError('Invalid active policy path')
    return deepcopy(_read_snapshot(cohort, key, filename))


def allowance_rules(snapshot):
    criteria = snapshot['criteria']
    allowance, conversion = criteria.get('allowance'), criteria.get('absence_conversion')
    if not allowance or not conversion:
        raise ValueError('장려금 출석률 또는 결석 환산 기준을 정책에서 확인하지 못했습니다.')
    if (allowance['document_hash'] != conversion['document_hash']
        or any(c['denominator'] != 'unit_period' or c['cohort'] != snapshot['cohort']
               for c in (allowance, conversion))):
        raise ValueError('Policy scope mismatch')
    return CalculationRules(version=allowance['document_hash'], review_status='unverified',
        source=f"{snapshot['storage_key']} / 제{allowance['article']}조·제{conversion['article']}조",
        attendance_threshold_percent=float(allowance['value']), exceptions_per_absence=int(conversion['value']),
        calendar_method='anchored_month_clamped', final_period_method='clip_to_course_end')


def completion_progress(snapshot, start, end, today, scheduled_dates, attendance):
    """Whole-course provisional comparison, using unit-period conversion buckets.

    This explicitly reapplies the current upload for a what-if comparison, not
    a historical adjudication. No actual graduation/benefit decision is made.
    """
    from decimal import Decimal, ROUND_CEILING
    from datetime import date
    from chatbot.unit_period import _periods, ATTENDANCE_STATUSES
    criteria = snapshot.get('criteria', {})
    threshold, conversion = criteria.get('completion'), criteria.get('absence_conversion')
    if not threshold or not conversion:
        return {'unavailable_reason': '수료 출석률 또는 결석 환산 기준 미확인'}
    if threshold['denominator'] != 'whole_course' or conversion['denominator'] != 'unit_period':
        return {'unavailable_reason': '수료 계산 범위 미확인'}
    if (threshold['document_hash'] != conversion['document_hash']
        or any(c['cohort'] != snapshot['cohort'] for c in (threshold, conversion))):
        return {'unavailable_reason': '수료 계산 정책 출처 불일치'}
    schedule = {d for d in scheduled_dates if start <= d <= end}
    if not schedule:
        return {'unavailable_reason': '전체 수업 예정일 미확인'}
    recorded, recognized = 0, 0
    for period in _periods(start, end):
        lo, hi = date.fromisoformat(period['start_date']), date.fromisoformat(period['end_date'])
        states = [s for d,s in attendance.items() if d in schedule and lo <= d <= hi
                  and d <= today and s in ATTENDANCE_STATUSES]
        exceptions = sum(s in ('late','earlyLeave','outing') for s in states)
        recorded += len(states)
        recognized += max(len(states)-states.count('absent')-exceptions//int(conversion['value']),0)
    target = int((Decimal(len(schedule))*Decimal(threshold['value'])/100).to_integral_value(rounding=ROUND_CEILING))
    missing = sum(d <= today and attendance.get(d) not in ATTENDANCE_STATUSES for d in schedule)
    future_registered = sum(d > today and attendance.get(d) in ATTENDANCE_STATUSES for d in schedule)
    return {'purpose':'completion','is_provisional':True,'threshold_percent':threshold['value'],
        'rule':threshold,'scheduled_days':len(schedule),'recorded_days':recorded,
        'recognized_attendance_days':recognized,'required_recognized_days':target,
        'unrecorded_past_or_today_days':missing,
        'additional_normal_attendance_days_needed':max(target-recognized,0) if not missing and not future_registered and recorded else None,
        'basis':'현재 활성 정책을 전체 기록에 적용한 예상 비교. 과거 정책 적용 이력과 수료 확정 판정은 아님.'}
