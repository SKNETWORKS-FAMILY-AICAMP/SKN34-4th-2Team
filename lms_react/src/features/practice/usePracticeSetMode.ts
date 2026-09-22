import { useState } from 'react';

import { recordPracticeAttempt, useMyPracticeAttempts, usePracticeSet, usePracticeSets } from '../../data/repository';
import { todayKey } from '../../data/store';
import type { PracticeAttempt, PracticeSet } from '../../domain/types';
import { useCurrentUser } from '../auth/session';
import { RETRY_SET_ID, retryItems, retrySet, shortDate } from './review';

export interface PracticeSetMode {
  /** 연 세트. 자유 연습장이면 undefined */
  set: PracticeSet | undefined;
  /** 다시 풀 문제로 열었는지 */
  isRetry: boolean;
  passedCount: number;
  attemptOf(index: number): PracticeAttempt | undefined;
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
  const storedSet = usePracticeSet(setId === RETRY_SET_ID ? null : setId);
  const allSets = usePracticeSets(user.cohortId);
  const myAttempts = useMyPracticeAttempts(user.uid);
  const [retry] = useState(() =>
    setId === RETRY_SET_ID ? retrySet(retryItems(allSets, myAttempts), todayKey()) : null,
  );
  const set = retry?.set ?? storedSet;

  const originOf = (i: number) => (retry ? retry.origins[i] : set ? { setId: set.id, index: i } : null);
  const attemptOf = (i: number) => {
    const o = originOf(i);
    return o ? myAttempts.find((a) => a.setId === o.setId && a.index === o.index) : undefined;
  };

  return {
    set,
    isRetry: retry !== null,
    passedCount: set ? set.problems.filter((_, i) => attemptOf(i)?.passed).length : 0,
    attemptOf,
    noteOf: (i) => (retry ? originNote(allSets, retry.origins[i]?.setId) : undefined),
    record: (i, passed) => {
      const o = originOf(i);
      if (o) recordPracticeAttempt(user.uid, o.setId, o.index, passed);
    },
  };
}

/** 다시 풀 문제 셀 머리에 붙일 원래 수업 — '9/14 · BLIP · Stable Diffusion · VQA' */
function originNote(sets: PracticeSet[], setId: string | undefined): string | undefined {
  const s = sets.find((x) => x.id === setId);
  return s ? `${shortDate(s.lessonDate)} · ${s.title}` : undefined;
}
