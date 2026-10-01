import { MaterialIcons } from '@expo/vector-icons';
import { Tabs } from 'expo-router';

import { useTheme } from '../../../src/theme/Theme';

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
      <Tabs.Screen name="index" options={{ title: '홈', tabBarIcon: ({ color }) => <MaterialIcons name="dashboard" color={color} size={24} /> }} />
      <Tabs.Screen name="board" options={{ title: '게시판', tabBarIcon: ({ color }) => <MaterialIcons name="forum" color={color} size={24} /> }} />
      <Tabs.Screen name="study" options={{ title: '공부', tabBarIcon: ({ color }) => <MaterialIcons name="menu-book" color={color} size={24} /> }} />
      <Tabs.Screen name="mileage" options={{ title: '마일리지', tabBarIcon: ({ color }) => <MaterialIcons name="card-giftcard" color={color} size={24} /> }} />
      <Tabs.Screen name="more" options={{ title: '더보기', tabBarIcon: ({ color }) => <MaterialIcons name="more-horiz" color={color} size={24} /> }} />
    </Tabs>
  );
}
