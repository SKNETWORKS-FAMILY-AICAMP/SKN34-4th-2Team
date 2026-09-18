# SKN34-4th-2Team

SK네트웍스 Family AI 캠프 34기 4차 프로젝트 - 2팀

## 브랜치 전략

| 브랜치 | 용도 |
| --- | --- |
| `main` | 배포/릴리스 기준. 직접 커밋하지 않고 `develop`에서만 머지 |
| `develop` | 통합 개발 브랜치. 모든 `feature/*`가 여기로 머지 |
| `feature/*` | 기능 단위 작업 브랜치. `develop`에서 분기 |

### 작업 흐름

```bash
git switch develop
git pull origin develop

git switch -c feature/<작업명>
# ... 작업 및 커밋 ...
git push -u origin feature/<작업명>
# GitHub에서 develop 으로 Pull Request
```

## 커밋 컨벤션

```
<type>: <제목>
```

`feat` / `fix` / `docs` / `refactor` / `test` / `chore`
