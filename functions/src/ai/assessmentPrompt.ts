/**
 * AI 성취도평가 출제 프롬프트 버전.
 * 루트 .env의 ASSESSMENT_PROMPT_VERSION이 있으면 그 값을 쓰고, 없으면 기본값.
 * Functions에 반영하려면 sync-functions-env 후 firebase deploy --only functions.
 */
export const ASSESSMENT_PROMPT_VERSION_DEFAULT = "assess_q_v2";

export function assessmentPromptVersion(): string {
  const fromEnv = process.env.ASSESSMENT_PROMPT_VERSION?.trim();
  return fromEnv || ASSESSMENT_PROMPT_VERSION_DEFAULT;
}
export const ASSESSMENT_MODEL = "gpt-4o-mini";

export const ASSESSMENT_SYSTEM_PROMPT = `당신은 코딩 부트캠프 성취도 평가 출제자입니다.
반드시 아래 규칙을 지키세요.

[범위 제한 — 최우선]
1. 제공된 커리큘럼 행의 "교과목"과 "내용"(및 "세부"가 있으면 세부)에만 근거해 출제합니다.
2. 커리큘럼에 없는 기술·라이브러리·심화 주제·다른 과목 문제는 절대 출제하지 마세요.
3. "내용"이 짧은 키워드(예: Python, Database)이면, 그 키워드의 입문·기초 개념만 내고 범위를 넓히지 마세요.
4. 객관식 오답( distractors )도 같은 교과목·내용 안에서만 만드세요. 다른 과목 지식을 끌어오지 마세요.
5. 각 문제는 커리큘럼의 특정 일수(sourceDay)와 내용(sourceTopic)에 연결되어야 합니다.
6. 여러 내용이 섞인 구간이면, 문항을 내용별로 고르게 분배하세요.

[형식]
응답은 JSON만 출력합니다:
{"questions":[{"type":"mc"|"sa","prompt":"...","points":4,"choices":["A","B","C","D"],"correctIndex":0,"acceptedAnswers":["정답1"],"explanation":"...","sourceDay":1,"sourceTopic":"Python"}]}
- 객관식(mc): choices 정확히 4개, correctIndex는 0~3
- 단답(sa): acceptedAnswers 1개 이상(동의어·대소문자 변형 가능)
- explanation에는 해설만 한 줄로 적으세요 (sourceDay/sourceTopic은 별도 필드)
- sourceDay, sourceTopic은 커리큘럼 행과 일치해야 합니다`;

export type ReplaceHint = {
  draftId?: string;
  type?: string;
  sourceDay?: number | string | null;
  sourceTopic?: string | null;
  promptPreview?: string | null;
};

export function buildAssessmentUserPrompt(params: {
  sheetTitle: string;
  sheetId: string;
  from: number;
  to: number;
  subjectList: string;
  topicList: string;
  mcCount: number;
  saCount: number;
  corpus: string;
}): string {
  const parts: string[] = [];
  if (params.mcCount > 0) parts.push(`객관식(mc) ${params.mcCount}문항`);
  if (params.saCount > 0) parts.push(`단답(sa) ${params.saCount}문항`);
  const countLine =
    parts.length > 0 ? parts.join(", ") : "문항 0개";

  return `커리큘럼 시트: ${params.sheetTitle || params.sheetId}
일수 구간: ${params.from} ~ ${params.to}
허용 교과목: ${params.subjectList || "(없음)"}
허용 내용(토픽): ${params.topicList || "(없음)"}
이번에 만들 문항: ${countLine}만 생성하세요. (요청하지 않은 유형은 0개)

위 허용 교과목·내용 밖의 문제는 만들지 마세요.
각 문항의 sourceTopic은 아래 목록의 "내용" 중 하나여야 합니다.

커리큘럼 행:
${params.corpus}`;
}

/** 마음에 안 드는 문항만 같은 단원 기준으로 대체 생성 */
export function buildAssessmentRegenPrompt(params: {
  sheetTitle: string;
  sheetId: string;
  from: number;
  to: number;
  subjectList: string;
  topicList: string;
  corpus: string;
  replaceOf: ReplaceHint[];
}): string {
  const lines = params.replaceOf.map((h, i) => {
    const type = h.type === "sa" ? "sa" : "mc";
    const day = h.sourceDay != null ? String(h.sourceDay) : "?";
    const topic = h.sourceTopic ? String(h.sourceTopic) : "(미상)";
    const preview = h.promptPreview ?
      String(h.promptPreview).slice(0, 100) :
      "";
    return `${i + 1}. type=${type}, sourceDay=${day}, sourceTopic=${topic}` +
      (preview ? `, 기존문항요약="${preview}"` : "");
  });

  const mc = params.replaceOf.filter((h) => h.type !== "sa").length;
  const sa = params.replaceOf.filter((h) => h.type === "sa").length;

  return `커리큘럼 시트: ${params.sheetTitle || params.sheetId}
일수 구간: ${params.from} ~ ${params.to}
허용 교과목: ${params.subjectList || "(없음)"}
허용 내용(토픽): ${params.topicList || "(없음)"}

강사가 마음에 들지 않아 교체를 요청한 문항입니다.
각 항목과 같은 type·비슷한 sourceDay/sourceTopic으로, 내용은 다른 새 문항을 정확히 ${params.replaceOf.length}개 만드세요.
객관식 ${mc}개, 단답 ${sa}개. 요청 개수보다 많거나 적게 만들지 마세요.
기존 문항을 살짝 바꾼 수준이 아니라, 같은 단원을 다른 각도에서 묻는 새 문제로 작성하세요.

교체 대상:
${lines.join("\n")}

커리큘럼 행:
${params.corpus}`;
}
