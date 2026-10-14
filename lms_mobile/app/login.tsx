import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useRef, useState, type Ref } from 'react';
import {
  ActivityIndicator,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useSession } from '../src/auth/session';
import { useTheme } from '../src/theme/Theme';
import { elevation, hit, typography } from '../src/theme/tokens';
import { Callout, T, type IconName } from '../src/ui/kit';

const CYAN = '#00c2d4';
const VIOLET = '#8b5cf6';

export default function LoginScreen() {
  const { signIn } = useSession();
  const { palette } = useTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const passwordRef = useRef<TextInput>(null);

  const ready = email.trim().length > 0 && password.length > 0 && !busy;

  const submit = () => {
    if (!ready) return;
    setBusy(true);
    setMessage('');
    void signIn(email.trim(), password).then((result) => {
      setBusy(false);
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      router.replace(result.mustChangePassword ? '/change-password' : '/tour');
    });
  };

  return (
    <View style={[styles.fill, { backgroundColor: palette.rail }]}>
      <View style={[styles.blob, { backgroundColor: CYAN, top: -80, right: -60 }]} />
      <View style={[styles.blob, { backgroundColor: VIOLET, top: 140, left: -90, opacity: 0.18 }]} />

      <SafeAreaView style={styles.fill} edges={['top', 'left', 'right']}>
        <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled" bounces={false}>
            <View style={styles.hero}>
              <View style={styles.logoBox}>
                <Image source={require('../assets/icon.png')} style={styles.logo} />
              </View>
              <Text style={styles.brand}>PLAYDATA LMS</Text>
              <Text style={styles.welcome}>다시 오신 걸 환영해요</Text>
              <Text style={styles.sub}>계정으로 로그인하고 오늘의 학습을 이어가세요.</Text>
            </View>

            <View style={[styles.sheet, { backgroundColor: palette.surface }]}>
              <T variant="title">로그인</T>

              <InputRow
                icon="mail-outline"
                placeholder="이메일"
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoComplete="email"
                returnKeyType="next"
                onSubmitEditing={() => passwordRef.current?.focus()}
              />
              <InputRow
                ref={passwordRef}
                icon="lock-outline"
                placeholder="비밀번호"
                value={password}
                onChangeText={setPassword}
                secure
                autoComplete="password"
                returnKeyType="done"
                onSubmitEditing={submit}
              />

              {message ? (
                <Callout tone="error">
                  <T variant="caption" tone="error">{message}</T>
                </Callout>
              ) : null}

              <Pressable
                accessibilityRole="button"
                accessibilityLabel="로그인"
                disabled={!ready}
                onPress={submit}
                style={({ pressed }) => [
                  styles.cta,
                  { backgroundColor: palette.primary, shadowColor: palette.primaryDark },
                  { opacity: !ready ? 0.5 : pressed ? 0.88 : 1 },
                ]}
              >
                {busy ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <>
                    <Text style={styles.ctaText}>로그인</Text>
                    <MaterialIcons name="arrow-forward" size={20} color="#fff" />
                  </>
                )}
              </Pressable>

              <T variant="caption" tone="hint" style={styles.footnote}>
                계정 문의는 담당 매니저에게 연락해 주세요.
              </T>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </View>
  );
}

type InputRowProps = {
  icon: IconName;
  placeholder: string;
  value: string;
  onChangeText: (value: string) => void;
  secure?: boolean;
  keyboardType?: 'default' | 'email-address';
  autoComplete?: 'email' | 'password';
  returnKeyType?: 'next' | 'done';
  onSubmitEditing?: () => void;
  ref?: Ref<TextInput>;
};

function InputRow({ icon, secure, ref, ...rest }: InputRowProps) {
  const { palette } = useTheme();
  const [focused, setFocused] = useState(false);
  const [hidden, setHidden] = useState(true);

  return (
    <View
      style={[
        styles.inputRow,
        {
          backgroundColor: palette.surfaceVariant,
          borderColor: focused ? palette.primary : 'transparent',
        },
      ]}
    >
      <MaterialIcons name={icon} size={20} color={focused ? palette.primary : palette.textHint} />
      <TextInput
        ref={ref}
        {...rest}
        accessibilityLabel={rest.placeholder}
        placeholderTextColor={palette.textHint}
        secureTextEntry={secure && hidden}
        autoCapitalize="none"
        autoCorrect={false}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        style={[styles.input, { color: palette.text }]}
      />
      {secure ? (
        <Pressable
          accessibilityLabel={hidden ? '비밀번호 보기' : '비밀번호 숨기기'}
          hitSlop={10}
          onPress={() => setHidden((value) => !value)}
        >
          <MaterialIcons name={hidden ? 'visibility-off' : 'visibility'} size={20} color={palette.textHint} />
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  scroll: { flexGrow: 1 },
  blob: { position: 'absolute', width: 260, height: 260, borderRadius: 130, opacity: 0.22 },
  hero: { paddingHorizontal: 28, paddingTop: 48, paddingBottom: 56, gap: 6 },
  logoBox: {
    width: 64,
    height: 64,
    borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(0,194,212,0.45)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 18,
  },
  logo: { width: 40, height: 40, borderRadius: 10 },
  brand: { color: CYAN, fontSize: 13, fontWeight: '800', letterSpacing: 2 },
  welcome: { ...typography.hero, color: '#fff', fontSize: 28 },
  sub: { color: '#94a3b8', fontSize: 14, lineHeight: 20 },
  sheet: {
    flex: 1,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingHorizontal: 24,
    paddingTop: 28,
    paddingBottom: 40,
    gap: 14,
    ...elevation,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    minHeight: hit + 8,
    paddingHorizontal: 14,
    borderRadius: 14,
    borderWidth: 1.5,
  },
  input: { flex: 1, fontSize: 16, paddingVertical: 12 },
  cta: {
    marginTop: 6,
    minHeight: 54,
    borderRadius: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    shadowOpacity: 0.35,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 5,
  },
  ctaText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  footnote: { textAlign: 'center', marginTop: 8 },
});
