import { Drawer } from 'expo-router/drawer';

import { StaffDrawer } from '../../src/nav/StaffDrawer';
import { useTheme } from '../../src/theme/Theme';

export default function AdminLayout() {
  const { palette } = useTheme();
  return (
    <Drawer
      drawerContent={(props) => <StaffDrawer role="admin" closeDrawer={() => props.navigation.closeDrawer()} />}
      screenOptions={{
        headerShown: false,
        drawerStyle: { backgroundColor: palette.rail, width: 280 },
      }}
    >
      <Drawer.Screen name="index" />
      <Drawer.Screen name="[...path]" />
    </Drawer>
  );
}
