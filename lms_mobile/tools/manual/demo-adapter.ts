// 설명서 캡처용 데모 서버 — 이 파일은 캡처 작업 폴더에만 있고 앱 저장소에는 넣지 않는다.
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { getDb } from '@web/data/store';
import { DemoAccounts, DemoConfig } from '@web/data/seed';

declare const window: { localStorage: { getItem(k: string): string | null } } | undefined;

export function demoUid(): string | null {
  try {
    return (typeof window !== 'undefined' && window.localStorage.getItem('demoUid')) || null;
  } catch {
    return null;
  }
}

const iso = (d: number) => new Date(Date.now() + d * 86400000).toISOString();
const day = (d: number) => iso(d).slice(0, 10);

const quests = [
  { id: 'q1', title: '기술 블로그 3편 연속 작성', description: '이번 달 안에 학습 내용을 블로그 글 3편으로 정리해 주세요.', reward: 3000, evidenceType: 'link', approval: 'manual', maxCompletions: 3, startOn: day(-10), endOn: day(20), published: true, closed: false, open: true, createdAt: iso(-10), counts: { pending: 2, approved: 5 } },
  { id: 'q2', title: '스터디 인증샷 올리기', description: '팀 스터디 진행 사진을 올리면 바로 지급됩니다.', reward: 1000, evidenceType: 'file', approval: 'auto', maxCompletions: 5, startOn: day(-5), endOn: day(25), published: true, closed: false, open: true, createdAt: iso(-5), counts: { approved: 12 } },
  { id: 'q3', title: '수업 회고 한 줄 남기기', description: '오늘 배운 내용 중 가장 기억에 남는 것을 한 줄로 적어 주세요.', reward: 500, evidenceType: 'text', approval: 'manual', maxCompletions: 10, startOn: day(-3), endOn: day(27), published: true, closed: false, open: true, createdAt: iso(-3), counts: { pending: 4, approved: 20, rejected: 1 } },
];
const submissions = [
  { id: 's1', questId: 'q1', questTitle: quests[0].title, uid: DemoAccounts.studentUid, studentName: '이수민', status: 'approved', text: '', link: 'https://velog.io/@example/1', files: [], reviewComment: '', grantedAmount: 3000, submittedAt: iso(-6), reviewedAt: iso(-5) },
  { id: 's2', questId: 'q3', questTitle: quests[2].title, uid: 'demo-student-002', studentName: '김하늘', status: 'pending', text: '파이썬 데코레이터 동작 원리를 이해했어요.', link: '', files: [], reviewComment: '', grantedAmount: 0, submittedAt: iso(-1), reviewedAt: null },
  { id: 's3', questId: 'q1', questTitle: quests[0].title, uid: 'demo-student-004', studentName: '박서연', status: 'pending', text: '', link: 'https://velog.io/@example/2', files: [], reviewComment: '', grantedAmount: 0, submittedAt: iso(-1), reviewedAt: null },
];
const counsel = [
  { id: 'c1', uid: 'demo-student-002', cohortId: DemoConfig.cohortId, round: 1, counseledOn: day(-20), category: 'regular', content: '학습 진도와 프로젝트 역할을 확인했습니다.', followUp: 'SQL 보충 자료 전달', followUpDone: true, nextOn: day(10), counselorName: 'PLAYDATA 관리자', createdAt: iso(-20), updatedAt: iso(-20) },
  { id: 'c2', uid: 'demo-student-003', cohortId: DemoConfig.cohortId, round: 1, counseledOn: day(-8), category: 'career', content: '희망 직무와 포트폴리오 방향을 상담했습니다.', followUp: '이력서 첨삭 일정 잡기', followUpDone: false, nextOn: day(6), counselorName: 'PLAYDATA 관리자', createdAt: iso(-8), updatedAt: iso(-8) },
];

function json<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

function route(method: string, url: string, body: Record<string, unknown>): unknown {
  const db = getDb();
  const uid = demoUid() ?? DemoAccounts.studentUid;
  const me = db.users.find((u) => u.uid === uid)!;
  if (url.endsWith('/token/refresh')) return { access: 'demo', refresh: 'demo' };
  if (url.endsWith('/login')) {
    const user = db.users.find((u) => u.email === body.email) ?? me;
    return { access: 'demo', refresh: 'demo', uid: user.uid, role: user.role, mustChangePassword: false };
  }
  if (url.endsWith('/me')) return json({ ...me, mustChangePassword: false });
  if (url.endsWith('/posts') && method === 'get') return { posts: json(db.posts) };
  const comments = /\/posts\/([^/]+)\/comments$/.exec(url);
  if (comments && method === 'get') return { comments: json(db.postComments.filter((c) => c.postId === comments[1])) };
  if (url.endsWith('/quests') && method === 'get') return { quests, submissions: submissions.filter((s) => s.uid === uid) };
  if (url.endsWith('/quest-submissions')) return { submissions };
  if (url.endsWith('/counsel-notes')) return { notes: counsel };
  if (url.endsWith('/study-sources/github')) return { owners: [{ id: 'g1', owner: 'playdata-skn', lastSyncedAt: iso(-1), error: null }] };
  const note = /\/study-notes\/([^/]+)$/.exec(url);
  if (note && method === 'get') return json(db.studyNotes.find((n) => n.id === decodeURIComponent(note[1])) ?? db.studyNotes[0]);
  const take = /\/assessments\/([^/]+)\/(take|review)$/.exec(url);
  if (take) {
    const id = decodeURIComponent(take[1]);
    const questions = json(db.assessmentQuestions[id] ?? []);
    if (take[2] === 'take') return { questions };
    const sub = db.assessmentSubmissions.find((s) => s.assessmentId === id && s.userId === uid);
    return { questions, submission: json({ id: sub?.id ?? 'x', totalScore: sub?.totalScore ?? 0, autoTotalScore: sub?.totalScore ?? 0, submittedAt: sub?.submittedAt ?? null, answers: sub?.answers ?? [] }) };
  }
  if (url.endsWith('/featured-postings')) return { postings: [] };
  return {};
}

export const demoAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  const method = (config.method ?? 'get').toLowerCase();
  let body: Record<string, unknown> = {};
  try {
    body = typeof config.data === 'string' ? JSON.parse(config.data) : (config.data ?? {});
  } catch {
    body = {};
  }
  const data = route(method, config.url ?? '', body);
  await new Promise((r) => setTimeout(r, 30));
  return { data, status: 200, statusText: 'OK', headers: {}, config, request: {} } as AxiosResponse;
};
