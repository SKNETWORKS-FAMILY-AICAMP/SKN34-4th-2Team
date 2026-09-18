"""추천 API의 요청·응답과 LLM 구조화 출력 스키마.

`StrictModel`은 정의되지 않은 필드를 거부한다. 앱이 오타 난 필드를 보내면
조용히 무시되는 대신 422로 돌아오게 하려는 것이다.

LLM 출력 스키마(`ResumeProfileOut`, `JobFit`)는 `with_structured_output`에
그대로 넘긴다. 모델이 형식을 지키도록 강제하되, 받은 값은 서비스에서 한 번 더
검증한다 — 형식이 맞다고 내용이 사실인 것은 아니다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── 요청 ────────────────────────────────────────────────

class RecommendRequest(StrictModel):
    """앱이 보내는 것. 이력서 원본은 Firestore에 있고, 서버는 평문만 받는다."""

    resume_text: str = Field(min_length=20, max_length=50_000)
    preferred_regions: list[str] = Field(default_factory=list, max_length=20)
    preferred_employment_types: list[str] = Field(default_factory=list, max_length=10)
    education_level: str = "미기재"
    career_years: float = Field(default=0, ge=0, le=60)
    majors: list[str] = Field(default_factory=list, max_length=10)
    certifications: list[str] = Field(default_factory=list, max_length=30)
    # 재정렬이 후보 12건까지만 판정하므로(service.RERANK_TOP_K) 그 위는 약속할 수 없다.
    # 회사당 2건 제한과 마감 제외까지 겹치면 그보다 적게 올 수도 있다.
    top_k: int = Field(default=10, ge=1, le=12)
    # 앱이 이력서를 저장할 때 미리 만들어 둔 구조화 결과. 있으면 서버는 다시 만들지 않는다.
    # 대기 시간이 2.7초 줄고, 무엇보다 **검색어가 고정되어 추천이 매번 흔들리지 않는다.**
    # 이력서를 고쳤으면 앱이 보내지 않으면 된다 — 그때는 서버가 새로 만든다.
    profile: "ResumeProfileOut | None" = None

    @field_validator("resume_text")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("resume_text must not be blank")
        return value.strip()


class ProfileRequest(StrictModel):
    """구조화만 요청한다. 이력서를 저장할 때 미리 불러 두는 용도다."""

    resume_text: str = Field(min_length=20, max_length=50_000)

    @field_validator("resume_text")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("resume_text must not be blank")
        return value.strip()


# ── LLM ① 이력서 구조화 ─────────────────────────────────

class ResumeProfileOut(StrictModel):
    """이력서에서 뽑은 검색용 프로필.

    `search_query`가 핵심이다. 이력서는 "FastAPI로 API를 개발했습니다"(경험)로
    쓰이고 공고는 "Python 개발 경험 2년 이상"(요구)으로 쓰여 표현이 다르다.
    공고 쪽 표현으로 바꿔야 벡터 검색이 잘 걸린다.
    """

    search_query: str = Field(
        description="이 사람에게 맞는 공고를 찾기 위한 질의문. 공고 자격요건처럼 쓴다."
    )
    target_roles: list[str] = Field(description="지원할 만한 직무 이름", max_length=5)
    skills: list[str] = Field(description="이력서에 근거가 있는 기술만", max_length=30)
    career_years: float = Field(description="이력서 경력사항으로 계산한 연차. 없으면 0", ge=0)
    summary: str = Field(description="이 지원자를 한 문장으로")


# RecommendRequest 가 위에서 이 형을 이름으로만 가리켰다. 여기서 이어 준다.
RecommendRequest.model_rebuild()


# ── LLM ② 재정렬 ────────────────────────────────────────

class Reason(StrictModel):
    claim: str = Field(description="적합하다고 본 이유 한 줄")
    resume_quote: str = Field(
        description="이력서 원문에 연속해서 존재하는 직접 인용. 할 줄 아는 일을 보여 주는 대목"
    )
    job_quote: str = Field(
        description="공고 원문에 연속해서 존재하는 직접 인용. 요구하는 업무·기술 대목"
    )


class JobFit(StrictModel):
    """재정렬 결과 하나.

    필드 순서가 곧 판단 순서다. 구조화 출력은 위에서부터 채워지므로, `fit`을 정하기 전에
    **무엇과 무엇을 견줬는지 먼저 쓰게** 한다. 이 세 칸이 없을 때는 모델이 대조를 건너뛰고
    감으로 등급을 매겨 30건 중 20건이 "높음"으로 몰렸다.
    """

    job_id: str
    job_core: str = Field(
        description="이 공고에서 매일 쓸 주된 기술·업무. 제목과 주요업무에서 잡는다. 셋 이내, 공고의 말로"
    )
    resume_core: str = Field(
        description="이력서의 주력. 실제로 만들어 본 것 기준. 셋 이내, 이력서에 적힌 말로"
    )
    overlap: str = Field(
        description="위 둘이 실제로 겹치는 것. 겹치는 게 없으면 '없음'이라고 쓴다"
    )
    fit: Literal["높음", "보통", "낮음"]
    reasons: list[Reason] = Field(
        default_factory=list,
        # 상한이 4면 "필수 요건 대부분을 충족했다"를 셀 수가 없어 적합도가 전부 '보통'으로
        # 몰렸다. 자격요건과 우대사항 충족을 함께 담을 만큼 넉넉하게 둔다.
        max_length=6,
        description="충족한 업무·기술. 자격요건·우대사항 모두. 조건(연차·학력·지역)은 넣지 않는다",
    )
    concerns: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="자격요건(필수) 중 이력서에서 확인되지 않는 것만. 우대사항은 넣지 않는다",
    )


class RerankOut(StrictModel):
    results: list[JobFit]


# ── 응답 ────────────────────────────────────────────────

class Conditions(StrictModel):
    region: str = ""
    employment_type: str | None = None
    career: str = ""
    education: str = ""
    deadline: str | None = None


class Recommendation(StrictModel):
    job_id: str
    company: str
    title: str
    source_url: str
    fit: Literal["높음", "보통", "낮음"]
    reasons: list[Reason] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    conditions: Conditions
    filter_status: Literal["PASS", "CHECK_REQUIRED"] = "PASS"
    unknown_conditions: list[str] = Field(default_factory=list)
    passed_conditions: list[str] = Field(default_factory=list)
    search_rank: int = Field(description="벡터 검색에서의 순위")
    body_is_image: bool = False


class RecommendResponse(StrictModel):
    recommendations: list[Recommendation]
    search_query: str = Field(description="LLM이 만든 검색 질의문. 왜 이렇게 찾았는지 보여 준다")
    profile_summary: str = ""
    reranked: bool = Field(description="LLM 재정렬이 적용됐는지. false면 검색 순서 그대로")
    warnings: list[str] = Field(default_factory=list, description="근거 검증에서 제거한 내용")
    notice: str = (
        "추천 순서는 이력서와 공고의 관련도이며 합격 가능성이나 지원자 점수가 아닙니다."
    )
    # LLMOps — 원문 없이 버전만. 앱이 aiGenerationLogs에 옮긴다.
    prompt_version: str = ""
    model: str = ""
    reasoning_effort: str = ""
    # 단계별 걸린 시간(ms). 열쇠는 profile·search·filter·liveness·pre_rank·rerank·verify·total.
    # 검색 결과가 없으면 search까지만 있다.
    timings_ms: dict[str, int] = Field(default_factory=dict)
    profile_source: str = Field(default="", description="구조화를 어디서 얻었나. 앱·캐시·LLM")


# ── 공고 찾아보기 챗봇 ──────────────────────────────────

class ChatFilters(StrictModel):
    """대화에서 뽑아낸 검색 조건.

    앱이 응답으로 받은 그대로 다음 요청에 실어 보낸다. 그래야 "서울만"처럼 앞말을
    이어받는 말이 통한다. 서버는 대화를 저장하지 않는다.
    """

    roles: list[str] = Field(default_factory=list, description="직무. 백엔드, 데이터분석")
    skills: list[str] = Field(default_factory=list, description="기술. Python, React")
    regions: list[str] = Field(default_factory=list, description="지역. 서울, 경기")
    career: Literal["신입", "경력", "무관"] = "무관"
    # 몇 년차인지. **`career`만으로는 부족하다.**
    #
    # "3년차인데 갈 만한 데 있어?"에 경력 5년 이상 공고가 나갔다. 경력이냐 신입이냐만
    # 보고 숫자를 버렸기 때문이다. 저장소에 최소 연차가 있는데 안 읽었다. 추천 쪽
    # 하드 필터는 이미 본다(`hard_filter`) — 챗봇 검색에만 없었다.
    career_years: int | None = Field(
        default=None, ge=0, le=50,
        description="말한 연차. '3년차', '5년 경력' → 3, 5. 안 밝혔으면 null",
    )
    employment_types: list[str] = Field(default_factory=list, description="정규직, 인턴")
    deadline_within_days: int | None = Field(
        default=None, description="마감 임박만 볼 때의 날짜 수. 아니면 null"
    )
    keywords: list[str] = Field(default_factory=list, description="위에 안 들어가는 말")
    # 빼 달라는 말. **걸러 달라는 말과 따로 둔다.**
    #
    # "스타트업은 빼고 데이터 분석 신입"에 답이 "스타트업을 제외하고 찾아보겠습니다"라고 했지만
    # 담을 칸이 없어 아무것도 빼지 않았다.
    exclude_keywords: list[str] = Field(
        default_factory=list,
        description="빼 달라는 말. '스타트업은 빼고' → 스타트업, '파견은 싫어요' → 파견, '계약직 말고' → 계약직",
    )
    # 공고가 올라온 지 며칠 안 됐나. 마감(`deadline_within_days`)과 다른 방향이다.
    #
    # "오늘 새로 올라온 개발 공고"에 날짜로 거르지 않고 개발 공고 전체가 나갔다.
    posted_within_days: int | None = Field(
        default=None, ge=0, le=60,
        description="최근 올라온 공고만 볼 때의 날짜 수. '오늘 올라온' → 0, '이번 주 새로 올라온' → 7. 아니면 null",
    )


class ChatTurnOut(StrictModel):
    """LLM ①: 무엇을 원하는 말인지 가르고, 조건을 뽑는다.

    조건은 의도와 상관없이 뽑는다. "백엔드 신입은 뭘 준비해야 해?"는 질문이지만
    그 안에 직무·경력이 들어 있고, 그 조건으로 공고를 세어야 숫자로 답할 수 있다.
    """

    intent: Literal["검색", "질문", "추천", "잡담"] = Field(
        description=(
            "공고 목록을 원하면 검색, 채용에 대해 묻는 말이면 질문, "
            "이력서를 근거로 골라 달라는 말이면 추천, 그 밖은 잡담"
        )
    )
    filters: ChatFilters
    # 무엇에 대한 말인가. **"채용"일 때만 답을 쓰는 단계로 간다.**
    #
    # 처음에는 "상관없으면 막는다"(off_topic)로 두었다. 기본값이 통과라 모델이 애매하게
    # 본 말은 전부 흘러 들어왔다. "호구"라고만 보냈는데 뜻풀이와 "이 말을 부드럽게 바꿔
    # 말해줘" 같은 제안까지 달려 나간 적이 있다.
    #
    # 그래서 뒤집었다. 기본값을 두지 않고 셋 중 하나를 반드시 고르게 한다. 채용이라고
    # 짚지 못한 말은 막힌다. 애매할 때 통과하는 것과 막히는 것은 다르다.
    topic: Literal["채용", "인사", "그 밖"] = Field(
        description=(
            "채용·취업·공고·이력서·면접에 대한 말이면 채용. "
            "인사와 짧은 예의치레면 인사. 그 밖은 전부 '그 밖'. "
            "채용인지 아닌지 분명하지 않으면 '그 밖'으로 둔다"
        )
    )
    counts_jobs: bool = Field(
        default=False,
        description="공고를 세어서 답할 질문이면 true. 조언을 구하는 말이면 false",
    )
    job_refs: list[int] = Field(
        default_factory=list,
        description=(
            "직전에 보여 준 목록에서 몇 번째를 가리켰는지. 1부터 센다. "
            "'2번 자세히', '첫 번째 거' → [2], [1]. 가리킨 것이 없으면 빈 목록"
        ),
    )
    # 번호 없이 "방금 그거"를 가리키는 말. 비교 뒤에 이어지는 물음이 대부분 이 꼴이다.
    refers_to_last_answer: bool = Field(
        default=False,
        description=(
            "번호를 대지 않고 직전 답이 다룬 공고를 가리키면 true. "
            "'두 공고의 자격요건만', '이 공고 마감일은', '둘 다 신입 가능해?'가 그렇다. "
            "새로 찾아 달라는 말이면 false"
        ),
    )
    # "이거 말고"를 거듭하면 같은 조건에서 **안 본 공고**를 차례로 보여 준다. 없으면 같은
    # 목록을 다시 찾아 놓고 답에는 "다른 공고를 찾았다"고 말했다.
    show_more: bool = Field(
        default=False,
        description=(
            "직전 목록 말고 같은 조건의 다른 공고를 더 보고 싶다는 말이면 true. "
            "'이거 말고', '다른 거', '더 보여줘', '다음'. 조건을 바꾸는 말이면 false"
        ),
    )
    resume_scope: Literal["전체", "프로젝트", "기술스택", "자기소개서", "경력"] = Field(
        default="전체",
        description=(
            "추천일 때 이력서의 어디를 근거로 삼을지. 사용자가 콕 집어 말했을 때만 "
            "좁힌다. '프로젝트 경험 보고' → 프로젝트, '기술스택으로' → 기술스택"
        ),
    )
    unavailable: Literal["", "급여", "복지", "합격 가능성", "회사 평판"] = Field(
        default="",
        description=(
            "우리가 가지고 있지 않은 정보로 찾거나 줄 세워 달라는 요청이면 그것. "
            "아니면 빈 문자열"
        ),
    )
    requirement_query: str = Field(
        default="",
        description=(
            "원하는 일을 채용공고의 자격요건·주요업무 말투로 고쳐 쓴 한두 문장. "
            "조건으로 못 찾았을 때 뜻으로 찾는 데 쓴다"
        ),
    )
    understood: str = Field(description="무엇으로 찾을지 사용자에게 확인시키는 한 문장")


class ChatAnswerOut(StrictModel):
    """LLM ②: 채용 질문에 대한 답. 공고 통계나 공고 원문을 근거로 쓴다."""

    answer: str = Field(description="사용자에게 보여 줄 답. 여러 문단이어도 된다")
    followups: list[str] = Field(
        default_factory=list,
        description="이어서 물어볼 만한 말 세 개 이내. 그대로 눌러 보낼 수 있는 문장으로",
    )


class JobChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=500)
    filters: ChatFilters | None = Field(
        default=None, description="직전 응답의 filters. 첫 질문이면 비운다"
    )
    top_k: int = Field(default=5, ge=1, le=20)
    job_id: str | None = Field(
        default=None,
        description="이 공고를 놓고 묻는 경우의 job_id. 있으면 그 공고를 근거로 답한다",
    )
    # 직전 답에서 보여 준 공고의 job_id를 **화면에 나온 순서 그대로** 담는다.
    #
    # 이게 없으면 "2번 자세히 봐줘"에 답할 수 없다. 서버는 대화를 저장하지 않으므로
    # 직전에 무엇을 보여 줬는지 모른다. 지금까지는 사용자가 공고 카드를 눌러
    # `job_id`를 보내야만 그 공고를 놓고 물을 수 있었다.
    #
    # 앱은 직전 응답의 `jobs`에서 그대로 뽑아 보내면 된다. 응답에 새 필드가 필요 없다.
    last_job_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="찾아 준 목록의 공고 id를 보여 준 순서대로. '2번'을 가리킬 때 쓴다",
    )
    # **직전 답이 다룬 공고.** 위와 다르다. 위는 번호가 가리킬 *목록*이고 이쪽은 방금
    # 이야기한 *대상*이다. 비교 답이면 견준 두 건, 공고 하나에 답했으면 그 한 건이다.
    #
    # 이게 없으면 비교 바로 뒤에 "두 공고의 자격요건만 간단히 비교해 주세요"라고 했을 때
    # 답하지 못한다. 번호가 없어 가리킨 자리가 없고, 서버는 방금 무엇을 견줬는지
    # 모르기 때문이다. 실제로 "두 공고의 자격요건 내용이 보이지 않아 비교할 수 없습니다"
    # 라고 답했다. 그 말을 부른 제안 문구를 챗봇이 직접 내놓고도 그랬다.
    last_answer_job_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="직전 답이 다룬 공고 id를 보여 준 순서대로. '두 공고', '이 공고'가 가리키는 것",
    )
    # **같은 조건으로 지금까지 보여 준 공고 전부.** 위 `last_job_ids`는 직전 한 쪽뿐이라,
    # 그것만 빼면 "이거 말고"를 두 번째 할 때 첫 목록이 다시 나온다. 앱이 조건이 바뀔
    # 때까지 모아 보내고, 서버는 `show_more`일 때 이것을 빼고 다음 공고를 준다.
    seen_job_ids: list[str] = Field(
        default_factory=list,
        max_length=3000,
        description="같은 조건으로 이미 보여 준 공고 id 전부. '이거 말고'를 거듭할 때 뺀다",
    )
    # 공고를 놓고 물을 때 "나한테 맞아?"는 이력서를 봐야 답할 수 있다. 없으면 서버는
    # 공고만 읽고 답하므로, 앱은 이력서 화면에서 물을 때 평문을 함께 보낸다.
    resume_text: str | None = Field(default=None, max_length=50_000)


class JobChatJob(StrictModel):
    job_id: str
    company: str
    title: str
    source_url: str
    region: str
    career: str
    employment_type: str
    deadline: str | None = None
    tech_stack: list[str] = Field(default_factory=list)


class JobChatResponse(StrictModel):
    mode: Literal["검색", "질문", "공고", "비교", "추천", "안내"] = Field(
        default="검색", description="앱이 답을 어떻게 보여 줄지 정하는 데 쓴다"
    )
    resume_scope: Literal["전체", "프로젝트", "기술스택", "자기소개서", "경력"] = Field(
        default="전체",
        description="mode가 추천일 때 이력서의 어디를 근거로 삼을지. 앱이 그만큼만 보낸다",
    )
    reply: str
    filters: ChatFilters
    jobs: list[JobChatJob] = Field(default_factory=list)
    total: int = Field(
        description=(
            "답이 말한 건수. 검색이면 제목·태그에 직접 맞은 공고 수(없으면 조건에 맞는 전체). "
            "jobs는 그중 일부"
        )
    )
    suggestions: list[str] = Field(
        default_factory=list, description="다음에 더 좁힐 거리. 그대로 눌러 보낼 수 있는 말"
    )
    prompt_version: str = ""
    model: str = ""
    reasoning_effort: str = ""
    # 지난 단계별 시간(ms). 갈래마다 지나는 단계가 달라 열쇠가 다르다.
    # route·store·search·meaning·stats·liveness·answer 중 지난 것과 total.
    timings_ms: dict[str, int] = Field(default_factory=dict)


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"
    index_name: str
    vector_count: int
    llm_configured: bool
