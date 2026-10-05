import 'react-native-gesture-handler';
import { MaterialIcons } from '@expo/vector-icons';
import { focusManager, QueryClientProvider } from '@tanstack/react-query';
import { Stack, useRouter, useSegments, type ErrorBoundaryProps } from 'expo-router';
import { useEffect } from 'react';
import { AppState, Platform, Pressable, Text, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { homeHref, SessionProvider, useSession } from '../src/auth/session';
import { queryClient } from '../src/data/query';
import { usePushNotifications } from '../src/push/notifications';
import { ThemeProvider, useTheme } from '../src/theme/Theme';
import { light } from '../src/theme/tokens';
import { Btn, T } from '../src/ui/kit';

export default function RootLayout() {
  useEffect(() => {
    if (Platform.OS === 'web') return;
    const sub = AppState.addEventListener('change', (state) => focusManager.setFocused(state === 'active'));
    return () => sub.remove();
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <SessionProvider>
            <Gate />
          </SessionProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </GestureHandlerRootView>
  );
}

/** ThemeProvider 바깥에서도 그려지므로 테마 훅을 쓰지 않는다 */
export function ErrorBoundary({ error, retry }: ErrorBoundaryProps) {
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 12, backgroundColor: light.background }}>
      <MaterialIcons name="error-outline" size={40} color={light.error} />
      <Text style={{ fontSize: 18, fontWeight: '700', color: light.text }}>화면을 그리지 못했습니다</Text>
      <Text style={{ color: light.textSecondary, textAlign: 'center' }}>{error.message}</Text>
      <Pressable
        accessibilityRole="button"
        onPress={() => void retry()}
        style={{ minHeight: 44, paddingHorizontal: 20, borderRadius: 12, justifyContent: 'center', backgroundColor: light.primary }}
      >
        <Text style={{ color: '#fff', fontWeight: '700' }}>다시 시도</Text>
      </Pressable>
    </View>
  );
}

function OfflineScreen({ onRetry }: { onRetry: () => void }) {
  const { palette } = useTheme();
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 12, backgroundColor: palette.background }}>
      <MaterialIcons name="wifi-off" size={40} color={palette.textHint} />
      <T variant="title">서버에 연결할 수 없습니다</T>
      <T tone="secondary" style={{ textAlign: 'center' }}>인터넷 연결을 확인한 뒤 다시 시도해 주세요.{'\n'}로그인 정보는 그대로 남아 있습니다.</T>
      <Btn label="다시 시도" icon="refresh" onPress={onRetry} />
    </View>
  );
}

function Gate() {
  const { user, loading, offline, retry } = useSession();
  const segments = useSegments();
  const router = useRouter();
  usePushNotifications(Boolean(user && !user.mustChangePassword && !loading));

  useEffect(() => {
    if (loading || offline) return;
    const top = segments[0];
    const auth = top === 'login' || top === 'change-password' || top === 'tour';
    if (!user) {
      if (!auth) router.replace('/login');
      return;
    }
    if (user.mustChangePassword) {
      if (top !== 'change-password') router.replace('/change-password');
      return;
    }
    if (top === 'login' || top === 'change-password' || top === undefined) router.replace(homeHref(user.role));
  }, [user, loading, offline, segments, router]);

  if (offline && !user) return <OfflineScreen onRetry={retry} />;
  return <Stack screenOptions={{ headerShown: false }} />;
}
