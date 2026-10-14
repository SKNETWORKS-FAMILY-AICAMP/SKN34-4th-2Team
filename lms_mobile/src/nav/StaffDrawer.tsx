import { MaterialIcons } from '@expo/vector-icons';
import { router, useNavigation, usePathname } from 'expo-router';
import { DrawerActions } from 'expo-router/react-navigation';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useSession } from '../auth/session';
import { useTheme } from '../theme/Theme';
import { typography } from '../theme/tokens';
import { Avatar } from '../ui/kit';
import { appNav, type AppNavItem, type AppNavSection } from './webNav';

/** 웹 상단 막대의 메뉴 단추 — 서랍을 연다 */
export function MenuButton() {
  const { palette } = useTheme();
  const navigation = useNavigation();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="메뉴"
      hitSlop={10}
      onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
      style={({ pressed }) => [styles.menuBtn, { borderColor: palette.border, backgroundColor: palette.surface, opacity: pressed ? 0.7 : 1 }]}
    >
      <MaterialIcons name="menu" size={22} color={palette.text} />
    </Pressable>
  );
}

/** 앱 경로에서 (그룹) 을 뺀 실제 주소 — usePathname 과 견준다 */
function plain(href: string): string {
  return href.replace(/\/\([^)]+\)/g, '') || '/';
}

function isSelected(pathname: string, href: string): boolean {
  const target = plain(href);
  if (target === '/') return pathname === '/';
  return pathname === target || pathname.startsWith(`${target}/`);
}

/** 웹 셸의 사이드바(`app/Shell.tsx`)와 같은 메뉴 · 같은 묶음을 서랍에 그린다 */
export function StaffDrawer({ role, closeDrawer }: { role: 'instructor' | 'admin'; closeDrawer: () => void }) {
  const { palette } = useTheme();
  const { user, signOut } = useSession();
  const pathname = usePathname();
  const sections = appNav(role);
  const open = (href: string) => {
    closeDrawer();
    router.push(href as never);
  };
  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: palette.rail }]} edges={['top', 'bottom', 'left']}>
      <View style={styles.brand}>
        <Text style={[styles.wordmark, { color: palette.railFg }]}>PLAYDATA</Text>
        <Text style={{ color: palette.textHint, fontSize: 12 }}>{role === 'admin' ? '관리자' : '강사'}</Text>
      </View>
      <ScrollView contentContainerStyle={styles.items}>
        {sections.map((section) => (
          <DrawerSection key={section.id} section={section} pathname={pathname} onOpen={open} />
        ))}
      </ScrollView>
      <View style={[styles.foot, { borderTopColor: 'rgba(255,255,255,0.08)' }]}>
        <Pressable style={styles.me} onPress={() => open(role === 'admin' ? '/(admin)/mypage' : '/(instructor)/mypage')}>
          <Avatar name={user?.displayName} size={30} />
          <View style={styles.fill}>
            <Text style={{ color: palette.railFg, fontWeight: '600' }} numberOfLines={1}>{user?.displayName}</Text>
            <Text style={{ color: palette.textHint, fontSize: 12 }} numberOfLines={1}>{user?.cohortName}</Text>
          </View>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={() => void signOut()} style={styles.logout}>
          <MaterialIcons name="logout" size={18} color={palette.railFg} />
          <Text style={{ color: palette.railFg }}>로그아웃</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

function DrawerSection({ section, pathname, onOpen }: { section: AppNavSection; pathname: string; onOpen: (href: string) => void }) {
  const { palette } = useTheme();
  const hasSelected = section.items.some((item) => isSelected(pathname, item.href));
  const [open, setOpen] = useState(true);
  if (!section.title) {
    return (
      <View style={styles.section}>
        {section.items.map((item) => (
          <DrawerRow key={item.href + item.label} item={item} selected={isSelected(pathname, item.href)} onOpen={onOpen} />
        ))}
      </View>
    );
  }
  return (
    <View style={styles.section}>
      <Pressable style={styles.group} onPress={() => setOpen((value) => !value)}>
        <Text style={[typography.label, { color: palette.textHint, flex: 1 }]}>{section.title}</Text>
        <MaterialIcons name={open ? 'expand-less' : 'expand-more'} size={18} color={palette.textHint} />
      </Pressable>
      {open || hasSelected
        ? section.items.map((item) => (
            <DrawerRow key={item.href + item.label} item={item} selected={isSelected(pathname, item.href)} onOpen={onOpen} />
          ))
        : null}
    </View>
  );
}

function DrawerRow({ item, selected, onOpen }: { item: AppNavItem; selected: boolean; onOpen: (href: string) => void }) {
  const { palette } = useTheme();
  const fg = selected ? '#fff' : palette.railFg;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={() => onOpen(item.href)}
      style={({ pressed }) => [
        styles.row,
        { backgroundColor: selected ? palette.primary : pressed ? 'rgba(255,255,255,0.06)' : 'transparent' },
      ]}
    >
      <MaterialIcons name={item.icon} size={20} color={fg} />
      <Text style={{ color: fg, fontSize: 15, fontWeight: selected ? '700' : '500' }} numberOfLines={1}>
        {item.label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  menuBtn: { width: 40, height: 40, borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, alignItems: 'center', justifyContent: 'center' },
  brand: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12, gap: 2 },
  wordmark: { fontSize: 18, fontWeight: '800', letterSpacing: 1 },
  items: { paddingHorizontal: 10, paddingBottom: 16, gap: 6 },
  section: { gap: 2 },
  group: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingTop: 12, paddingBottom: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 44, paddingHorizontal: 12, borderRadius: 10 },
  foot: { borderTopWidth: StyleSheet.hairlineWidth, padding: 12, gap: 4 },
  me: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 8 },
  logout: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 12, paddingVertical: 10 },
});
