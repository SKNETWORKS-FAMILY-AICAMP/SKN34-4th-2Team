import 'react-native-gesture-handler';
import { QueryClientProvider } from '@tanstack/react-query';
import { Stack, useRouter, useSegments } from 'expo-router';
import { useEffect } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { homeHref, SessionProvider, useSession } from '../src/auth/session';
import { queryClient } from '../src/data/query';
import { ThemeProvider } from '../src/theme/Theme';

export default function RootLayout() {
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

function Gate() {
  const { user, loading } = useSession();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
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
  }, [user, loading, segments, router]);

  return <Stack screenOptions={{ headerShown: false }} />;
}
