import type { ResumeContent, ResumeProjectItem } from '../../domain/types';
import { jobSkillNames } from '../resume/skills/jobSkillNames';

/**
 * 공고 요건 맞춤 초안 — 공고를 먼저 고른 뒤, 바탕 이력서의 사본을 그 공고 요건 순으로 다시 늘어놓는다.
 *
 * 글은 한 글자도 바꾸지 않는다. 순서만 바꾼다. 문장을 고치는 일은 AI 첨삭이 근거 인용과 함께 한다 —
 * 여기서 모델 없이 문장을 만들면 없는 경험을 지어낼 수 있다.
 * - 기술스택: 공고 필수 기술 → 우대 기술 → 나머지
 * - 프로젝트: 공고 기술이 많이 겹치는 순(필수 2점, 우대 1점). 같으면 원래 순서
 * - 경력 · 학력 · 교육은 시간 순이 뜻이라 그대로 둔다
 */
export interface PostingSkills {
  required: string[];
  preferred: string[];
}

/** 공고 요건 한 줄 — 첨삭 서버가 정리한 것(필수 must · 우대 preferred · 주요 업무 task) */
export interface PostingRequirement {
  id: string;
  group: string;
  label: string;
  postingQuote: string;
}

/** 비교용 이름 — 대소문자 · 띄어쓰기 · 점 · 하이픈 · 빗금을 지운다. Node.js = nodejs, Spring Boot = springboot */
export function skillKey(name: string): string {
  return name.toLowerCase().replace(/[\s._\-/]/g, '');
}

const HANGUL = /[가-힣]/;

/**
 * 두 기술 이름이 같은가. 앞부분이 같고 짧은 쪽이 다섯 글자 이상이면 같다고 본다(spring ↔ springboot).
 * 네 글자 이하는 정확히 같아야 한다 — java 가 javascript 에 걸리면 안 된다.
 */
export function sameSkill(a: string, b: string): boolean {
  const x = skillKey(a);
  const y = skillKey(b);
  if (x === '' || y === '') return false;
  if (x === y) return true;
  const [short, long] = x.length <= y.length ? [x, y] : [y, x];
  return short.length >= 5 && long.startsWith(short);
}

/** 글 속 낱말. 이웃한 두 낱말을 붙인 것도 넣는다(node . js → nodejs, spring boot → springboot) */
function wordsOf(text: string): string[] {
  const words = text.toLowerCase().split(/[^a-z0-9+#가-힣]+/).filter((w) => w !== '');
  return [...words, ...words.slice(1).map((w, i) => `${words[i]}${w}`)];
}

/** 글에 이 기술이 나오는가. 한글 이름(머신러닝)은 조사가 붙으므로 띄어쓰기를 지운 글에서 찾는다 */
export function textMentions(text: string, skill: string): boolean {
  const key = skillKey(skill);
  if (key === '') return false;
  if (HANGUL.test(key)) return skillKey(text).includes(key);
  return wordsOf(text).some((w) => sameSkill(w, skill));
}

/**
 * 맞출 기술 목록. 수집기가 뽑아 둔 기술 태그에, 요건 문장에 나오는 기술 이름(공고에 자주 나오는 228개)을 더한다.
 * 태그가 비어 있는 공고도 요건 문장으로 맞출 수 있다. 필수에 있으면 우대에서는 뺀다.
 */
export function postingSkills(
  tags: { required: string[]; preferred: string[] },
  requirements: PostingRequirement[] = [],
): PostingSkills {
  const required: string[] = [];
  const preferred: string[] = [];
  const has = (list: string[], name: string) => list.some((s) => sameSkill(s, name));
  const add = (list: string[], name: string) => {
    if (name.trim() !== '' && !has(required, name) && !has(list, name)) list.push(name.trim());
  };
  tags.required.forEach((s) => add(required, s));
  const mustText = requirements.filter((r) => r.group === 'must').map((r) => `${r.label} ${r.postingQuote}`).join('\n');
  jobSkillNames.filter((s) => textMentions(mustText, s)).forEach((s) => add(required, s));
  tags.preferred.forEach((s) => add(preferred, s));
  const restText = requirements.filter((r) => r.group !== 'must').map((r) => `${r.label} ${r.postingQuote}`).join('\n');
  jobSkillNames.filter((s) => textMentions(restText, s)).forEach((s) => add(preferred, s));
  return { required, preferred: preferred.filter((s) => !has(required, s)) };
}

/** 기술스택 칸을 뺀 이력서 글 전부 — 기본 정보(이름 · 연락처)도 뺀다 */
function bodyText(content: ResumeContent): string {
  const out: string[] = [];
  const walk = (value: unknown) => {
    if (typeof value === 'string') out.push(value);
    else if (Array.isArray(value)) value.forEach(walk);
    else if (value !== null && typeof value === 'object') Object.values(value).forEach(walk);
  };
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { basicInfo, techStack, ...rest } = content;
  walk(rest);
  return out.join('\n');
}

/** techStack: 기술스택 칸에 있음 · text: 본문(프로젝트 · 경력 등)에만 있음 · missing: 이력서에 없음 */
export type SkillPlace = 'techStack' | 'text' | 'missing';

export interface SkillCoverage {
  skill: string;
  group: 'required' | 'preferred';
  place: SkillPlace;
}

export function skillCoverage(content: ResumeContent, skills: PostingSkills): SkillCoverage[] {
  const text = bodyText(content);
  const placeOf = (skill: string): SkillPlace => {
    if (content.techStack.some((t) => sameSkill(t.name, skill))) return 'techStack';
    return textMentions(text, skill) ? 'text' : 'missing';
  };
  return [
    ...skills.required.map((skill) => ({ skill, group: 'required' as const, place: placeOf(skill) })),
    ...skills.preferred.map((skill) => ({ skill, group: 'preferred' as const, place: placeOf(skill) })),
  ];
}

/**
 * 본문에는 나오는데 기술스택 칸에 없는 공고 기술을 칸에 더한다. 이력서에 근거가 있는 것만 더한다 —
 * 이력서 어디에도 없는 기술(missing)은 넣지 않는다. 그건 첨삭의 「경험 보완」이 물어서 채운다.
 */
export function addEvidencedSkills(
  content: ResumeContent,
  coverage: SkillCoverage[],
  newId: () => string,
): { content: ResumeContent; added: string[] } {
  const added = coverage.filter((c) => c.place === 'text').map((c) => c.skill);
  if (added.length === 0) return { content, added };
  const items = added.map((name) => ({ id: newId(), name, level: '' }));
  return { content: { ...content, techStack: [...content.techStack, ...items] }, added };
}

function projectScore(project: ResumeProjectItem, skills: PostingSkills): number {
  const text = [project.name, project.role, project.techStack, project.description].join('\n');
  const hits = (list: string[]) => list.filter((s) => textMentions(text, s)).length;
  return hits(skills.required) * 2 + hits(skills.preferred);
}

/** 점수가 높은 것부터. 같으면 원래 순서를 지킨다 */
function stableSortBy<T>(items: T[], score: (item: T) => number): T[] {
  return items
    .map((item, index) => ({ item, index, score: score(item) }))
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map((x) => x.item);
}

export interface AlignResult {
  content: ResumeContent;
  /** 앞으로 옮긴 공고 기술 수(기술스택에 있던 것) */
  matchedSkills: number;
  /** 프로젝트 순서가 바뀌었는가 */
  projectsReordered: boolean;
}

export function alignToPosting(content: ResumeContent, skills: PostingSkills): AlignResult {
  const rank = (name: string) =>
    skills.required.some((s) => sameSkill(s, name)) ? 2 : skills.preferred.some((s) => sameSkill(s, name)) ? 1 : 0;
  const techStack = stableSortBy(content.techStack, (t) => rank(t.name));
  const projects = stableSortBy(content.projects, (p) => projectScore(p, skills));
  return {
    content: { ...content, techStack, projects },
    matchedSkills: content.techStack.filter((t) => rank(t.name) > 0).length,
    projectsReordered: projects.some((p, i) => p !== content.projects[i]),
  };
}
