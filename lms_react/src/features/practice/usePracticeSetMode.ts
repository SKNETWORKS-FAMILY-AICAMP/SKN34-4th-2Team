import { useState } from 'react';

import {
  recordPracticeAttempt,
  reportPracticeProblem,
  useMyPracticeAttempts,
  usePracticeReports,
  usePracticeReviews,
  usePracticeSet,
  usePracticeSets,
} from '../../data/repository';
import { todayKey } from '../../data/store';
import type { PracticeAttempt, PracticeReport, PracticeReportReason, PracticeSet } from '../../domain/types';
import { useCurrentUser } from '../auth/session';
import { isHidden } from './reports';
import { isRetryId, retryItems, retryScope, retrySet, shortDate } from './review';

export interface PracticeSetMode {
  /** 연 세트. 자유 연습장이면 undefined */
  set: PracticeSet | undefined;
  /** 다시 풀 문제로 열었는지 */
  isRetry: boolean;
  passedCount: number;
  /** 숨긴 문제를 뺀 문제 수 — 진행률의 분모 */
  visibleCount: number;
  attemptOf(index: number): PracticeAttempt | undefined;
  /** 신고가 모여(또는 강사가) 숨긴 문제인지 */
  hiddenOf(index: number): boolean;
  /** 내가 이 문제에 남긴 신고 */
  myReportOf(index: number): PracticeReport | undefined;
  report(index: number, reason: PracticeReportReason, note: string): void;
  /** 문제 i 의 원래 자리 — 다시 풀 문제는 여러 세트에서 모였다 */
  originOf(index: number): { setId: string; index: number } | null;
  /** 튜터 대화 — 다시 풀 문제는 'retry:오늘'(복습 때 대화와 따로, 날마다 새로). 복습 세트는 undefined */
  tutorThread: string | undefined;
  /** 문제 머리에 붙일 원래 수업 — 다시 풀 문제에서만 */
  noteOf(index: number): string | undefined;
  record(index: number, passed: boolean): void;
}

/**
 * 연습장을 어떤 문제 세트로 열었는지 — 없음 · 날짜별 복습 세트 · 다시 풀 문제.
 *
 * 다시 풀 문제는 여러 세트에서 모인 목록이라, 문제 i 의 원래 자리(세트·번호)를 기억해
 * 풀이 기록을 원래 세트에 남긴다. 목록은 연 순간으로 고정한다 — 풀다가 통과해도
 * 그 자리에서 사라지지 않게.
 */
export function usePracticeSetMode(setId: string | null): PracticeSetMode {
  const user = useCurrentUser();
  const retryId = isRetryId(setId) ? setId! : null;
  const storedSet = usePracticeSet(retryId ? null : setId);
  const allSets = usePracticeSets(user.cohortId);
  const myAttempts = useMyPracticeAttempts(user.uid);
  const reports = usePracticeReports();
  const reviews = usePracticeReviews();
  // 무엇을 모을지는 id 가 정한다(retryScope) — 대시보드는 하루 지난 것, 공부방 · 오답노트는 전체 또는 그 날짜.
  // 링크에 적힌 개수와 연 세트가 같아야 한다
  const [retry] = useState(() =>
    retryId
      ? retrySet(
          retryScope(retryId, retryItems(allSets, myAttempts).filter((i) => !isHidden(reports, reviews, i.set.id, i.index)), todayKey()),
          todayKey(),
          retryId,
        )
      : null,
  );
  const set = retry?.set ?? storedSet;

  const originOf = (i: number) => (retry ? retry.origins[i] : set ? { setId: set.id, index: i } : null);
  const attemptOf = (i: number) => {
    const o = originOf(i);
    return o ? myAttempts.find((a) => a.setId === o.setId && a.index === o.index) : undefined;
  };

  const hiddenOf = (i: number) => {
    const o = originOf(i);
    return o ? isHidden(reports, reviews, o.setId, o.index) : false;
  };
  const visible = set ? set.problems.map((_, i) => i).filter((i) => !hiddenOf(i)) : [];

  return {
    set,
    isRetry: retry !== null,
    tutorThread: retry ? `retry:${retry.set.lessonDate}` : undefined,
    passedCount: visible.filter((i) => attemptOf(i)?.passed).length,
    visibleCount: visible.length,
    attemptOf,
    hiddenOf,
    originOf: (i) => originOf(i) ?? null,
    myReportOf: (i) => {
      const o = originOf(i);
      return o ? reports.find((r) => r.uid === user.uid && r.setId === o.setId && r.index === o.index) : undefined;
    },
    report: (i, reason, note) => {
      const o = originOf(i);
      if (o) reportPracticeProblem(user.uid, o.setId, o.index, reason, note);
    },
    noteOf: (i) => (retry ? originNote(allSets, retry.origins[i]) : undefined),
    record: (i, passed) => {
      const o = originOf(i);
      if (o) recordPracticeAttempt(user.uid, o.setId, o.index, passed);
    },
  };
}

/** 다시 풀 문제 셀 머리에 붙일 원래 자리 — '9/14 문제 4 · BLIP · Stable Diffusion · VQA'(오답노트 목록의 번호와 같다) */
function originNote(sets: PracticeSet[], origin: { setId: string; index: number } | undefined): string | undefined {
  const s = sets.find((x) => x.id === origin?.setId);
  return s && origin ? `${shortDate(s.lessonDate)} 문제 ${origin.index + 1} · ${s.title}` : undefined;
}
