"""웹용 가상 이력서(scripts/resume_mocks.json)를 Flutter가 읽는 Dart 모듈로 내보낸다.

앱 안의 "목업 채우기" 메뉴가 이 파일을 읽는다. JSON을 assets로 묶으면 pubspec
설정과 비동기 로딩이 필요하고, Dart에 손으로 옮기면 시드 스크립트가 쓰는
JSON과 갈라진다. 그래서 `collected_jobs.g.dart`와 같은 방식으로 생성한다.

JSON 객체 리터럴은 Dart 맵 리터럴과 거의 같지만 `$`가 다르다. Dart 문자열에서
`$`는 보간이라 반드시 `\\$`로 이스케이프해야 한다.
"""

from __future__ import annotations

import json
from typing import Any

GENERATED_HEADER = """// 이 파일은 자동 생성됩니다. 직접 수정하지 마세요.
// 다시 만들려면 레포 루트에서 실행하세요:
//   python -m job_matching_bot
//
// 원본: scripts/resume_mocks.json
"""


def _dart_literal(value: Any, indent: int) -> str:
    """JSON 값을 Dart 리터럴로. 문자열의 `$`만 Dart 규칙에 맞게 처리한다."""
    pad = "  " * indent
    inner = "  " * (indent + 1)
    if isinstance(value, dict):
        if not value:
            return "<String, dynamic>{}"
        items = [
            f"{inner}{json.dumps(key, ensure_ascii=False)}: {_dart_literal(item, indent + 1)},"
            for key, item in value.items()
        ]
        return "<String, dynamic>{\n" + "\n".join(items) + f"\n{pad}}}"
    if isinstance(value, list):
        if not value:
            return "<dynamic>[]"
        items = [f"{inner}{_dart_literal(item, indent + 1)}," for item in value]
        return "<dynamic>[\n" + "\n".join(items) + f"\n{pad}]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(value, ensure_ascii=False).replace("$", r"\$")


def build_resume_mocks_module(mocks: dict[str, Any]) -> str:
    """resume_mocks.json 내용을 `resume_mocks.g.dart` 문자열로 만든다."""
    entries = []
    for key, persona in mocks["personas"].items():
        entries.append(
            "  ResumeMockPersona(\n"
            f"    key: {json.dumps(key)},\n"
            f"    title: {_dart_literal(persona['title'], 2)},\n"
            f"    content: {_dart_literal(persona['content'], 2)},\n"
            "  ),"
        )
    body = "\n".join(entries)
    return (
        f"{GENERATED_HEADER}\n"
        "import '../../models/resume_mock_persona.dart';\n\n"
        "const resumeMockPersonas = <ResumeMockPersona>[\n"
        f"{body}\n"
        "];\n"
    )


def main() -> int:
    """`scripts/resume_mocks.json` → 앱의 `resume_mocks.g.dart`.

        python -m job_matching_bot.exporters.resume_mocks_dart
    """
    import argparse
    import sys
    from pathlib import Path

    from job_matching_bot.config import (
        DEFAULT_RESUME_MOCKS_DART_OUTPUT,
        DEFAULT_RESUME_MOCKS_INPUT,
    )

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="이력서 목업 → Dart 생성 파일")
    parser.add_argument("--input", type=Path, default=DEFAULT_RESUME_MOCKS_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESUME_MOCKS_DART_OUTPUT)
    args = parser.parse_args()

    mocks = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_resume_mocks_module(mocks), encoding="utf-8")
    print(f"{len(mocks['personas'])}명 → {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
