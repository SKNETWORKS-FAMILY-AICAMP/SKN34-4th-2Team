import { useMemo, useState } from 'react';

import { useDb } from '../../data/repository';
import { dateKeyOf } from '../../data/seed';
import type { User } from '../../domain/types';
import { Badge, Row, Spacer, TextInput } from '../../ui/components';
import { periodLabelOf, rollCallSessions, rollCallTable, type RollCallSession } from '../attendance/rollCallTable';
import { ExportMenu } from '../export/ExportMenu';
import { useSeatLabel } from '../manager/SpotCheck';
import '../manager/manager.css';

/** 교시 호명 기록 — 강사가 남긴 확인 · 보류를 기간 · 교시별로 보고 내려받는다. */
export function RollCallRecords({ cohortId, cohortName, students }: { cohortId: string; cohortName: string; students: User[] }) {
  const presence = useDb((db) => db.seatPresence);
  const seatLabelOf = useSeatLabel(cohortId, students);
  const [to, setTo] = useState(() => dateKeyOf(new Date()));
  const [from, setFrom] = useState(() => dateKeyOf(new Date(Date.now() - 6 * 86_400_000)));

  const sessions = useMemo(() => rollCallSessions(presence, students, from, to), [presence, students, from, to]);
  const shown = [...sessions].reverse();

  const exportProps = (list: RollCallSession[], label: string) => ({
    fileName: `교시호명_${cohortName || cohortId}_${label}`,
    build: () => {
      const table = rollCallTable(list, presence, students, seatLabelOf);
      return { ...table, title: `${table.title} · ${cohortName || cohortId} · ${label}` };
    },
  });

  return (
    <div className="spot-check">
      <div className="panel toolbar-card spot-check__toolbar">
        <label className="spot-check__field">
          <span className="hint">시작일</span>
          <TextInput type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="spot-check__field">
          <span className="hint">종료일</span>
          <TextInput type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} />
        </label>
        <Spacer />
        <ExportMenu label="기간 전체 내려받기" disabled={sessions.length === 0} {...exportProps(sessions, `${from}~${to}`)} />
      </div>
      <p className="hint">강사가 「자리 확인」에서 교시마다 호명한 기록입니다. 호명하지 않은 학생은 「미확인」으로 내려받습니다.</p>

      {shown.length === 0 ? (
        <p className="panel panel--empty hint">이 기간에 호명한 교시가 없습니다.</p>
      ) : (
        <div className="panel panel--flush">
          <table className="table">
            <thead>
              <tr>
                <th>날짜</th>
                <th style={{ width: 100 }}>교시</th>
                <th>결과</th>
                <th style={{ width: 140 }} />
              </tr>
            </thead>
            <tbody>
              {shown.map((s) => (
                <tr key={`${s.dateKey}-${s.period}`}>
                  <td>{s.dateKey}</td>
                  <td>{periodLabelOf(s.period)}</td>
                  <td>
                    <Row gap={6}>
                      <Badge tone="success">확인 {s.confirmed}</Badge>
                      <Badge tone="warning">보류 {s.held}</Badge>
                      <Badge tone="neutral">미확인 {s.unknown}</Badge>
                    </Row>
                  </td>
                  <td>
                    <ExportMenu {...exportProps([s], `${s.dateKey}_${periodLabelOf(s.period).replace(':', '')}`)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
