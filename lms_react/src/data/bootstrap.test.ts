import { describe, expect, it } from 'vitest';

import { mapAlert, mapBootstrap, mapNotice, mapScheduled } from './bootstrap';

describe('Django bootstrap IDs', () => {
  it('keeps only published PDF metadata, separate from curriculum CSV sheets', () => {
    const db = mapBootstrap({ curriculumPdfs: [
      { cohortId: 'cohort_34', originalFilename: 'curriculum.pdf', storageKey: 'cohorts/34/a.pdf', published: true },
      { cohortId: 'cohort_34', originalFilename: 'draft.pdf', storageKey: 'cohorts/34/b.pdf', published: false },
      { cohortId: 'cohort_34', published: true },
    ] });
    expect(db.curriculumPdfs).toEqual([{ cohortId: 'cohort_34', filename: 'curriculum.pdf' }]);
    expect(db.curriculumSheets).toEqual([]);
  });
  it('uses the database primary key for routes that require numeric IDs', () => {
    const row = { id: 'legacy-notice-id', pk: 42, title: '공지' };

    expect(mapNotice(row).id).toBe('42');
    expect(mapScheduled(row).id).toBe('42');
    expect(mapAlert(row).id).toBe('42');
  });

  it('still accepts a plain ID in demo data', () => {
    expect(mapNotice({ id: 'n-demo', title: '공지' }).id).toBe('n-demo');
  });

  it('maps persisted seat presence into the instructor screen shape', () => {
    const db = mapBootstrap({
      seatPresences: [{ presenceDate: '2026-09-24', period: '09', userId: 'student-uid', state: 'held' }],
    });
    expect(db.seatPresence).toEqual([
      { dateKey: '2026-09-24', period: 9, userId: 'student-uid', state: 'held' },
    ]);
  });
});
