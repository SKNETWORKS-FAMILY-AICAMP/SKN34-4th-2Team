import AsyncStorage from '@react-native-async-storage/async-storage';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Text } from 'react-native';

import { homeHref, useSession } from '../src/auth/session';
import { Btn, Card, Screen } from '../src/ui/kit';

const SLIDES = [
  '출결, 공지, 마일리지는 핸드폰에서 바로 확인합니다.',
  '이력서와 설문, 평가는 앱에서 작성할 수 있습니다.',
  '연습장과 좌석 배치 편집은 PC 웹에서 이어서 합니다.',
];

export default function TourScreen() {
  const { user } = useSession();
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!user) return;
    void AsyncStorage.getItem(`lms.tour.${user.uid}`).then((seen) => {
      if (seen) router.replace(homeHref(user.role));
    });
  }, [user]);
  const last = index >= SLIDES.length - 1;

  async function finish() {
    if (user) await AsyncStorage.setItem(`lms.tour.${user.uid}`, '1');
    if (user) router.replace(homeHref(user.role));
  }

  return (
    <Screen title="시작하기" back={false}>
      <Card>
        <Text style={{ fontSize: 18 }}>{SLIDES[index]}</Text>
      </Card>
      {last ? <Btn label="시작" onPress={() => void finish()} /> : <Btn label="다음" onPress={() => setIndex((value) => value + 1)} />}
      <Btn label="건너뛰기" tone="ghost" onPress={() => void finish()} />
    </Screen>
  );
}
