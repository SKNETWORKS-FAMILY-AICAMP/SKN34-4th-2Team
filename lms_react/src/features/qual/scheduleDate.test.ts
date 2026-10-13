import { describe, expect, it } from 'vitest';
import type { QualExamSchedule } from '../../domain/types';
import { nextScheduleDay } from './scheduleDate';

const today = new Date(2026, 9, 13);
const exam = (dates: Partial<QualExamSchedule>) => dates as QualExamSchedule;

describe('nextScheduleDay', () => {
  it('필기가 끝나도 실기가 남으면 표시한다', () => {
    expect(nextScheduleDay(exam({ docExamStartDt: '20260807', pracExamStartDt: '20261024' }), today))
      .toEqual(new Date(2026, 9, 24));
  });
  it('진행 중인 접수 기간은 오늘 일정으로 유지한다', () => {
    expect(nextScheduleDay(exam({ pracRegStartDt: '20260921', pracRegEndDt: '20261019' }), today)).toEqual(today);
  });
  it('시험이 끝나도 발표가 남으면 표시한다', () => {
    expect(nextScheduleDay(exam({ pracExamStartDt: '20260901', pracPassDt: '20261211' }), today))
      .toEqual(new Date(2026, 11, 11));
  });
  it('모든 일정이 끝났거나 날짜가 없으면 제외한다', () => {
    expect(nextScheduleDay(exam({ pracPassDt: '20261012' }), today)).toBeNull();
    expect(nextScheduleDay(exam({}), today)).toBeNull();
  });
  it('오늘이 마감일이면 아직 표시한다', () => {
    expect(nextScheduleDay(exam({ docRegStartDt: '20261001', docRegEndDt: '20261013' }), today)).toEqual(today);
  });
});
