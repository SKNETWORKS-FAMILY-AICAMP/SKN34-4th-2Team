import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { router } from 'expo-router';
import { useEffect } from 'react';
import { Platform } from 'react-native';

import { http } from '../data/http';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

/** 이 기기에서 서버에 올린 토큰 — 로그아웃할 때 지운다 */
let registeredToken: string | null = null;

function projectId(): string | undefined {
  const extra = Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined;
  return extra?.eas?.projectId ?? Constants.easConfig?.projectId;
}

/**
 * 알림 권한을 묻고 Expo 푸시 토큰을 서버에 올린다.
 * 시뮬레이터 · EAS projectId 없음 · Android Expo Go(원격 푸시 미지원)에서는 조용히 건너뛴다.
 */
export async function registerPush(): Promise<void> {
  if (Platform.OS === 'web' || !Device.isDevice) return;
  const id = projectId();
  if (!id) {
    console.warn('[push] EAS projectId 가 없어 푸시 등록을 건너뜁니다 — `npx eas-cli init` 으로 연결하세요.');
    return;
  }
  try {
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('default', {
        name: '기본 알림',
        importance: Notifications.AndroidImportance.HIGH,
      });
    }
    let { status } = await Notifications.getPermissionsAsync();
    if (status !== 'granted') ({ status } = await Notifications.requestPermissionsAsync());
    if (status !== 'granted') return;
    const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId: id });
    await http.post('/push-tokens', { token, platform: Platform.OS });
    registeredToken = token;
  } catch (error) {
    console.warn('[push] 등록 실패', error instanceof Error ? error.message : error);
  }
}

/** 로그아웃 직전 — 토큰을 지우기 전에 불러야 인증 헤더가 실린다. 오래 기다리지 않는다. */
export async function unregisterPush(): Promise<void> {
  const token = registeredToken;
  registeredToken = null;
  if (!token) return;
  await Promise.race([
    http.post('/push-tokens/remove', { token }).catch(() => undefined),
    new Promise((resolve) => setTimeout(resolve, 3000)),
  ]);
}

function openFrom(response: Notifications.NotificationResponse | null): void {
  const url = response?.notification.request.content.data?.url;
  if (typeof url === 'string' && url.startsWith('/')) router.push(url as never);
}

/** 로그인한 동안 토큰을 올리고, 알림을 누르면 그 화면으로 연다(앱이 꺼져 있다가 알림으로 켜진 경우 포함) */
export function usePushNotifications(signedIn: boolean): void {
  useEffect(() => {
    if (!signedIn || Platform.OS === 'web') return;
    void registerPush();
    const cold = Notifications.getLastNotificationResponse();
    if (cold) {
      Notifications.clearLastNotificationResponse();
      setTimeout(() => openFrom(cold), 0);
    }
    const sub = Notifications.addNotificationResponseReceivedListener(openFrom);
    return () => sub.remove();
  }, [signedIn]);
}
