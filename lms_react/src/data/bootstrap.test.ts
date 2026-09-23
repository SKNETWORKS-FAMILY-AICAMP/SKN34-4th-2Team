import { describe, expect, it } from 'vitest';

import { mapAlert, mapNotice, mapScheduled } from './bootstrap';

describe('Django bootstrap IDs', () => {
  it('uses the database primary key for routes that require numeric IDs', () => {
    const row = { id: 'legacy-notice-id', pk: 42, title: '공지' };

    expect(mapNotice(row).id).toBe('42');
    expect(mapScheduled(row).id).toBe('42');
    expect(mapAlert(row).id).toBe('42');
  });

  it('still accepts a plain ID in demo data', () => {
    expect(mapNotice({ id: 'n-demo', title: '공지' }).id).toBe('n-demo');
  });
});
