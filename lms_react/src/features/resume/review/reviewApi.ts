import { http } from '../../../data/http';

/**
 * 첨삭 서버 호출 — ai_coach/data/resume_review_api_client.dart 를 Django 창구(/api/resume-review/*)로.
 *
 * 원본은 Firebase 토큰으로 첨삭 서버를 바로 불렀다. 우리 앱은 자체 JWT 라 Django 가 학생을 확인하고
 * uid 로 넘긴다. 요청 · 응답 모양(snake_case)은 원본 그대로 둔다 — 세션 저장본도 원본과 호환된다.
 */
export type Json = Record<string, unknown>;

export class ReviewApiError extends Error {
  constructor(
    message: string,
    readonly statusCode: number,
  ) {
    super(message);
  }
}

/** 원본 _failureMessage 그대로. 서버 detail 을 사람이 읽을 문장으로 바꾼다 */
function failureMessage(status: number, detail: string | undefined): string {
  const key = `${status}:${detail ?? ''}`;
  switch (key) {
    case '409:selected_job_closed':
    case '409:selected_job_expired':
      return '선택한 공고가 마감되어 맞춤 첨삭을 할 수 없습니다. 다른 공고를 선택해 주세요.';
    case '422:selected_job_full_text_unavailable':
      return '이 공고는 상세 내용이 이미지뿐이라 원문 근거 첨삭을 할 수 없습니다. 텍스트 공고를 선택해 주세요.';
    case '422:selected_job_deadline_unverified':
      return '선택한 공고의 마감일 형식을 확인할 수 없습니다. 공고 원문을 확인하거나 다른 공고를 선택해 주세요.';
    case '422:selected_job_not_found':
      return '선택한 공고 원문을 찾을 수 없습니다. 추천 목록을 새로고침한 뒤 다시 선택해 주세요.';
    case '422:invalid_selection':
    case '422:selection_not_applicable':
      return '선택한 수정안이 현재 이력서 원문에 적용될 수 없습니다. 첨삭을 다시 실행해 주세요.';
    case '422:unknown, duplicate or mismatched question':
      return '이전 단계의 질문 상태를 확인하지 못했습니다. 창을 닫고 최신 이력서로 첨삭을 다시 시작해 주세요.';
    case '409:resume_version_changed':
    case '409:resume_version_changed: reload the resume and review':
      return '수정안 적용으로 이력서가 갱신되었습니다. 기존 결과는 적용 전 내용 기준이므로 최신 이력서로 첨삭을 다시 시작해 주세요.';
    case '409:resume_changed_after_application':
      return '이력서가 적용 후 변경되어 되돌릴 수 없습니다. 최신 내용을 확인해 주세요.';
    // 앞서 적용한 수정안이 이 수정안의 원문을 바꿨다. 오류가 아니라 이미 다른 수정안으로 고친 문장이다
    case '409:ambiguous_or_masked_quote':
    case '409:overlapping_edits':
      return '이 문장은 앞서 적용한 수정안으로 이미 바뀌어 이 수정안은 적용할 수 없어요. 건너뛰고 다음으로 넘어가 주세요.';
    case '409:resume_item_changed':
      return '이력서 항목 구성이 바뀌어 새 프로젝트를 추가할 수 없어요. 최신 이력서로 첨삭을 다시 시작해 주세요.';
  }
  switch (status) {
    case 401:
      return '로그인이 만료됐습니다. 다시 로그인해 주세요.';
    case 403:
      return '본인 소유 이력서만 첨삭할 수 있습니다.';
    case 404:
      return '이력서를 찾을 수 없습니다.';
    case 409:
      return '이력서 또는 공고가 변경됐거나 요청이 처리 중입니다. 결과를 확인하고 다시 시도해 주세요.';
    case 422:
      return '첨삭에 필요한 공고 원문 또는 선택한 수정안을 확인할 수 없습니다.';
    case 503:
      return detail?.includes('연결') ? detail : '첨삭 서버 설정 또는 공고 원문 DB를 사용할 수 없습니다. 서버 로그의 오류 유형을 확인해 주세요.';
    default:
      return `첨삭 요청에 실패했습니다 (HTTP ${status}).`;
  }
}

async function post(path: string, body: Json): Promise<Json> {
  try {
    const { data } = await http.post<Json>(path, body, { timeout: 180_000 });
    return data;
  } catch (err) {
    const response = (err as { response?: { status?: number; data?: { detail?: unknown } } }).response;
    if (response?.status !== undefined) {
      const detail = typeof response.data?.detail === 'string' ? response.data.detail : undefined;
      throw new ReviewApiError(failureMessage(response.status, detail), response.status);
    }
    if ((err as { code?: string }).code === 'ECONNABORTED') {
      throw new ReviewApiError('응답 시간이 초과됐습니다. 재시도는 같은 요청 ID로 처리됩니다.', 0);
    }
    throw new ReviewApiError('첨삭 서버에 연결하지 못했습니다. 서버 주소와 실행 상태를 확인해 주세요.', 0);
  }
}

/** 원본 요청(snake_case)의 이력서 · 공고 식별자는 Django 가 채운다. 나머지는 그대로 넘긴다 */
export const reviewApi = {
  context: (resumeId: string, jobId?: string, tailoredResumeId?: string) =>
    post('/resume-review/context', { resumeId, selectedJobId: jobId, tailoredResumeId }),

  createTailored: (resumeId: string, jobId: string) =>
    post('/resume-review/tailored', { resumeId, selectedJobId: jobId }),

  tailored: (resumeId: string, tailoredResumeId: string) =>
    post('/resume-review/tailored/get', { resumeId, tailoredResumeId }),

  saveSession: (resumeId: string, tailoredResumeId: string, state: Json) =>
    post('/resume-review/session', { resumeId, tailoredResumeId, state }),

  promote: async (resumeId: string, tailoredResumeId: string): Promise<string> => {
    const data = await post('/resume-review/promote', { resumeId, tailoredResumeId });
    return String(data.workspace_resume_id ?? '');
  },

  review: (resumeId: string, request: Json) =>
    post('/resume-review', {
      resumeId,
      reviewMode: request.review_mode,
      reviewPhase: request.review_phase,
      requestId: request.request_id,
      expectedInputHash: request.expected_input_hash,
      expectedJobHash: request.expected_job_hash,
      previousReviewId: request.previous_review_id,
      selectedJobId: request.selected_job_id,
      tailoredResumeId: request.tailored_resume_id,
      answers: request.answers,
    }),

  apply: (resumeId: string, request: Json) =>
    post('/resume-review/apply', {
      resumeId,
      requestId: request.request_id,
      reviewId: request.review_id,
      expectedInputHash: request.expected_input_hash,
      selectedIndices: request.selected_indices,
      tailoredResumeId: request.tailored_resume_id,
    }),

  undo: (resumeId: string, request: Json) =>
    post('/resume-review/undo', {
      resumeId,
      reviewId: '',
      requestId: request.request_id,
      applicationId: request.application_id,
      expectedInputHash: request.expected_input_hash,
      tailoredResumeId: request.tailored_resume_id,
    }),
};
