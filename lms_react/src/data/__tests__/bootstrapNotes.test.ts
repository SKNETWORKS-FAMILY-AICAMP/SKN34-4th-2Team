import { describe, expect, it } from 'vitest';

import { lessonDays } from '../../features/study/lessonDays';
import { mapBootstrap } from '../bootstrap';

// lms_api /bootstrap 이 보내는 study_notes 한 줄(ETL 로 채운 실제 DB 모양 그대로)
const row = {
  id: 'src-multimodal_2026-09-15',
  pk: 3,
  sourceId: 'src-multimodal',
  status: 'ready',
  scopeType: 'date',
  scopeValue: '2026-09-15',
  scopeKey: '2026-09-15',
  reportMarkdown: '## 요약',
  reviewMarkdown: '## 복습',
  files: [],
  createdAt: '2026-09-15T12:00:00+09:00',
};

describe('bootstrap 의 공부방 노트', () => {
  it('scope_type · scope_value 를 받아 날짜 노트로 읽는다', () => {
    const db = mapBootstrap({ studyNotes: [row] });
    expect(db.studyNotes[0]).toMatchObject({ scopeType: 'date', scopeValue: '2026-09-15', scopeKey: '2026-09-15' });
    expect(lessonDays([], db.studyNotes).map((d) => [d.date, d.note?.id])).toEqual([['2026-09-15', row.id]]);
  });
});
