import { useLocalSearchParams } from 'expo-router';

import { AdminRoute } from '../../src/screens/resolve';

export default function CatchAll() {
  const params = useLocalSearchParams<{ path: string | string[] }>();
  const parts = Array.isArray(params.path) ? params.path : params.path ? [params.path] : [];
  return <AdminRoute parts={parts} />;
}