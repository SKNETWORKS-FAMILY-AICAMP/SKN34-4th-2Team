"""원본 코드를 수정하지 않고 Luna 설정과 실험 프롬프트만 덧씌운 챗봇."""

from __future__ import annotations

import os
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any, Iterator, Sequence

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from pydantic import Field

from chatbot.student_chatbot import (
    ANSWER_PROMPT,
    LmsStudentChatbot,
    SUPERVISOR_PROMPT,
    StudentContextLoader,
    SupervisorDecision,
    MAX_SEARCH_K,
    _project_filter,
    _requested_k,
)
from chatbot_lab.prompts import LAB_ANSWER_PROMPT, LAB_SUPERVISOR_PROMPT
from chatbot_lab.routing import LabSupervisorGuardrail, bind_session_cohort_to_project_query
from chatbot_lab.attendance import enrich_student_context
from chatbot_lab.project_search import (
    cohort_buckets,
    cohort_range,
    diversify_by_cohort,
    neutralize_cohort_ranges,
)

LAB_MODEL = "gpt-5.6-luna"
LAB_REVISION = "project-range-diversity-v3"


class LabTask(SupervisorDecision):
    """복합 질문에서 독립적으로 조회할 한 가지 요청."""

    route: str = "lms"
    reason: str = ""


class LabSupervisorDecision(SupervisorDecision):
    tasks: list[LabTask] = Field(default_factory=list)


@contextmanager
def _luna_environment() -> Iterator[None]:
    """프로세스의 기존 모델 설정을 생성 중에만 보존하고 Luna로 고정한다."""
    names = ("LMS_SUPERVISOR_MODEL", "LMS_NODE_MODEL")
    previous = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            os.environ[name] = LAB_MODEL
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _model_name(llm: Any) -> str:
    return str(getattr(llm, "model_name", None) or getattr(llm, "model", ""))


def _assert_luna(llm: Any, role: str) -> None:
    actual = _model_name(llm)
    if actual != LAB_MODEL:
        raise RuntimeError(f"{role} 모델이 Luna가 아니어서 실험을 중단합니다: {actual or 'unknown'}")


class LunaLabStudentChatbot(LmsStudentChatbot):
    """원본 그래프를 사용하되 모든 LLM과 prompt를 실험 폴더에서 통제한다."""

    supervisor_prompt = LAB_SUPERVISOR_PROMPT
    variant_name = "개선 챗봇"

    def __init__(
        self,
        *,
        checkpointer: Any | None = None,
        k: int = 4,
        student_context_loader: StudentContextLoader | None = None,
    ) -> None:
        if not os.getenv("PINECONE_API_KEY2", "").strip():
            raise RuntimeError("실험판에는 PINECONE_API_KEY2가 필요합니다")
        with _luna_environment():
            super().__init__(
                checkpointer=checkpointer,
                k=k,
                student_context_loader=student_context_loader,
            )

        _assert_luna(self.supervisor_llm, "Supervisor")
        _assert_luna(self.node_llm, "답변 생성")

        self.supervisor_chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", self.supervisor_prompt),
                    MessagesPlaceholder("messages"),
                ]
            )
            | self.supervisor_llm.with_structured_output(SupervisorDecision)
        )
        self.answer_chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", ANSWER_PROMPT),
                    MessagesPlaceholder("history"),
                    ("human", "검색 문맥:\n{context}\n\n학생 질문: {question}"),
                ]
            )
            | self.node_llm
        )

    def classify_debug(
        self,
        question: str,
        *,
        cohort: str = "",
        history: Sequence[dict[str, str]] = (),
    ) -> dict[str, Any]:
        """검색·답변 생성 없이 실제 supervisor 노드의 최종 보정 결과를 반환한다."""
        messages: list[Any] = []
        for item in history:
            content = str(item.get("content", ""))
            messages.append(
                HumanMessage(content=content)
                if item.get("role") == "user"
                else AIMessage(content=content)
            )
        messages.append(HumanMessage(content=question))
        result = self._supervisor(
            {
                "question": question,
                "cohort": cohort,
                "messages": messages,
            }
        )
        return {
            key: result.get(key)
            for key in ("route", "namespaces", "student_scopes", "query")
        }

    def invoke_debug(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """실험 UI에 최종 답변과 중간 라우팅 정보를 함께 제공한다."""
        graph_input, config = self._prepare_call(inputs)
        state = self.graph.invoke(graph_input, config)
        return {
            key: state.get(key)
            for key in (
                "answer",
                "route",
                "namespaces",
                "student_scopes",
                "query",
                "sources",
            )
        }


class OriginalPromptLunaChatbot(LunaLabStudentChatbot):
    """팀원의 현재 구조·프롬프트를 유지하고 모델만 Luna로 고정한 기준선."""

    supervisor_prompt = SUPERVISOR_PROMPT
    variant_name = "기존 구조 (Luna)"


class ImprovedPromptLunaChatbot(LunaLabStudentChatbot):
    """실험 규칙을 적용해 계속 개선할 후보."""

    supervisor_prompt = LAB_SUPERVISOR_PROMPT
    variant_name = "개선 구조 (Luna)"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        base_student_loader = self.student_context_loader

        def improved_student_loader(
            uid: str, cohort: str, scopes: list[str], query: str,
        ) -> dict[str, Any]:
            return enrich_student_context(base_student_loader(uid, cohort, scopes, query))

        self.student_context_loader = improved_student_loader
        # 기준선(OriginalPromptLunaChatbot)은 팀원의 guardrail을 그대로 쓴다.
        # 이 보정은 개선 실험군에만 적용해야 A/B 비교가 성립한다.
        self.supervisor_middleware = LabSupervisorGuardrail(self.supervisor_middleware)
        self.supervisor_chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", self.supervisor_prompt),
                    MessagesPlaceholder("messages"),
                ]
            )
            | self.supervisor_llm.with_structured_output(LabSupervisorDecision)
        )
        # 운영 답변 규칙은 그대로 두고 개선판에만 정책-공지 충돌 판정을 실험한다.
        self.answer_chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", LAB_ANSWER_PROMPT),
                    MessagesPlaceholder("history"),
                    ("human", "검색 문맥:\n{context}\n\n학생 질문: {question}"),
                ]
            )
            | self.node_llm
        )

    def _supervisor(self, state: dict[str, Any]) -> dict[str, Any]:
        result = super()._supervisor(state)
        if result.get("answer"):
            return result
        namespaces = list(result.get("namespaces", []))
        result["query"] = bind_session_cohort_to_project_query(
            str(result.get("query", "")), str(state.get("cohort", "")), namespaces,
        )
        return result

    def _project_retrieve(self, state: dict[str, Any]) -> dict[str, Any]:
        """범위 질문은 끝 기수 하나로 오인하지 않고 구간별 후보를 모은다."""
        query = str(state.get("query", ""))
        bounds = cohort_range(query)
        if not bounds:
            return super()._project_retrieve(state)

        search_query = neutralize_cohort_ranges(query)
        vector = self.embeddings.embed_query(search_query)
        start, end = bounds
        buckets = cohort_buckets(start, end)
        round_filter = _project_filter(search_query)

        def search(bucket: list[str]) -> list[tuple[float, Document]]:
            cohort_filter: dict[str, Any] = {"cohort": {"$in": bucket}}
            metadata_filter = (
                {"$and": [cohort_filter, round_filter]}
                if round_filter else cohort_filter
            )
            response = self.index.query(
                vector=vector,
                top_k=3,
                namespace="project_reference",
                filter=metadata_filter,
                include_metadata=True,
                include_values=False,
            )
            found: list[tuple[float, Document]] = []
            for match in response.matches:
                metadata = dict(match.metadata or {})
                page_content = str(metadata.pop("page_content", "")).strip()
                if page_content:
                    metadata["_namespace"] = "project_reference"
                    found.append((
                        float(getattr(match, "score", 0.0) or 0.0),
                        Document(id=str(match.id), page_content=page_content, metadata=metadata),
                    ))
            return found

        with ThreadPoolExecutor(max_workers=min(len(buckets), 8)) as executor:
            grouped = list(executor.map(search, buckets))
        ranked = sorted(
            (candidate for group in grouped for candidate in group),
            key=lambda candidate: candidate[0],
            reverse=True,
        )
        requested = _requested_k(query, min(self.k * 2, MAX_SEARCH_K))
        matches = diversify_by_cohort((document for _, document in ranked), requested)

        documents = list(state.get("documents", []))
        seen = {
            (str(doc.metadata.get("_namespace", "")), str(doc.metadata.get("doc_id", doc.id)))
            for doc in documents
        }
        for document in matches:
            key = ("project_reference", str(document.metadata.get("doc_id", document.id)))
            if key not in seen:
                seen.add(key)
                documents.append(document)
        return {"documents": documents}


def create_lab_chatbot(
    *,
    checkpointer: Any | None = None,
    k: int = 4,
    student_context_loader: StudentContextLoader | None = None,
) -> ImprovedPromptLunaChatbot:
    return ImprovedPromptLunaChatbot(
        checkpointer=checkpointer,
        k=k,
        student_context_loader=student_context_loader,
    )


def create_supervisor_harness(*, improved: bool) -> Any:
    """Pinecone/embedding 없이 Luna supervisor만 평가하는 작은 실행기."""
    with _luna_environment():
        llm = ChatOpenAI(model=LAB_MODEL, temperature=0, max_retries=2)
    _assert_luna(llm, "Supervisor")
    prompt = LAB_SUPERVISOR_PROMPT if improved else SUPERVISOR_PROMPT
    decision_schema = LabSupervisorDecision if improved else SupervisorDecision
    chain = (
        ChatPromptTemplate.from_messages([
            ("system", prompt),
            MessagesPlaceholder("messages"),
        ])
        | llm.with_structured_output(decision_schema)
    )
    from chatbot.student_chatbot import SupervisorGuardrailMiddleware

    middleware: Any = SupervisorGuardrailMiddleware()
    if improved:
        middleware = LabSupervisorGuardrail(middleware)
    return SimpleNamespace(supervisor_chain=chain, supervisor_middleware=middleware)
