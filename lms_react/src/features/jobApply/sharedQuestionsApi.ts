/**
 * 자소서 문항 공유 — 같은 회사 · 시즌 · 직무를 고른 수강생끼리 정리한 문항을 나눠 쓴다(lms_api/lms/shared_questions.py).
 *
 * 회사 · 시즌은 서버가 고른 공고에서 정한다. 직무는 학생이 고른다. 띄어쓰기 · 꼬리말(직무 · 분야 …) · 줄임말만 다른
 * 이름은 서버의 role_key 가 한 직무로 접는다. 여기 roleKey 는 입력할 때 「혹시 이 직무인가요?」를 띄우는 데만 쓴다.
 */
import { http } from '../../data/http';
import type { CompanyQuestion } from './companyQuestions';

export const COMMON_ROLE = '모든 직무 공통';

export interface SharedQuestion {
  question: string;
  limit: number | null;
}

export interface SharedSet {
  id: string;
  ids: string[];
  roleNames: string[];
  questions: SharedQuestion[];
  useCount: number;
  updatedAt: string;
  mine: boolean;
  shared: boolean;
}

export interface SharedRole {
  key: string;
  name: string;
  names: string[];
  sets: SharedSet[];
  useCount: number;
  people: number;
}

export interface SharedQuestions {
  company: string;
  season: string;
  roles: SharedRole[];
  common: SharedSet[];
  canReport: boolean;
}

export type ReportReason = 'other_company' | 'wrong' | 'past_season';

export const REPORT_REASONS: { id: ReportReason; label: string }[] = [
  { id: 'other_company', label: '다른 회사 문항이에요' },
  { id: 'wrong', label: '문항이 빠졌거나 틀렸어요' },
  { id: 'past_season', label: '지난 시즌 문항이에요' },
];

const asItems = (questions: CompanyQuestion[]) => questions.map((q) => ({ question: q.question, limit: q.limit }));

export const sharedQuestionsApi = {
  list: (jobId: string) => http.get<SharedQuestions>('/apply/shared-questions', { params: { jobId } }).then((r) => r.data),
  check: (jobId: string, roleName: string, questions: CompanyQuestion[]) =>
    http
      .post<{ sameRole: { name: string; useCount: number } | null }>('/apply/shared-questions/check', {
        jobId,
        roleName,
        questions: asItems(questions),
      })
      .then((r) => r.data),
  save: (jobId: string, roleName: string, questions: CompanyQuestion[], share: boolean) =>
    http
      .post<{ id: string; created: boolean; roleName: string }>('/apply/shared-questions', {
        jobId,
        roleName,
        questions: asItems(questions),
        share,
      })
      .then((r) => r.data),
  use: (id: string) => http.post(`/apply/shared-questions/${id}/use`).then(() => undefined),
  report: (id: string, reason: ReportReason) =>
    http.post<{ hidden: boolean }>(`/apply/shared-questions/${id}/report`, { reason }).then((r) => r.data),
};

const ROLE_WORDS: [RegExp, string][] = [
  [/소프트웨어|software/g, 'sw'],
  [/개발자/g, '개발'],
];
const ROLE_SUFFIX = /(직무|분야|직군|부문|담당|파트|포지션)$/;

/** 서버 role_key 의 가벼운 꼴 — 띄어쓰기 · 문장부호 · 꼬리말 · 줄임말 */
export function roleKey(name: string): string {
  let text = name.normalize('NFKC').toLowerCase().replace(/[\s·・,./()[\]{}<>\-_&+|:;'"]+/g, '');
  for (const [word, short] of ROLE_WORDS) text = text.replace(word, short);
  while (text.length > 2 && ROLE_SUFFIX.test(text)) text = text.replace(ROLE_SUFFIX, '');
  return text;
}

/** 입력한 직무와 비슷한 기존 직무 — 같은 열쇠거나 한쪽이 다른 쪽을 품을 때 */
export function similarRoles(typed: string, roles: SharedRole[]): SharedRole[] {
  const key = roleKey(typed);
  if (key.length < 2) return [];
  return roles.filter((r) => r.key === key || r.key.includes(key) || key.includes(r.key));
}

const TITLE_NOISE =
  /\[[^\]]*\]|\([^)]*\)|\d{2,4}\s*년?\s*(상반기|하반기)?|상반기|하반기|신입사원|신입|경력|사원|직원|정규직|계약직|인턴|공개|대규모|공채|채용|모집|수시|및|각|부문|분야|직군|담당자?/g;

/** 공고 제목에서 직무를 짐작한다 — 「2026 하반기 SW 직군 신입사원 채용」 → 「SW」. 학생이 고칠 수 있다 */
export function roleFromTitle(title: string, company: string): string {
  const name = company.replace(/\(주\)|㈜|주식회사|\s/g, '');
  return title
    .replace(TITLE_NOISE, ' ')
    .split(/\s+/)
    .filter((w) => w !== '' && w.replace(/\(주\)|㈜|주식회사/g, '') !== name)
    .join(' ')
    .trim();
}

/** 공유 정리의 문항 → 화면의 문항(답은 비운다) */
export function toCompanyQuestions(set: SharedSet, newId: () => string): CompanyQuestion[] {
  return set.questions.map((q) => ({ id: newId(), question: q.question, limit: q.limit, answer: '' }));
}
