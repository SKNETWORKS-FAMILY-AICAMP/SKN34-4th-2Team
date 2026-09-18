import type { ReactNode } from 'react';

/**
 * 목록 화면 맨 위의 필터 줄 — core/widgets/filter_pill_header.dart
 *
 * 왼쪽에 「재원 8」 같은 알약 필터가 서고, 오른쪽에 검색과 주된 단추가 붙는다.
 * 화면 너비를 가로지르고 아래로 한 줄 선을 긋는다.
 */
export interface FilterPill {
  id: string;
  label: string;
  count?: number;
}

export function FilterPillHeader({
  pills,
  selected,
  onSelect,
  trailing,
}: {
  pills: FilterPill[];
  selected: string;
  onSelect(id: string): void;
  trailing?: ReactNode;
}) {
  return (
    <div className="pill-head">
      <div className="pill-head__pills">
        {pills.map((pill) => (
          <button
            key={pill.id}
            type="button"
            className={`pill${selected === pill.id ? ' pill--on' : ''}`}
            onClick={() => onSelect(pill.id)}
          >
            {pill.label}
            {pill.count !== undefined && <span className="pill__count">{pill.count}</span>}
          </button>
        ))}
      </div>
      {trailing !== undefined && <div className="pill-head__trailing">{trailing}</div>}
    </div>
  );
}
