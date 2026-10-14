import { useMemo, useState } from 'react';

import { useAttendanceIssues, useDb, useSpotChecks } from '../../data/repository';
import { dateKeyOf } from '../../data/seed';
import type { User } from '../../domain/types';
import { Button, Checkbox, Chip, TextInput } from '../../ui/components';
import {
  StudentFilterHints,
  StudentFilterLabels,
  matchStudents,
  type StudentFilterId,
} from './studentFilters';
import './manager.css';

const FILTERS: StudentFilterId[] = ['missingCheckIn', 'missingAttendanceForm', 'absentInSpotCheck'];

/**
 * 지정 알림 대상 고르기 — 학생을 하나씩 고르거나, 빠른 필터(교집합)로 한 번에 고른다.
 * 아무도 고르지 않으면 기수 전체 알림이다.
 */
export function TargetPicker({
  cohortId,
  students,
  selected,
  onChange,
}: {
  cohortId: string;
  students: User[];
  selected: string[];
  onChange(next: string[]): void;
}) {
  const [dateKey, setDateKey] = useState(() => dateKeyOf(new Date()));
  const [filters, setFilters] = useState<StudentFilterId[]>([]);
  const [query, setQuery] = useState('');
  const attendances = useDb((db) => db.attendances);
  const issues = useAttendanceIssues();
  const spotChecks = useSpotChecks(cohortId);

  const roll = useMemo(
    () => [...students].sort((a, b) => a.displayName.localeCompare(b.displayName, 'ko')),
    [students],
  );
  const matched = matchStudents(roll, filters, dateKey, { attendances, issues, spotChecks });
  const chosen = new Set(selected);
  const q = query.trim();
  const shown = q === '' ? roll : roll.filter((s) => s.displayName.includes(q));

  const toggleFilter = (id: StudentFilterId) =>
    setFilters((f) => (f.includes(id) ? f.filter((x) => x !== id) : [...f, id]));

  const toggle = (uid: string) =>
    onChange(chosen.has(uid) ? selected.filter((u) => u !== uid) : [...selected, uid]);

  return (
    <div className="target-picker">
      <div className="target-picker__filters">
        <TextInput
          type="date"
          aria-label="필터 기준 날짜"
          value={dateKey}
          style={{ width: 160 }}
          onChange={(e) => setDateKey(e.target.value)}
        />
        {FILTERS.map((id) => (
          <span key={id} title={StudentFilterHints[id]}>
            <Chip selected={filters.includes(id)} onClick={() => toggleFilter(id)}>
              {StudentFilterLabels[id]}
            </Chip>
          </span>
        ))}
        {filters.length > 0 && (
          <Button size="sm" variant="outline" onClick={() => onChange(matched.map((s) => s.uid))}>
            조건에 맞는 {matched.length}명 고르기
          </Button>
        )}
      </div>
      <div className="target-picker__filters">
        <TextInput
          placeholder="이름 검색"
          aria-label="학생 이름 검색"
          value={query}
          style={{ width: 180 }}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="hint">
          {selected.length === 0 ? '고른 학생이 없으면 기수 전체에게 보입니다.' : `${selected.length}명 선택됨`}
        </span>
        {selected.length > 0 && (
          <Button size="sm" variant="text" onClick={() => onChange([])}>
            선택 해제(기수 전체)
          </Button>
        )}
      </div>
      <div className="target-picker__list" role="group" aria-label="알림 받을 학생">
        {shown.map((s) => (
          <Checkbox key={s.uid} checked={chosen.has(s.uid)} onChange={() => toggle(s.uid)} label={s.displayName} />
        ))}
        {shown.length === 0 && <span className="hint">학생이 없습니다.</span>}
      </div>
    </div>
  );
}
