import AsyncStorage from '@react-native-async-storage/async-storage';
import { MaterialIcons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, View, useWindowDimensions } from 'react-native';
import type { UserRole } from '@web/domain/types';

import { homeHref, useSession } from '../src/auth/session';
import { useTheme } from '../src/theme/Theme';
import { Btn, Card, Screen, T, type IconName } from '../src/ui/kit';

interface Slide {
  icon: IconName;
  title: string;
  body: string;
}

/** 역할마다 보여 줄 이용 안내 — 앱에서 바로 하는 일과 PC 웹에서 이어서 하는 일을 나눠 알려 준다 */
const SLIDES: Record<UserRole, Slide[]> = {
  student: [
    { icon: 'dashboard', title: '대시보드', body: '오늘 수업과 공지, 해야 할 일을 한 화면에서 확인해요.' },
    { icon: 'notifications-active', title: '알림', body: '새 알림은 앱을 켜 두면 바로 떠요.\n오른쪽 위 종을 누르면 받은 알림을 다시 볼 수 있어요.' },
    { icon: 'event-busy', title: '출결 신청', body: '지각 · 조퇴 · 외출 · 결석이 있으면 오른쪽 위 「출결 신청」에서 그날 바로 신청해요.' },
    { icon: 'description', title: '이력서', body: '이력서 관리에서 바탕 이력서를 쓰고 고쳐요.\n「마이페이지 정보로 빈 칸 채우기」로 기본 정보를 한 번에 넣을 수 있어요.' },
    { icon: 'computer', title: 'PC 웹에서 이어서', body: '공고 맞춤 지원 · AI 첨삭 · 연습장은 PC 웹에서 이어서 해요.' },
  ],
  admin: [
    { icon: 'fact-check', title: '불시 점검', body: '대시보드 오른쪽 위 「불시 점검」을 누르면 좌석 배치도에서 바로 체크해요.\n칸을 누를 때마다 유 → 무로 바뀌어요.' },
    { icon: 'groups', title: '보고 있는 기수', body: '대시보드에서 기수를 고르면 학생 · 출결 · 점검 등 모든 메뉴가 그 기수 기준으로 바뀌어요.' },
    { icon: 'pending-actions', title: '출석 관리', body: '학생의 출결 신청 승인 · 반려와 불시 점검 이력은 출석 관리에서 봐요.' },
    { icon: 'campaign', title: '알림 팝업', body: '알림 팝업을 켜 두면 학생 앱과 웹에 바로 떠요.\n학생은 종 아이콘에서 다시 볼 수 있어요.' },
    { icon: 'computer', title: 'PC 웹에서 이어서', body: '좌석 배치 편집과 점검 기록 내려받기(Excel · Word · PDF)는 PC 웹에서 해요.' },
  ],
  instructor: [
    { icon: 'fact-check', title: '자리 확인', body: '첫 화면에서 교시마다 학생 자리를 확인해요.' },
    { icon: 'description', title: '이력서 · 게시물', body: '학생 이력서와 게시물은 메뉴에서 바로 보고 관리해요.' },
    { icon: 'quiz', title: '성취도평가', body: '평가 출제와 채점은 성취도평가 메뉴에서 해요.' },
    { icon: 'computer', title: 'PC 웹에서 이어서', body: '복습 문제 출제처럼 큰 화면이 필요한 일은 PC 웹에서 해요.' },
  ],
};

export default function TourScreen() {
  const { user } = useSession();
  const { palette } = useTheme();
  const { width } = useWindowDimensions();
  const { replay } = useLocalSearchParams<{ replay?: string }>();
  const replaying = replay === '1';
  const [index, setIndex] = useState(0);
  const slides = SLIDES[user?.role ?? 'student'] ?? SLIDES.student;
  const slide = slides[Math.min(index, slides.length - 1)];
  const last = index >= slides.length - 1;

  // 처음 로그인할 때만 자동으로 보여 준다 — 설정의 「이용 안내 다시 보기」로 연 경우는 그대로 둔다
  useEffect(() => {
    if (!user || replaying) return;
    void AsyncStorage.getItem(`lms.tour.${user.uid}`).then((seen) => {
      if (seen) router.replace(homeHref(user.role));
    });
  }, [user, replaying]);

  async function finish() {
    if (!user) return;
    await AsyncStorage.setItem(`lms.tour.${user.uid}`, '1');
    if (replaying && router.canGoBack()) router.back();
    else router.replace(homeHref(user.role));
  }

  const cardWidth = Math.min(width - 32, 560);

  return (
    <Screen title="이용 안내" back={replaying}>
      <View style={{ alignItems: 'center', gap: 20, paddingTop: 12 }}>
        <Card style={{ width: cardWidth, alignItems: 'center', gap: 16, paddingVertical: 36, paddingHorizontal: 24 }}>
          <View style={{ width: 88, height: 88, borderRadius: 26, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.primaryLight }}>
            <MaterialIcons name={slide.icon} size={46} color={palette.primary} />
          </View>
          <T variant="caption" tone="secondary">
            {index + 1} / {slides.length}
          </T>
          <T variant="hero" style={{ textAlign: 'center' }}>{slide.title}</T>
          <T style={{ textAlign: 'center', fontSize: 16, lineHeight: 25 }} tone="secondary">
            {slide.body}
          </T>
        </Card>

        <View style={{ flexDirection: 'row', gap: 8 }} accessibilityRole="tablist">
          {slides.map((item, i) => (
            <Pressable
              key={item.title}
              accessibilityRole="tab"
              accessibilityLabel={`${i + 1}번째 안내: ${item.title}`}
              accessibilityState={{ selected: i === index }}
              onPress={() => setIndex(i)}
              hitSlop={8}
              style={{ width: i === index ? 22 : 8, height: 8, borderRadius: 4, backgroundColor: i === index ? palette.primary : palette.border }}
            />
          ))}
        </View>

        <View style={{ width: cardWidth, gap: 10 }}>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            {index > 0 ? (
              <View style={{ flex: 1 }}>
                <Btn label="이전" tone="ghost" onPress={() => setIndex((value) => Math.max(0, value - 1))} />
              </View>
            ) : null}
            <View style={{ flex: 2 }}>
              {last ? (
                <Btn label={replaying ? '닫기' : '시작하기'} icon="check" onPress={() => void finish()} />
              ) : (
                <Btn label="다음" onPress={() => setIndex((value) => value + 1)} />
              )}
            </View>
          </View>
          {!last ? <Btn label={replaying ? '닫기' : '건너뛰기'} tone="ghost" onPress={() => void finish()} /> : null}
        </View>
      </View>
    </Screen>
  );
}
