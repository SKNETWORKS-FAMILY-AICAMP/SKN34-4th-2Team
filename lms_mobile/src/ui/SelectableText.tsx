import { Platform, StyleSheet, Text, TextInput, View, type StyleProp, type TextStyle } from 'react-native';
import type { ReactNode } from 'react';

import { useTheme } from '../theme/Theme';
import type { Palette } from '../theme/tokens';
import { CodeBlock, MarkdownView, NATIVE_SELECT } from './MarkdownView';

/**
 * 말풍선 안에서 글자를 드래그로 골라 복사하기.
 * 안드로이드는 Text 의 selectable 이 손잡이로 범위를 고르게 해 준다.
 * iOS 의 Text selectable 은 길게 누르면 글 전체 「복사」만 떠서 일부를 고를 수 없다 — 읽기 전용 TextInput 은
 * iOS 에서도 손잡이로 고를 수 있어서, iOS 는 글을 입력칸에 그리고 꾸밈(굵게 · 제목 · 코드)은 안쪽 Text 스타일로 낸다.
 */
const readOnly = { editable: false, multiline: true, scrollEnabled: false, caretHidden: true } as const;

/** 꾸밈 없는 글 — 내가 보낸 말풍선 · 관리자 비서 */
export function SelectableText({ text, style }: { text: string; style?: StyleProp<TextStyle> }) {
  if (NATIVE_SELECT) {
    return (
      <Text selectable style={style}>
        {text}
      </Text>
    );
  }
  return <TextInput {...readOnly} value={text} style={[style, styles.input]} />;
}

const SIZE = 15;
const LINE = 24;
const MONO = Platform.select({ ios: 'Menlo', default: 'monospace' });

/** **굵게** · `코드` · [링크](주소) · *기울임* — 한 줄 안의 꾸밈 */
function inline(line: string, key: string, palette: Palette): ReactNode[] {
  const out: ReactNode[] = [];
  const pattern = /\*\*(.+?)\*\*|__(.+?)__|`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\)|\*([^*\s][^*]*)\*/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let n = 0;
  while ((match = pattern.exec(line)) !== null) {
    if (match.index > last) out.push(line.slice(last, match.index));
    const k = `${key}-${n++}`;
    const [, bold, bold2, code, label, , em] = match;
    if (bold !== undefined || bold2 !== undefined) out.push(<Text key={k} style={{ fontWeight: '700' }}>{bold ?? bold2}</Text>);
    else if (code !== undefined)
      out.push(
        <Text key={k} style={{ fontFamily: MONO, fontSize: SIZE - 2, color: palette.primaryDark, backgroundColor: palette.surfaceVariant }}>
          {code}
        </Text>,
      );
    else if (label !== undefined) out.push(<Text key={k} style={{ color: palette.primary, textDecorationLine: 'underline' }}>{label}</Text>);
    else if (em !== undefined) out.push(<Text key={k} style={{ fontStyle: 'italic' }}>{em}</Text>);
    last = match.index + match[0].length;
  }
  if (last < line.length) out.push(line.slice(last));
  return out;
}

/** 여러 줄 글 → 입력칸 하나에 넣을 꾸민 글자들. 문단을 넘어 한 번에 고를 수 있다 */
function richLines(lines: string[], key: string, palette: Palette): ReactNode[] {
  const out: ReactNode[] = [];
  lines.forEach((raw, index) => {
    const k = `${key}-${index}`;
    const nl = index < lines.length - 1 ? '\n' : '';
    const heading = /^(#{1,6})\s+(.*)$/.exec(raw);
    const bullet = /^(\s*)[-*+]\s+(.*)$/.exec(raw);
    const ordered = /^(\s*)(\d+[.)])\s+(.*)$/.exec(raw);
    const quote = /^>\s?(.*)$/.exec(raw);
    if (heading) {
      const level = heading[1].length;
      out.push(
        <Text key={k} style={{ fontWeight: '800', fontSize: level <= 2 ? SIZE + 2 : SIZE + 1, color: level === 3 ? palette.primary : palette.text }}>
          {inline(heading[2], k, palette)}
          {nl}
        </Text>,
      );
    } else if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(raw)) {
      out.push(<Text key={k} style={{ color: palette.border }}>{'────────'}{nl}</Text>);
    } else if (bullet) {
      out.push(
        <Text key={k}>
          {bullet[1]}
          <Text style={{ color: palette.primary, fontWeight: '800' }}>{'•  '}</Text>
          {inline(bullet[2], k, palette)}
          {nl}
        </Text>,
      );
    } else if (ordered) {
      out.push(
        <Text key={k}>
          {ordered[1]}
          <Text style={{ color: palette.primary, fontWeight: '700' }}>{`${ordered[2]} `}</Text>
          {inline(ordered[3], k, palette)}
          {nl}
        </Text>,
      );
    } else if (quote) {
      out.push(
        <Text key={k} style={{ color: palette.textSecondary }}>
          {inline(quote[1], k, palette)}
          {nl}
        </Text>,
      );
    } else {
      out.push(
        <Text key={k}>
          {inline(raw, k, palette)}
          {nl}
        </Text>,
      );
    }
  });
  return out;
}

type Block = { kind: 'text'; lines: string[] } | { kind: 'code'; code: string; lang?: string } | { kind: 'table'; source: string };

/** 코드 블록 · 표는 따로 그린다 — 입력칸 안에는 가로로 미는 칸을 넣을 수 없다 */
function blocksOf(markdown: string): Block[] {
  const lines = markdown.split('\n');
  const blocks: Block[] = [];
  let text: string[] = [];
  const flush = () => {
    while (text.length && !text[text.length - 1].trim()) text.pop();
    while (text.length && !text[0].trim()) text.shift();
    if (text.length) blocks.push({ kind: 'text', lines: text.map((line) => line.replace(/\s+$/, '')).filter((line, i, all) => line || all[i - 1]) });
    text = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = /^\s*```\s*(\S*)/.exec(line);
    if (fence) {
      flush();
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) body.push(lines[i++]);
      blocks.push({ kind: 'code', code: body.join('\n'), lang: fence[1] || undefined });
      continue;
    }
    if (/^\s*\|/.test(line)) {
      flush();
      const rows: string[] = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
      i--;
      blocks.push({ kind: 'table', source: rows.join('\n') });
      continue;
    }
    text.push(line);
  }
  flush();
  return blocks;
}

/** 챗봇 답변(마크다운) — 안드로이드는 MarkdownView 그대로, iOS 는 입력칸에 꾸민 글자로 */
export function ChatMarkdown({ text }: { text: string }) {
  const { palette } = useTheme();
  if (NATIVE_SELECT) return <MarkdownView text={text} size="compact" />;
  const blocks = blocksOf(text);
  return (
    <View style={{ gap: 6 }}>
      {blocks.map((block, index) =>
        block.kind === 'code' ? (
          <CodeBlock key={index} code={block.code} lang={block.lang} palette={palette} />
        ) : block.kind === 'table' ? (
          <MarkdownView key={index} text={block.source} size="compact" />
        ) : (
          <TextInput key={index} {...readOnly} style={[styles.input, { color: palette.text, fontSize: SIZE, lineHeight: LINE }]}>
            {richLines(block.lines, String(index), palette)}
          </TextInput>
        ),
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  // 입력칸 기본 안쪽 여백을 없애 Text 와 같은 자리에 그린다
  input: { padding: 0, paddingTop: 0, paddingBottom: 0, margin: 0, textAlignVertical: 'top' },
});
