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
  it('서버는 jsonb 칸을 JSON 글자로 보낸다 — 풀어서 읽는다', () => {
    const db = mapBootstrap({
      studyNotes: [{ ...row, scopeValue: '"2026-09-15"', files: '[{"path":"a.ipynb","commit":"c1"}]' }],
      resumes: [{ id: 'r1', pk: 1, title: 't', status: 'submitted', isBaseResume: true,
        content: '{"basicInfo":{"name":"문성호","email":"a@b.c"}}', sections: '{"basicInfo":true,"projects":true}' }],
    });
    expect(db.studyNotes[0].scopeValue).toBe('2026-09-15');
    expect(db.studyNotes[0].files).toEqual([{ path: 'a.ipynb', commit: 'c1' }]);
    expect(lessonDays([], db.studyNotes)[0].date).toBe('2026-09-15');
    expect(db.resumes[0].content.basicInfo.name).toBe('문성호');
    expect(db.resumes[0].sections).toEqual({ basicInfo: true, projects: true });
    expect(db.resumes[0].status).toBe('feedbackRequested');
  });

  it('scope_type · scope_value 를 받아 날짜 노트로 읽는다', () => {
    const db = mapBootstrap({ studyNotes: [row] });
    expect(db.studyNotes[0]).toMatchObject({ scopeType: 'date', scopeValue: '2026-09-15', scopeKey: '2026-09-15' });
    expect(lessonDays([], db.studyNotes).map((d) => [d.date, d.note?.id])).toEqual([['2026-09-15', row.id]]);
  });
});
