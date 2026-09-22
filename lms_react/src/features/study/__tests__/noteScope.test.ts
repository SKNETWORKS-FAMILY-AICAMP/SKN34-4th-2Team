import { describe, expect, it } from 'vitest';

import { buildScopeKey, scopeLabel } from '../noteScope';

// study_notes/service.py 의 build_scope_key · scope_label 과 같아야 한다
describe('노트 범위 규칙', () => {
  it('키 — 날짜는 그대로, 폴더는 prefix_, 파일은 files_해시', () => {
    expect(buildScopeKey('date', '2026-09-15')).toBe('2026-09-15');
    expect(buildScopeKey('prefix', 'python/day01')).toBe('prefix_python_day01');
    expect(buildScopeKey('prefix', '///')).toBe('prefix_root');
    expect(buildScopeKey('files', ['a.py', 'b.py'])).toMatch(/^files_[0-9a-f]{8}$/);
    expect(buildScopeKey('files', ['a.py', 'b.py'])).toBe(buildScopeKey('files', ['a.py', 'b.py']));
  });

  it('이름', () => {
    expect(scopeLabel('date', '2026-09-15')).toBe('2026-09-15 수업');
    expect(scopeLabel('prefix', 'python/day01')).toBe('폴더 python/day01');
    expect(scopeLabel('files', ['lab/a.py', 'b.py'])).toBe('파일 a.py, b.py');
  });
});
