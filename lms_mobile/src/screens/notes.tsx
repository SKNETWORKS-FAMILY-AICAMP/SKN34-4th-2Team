import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { isReadyNote, noteDate, noteLabel } from '@web/features/study/noteScope';
import type { StudyNote } from '@web/domain/types';
import { useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';

import { refreshBootstrap } from '../data/query';
import { useNotes, useSources } from '../data/study';
import { useTheme } from '../theme/Theme';
import { MarkdownView } from '../ui/MarkdownView';
import { Badge, Callout, Card, Chip, EmptyState, ListGroup, ListItem, Screen, Segmented, T, type IconName } from '../ui/kit';

const STATUS: Record<string, { label: string; tone: 'warning' | 'error' | 'info' }> = {
  generating: { label: '정리 중', tone: 'info' },
  too_broad: { label: '범위가 넓음', tone: 'warning' },
  failed: { label: '정리 실패', tone: 'error' },
};

/** 노트 소제목(study_notes/pipeline.py NOTE_HEADS) — 칩에 쓸 짧은 이름과 아이콘 */
const HEADS: { match: string; short: string; icon: IconName }[] = [
  { match: '꼭 알아야', short: '핵심', icon: 'lightbulb-outline' },
  { match: '개념별', short: '개념', icon: 'menu-book' },
  { match: '핵심 한 문장', short: '핵심', icon: 'lightbulb-outline' },
  { match: '수업 흐름', short: '흐름', icon: 'timeline' },
  { match: '파일별', short: '파일별', icon: 'description' },
  { match: '핵심 코드', short: '코드', icon: 'code' },
  { match: '이전 학습', short: '연결', icon: 'link' },
  { match: '체크리스트', short: '체크리스트', icon: 'checklist' },
  { match: '실습', short: '실습', icon: 'build' },
  { match: '회고', short: '회고', icon: 'auto-awesome' },
  { match: '실수', short: '주의', icon: 'warning-amber' },
  { match: '주의', short: '주의', icon: 'warning-amber' },
  { match: '문제', short: '확인 문제', icon: 'quiz' },
  { match: '요약', short: '요약', icon: 'summarize' },
  { match: '정리', short: '정리', icon: 'menu-book' },
];
/** 처음 펼쳐 둘 소제목 — 없으면 첫 소제목 */
const OPEN_FIRST = new Set(['핵심', '흐름']);

function defaultOpen(sections: Section[]): Set<number> {
  const picked = sections.flatMap((section, index) => (OPEN_FIRST.has(section.short) ? [index] : []));
  return new Set(picked.length > 0 ? picked : [0]);
}

interface Section {
  title: string;
  short: string;
  icon: IconName;
  body: string;
}

/** `## 소제목` 단위로 자른다 — 첫 소제목 앞 글은 머리말로 둔다 */
function splitSections(markdown: string): { intro: string; sections: Section[] } {
  const lines = markdown.split('\n');
  const sections: Section[] = [];
  const intro: string[] = [];
  let fenced = false;
  for (const line of lines) {
    if (/^\s*(```|~~~)/.test(line)) fenced = !fenced;
    const head = !fenced ? /^##\s+(.+?)\s*#*\s*$/.exec(line) : null;
    if (head) {
      const title = head[1].replace(/^[\d.)\s]+/, '').trim();
      const known = HEADS.find((h) => title.includes(h.match));
      sections.push({ title, short: known?.short ?? (title.length > 8 ? `${title.slice(0, 8)}…` : title), icon: known?.icon ?? 'notes', body: '' });
    } else if (sections.length === 0) {
      intro.push(line);
    } else {
      sections[sections.length - 1].body += `${line}\n`;
    }
  }
  return { intro: intro.join('\n').trim(), sections: sections.map((s) => ({ ...s, body: s.body.trim() })) };
}

function dateTitle(key: string): string {
  const date = new Date(`${key}T00:00:00`);
  if (Number.isNaN(date.getTime())) return key;
  const weekday = date.toLocaleDateString('ko-KR', { weekday: 'short' });
  return `${date.getMonth() + 1}월 ${date.getDate()}일 (${weekday})`;
}

function titleOf(note: StudyNote): string {
  const date = noteDate(note);
  return date ? `${dateTitle(date)} 수업` : noteLabel(note);
}

function sortKey(note: StudyNote): number {
  const date = noteDate(note);
  if (date) return new Date(`${date}T00:00:00`).getTime();
  return note.createdAt?.getTime() ?? 0;
}

export function NotesPage() {
  const notes = useNotes();
  const sources = useSources();
  const { palette } = useTheme();
  const sorted = useMemo(() => [...notes].sort((a, b) => sortKey(b) - sortKey(a)), [notes]);
  return (
    <Screen title="공부 노트" onRefresh={refreshBootstrap} empty={notes.length === 0} emptyText="아직 만든 노트가 없어요.">
      <T variant="caption" tone="secondary">수업 날짜별로 정리된 노트예요. 최근 수업이 위에 있어요.</T>
      <ListGroup>
        {sorted.map((note) => {
          const status = STATUS[note.status];
          const source = sources.find((row) => row.id === note.sourceId)?.title;
          return (
            <ListItem
              key={note.id}
              title={titleOf(note)}
              subtitle={source}
              left={
                <View style={{ width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.primaryLight }}>
                  <MaterialIcons name={noteDate(note) ? 'event-note' : 'folder-open'} size={20} color={palette.primary} />
                </View>
              }
              right={status ? <Badge label={status.label} tone={status.tone} /> : undefined}
              onPress={() => router.push(`/(student)/notes/${note.id}` as never)}
            />
          );
        })}
      </ListGroup>
    </Screen>
  );
}

type Tab = 'report' | 'review' | 'files';

export function NotePage({ id }: { id: string }) {
  const note = useNotes().find((row) => row.id === id);
  const source = useSources().find((row) => row.id === note?.sourceId)?.title;
  const { palette } = useTheme();
  const scrollRef = useRef<ScrollView>(null);
  const [tab, setTab] = useState<Tab>('report');
  const parsed = useMemo(() => splitSections(note?.reportMarkdown ?? ''), [note?.reportMarkdown]);
  const [open, setOpen] = useState<Set<number>>(() => defaultOpen(parsed.sections));
  const offsets = useRef<Record<number, number>>({});

  if (!note) return <Screen title="노트" empty emptyText="노트를 찾지 못했어요." />;

  const hasReview = note.reviewMarkdown.trim() !== '';
  const tabs: { key: Tab; label: string }[] = [
    { key: 'report', label: '요약' },
    ...(hasReview ? [{ key: 'review' as Tab, label: '복습' }] : []),
    { key: 'files', label: `파일 ${note.files.length}` },
  ];
  const sectioned = parsed.sections.length >= 2;
  const allOpen = open.size >= parsed.sections.length;

  const toggle = (index: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });

  const jump = (index: number) => {
    setOpen((prev) => new Set(prev).add(index));
    const y = offsets.current[index];
    if (y !== undefined) scrollRef.current?.scrollTo({ y: Math.max(0, y - 8), animated: true });
  };

  return (
    <Screen title={titleOf(note)} onRefresh={refreshBootstrap} scrollRef={scrollRef}>
      {source ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <MaterialIcons name="folder-open" size={16} color={palette.textHint} />
          <T variant="caption" tone="secondary" numberOfLines={1} style={{ flex: 1 }}>{source}</T>
        </View>
      ) : null}

      <NoteStatus note={note} />

      {isReadyNote(note) ? (
        <>
          <Segmented options={tabs} value={tab} onChange={setTab} />

          {tab === 'report' && sectioned ? (
            <>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 2 }}>
                {parsed.sections.map((section, index) => (
                  <Chip key={index} label={section.short} selected={open.has(index)} onPress={() => jump(index)} />
                ))}
              </ScrollView>
              <Pressable
                onPress={() => setOpen(allOpen ? new Set() : new Set(parsed.sections.map((_, i) => i)))}
                hitSlop={8}
                style={{ alignSelf: 'flex-end', flexDirection: 'row', alignItems: 'center', gap: 4 }}
              >
                <MaterialIcons name={allOpen ? 'unfold-less' : 'unfold-more'} size={18} color={palette.textSecondary} />
                <T variant="caption" tone="secondary">{allOpen ? '모두 접기' : '모두 펼치기'}</T>
              </Pressable>
              {parsed.intro ? (
                <Card>
                  <MarkdownView text={parsed.intro} />
                </Card>
              ) : null}
              {parsed.sections.map((section, index) => (
                <View
                  key={index}
                  onLayout={(event) => {
                    offsets.current[index] = event.nativeEvent.layout.y;
                  }}
                >
                  <SectionCard section={section} open={open.has(index)} onToggle={() => toggle(index)} />
                </View>
              ))}
            </>
          ) : null}

          {tab === 'report' && !sectioned ? (
            <Card>
              <MarkdownView text={note.reportMarkdown || '내용이 없어요.'} />
            </Card>
          ) : null}

          {tab === 'review' ? (
            <Card>
              <MarkdownView text={note.reviewMarkdown} />
            </Card>
          ) : null}

          {tab === 'files' ? (
            note.files.length === 0 ? (
              <Card><EmptyState icon="description" text="이 노트가 정리한 파일 기록이 없어요." /></Card>
            ) : (
              <ListGroup>
                {note.files.map((file) => {
                  const parts = file.path.split('/');
                  const name = parts.pop() ?? file.path;
                  return (
                    <ListItem
                      key={file.path}
                      title={name}
                      subtitle={[parts.join('/'), file.commit ? file.commit.slice(0, 7) : ''].filter(Boolean).join(' · ')}
                      left={<MaterialIcons name="insert-drive-file" size={20} color={palette.textHint} />}
                    />
                  );
                })}
              </ListGroup>
            )
          ) : null}
        </>
      ) : null}
    </Screen>
  );
}

function NoteStatus({ note }: { note: StudyNote }) {
  if (note.status === 'generating') {
    return (
      <Callout tone="info">
        <T>{note.message || '노트를 정리하고 있어요.'}</T>
        <T variant="caption" tone="secondary" style={{ marginTop: 4 }}>잠시 뒤 화면을 아래로 당겨 새로고침해 주세요.</T>
      </Callout>
    );
  }
  if (note.status === 'too_broad') {
    return (
      <Callout tone="warning">
        <T>{note.message || '이 범위에는 파일이 너무 많아요.'}</T>
        <T variant="caption" tone="secondary" style={{ marginTop: 4 }}>PC 웹 공부방에서 파일을 골라 다시 정리할 수 있어요.</T>
      </Callout>
    );
  }
  if (note.status === 'failed') {
    return (
      <Callout tone="error">
        <T>{note.errorMessage || '노트를 정리하지 못했어요.'}</T>
      </Callout>
    );
  }
  return null;
}

function SectionCard({ section, open, onToggle }: { section: Section; open: boolean; onToggle: () => void }) {
  const { palette } = useTheme();
  return (
    <Card style={{ padding: 0, gap: 0, overflow: 'hidden' }}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={onToggle}
        style={({ pressed }) => ({
          flexDirection: 'row',
          alignItems: 'center',
          gap: 10,
          paddingHorizontal: 16,
          paddingVertical: 14,
          backgroundColor: pressed ? palette.surfaceVariant : 'transparent',
        })}
      >
        <View style={{ width: 32, height: 32, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.primaryLight }}>
          <MaterialIcons name={section.icon} size={18} color={palette.primary} />
        </View>
        <T variant="subtitle" style={{ flex: 1 }} numberOfLines={2}>{section.title}</T>
        <MaterialIcons name={open ? 'expand-less' : 'expand-more'} size={24} color={palette.textHint} />
      </Pressable>
      {open ? (
        <View style={{ paddingHorizontal: 16, paddingBottom: 8, borderTopWidth: 1, borderTopColor: palette.divider, paddingTop: 12 }}>
          {section.body ? <MarkdownView text={section.body} /> : <T tone="hint">내용이 없어요.</T>}
        </View>
      ) : null}
    </Card>
  );
}
