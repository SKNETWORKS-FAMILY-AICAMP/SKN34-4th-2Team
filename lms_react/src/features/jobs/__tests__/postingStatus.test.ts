import { describe, expect, it } from 'vitest';

import { closedReason } from '../postingStatus';

describe('공고가 열려 있지 않은 까닭', () => {
  it('상태마다 다르게 말한다 — 목록에서 안 보인 것(REMOVED)을 내려갔다고 단정하지 않는다', () => {
    expect(closedReason('EXPIRED', '2026-09-20T23:59:59+09:00')).toBe('마감일(2026-09-20)이 지난 공고예요.');
    expect(closedReason('EXPIRED', null)).toBe('마감일이 지난 공고예요.');
    expect(closedReason('CLOSED', '2026-10-14')).toBe('사이트에서 접수가 마감된 공고예요.');
    expect(closedReason('REMOVED', null)).toContain('마감됐을 수 있는');
  });
});
