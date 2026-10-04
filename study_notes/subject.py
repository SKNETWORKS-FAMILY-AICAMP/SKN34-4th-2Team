"""과목 전체 요약 — 수업 파일을 직접 읽어 주제(맨 위 폴더)별로 한 장에 정리한다.

예전엔 날짜 노트를 모아 다시 요약했다. 날짜 노트가 날마다 6천 자에서 잘려 뒤 내용이 빠졌고, 날짜 노트가 없으면 그것부터
만들어야 해서 오래 걸렸고, 같은 주제가 며칠에 걸치면 날짜별로 흩어졌다(python_basic 세 방식 비교에서 파일 직접 · 주제별이 가장
나았다). 날짜 없이 폴더로 올린 지난 자료도 파일은 있으니 요약된다.

- 주제 = 저장소 맨 위 폴더(01_variable · 04_function …). 맨 위 파일은 「맨 위 파일」 한 주제로.
- 주제마다 배운 날짜 = 그 폴더 파일이 바뀐 수업 날짜(지난 자료는 날짜 없음).
- 자료가 많으면 주제를 묶음으로 나눠 묶음마다 「주제별 핵심 정리」만 만들고(주제가 묶음끼리 겹치지 않아 그대로 이어 붙인다),
  마지막에 한 번 더 불러 과목 전체를 아우르는 소제목(한눈에 · 흐름 · 비교 · 실수 …)을 쓴다.
- 코드 블록은 수업 자료 그대로 — 날짜 노트처럼 대조(grounding)한다.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from langchain_core.prompts import ChatPromptTemplate

from study_notes.git_tools import RepoCache, _day_of, is_learning_file
from study_notes.grounding import ground_report
from study_notes.pipeline import (
    LEARNER_LEVEL,
    Material,
    _llm,
    _split_report_and_review,
    pack_materials,
    response_text,
)

ROOT_TOPIC = "맨 위 파일"
# 한 번에 넣는 자료 — 이보다 많으면 주제 묶음으로 나눈다. 묶음은 동시에 SUBJECT_WORKERS 개
SUBJECT_BATCH_CHARS = 40_000
SUBJECT_WORKERS = 4
MAX_SUBJECT_FILES = 200

SUBJECT_HEADS = (
    "과목 한눈에 보기", "수업 흐름", "주제별 핵심 정리", "비교로 기억하기", "자주 하는 실수", "말로 설명해 보기", "이어서 공부할 것",
)
TOPIC_HEAD = "주제별 핵심 정리"
GUIDE = {
    "과목 한눈에 보기": "이 과목에서 배운 것을 세 문장 안으로",
    "수업 흐름": "표 하나 — | 날짜 | 다룬 주제 |. 날짜가 없는 주제(지난 자료)는 날짜 칸에 '지난 자료'",
    TOPIC_HEAD: (
        "위 「주제」 목록의 `###` 줄을 주제 소제목으로 글자 그대로, 같은 순서로 쓴다(이름을 바꾸거나 한 주제를 여러 ### 로 나누지 않는다). "
        "그 아래 핵심 개념을 글머리표로 — 핵심어는 굵게, 개념마다 한두 문장. 주제 안의 작은 개념이 많으면 `####` 소제목으로 묶는다. "
        "꼭 기억할 코드가 있으면 주제마다 한 블록까지, 수업 자료 코드를 그대로 옮기고 바로 위 줄에 출처 경로를 백틱으로"
    ),
    "비교로 기억하기": "과목 안에서 짝지어 볼 만한 것이 있을 때만 표로(행 2~8개). 없으면 소제목을 쓰지 않는다",
    "자주 하는 실수": "수업 자료에 나온 오류 예시 · 주의할 점만, 한 줄씩. 없으면 소제목을 쓰지 않는다",
    "말로 설명해 보기": "과목 전체를 돌아보는 질문 4~6개(답은 쓰지 않는다)",
    "이어서 공부할 것": "이 과목 다음에 스스로 더 볼 것 2~4줄 — 수업 자료에서 이어지는 것만",
}
SYSTEM = (
    "당신은 AI 부트캠프 한 과목의 수업을 한 장의 공부 노트로 정리하는 교육 전문가입니다.\n"
    "날짜가 아니라 주제(폴더) 단위로 묶습니다. 한 주제가 여러 날에 걸쳤으면 한곳에 모읍니다.\n"
    "주어진 자료에 없는 내용은 지어내지 마세요. 문제와 정답은 넣지 마세요.\n"
    "모든 문장은 「~습니다 · ~합니다」체로 씁니다. 문장은 짧게, 핵심어는 굵게.\n"
    "소제목은 아래 목록의 것만 `##` 로 쓰고, 첫 소제목 앞에 아무것도 쓰지 마세요. git 커밋 해시는 쓰지 마세요."
)


def _heads(heads: tuple[str, ...]) -> str:
    return "\n".join(f"## {h}\n({GUIDE[h]})" for h in heads)


WHOLE = ChatPromptTemplate.from_messages([
    ("system", SYSTEM),
    ("human", "과목: {subject}\n학습자 수준: {learner_level}\n\n주제(배운 날짜 · 파일):\n{topics}\n\n"
              "수업 파일(주제 순서):\n{materials}\n\n아래 소제목 순서대로 한국어 Markdown 으로 작성하세요. 괄호 안은 쓰는 법이니 옮겨 적지 마세요.\n\n"
              + _heads(SUBJECT_HEADS)),
])
TOPICS_ONLY = ChatPromptTemplate.from_messages([
    ("system", SYSTEM),
    ("human", "과목: {subject}\n학습자 수준: {learner_level}\n\n이번에 정리할 주제(배운 날짜 · 파일):\n{topics}\n\n"
              "수업 파일:\n{materials}\n\n과목 자료가 많아 주제를 나눠 정리합니다. 아래 소제목 하나만 쓰세요 — 위 주제만, 주제 순서대로.\n\n"
              + _heads((TOPIC_HEAD,))),
])
OVERVIEW = ChatPromptTemplate.from_messages([
    ("system", SYSTEM),
    ("human", "과목: {subject}\n학습자 수준: {learner_level}\n\n주제(배운 날짜 · 파일):\n{topics}\n\n"
              "주제별 핵심 정리(이미 썼습니다):\n{sections}\n\n위 정리를 보고 과목 전체를 아우르는 소제목만 쓰세요. "
              "주제별 핵심 정리는 다시 쓰지 마세요.\n\n" + _heads(tuple(h for h in SUBJECT_HEADS if h != TOPIC_HEAD))),
])


@dataclass
class Topic:
    name: str
    dates: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    @property
    def heading(self) -> str:
        """주제 소제목 — 코드가 정해 모델이 그대로 쓴다(모델에 맡기면 폴더를 개념마다 ### 로 쪼갰다, LLM파트 05_langchain)"""
        if not self.dates:
            return f"### {self.name} · 지난 자료"
        when = f"{_short(self.dates[0])}~{_short(self.dates[-1])}" if len(self.dates) > 1 else _short(self.dates[0])
        return f"### {self.name} · {when}"

    def line(self) -> str:
        return f"{self.heading}\n  파일: {', '.join(p.split('/', 1)[-1] for p in self.files)}"


def _short(day: str) -> str:
    return f"{int(day[5:7])}/{int(day[8:10])}"


def _natural(text: str) -> list:
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text.lower())]


def subject_topics(cache: RepoCache, prefixes: list[str]) -> tuple[list[Topic], list[str], str]:
    """(주제들, 수업 날짜 전부, 읽을 커밋). 주제 = 맨 위 폴더, 날짜 = 그 폴더 파일이 바뀐 수업 날짜"""
    head = cache.sync()
    files = cache.list_tree(prefixes)[:MAX_SUBJECT_FILES]
    by_topic: dict[str, Topic] = {}
    for path in files:
        name = path.split("/", 1)[0] if "/" in path else ROOT_TOPIC
        by_topic.setdefault(name, Topic(name)).files.append(path)
    dates: set[str] = set()
    for _sha, iso, changed in cache._log_with_files([]):  # 지난 자료 커밋은 여기서 빠진다(수업 날이 아니다)
        day = _day_of(iso)
        if not day or not any(is_learning_file(p) for p in changed):
            continue
        dates.add(day)
        for path in changed:
            name = path.split("/", 1)[0] if "/" in path else ROOT_TOPIC
            if name in by_topic and day not in by_topic[name].dates:
                by_topic[name].dates.append(day)
    topics = sorted(by_topic.values(), key=lambda t: (t.name == ROOT_TOPIC, _natural(t.name)))
    for t in topics:
        t.dates.sort()
    return topics, sorted(dates), head


def _batches(topics: list[Topic], materials: dict[str, Material]) -> list[list[Topic]]:
    """주제를 순서대로 묶는다 — 묶음마다 자료가 SUBJECT_BATCH_CHARS 를 넘지 않게(한 주제가 크면 그 주제 혼자)"""
    out: list[list[Topic]] = [[]]
    size = 0
    for t in topics:
        chars = sum(len(materials[p]["content"]) for p in t.files if p in materials)
        if out[-1] and size + chars > SUBJECT_BATCH_CHARS:
            out.append([])
            size = 0
        out[-1].append(t)
        size += chars
    return [b for b in out if b]


def _pack(batch: list[Topic], materials: dict[str, Material]) -> str:
    return pack_materials([materials[p] for t in batch for p in t.files if p in materials], budget=SUBJECT_BATCH_CHARS)


def _sections(markdown: str) -> dict[str, str]:
    out: dict[str, str] = {}
    current = ""
    for line in markdown.split("\n"):
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match and match.group(1) in SUBJECT_HEADS:
            current = match.group(1)
            out.setdefault(current, "")
            continue
        if current:
            out[current] += line + "\n"
    return {k: v.strip() for k, v in out.items()}


def _invoke(prompt: ChatPromptTemplate, **values: str) -> str:
    report, _review = _split_report_and_review(response_text((prompt | _llm()).invoke({"learner_level": LEARNER_LEVEL, **values})))
    return report


def fix_topic_headings(report: str, topics: list[Topic]) -> str:
    """주제 목록에 없는 ### 는 한 단계 아래(####)로 — 모델이 주제를 개념마다 ### 로 쪼개도 주제 뼈대가 남게"""
    allowed = {t.heading for t in topics}
    return "\n".join(f"#{line}" if line.startswith("### ") and line.rstrip() not in allowed else line for line in report.split("\n"))


def topic_blocks(text: str, topics: list[Topic]) -> dict[str, str]:
    """모델 답 → {주제 소제목: 그 주제 글}. 정해진 소제목이 아닌 ### 는 먼저 ####로 내린다.
    「## 주제별 핵심 정리」 아래만 보지 않고 답 전체에서 찾는다 — 모델이 그 ## 줄을 빼먹고 바로 ### 주제부터 쓰면 주제가 통째로
    빠졌다(LLM파트 10_sllm_finetuning). 다른 ## 소제목을 만나면 주제 글이 끝난다."""
    allowed = {t.heading for t in topics}
    blocks: dict[str, list[str]] = {}
    current = ""
    for line in fix_topic_headings(text, topics).split("\n"):
        if line.rstrip() in allowed:
            current = line.rstrip()
            blocks.setdefault(current, [])
            continue
        if line.startswith("## "):
            current = ""
            continue
        if current:
            blocks[current].append(line)
    return {h: "\n".join(lines).strip() for h, lines in blocks.items() if "\n".join(lines).strip()}


def _topics_part(subject: str, batch: list[Topic], by_path: dict[str, Material]) -> dict[str, str]:
    report = _invoke(TOPICS_ONLY, subject=subject, topics="\n".join(t.line() for t in batch), materials=_pack(batch, by_path))
    return topic_blocks(report, batch)


def generate_subject_from_files(*, subject: str, topics: list[Topic], materials: list[Material]) -> tuple[str, str]:
    """(과목 요약 Markdown, 대조 결과 한 줄). 자료가 적으면 LLM 1회, 많으면 주제 묶음 수 + 1회.
    빠진 주제가 있으면 그 주제만 한 번 더 불러 채운다(LLM파트 묶음 하나가 06_2stage_rag 를 통째로 빠뜨렸다)."""
    if not materials:
        raise ValueError("요약할 수업 파일이 없습니다.")
    by_path = {m["path"]: m for m in materials}
    batches = _batches(topics, by_path)
    topic_text = "\n".join(t.line() for t in topics)
    packs = [_pack(b, by_path) for b in batches]
    if len(batches) == 1:
        raw = _invoke(WHOLE, subject=subject, topics=topic_text, materials=packs[0])
        whole = _sections(raw)
        blocks = topic_blocks(raw, topics)
    else:
        with ThreadPoolExecutor(max_workers=min(SUBJECT_WORKERS, len(batches))) as pool:
            parts = list(pool.map(lambda b: _topics_part(subject, b, by_path), batches))
        blocks = {h: body for part in parts for h, body in part.items()}
        whole = None
    missing = [t for t in topics if t.heading not in blocks]
    for batch in _batches(missing, by_path) if missing else []:
        blocks.update(_topics_part(subject, batch, by_path))
    topic_section = "\n\n".join(f"{t.heading}\n{blocks[t.heading]}" for t in topics if t.heading in blocks)
    if whole is None:
        whole = _sections(_invoke(OVERVIEW, subject=subject, topics=topic_text, sections=topic_section))
    whole[TOPIC_HEAD] = topic_section
    report = "\n\n".join(f"## {h}\n{whole[h]}" for h in SUBJECT_HEADS if whole.get(h))
    report, stats = ground_report(report, "\n\n".join(packs))
    left = [t.name for t in topics if t.heading not in blocks]
    return report, stats.summary() + (f" · 끝내 못 채운 주제 {left}" if left else "")
