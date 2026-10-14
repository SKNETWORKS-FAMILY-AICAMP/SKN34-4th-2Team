"""기술명 표준화.

공고와 이력서는 같은 기술을 다르게 적는다. 사람인 기술스택 태그만 봐도
`ReactJS`/`React`, `Node.js`, `React-Native`, `SpringBoot`, `RestAPI`가 섞여 있고,
이력서에는 `Spring Boot`, `REST API`, `Postgres`처럼 들어온다. 소문자 비교만으로는
이런 것들이 전부 불일치가 돼서, 기술스택을 채점 신호로 쓰는 순간 점수가 크게
새 나간다.

규칙은 두 단계다.

1. 소문자로 바꾸고 영숫자·`+`·`#`·한글만 남긴다.
   `Node.js`→`nodejs`, `Spring Boot`→`springboot`, `PL/SQL`→`plsql`.
   `C++`/`C#`은 그대로 살아남고, `.NET`은 `net`이 된다.
2. 별칭 표로 한 번 더 접는다. `reactjs`→`react`, `postgres`→`postgresql`.

이 표는 functions/src/jobCoachScoring.ts 의 SKILL_ALIASES 와 같아야 한다.
값이 갈라지면 같은 이력서로 Python POC와 Functions가 다른 점수를 낸다.
"""

from __future__ import annotations

import re

# 표준 키 → 그 키로 접을 표기들. 확신이 있는 것만 넣는다. `ts`처럼 다른 뜻과
# 겹칠 수 있는 약어는 넣지 않는다.
SKILL_ALIASES: dict[str, str] = {
    "reactjs": "react",
    "vuejs": "vue",
    "node": "nodejs",
    "js": "javascript",
    "postgres": "postgresql",
    "oracledb": "oracle",
    "golang": "go",
    "k8s": "kubernetes",
    "rest": "restapi",
    "restfulapi": "restapi",
    "css3": "css",
    "html5": "html",
    "c언어": "c",
    "dotnet": "net",
    "sqlserver": "mssql",
    "amazonwebservices": "aws",
    "googlecloud": "gcp",
    "python3": "python",
}

# 남길 문자: 영숫자, C++/C#의 기호, 한글.
_STRIP = re.compile(r"[^a-z0-9+#가-힣]")


def canonical_skill(name: str) -> str:
    """기술명을 비교용 표준 키로 만든다. 표시용으로는 원문을 그대로 쓴다."""
    key = _STRIP.sub("", name.strip().lower())
    return SKILL_ALIASES.get(key, key)


def canonical_set(names: list[str]) -> set[str]:
    return {canonical_skill(name) for name in names if name and name.strip()}
