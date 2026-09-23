import { jobSkillNames } from './jobSkillNames';

/**
 * 기술스택 태그 후보 — resume/presentation/widgets/skill_catalog.dart.
 *
 * 부트캠프 수료생이 자주 적는 기술을 손으로 고른 기본 목록에, 수집한 채용공고가 실제로
 * 요구하는 기술을 합친다. 공고 쪽 이름이 들어가야 태그를 고르는 것만으로 공고에 쓰인 표기를 쓴다.
 */
const BASE_SKILLS = [
  // 언어
  'Python', 'Java', 'JavaScript', 'TypeScript', 'Dart', 'Kotlin', 'Swift',
  'C', 'C++', 'C#', 'Go', 'Rust', 'R', 'SQL', 'HTML/CSS',
  // 백엔드 · 프레임워크
  'Spring Boot', 'FastAPI', 'Django', 'Flask', 'Node.js', 'Express', 'NestJS',
  'REST API', 'GraphQL', 'JPA',
  // 프론트엔드 · 모바일
  'React', 'Next.js', 'Vue', 'Flutter', 'React Native', 'Android', 'iOS',
  'Tailwind CSS',
  // 데이터 · AI
  'NumPy', 'Pandas', 'Matplotlib', 'Scikit-learn', 'PyTorch', 'TensorFlow',
  'Keras', 'OpenCV', 'Hugging Face', 'LangChain', 'LLM', 'RAG',
  'Deep Learning', 'Machine Learning', 'Data Analysis', 'NLP',
  'Streamlit', 'Airflow', 'Spark', 'Hadoop', 'Kafka', 'Tableau', 'Power BI',
  'Excel',
  // 데이터베이스
  'MySQL', 'PostgreSQL', 'Oracle', 'MongoDB', 'Redis', 'Elasticsearch',
  'Neo4j', 'Firebase', 'Firestore',
  // 인프라 · 협업
  'Linux', 'Docker', 'Kubernetes', 'AWS', 'GCP', 'Azure', 'Git', 'GitHub',
  'GitHub Actions', 'Jenkins', 'Nginx', 'Figma', 'Jira', 'Notion',
];

/**
 * 같은 기술인데 표기가 갈리는 것. **영문 하나만** 남긴다. 공고 태그는 한글이 많지만
 * 추천은 뜻으로 찾고(벡터 검색), 이력서는 사람이 읽는 문서라 영문 표기가 낫다.
 * `Power BI` 와 `파워빌더` 처럼 이름만 비슷하고 다른 제품은 넣지 않는다.
 */
const ALIASES: Record<string, string> = {
  딥러닝: 'Deep Learning',
  머신러닝: 'Machine Learning',
  데이터분석: 'Data Analysis',
  'nlp(자연어처리)': 'NLP',
};

const aliasOf = (name: string) => ALIASES[name.toLowerCase()] ?? name;

/** 기본 목록 + 공고 기술. 표기가 같으면 하나만. 기본 목록은 손으로 정한 순서, 공고 쪽은 그 뒤 이름순 */
export const allSkills: readonly string[] = (() => {
  const byKey = new Map<string, string>();
  const add = (name: string) => {
    const trimmed = name.trim();
    if (trimmed === '') return;
    const canonical = aliasOf(trimmed);
    if (!byKey.has(canonical.toLowerCase())) byKey.set(canonical.toLowerCase(), canonical);
  };
  BASE_SKILLS.forEach(add);
  jobSkillNames.forEach(add);
  const baseKeys = new Set(BASE_SKILLS.map((s) => aliasOf(s).toLowerCase()));
  const fromJobs = [...byKey.values()]
    .filter((n) => !baseKeys.has(n.toLowerCase()))
    .sort((a, b) => (a.toLowerCase() < b.toLowerCase() ? -1 : a.toLowerCase() > b.toLowerCase() ? 1 : 0));
  return [...BASE_SKILLS.map((s) => byKey.get(aliasOf(s).toLowerCase()) ?? aliasOf(s)), ...fromJobs];
})();

/** 검색어로 후보를 거른다. 앞이 맞는 것 먼저, 그다음 들어 있는 것. 비어 있으면 전체 */
export function searchSkills(query: string): string[] {
  const q = query.trim().toLowerCase();
  if (q === '') return [...allSkills];
  const starts: string[] = [];
  const contains: string[] = [];
  for (const name of allSkills) {
    const lower = name.toLowerCase();
    if (lower.startsWith(q)) starts.push(name);
    else if (lower.includes(q)) contains.push(name);
  }
  return [...starts, ...contains];
}

/** 대소문자 · 앞뒤 공백 차이를 무시하고 같은 기술로 본다 */
export const sameSkill = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();

/** 목록에 있는 표기로 맞춘다. 별칭을 먼저 본다(예전에 저장된 「딥러닝」). 없으면 입력 그대로 */
export function canonicalSkill(name: string): string {
  const aliased = aliasOf(name.trim());
  return allSkills.find((candidate) => sameSkill(candidate, aliased)) ?? aliased;
}

/**
 * 숙련도 단계 — shared/models/tech_skill_level.dart. 이력서에는 이름만 저장한다.
 * 설명은 고를 때 기준을 맞추려는 것이고, 숫자 대신 말로 보여 준다.
 */
export const TECH_SKILL_LEVELS = [
  { label: '입문', description: '기본 문법과 개념을 학습했다' },
  { label: '초급', description: '예제나 과제 수준을 혼자 구현할 수 있다' },
  { label: '중급', description: '프로젝트에 실제로 사용해 기능을 완성했다' },
  { label: '고급', description: '구조 설계와 성능 개선을 주도할 수 있다' },
  { label: '전문가', description: '기술 선정과 다른 사람 지도가 가능하다' },
] as const;

/** 저장된 숙련도에 맞는 단계. 예전 자유 입력 값이면 undefined */
export const techSkillLevelOf = (value: string) => TECH_SKILL_LEVELS.find((level) => level.label === value.trim());
