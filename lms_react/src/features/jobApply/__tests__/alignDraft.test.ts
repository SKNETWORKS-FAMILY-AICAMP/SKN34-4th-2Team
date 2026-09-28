import { describe, expect, it } from 'vitest';

import type { ResumeContent, ResumeProjectItem } from '../../../domain/types';
import { addEvidencedSkills, alignToPosting, postingSkills, sameSkill, skillCoverage, textMentions } from '../alignDraft';

const project = (id: string, techStack: string, description = ''): ResumeProjectItem => ({
  id,
  name: `프로젝트 ${id}`,
  startDate: '',
  endDate: '',
  role: '',
  techStack,
  description,
  url: '',
});

const intro = { subtitle: '', body: '' };
const content = (overrides: Partial<ResumeContent> = {}): ResumeContent => ({
  basicInfo: { name: 'Java 김', phone: '', email: '', birthDate: '', githubUrl: '', blogUrl: '' },
  coreCompetencies: { text: '' },
  experience: [],
  education: [],
  techStack: [],
  certifications: [],
  awards: [],
  trainingExperience: [],
  otherActivities: [],
  projects: [],
  selfIntroduction: {
    intro,
    motivation: intro,
    challenge: intro,
    growth: intro,
    strengthsWeaknesses: intro,
    aspiration: intro,
  },
  ...overrides,
});

const tech = (...names: string[]) => names.map((name, i) => ({ id: `t${i}`, name, level: '' }));

describe('기술 이름 비교', () => {
  it('표기 차이는 같게 보고, 짧은 이름이 긴 이름에 걸리지 않는다', () => {
    expect(sameSkill('Node.js', 'nodejs')).toBe(true);
    expect(sameSkill('Spring Boot', 'SpringBoot')).toBe(true);
    expect(sameSkill('Spring', 'SpringBoot')).toBe(true);
    expect(sameSkill('Java', 'JavaScript')).toBe(false);
    expect(sameSkill('C', 'C++')).toBe(false);
  });

  it('글 속에서 낱말로 찾고, 한글 이름은 조사가 붙어도 찾는다', () => {
    expect(textMentions('Spring Boot 로 API 를 만들었다', 'SpringBoot')).toBe(true);
    expect(textMentions('Vue.js 화면', 'Vue.js')).toBe(true);
    expect(textMentions('JavaScript 만 썼다', 'Java')).toBe(false);
    expect(textMentions('머신러닝을 공부했다', '머신러닝')).toBe(true);
  });
});

describe('맞출 기술 목록', () => {
  it('태그에 요건 문장의 기술을 더하고, 필수에 있으면 우대에서 뺀다', () => {
    const skills = postingSkills({ required: ['Python'], preferred: ['python', 'AWS'] }, [
      { id: 'req-1', group: 'must', label: 'Django REST 개발', postingQuote: 'Django 와 PostgreSQL 기반 API 개발 경험' },
      { id: 'req-2', group: 'preferred', label: '컨테이너', postingQuote: 'Docker, Kubernetes 운영 경험' },
    ]);
    expect(skills.required).toEqual(expect.arrayContaining(['Python', 'PostgreSQL']));
    expect(skills.preferred).toEqual(expect.arrayContaining(['AWS', 'Docker', 'Kubernetes']));
    expect(skills.preferred.some((s) => sameSkill(s, 'Python'))).toBe(false);
  });
});

describe('요건 맞춤 초안', () => {
  const skills = { required: ['Python', 'Django'], preferred: ['AWS'] };

  it('기술스택은 필수 → 우대 → 나머지, 같은 무리 안에서는 원래 순서', () => {
    const { content: aligned, matchedSkills } = alignToPosting(content({ techStack: tech('Figma', 'AWS', 'Git', 'Django', 'Python') }), skills);
    expect(aligned.techStack.map((t) => t.name)).toEqual(['Django', 'Python', 'AWS', 'Figma', 'Git']);
    expect(matchedSkills).toBe(3);
  });

  it('프로젝트는 공고 기술이 많이 겹치는 순이고, 글은 바꾸지 않는다', () => {
    const before = content({
      projects: [project('a', 'React'), project('b', 'AWS'), project('c', 'Python, Django')],
    });
    const result = alignToPosting(before, skills);
    expect(result.content.projects.map((p) => p.id)).toEqual(['c', 'b', 'a']);
    expect(result.projectsReordered).toBe(true);
    expect(result.content.projects[0]).toBe(before.projects[2]);
  });

  it('맞출 것이 없으면 순서를 그대로 둔다', () => {
    const before = content({ techStack: tech('Figma'), projects: [project('a', 'React'), project('b', 'Vue')] });
    const result = alignToPosting(before, skills);
    expect(result.projectsReordered).toBe(false);
    expect(result.content.projects).toEqual(before.projects);
  });
});

describe('요건 확인표', () => {
  it('기술스택 칸 · 본문에만 · 없음을 가르고, 이름 칸은 보지 않는다', () => {
    const coverage = skillCoverage(
      content({ techStack: tech('Python'), projects: [project('a', '', 'Django 로 관리자 화면을 만들었다')] }),
      { required: ['Python', 'Django', 'Java'], preferred: ['AWS'] },
    );
    expect(coverage).toEqual([
      { skill: 'Python', group: 'required', place: 'techStack' },
      { skill: 'Django', group: 'required', place: 'text' },
      { skill: 'Java', group: 'required', place: 'missing' },
      { skill: 'AWS', group: 'preferred', place: 'missing' },
    ]);
  });

  it('본문에 근거가 있는 기술만 기술스택에 더하고, 없는 기술은 지어 넣지 않는다', () => {
    let n = 0;
    const { content: next, added } = addEvidencedSkills(
      content({ techStack: tech('Python') }),
      [
        { skill: 'Python', group: 'required', place: 'techStack' },
        { skill: 'Django', group: 'required', place: 'text' },
        { skill: 'Java', group: 'required', place: 'missing' },
      ],
      () => `new-${++n}`,
    );
    expect(added).toEqual(['Django']);
    expect(next.techStack.map((t) => t.name)).toEqual(['Python', 'Django']);
    expect(next.techStack[1]).toEqual({ id: 'new-1', name: 'Django', level: '' });
  });
});
