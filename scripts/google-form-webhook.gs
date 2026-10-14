/**
 * Google Forms → PLAYDATA LMS Webhook
 *
 * LMS 관리자 → 설문 상세 → "Apps Script 코드 복사"가 이 파일과 같은 코드를 넣는다.
 * 복사본은 WEBHOOK_URL / COHORT_ID / TASK_ID 가 채워져 있다.
 *
 * 1. WEBHOOK_SECRET = firebase functions:secrets:set GOOGLE_FORM_WEBHOOK_SECRET 값
 * 2. 트리거: 실행할 함수 onFormSubmit / 이벤트 소스 설문지에서 / 양식 제출 시 (하나만)
 * 3. 구글폼 설정 → 응답 → 이메일 주소 수집: 확인됨
 * 4. 이 편집기에서 "배포"는 하지 않는다. 폼 제출 트리거만 걸면 된다.
 */

const WEBHOOK_URL =
  'https://asia-northeast3-skn34-3rd-2team.cloudfunctions.net/googleFormWebhook';
const WEBHOOK_SECRET = 'YOUR_SECRET_HERE'; // Firebase Secret과 동일하게!
const COHORT_ID = 'cohort_34';
const TASK_ID = 'YOUR_TASK_ID'; // LMS 설문 상세에서 복사

function onFormSubmit(e) {
  const response = resolveResponse(e);
  if (!response) {
    console.error('폼 응답을 찾지 못했습니다. 폼을 먼저 제출하세요.');
    return;
  }

  const answers = collectAnswers(response);
  const email = extractEmail(response) || '';
  if (!email && !answers['이름']) {
    console.warn('이메일/이름 없음 — 이메일 수집을 켜거나 이름 문항을 확인하세요.');
    return;
  }
  if (WEBHOOK_SECRET === 'YOUR_SECRET_HERE') {
    console.error('WEBHOOK_SECRET을 Firebase Secret 값으로 바꿔주세요.');
    return;
  }

  const res = UrlFetchApp.fetch(WEBHOOK_URL, {
    method: 'post',
    contentType: 'application/json',
    headers: { 'X-Webhook-Secret': WEBHOOK_SECRET },
    payload: JSON.stringify({
      cohortId: COHORT_ID,
      taskId: TASK_ID,
      email: String(email).trim().toLowerCase(),
      responseId: response.getId(),
      answers: answers,
    }),
    muteHttpExceptions: true,
  });

  const code = res.getResponseCode();
  console.log('Webhook', code, res.getContentText(), 'email:', email);
  if (code !== 200) {
    console.error('LMS 연동 실패:', code, res.getContentText());
  }
}

/** 트리거 이벤트에 response가 없으면(수동 실행 등) 폼의 최신 응답을 쓴다. */
function resolveResponse(e) {
  if (e && e.response) return e.response;
  const responses = FormApp.getActiveForm().getResponses();
  return responses.length ? responses[responses.length - 1] : null;
}

function collectAnswers(response) {
  const answers = {};
  const items = response.getItemResponses();
  for (var i = 0; i < items.length; i++) {
    const title = items[i].getItem().getTitle();
    const resp = items[i].getResponse();
    answers[title] = Array.isArray(resp) ? resp.join(', ') : String(resp);
  }
  return answers;
}

function extractEmail(response) {
  const respondent = response.getRespondentEmail();
  if (respondent) return respondent;
  const items = response.getItemResponses();
  for (var i = 0; i < items.length; i++) {
    const title = items[i].getItem().getTitle();
    if (title.includes('이메일') || title.toLowerCase().includes('email')) {
      return items[i].getResponse();
    }
  }
  return null;
}
