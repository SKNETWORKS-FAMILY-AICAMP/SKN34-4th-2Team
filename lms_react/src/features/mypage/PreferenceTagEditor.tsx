import { useState } from 'react';

import { Icon } from '../../ui/Icon';
import '../resume/skills/skills.css';

/** 띄어쓰기·대소문자만 다른 값은 같은 것으로 본다(「AI엔지니어」 = 「AI 엔지니어」) */
const sameValue = (a: string, b: string) => a.replace(/\s+/g, '').toLowerCase() === b.replace(/\s+/g, '').toLowerCase();

/**
 * 취업 희망 조건 한 줄을 태그로 고르는 편집기 — 이력서 기술스택 편집기와 같은 모양.
 *
 * 미리 준비한 후보 태그를 눌러 켜고 끄고, 후보에 없으면 입력칸에 적고 Enter 로 추가한다.
 * 직접 추가한 값도 후보 뒤에 켜진 태그로 붙어서, 다시 누르면 빠진다.
 */
export function PreferenceTagEditor({
  values,
  presets,
  placeholder,
  onChange,
}: {
  values: string[];
  presets: readonly string[];
  placeholder: string;
  onChange(next: string[]): void;
}) {
  const [query, setQuery] = useState('');

  const has = (v: string) => values.some((x) => sameValue(x, v));
  const custom = values.filter((v) => !presets.some((p) => sameValue(p, v)));
  const options = [...presets, ...custom];

  const add = (raw: string) => {
    const typed = raw.trim();
    if (typed === '') return;
    // 후보에 있는 말이면 후보 표기로 넣는다 — 매처가 비교하는 값이 하나로 모인다
    const value = presets.find((p) => sameValue(p, typed)) ?? typed;
    if (!has(value)) onChange([...values, value]);
    setQuery('');
  };

  const toggle = (v: string) => {
    if (has(v)) onChange(values.filter((x) => !sameValue(x, v)));
    else onChange([...values, v]);
  };

  const trimmed = query.trim();

  return (
    <div className="tech-editor">
      <div className="skill-tags">
        {options.map((v) => {
          const selected = has(v);
          return (
            <button
              key={v}
              type="button"
              className={`skill-pick${selected ? ' is-selected' : ''}`}
              aria-pressed={selected}
              onClick={() => toggle(v)}
            >
              {v}
            </button>
          );
        })}
      </div>

      <div className="tech-editor__search mypref__add">
        <Icon name="add" size={18} />
        <input
          value={query}
          placeholder={placeholder}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key !== 'Enter' || e.nativeEvent.isComposing) return;
            e.preventDefault();
            add(query);
          }}
        />
        {trimmed !== '' && (
          <button type="button" className="btn btn--text btn--sm" onClick={() => add(query)}>
            추가
          </button>
        )}
      </div>
    </div>
  );
}
