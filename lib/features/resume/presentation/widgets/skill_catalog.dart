import '../../ai_coach/data/generated/job_skill_names.g.dart';

/// 기술스택 태그 후보.
///
/// 부트캠프 수료생이 자주 적는 기술을 손으로 고른 기본 목록에, 수집한 채용공고가
/// 실제로 요구하는 기술을 합친다. 공고 쪽 이름이 들어가야 태그를 고르는 것만으로
/// 공고에 쓰인 표기를 쓰게 된다.
///
/// 공고 쪽 이름은 `job_skill_names.g.dart`에서 온다. 예전에는 앱이 공고 8.4MB를
/// 안고 있으면서 거기서 뽑았는데, 공고가 서버로 옮겨 가면서 이름만 남겼다.
abstract final class SkillCatalog {
  static const baseSkills = <String>[
    // 언어
    'Python', 'Java', 'JavaScript', 'TypeScript', 'Dart', 'Kotlin', 'Swift',
    'C', 'C++', 'C#', 'Go', 'Rust', 'R', 'SQL', 'HTML/CSS',
    // 백엔드 · 프레임워크
    'Spring Boot', 'FastAPI', 'Django', 'Flask', 'Node.js', 'Express', 'NestJS',
    'REST API', 'GraphQL', 'JPA',
    // 프론트엔드 · 모바일
    'React', 'Next.js', 'Vue', 'Flutter', 'React Native', 'Android', 'iOS',
    'Tailwind CSS',
    // 데이터 · AI
    'NumPy', 'Pandas', 'Matplotlib', 'Scikit-learn', 'PyTorch', 'TensorFlow',
    'Keras', 'OpenCV', 'Hugging Face', 'LangChain', 'LLM', 'RAG',
    'Deep Learning', 'Machine Learning', 'Data Analysis', 'NLP',
    'Streamlit', 'Airflow', 'Spark', 'Hadoop', 'Kafka', 'Tableau', 'Power BI',
    'Excel',
    // 데이터베이스
    'MySQL', 'PostgreSQL', 'Oracle', 'MongoDB', 'Redis', 'Elasticsearch',
    'Neo4j', 'Firebase', 'Firestore',
    // 인프라 · 협업
    'Linux', 'Docker', 'Kubernetes', 'AWS', 'GCP', 'Azure', 'Git', 'GitHub',
    'GitHub Actions', 'Jenkins', 'Nginx', 'Figma', 'Jira', 'Notion',
  ];

  /// 같은 기술인데 표기가 갈리는 것. **영문 하나만** 남긴다.
  ///
  /// 기본 목록은 영문으로 적었는데 공고는 한글로 태그를 단다. 그대로 두면 선택지에
  /// 둘 다 나와서(`Deep Learning` 과 `딥러닝`) 무엇을 골라야 할지 알 수 없다.
  ///
  /// 공고 태그는 한글이 많다(딥러닝 417건 대 Deep Learning 0건). 그런데도 영문을
  /// 남기는 이유는 둘이다.
  ///
  /// 1. **추천은 뜻으로 찾는다.** 이력서 글은 벡터로 검색하므로 표기가 달라도 걸린다.
  ///    실측(같은 요건 문장을 영문·한글로): 영문 질의 0.63, 한글 질의 0.56.
  /// 2. **이력서에 적히는 이름이다.** 사람이 읽는 문서라 영문 표기가 낫다.
  ///
  /// `Power BI` 와 `파워빌더` 처럼 이름만 비슷하고 다른 제품은 여기 넣지 않는다.
  static const aliases = <String, String>{
    '딥러닝': 'Deep Learning',
    '머신러닝': 'Machine Learning',
    '데이터분석': 'Data Analysis',
    'nlp(자연어처리)': 'NLP',
  };

  /// 기본 목록 + 수집 공고의 필수·우대·태그 기술. 표기가 같으면 하나만 남긴다.
  static final List<String> all = _build();

  static List<String> _build() {
    final byKey = <String, String>{};
    void add(String name) {
      final trimmed = name.trim();
      if (trimmed.isEmpty) return;
      final canonical = aliases[trimmed.toLowerCase()] ?? trimmed;
      byKey.putIfAbsent(canonical.toLowerCase(), () => canonical);
    }

    baseSkills.forEach(add);
    jobSkillNames.forEach(add);
    final names = byKey.values.toList();
    // 기본 목록은 손으로 정한 순서를 지키고, 공고에서 온 것은 그 뒤에 이름순으로 둔다.
    // 기본 목록 이름이 별칭이면 바뀐 이름으로 자리를 잡는다.
    final baseKeys = baseSkills
        .map((s) => (aliases[s.toLowerCase()] ?? s).toLowerCase())
        .toSet();
    final fromJobs = names.where((n) => !baseKeys.contains(n.toLowerCase())).toList()
      ..sort((a, b) => a.toLowerCase().compareTo(b.toLowerCase()));
    return [
      ...baseSkills.map((s) {
        final canonical = aliases[s.toLowerCase()] ?? s;
        return byKey[canonical.toLowerCase()] ?? canonical;
      }),
      ...fromJobs,
    ];
  }

  /// 검색어로 후보를 거른다. 비어 있으면 전체.
  static List<String> search(String query) {
    final q = query.trim().toLowerCase();
    if (q.isEmpty) return all;
    final starts = <String>[];
    final contains = <String>[];
    for (final name in all) {
      final lower = name.toLowerCase();
      if (lower.startsWith(q)) {
        starts.add(name);
      } else if (lower.contains(q)) {
        contains.add(name);
      }
    }
    return [...starts, ...contains];
  }

  /// 대소문자·공백 차이를 무시하고 같은 기술로 본다.
  static bool sameSkill(String a, String b) =>
      a.trim().toLowerCase() == b.trim().toLowerCase();

  /// 후보 목록에 있는 표기가 있으면 그것으로 맞춰 준다. 없으면 입력 그대로.
  /// 사용자가 적은 이름을 목록의 표기로 맞춘다.
  ///
  /// 별칭을 먼저 본다. 예전에 저장된 이력서나 직접 입력한 "딥러닝" 이 목록에서
  /// 사라졌으므로, 그대로 두면 선택지에 없는 이름이 남는다.
  static String canonical(String name) {
    final trimmed = name.trim();
    final aliased = aliases[trimmed.toLowerCase()] ?? trimmed;
    for (final candidate in all) {
      if (sameSkill(candidate, aliased)) return candidate;
    }
    return aliased;
  }
}
