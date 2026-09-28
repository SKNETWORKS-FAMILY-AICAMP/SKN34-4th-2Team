/**
 * 회사 자기소개서 문항 — 공고마다 다른 문항 · 글자 수를 공고용 이력서에 담는다.
 *
 * 수집한 공고 글에 문항이 그대로 적힌 경우는 0.1% 남짓이다(2026-09-28, 열린 텍스트 공고 47,132건 중 16~42건).
 * 문항은 대개 회사 채용 사이트 · 첨부 양식에 있다. 그래서 사용자가 붙여 넣은 글을 문항으로 나누는 것이
 * 주 경로이고, 아직 문항을 모르면 자주 나오는 문항에서 고른다.
 */
import type { ResumeCompanyQuestion } from '../../domain/types';

export type CompanyQuestion = ResumeCompanyQuestion;

/** 회사들이 자주 묻는 문항 — 진짜 문항을 모를 때 먼저 써 둔다 */
export const COMMON_QUESTIONS: { key: string; question: string; limit: number }[] = [
  { key: 'motivation', question: '지원 동기와 입사 후 포부', limit: 600 },
  { key: 'competency', question: '직무 관련 역량과 경험', limit: 800 },
  { key: 'problem', question: '문제를 해결한 경험', limit: 800 },
  { key: 'collaboration', question: '협업 · 갈등을 해결한 경험', limit: 500 },
  { key: 'growth', question: '성장 과정', limit: 500 },
  { key: 'personality', question: '성격의 장단점', limit: 500 },
];

// 문항 머리: "1.", "1)", "Q1.", "①", "문항 1." 따위
const NUMBERED = /^\s*(?:문항\s*)?(?:Q\s*)?(?:\d{1,2}|[①-⑩])\s*[.)．:]?\s+(?=\S)/i;
const CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩';
// "(공백 포함 600자 이내)", "600자 내외", "최대 1,000자" — 숫자만 꺼낸다
const LIMIT = /(\d{1,2},?\d{3}|\d{2,4})\s*자/;
// 줄 끝의 글자 수 표기 — 괄호째("(공백 포함 600자 이내)")거나 괄호 없이("공백 포함 800자 이내")
const LIMIT_NOTE =
  /\s*(?:[([][^()[\]]*?\d{2,4}\s*자[^()[\]]*[)\]]|(?:[-–/,]\s*)?(?:공백\s*(?:포함|제외)\s*)?(?:최대\s*)?(?:\d{1,2},?\d{3}|\d{2,4})\s*자\s*(?:이내|내외|이하|미만)?)\s*$/;
// 문항이 아닌 줄 — 머리글("[자기소개서]"), 작성 안내("(* Guide : …)", "※ …")
const NOT_QUESTION = /^\s*(?:\[[^\]]*\]\s*$|[(*※·•-])/;
const ASKS = /(?:\?|시오\.?|주세요\.?|바랍니다\.?|하세요\.?|기술|서술|작성)\s*$/;

function limitOf(text: string): number | null {
  const found = LIMIT.exec(text);
  if (found === null) return null;
  const value = Number(found[1].replace(',', ''));
  return value >= 50 && value <= 5000 ? value : null;
}

function cleanQuestion(text: string): string {
  let q = text.replace(NUMBERED, '').trim();
  const circled = CIRCLED.indexOf(q[0] ?? '');
  if (circled >= 0) q = q.slice(1).trim();
  return q.replace(LIMIT_NOTE, '').trim();
}

/**
 * 붙여 넣은 글 → 문항 목록.
 * - 번호가 붙은 줄이 있으면 그 줄들이 문항이다. 번호 없는 이어진 줄은 앞 문항에 붙인다(긴 문항이 두 줄로 접힌 경우)
 * - 번호가 없으면 묻는 말로 끝나는 줄(“…작성해 주세요.”, “…?”)을 문항으로 본다
 * - 글자 수는 문항 줄이나 바로 다음 줄에서 읽는다
 */
export function splitQuestions(text: string, newId: () => string): CompanyQuestion[] {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter((l) => l !== '');
  const numbered = lines.some((l) => NUMBERED.test(l) || CIRCLED.includes(l[0] ?? ''));
  const out: { question: string; limit: number | null }[] = [];
  for (const line of lines) {
    const isHead = NUMBERED.test(line) || CIRCLED.includes(line[0] ?? '');
    const last = out[out.length - 1];
    if (numbered ? isHead : !NOT_QUESTION.test(line) && ASKS.test(line.replace(LIMIT_NOTE, ''))) {
      out.push({ question: cleanQuestion(line), limit: limitOf(line) });
      continue;
    }
    if (last === undefined) continue;
    const rest = line.replace(LIMIT_NOTE, '').trim();
    // 번호 문항이 두 줄로 접힌 경우만 잇는다(끝에 글자 수가 붙어 있어도). 안내 문구는 버린다
    if (numbered && !NOT_QUESTION.test(line) && rest.length >= 2 && last.question.length < 200) {
      last.question = `${last.question} ${rest}`.trim();
      last.limit ??= limitOf(line);
      continue;
    }
    // 문항 다음 줄의 글자 수 안내("(공백 포함 600자 이내)")
    if (last.limit === null && limitOf(line) !== null && line.length < 40) last.limit = limitOf(line);
  }
  return out
    .filter((q) => q.question.length >= 4)
    .map((q) => ({ id: newId(), question: q.question, limit: q.limit, answer: '' }));
}

const DEFAULT_SECTIONS = [
  ['intro', '자기소개'],
  ['motivation', '지원동기'],
  ['challenge', '어려움을 극복한 경험'],
  ['growth', '성장과정'],
  ['strengthsWeaknesses', '성격의 장단점'],
  ['aspiration', '입사 후 포부'],
] as const;

/**
 * 기본 6문항을 회사 문항 모양으로 — 자유양식 공고도 같은 문항 답변 첨삭을 탄다.
 * 바탕 이력서에 써 둔 자기소개서를 답으로 옮겨 둔다(첨삭이 그 글을 다듬는 게 아니라 새로 쓰지만, 처음 보는 칸이 비지 않게).
 */
export function defaultQuestions(
  intro: Partial<Record<(typeof DEFAULT_SECTIONS)[number][0], { body?: string }>> | undefined,
  newId: () => string,
): CompanyQuestion[] {
  return DEFAULT_SECTIONS.map(([key, question]) => ({
    id: newId(),
    question,
    limit: null,
    answer: String(intro?.[key]?.body ?? ''),
  }));
}
