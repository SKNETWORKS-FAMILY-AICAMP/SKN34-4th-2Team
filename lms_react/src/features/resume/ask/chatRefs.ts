import { computeSections } from '../../../domain/constants';
import type { ResumeContent } from '../../../domain/types';

/**
 * 코치에게 묻기 — 무엇을 기억해 되돌려 보낼지.
 *
 * 서버는 대화를 저장하지 않는다. 직전에 무엇을 보여 줬는지는 화면이 `lastJobIds` 로
 * 되돌려 줘야 안다. 규칙은 원본 그대로다
 * (`ai_coach/data/chat_job_refs.dart`, `resume_text_builder.dart`, `ai_job_coach_panel.dart`).
 */

/** 답이 어떤 종류인가 — 서버 JobChatResponse.mode */
export type ChatMode = '검색' | '질문' | '공고' | '비교' | '추천' | '안내';

/** 추천을 이력서의 어디에 기대어 할지 — 서버 JobChatResponse.resume_scope */
export type ResumeScope = '전체' | '프로젝트' | '기술스택' | '자기소개서' | '경력';

/**
 * 이번 답을 받은 뒤 "2번"이 가리킬 목록.
 *
 * 번호는 **찾아 준 목록**을 가리킨다. 비교한 두 건이나 질문 답에 붙는 근거 공고는 그 목록이
 * 아니다. 2번과 5번을 비교한 뒤 "아까 1번 3번"이라고 하면 화면에 그대로 보이는 처음 목록에서
 * 골라야 한다. 0건인 검색도 앞 목록을 지킨다 — 보여 준 것이 없으니 바꿀 것도 없다.
 */
export function nextShownJobIds(mode: string, jobsInAnswer: string[], previous: string[]): string[] {
  return mode === '검색' && jobsInAnswer.length > 0 ? jobsInAnswer : previous;
}

/**
 * 같은 조건으로 **지금까지 보여 준 공고 전부.** "이거 말고"를 거듭할 때 서버가 뺀다.
 * 조건이 그대로인 동안 쌓고, 조건이 바뀌면 새로 센다.
 */
export function nextSeenJobIds(
  mode: string,
  jobsInAnswer: string[],
  previous: string[],
  sameConditions: boolean,
): string[] {
  if (mode !== '검색' || jobsInAnswer.length === 0) return previous;
  if (!sameConditions) return jobsInAnswer;
  return [...previous, ...jobsInAnswer.filter((id) => !previous.includes(id))];
}

/** 두 조건이 같은가. 서버가 돌려준 조건을 그대로 견준다. */
export function sameChatConditions(before: unknown, after: unknown): boolean {
  return JSON.stringify(before ?? null) === JSON.stringify(after ?? null);
}

/**
 * 이력서를 함께 보낼지. **가리킬 것이 있으면 보낸다** — 카드를 눌렀거나, 직전에 목록을 보여 줬거나.
 *
 * 카드를 누른 경우에만 보내던 때에는 "1번하고 3번 중 나한테 맞는 건?"에 "이력서는 없음"이라고
 * 답했다. 쓰이지 않는 턴에 실려 가도 모델에는 들어가지 않는다.
 */
export function shouldSendResume(askingAboutJob: boolean, hasShownJobs: boolean): boolean {
  return askingAboutJob || hasShownJobs;
}

/** 좁힌 곳이 비어 있으면 추천이 근거 없이 돈다. 먼저 알린다. */
export function emptyScopeReason(scope: string, content: ResumeContent): string | null {
  const filled = computeSections(content);
  if (scope === '프로젝트' && content.projects.length === 0) {
    return '이력서에 프로젝트가 아직 없어요. 하나 적어 주시면 그걸 기준으로 찾아드릴게요.';
  }
  if (scope === '기술스택' && content.techStack.length === 0) {
    return '이력서에 기술스택이 아직 없어요. 쓸 줄 아는 기술을 넣어 주시면 그걸 기준으로 찾아드릴게요.';
  }
  if (scope === '자기소개서' && !filled.selfIntroduction && !filled.coreCompetencies) {
    return '이력서에 자기소개서가 아직 없어요. 한 항목이라도 적어 주시면 그걸 기준으로 찾아드릴게요.';
  }
  if (scope === '경력' && !filled.experience) {
    return '이력서에 경력이 아직 없어요. 신입이시라면 "내 프로젝트 경험만 보고 추천해줘"라고 해보세요.';
  }
  return null;
}

const SCOPE_SOURCE: Record<string, string> = {
  프로젝트: '프로젝트 경험',
  기술스택: '기술스택',
  자기소개서: '자기소개서',
  경력: '경력',
};

/** 몇 건을 골랐는지. 적합도 등급은 순서에만 쓰므로 말하지 않는다. */
export function recommendSummary(count: number, scope: string): string {
  const source = SCOPE_SOURCE[scope] ?? '이력서';
  if (count === 0) {
    return `${source}을 읽었지만 조건에 맞는 공고를 찾지 못했어요.\n희망 지역이나 고용형태를 넓혀 보시겠어요?`;
  }
  return `${source}을 읽고 ${count}건을 골랐어요.`;
}

/** 추천을 기다리는 동안 차례로 보일 말 — 무엇을 읽는 중인지 밝힌다 */
export function recommendBusyLabels(scope: string): string[] {
  const first = scope in SCOPE_SOURCE ? `${SCOPE_SOURCE[scope]}을 읽는 중…` : '이력서를 읽는 중…';
  return [first, '맞는 공고를 고르는 중…', '적합도를 비교하는 중…'];
}
