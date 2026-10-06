# PLAYDATA LXP 모바일

웹(`lms_react`)과 같은 Django API를 쓰는 Expo 앱입니다. 연습장, 코드 편집, 좌석 배치 편집은 PC 웹으로 안내합니다.

## 실행

```bash
cd lms_mobile
cp .env.example .env
npm start
```

Expo Go에서 QR을 찍습니다.

`.env`

- `EXPO_PUBLIC_API_BASE` — `http://<PC LAN IP>:8000/api`
- `EXPO_PUBLIC_WEB_URL` — 연습장 등을 브라우저로 열 주소

폰과 PC는 같은 와이파이에 있어야 합니다. API 서버:

```bash
cd lms_api
python manage.py runserver 0.0.0.0:8000
```

`ALLOWED_HOSTS`에 PC IP를 넣고, 웹 주소가 바뀌면 `CORS_ALLOWED_ORIGINS`와 `CSRF_TRUSTED_ORIGINS`도 환경 변수로 맞춥니다. 기본값은 로컬 Vite(`http://127.0.0.1:5173`)입니다.

## 빌드

미리보기 APK:

```bash
npx eas-cli login
npx eas-cli build -p android --profile preview
```

스토어 제출은 `eas.json`의 `production` 프로필로 `eas build` 한 뒤 `eas submit` 합니다. 운영 API는 HTTPS여야 합니다.

## 같이 쓰는 코드

`metro.config.js`가 `@web/*`를 `lms_react/src`로 연결합니다. 도메인 타입, bootstrap 매핑, 공고 본문 정리처럼 브라우저 API가 없는 모듈만 가져옵니다.
