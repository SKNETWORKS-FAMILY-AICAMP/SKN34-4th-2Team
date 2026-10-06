import { router } from 'expo-router';
import { useState } from 'react';
import { Text } from 'react-native';

import { homeHref, useSession } from '../src/auth/session';
import { Btn, Field, Screen } from '../src/ui/kit';

export default function ChangePasswordScreen() {
  const { user, changePassword, skipPasswordChange } = useSession();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [message, setMessage] = useState('');

  return (
    <Screen title="비밀번호 변경" back={false}>
      <Field label="현재 비밀번호" value={current} onChangeText={setCurrent} secure />
      <Field label="새 비밀번호" value={next} onChangeText={setNext} secure />
      {message ? <Text>{message}</Text> : null}
      <Btn label="변경" onPress={() => {
        void changePassword(next, current).then((result) => {
          if (!result.ok) setMessage(result.message);
          else if (user) router.replace(homeHref(user.role));
        });
      }} />
      <Btn label="다음에" tone="ghost" onPress={() => {
        void skipPasswordChange().then((result) => {
          if (!result.ok) setMessage(result.message);
          else if (user) router.replace(homeHref(user.role));
        });
      }} />
    </Screen>
  );
}
