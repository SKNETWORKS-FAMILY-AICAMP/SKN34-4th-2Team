import { useState } from 'react';

import type { ResumeContent } from '../../../domain/types';
import { Icon } from '../../../ui/Icon';
import { TECH_SKILL_LEVELS, canonicalSkill, sameSkill, searchSkills, techSkillLevelOf } from './skillCatalog';
import './skills.css';

type TechItem = ResumeContent['techStack'][number];

/** 한 페이지에 보여 줄 후보 수. 전부 펼치면 화면이 길어져 고르기 어렵다 */
const PAGE_SIZE = 40;

/**
 * 기술스택을 태그로 고르고, 숙련도를 설명이 달린 단계로 정하는 편집기 — widgets/tech_stack_editor.dart.
 *
 * - 위: 선택한 기술 태그. 태그를 누르면 그 기술의 숙련도 고르기가 열린다.
 * - 아래: 후보 태그. 검색으로 거르고, 후보에 없으면 직접 입력해 추가한다.
 * - 숙련도는 숫자가 아니라 단계 이름과 한 줄 설명을 가로로 늘어놓아 고른다.
 */
export function TechStackEditor({
  items,
  readOnly,
  onChange,
  newId,
}: {
  items: TechItem[];
  readOnly: boolean;
  onChange(next: TechItem[]): void;
  newId(): string;
}) {
  const [query, setQuery] = useState('');
  const [activeId, setActiveId] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const filled = items.filter((item) => item.name.trim() !== '');

  if (readOnly) {
    if (filled.length === 0) return <p className="hint">미작성</p>;
    return (
      <div className="skill-tags">
        {filled.map((item) => (
          <SkillTag key={item.id} item={item} />
        ))}
      </div>
    );
  }

  const has = (name: string) => items.some((item) => sameSkill(item.name, name));

  const add = (rawName: string) => {
    const name = canonicalSkill(rawName);
    if (name === '' || has(name)) return;
    const item: TechItem = { id: newId(), name, level: '' };
    onChange([...items, item]);
    setActiveId(item.id);
    setQuery('');
  };

  const remove = (item: TechItem) => {
    onChange(items.filter((x) => x.id !== item.id));
    if (activeId === item.id) setActiveId(null);
  };

  const setLevel = (item: TechItem, level: string) =>
    onChange(items.map((x) => (x.id === item.id ? { ...x, level } : x)));

  const active = filled.find((item) => item.id === activeId);
  // 검색 결과 전체를 페이지로 나눈다. 검색어가 바뀌면 첫 페이지로 돌아간다
  const matches = searchSkills(query);
  const pageCount = matches.length === 0 ? 1 : Math.ceil(matches.length / PAGE_SIZE);
  const current = Math.min(Math.max(page, 0), pageCount - 1);
  const suggestions = matches.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);
  const trimmed = query.trim();
  const canAddCustom = trimmed !== '' && !has(trimmed) && !matches.some((s) => sameSkill(s, trimmed));

  return (
    <div className="tech-editor">
      <span className="tech-editor__label">선택한 기술</span>
      {filled.length === 0 ? (
        <p className="hint">아래에서 태그를 고르거나 직접 입력해 추가하세요.</p>
      ) : (
        <div className="skill-tags">
          {filled.map((item) => (
            <SkillTag
              key={item.id}
              item={item}
              selected={item.id === activeId}
              onTap={() => setActiveId(activeId === item.id ? null : item.id)}
              onDelete={() => remove(item)}
            />
          ))}
        </div>
      )}

      {active !== undefined && <LevelPicker item={active} onChange={(level) => setLevel(active, level)} />}

      <span className="tech-editor__label tech-editor__label--add">기술 추가</span>
      <div className="tech-editor__search">
        <Icon name="search" size={20} />
        <input
          value={query}
          placeholder="기술 검색 또는 직접 입력 후 Enter"
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
          onKeyDown={(e) => {
            if (e.key !== 'Enter' || e.nativeEvent.isComposing) return;
            e.preventDefault();
            if (query.trim() === '') return;
            // 지금 보이는 페이지가 아니라 검색 결과 전체에서 가장 가까운 것을 고른다
            const match = matches[0] ?? query;
            add(sameSkill(match, query) ? match : query);
          }}
        />
        {query !== '' && (
          <button
            type="button"
            className="icon-btn"
            aria-label="검색어 지우기"
            onClick={() => {
              setQuery('');
              setPage(0);
            }}
          >
            <Icon name="close" size={18} />
          </button>
        )}
      </div>

      <div className="skill-tags skill-tags--pick">
        {canAddCustom && (
          <button type="button" className="skill-pick skill-pick--custom" onClick={() => add(trimmed)}>
            <Icon name="add" size={16} />
            &apos;{trimmed}&apos; 추가
          </button>
        )}
        {suggestions.map((name) => {
          const selected = has(name);
          return (
            <button
              key={name}
              type="button"
              className={`skill-pick${selected ? ' is-selected' : ''}`}
              aria-pressed={selected}
              onClick={() => {
                if (!selected) add(name);
                else {
                  const item = items.find((x) => sameSkill(x.name, name));
                  if (item !== undefined) remove(item);
                }
              }}
            >
              {name}
            </button>
          );
        })}
        {suggestions.length === 0 && !canAddCustom && <p className="hint">검색 결과가 없습니다.</p>}
      </div>

      {matches.length > PAGE_SIZE && (
        <div className="tech-editor__pager">
          <button type="button" className="btn btn--text btn--sm" disabled={current === 0} onClick={() => setPage(current - 1)}>
            <Icon name="chevron_left" size={18} />
            이전
          </button>
          <span>
            {current + 1} / {pageCount} 페이지 · 전체 {matches.length}개
          </span>
          <button
            type="button"
            className="btn btn--text btn--sm"
            disabled={current >= pageCount - 1}
            onClick={() => setPage(current + 1)}
          >
            다음
            <Icon name="chevron_right" size={18} />
          </button>
        </div>
      )}
    </div>
  );
}

/** 선택한 기술 태그. 숙련도가 있으면 「Python · 중급」처럼 같이 보여 준다 */
function SkillTag({
  item,
  selected = false,
  onTap,
  onDelete,
}: {
  item: TechItem;
  selected?: boolean;
  onTap?(): void;
  onDelete?(): void;
}) {
  const level = item.level.trim();
  const label = level === '' ? item.name.trim() : `${item.name.trim()} · ${level}`;
  if (onTap === undefined) return <span className="skill-tag">{label}</span>;
  return (
    <span className={`skill-tag skill-tag--input${selected ? ' is-selected' : ''}`}>
      <button type="button" className="skill-tag__main" title={level === '' ? '눌러서 숙련도 선택' : `숙련도: ${level}`} onClick={onTap}>
        {label}
      </button>
      <button type="button" className="skill-tag__delete" aria-label={`${item.name} 삭제`} onClick={onDelete}>
        <Icon name="cancel" size={16} />
      </button>
    </span>
  );
}

/** 숙련도 단계를 설명과 함께 가로로 늘어놓고 고른다. 같은 단계를 다시 누르면 지운다 */
function LevelPicker({ item, onChange }: { item: TechItem; onChange(level: string): void }) {
  const current = item.level.trim();
  const known = techSkillLevelOf(current);
  return (
    <div className="level-picker">
      <div className="level-picker__head">
        <strong>{item.name.trim()} 숙련도</strong>
        <span className="hint">(선택) 같은 단계를 다시 누르면 지워집니다</span>
      </div>
      {current !== '' && known === undefined && (
        <p className="level-picker__legacy">
          기존 값 &apos;{current}&apos;은(는) 단계 목록에 없습니다. 아래에서 다시 고르면 바뀝니다.
        </p>
      )}
      <div className="level-picker__tiles">
        {TECH_SKILL_LEVELS.map((level) => {
          const selected = known?.label === level.label;
          return (
            <button
              key={level.label}
              type="button"
              className={`level-tile${selected ? ' is-selected' : ''}`}
              aria-pressed={selected}
              onClick={() => onChange(selected ? '' : level.label)}
            >
              <strong>{level.label}</strong>
              <span>{level.description}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
