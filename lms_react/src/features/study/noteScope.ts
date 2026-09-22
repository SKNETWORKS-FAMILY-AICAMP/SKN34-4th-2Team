import type { StudyNote, StudyNoteScopeType } from '../../domain/types';

/**
 * 노트 범위 규칙 — 공부방 백엔드(study_notes/service.py)와 DB(study_notes.scope_type · scope_key)를 그대로 따른다.
 *
 *   date    scope_key = '2026-09-15'            이름 '2026-09-15 수업'
 *   prefix  scope_key = 'prefix_python_day01'   이름 '폴더 python/day01'
 *   files   scope_key = 'files_<해시>'           이름 '파일 a.py, b.py'
 *
 * 백엔드는 files 해시에 sha1 앞 12자를 쓴다. 브라우저 데모는 같은 자리에 짧은 해시를 쓴다(데모에서만 만든다).
 */

export function buildScopeKey(type: StudyNoteScopeType, value: string | string[]): string {
  if (type === 'date') return String(value);
  if (type === 'prefix') {
    const safe = String(value).replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 80);
    return `prefix_${safe || 'root'}`;
  }
  const joined = (Array.isArray(value) ? value : [value]).join('\n');
  let h = 0x811c9dc5;
  for (let i = 0; i < joined.length; i++) h = Math.imul(h ^ joined.charCodeAt(i), 0x01000193) >>> 0;
  return `files_${h.toString(16).padStart(8, '0')}`;
}

/** 백엔드 scope_label 과 같은 이름 */
export function scopeLabel(type: StudyNoteScopeType, value: string | string[]): string {
  if (type === 'date') return `${value} 수업`;
  if (type === 'prefix') return `폴더 ${value}`;
  const names = (Array.isArray(value) ? value : [value]).map((p) => String(p).split('/').pop());
  return `파일 ${names.join(', ')}`;
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** 날짜로 만든 노트면 그 날짜 'YYYY-MM-DD' */
export function noteDate(note: StudyNote): string | null {
  if (note.scopeType && note.scopeType !== 'date') return null;
  const value = typeof note.scopeValue === 'string' ? note.scopeValue : note.scopeKey ?? '';
  return DATE.test(value) ? value : null;
}

/** 목록에 보일 노트 이름 — 날짜 노트는 '09/15 수업', 나머지는 백엔드 이름 규칙 */
export function noteLabel(note: StudyNote): string {
  const date = noteDate(note);
  if (date) return `${date.slice(5).replace('-', '/')} 수업`;
  if (note.scopeType && note.scopeValue !== undefined) return scopeLabel(note.scopeType, note.scopeValue);
  return note.scopeKey ?? note.id;
}
