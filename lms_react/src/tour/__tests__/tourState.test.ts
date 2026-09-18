import { describe, expect, it } from 'vitest';

import { studentTour } from '../steps/student';
import { instructorTour } from '../steps/instructor';
import { adminTour } from '../steps/admin';
import {
  currentStep,
  isAtRoute,
  isLast,
  tourReducer,
  type TourState,
} from '../tourState';

function start(): TourState {
  return {
    tourId: studentTour.tourId,
    version: studentTour.version,
    uid: 'u1',
    steps: studentTour.steps,
    index: 0,
    active: true,
  };
}

describe('스텝 정의', () => {
  it('역할별 스텝 수가 Flutter와 같다', () => {
    expect(studentTour.steps).toHaveLength(14);
    expect(instructorTour.steps).toHaveLength(12);
    expect(adminTour.steps).toHaveLength(17);
  });

  it('스텝 id가 투어 안에서 유일하다', () => {
    for (const tour of [studentTour, instructorTour, adminTour]) {
      const ids = tour.steps.map((s) => s.id);
      expect(new Set(ids).size).toBe(ids.length);
    }
  });

  it('학생 마지막 스텝만 라우트를 비워 둔다 — 앱바는 어디에나 있다', () => {
    const withoutRoute = studentTour.steps.filter((s) => s.route === undefined);
    expect(withoutRoute.map((s) => s.id)).toEqual(['nav_mypage']);
  });
});

describe('투어 상태 전이', () => {
  it('next는 마지막에서 멈춘다', () => {
    let state: TourState | null = { ...start(), index: studentTour.steps.length - 1 };
    expect(isLast(state)).toBe(true);
    state = tourReducer(state, { type: 'next' });
    expect(state?.index).toBe(studentTour.steps.length - 1);
  });

  it('previous는 첫 단계에서 멈춘다', () => {
    const state = tourReducer(start(), { type: 'previous' });
    expect(state?.index).toBe(0);
  });

  it('범위를 벗어난 goToIndex는 무시한다', () => {
    expect(tourReducer(start(), { type: 'goToIndex', index: 99 })?.index).toBe(0);
    expect(tourReducer(start(), { type: 'goToIndex', index: -1 })?.index).toBe(0);
  });

  it('end는 투어를 지운다', () => {
    expect(tourReducer(start(), { type: 'end' })).toBeNull();
  });

  it('currentStep은 투어가 없으면 null', () => {
    expect(currentStep(null)).toBeNull();
    expect(currentStep({ ...start(), active: false })).toBeNull();
    expect(currentStep(start())?.id).toBe('nav_dashboard');
  });
});

describe('라우트 일치', () => {
  it('루트 경로는 exact match만 인정한다', () => {
    expect(isAtRoute('/admin', '/admin', ['/admin'])).toBe(true);
    expect(isAtRoute('/admin/students', '/admin', ['/admin'])).toBe(false);
  });

  it('하위 경로는 접두사로 인정한다', () => {
    expect(isAtRoute('/admin/students/create', '/admin/students', ['/admin'])).toBe(true);
    expect(isAtRoute('/admin/studentsX', '/admin/students', ['/admin'])).toBe(false);
  });

  it('학생 홈은 빈 문자열도 홈으로 본다', () => {
    expect(isAtRoute('', '/', ['/'])).toBe(true);
    expect(isAtRoute('/board', '/', ['/'])).toBe(false);
  });
});
