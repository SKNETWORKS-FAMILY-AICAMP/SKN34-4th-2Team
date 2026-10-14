#!/usr/bin/env python3
"""
설명서 캡처용 데모 앱 만들기 — lms_mobile 을 임시 폴더에 복사하고, 서버 대신 웹 데모 데이터(lms_react/src/data/seed.ts)를
쓰도록 몇 군데를 고친 뒤 웹으로 내보낸다. 원본 lms_mobile 은 건드리지 않는다.

  python3 tools/manual/prepare-demo.py /tmp/lms-demo

끝나면 /tmp/lms-demo/app/dist-web 에 정적 웹 앱이 생긴다. README.md 의 다음 단계를 따른다.
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MOBILE = HERE.parent.parent
WEB_SRC = Path(__import__('os').environ.get('LMS_WEB_SRC', MOBILE.parent / 'lms_react' / 'src'))


def patch(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'패치할 곳을 못 찾음: {path}\n---\n{old}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    out = Path(args[0] if args else '/tmp/lms-demo').resolve()
    app = out / 'app'
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(MOBILE, app, ignore=shutil.ignore_patterns('node_modules', '.git', 'dist*', 'ios', 'android', '.expo'))
    shutil.copytree(WEB_SRC, out / 'lms_react' / 'src')

    (app / 'src' / 'demo').mkdir(exist_ok=True)
    shutil.copy(HERE / 'demo-adapter.ts', app / 'src' / 'demo' / 'adapter.ts')

    # 1) 모든 요청을 데모 어댑터로
    http = app / 'src' / 'data' / 'http.ts'
    patch(http, "import { useSessionStore } from './sessionStore';",
          "import { useSessionStore } from './sessionStore';\nimport { demoAdapter } from '../demo/adapter';")
    for name in ('http', 'raw'):
        patch(http, f"const {name} = axios.create({{\n  baseURL: API_BASE,", f"const {name} = axios.create({{\n  adapter: demoAdapter,\n  baseURL: API_BASE,")

    # 2) bootstrap 은 웹 데모 저장소 그대로 — 알림 팝업은 시간대 제한을 풀고, 링크 있는 알림 하나를 더한다
    patch(app / 'src' / 'data' / 'query.ts',
          "  const { data } = await http.get<Record<string, unknown>>('/bootstrap');\n  return mapBootstrap(data);",
          """  void mapBootstrap;
  const { getDb } = await import('@web/data/store');
  const base = getDb();
  const alertPopups = [
    ...base.alertPopups.map((a) => ({ ...a, startTime: undefined, endTime: undefined })),
    { id: 'ap2', title: '이력서 클리닉 신청 안내', content: '이번 주 금요일까지 이력서 클리닉 신청을 받습니다. 아래 링크에서 신청해 주세요.', authorName: 'PLAYDATA 관리자', isActive: true, sortOrder: 2, linkUrl: 'https://example.com/clinic', createdAt: new Date(Date.now() - 3 * 3600000) },
  ];
  const hidePopups = typeof window !== 'undefined' && window.localStorage.getItem('demoPopups') !== '1';
  return { ...base, alertPopups, alertReadIds: hidePopups ? alertPopups.map((a) => a.id) : [] } as Database;""")

    # 3) 로그인 토큰은 메모리에 — localStorage 의 demoUid 가 있으면 로그인된 것으로 시작
    patch(app / 'src' / 'data' / 'sessionStore.ts', "import * as SecureStore from 'expo-secure-store';",
          "const SecureStore = { setItemAsync: async (_k: string, _v: string) => undefined, deleteItemAsync: async (_k: string) => undefined, "
          "getItemAsync: async (_k: string) => (typeof window !== 'undefined' && window.localStorage.getItem('demoUid') ? 'demo' : null) };")

    # 4) 캡처 스크립트가 화면을 옮길 수 있게 router 와 데모 저장소를 전역에 둔다
    layout = app / 'app' / '_layout.tsx'
    layout.write_text(
        "import { router as __demoRouter } from 'expo-router';\nimport { getDb as __demoDb } from '@web/data/store';\n"
        "(globalThis as Record<string, unknown>).__router = __demoRouter;\n(globalThis as Record<string, unknown>).__db = __demoDb;\n"
        + layout.read_text(encoding='utf-8'),
        encoding='utf-8',
    )

    (app / '.npmrc').write_text('legacy-peer-deps=true\n', encoding='utf-8')
    if '--no-build' in sys.argv:
        print(f'패치만 끝냄: {app}')
        return
    run = lambda *cmd: subprocess.run(cmd, cwd=app, check=True)  # noqa: E731
    run('npm', 'ci')
    # 웹으로 띄우는 데 필요한 패키지 — 앱 package.json 에는 넣지 않는다
    run('npm', 'i', '--no-save', 'react-dom@19.2.3', 'react-native-web@0.21.4', '@expo/metro-runtime@57.0.16')
    subprocess.run(['npx', 'expo', 'export', '-p', 'web', '--output-dir', 'dist-web'], cwd=app, check=True, env={**__import__('os').environ, 'CI': '1'})
    print(f'\n데모 웹 앱: {app / "dist-web"}')


if __name__ == '__main__':
    main()
