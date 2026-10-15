import { MaterialIcons } from '@expo/vector-icons';
import { useMemo, useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import type { ResumeContent } from '@web/domain/types';
import { TECH_SKILL_LEVELS, canonicalSkill, sameSkill, searchSkills, techSkillLevelOf } from '@web/features/resume/skills/skillCatalog';

import { useTheme } from '../theme/Theme';
import { T } from './kit';

type TechItem = ResumeContent['techStack'][number];

/**
 * 후보 칸 수 — 폰 · 태블릿 모두 한 페이지에 12개만 보여 주고 화살표로 넘긴다.
 * 글자 폭으로 줄 수를 어림하면 기기마다 줄이 늘어나 목록이 길어졌다. 칸 수를 고정한다.
 */
const PER_PAGE = 12;
const CHIP_GAP = 6;

function paginate<V>(list: V[], perPage: number): V[][] {
  const pages: V[][] = [];
  for (let i = 0; i < list.length; i += perPage) pages.push(list.slice(i, i + perPage));
  return pages.length ? pages : [[]];
}

/**
 * 기술 스택 편집 — 웹 `features/resume/skills/TechStackEditor.tsx` 와 같은 흐름.
 * 위: 고른 기술(「Python · 중급」). 누르면 숙련도 5단계(설명 포함)를 고르고, ✕ 로 지운다.
 * 아래: 「기술 목록에서 고르기」를 열면 후보가 나온다. 검색으로 거르고 정해진 칸 수씩 화살표로 넘긴다.
 *       후보에 없으면 직접 입력해 추가한다. 목록은 다시 눌러 접는다. 한 페이지 칸 수는 12개로 고정.
 */
export function TechStackEditor({ items, onChange, newId }: { items: TechItem[]; onChange: (next: TechItem[]) => void; newId: () => string }) {
  const { palette } = useTheme();
  const [query, setQuery] = useState('');
  const [activeId, setActiveId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  // 후보 목록은 길어서 접어 두고, 필요할 때 연다
  const [open, setOpen] = useState(false);

  const filled = items.filter((item) => item.name.trim() !== '');
  // 고른 기술도 12개씩 나눠 보여 준다
  const [selPage, setSelPage] = useState(0);
  const selPages = paginate(filled, PER_PAGE);
  const selCurrent = Math.min(selPage, selPages.length - 1);
  const has = (name: string) => items.some((item) => sameSkill(item.name, name));
  const matches = useMemo(() => searchSkills(query), [query]);
  const pages = useMemo(() => paginate(matches, PER_PAGE), [matches]);
  const current = Math.min(page, pages.length - 1);
  const trimmed = query.trim();
  const canAddCustom = trimmed !== '' && !has(trimmed) && !matches.some((s) => sameSkill(s, trimmed));
  const active = filled.find((item) => item.id === activeId);

  const add = (raw: string) => {
    const name = canonicalSkill(raw);
    if (name === '' || has(name)) return;
    const item: TechItem = { id: newId(), name, level: '' };
    onChange([...items, item]);
    setActiveId(item.id);
    setSelPage(Math.floor(items.filter((x) => x.name.trim() !== '').length / PER_PAGE));
    setQuery('');
    setPage(0);
  };
  const remove = (item: TechItem) => {
    onChange(items.filter((x) => x.id !== item.id));
    if (activeId === item.id) setActiveId(null);
  };
  const setLevel = (item: TechItem, level: string) => onChange(items.map((x) => (x.id === item.id ? { ...x, level } : x)));

  return (
    <View style={{ gap: 10 }}>
      <T variant="label" tone="secondary">선택한 기술</T>
      {filled.length === 0 ? (
        <T variant="caption" tone="hint">아래에서 태그를 고르거나 직접 입력해 추가하세요.</T>
      ) : (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {selPages[selCurrent].map((item) => {
            const selected = item.id === activeId;
            const level = item.level.trim();
            return (
              <View
                key={item.id}
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: selected ? palette.primary : palette.border,
                  backgroundColor: selected ? palette.primaryLight : palette.surface,
                }}
              >
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={level ? `${item.name} 숙련도 ${level}` : `${item.name} 숙련도 고르기`}
                  onPress={() => setActiveId(selected ? null : item.id)}
                  style={{ paddingLeft: 12, paddingRight: 4, paddingVertical: 7 }}
                >
                  <Text style={{ color: palette.text, fontSize: 14 }}>
                    {item.name.trim()}
                    {level ? <Text style={{ color: palette.primary, fontWeight: '600' }}>{` · ${level}`}</Text> : null}
                  </Text>
                </Pressable>
                <Pressable accessibilityRole="button" accessibilityLabel={`${item.name} 삭제`} hitSlop={6} onPress={() => remove(item)} style={{ paddingLeft: 2, paddingRight: 10, paddingVertical: 7 }}>
                  <MaterialIcons name="cancel" size={16} color={palette.textHint} />
                </Pressable>
              </View>
            );
          })}
        </View>
      )}

      <Pager current={selCurrent} count={selPages.length} total={filled.length} onChange={setSelPage} label="선택한 기술" />

      {active ? (
        <View style={{ gap: 8, padding: 12, borderRadius: 12, backgroundColor: palette.background, borderWidth: 1, borderColor: palette.border }}>
          <View style={{ gap: 2 }}>
            <T variant="label">{active.name.trim()} 숙련도</T>
            <T variant="caption" tone="hint">(선택) 같은 단계를 다시 누르면 지워집니다</T>
          </View>
          {active.level.trim() && !techSkillLevelOf(active.level) ? (
            <T variant="caption" tone="secondary">기존 값 &apos;{active.level.trim()}&apos;은(는) 단계 목록에 없습니다. 아래에서 다시 고르면 바뀝니다.</T>
          ) : null}
          {TECH_SKILL_LEVELS.map((level) => {
            const selected = techSkillLevelOf(active.level)?.label === level.label;
            return (
              <Pressable
                key={level.label}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                onPress={() => setLevel(active, selected ? '' : level.label)}
                style={({ pressed }) => ({
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 10,
                  padding: 10,
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: selected ? palette.primary : palette.border,
                  backgroundColor: selected ? palette.primaryLight : palette.surface,
                  opacity: pressed ? 0.7 : 1,
                })}
              >
                <Text style={{ width: 48, fontWeight: '700', color: selected ? palette.primary : palette.text }}>{level.label}</Text>
                <T variant="caption" tone="secondary" style={{ flex: 1 }}>{level.description}</T>
              </Pressable>
            );
          })}
        </View>
      ) : null}

      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen((v) => !v)}
        style={({ pressed }) => ({
          flexDirection: 'row',
          alignItems: 'center',
          gap: 8,
          marginTop: 4,
          paddingVertical: 10,
          paddingHorizontal: 12,
          borderRadius: 10,
          backgroundColor: palette.primaryLight,
          opacity: pressed ? 0.7 : 1,
        })}
      >
        <MaterialIcons name="add-circle-outline" size={18} color={palette.primary} />
        <Text style={{ flex: 1, color: palette.primary, fontWeight: '600' }}>기술 목록에서 고르기</Text>
        <Text style={{ color: palette.primary, fontSize: 13 }}>{open ? '닫기' : '열기'}</Text>
        <MaterialIcons name={open ? 'expand-less' : 'expand-more'} size={20} color={palette.primary} />
      </Pressable>

      {open ? (
      <View style={{ gap: 10 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: palette.border, borderRadius: 10, paddingHorizontal: 10, backgroundColor: palette.surface }}>
        <MaterialIcons name="search" size={20} color={palette.textHint} />
        <TextInput
          value={query}
          onChangeText={(text) => {
            setQuery(text);
            setPage(0);
          }}
          onSubmitEditing={() => {
            if (!trimmed) return;
            const match = matches[0] ?? trimmed;
            add(sameSkill(match, trimmed) ? match : trimmed);
          }}
          placeholder="기술 검색 또는 직접 입력"
          placeholderTextColor={palette.textHint}
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="done"
          style={{ flex: 1, paddingVertical: 9, fontSize: 15, color: palette.text }}
        />
        {query ? (
          <Pressable accessibilityRole="button" accessibilityLabel="검색어 지우기" hitSlop={8} onPress={() => { setQuery(''); setPage(0); }}>
            <MaterialIcons name="close" size={18} color={palette.textHint} />
          </Pressable>
        ) : null}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: CHIP_GAP }}>
        {canAddCustom ? (
          <Pressable
            accessibilityRole="button"
            onPress={() => add(trimmed)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderStyle: 'dashed', borderColor: palette.primary }}
          >
            <MaterialIcons name="add" size={16} color={palette.primary} />
            <Text style={{ color: palette.primary, fontSize: 13, fontWeight: '600' }}>&apos;{trimmed}&apos; 추가</Text>
          </Pressable>
        ) : null}
        {pages[current].map((name) => {
          const selected = has(name);
          return (
            <Pressable
              key={name}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              onPress={() => {
                if (!selected) add(name);
                else {
                  const item = items.find((x) => sameSkill(x.name, name));
                  if (item) remove(item);
                }
              }}
              style={{
                paddingHorizontal: 12,
                paddingVertical: 6,
                borderRadius: 999,
                borderWidth: 1,
                borderColor: selected ? palette.primary : palette.border,
                backgroundColor: selected ? palette.primary : palette.surface,
              }}
            >
              <Text style={{ fontSize: 13, color: selected ? '#fff' : palette.text, fontWeight: selected ? '600' : '400' }} numberOfLines={1}>
                {name}
              </Text>
            </Pressable>
          );
        })}
        {pages[current].length === 0 && !canAddCustom ? <T variant="caption" tone="hint">검색 결과가 없습니다.</T> : null}
      </View>

      <Pager current={current} count={pages.length} total={matches.length} onChange={setPage} label="후보" />
      </View>
      ) : null}
    </View>
  );
}

/** 「‹ 이전 · 1 / n · 전체 n개 · 다음 ›」 — 한 페이지뿐이면 숨긴다 */
function Pager({ current, count, total, onChange, label }: { current: number; count: number; total: number; onChange: (page: number) => void; label: string }) {
  const { palette } = useTheme();
  if (count <= 1) return null;
  const button = (dir: -1 | 1) => {
    const disabled = dir < 0 ? current === 0 : current >= count - 1;
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${dir < 0 ? '이전' : '다음'} ${label}`}
        disabled={disabled}
        hitSlop={8}
        onPress={() => onChange(current + dir)}
        style={{ flexDirection: 'row', alignItems: 'center', padding: 6, opacity: disabled ? 0.3 : 1 }}
      >
        {dir < 0 ? <MaterialIcons name="chevron-left" size={22} color={palette.primary} /> : null}
        <Text style={{ color: palette.primary, fontWeight: '600' }}>{dir < 0 ? '이전' : '다음'}</Text>
        {dir > 0 ? <MaterialIcons name="chevron-right" size={22} color={palette.primary} /> : null}
      </Pressable>
    );
  };
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
      {button(-1)}
      <T variant="caption" tone="secondary">
        {current + 1} / {count} · 전체 {total}개
      </T>
      {button(1)}
    </View>
  );
}
