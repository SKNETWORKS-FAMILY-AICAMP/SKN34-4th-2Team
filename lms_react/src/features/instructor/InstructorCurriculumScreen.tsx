import { useState } from 'react';

import { replaceCurriculumSheet, useCurriculumSheets } from '../../data/repository';
import { nextId } from '../../data/store';
import type { CurriculumRow } from '../../domain/types';
import { InstructorTargets } from '../../tour/targets';
import { useTourTarget } from '../../tour/useTourTarget';
import { Icon } from '../../ui/Icon';
import { Button, Dialog, Field, Row, Spacer, TextArea } from '../../ui/components';
import { formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';

/**
 * 커리큘럼 — features/instructor/presentation/instructor_curriculum_screen.dart
 *
 * 실제 앱은 구글시트 CSV 파일을 올린다. 프로토타입은 같은 형식의 CSV 텍스트를
 * 붙여 넣게 한다. 올린 뒤 표가 통째로 바뀌는 동작은 같다.
 */
export function InstructorCurriculumScreen() {
  const sheets = useCurriculumSheets();
  const user = useCurrentUser();
  const uploadRef = useTourTarget(InstructorTargets.curriculumUpload);
  const [open, setOpen] = useState(false);
  const [csv, setCsv] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const sheet = sheets[0];

  const upload = () => {
    const rows = parseCsv(csv);
    if (rows.length === 0) {
      setError('읽을 수 있는 줄이 없습니다. 형식을 확인해 주세요.');
      return;
    }
    replaceCurriculumSheet({
      id: nextId('cs'),
      title: `${user.cohortName} 커리큘럼`,
      fileName: 'pasted.csv',
      rows,
      uploadedBy: user.uid,
      uploadedByName: user.displayName,
      uploadedAt: new Date(),
    });
    setOpen(false);
    setCsv('');
    setError(null);
  };

  const q = query.trim().toLowerCase();
  const rows = (sheet?.rows ?? []).filter(
    (r) =>
      q === '' ||
      String(r.dayIndex).includes(q) ||
      r.subject.toLowerCase().includes(q) ||
      r.topic.toLowerCase().includes(q) ||
      r.detail.toLowerCase().includes(q),
  );

  return (
    <div className="curri-page">
      <div className="curri-column">
        {sheet === undefined ? (
          <div className="list-page__empty">
            <Icon name="table_chart" size={44} />
            <p>등록된 커리큘럼이 없습니다</p>
            <Button onClick={() => setOpen(true)}>CSV 등록</Button>
          </div>
        ) : (
          <>
            <h1 className="curri-title">{sheet.title}</h1>
            <p className="curri-meta">
              {sheet.fileName} · {sheet.rows.length}행 · {formatDateTime(sheet.uploadedAt)}
            </p>

            <label className="study-search">
              <Icon name="search" size={20} />
              <input
                className="study-search__input"
                value={query}
                placeholder="검색 (일수·교과목·내용)"
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>

            {rows.map((r) => (
              <CurriculumRowCard key={`${r.dayIndex}-${r.order}`} row={r} />
            ))}
          </>
        )}
      </div>

      {/* 오른쪽 아래에 떠 있는 단추 — 원본의 확장 FAB */}
      <button type="button" className="curri-fab" ref={uploadRef} onClick={() => setOpen(true)}>
        <Icon name="upload_file" size={20} />
        CSV 교체
      </button>

      {open && (
        <Dialog
          title="CSV 등록/교체"
          width={620}
          onClose={() => setOpen(false)}
          actions={
            <>
              <Button variant="outline" onClick={() => setOpen(false)}>
                취소
              </Button>
              <Button onClick={upload}>등록</Button>
            </>
          }
        >
          <p className="muted">
            열 순서는 <code>일차, 표기, 교과목, 주제, 세부내용</code> 입니다. 첫 줄이 머리글이면 건너뜁니다.
          </p>
          <Field label="CSV 내용" error={error ?? undefined}>
            <TextArea
              rows={10}
              value={csv}
              placeholder={'1,1일차,프로그래밍과 데이터 기초,Python,변수와 자료형'}
              onChange={(e) => setCsv(e.target.value)}
            />
          </Field>
          <Row>
            <Spacer />
            <span className="hint">{parseCsv(csv).length}줄 인식됨</span>
          </Row>
        </Dialog>
      )}
    </div>
  );
}

/** 하루치 한 칸 — 누르면 세부 내용이 펼쳐진다. */
function CurriculumRowCard({ row }: { row: CurriculumRow }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="curri-row">
      <button type="button" className="curri-row__head" onClick={() => setOpen((v) => !v)}>
        <span className="curri-row__text">
          <strong>
            {row.dayIndex}. {row.topic}
          </strong>
          <span className="hint">
            {row.dateLabel} · {row.subject}
          </span>
        </span>
        <Icon name={open ? 'expand_less' : 'expand_more'} size={20} />
      </button>
      {open && <p className="curri-row__detail">{row.detail}</p>}
    </div>
  );
}

/** 아주 단순한 CSV 파서 — 따옴표 없는 쉼표 구분만 다룬다. */
export function parseCsv(text: string): CurriculumRow[] {
  const lines = text
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l !== '');
  const rows: CurriculumRow[] = [];
  lines.forEach((line, i) => {
    const cells = line.split(',').map((c) => c.trim());
    if (cells.length < 5) return;
    const dayIndex = Number(cells[0]);
    if (Number.isNaN(dayIndex)) return; // 머리글 줄
    rows.push({
      dayIndex,
      dateLabel: cells[1],
      subject: cells[2],
      topic: cells[3],
      detail: cells.slice(4).join(', '),
      order: i,
    });
  });
  return rows;
}
