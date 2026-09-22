import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Button, SafeAreaView, ScrollView, Text, TextInput, View } from 'react-native';

import { http } from './http';
import { useSessionStore } from './sessionStore';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

function Login({ onAuthed }: { onAuthed: () => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [mustChange, setMustChange] = useState(false);
  const [nextPassword, setNextPassword] = useState('');

  const login = async () => {
    setError('');
    try {
      const { data } = await http.post('/login', { email: email.trim(), password });
      useSessionStore.getState().setTokens(data.access, data.refresh);
      if (data.mustChangePassword) setMustChange(true);
      else onAuthed();
    } catch {
      setError('로그인에 실패했습니다.');
    }
  };

  const change = async () => {
    try {
      await http.post('/password', { password: nextPassword });
      setMustChange(false);
      onAuthed();
    } catch {
      setError('비밀번호 변경에 실패했습니다.');
    }
  };

  const skip = async () => {
    await http.post('/password', { skip: true });
    setMustChange(false);
    onAuthed();
  };

  if (mustChange) {
    return (
      <SafeAreaView>
        <Text>첫 로그인 — 비밀번호를 바꿔 주세요 (8자 이상)</Text>
        <TextInput value={nextPassword} onChangeText={setNextPassword} secureTextEntry />
        <Button title="변경" onPress={() => void change()} />
        <Button title="나중에 변경하기" onPress={() => void skip()} />
        {error ? <Text>{error}</Text> : null}
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView>
      <Text>PLAYDATA LXP</Text>
      <TextInput placeholder="이메일" value={email} onChangeText={setEmail} autoCapitalize="none" />
      <TextInput placeholder="비밀번호" value={password} onChangeText={setPassword} secureTextEntry />
      <Button title="로그인" onPress={() => void login()} />
      {error ? <Text>{error}</Text> : null}
    </SafeAreaView>
  );
}

function Home() {
  const { data } = useQuery({
    queryKey: ['bootstrap'],
    queryFn: async () => (await http.get('/bootstrap')).data,
  });
  const notices = (data?.notices ?? []) as { id: string; title: string; content: string }[];
  const me = data?.me as { display_name?: string; displayName?: string } | undefined;

  return (
    <SafeAreaView>
      <ScrollView>
        <Text>{me?.displayName || me?.display_name || '학생'}</Text>
        <Text>공지</Text>
        {notices.map((notice) => (
          <View key={notice.id}>
            <Text>{notice.title}</Text>
            <Text>{notice.content}</Text>
          </View>
        ))}
        <Button
          title="로그아웃"
          onPress={() => {
            useSessionStore.getState().clear();
            queryClient.clear();
          }}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

function Root() {
  const [ready, setReady] = useState(false);
  const access = useSessionStore((s) => s.access);
  if (!access || !ready) return <Login onAuthed={() => setReady(true)} />;
  return <Home />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar style="auto" />
      <Root />
    </QueryClientProvider>
  );
}
