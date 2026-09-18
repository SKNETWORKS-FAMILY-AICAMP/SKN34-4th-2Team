/// 이력서 작성 본문 — Firestore `content` 필드 매핑
class ResumeContent {
  const ResumeContent({
    this.basicInfo = const ResumeBasicInfo(),
    this.coreCompetencies = const ResumeCoreCompetencies(),
    this.experience = const [],
    this.education = const [],
    this.techStack = const [],
    this.certifications = const [],
    this.awards = const [],
    this.trainingExperience = const [],
    this.otherActivities = const [],
    this.projects = const [],
    this.selfIntroduction = const ResumeSelfIntroduction(),
  });

  final ResumeBasicInfo basicInfo;
  final ResumeCoreCompetencies coreCompetencies;
  final List<ResumeExperienceItem> experience;
  final List<ResumeEducationItem> education;
  final List<ResumeTechStackItem> techStack;
  final List<ResumeCertificationItem> certifications;
  final List<ResumeAwardItem> awards;
  final List<ResumeTrainingItem> trainingExperience;
  final List<ResumeActivityItem> otherActivities;
  final List<ResumeProjectItem> projects;
  final ResumeSelfIntroduction selfIntroduction;

  factory ResumeContent.empty() => const ResumeContent();

  /// 맞춤 공고 점수를 계산할 수 있는 직무 관련 근거가 있는지 여부.
  /// 기본정보만 입력된 상태는 매칭 가능한 이력서로 보지 않는다.
  bool get hasMatchingEvidence =>
      coreCompetencies.isFilled ||
      experience.any((item) => item.isFilled) ||
      techStack.any((item) => item.isFilled) ||
      projects.any((item) => item.isFilled);

  factory ResumeContent.fromMap(Map<String, dynamic>? map) {
    if (map == null || map.isEmpty) return ResumeContent.empty();
    return ResumeContent(
      basicInfo: ResumeBasicInfo.fromMap(
        map['basicInfo'] as Map<String, dynamic>?,
      ),
      coreCompetencies: ResumeCoreCompetencies.fromMap(
        map['coreCompetencies'] as Map<String, dynamic>?,
      ),
      experience: _listFrom(map['experience'], ResumeExperienceItem.fromMap),
      education: _listFrom(map['education'], ResumeEducationItem.fromMap),
      techStack: _listFrom(map['techStack'], ResumeTechStackItem.fromMap),
      certifications:
          _listFrom(map['certifications'], ResumeCertificationItem.fromMap),
      awards: _listFrom(map['awards'], ResumeAwardItem.fromMap),
      trainingExperience:
          _listFrom(map['trainingExperience'], ResumeTrainingItem.fromMap),
      otherActivities:
          _listFrom(map['otherActivities'], ResumeActivityItem.fromMap),
      projects: _listFrom(map['projects'], ResumeProjectItem.fromMap),
      selfIntroduction: ResumeSelfIntroduction.fromMap(
        map['selfIntroduction'] as Map<String, dynamic>?,
      ),
    );
  }

  Map<String, dynamic> toMap() => {
        'basicInfo': basicInfo.toMap(),
        'coreCompetencies': coreCompetencies.toMap(),
        'experience': experience.map((e) => e.toMap()).toList(),
        'education': education.map((e) => e.toMap()).toList(),
        'techStack': techStack.map((e) => e.toMap()).toList(),
        'certifications': certifications.map((e) => e.toMap()).toList(),
        'awards': awards.map((e) => e.toMap()).toList(),
        'trainingExperience':
            trainingExperience.map((e) => e.toMap()).toList(),
        'otherActivities': otherActivities.map((e) => e.toMap()).toList(),
        'projects': projects.map((e) => e.toMap()).toList(),
        'selfIntroduction': selfIntroduction.toMap(),
      };

  /// content 기반 섹션 완료 여부 계산
  Map<String, bool> computeSections() => {
        'basicInfo': basicInfo.isFilled,
        'coreCompetencies': coreCompetencies.isFilled,
        'experience': experience.any((e) => e.isFilled),
        'education': education.any((e) => e.isFilled),
        'techStack': techStack.any((e) => e.isFilled),
        'certifications': certifications.any((e) => e.isFilled),
        'awards': awards.any((e) => e.isFilled),
        'trainingExperience': trainingExperience.any((e) => e.isFilled),
        'otherActivities': otherActivities.any((e) => e.isFilled),
        'projects': projects.any((e) => e.isFilled),
        'selfIntroduction': selfIntroduction.isFilled,
      };

  ResumeContent copyWith({
    ResumeBasicInfo? basicInfo,
    ResumeCoreCompetencies? coreCompetencies,
    List<ResumeExperienceItem>? experience,
    List<ResumeEducationItem>? education,
    List<ResumeTechStackItem>? techStack,
    List<ResumeCertificationItem>? certifications,
    List<ResumeAwardItem>? awards,
    List<ResumeTrainingItem>? trainingExperience,
    List<ResumeActivityItem>? otherActivities,
    List<ResumeProjectItem>? projects,
    ResumeSelfIntroduction? selfIntroduction,
  }) {
    return ResumeContent(
      basicInfo: basicInfo ?? this.basicInfo,
      coreCompetencies: coreCompetencies ?? this.coreCompetencies,
      experience: experience ?? this.experience,
      education: education ?? this.education,
      techStack: techStack ?? this.techStack,
      certifications: certifications ?? this.certifications,
      awards: awards ?? this.awards,
      trainingExperience: trainingExperience ?? this.trainingExperience,
      otherActivities: otherActivities ?? this.otherActivities,
      projects: projects ?? this.projects,
      selfIntroduction: selfIntroduction ?? this.selfIntroduction,
    );
  }

  static List<T> _listFrom<T>(
    dynamic raw,
    T Function(Map<String, dynamic>) fromMap,
  ) {
    if (raw is! List) return [];
    return raw
        .whereType<Map>()
        .map((e) => fromMap(Map<String, dynamic>.from(e)))
        .toList();
  }
}

String newResumeItemId() =>
    DateTime.now().microsecondsSinceEpoch.toString();

class ResumeBasicInfo {
  const ResumeBasicInfo({
    this.name = '',
    this.phone = '',
    this.email = '',
    this.birthDate = '',
    this.githubUrl = '',
    this.blogUrl = '',
  });

  final String name;
  final String phone;
  final String email;
  final String birthDate;
  final String githubUrl;
  final String blogUrl;

  bool get isFilled =>
      name.trim().isNotEmpty && email.trim().isNotEmpty;

  factory ResumeBasicInfo.fromMap(Map<String, dynamic>? map) {
    if (map == null) return const ResumeBasicInfo();
    return ResumeBasicInfo(
      name: map['name'] as String? ?? '',
      phone: map['phone'] as String? ?? '',
      email: map['email'] as String? ?? '',
      birthDate: map['birthDate'] as String? ?? '',
      githubUrl: map['githubUrl'] as String? ?? '',
      blogUrl: map['blogUrl'] as String? ?? '',
    );
  }

  Map<String, dynamic> toMap() => {
        'name': name,
        'phone': phone,
        'email': email,
        'birthDate': birthDate,
        'githubUrl': githubUrl,
        'blogUrl': blogUrl,
      };

  ResumeBasicInfo copyWith({
    String? name,
    String? phone,
    String? email,
    String? birthDate,
    String? githubUrl,
    String? blogUrl,
  }) {
    return ResumeBasicInfo(
      name: name ?? this.name,
      phone: phone ?? this.phone,
      email: email ?? this.email,
      birthDate: birthDate ?? this.birthDate,
      githubUrl: githubUrl ?? this.githubUrl,
      blogUrl: blogUrl ?? this.blogUrl,
    );
  }
}

class ResumeCoreCompetencies {
  const ResumeCoreCompetencies({this.text = ''});
  final String text;

  bool get isFilled => text.trim().isNotEmpty;

  factory ResumeCoreCompetencies.fromMap(Map<String, dynamic>? map) {
    if (map == null) return const ResumeCoreCompetencies();
    return ResumeCoreCompetencies(text: map['text'] as String? ?? '');
  }

  Map<String, dynamic> toMap() => {'text': text};

  ResumeCoreCompetencies copyWith({String? text}) =>
      ResumeCoreCompetencies(text: text ?? this.text);
}

class ResumeExperienceItem {
  const ResumeExperienceItem({
    required this.id,
    this.company = '',
    this.role = '',
    this.startDate = '',
    this.endDate = '',
    this.isCurrent = false,
    this.description = '',
  });

  final String id;
  final String company;
  final String role;
  final String startDate;
  final String endDate;
  final bool isCurrent;
  final String description;

  bool get isFilled => company.trim().isNotEmpty;

  factory ResumeExperienceItem.empty() =>
      ResumeExperienceItem(id: newResumeItemId());

  factory ResumeExperienceItem.fromMap(Map<String, dynamic> map) {
    return ResumeExperienceItem(
      id: map['id'] as String? ?? newResumeItemId(),
      company: map['company'] as String? ?? '',
      role: map['role'] as String? ?? '',
      startDate: map['startDate'] as String? ?? '',
      endDate: map['endDate'] as String? ?? '',
      isCurrent: map['isCurrent'] as bool? ?? false,
      description: map['description'] as String? ?? '',
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'company': company,
        'role': role,
        'startDate': startDate,
        'endDate': endDate,
        'isCurrent': isCurrent,
        'description': description,
      };

  ResumeExperienceItem copyWith({
    String? company,
    String? role,
    String? startDate,
    String? endDate,
    bool? isCurrent,
    String? description,
  }) {
    return ResumeExperienceItem(
      id: id,
      company: company ?? this.company,
      role: role ?? this.role,
      startDate: startDate ?? this.startDate,
      endDate: endDate ?? this.endDate,
      isCurrent: isCurrent ?? this.isCurrent,
      description: description ?? this.description,
    );
  }
}

class ResumeEducationItem {
  const ResumeEducationItem({
    required this.id,
    this.school = '',
    this.major = '',
    this.startDate = '',
    this.endDate = '',
    this.status = '',
  });

  final String id;
  final String school;
  final String major;
  final String startDate;
  final String endDate;
  final String status;

  bool get isFilled => school.trim().isNotEmpty;

  factory ResumeEducationItem.empty() =>
      ResumeEducationItem(id: newResumeItemId());

  factory ResumeEducationItem.fromMap(Map<String, dynamic> map) {
    return ResumeEducationItem(
      id: map['id'] as String? ?? newResumeItemId(),
      school: map['school'] as String? ?? '',
      major: map['major'] as String? ?? '',
      startDate: map['startDate'] as String? ?? '',
      endDate: map['endDate'] as String? ?? '',
      status: map['status'] as String? ?? '',
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'school': school,
        'major': major,
        'startDate': startDate,
        'endDate': endDate,
        'status': status,
      };

  ResumeEducationItem copyWith({
    String? school,
    String? major,
    String? startDate,
    String? endDate,
    String? status,
  }) {
    return ResumeEducationItem(
      id: id,
      school: school ?? this.school,
      major: major ?? this.major,
      startDate: startDate ?? this.startDate,
      endDate: endDate ?? this.endDate,
      status: status ?? this.status,
    );
  }
}

class ResumeTechStackItem {
  const ResumeTechStackItem({
    required this.id,
    this.name = '',
    this.level = '',
  });

  final String id;
  final String name;
  final String level;

  bool get isFilled => name.trim().isNotEmpty;

  factory ResumeTechStackItem.empty() =>
      ResumeTechStackItem(id: newResumeItemId());

  factory ResumeTechStackItem.fromMap(Map<String, dynamic> map) {
    return ResumeTechStackItem(
      id: map['id'] as String? ?? newResumeItemId(),
      name: map['name'] as String? ?? '',
      level: map['level'] as String? ?? '',
    );
  }

  Map<String, dynamic> toMap() => {'id': id, 'name': name, 'level': level};

  ResumeTechStackItem copyWith({String? name, String? level}) {
    return ResumeTechStackItem(
      id: id,
      name: name ?? this.name,
      level: level ?? this.level,
    );
  }
}

class ResumeCertificationItem {
  const ResumeCertificationItem({
    required this.id,
    this.name = '',
    this.issuer = '',
    this.acquiredDate = '',
  });

  final String id;
  final String name;
  final String issuer;
  final String acquiredDate;

  bool get isFilled => name.trim().isNotEmpty;

  factory ResumeCertificationItem.empty() =>
      ResumeCertificationItem(id: newResumeItemId());

  factory ResumeCertificationItem.fromMap(Map<String, dynamic> map) {
    return ResumeCertificationItem(
      id: map['id'] as String? ?? newResumeItemId(),
      name: map['name'] as String? ?? '',
      issuer: map['issuer'] as String? ?? '',
      acquiredDate: map['acquiredDate'] as String? ?? '',
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'name': name,
        'issuer': issuer,
        'acquiredDate': acquiredDate,
      };

  ResumeCertificationItem copyWith({
    String? name,
    String? issuer,
    String? acquiredDate,
  }) {
    return ResumeCertificationItem(
      id: id,
      name: name ?? this.name,
      issuer: issuer ?? this.issuer,
      acquiredDate: acquiredDate ?? this.acquiredDate,
    );
  }
}

class ResumeAwardItem {
  const ResumeAwardItem({
    required this.id,
    this.name = '',
    this.organization = '',
    this.date = '',
    this.description = '',
  });

  final String id;
  final String name;
  final String organization;
  final String date;
  final String description;

  bool get isFilled => name.trim().isNotEmpty;

  factory ResumeAwardItem.empty() => ResumeAwardItem(id: newResumeItemId());

  factory ResumeAwardItem.fromMap(Map<String, dynamic> map) {
    return ResumeAwardItem(
      id: map['id'] as String? ?? newResumeItemId(),
      name: map['name'] as String? ?? '',
      organization: map['organization'] as String? ?? '',
      date: map['date'] as String? ?? '',
      description: map['description'] as String? ?? '',
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'name': name,
        'organization': organization,
        'date': date,
        'description': description,
      };

  ResumeAwardItem copyWith({
    String? name,
    String? organization,
    String? date,
    String? description,
  }) {
    return ResumeAwardItem(
      id: id,
      name: name ?? this.name,
      organization: organization ?? this.organization,
      date: date ?? this.date,
      description: description ?? this.description,
    );
  }
}

class ResumeTrainingItem {
  const ResumeTrainingItem({
    required this.id,
    this.course = '',
    this.organization = '',
    this.startDate = '',
    this.endDate = '',
    this.description = '',
  });

  final String id;
  final String course;
  final String organization;
  final String startDate;
  final String endDate;
  final String description;

  bool get isFilled => course.trim().isNotEmpty;

  factory ResumeTrainingItem.empty() =>
      ResumeTrainingItem(id: newResumeItemId());

  factory ResumeTrainingItem.fromMap(Map<String, dynamic> map) {
    return ResumeTrainingItem(
      id: map['id'] as String? ?? newResumeItemId(),
      course: map['course'] as String? ?? '',
      organization: map['organization'] as String? ?? '',
      startDate: map['startDate'] as String? ?? '',
      endDate: map['endDate'] as String? ?? '',
      description: map['description'] as String? ?? '',
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'course': course,
        'organization': organization,
        'startDate': startDate,
        'endDate': endDate,
        'description': description,
      };

  ResumeTrainingItem copyWith({
    String? course,
    String? organization,
    String? startDate,
    String? endDate,
    String? description,
  }) {
    return ResumeTrainingItem(
      id: id,
      course: course ?? this.course,
      organization: organization ?? this.organization,
      startDate: startDate ?? this.startDate,
      endDate: endDate ?? this.endDate,
      description: description ?? this.description,
    );
  }
}

class ResumeActivityItem {
  const ResumeActivityItem({
    required this.id,
    this.name = '',
    this.startDate = '',
    this.endDate = '',
    this.description = '',
  });

  final String id;
  final String name;
  final String startDate;
  final String endDate;
  final String description;

  bool get isFilled => name.trim().isNotEmpty;

  factory ResumeActivityItem.empty() =>
      ResumeActivityItem(id: newResumeItemId());

  factory ResumeActivityItem.fromMap(Map<String, dynamic> map) {
    return ResumeActivityItem(
      id: map['id'] as String? ?? newResumeItemId(),
      name: map['name'] as String? ?? '',
      startDate: map['startDate'] as String? ?? '',
      endDate: map['endDate'] as String? ?? '',
      description: map['description'] as String? ?? '',
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'name': name,
        'startDate': startDate,
        'endDate': endDate,
        'description': description,
      };

  ResumeActivityItem copyWith({
    String? name,
    String? startDate,
    String? endDate,
    String? description,
  }) {
    return ResumeActivityItem(
      id: id,
      name: name ?? this.name,
      startDate: startDate ?? this.startDate,
      endDate: endDate ?? this.endDate,
      description: description ?? this.description,
    );
  }
}

class ResumeProjectItem {
  const ResumeProjectItem({
    required this.id,
    this.name = '',
    this.startDate = '',
    this.endDate = '',
    this.role = '',
    this.techStack = '',
    this.description = '',
    this.url = '',
  });

  final String id;
  final String name;
  final String startDate;
  final String endDate;
  final String role;
  final String techStack;
  final String description;
  final String url;

  bool get isFilled => name.trim().isNotEmpty;

  factory ResumeProjectItem.empty() =>
      ResumeProjectItem(id: newResumeItemId());

  factory ResumeProjectItem.fromMap(Map<String, dynamic> map) {
    return ResumeProjectItem(
      id: map['id'] as String? ?? newResumeItemId(),
      name: map['name'] as String? ?? '',
      startDate: map['startDate'] as String? ?? '',
      endDate: map['endDate'] as String? ?? '',
      role: map['role'] as String? ?? '',
      techStack: map['techStack'] as String? ?? '',
      description: map['description'] as String? ?? '',
      url: map['url'] as String? ?? '',
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'name': name,
        'startDate': startDate,
        'endDate': endDate,
        'role': role,
        'techStack': techStack,
        'description': description,
        'url': url,
      };

  ResumeProjectItem copyWith({
    String? name,
    String? startDate,
    String? endDate,
    String? role,
    String? techStack,
    String? description,
    String? url,
  }) {
    return ResumeProjectItem(
      id: id,
      name: name ?? this.name,
      startDate: startDate ?? this.startDate,
      endDate: endDate ?? this.endDate,
      role: role ?? this.role,
      techStack: techStack ?? this.techStack,
      description: description ?? this.description,
      url: url ?? this.url,
    );
  }
}

class ResumeIntroSection {
  const ResumeIntroSection({this.subtitle = '', this.body = ''});

  final String subtitle;
  final String body;

  bool get isFilled => body.trim().isNotEmpty;

  factory ResumeIntroSection.fromMap(Map<String, dynamic>? map) {
    if (map == null) return const ResumeIntroSection();
    return ResumeIntroSection(
      subtitle: map['subtitle'] as String? ?? '',
      body: map['body'] as String? ?? '',
    );
  }

  Map<String, dynamic> toMap() => {'subtitle': subtitle, 'body': body};

  ResumeIntroSection copyWith({String? subtitle, String? body}) {
    return ResumeIntroSection(
      subtitle: subtitle ?? this.subtitle,
      body: body ?? this.body,
    );
  }
}

class ResumeSelfIntroduction {
  const ResumeSelfIntroduction({
    this.intro = const ResumeIntroSection(),
    this.motivation = const ResumeIntroSection(),
    this.challenge = const ResumeIntroSection(),
    this.growth = const ResumeIntroSection(),
    this.strengthsWeaknesses = const ResumeIntroSection(),
    this.aspiration = const ResumeIntroSection(),
  });

  final ResumeIntroSection intro;
  final ResumeIntroSection motivation;
  final ResumeIntroSection challenge;
  final ResumeIntroSection growth;
  final ResumeIntroSection strengthsWeaknesses;
  final ResumeIntroSection aspiration;

  bool get isFilled =>
      intro.isFilled ||
      motivation.isFilled ||
      challenge.isFilled ||
      growth.isFilled ||
      strengthsWeaknesses.isFilled ||
      aspiration.isFilled;

  factory ResumeSelfIntroduction.fromMap(Map<String, dynamic>? map) {
    if (map == null) return const ResumeSelfIntroduction();
    return ResumeSelfIntroduction(
      intro: ResumeIntroSection.fromMap(map['intro'] as Map<String, dynamic>?),
      motivation:
          ResumeIntroSection.fromMap(map['motivation'] as Map<String, dynamic>?),
      challenge:
          ResumeIntroSection.fromMap(map['challenge'] as Map<String, dynamic>?),
      growth: ResumeIntroSection.fromMap(map['growth'] as Map<String, dynamic>?),
      strengthsWeaknesses: ResumeIntroSection.fromMap(
        map['strengthsWeaknesses'] as Map<String, dynamic>?,
      ),
      aspiration:
          ResumeIntroSection.fromMap(map['aspiration'] as Map<String, dynamic>?),
    );
  }

  Map<String, dynamic> toMap() => {
        'intro': intro.toMap(),
        'motivation': motivation.toMap(),
        'challenge': challenge.toMap(),
        'growth': growth.toMap(),
        'strengthsWeaknesses': strengthsWeaknesses.toMap(),
        'aspiration': aspiration.toMap(),
      };

  ResumeIntroSection sectionByKey(String key) => switch (key) {
        'intro' => intro,
        'motivation' => motivation,
        'challenge' => challenge,
        'growth' => growth,
        'strengthsWeaknesses' => strengthsWeaknesses,
        'aspiration' => aspiration,
        _ => const ResumeIntroSection(),
      };

  ResumeSelfIntroduction copyWithSection(
    String key,
    ResumeIntroSection section,
  ) {
    return switch (key) {
      'intro' => copyWith(intro: section),
      'motivation' => copyWith(motivation: section),
      'challenge' => copyWith(challenge: section),
      'growth' => copyWith(growth: section),
      'strengthsWeaknesses' => copyWith(strengthsWeaknesses: section),
      'aspiration' => copyWith(aspiration: section),
      _ => this,
    };
  }

  ResumeSelfIntroduction copyWith({
    ResumeIntroSection? intro,
    ResumeIntroSection? motivation,
    ResumeIntroSection? challenge,
    ResumeIntroSection? growth,
    ResumeIntroSection? strengthsWeaknesses,
    ResumeIntroSection? aspiration,
  }) {
    return ResumeSelfIntroduction(
      intro: intro ?? this.intro,
      motivation: motivation ?? this.motivation,
      challenge: challenge ?? this.challenge,
      growth: growth ?? this.growth,
      strengthsWeaknesses: strengthsWeaknesses ?? this.strengthsWeaknesses,
      aspiration: aspiration ?? this.aspiration,
    );
  }
}

/// 자기소개서 하위 항목 라벨
abstract final class ResumeSelfIntroLabels {
  static const keys = [
    'intro',
    'motivation',
    'challenge',
    'growth',
    'strengthsWeaknesses',
    'aspiration',
  ];

  static const labels = {
    'intro': '자기소개',
    'motivation': '지원동기',
    'challenge': '직무와 관련된 경험 중 어려움을 극복한 사례',
    'growth': '성장과정',
    'strengthsWeaknesses': '직무와 관련된 성격의 장단점',
    'aspiration': '지원한 회사에 대한 포부',
  };
}
