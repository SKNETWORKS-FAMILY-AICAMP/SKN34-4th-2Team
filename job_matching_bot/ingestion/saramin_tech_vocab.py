"""사람인 직무 코드표로 태그를 분류한다.

사람인은 분류 체계가 하나뿐이다. 대분류(IT개발·데이터 등) 밑에 축(`scls`:
직무·직업 / 전문분야 / 기술스택 / 작업Tool …)이 있고, 그 밑에 키워드 코드가
있다. 기업이 공고 등록 때 고르는 것도, 상세 페이지 해시태그도, 사람인 API의
`job-code`도 전부 이 코드다. 별도의 "기술스택 필드"는 없다 — **기술스택은 이
코드표의 한 축**이다.

코드표는 `fixtures/saramin_job_codes.json`에 있다(목록 페이지에 내장된 JSON을
그대로 저장한 것, 2,178개). 손으로 만든 어휘 대신 이 표를 읽는다.

태그 하나를 넣으면 축을 돌려주고, 기술로 볼지는 축으로 정한다:

- `기술스택` 축 (IT, 140개)          → 기술
- `작업Tool`/`작업도구` 축의 소프트웨어 → 기술 (Figma, CAD …; 크레인·용접기 같은 장비는 제외)
- `전문분야` 중 `FIELD_AS_TECH` 허용 목록 → 기술 (SAP, DevOps, 펌웨어처럼 이력서에 기술로 적는 것)
- 그 밖(직무·직업, 나머지 전문분야, 지역 …) → 키워드
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from job_matching_bot.config import REPO_ROOT
from job_matching_bot.matching.skill_normalize import canonical_skill

CODES_PATH = REPO_ROOT / "job_matching_bot" / "fixtures" / "saramin_job_codes.json"

AXIS_TECH_STACK = "기술스택"
AXIS_FIELD = "전문분야"
AXIS_ROLE = "직무·직업"
TOOL_AXES = ("작업Tool", "작업도구")

# 전문분야 축이지만 이력서에 "기술"로 적는 것들. 산업·도메인 용어(핀테크, 헬스케어,
# 네트워크, 정보보안 …)는 키워드로 남긴다. 표에 없는 이름을 적으면 테스트가 잡는다.
FIELD_AS_TECH = frozenset({
    "API", "DBMS", "RDBMS", "DW", "OLAP", "ETL", "DevOps", "ERP", "SAP", "RPA", "SDK",
    "RTOS", "MCU", "FPGA", "IoT", "펌웨어", "임베디드",
    "Nginx", "IIS", "VMware", "VDI", "VPN", "WCF", "SOA", "HTTP", "Windows",
    "딥러닝", "머신러닝", "신경망", "컴퓨터비전", "영상처리", "이미지프로세싱",
    "NLP(자연어처리)", "NLU(자연어이해)", "OCR", "STT", "TTS", "음성인식", "챗봇",
    "빅데이터", "데이터마이닝", "텍스트마이닝", "데이터시각화", "데이터라벨링",
    "클라우드", "블록체인", "크롤링", "GIS", "3D", "루비온레일즈",
})

# 작업Tool/작업도구 축에서 기술로 볼 소프트웨어. 장비(크레인·용접기·프레스)는 뺀다.
TOOL_AS_TECH = frozenset({
    "CAD", "CAM", "Revit", "Navisworks", "3DMax", "Blender", "Cinema4D", "Maya",
    "Figma", "Sketch", "XD", "Zeplin", "PhotoShop", "일러스트", "인디자인", "애프터이펙트",
    "프리미어", "파이널컷", "베가스", "Unity", "Unreal", "V-Ray", "Keyshot", "Substance",
    "지브러쉬", "라이노", "스케치업", "HTML", "FLEX", "PLC",
})


@lru_cache(maxsize=1)
def load_codes() -> list[dict]:
    """코드표 전체(모든 대분류)."""
    return json.loads(Path(CODES_PATH).read_text(encoding="utf-8"))["rows"]


@lru_cache(maxsize=1)
def _axis_by_key() -> dict[str, str]:
    """표준 키 → 축. 같은 이름이 여러 대분류에 있으면 IT개발·데이터(2)를 우선한다."""
    axis: dict[str, str] = {}
    for row in sorted(load_codes(), key=lambda r: (r["mcls_code"] != 2, r["mcls_code"])):
        key = canonical_skill(row["kewd_name"])
        axis.setdefault(key, row["scls_name"])
    return axis


@lru_cache(maxsize=1)
def _tech_keys() -> frozenset[str]:
    keys = set()
    for row in load_codes():
        name, axis = row["kewd_name"], row["scls_name"]
        if (
            axis == AXIS_TECH_STACK
            or (axis == AXIS_FIELD and name in FIELD_AS_TECH)
            or (axis in TOOL_AXES and name in TOOL_AS_TECH)
        ):
            keys.add(canonical_skill(name))
    return frozenset(keys)


def axis_of(tag: str) -> str | None:
    """태그가 코드표의 어느 축인지. 표에 없으면 None (지역 태그 등)."""
    return _axis_by_key().get(canonical_skill(tag.lstrip("#")))


def is_tech_tag(tag: str) -> bool:
    """태그 하나를 기술로 볼지. 표기 변형(ReactJS/React)은 같은 키로 본다."""
    key = canonical_skill(tag.lstrip("#"))
    return bool(key) and key in _tech_keys()


def split_tags(tags: list[str]) -> tuple[list[str], list[str]]:
    """(기술 태그, 그 밖의 태그)로 나눈다. 순서를 유지하고 표기 변형은 하나로 접는다."""
    tech: dict[str, str] = {}
    other: list[str] = []
    for raw in tags:
        tag = raw.lstrip("#").strip()
        if not tag:
            continue
        if is_tech_tag(tag):
            tech.setdefault(canonical_skill(tag), tag)
        elif tag not in other:
            other.append(tag)
    return list(tech.values()), other


# 글에서 찾을 때 뺄 키. 한두 글자라 다른 말에 섞여 잡힌다(`C`, `R`은 이미 한 글자라 빠진다).
_AMBIGUOUS_IN_TEXT = frozenset({"go", "3d", "dw", "xd"})
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*|[가-힣]+")


@lru_cache(maxsize=1)
def _korean_keys() -> tuple[str, ...]:
    return tuple(sorted((k for k in _tech_keys() if re.match(r"[가-힣]", k)), key=len, reverse=True))


def find_tech_in_text(text: str) -> list[str]:
    """글에 적힌 기술을 코드표 어휘로 찾는다. 표준 키를 나온 순서대로 돌려준다.

    태그를 안 단 공고가 많다(기술 정보가 없는 OPEN 공고 22,383건). 그중 요건 구간에
    기술을 글로 적어 둔 것이 5,276건이다. 태그와 같은 어휘로 찾으므로 태그가 있는
    공고와 같은 기준으로 겹침을 잴 수 있다.

    낱말 단위로 맞춘다. 영문은 한 낱말이나 두 낱말(`Spring Boot`)을, 한글은 조사가
    붙어도(`클라우드를`) 앞부분이 어휘와 같으면 잡는다.
    """
    tokens = _TOKEN.findall(text or "")
    keys = _tech_keys()
    found: list[str] = []

    def add(key: str) -> None:
        if len(key) >= 2 and key not in _AMBIGUOUS_IN_TEXT and key not in found:
            found.append(key)

    for i, token in enumerate(tokens):
        if "가" <= token[0] <= "힣":
            prefix = next((k for k in _korean_keys() if token.startswith(k)), None)
            if prefix:
                add(prefix)
            continue
        pair = f"{token} {tokens[i + 1]}" if i + 1 < len(tokens) else ""
        for candidate in (pair, token, token.rstrip(".-")):
            key = canonical_skill(candidate) if candidate else ""
            if key in keys:
                add(key)
                break
    return found


def tech_stack_codes() -> dict[str, int]:
    """IT 기술스택 축의 이름 → cat_kewd 코드. 기술별 수집(`--cat-kewd`)에 쓴다."""
    return {
        row["kewd_name"]: row["kewd_code"]
        for row in load_codes()
        if row["mcls_code"] == 2 and row["scls_name"] == AXIS_TECH_STACK
    }
