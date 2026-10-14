import { MaterialIcons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { useMemo, useState, type ReactNode } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import Markdown, { type ASTNode, type RenderRules } from 'react-native-markdown-display';

import { useTheme } from '../theme/Theme';
import type { Palette } from '../theme/tokens';

const MONO = Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' });
const CELL_MIN = 112;

function trimEnd(content: string): string {
  return content.endsWith('\n') ? content.slice(0, -1) : content;
}

function CodeBlock({ code, lang, palette }: { code: string; lang?: string; palette: Palette }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void Clipboard.setStringAsync(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <View style={[styles.code, { backgroundColor: palette.surfaceVariant, borderColor: palette.border }]}>
      <View style={[styles.codeHead, { borderBottomColor: palette.border }]}>
        <Text style={{ flex: 1, fontSize: 12, fontWeight: '600', color: palette.textSecondary }} numberOfLines={1}>
          {lang || '코드'}
        </Text>
        <Pressable accessibilityRole="button" accessibilityLabel="코드 복사" onPress={copy} hitSlop={8} style={styles.copy}>
          <MaterialIcons name={copied ? 'check' : 'content-copy'} size={15} color={copied ? palette.success : palette.textSecondary} />
          <Text style={{ fontSize: 12, fontWeight: '600', color: copied ? palette.success : palette.textSecondary }}>{copied ? '복사됨' : '복사'}</Text>
        </Pressable>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={{ padding: 12 }}>
        <Text selectable style={{ fontFamily: MONO, fontSize: 13, lineHeight: 20, color: palette.text }}>
          {code}
        </Text>
      </ScrollView>
    </View>
  );
}

function rulesFor(palette: Palette): RenderRules {
  const code = (node: ASTNode) => (
    <CodeBlock key={node.key} code={trimEnd(node.content)} lang={(node as ASTNode & { sourceInfo?: string }).sourceInfo?.trim().split(/\s+/)[0]} palette={palette} />
  );
  return {
    fence: code,
    code_block: code,
    table: (node, children: ReactNode[]) => (
      <ScrollView key={node.key} horizontal showsHorizontalScrollIndicator style={styles.tableScroll}>
        <View style={[styles.table, { borderColor: palette.border }]}>{children}</View>
      </ScrollView>
    ),
    th: (node, children: ReactNode[]) => (
      <View key={node.key} style={[styles.cell, { borderColor: palette.border, backgroundColor: palette.surfaceVariant }]}>
        {children}
      </View>
    ),
    td: (node, children: ReactNode[]) => (
      <View key={node.key} style={[styles.cell, { borderColor: palette.border }]}>
        {children}
      </View>
    ),
  };
}

function stylesFor(palette: Palette, size: 'normal' | 'compact') {
  const base = size === 'compact' ? 15 : 16;
  return StyleSheet.create({
    body: { color: palette.text, fontSize: base, lineHeight: Math.round(base * 1.6) },
    paragraph: { marginTop: 0, marginBottom: 10 },
    // 줄 높이를 글자보다 넉넉히 — 본문 줄 높이를 물려받으면 큰 글자 윗부분이 잘린다
    heading1: { color: palette.text, fontSize: 20, fontWeight: '800', lineHeight: 30, marginTop: 14, marginBottom: 8 },
    heading2: { color: palette.text, fontSize: 18, fontWeight: '800', lineHeight: 28, marginTop: 12, marginBottom: 8 },
    heading3: {
      color: palette.primary,
      fontSize: 16,
      fontWeight: '700',
      lineHeight: 25,
      marginTop: 14,
      marginBottom: 6,
      paddingTop: 12,
      borderTopWidth: 1,
      borderTopColor: palette.divider,
    },
    heading4: { color: palette.text, fontSize: 15, fontWeight: '700', lineHeight: 24, marginTop: 8, marginBottom: 4 },
    heading5: { color: palette.text, fontSize: 15, fontWeight: '700', lineHeight: 24 },
    heading6: { color: palette.textSecondary, fontSize: 14, fontWeight: '700', lineHeight: 22 },
    // 노트의 「뜻:」「언제 쓰나:」 같은 굵은 앞머리를 눈에 띄게 — 공지 · 챗봇(compact)은 본문색 그대로
    strong: { fontWeight: '700', color: size === 'normal' ? palette.primary : palette.text },
    em: { fontStyle: 'italic' },
    link: { color: palette.primary, textDecorationLine: 'underline' },
    bullet_list: { marginBottom: 10 },
    ordered_list: { marginBottom: 10 },
    list_item: { marginBottom: 4 },
    bullet_list_icon: { color: palette.primary, fontWeight: '800', marginLeft: 2, marginRight: 8 },
    ordered_list_icon: { color: palette.primary, fontWeight: '700', marginRight: 6 },
    bullet_list_content: { flex: 1 },
    ordered_list_content: { flex: 1 },
    code_inline: {
      fontFamily: MONO,
      fontSize: base - 2,
      color: palette.primaryDark,
      backgroundColor: palette.surfaceVariant,
      borderRadius: 4,
      paddingHorizontal: 4,
    },
    blockquote: {
      backgroundColor: palette.surfaceVariant,
      borderLeftColor: palette.primary,
      borderLeftWidth: 3,
      borderRadius: 6,
      paddingHorizontal: 12,
      paddingVertical: 6,
      marginVertical: 6,
      marginLeft: 0,
    },
    hr: { backgroundColor: palette.border, height: StyleSheet.hairlineWidth, marginVertical: 12 },
    tr: { flexDirection: 'row' },
    thead: { fontWeight: '700' },
    text: {},
  });
}

/** 노트 · 공지 · 챗봇 답변의 마크다운 — 테마 색, 가로로 미는 코드 블록과 표 */
export function MarkdownView({ text, size = 'normal' }: { text: string; size?: 'normal' | 'compact' }) {
  const { palette } = useTheme();
  const rules = useMemo(() => rulesFor(palette), [palette]);
  const style = useMemo(() => stylesFor(palette, size), [palette, size]);
  return (
    <Markdown style={style} rules={rules}>
      {text}
    </Markdown>
  );
}

const styles = StyleSheet.create({
  code: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 10, marginVertical: 8, overflow: 'hidden' },
  codeHead: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  copy: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  tableScroll: { marginVertical: 8 },
  table: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 8, overflow: 'hidden' },
  cell: { width: CELL_MIN * 1.4, minWidth: CELL_MIN, padding: 8, borderWidth: StyleSheet.hairlineWidth },
});
