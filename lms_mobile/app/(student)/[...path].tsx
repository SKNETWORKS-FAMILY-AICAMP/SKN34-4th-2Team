import { useLocalSearchParams } from 'expo-router';

import { StudentRoute } from '../../src/screens/resolve';

export default function CatchAll() {
  const params = useLocalSearchParams<{ path: string | string[] }>();
  const parts = Array.isArray(params.path) ? params.path : params.path ? [params.path] : [];
  return <StudentRoute parts={parts} />;
}
