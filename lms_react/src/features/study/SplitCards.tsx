import { Icon } from '../../ui/Icon';
import { Select } from '../../ui/components';
import { canSplit, dayNotice, splitProblem, type PlanCalendar, type PlanFile, type SplitChoice, type SplitState } from './folderUploadModel';

/**
 * 두 날에 걸친 파일 — 나눠 넣기(날짜마다 그날까지의 셀) 또는 한 날짜로 두기(통째로).
 * 서버가 찾은 것(이름에 날짜가 둘 · 제목에 날짜가 여럿)과 강사가 「두 날에 나누기」로 직접 나눈 노트북이 온다.
 * 노트북만 셀로 나눌 수 있다(.py · .md 는 한 날짜로).
 */

const short = (d: string) => (d ? `${Number(d.slice(5, 7))}/${Number(d.slice(8))}` : '-');
const PART = ['앞부분', '다음 부분', '그다음 부분', '그다음 부분'];

export function SplitCards({
  files,
  splits,
  calendar,
  disabled,
  onChange,
}: {
  files: PlanFile[];
  splits: SplitState;
  calendar: PlanCalendar;
  disabled: boolean;
  onChange(path: string, choice: SplitChoice | null): void;
}) {
  if (!files.length) return null;
  return (
    <div className="fu__splits" aria-label="두 날에 걸친 파일">
      <strong className="fu__splits-title">
        <Icon name="call_split" size={16} /> 두 날에 걸친 파일
      </strong>
      {files.map((f) => (
        <SplitCard key={f.path} file={f} choice={splits[f.path]} calendar={calendar} disabled={disabled} onChange={(c) => onChange(f.path, c)} />
      ))}
      <p className="hint fu__splits-note">
        나눠 넣으면 앞 날짜 커밋엔 그날까지의 셀만, 마지막 날짜엔 전체를 넣어요. 노트 · 복습 문제는 날마다 새로 더해진 셀만 다뤄요.
      </p>
    </div>
  );
}

function SplitCard({
  file: f,
  choice,
  calendar,
  disabled,
  onChange,
}: {
  file: PlanFile;
  choice: SplitChoice;
  calendar: PlanCalendar;
  disabled: boolean;
  onChange(choice: SplitChoice | null): void;
}) {
  const cells = f.cells ?? [];
  const splittable = canSplit(f);
  const why = choice.manual ? `직접 나눔 · 셀 ${cells.length}개` : f.from === 'name' ? '이름에 날짜가 두 개예요' : `제목에 날짜가 ${f.dates?.length ?? 0}개 있어요`;
  const problem = splitProblem(choice, calendar, cells.length);
  const setDate = (k: number, value: string) => onChange({ ...choice, dates: choice.dates.map((d, i) => (i === k ? value : d)) });
  const setCut = (k: number, value: number) => onChange({ ...choice, cuts: choice.cuts.map((c, i) => (i === k ? value : c)) });
  const singleDates = choice.manual ? choice.dates.filter(Boolean) : f.dates ?? choice.dates;

  return (
    <div className={`fu__split${problem ? ' fu__split--check' : ''}`}>
      <div className="fu__split-head">
        <b>{f.path}</b>
        <span className="hint">
          {why}
          {!choice.manual && f.dates?.length ? ` · ${f.dates.map(short).join(' · ')}` : ''}
        </span>
        {choice.manual && (
          <button type="button" className="fu__more" disabled={disabled} onClick={() => onChange(null)}>
            나누기 취소
          </button>
        )}
      </div>
      {splittable && (
        <label className="fu__split-opt">
          <input
            type="radio"
            name={`split-${f.path}`}
            checked={choice.mode === 'split'}
            disabled={disabled}
            onChange={() => onChange({ ...choice, mode: 'split', cuts: choice.cuts.length ? choice.cuts : [Math.max(1, Math.floor(cells.length / 2))] })}
          />
          나눠 넣기
        </label>
      )}
      {choice.mode === 'split' && (
        <ol className="fu__parts">
          {choice.dates.map((d, k) => {
            const from = k === 0 ? 0 : choice.cuts[k - 1];
            const to = k < choice.cuts.length ? choice.cuts[k] : cells.length;
            const notice = dayNotice(d, calendar);
            return (
              <li key={k} className="fu__part">
                <input
                  type="date"
                  className="input"
                  value={d}
                  min={calendar.start}
                  max={calendar.today}
                  disabled={disabled}
                  aria-label={`${f.path} ${k + 1}번째 날짜`}
                  onChange={(e) => setDate(k, e.target.value)}
                />
                <span className="hint">
                  {PART[Math.min(k, PART.length - 1)]} — {from + 1}~{to}번 셀
                  {k === 0 && cells[0] ? ` 「${cells[0]}」부터` : ''}
                </span>
                {k > 0 && (
                  <Select
                    aria-label={`${f.path} ${k + 1}번째 날짜가 시작하는 셀`}
                    value={String(choice.cuts[k - 1])}
                    disabled={disabled}
                    onChange={(e) => setCut(k - 1, Number(e.target.value))}
                  >
                    {cells.map((line, i) =>
                      i === 0 ? null : (
                        <option key={i} value={i}>
                          {i + 1}번 셀 「{line || '(빈 셀)'}」부터
                        </option>
                      ),
                    )}
                  </Select>
                )}
                {notice && <span className="fu__notice">{notice}</span>}
              </li>
            );
          })}
        </ol>
      )}
      <label className="fu__split-opt">
        <input
          type="radio"
          name={`split-${f.path}`}
          checked={choice.mode === 'single'}
          disabled={disabled || singleDates.length === 0}
          onChange={() => onChange({ ...choice, mode: 'single', dates: choice.manual ? choice.dates : f.dates ?? choice.dates })}
        />
        한 날짜로 두기 —
        <Select
          aria-label={`${f.path} 넣을 날짜`}
          value={choice.mode === 'single' ? choice.dates[0] ?? '' : singleDates[0] ?? ''}
          disabled={disabled || choice.mode !== 'single'}
          onChange={(e) => onChange({ ...choice, mode: 'single', dates: [e.target.value, ...choice.dates.filter((d) => d !== e.target.value)] })}
        >
          {singleDates.map((d) => (
            <option key={d} value={d}>
              {short(d)}
            </option>
          ))}
        </Select>
        수업으로 통째로{!splittable ? ' (노트북이 아니라 셀로 나눌 수 없어요)' : ''}
      </label>
      {problem && <span className="fu__notice">{problem}</span>}
    </div>
  );
}
