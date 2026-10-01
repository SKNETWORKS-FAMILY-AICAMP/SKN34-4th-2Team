import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { type ReactNode } from 'react';
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
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { hit, radius } from '../theme/tokens';
import { useTheme } from '../theme/Theme';

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
}: {
  title: string;
  loading?: boolean;
  error?: string | null;
  empty?: boolean;
  emptyText?: string;
  refreshing?: boolean;
  onRefresh?: () => void;
  children?: ReactNode;
  footer?: ReactNode;
  back?: boolean;
}) {
  const { palette } = useTheme();
  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: palette.background }]} edges={['top', 'left', 'right']}>
      <View style={[styles.bar, { borderBottomColor: palette.border, backgroundColor: palette.surface }]}>
        {back ? (
          <Pressable accessibilityLabel="뒤로" onPress={() => router.back()} style={styles.hit}>
            <MaterialIcons name="arrow-back" size={24} color={palette.text} />
          </Pressable>
        ) : (
          <View style={styles.hit} />
        )}
        <Text style={[styles.title, { color: palette.text }]} numberOfLines={1}>
          {title}
        </Text>
        <View style={styles.hit} />
      </View>
      <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        {loading ? (
          <View style={styles.center}>
            <ActivityIndicator color={palette.primary} />
            <Text style={{ color: palette.textSecondary, marginTop: 8 }}>불러오는 중…</Text>
          </View>
        ) : error ? (
          <View style={styles.center}>
            <Text style={{ color: palette.error, textAlign: 'center' }}>{error}</Text>
            {onRefresh ? (
              <Btn label="다시 시도" onPress={onRefresh} />
            ) : null}
          </View>
        ) : (
          <ScrollView
            contentContainerStyle={styles.body}
            keyboardShouldPersistTaps="handled"
            refreshControl={
              onRefresh ? <RefreshControl refreshing={Boolean(refreshing)} onRefresh={onRefresh} /> : undefined
            }
          >
            {empty ? <Text style={{ color: palette.textSecondary, textAlign: 'center' }}>{emptyText}</Text> : children}
          </ScrollView>
        )}
        {footer}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

export function Card({ children, onPress }: { children: ReactNode; onPress?: () => void }) {
  const { palette } = useTheme();
  const body = <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>{children}</View>;
  if (!onPress) return body;
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => ({ opacity: pressed ? 0.75 : 1 })}>
      {body}
    </Pressable>
  );
}

export function Btn({
  label,
  onPress,
  tone = 'primary',
  disabled,
}: {
  label: string;
  onPress: () => void;
  tone?: 'primary' | 'ghost' | 'danger';
  disabled?: boolean;
}) {
  const { palette } = useTheme();
  const bg = tone === 'primary' ? palette.primary : tone === 'danger' ? palette.error : 'transparent';
  const fg = tone === 'ghost' ? palette.primary : '#fff';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={[styles.btn, { backgroundColor: bg, borderColor: palette.primary, opacity: disabled ? 0.5 : 1 }]}
    >
      <Text style={{ color: fg, fontWeight: '600' }}>{label}</Text>
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
      <Text style={{ color: palette.textSecondary }}>{label}</Text>
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
  const { palette } = useTheme();
  return <Text style={{ color: palette.textSecondary }}>{children}</Text>;
}

export function Row({ title, subtitle, onPress }: { title: string; subtitle?: string; onPress?: () => void }) {
  const { palette } = useTheme();
  return (
    <Card onPress={onPress}>
      <Text style={{ fontWeight: '600', fontSize: 16, color: palette.text }}>{title}</Text>
      {subtitle ? <Muted>{subtitle}</Muted> : null}
    </Card>
  );
}

export function fmt(value?: Date | string | null): string {
  if (!value) return '';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function todayKey(date = new Date()): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  bar: { minHeight: 56, flexDirection: 'row', alignItems: 'center', borderBottomWidth: StyleSheet.hairlineWidth },
  hit: { width: hit, height: hit, alignItems: 'center', justifyContent: 'center' },
  title: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 12 },
  body: { padding: 16, gap: 12, paddingBottom: 32 },
  card: { borderWidth: StyleSheet.hairlineWidth, borderRadius: radius, padding: 14, gap: 4 },
  btn: { minHeight: hit, borderRadius: radius, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16, borderWidth: 1 },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 16 },
});
