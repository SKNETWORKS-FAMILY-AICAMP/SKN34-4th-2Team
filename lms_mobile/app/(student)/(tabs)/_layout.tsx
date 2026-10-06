import { MaterialIcons } from '@expo/vector-icons';
import { RoutePaths } from '@web/app/routePaths';
import { Tabs } from 'expo-router';

import { navIcon, navLabel } from '../../../src/nav/webNav';
import { useTheme } from '../../../src/theme/Theme';
import type { IconName } from '../../../src/ui/kit';

const tabs: { name: string; webPath?: string; title: string; icon: IconName }[] = [
  { name: 'index', webPath: RoutePaths.dashboard, title: '대시보드', icon: 'dashboard' },
  { name: 'board', webPath: RoutePaths.board, title: '게시판', icon: 'forum' },
  { name: 'study', webPath: RoutePaths.studyRoom, title: '학습실', icon: 'menu-book' },
  { name: 'mileage', webPath: RoutePaths.mileage, title: '마일리지', icon: 'card-giftcard' },
  { name: 'more', title: '메뉴', icon: 'menu' },
];

export default function StudentTabs() {
  const { palette } = useTheme();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: palette.primary,
        tabBarInactiveTintColor: palette.textSecondary,
        tabBarStyle: { backgroundColor: palette.surface, borderTopColor: palette.border, minHeight: 56 },
      }}
    >
      {tabs.map((tab) => {
        const title = tab.webPath ? navLabel(tab.webPath, tab.title) : tab.title;
        const icon = tab.webPath ? navIcon(tab.webPath, tab.icon) : tab.icon;
        return (
          <Tabs.Screen
            key={tab.name}
            name={tab.name}
            options={{ title, tabBarIcon: ({ color }) => <MaterialIcons name={icon} color={color} size={24} /> }}
          />
        );
      })}
    </Tabs>
  );
}
