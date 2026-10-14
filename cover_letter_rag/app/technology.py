"""Conservative technology aliases. Never rewrite source evidence."""
import re
import unicodedata


ALIASES = {
    "Python": ("python", "파이썬"),
    "React": ("react", "react.js", "reactjs", "리액트"),
    "React Native": ("react native", "리액트 네이티브"),
    "TypeScript": ("typescript", "타입스크립트"),
    "JavaScript": ("javascript", "자바스크립트"),
    "Java": ("java", "자바"),
    "Spring Boot": ("spring boot", "springboot", "스프링 부트", "스프링부트"),
    "Spring": ("spring", "스프링"),
    "Vue": ("vue", "vue.js", "vuejs", "뷰"),
    "Node.js": ("node.js", "nodejs", "노드제이에스"),
    "Next.js": ("next.js", "nextjs", "넥스트제이에스"),
    "FastAPI": ("fastapi", "패스트API", "패스트에이피아이"),
    "Docker": ("docker", "도커"),
    "Kubernetes": ("kubernetes", "k8s", "쿠버네티스"),
    "C++": ("c++", "씨플러스플러스"),
    "C#": ("c#", "씨샵"),
}


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


_LOOKUP = {_normalize(alias): canonical for canonical, aliases in ALIASES.items() for alias in aliases}
# Longer names win so Spring Boot is not silently reduced to Spring.
_PATTERN = re.compile(
    r"(?<![\w])(?:" + "|".join(re.escape(a) for a in sorted(_LOOKUP, key=len, reverse=True))
    + r")(?![a-z0-9_+#]|\.[a-z])"
)


def canonical_technology(name: str) -> str:
    return _LOOKUP.get(_normalize(name.strip()), name.strip())


def technology_mentions(text: str) -> set[str]:
    return {_LOOKUP[m.group()] for m in _PATTERN.finditer(_normalize(text))}


def comparison_terms(text: str) -> set[str]:
    """Known aliases plus unmatched English tokens for conservative grounding."""
    normalized = _normalize(text)
    known = {"tech:" + name for name in technology_mentions(text)}
    remainder = _PATTERN.sub(" ", normalized)
    return known | set(re.findall(r"[a-z][a-z0-9.+#/-]*", remainder))


_NUMBER_WITH_UNIT = re.compile(r"\d+(?:[.,]\d+)*\s*(?:ms|sec|min|s|h)(?![a-z])")


def grounding_terms(text: str) -> set[str]:
    """이력서 첨삭 수정안을 원문과 견줄 때 쓰는 영문·기술 토큰.

    comparison_terms를 그대로 쓰면 문장을 다듬기만 해도 사실이 바뀐 것으로 본다.
    원문 "p95 1.2s→0.5s"의 단위 `s`가 영단어로 잡혀 "1.2초에서 0.5초로"가 사실을 빠뜨린
    것이 되고, "ECS+GitHub"가 한 덩어리라 "ECS와 GitHub"가 새 기술어가 된다(2026-09-14
    A/B에서 수정안 24개 중 이 둘로 버려진 것이 대부분이었다). 숫자에 붙은 단위는 숫자 검사가
    따로 맡으므로 떼고, `+`·`/`로 이어 쓴 이름은 나눠 본다.
    """
    cleaned = _NUMBER_WITH_UNIT.sub(" ", _normalize(text))
    terms = set()
    for term in comparison_terms(cleaned):
        if term.startswith("tech:"):
            terms.add(term)
            continue
        for part in re.split(r"[+/]", term):
            part = part.strip(".-")
            if part:
                terms.add(part)
    return terms


def technology_in_text(name: str, text: str) -> bool:
    canonical = canonical_technology(name)
    if canonical in ALIASES:
        return canonical in technology_mentions(text)
    return bool(re.search(r"(?<!\w)" + re.escape(_normalize(name)) + r"(?![a-z0-9_])", _normalize(text)))
