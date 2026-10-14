"""
채용공고 텍스트(제목, 지원자격, 우대사항 등)에서 기술 키워드를 뽑아내는 추출기.

ALIO처럼 구조화된 '기술스택' 필드가 없는 소스에서, 텍스트 안에 자연스럽게 언급된
기술명을 찾아내 required_skills를 보강하는 용도로 쓴다.

한계: 정규식/키워드 매칭 기반이라 완벽하지 않다. 문맥은 이해하지 못하고
      "이 단어가 텍스트에 등장하는가"만 본다. 나중에 사람인/원티드처럼
      구조화된 스킬 필드를 주는 API가 승인되면, 그쪽 데이터가 항상 우선이다.
"""

import re

# 정규 표기명 → [매칭할 표현들](영문/한글 표기, 대소문자 무관하게 매칭)
SKILL_ALIASES: dict[str, list[str]] = {
    # 언어
    "Python": ["python", "파이썬"],
    "Java": ["java", "자바"],
    "JavaScript": ["javascript", "자바스크립트", "js"],
    "TypeScript": ["typescript", "타입스크립트", "ts"],
    "C": [r"\bc언어\b", r"(?<![+#a-z])c(?![+#a-z0-9])"],
    "C++": ["c++", "씨쁠쁠"],
    "C#": ["c#", "씨샵"],
    "Go": [r"\bgo언어\b", r"\bgolang\b"],
    "Kotlin": ["kotlin", "코틀린"],
    "Swift": ["swift", "스위프트"],
    "PHP": ["php"],
    "Ruby": ["ruby", "루비"],
    "R": [r"\br언어\b", r"\br분석\b"],
    "SQL": ["sql", "에스큐엘"],

    # 웹/프레임워크
    "React": ["react", "리액트"],
    "Vue.js": ["vue.js", "vue", "뷰js", "뷰.js"],
    "Angular": ["angular", "앵귤러"],
    "Node.js": ["node.js", "nodejs", "노드js", "노드.js"],
    "Django": ["django", "장고"],
    "Flask": ["flask", "플라스크"],
    "FastAPI": ["fastapi"],
    "Spring": ["spring framework", "스프링"],
    "Spring Boot": ["spring boot", "스프링부트"],
    "HTML/CSS": ["html", "css"],
    "jQuery": ["jquery", "제이쿼리"],

    # 데이터/DB
    "MySQL": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MongoDB": ["mongodb", "몽고디비"],
    "Redis": ["redis", "레디스"],
    "Oracle": ["oracle db", "오라클"],
    "NoSQL": ["nosql"],
    "Hadoop": ["hadoop", "하둡"],
    "Spark": ["spark", "스파크"],
    "Kafka": ["kafka", "카프카"],
    "Elasticsearch": ["elasticsearch", "엘라스틱서치"],

    # AI/데이터분석
    "TensorFlow": ["tensorflow", "텐서플로"],
    "PyTorch": ["pytorch", "파이토치"],
    "pandas": ["pandas", "판다스"],
    "NumPy": ["numpy"],
    "머신러닝": ["머신러닝", "machine learning", "ml모델"],
    "딥러닝": ["딥러닝", "deep learning"],
    "데이터분석": ["데이터 분석", "데이터분석", "data analysis"],

    # 인프라/클라우드
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure", "애저"],
    "GCP": ["gcp", "google cloud"],
    "Docker": ["docker", "도커"],
    "Kubernetes": ["kubernetes", "쿠버네티스", "k8s"],
    "Git": ["git", "깃"],
    "Linux": ["linux", "리눅스"],
    "Jenkins": ["jenkins", "젠킨스"],
    "CI/CD": ["ci/cd", "씨아이씨디"],

    # 모바일
    "Android": ["android", "안드로이드"],
    "iOS": ["ios 개발", "아이폰 개발"],
    "Flutter": ["flutter", "플러터"],

    # 협업/디자인 툴 (직군에 따라 필요한 경우가 있어 포함)
    "Figma": ["figma", "피그마"],
    "Excel": ["엑셀", "excel"],
    "SAS": [r"\bsas\b"],
    "Tableau": ["tableau", "태블로"],
    "Power BI": ["power bi", "파워비아이"],
}

def _compile_pattern(alias: str) -> str:
    """이미 정규식으로 작성된 패턴(백슬래시 포함)은 그대로 두고,
    일반 문자열은 특수문자(+, #, . 등)를 이스케이프해서 리터럴로 매칭한다."""
    if "\\" in alias:
        return alias
    return re.escape(alias)


_COMPILED: list[tuple[str, re.Pattern]] = [
    (canonical, re.compile("|".join(_compile_pattern(a) for a in patterns), re.IGNORECASE))
    for canonical, patterns in SKILL_ALIASES.items()
]


def extract_skills(text: str) -> list[str]:
    """텍스트에서 언급된 기술 키워드를 정규 표기명 리스트로 반환한다 (중복 제거, 등장 순서 유지)."""
    if not text:
        return []

    found = []
    for canonical, pattern in _COMPILED:
        if pattern.search(text):
            found.append(canonical)
    return found


if __name__ == "__main__":
    sample = """
    Python, Django 기반 백엔드 개발 경험자 우대. AWS EC2/RDS 운영 경험,
    Docker/Kubernetes 사용 경험자 우대. PostgreSQL 및 SQL 활용 능력 필수.
    """
    print(extract_skills(sample))
