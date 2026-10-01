import { Drawer } from 'expo-router/drawer';

import { useTheme } from '../../src/theme/Theme';

export default function InstructorLayout() {
  const { palette } = useTheme();
  return (
    <Drawer
      screenOptions={{
        headerStyle: { backgroundColor: palette.rail },
        headerTintColor: palette.railFg,
        drawerStyle: { backgroundColor: palette.surface },
      }}
    >
      <Drawer.Screen name="index" options={{ title: '자리 확인' }} />
      <Drawer.Screen name="[...path]" options={{ title: '메뉴', drawerItemStyle: { display: 'none' } }} />
    </Drawer>
  );
}
