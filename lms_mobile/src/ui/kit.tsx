import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { Children, Fragment, isValidElement, useRef, useState, type ComponentProps, type ReactNode, type RefObject } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { elevation, hit, radius, typography, type TypeVariant } from '../theme/tokens';
import { useTheme } from '../theme/Theme';
import type { Palette } from '../theme/tokens';

export type IconName = ComponentProps<typeof MaterialIcons>['name'];
export type Tone = 'primary' | 'success' | 'warning' | 'error' | 'info' | 'neutral';

function toneColor(palette: Palette, tone: Tone | string): string {
  switch (tone) {
    case 'primary':
      return palette.primary;
    case 'success':
      return palette.success;
    case 'warning':
      return palette.warning;
    case 'error':
      return palette.error;
    case 'info':
      return palette.info;
    case 'neutral':
      return palette.textSecondary;
    default:
      return tone;
  }
}

/** `#rrggbb` 에 투명도를 붙인 옅은 배경색 */
function soft(color: string, alpha = 0.12): string {
  if (!/^#[0-9a-f]{6}$/i.test(color)) return color;
  return `${color}${Math.round(alpha * 255).toString(16).padStart(2, '0')}`;
}

export function T({
  children,
  variant = 'body',
  tone = 'default',
  style,
  numberOfLines,
  fit,
  onPress,
}: {
  children?: ReactNode;
  variant?: TypeVariant;
  tone?: 'default' | 'secondary' | 'hint' | Tone;
  style?: StyleProp<TextStyle>;
  numberOfLines?: number;
  /** 넘치면 말줄임 대신 글자를 줄인다 — numberOfLines 와 함께 쓴다 */
  fit?: boolean;
  onPress?: () => void;
}) {
  const { palette } = useTheme();
  const color =
    tone === 'default' ? palette.text : tone === 'secondary' ? palette.textSecondary : tone === 'hint' ? palette.textHint : toneColor(palette, tone);
  return (
    <Text
      style={[typography[variant], { color }, style]}
      numberOfLines={numberOfLines}
      adjustsFontSizeToFit={fit}
      minimumFontScale={fit ? 0.75 : undefined}
      onPress={onPress}
      suppressHighlighting={!onPress}
      lineBreakStrategyIOS="hangul-word"
    >
      {children}
    </Text>
  );
}

/** 딥링크로 바로 열린 화면은 돌아갈 곳이 없다 — 루트로 보내면 Gate 가 역할별 홈으로 옮긴다 */
export function goBack() {
  if (router.canGoBack()) router.back();
  else router.replace('/');
}

export function Screen({
  title,
  loading,
  error,
  empty,
  emptyText = '표시할 내용이 없습니다.',
  refreshing,
  onRefresh,
  children,
  footer,
  back = true,
  left,
  right,
  stickToBottom,
  scrollRef: externalScrollRef,
}: {
  title: string;
  /** 화면 안 특정 위치로 옮겨야 할 때 — 본문 ScrollView 를 넘겨받는다 */
  scrollRef?: RefObject<ScrollView | null>;
  /** 채팅처럼 내용이 늘면 맨 아래를 따라간다 */
  stickToBottom?: boolean;
  loading?: boolean;
  error?: string | null;
  empty?: boolean;
  emptyText?: string;
  refreshing?: boolean;
  /** Promise 를 돌려주면 끝날 때까지 새로고침 스피너를 보인다 */
  onRefresh?: () => void | Promise<unknown>;
  children?: ReactNode;
  footer?: ReactNode;
  back?: boolean;
  left?: ReactNode;
  right?: ReactNode;
}) {
  const { palette } = useTheme();
  const ownScrollRef = useRef<ScrollView>(null);
  const scrollRef = externalScrollRef ?? ownScrollRef;
  const [pulling, setPulling] = useState(false);
  const pull = onRefresh
    ? () => {
        const pending = onRefresh();
        if (!pending) return;
        setPulling(true);
        void pending.catch(() => undefined).finally(() => setPulling(false));
      }
    : undefined;
  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: palette.background }]} edges={['top', 'left', 'right']}>
      {back ? (
        <View style={[styles.bar, { borderBottomColor: palette.border, backgroundColor: palette.surface }]}>
          <Pressable accessibilityLabel="뒤로" onPress={goBack} style={styles.hit}>
            <MaterialIcons name="arrow-back" size={24} color={palette.text} />
          </Pressable>
          <Text style={[styles.title, { color: palette.text }]} numberOfLines={2} lineBreakStrategyIOS="hangul-word">
            {title}
          </Text>
          <View style={styles.hit}>{right}</View>
        </View>
      ) : (
        <View style={styles.largeBar}>
          {left}
          <T variant="hero" style={styles.fill} numberOfLines={1}>
            {title}
          </T>
          {right}
        </View>
      )}
      <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        {loading ? (
          <View style={styles.center}>
            <ActivityIndicator color={palette.primary} />
            <T tone="secondary">불러오는 중…</T>
          </View>
        ) : error ? (
          <View style={styles.center}>
            <MaterialIcons name="error-outline" size={36} color={palette.error} />
            <T tone="error" style={{ textAlign: 'center' }}>{error}</T>
            {onRefresh ? <Btn label="다시 시도" onPress={onRefresh} /> : null}
          </View>
        ) : (
          <ScrollView
            ref={scrollRef}
            onContentSizeChange={stickToBottom ? () => scrollRef.current?.scrollToEnd({ animated: true }) : undefined}
            contentContainerStyle={styles.body}
            keyboardShouldPersistTaps="handled"
            refreshControl={
              pull ? (
                <RefreshControl refreshing={Boolean(refreshing) || pulling} onRefresh={pull} tintColor={palette.primary} colors={[palette.primary]} />
              ) : undefined
            }
          >
            {empty ? <EmptyState text={emptyText} /> : children}
          </ScrollView>
        )}
        {footer}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

export function Card({
  children,
  onPress,
  style,
}: {
  children: ReactNode;
  onPress?: () => void;
  style?: StyleProp<ViewStyle>;
}) {
  const { palette } = useTheme();
  const box = [styles.card, elevation, { backgroundColor: palette.surface, borderColor: palette.border }, style];
  if (!onPress) return <View style={box}>{children}</View>;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [box, pressed && { transform: [{ scale: 0.985 }], opacity: 0.9 }]}
    >
      {children}
    </Pressable>
  );
}

export function Btn({
  label,
  onPress,
  tone = 'primary',
  disabled,
  icon,
}: {
  label: string;
  onPress: () => void;
  tone?: 'primary' | 'ghost' | 'danger' | 'soft';
  disabled?: boolean;
  icon?: IconName;
}) {
  const { palette } = useTheme();
  const bg =
    tone === 'primary' ? palette.primary : tone === 'danger' ? palette.error : tone === 'soft' ? palette.primaryLight : 'transparent';
  const fg = tone === 'ghost' || tone === 'soft' ? palette.primary : '#fff';
  const border = tone === 'ghost' ? palette.border : bg;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.btn,
        { backgroundColor: bg, borderColor: border, opacity: disabled ? 0.45 : pressed ? 0.85 : 1 },
      ]}
    >
      {icon ? <MaterialIcons name={icon} size={18} color={fg} /> : null}
      <Text
        style={[typography.subtitle, { color: fg, fontSize: 15, flexShrink: 1, textAlign: 'center' }]}
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.75}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export function Field({
  label,
  value,
  onChangeText,
  placeholder,
  secure,
  multiline,
  keyboard,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
  secure?: boolean;
  multiline?: boolean;
  keyboard?: 'default' | 'email-address' | 'numeric' | 'url';
}) {
  const { palette } = useTheme();
  return (
    <View style={{ gap: 6 }}>
      <T variant="label" tone="secondary">{label}</T>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={palette.textHint}
        secureTextEntry={secure}
        multiline={multiline}
        keyboardType={keyboard}
        autoCapitalize="none"
        textAlignVertical={multiline ? 'top' : 'center'}
        style={[
          styles.input,
          {
            color: palette.text,
            borderColor: palette.border,
            backgroundColor: palette.surface,
            minHeight: multiline ? 96 : hit,
          },
        ]}
      />
    </View>
  );
}

export function Muted({ children }: { children: ReactNode }) {
  return <T variant="caption" tone="secondary">{children}</T>;
}

export function Row({
  title,
  subtitle,
  onPress,
  icon,
  right,
}: {
  title: string;
  subtitle?: string;
  onPress?: () => void;
  icon?: IconName;
  right?: ReactNode;
}) {
  const { palette } = useTheme();
  return (
    <Card onPress={onPress}>
      <View style={styles.rowLine}>
        {icon ? (
          <View style={[styles.iconBox, { backgroundColor: palette.primaryLight }]}>
            <MaterialIcons name={icon} size={20} color={palette.primary} />
          </View>
        ) : null}
        <View style={styles.fillGap}>
          <T variant="subtitle" numberOfLines={2}>{title}</T>
          {subtitle ? <T variant="caption" tone="secondary" numberOfLines={3}>{subtitle}</T> : null}
        </View>
        {right}
        {onPress ? <MaterialIcons name="chevron-right" size={22} color={palette.textHint} /> : null}
      </View>
    </Card>
  );
}

/** 세로로 쌓이는 자리에 둘 때는 `style={{ alignSelf: 'flex-start' }}` 로 늘어나지 않게 한다 */
export function Badge({ label, tone = 'primary', style }: { label: string; tone?: Tone | string; style?: StyleProp<ViewStyle> }) {
  const { palette } = useTheme();
  const color = toneColor(palette, tone);
  return (
    <View style={[styles.badge, { backgroundColor: soft(color) }, style]}>
      <Text style={[typography.label, { color }]} numberOfLines={1}>{label}</Text>
    </View>
  );
}

export function Avatar({ name, size = 52 }: { name?: string; size?: number }) {
  const { palette } = useTheme();
  const initial = (name ?? '').trim().slice(0, 1);
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: palette.primaryLight, alignItems: 'center', justifyContent: 'center' }}>
      {initial ? (
        <Text style={{ color: palette.primary, fontSize: size * 0.42, fontWeight: '800' }}>{initial}</Text>
      ) : (
        <MaterialIcons name="person" size={size * 0.55} color={palette.primary} />
      )}
    </View>
  );
}

export function SectionHeader({ title, actionLabel = '더보기', onAction }: { title: string; actionLabel?: string; onAction?: () => void }) {
  const { palette } = useTheme();
  return (
    <View style={styles.section}>
      <T variant="title" style={styles.fill}>{title}</T>
      {onAction ? (
        <Pressable accessibilityRole="link" onPress={onAction} hitSlop={10} style={styles.rowLine}>
          <T variant="caption" tone="secondary">{actionLabel}</T>
          <MaterialIcons name="chevron-right" size={16} color={palette.textSecondary} />
        </Pressable>
      ) : null}
    </View>
  );
}

/** 웹 `.panel--flush` 목록처럼 여러 줄을 한 카드에 구분선으로 묶는다. */
export function ListGroup({ children }: { children: ReactNode }) {
  const { palette } = useTheme();
  const items = Children.toArray(children).filter(isValidElement);
  return (
    <View style={[styles.card, styles.flush, elevation, { backgroundColor: palette.surface, borderColor: palette.border }]}>
      {items.map((child, index) => (
        <Fragment key={child.key ?? index}>
          {index > 0 ? <View style={[styles.divider, { backgroundColor: palette.divider }]} /> : null}
          {child}
        </Fragment>
      ))}
    </View>
  );
}

export function ListItem({
  title,
  subtitle,
  left,
  right,
  onPress,
  titleLines = 1,
  subtitleLines = 2,
}: {
  title: string;
  subtitle?: string;
  left?: ReactNode;
  right?: ReactNode;
  onPress?: () => void;
  titleLines?: number;
  subtitleLines?: number;
}) {
  const { palette } = useTheme();
  return (
    <Pressable
      disabled={!onPress}
      onPress={onPress}
      accessibilityRole={onPress ? 'button' : undefined}
      style={({ pressed }) => [styles.listItem, pressed && { backgroundColor: palette.surfaceVariant }]}
    >
      {left}
      <View style={styles.fillGap}>
        <T variant="body" numberOfLines={titleLines} style={{ fontWeight: '500' }}>{title}</T>
        {subtitle ? <T variant="caption" tone="hint" numberOfLines={subtitleLines}>{subtitle}</T> : null}
      </View>
      {right}
      {onPress ? <MaterialIcons name="chevron-right" size={20} color={palette.textHint} /> : null}
    </Pressable>
  );
}

export function StatTile({
  icon,
  label,
  value,
  tone = 'primary',
  onPress,
}: {
  icon: IconName;
  label: string;
  value: string;
  tone?: Tone | string;
  onPress?: () => void;
}) {
  const { palette } = useTheme();
  const color = toneColor(palette, tone);
  return (
    <View style={styles.fill}>
      <Card onPress={onPress} style={{ gap: 10, flex: 1 }}>
        <View style={[styles.iconBox, { backgroundColor: soft(color) }]}>
          <MaterialIcons name={icon} size={20} color={color} />
        </View>
        <View style={{ gap: 2 }}>
          <T variant="caption" tone="secondary" numberOfLines={2}>{label}</T>
          <Text style={[typography.title, { color: palette.text }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6}>
            {value}
          </Text>
        </View>
      </Card>
    </View>
  );
}

export function EmptyState({ text, icon = 'inbox' }: { text: string; icon?: IconName }) {
  const { palette } = useTheme();
  return (
    <View style={styles.empty}>
      <MaterialIcons name={icon} size={36} color={palette.textHint} />
      <T tone="secondary" style={{ textAlign: 'center' }}>{text}</T>
    </View>
  );
}

/** 화면 오른쪽 아래에 떠 있는 버튼 — Screen 의 footer 로 넘긴다. */
export function Fab({ icon, label, onPress }: { icon: IconName; label: string; onPress: () => void }) {
  const { palette } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [
        styles.fab,
        { backgroundColor: palette.primary, shadowColor: palette.primaryDark, opacity: pressed ? 0.9 : 1 },
      ]}
    >
      <MaterialIcons name={icon} size={22} color="#fff" />
      <Text style={[typography.subtitle, { color: '#fff', fontSize: 15 }]} numberOfLines={1}>{label}</Text>
    </Pressable>
  );
}

export function QuickAction({ icon, label, onPress }: { icon: IconName; label: string; onPress: () => void }) {
  const { palette } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [styles.quick, { opacity: pressed ? 0.6 : 1 }]}
    >
      <View style={[styles.quickIcon, { backgroundColor: palette.surface, borderColor: palette.border }, elevation]}>
        <MaterialIcons name={icon} size={24} color={palette.primary} />
      </View>
      <Text style={[typography.caption, { color: palette.text }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.75}>
        {label}
      </Text>
    </Pressable>
  );
}

/** 웹 `.chip` / `.chip--on` — 여럿 중 하나를 고른다 */
export function Chip({ label, selected, onPress }: { label: string; selected?: boolean; onPress: () => void }) {
  const { palette } = useTheme();
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected: Boolean(selected) }}
      onPress={onPress}
      style={({ pressed }) => [
        styles.chip,
        {
          backgroundColor: selected ? palette.primaryLight : palette.surface,
          borderColor: selected ? palette.primary : palette.border,
          opacity: pressed ? 0.75 : 1,
        },
      ]}
    >
      <Text style={{ fontSize: 14, color: selected ? palette.primaryDark : palette.textSecondary, fontWeight: selected ? '700' : '500' }} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

export function Callout({ tone, children }: { tone: 'success' | 'warning' | 'error' | 'info'; children: ReactNode }) {
  const { palette } = useTheme();
  const color = toneColor(palette, tone);
  const icon: IconName = tone === 'success' ? 'check-circle' : tone === 'info' ? 'info-outline' : 'error-outline';
  return (
    <View style={[styles.callout, { backgroundColor: soft(color, 0.1), borderColor: soft(color, 0.35) }]}>
      <MaterialIcons name={icon} size={18} color={color} style={{ marginTop: 1 }} />
      <View style={styles.fill}>{children}</View>
    </View>
  );
}

export function Segmented<K extends string>({
  options,
  value,
  onChange,
}: {
  options: { key: K; label: string }[];
  value: K;
  onChange: (key: K) => void;
}) {
  const { palette } = useTheme();
  return (
    <View style={[styles.segment, { backgroundColor: palette.surfaceVariant, borderColor: palette.border }]}>
      {options.map((option) => {
        const active = option.key === value;
        return (
          <Pressable
            key={option.key}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            onPress={() => onChange(option.key)}
            style={[styles.segmentItem, active && [{ backgroundColor: palette.surface }, elevation]]}
          >
            <Text
              style={[typography.subtitle, { fontSize: 14, color: active ? palette.text : palette.textSecondary }]}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.75}
            >
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

/** 채팅 · 댓글 입력줄 — Screen 의 footer 로 넘긴다. */
export function Composer({
  value,
  onChangeText,
  onSend,
  placeholder = '메시지를 입력하세요',
  busy,
}: {
  value: string;
  onChangeText: (value: string) => void;
  onSend: () => void;
  placeholder?: string;
  busy?: boolean;
}) {
  const { palette } = useTheme();
  const ready = value.trim().length > 0 && !busy;
  return (
    <SafeAreaView edges={['bottom']} style={[styles.composer, { backgroundColor: palette.surface, borderTopColor: palette.border }]}>
      <TextInput
        accessibilityLabel={placeholder}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={palette.textHint}
        multiline
        style={[styles.composerInput, { color: palette.text, backgroundColor: palette.surfaceVariant }]}
      />
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="보내기"
        disabled={!ready}
        onPress={onSend}
        style={[styles.sendBtn, { backgroundColor: ready ? palette.primary : palette.border }]}
      >
        {busy ? <ActivityIndicator color="#fff" size="small" /> : <MaterialIcons name="arrow-upward" size={22} color="#fff" />}
      </Pressable>
    </SafeAreaView>
  );
}

export function fmt(value?: Date | string | null): string {
  if (!value) return '';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** 기간 표기 — 같은 날이면 날짜를 한 번만 쓰고, 다른 날이면 `10/7 09:30 ~ 10/14 18:00` 처럼 줄인다 */
export function fmtRange(start?: Date | string | null, end?: Date | string | null): string {
  const toDate = (value?: Date | string | null) => {
    if (!value) return null;
    const date = value instanceof Date ? value : new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  };
  const from = toDate(start);
  const to = toDate(end);
  const time = (d: Date) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  const short = (d: Date) => `${d.getMonth() + 1}/${d.getDate()} ${time(d)}`;
  if (!from && !to) return '';
  if (!from) return `~ ${short(to!)}`;
  if (!to) return `${short(from)} ~`;
  if (todayKey(from) === todayKey(to)) return `${from.getMonth() + 1}/${from.getDate()} ${time(from)}~${time(to)}`;
  return `${short(from)} ~ ${short(to)}`;
}

export function todayKey(date = new Date()): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  fillGap: { flex: 1, gap: 2 },
  bar: { minHeight: 56, flexDirection: 'row', alignItems: 'center', borderBottomWidth: StyleSheet.hairlineWidth },
  largeBar: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 20, paddingTop: 12, paddingBottom: 4 },
  hit: { width: hit, height: hit, alignItems: 'center', justifyContent: 'center' },
  title: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 12 },
  body: { padding: 16, gap: 12, paddingBottom: 96 },
  card: { borderWidth: StyleSheet.hairlineWidth, borderRadius: radius, padding: 16, gap: 4 },
  flush: { padding: 0, gap: 0, overflow: 'hidden' },
  divider: { height: StyleSheet.hairlineWidth, marginLeft: 16 },
  btn: {
    minHeight: hit,
    borderRadius: 12,
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
    borderWidth: 1,
  },
  input: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10, fontSize: 16 },
  rowLine: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  iconBox: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, flexShrink: 0 },
  section: { flexDirection: 'row', alignItems: 'center', marginTop: 8 },
  listItem: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 52, paddingHorizontal: 16, paddingVertical: 10 },
  empty: { alignItems: 'center', justifyContent: 'center', gap: 10, paddingVertical: 40 },
  fab: {
    position: 'absolute',
    right: 20,
    bottom: 20,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    height: 52,
    paddingHorizontal: 20,
    borderRadius: 26,
    shadowOpacity: 0.3,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  chip: { minHeight: 36, paddingHorizontal: 14, borderRadius: 999, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  callout: { flexDirection: 'row', gap: 8, padding: 12, borderRadius: 12, borderWidth: 1 },
  segment: { flexDirection: 'row', padding: 4, borderRadius: 12, borderWidth: StyleSheet.hairlineWidth },
  segmentItem: { flex: 1, minHeight: 36, borderRadius: 9, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4 },
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  composerInput: { flex: 1, minHeight: 42, maxHeight: 120, borderRadius: 21, paddingHorizontal: 16, paddingTop: 11, paddingBottom: 11, fontSize: 15 },
  sendBtn: { width: 42, height: 42, borderRadius: 21, alignItems: 'center', justifyContent: 'center' },
  quick: { flex: 1, alignItems: 'center', gap: 6 },
  quickIcon: { width: 52, height: 52, borderRadius: 16, borderWidth: StyleSheet.hairlineWidth, alignItems: 'center', justifyContent: 'center' },
});
