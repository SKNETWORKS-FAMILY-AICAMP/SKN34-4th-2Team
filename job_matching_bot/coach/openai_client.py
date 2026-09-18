"""OpenAI 호출 어댑터.

**structured output(JSON 스키마 강제)을 지원**한다.
`client.chat.completions.parse()`에 Pydantic 모델을 넘기면 SDK가 스키마로
변환하고, 응답을 그 타입으로 되돌려준다. 모델이 형식을 틀릴 여지가 없어서
`requirement_extractor`의 재시도 루프는 안전망으로만 남는다.

    completion = client.chat.completions.parse(
        model=..., messages=[...], response_format=PydanticModel
    )
    completion.choices[0].message.parsed    # 검증된 인스턴스
    completion.choices[0].message.refusal   # 거절 사유 (있으면)

모델 ID(2026-09 기준):

    gpt-5.6-sol    플래그십        $5 / $30  per 1M
    gpt-5.6-terra  성능·비용 균형   $2 / $12
    gpt-5.6-luna   대량·저비용     $0.20 / $1.20

이 작업(공고 본문에서 요구역량 추출)은 판단이 단순하고 건수가 많아 기본값을
`gpt-5.6-luna`로 둔다. `OPENAI_MODEL` 환경변수로 바꿀 수 있다.

주의: OpenAI structured outputs는 JSON Schema의 일부만 지원한다. `minimum`,
`maxLength` 같은 제약은 스키마에서 빠지고 필드 설명으로만 전달되므로,
그런 제약에 의존하지 않는다.
"""

from __future__ import annotations

import os
from typing import Any

from job_matching_bot.env import ensure_loaded

# 키는 저장소 루트 .env에 모여 있다. 모듈 상수를 읽기 전에 먼저 채운다.
ensure_loaded()

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
DEFAULT_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# 추출 작업이라 창의성이 필요 없다. 같은 공고에 같은 결과가 나오는 편이 낫다.
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 4096


class OpenAIChatModel:
    """OpenAI 채팅 모델.

    `complete(system, user, schema)` 하나만 제공한다. 이 인터페이스만 맞추면
    다른 공급자로 갈아끼울 수 있다.
    """

    provider = "openai"
    # 스키마를 모델 쪽에서 강제할 수 있다. 추출기가 이 값을 보고 동작을 조절한다.
    supports_schema = True

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        client: Any = None,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client = client
        # GPT-5 계열은 max_completion_tokens, 구형은 max_tokens를 받는다.
        # 첫 호출에서 400이 나면 반대쪽으로 한 번 바꿔 재시도한다.
        self.token_limit_param = "max_completion_tokens"
        # GPT-5 계열은 temperature 기본값(1)만 받는다. 400을 받으면 빼고 다시 부른다.
        self.send_temperature = True

    @property
    def client(self) -> Any:
        if self._client is None:
            # 키 확인을 import보다 먼저 한다. SDK가 없을 때도 "키가 없다"는
            # 정확한 이유를 먼저 알려주기 위해서다.
            if not self._api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY가 없습니다. 저장소 루트 .env에 넣거나 "
                    "환경변수로 설정해주세요."
                )
            try:
                from openai import OpenAI
            except ImportError as error:
                raise RuntimeError(
                    "openai 패키지가 필요합니다. `pip install openai`로 설치하세요."
                ) from error
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def complete(
        self, system: str, user: str, schema: Any = None
    ) -> tuple[str, dict[str, int]]:
        """(응답 JSON 문자열, 토큰 사용량)을 돌려준다.

        `schema`(Pydantic 모델)를 주면 structured output으로 형식을 강제한다.
        추출기가 어차피 한 번 더 검증하므로 여기서는 문자열로 돌려준다.
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        # GPT-5 계열은 `max_tokens`를 거부하고 `max_completion_tokens`를 쓴다.
        # 구형 모델은 반대라, 400을 받으면 다른 이름으로 한 번 다시 시도한다.
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            self.token_limit_param: self.max_tokens,
        }
        if self.send_temperature:
            kwargs["temperature"] = self.temperature

        completion = self._call(kwargs, schema)

        message = completion.choices[0].message
        refusal = getattr(message, "refusal", None)
        if refusal:
            raise RuntimeError(f"모델이 요청을 거절했습니다: {refusal}")

        usage = getattr(completion, "usage", None)
        return message.content or "", {
            "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
        }

    def _call(self, kwargs: dict[str, Any], schema: Any) -> Any:
        """모델 호출.

        모델 세대마다 받는 파라미터가 다르다. GPT-5 계열은 `max_tokens` 대신
        `max_completion_tokens`를 쓰고 `temperature`는 기본값만 받는다.
        400이 오면 문제가 된 파라미터를 고쳐 다시 부른다. 모델 ID로 분기하면
        새 모델이 나올 때마다 코드를 고쳐야 해서, 응답을 보고 맞춘다.
        """
        for _ in range(3):
            try:
                if schema is not None:
                    return self.client.chat.completions.parse(
                        response_format=schema, **kwargs
                    )
                return self.client.chat.completions.create(**kwargs)
            except Exception as error:
                message = str(error)
                swapped = (
                    "max_completion_tokens"
                    if self.token_limit_param == "max_tokens"
                    else "max_tokens"
                )
                if self.token_limit_param in message and swapped in message:
                    kwargs[swapped] = kwargs.pop(self.token_limit_param)
                    self.token_limit_param = swapped
                    continue
                if "temperature" in message and "temperature" in kwargs:
                    kwargs.pop("temperature")
                    self.send_temperature = False
                    continue
                raise
        raise RuntimeError("모델이 받는 파라미터 조합을 찾지 못했습니다.")

    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """텍스트를 벡터로 만든다. 시맨틱 매칭·RAG에 쓴다."""
        response = self.client.embeddings.create(
            model=model or DEFAULT_EMBEDDING_MODEL, input=texts
        )
        return [item.embedding for item in response.data]


def is_configured() -> bool:
    ensure_loaded()
    return bool(os.environ.get("OPENAI_API_KEY"))
