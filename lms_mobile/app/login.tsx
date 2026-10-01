import { router } from 'expo-router';
import { useState } from 'react';
import { Text } from 'react-native';

import { useSession } from '../src/auth/session';
import { Btn, Field, Screen } from '../src/ui/kit';

export default function LoginScreen() {
  const { signIn } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  return (
    <Screen title="로그인" back={false}>
      <Field label="이메일" value={email} onChangeText={setEmail} keyboard="email-address" />
      <Field label="비밀번호" value={password} onChangeText={setPassword} secure />
      {message ? <Text>{message}</Text> : null}
      <Btn
        label={busy ? '확인 중…' : '로그인'}
        disabled={busy}
        onPress={() => {
          setBusy(true);
          void signIn(email, password).then((result) => {
            setBusy(false);
            if (!result.ok) {
              setMessage(result.message);
              return;
            }
            router.replace(result.mustChangePassword ? '/change-password' : '/tour');
          });
        }}
      />
    </Screen>
  );
}
