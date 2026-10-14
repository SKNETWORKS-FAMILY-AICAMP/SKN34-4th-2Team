// 가이드 캡처용 AI 서버 예시 응답.
//
// 데모 빌드(--mode test)는 백엔드 없이 뜨지만, AI 기능(공고 추천 · 코치에게 묻기 · 첨삭 · 공고 맞춤 지원)은
// /api 를 부른다. 실서버(RDS)로 찍으면 실제 수강생 정보가 PDF 에 남으므로, 여기서 예시 응답을 끼운다.
// 회사 · 공고 · 문장은 모두 지어낸 예시다. 응답 모양은 화면 코드의 파서(toResult 등)에 맞췄다.
import fs from 'node:fs';
import path from 'node:path';
import { outRoot } from './serve.mjs';

const resumeFile = path.join(outRoot, 'demo-resume.json');

function demoResume() {
  if (!fs.existsSync(resumeFile)) {
    throw new Error(`${resumeFile} 가 없습니다. npx vite-node tools/guide/dump-seed.ts ${resumeFile} 를 먼저 실행하세요.`);
  }
  return JSON.parse(fs.readFileSync(resumeFile, 'utf-8'));
}

const deadline = (days) => {
  const d = new Date(Date.now() + days * 86400000);
  return `${d.toISOString().slice(0, 10)}T23:59:00+09:00`;
};

const postings = {
  'demo-job-1': {
    job_id: 'demo-job-1', source: 'SARAMIN_POC', source_url: 'https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=00000001',
    company: '(주)데이터웨이브', title: '데이터 분석가 (신입/주니어)',
    description: '서비스 로그 기반 지표 설계와 대시보드 운영을 함께할 데이터 분석가를 찾습니다.',
    region: '서울 강남구', career_type: 'NEW', min_career_years: null, employment_type: '정규직', education: '초대졸 이상',
    deadline: deadline(18), status: 'OPEN', required_skills: ['Python', 'SQL'], preferred_skills: ['Airflow', 'Tableau'],
  },
  'demo-job-2': {
    job_id: 'demo-job-2', source: 'JOBKOREA_POC', source_url: 'https://www.jobkorea.co.kr/Recruit/GI_Read/00000002',
    company: '(주)클라우드핏', title: '데이터 엔지니어 (배치 파이프라인)',
    description: 'Airflow 기반 배치 파이프라인을 운영하고 데이터 마트를 설계합니다.',
    region: '경기 성남시', career_type: 'NEW', min_career_years: null, employment_type: '정규직', education: '학력무관',
    deadline: deadline(25), status: 'OPEN', required_skills: ['Python', 'Airflow', 'SQL'], preferred_skills: ['Spark'],
  },
  'demo-job-3': {
    job_id: 'demo-job-3', source: 'SARAMIN_POC', source_url: 'https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=00000003',
    company: '(주)리테일인사이트', title: '마케팅 데이터 분석 (GA4)',
    description: 'GA4 · 광고 데이터로 캠페인 성과를 분석합니다.',
    region: '서울 마포구', career_type: 'NEW', min_career_years: null, employment_type: '정규직', education: '초대졸 이상',
    deadline: deadline(9), status: 'OPEN', required_skills: ['SQL', 'GA4'], preferred_skills: ['Python'],
  },
};

const recommendations = [
  {
    job_id: 'demo-job-1', title: postings['demo-job-1'].title, company: postings['demo-job-1'].company,
    source_url: postings['demo-job-1'].source_url, fit: '높음',
    reasons: [
      { claim: 'Python · SQL 데이터 정제 경험이 필수 요건과 맞습니다.', resume_quote: 'Python·Pandas·SQL로 데이터 정제와 집계 파이프라인 구축', job_quote: 'Python, SQL 을 활용한 데이터 추출 · 가공 경험' },
      { claim: '주간 리포트 자동화 경험이 대시보드 운영 업무와 이어집니다.', resume_quote: 'GA4 이벤트 로그를 정리해 주간 유입 리포트를 자동화했습니다.', job_quote: '핵심 지표 대시보드 설계 및 운영' },
    ],
    concerns: ['Tableau 사용 경험은 이력서에서 확인되지 않습니다.'],
    conditions: { region: '서울 강남구', employment_type: '정규직', career: '신입', education: '초대졸 이상', deadline: postings['demo-job-1'].deadline },
    filter_status: 'PASS', unknown_conditions: [], body_is_image: false,
  },
  {
    job_id: 'demo-job-2', title: postings['demo-job-2'].title, company: postings['demo-job-2'].company,
    source_url: postings['demo-job-2'].source_url, fit: '보통',
    reasons: [
      { claim: 'Airflow 배치 스케줄링 경험이 주요 업무와 겹칩니다.', resume_quote: 'Airflow로 배치 스케줄링', job_quote: 'Airflow 기반 배치 파이프라인 운영' },
    ],
    concerns: ['Spark 는 초급으로 적혀 있어 우대 요건과 차이가 있습니다.'],
    conditions: { region: '경기 성남시', employment_type: '정규직', career: '신입', education: '학력무관', deadline: postings['demo-job-2'].deadline },
    filter_status: 'PASS', unknown_conditions: [], body_is_image: false,
  },
  {
    job_id: 'demo-job-3', title: postings['demo-job-3'].title, company: postings['demo-job-3'].company,
    source_url: postings['demo-job-3'].source_url, fit: '보통',
    reasons: [
      { claim: 'GA4 로그 정리 경험이 공고의 분석 도구와 같습니다.', resume_quote: 'GA4 이벤트 로그를 정리해', job_quote: 'GA4 · 광고 데이터로 캠페인 성과 분석' },
    ],
    concerns: [],
    conditions: { region: '서울 마포구', employment_type: '정규직', career: '신입', education: '초대졸 이상', deadline: postings['demo-job-3'].deadline },
    filter_status: 'PASS', unknown_conditions: [], body_is_image: false,
  },
];

const chatJob = (p) => ({
  job_id: p.job_id, company: p.company, title: p.title, source_url: p.source_url, region: p.region,
  career: '신입', employment_type: p.employment_type, deadline: p.deadline, tech_stack: [...p.required_skills, ...p.preferred_skills],
});

const requirements = [
  { id: 'req-1', group: 'must', label: 'Python · SQL 데이터 가공', posting_quote: 'Python, SQL 을 활용한 데이터 추출 · 가공 경험' },
  { id: 'req-2', group: 'must', label: '지표 대시보드 운영', posting_quote: '핵심 지표 대시보드 설계 및 운영' },
  { id: 'req-3', group: 'preferred', label: 'Airflow 배치 경험', posting_quote: 'Airflow 등 워크플로 도구 사용 경험' },
  { id: 'req-4', group: 'preferred', label: 'Tableau 시각화', posting_quote: 'Tableau 로 대시보드를 만들어 본 경험' },
  { id: 'req-5', group: 'task', label: '서비스 로그 분석', posting_quote: '서비스 로그 기반 사용자 행동 분석' },
];

const requirementMap = [
  { ...requirements[0], status: 'met', evidence_paths: ['coreCompetencies.text'], evidence_quotes: ['Python·Pandas·SQL로 데이터 정제'], source: 'resume', kind: 'skill' },
  { ...requirements[1], status: 'partial', evidence_paths: ['experience[0].description'], evidence_quotes: ['주간 유입 리포트를 자동화'], source: 'resume', kind: 'experience' },
  { ...requirements[2], status: 'met', evidence_paths: ['coreCompetencies.text'], evidence_quotes: ['Airflow로 배치 스케줄링'], source: 'resume', kind: 'skill' },
  { ...requirements[3], status: 'unconfirmed', evidence_paths: [], evidence_quotes: [], source: 'none', kind: 'skill' },
];

function reviewResponse(general) {
  return {
    review_id: `demo-review-${general ? 'g' : 'j'}`,
    input_hash: 'demo-hash',
    summary: general
      ? '핵심역량과 경력 문장은 구체적이에요. 결과가 드러나지 않는 문장 두 곳을 다듬어 볼게요.'
      : '(주)데이터웨이브 데이터 분석가 공고와 비교했어요. 필수 요건 2개 중 1개는 이력서에서 확인되고, 1개는 일부만 드러나요.',
    sentence_reviews: [
      {
        field_path: 'experience[0].description', edit_type: 'impact',
        original_quote: 'GA4 이벤트 로그를 정리해 주간 유입 리포트를 자동화했습니다.',
        suggested_revision: 'GA4 이벤트 로그를 Python 으로 정리해 주간 유입 리포트를 자동화하고, 매주 수작업으로 만들던 보고서 작성 시간을 줄였습니다.',
        reason: '무엇으로 자동화했는지와 그 결과를 함께 적으면 담당 업무가 더 분명해져요. 이력서에 없는 수치는 넣지 않았어요.',
      },
      {
        field_path: 'coreCompetencies.text', edit_type: 'clarity',
        original_quote: 'Spark 기초와 Tensorflow 모델 학습 실습 경험.',
        suggested_revision: 'Spark 기초 실습과 Tensorflow 모델 학습 실습을 경험했습니다.',
        reason: '명사로 끝난 문장을 완결된 문장으로 바꿨어요.',
      },
    ],
    requirement_map: general ? [] : requirementMap,
    star_checks: [],
    grounding_warnings: [],
    job_source: general ? null : { company: '(주)데이터웨이브', title: '데이터 분석가 (신입/주니어)', snapshot_hash: 'demo-job-hash' },
    telemetry: {},
  };
}

function answerResponse() {
  return {
    draft:
      '데이터로 사용자의 행동을 설명하는 일에 관심이 있어 (주)데이터웨이브에 지원했습니다. 인턴으로 일하며 GA4 이벤트 로그를 정리해 주간 유입 리포트를 자동화했고, ' +
      '이 과정에서 지표를 꾸준히 보는 일의 가치를 배웠습니다. Python·Pandas·SQL로 데이터를 정제하고 Airflow로 배치를 돌려 본 경험을 살려, 핵심 지표 대시보드를 안정적으로 운영하겠습니다.',
    char_count: 238,
    limit: 500,
    sentences: [
      { text: '인턴으로 일하며 GA4 이벤트 로그를 정리해 주간 유입 리포트를 자동화했고', basis: 'resume', quote: 'GA4 이벤트 로그를 정리해 주간 유입 리포트를 자동화했습니다.', requirement_ids: ['req-2'] },
      { text: 'Python·Pandas·SQL로 데이터를 정제하고 Airflow로 배치를 돌려 본 경험', basis: 'resume', quote: 'Python·Pandas·SQL로 데이터 정제와 집계 파이프라인 구축, Airflow로 배치 스케줄링', requirement_ids: ['req-1', 'req-3'] },
      { text: '핵심 지표 대시보드를 안정적으로 운영하겠습니다', basis: 'posting', quote: '핵심 지표 대시보드 설계 및 운영', requirement_ids: ['req-2'] },
    ],
    dropped: 0,
    gaps: [{ requirement_id: 'req-4', question: 'Tableau 로 대시보드를 만들어 본 적이 있나요? 있다면 무엇을 보여 주는 대시보드였나요?' }],
    requirements: requirements.map(({ id, group, label }) => ({ id, group, label })),
  };
}

const json = (route, body, status = 200) =>
  route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) });

/// 페이지의 /api 요청을 예시 응답으로 바꾼다. 모르는 요청은 404 로 막아 실서버로 나가지 않게 한다.
export async function installMocks(page, { delayMs = 0 } = {}) {
  const wait = () => new Promise((r) => setTimeout(r, delayMs));
  await page.route(/\/api\//, async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname.replace(/^.*?\/api/, '');
    const body = (() => {
      try {
        return route.request().postDataJSON() ?? {};
      } catch {
        return {};
      }
    })();

    if (p === '/jobs/recommend') {
      await wait();
      return json(route, { search_query: '데이터 분석가 · Python · SQL · Pandas · Airflow', notice: '', warnings: [], recommendations });
    }
    if (p === '/jobs/chat/stream') return json(route, { detail: 'stream off' }, 404);
    if (p === '/jobs/chat') {
      await wait();
      return json(route, {
        mode: '검색',
        reply: '서울 · 경기에서 신입을 뽑는 데이터 분석 · 엔지니어 공고 3건을 찾았어요. 마감이 가까운 순으로 정리했어요.',
        filters: { region: ['서울', '경기'], career: '신입' },
        jobs: Object.values(postings).map(chatJob),
        suggestions: ['이 중에서 내 이력서와 가장 잘 맞는 공고는?', 'Airflow 를 쓰는 공고만 보여 줘'],
      });
    }
    if (p === '/posting-link') return json(route, postings['demo-job-1']);
    if (p.startsWith('/postings/')) {
      const id = decodeURIComponent(p.slice('/postings/'.length));
      return json(route, postings[id] ?? { ...postings['demo-job-1'], job_id: id });
    }
    if (p === '/resume-review/requirements') return json(route, { requirements });
    if (p === '/resume-review/context') {
      return json(route, {
        content: demoResume(),
        input_hash: 'demo-hash',
        job_source: body.selectedJobId ? { snapshot_hash: 'demo-job-hash', company: '(주)데이터웨이브', title: '데이터 분석가 (신입/주니어)' } : null,
      });
    }
    if (p === '/resume-review/tailored' || p === '/resume-review/tailored/get') {
      return json(route, { tailored_resume_id: 'demo-tailored-1', content: demoResume(), review_session: {} });
    }
    if (p === '/resume-review/session') return json(route, { ok: true });
    if (p === '/resume-review') {
      await wait();
      return json(route, reviewResponse(body.reviewMode === 'general'));
    }
    if (p === '/resume-review/question-answer') {
      await wait();
      return json(route, answerResponse());
    }
    if (p === '/resume-review/question-extract-link') {
      return json(route, {
        questions: [
          { question: '지원 동기와 입사 후 포부를 작성해 주세요.', limit: 500 },
          { question: '데이터로 문제를 해결한 경험을 작성해 주세요.', limit: 700 },
        ],
      });
    }
    return json(route, { detail: 'guide mock: not available' }, 404);
  });
}
