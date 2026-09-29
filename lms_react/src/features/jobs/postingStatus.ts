/**
 * 공고가 열려 있지 않은 까닭 — 수집기 상태값마다 뜻이 다르다(job_matching_bot/schemas/job_record.py).
 *
 * - EXPIRED: 마감일이 지났다
 * - CLOSED: 사이트 페이지에 「마감되었습니다」가 떠 있다(조기 마감 포함)
 * - REMOVED: 수집할 때 사이트 목록에서 몇 번 안 보였다. 내려갔다는 증거는 아니다 —
 *   공고 맞춤 지원은 불러올 때 페이지를 열어 확인하고, 그래도 모를 때만 이 상태가 남는다
 */
export function closedReason(status: string, deadline: string | null): string {
  switch (status) {
    case 'EXPIRED':
      return deadline ? `마감일(${deadline.slice(0, 10)})이 지난 공고예요.` : '마감일이 지난 공고예요.';
    case 'CLOSED':
      return '사이트에서 접수가 마감된 공고예요.';
    case 'REMOVED':
      return '사이트 목록에서 보이지 않아 마감됐을 수 있는 공고예요. 원문 링크에서 직접 확인해 주세요.';
    default:
      return '지금은 지원을 받지 않는 공고예요.';
  }
}
