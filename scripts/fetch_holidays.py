"""공휴일 표를 새로 만든다.

공공데이터포털 특일 정보(한국천문연구원)에서 받아
`lib/core/constants/korean_holidays.dart`를 다시 쓴다.

    python scripts/fetch_holidays.py                # 2026~2030
    python scripts/fetch_holidays.py 2026 2032      # 범위를 직접

자격 시험 일정 Functions도 같은 포털 키를 쓰지만 이름이 `DATA_GO_KR_SERVICE_KEY`로
다르다. **일부러 합치지 않는다.** 그쪽은 담당이 다르고, 이름을 합치면 여태 비어 있던
그 설정이 이 저장소에서 켜져 버린다. 값은 같아도 줄은 따로 둔다.

**앱이 실행 중에 이 API를 부르지 않는다.** 달력은 만들어진 표만 읽는다.
키를 앱에 넣지 않아도 되고, 네트워크가 없어도 공휴일 색이 나온다. 대신
임시공휴일이 새로 지정되면 이 명령을 다시 돌리고 결과를 커밋해야 한다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import unquote

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "lib" / "core" / "constants" / "korean_holidays.dart"
URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"


def fetch_year(key: str, year: int) -> list[tuple[str, str]]:
    """그 해의 (YYYY-MM-DD, 이름). 쉬는 날만 고른다."""
    response = requests.get(
        URL,
        params={"serviceKey": key, "solYear": year, "_type": "json", "numOfRows": 100},
        timeout=30,
    )
    if response.status_code != 200:
        # 응답 본문에는 키가 그대로 실려 온다. 상태 코드만 남긴다.
        raise SystemExit(f"{year}년 조회 실패: HTTP {response.status_code}")
    body = response.json()["response"]["body"]
    if not body.get("totalCount"):
        return []
    items = body["items"]["item"]
    # 한 건만 있으면 리스트가 아니라 객체로 온다.
    if isinstance(items, dict):
        items = [items]
    # 하루에 이름이 둘일 수 있다. 2028-10-03은 개천절이면서 추석이다.
    # 달력은 색만 칠하므로 이름은 겹쳐 적고 날짜는 하나만 남긴다.
    days: dict[str, list[str]] = {}
    for item in items:
        # 기념일·절기도 같은 창구로 오므로 실제로 쉬는 날만 남긴다.
        if item.get("isHoliday") != "Y":
            continue
        date = str(item["locdate"])
        key = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        name = str(item["dateName"])
        if name not in days.setdefault(key, []):
            days[key].append(name)
    return sorted((key, "·".join(names)) for key, names in days.items())


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    key = os.getenv("DATA_GO_KR_API_KEY")
    if not key:
        print("DATA_GO_KR_API_KEY가 없습니다. 저장소 루트 .env에 넣어 주세요.")
        return 1
    # 포털은 인코딩 키와 디코딩 키를 둘 다 준다. 인코딩된 것을 그대로 넘기면
    # requests가 한 번 더 인코딩해 `%2F`가 `%252F`가 되고 403이 돌아온다.
    key = unquote(key.strip().strip('"').strip("'"))

    start = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 2030

    rows: list[tuple[str, str]] = []
    for year in range(start, end + 1):
        found = fetch_year(key, year)
        print(f"  {year} {len(found)}일")
        rows.extend(found)

    if not rows:
        print("받은 날이 없습니다. 표를 덮어쓰지 않았습니다.")
        return 1

    years = sorted({date[:4] for date, _ in rows})
    lines = [
        "// 공공데이터포털 특일 정보(한국천문연구원)로 만든 표. 손으로 고치지 않는다.",
        "//",
        "// 다시 만들려면: python scripts/fetch_holidays.py",
        f"// 담고 있는 해: {years[0]}~{years[-1]} (그 뒤는 아직 고시 전이라 비어 있다)",
        "library;",
        "",
        "/// 쉬는 날과 그 이름. 날짜는 `YYYY-MM-DD`.",
        "const koreanHolidays = <String, String>{",
    ]
    lines += [f"  '{date}': '{name}'," for date, name in sorted(rows)]
    lines += ["};", ""]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)}일 → {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
