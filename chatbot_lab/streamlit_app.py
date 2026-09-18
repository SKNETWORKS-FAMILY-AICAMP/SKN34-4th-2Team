"""운영 사이트와 연결되지 않는 Luna 사용자 챗봇 비교 화면."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from chatbot_lab.bot import LAB_MODEL, LAB_REVISION
from chatbot_lab.comparison import compare, create_pair
from chatbot_lab.firebase_loader import create_firebase_student_loader

RESULTS_DIR = Path(__file__).with_name("results")


@st.cache_resource
def _bots(data_source: str, identifier: str, revision: str):
    if data_source == "실제 Firebase":
        loader, uid, cohort = create_firebase_student_loader(identifier)
        return create_pair(loader), uid, cohort
    return create_pair(), "mock-student-001", ""


def _reset() -> None:
    st.session_state.thread_id = uuid.uuid4().hex
    st.session_state.turns = []


def _render_result(result: dict[str, Any]) -> None:
    st.markdown(f"#### {result['variant']}")
    st.caption(f"모델 {LAB_MODEL} · {result['elapsed_ms']:,}ms")
    st.markdown(result.get("answer") or "응답 없음")
    with st.expander("라우팅 및 검색 정보", expanded=True):
        st.write("Route", result.get("route"))
        st.write("Namespaces", result.get("namespaces") or [])
        st.write("Student scopes", result.get("student_scopes") or [])
        st.write("재작성 검색어", result.get("query") or "")
        sources = result.get("sources") or []
        st.write("근거 문서 수", len(sources))
        for index, source in enumerate(sources, 1):
            st.caption(
                f"{index}. {source.get('title') or source.get('doc_id') or '제목 없음'} "
                f"[{source.get('namespace') or '-'}]"
            )


def _save_judgement(turn: dict[str, Any], winner: str, note: str) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "saved_at": datetime.now().astimezone().isoformat(),
        "winner": winner,
        "note": note.strip(),
        **turn,
    }
    with (RESULTS_DIR / "comparisons.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


st.set_page_config(page_title="학생 챗봇 Luna Lab", page_icon="🧪", layout="wide")
st.title("🧪 학생 챗봇 Luna 비교 Lab")
st.caption("왼쪽은 기존 구조, 오른쪽은 개선 구조입니다. 두 화면 모두 Luna만 사용합니다.")
st.warning("운영 사이트·통합 서버와 연결되지 않은 로컬 실험 화면입니다.")

if "thread_id" not in st.session_state:
    _reset()

with st.sidebar:
    st.subheader("실험 설정")
    mode = st.radio("평가 범위", ["Supervisor만", "전체 답변"], index=0)
    data_source = st.radio("학생 데이터", ["목업 데이터", "실제 Firebase"], index=0)
    if data_source == "실제 Firebase":
        student_identifier = st.text_input(
            "학생 UID 또는 이메일",
            type="password",
            help="Flutter가 사용하는 Firebase 프로젝트에서 이 학생 한 명만 조회합니다.",
        )
        cohort = ""
        st.warning("실제 학생 데이터는 화면에서만 확인하며 비교 결과 파일에는 저장하지 않습니다.")
    else:
        student_identifier = ""
        cohort = st.text_input("테스트 기수", value="cohort_34")
        st.info("개인 데이터 질문에는 lab의 익명 원시 fixture를 사용합니다.")
    st.caption("전체 답변은 양쪽에서 Pinecone 검색과 Luna 답변 생성을 실행합니다.")
    if st.button("대화 초기화", use_container_width=True):
        _reset()
        st.rerun()

source_key = f"{data_source}:{student_identifier}"
if st.session_state.get("source_key") != source_key:
    _reset()
    st.session_state.source_key = source_key

for index, turn in enumerate(st.session_state.turns):
    st.chat_message("user").write(turn["question"])
    left_col, right_col = st.columns(2)
    with left_col:
        _render_result(turn["left"])
    with right_col:
        _render_result(turn["right"])
    with st.expander("이 결과 평가하기"):
        winner = st.radio(
            "더 나은 결과",
            ["기존 구조", "비슷함", "개선 구조", "둘 다 문제"],
            horizontal=True,
            key=f"winner-{index}",
        )
        note = st.text_input("판정 메모", key=f"note-{index}")
        if turn.get("data_source") == "실제 Firebase":
            st.caption("실제 학생 데이터가 포함될 수 있어 이 결과는 파일로 저장하지 않습니다.")
        elif st.button("평가 저장", key=f"save-{index}"):
            _save_judgement(turn, winner, note)
            st.success("chatbot_lab/results에 저장했습니다.")

question = st.chat_input("두 Luna 챗봇에 같은 질문 보내기")
if question:
    with st.spinner("두 실험군을 동시에 실행하고 있습니다..."):
        try:
            pair, student_uid, firebase_cohort = _bots(
                data_source, student_identifier, LAB_REVISION,
            )
            active_cohort = firebase_cohort or cohort.strip()
            if active_cohort.isdigit():
                active_cohort = f"cohort_{active_cohort}"
            recent_turns = st.session_state.turns[-4:]
            left_history = []
            right_history = []
            for turn in recent_turns:
                left_history.extend(
                    [
                        {"role": "user", "content": turn["question"]},
                        {"role": "assistant", "content": turn["left"].get("answer", "")},
                    ]
                )
                right_history.extend(
                    [
                        {"role": "user", "content": turn["question"]},
                        {"role": "assistant", "content": turn["right"].get("answer", "")},
                    ]
                )
            left, right = compare(
                pair,
                question=question,
                thread_id=st.session_state.thread_id,
                cohort=active_cohort,
                left_history=left_history,
                right_history=right_history,
                supervisor_only=mode == "Supervisor만",
                student_uid=student_uid,
            )
            st.session_state.turns.append(
                {
                    "question": question,
                    "mode": mode,
                    "cohort": active_cohort,
                    "data_source": data_source,
                    "left": left,
                    "right": right,
                }
            )
            st.rerun()
        except Exception as error:
            st.error(f"비교 실행 실패: {type(error).__name__}: {error}")
