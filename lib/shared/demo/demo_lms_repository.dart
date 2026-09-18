import 'dart:async';

import '../../core/constants/attendance_status.dart';
import '../../core/constants/cohort_status.dart';
import '../../core/constants/record_types.dart';
import '../../core/constants/role.dart';
import '../../core/utils/class_period_utils.dart';
import '../../features/resume/ai_coach/data/generated/resume_mocks.g.dart';
import '../models/assessment_model.dart';
import '../models/alert_popup_model.dart';
import '../models/curriculum_sheet_model.dart';
import '../models/inflearn_package_model.dart';
import '../models/study_source_model.dart';
import '../models/youtube_recommendation_model.dart';
import '../models/cohort_model.dart';
import '../models/domain_models.dart';
import '../models/notice_model.dart';
import '../models/form_task_model.dart';
import '../models/post_model.dart';
import '../models/resume_content.dart';
import '../models/resume_model.dart';
import '../models/submission_model.dart';
import '../models/todo_model.dart';
import '../models/user_model.dart';
import 'demo_accounts.dart';
import 'demo_session.dart';

/// Firebase 대신 메모리 데이터를 제공하는 Demo Repository
class DemoLmsRepository {
  DemoLmsRepository() {
    _seed();
    _emit();
  }

  final _todoController = StreamController<List<TodoModel>>.broadcast();
  final _postController = StreamController<List<PostModel>>.broadcast();
  final _submissionController =
      StreamController<List<SubmissionModel>>.broadcast();
  final _assessmentController =
      StreamController<List<AssessmentModel>>.broadcast();
  final _inflearnPackageController =
      StreamController<List<InflearnPackageModel>>.broadcast();
  final _youtubeRecommendationController =
      StreamController<List<YoutubeRecommendationModel>>.broadcast();
  final _assessmentSubmissionController =
      StreamController<List<AssessmentSubmissionModel>>.broadcast();
  final _curriculumSheetController =
      StreamController<List<CurriculumSheetModel>>.broadcast();

  late List<TodoModel> _todos;
  late List<PostModel> _posts;
  late List<NoticeModel> _notices;
  late List<SubmissionModel> _submissions;
  late List<ResumeModel> _resumes;
  late List<AttendanceModel> _attendances;
  late List<MileageTransactionModel> _mileageTx;
  late List<AssessmentModel> _assessments;
  late Map<String, List<AssessmentQuestionModel>> _assessmentQuestions;
  late List<AssessmentSubmissionModel> _assessmentSubmissions;
  late List<InflearnPackageModel> _inflearnPackages;
  late List<YoutubeRecommendationModel> _youtubeRecommendations;
  late List<CurriculumSheetModel> _curriculumSheets;
  late List<FormTaskModel> _formTasks;
  final Map<String, List<FormResponseModel>> _formResponses = {};
  late List<AlertPopupModel> _alertPopups;

  void _seed() {
    _todos = [];
    _posts = [];
    _notices = [];
    // 관리자 시연에서 승인·반려 흐름을 보여 줄 대기 기록. 이름은 예시다.
    final now = DateTime.now();
    _submissions = [
      SubmissionModel(
        id: 'sub-demo-1',
        userId: 'demo-student-002',
        userDisplayName: '김하늘',
        title: 'PCCP Lv.2 취득',
        type: RecordTypes.certification,
        status: 'pending',
        certType: 'PCCP',
        submittedAt: now.subtract(const Duration(hours: 3)),
      ),
      SubmissionModel(
        id: 'sub-demo-2',
        userId: 'demo-student-003',
        userDisplayName: '이도윤',
        title: 'Pandas groupby 정리',
        type: RecordTypes.blog,
        status: 'pending',
        link: 'https://velog.io/@example/pandas-groupby',
        submittedAt: now.subtract(const Duration(hours: 20)),
      ),
      SubmissionModel(
        id: 'sub-demo-3',
        userId: DemoAccounts.studentUid,
        userDisplayName: DemoAccounts.student.displayName,
        title: 'SQL 스터디 3주차',
        type: RecordTypes.study,
        status: 'pending',
        weekNumber: 3,
        weekLabel: '3주차',
        isTeamStudy: true,
        submittedAt: now.subtract(const Duration(days: 1, hours: 2)),
      ),
      SubmissionModel(
        id: 'sub-demo-4',
        userId: 'demo-student-004',
        userDisplayName: '박서연',
        title: 'SQLD 합격',
        type: RecordTypes.certification,
        status: 'approved',
        certType: 'SQLD',
        mileageGranted: true,
        submittedAt: now.subtract(const Duration(days: 3)),
      ),
    ];
    // AI 코치(맞춤 공고 추천·첨삭)를 보여 줄 수 있도록 데이터 직무 목업 이력서로 채운다.
    // 연락처는 비워 두어 시연에서 직접 입력하는 모습을 보인다.
    final demoResumeContent = resumeMockPersonas
        .firstWhere((p) => p.key == 'data_entry_junior_college')
        .toContent(
          name: DemoAccounts.student.displayName,
          email: DemoAccounts.student.personalEmail ?? '',
        );
    final seededContent = demoResumeContent.copyWith(
      basicInfo: demoResumeContent.basicInfo.copyWith(phone: ''),
    );
    // 피드백을 요청한 이력서는 편집 화면 오른쪽에 AI 코치 대신 피드백 패널이 뜬다.
    // 그래서 학생 시연용 기본 이력서는 작성 중으로 두고, 강사·관리자가 검토할
    // 피드백 요청 이력서를 따로 하나 둔다.
    _resumes = [
      ResumeModel(
        id: 'r-demo-1',
        userId: DemoAccounts.studentUid,
        title: '데이터 분석가 지원 이력서',
        status: 'draft',
        content: seededContent,
        sections: seededContent.computeSections(),
        isBaseResume: true,
        revisionCount: 1,
        updatedAt: now.subtract(const Duration(hours: 5)),
      ),
      ResumeModel(
        id: 'r-demo-2',
        userId: DemoAccounts.studentUid,
        title: '데이터 엔지니어 지원 이력서',
        status: 'submitted',
        content: demoResumeContent,
        sections: demoResumeContent.computeSections(),
        revisionCount: 1,
        updatedAt: now.subtract(const Duration(days: 1)),
      ),
    ];
    _attendances = [];
    _mileageTx = [];
    _assessments = [
      AssessmentModel(
        id: 'a1',
        title: '34기 2차 성취도평가',
        tags: const ['데이터 분석', '머신러닝/딥러닝'],
        questionCount: 2,
        maxScore: 10,
        startAt: DateTime(2026, 7, 1),
        endAt: DateTime(2026, 12, 31),
        published: true,
        createdAt: DateTime(2026, 6, 20),
        thumbnailUrl: null,
      ),
      AssessmentModel(
        id: 'a2',
        title: '34기 1차 성취도평가',
        tags: const ['Python', '기초'],
        questionCount: 2,
        maxScore: 10,
        startAt: DateTime(2026, 5, 1),
        endAt: DateTime(2026, 6, 30),
        published: true,
        createdAt: DateTime(2026, 4, 20),
      ),
    ];
    _assessmentQuestions = {
      'a1': [
        const AssessmentQuestionModel(
          id: 'q1',
          order: 0,
          type: AssessmentQuestionType.multipleChoice,
          prompt: '과적합(overfitting)을 줄이는 방법으로 적절한 것은?',
          points: 5,
          choices: ['학습 데이터를 줄인다', '정규화를 사용한다', '에폭을 무한히 늘린다', '검증셋을 제거한다'],
          correctIndex: 1,
        ),
        const AssessmentQuestionModel(
          id: 'q2',
          order: 1,
          type: AssessmentQuestionType.shortAnswer,
          prompt: '지도학습에서 정답 레이블을 영어 한 단어로 쓰면?',
          points: 5,
          acceptedAnswers: ['label', 'labels'],
        ),
      ],
      'a2': [
        const AssessmentQuestionModel(
          id: 'q1',
          order: 0,
          type: AssessmentQuestionType.multipleChoice,
          prompt: 'Python에서 리스트를 만드는 기호는?',
          points: 5,
          choices: ['()', '[]', '{}', '<>'],
          correctIndex: 1,
        ),
        const AssessmentQuestionModel(
          id: 'q2',
          order: 1,
          type: AssessmentQuestionType.shortAnswer,
          prompt: 'None 타입을 나타내는 키워드는?',
          points: 5,
          acceptedAnswers: ['None'],
        ),
      ],
    };
    _inflearnPackages = [
      InflearnPackageModel(
        id: 'pkg1',
        title: '프로그래밍과 데이터 기초 예복습',
        subject: '프로그래밍과 데이터 기초',
        type: InflearnPackageType.review,
        summary: '첫번째 교과목 예복습에 필요한 6개 강의입니다. 파이썬 기초를 반복 학습해 주세요.',
        isPublished: true,
        sortOrder: 1,
        publishedAt: DateTime(2026, 7, 4),
        units: const [
          InflearnUnitModel(
            name: 'Python',
            courses: [
              InflearnCourseModel(
                title: '단 60분! 파이썬 핵심 개념 초압축 강의',
                url: 'https://www.inflearn.com',
              ),
              InflearnCourseModel(
                title: '문과생도, 비전공자도, 누구나 배울 수 있는 파이썬(Python)!',
                url: 'https://www.inflearn.com',
              ),
            ],
          ),
          InflearnUnitModel(
            name: 'Data base',
            courses: [
              InflearnCourseModel(
                title: 'Do it! SQL 입문',
                url: 'https://www.inflearn.com',
              ),
              InflearnCourseModel(
                title: '초보자를 위한 BigQuery(SQL) 입문',
                url: 'https://www.inflearn.com',
              ),
            ],
          ),
          InflearnUnitModel(
            name: 'Web Crawling',
            courses: [
              InflearnCourseModel(
                title: '[신규 개정판] 이것이 진짜 크롤링이다 - 기본편',
                url: 'https://www.inflearn.com',
              ),
              InflearnCourseModel(
                title: '[Python 실전] 웹크롤링과 데이터분석',
                url: 'https://www.inflearn.com',
              ),
            ],
          ),
        ],
      ),
      InflearnPackageModel(
        id: 'pkg2',
        title: 'LLM 미리보기',
        subject: 'LLM',
        type: InflearnPackageType.bonus,
        summary: '다가올 LLM 교과목 예습용 강의입니다.',
        isPublished: true,
        sortOrder: 3,
        publishedAt: DateTime(2026, 7, 4),
        courses: const [
          InflearnCourseModel(
            title: '입문자를 위한 LangChain 기초',
            url: 'https://www.inflearn.com',
          ),
          InflearnCourseModel(
            title: 'TypeScript로 시작하는 LangChain - LLM & RAG 입문',
            url: 'https://www.inflearn.com',
          ),
        ],
      ),
    ];
    _youtubeRecommendations = [
      YoutubeRecommendationModel(
        id: 'yt1',
        title: 'Flutter 입문 — 30분 핵심 정리',
        youtubeUrl: 'https://www.youtube.com/watch?v=VPvVD8t02U8',
        videoId: 'VPvVD8t02U8',
        tags: const ['Flutter', 'Dart'],
        description: 'Flutter 위젯·상태관리 입문 영상',
        isPublished: true,
        sortOrder: 1,
        createdAt: DateTime(2026, 7, 1),
      ),
      YoutubeRecommendationModel(
        id: 'yt2',
        title: 'Python 기초 — 변수와 자료형',
        youtubeUrl: 'https://www.youtube.com/watch?v=kqtD5dpn9C8',
        videoId: 'kqtD5dpn9C8',
        tags: const ['Python', 'Django', 'FastAPI'],
        description: '파이썬 문법 기초',
        isPublished: true,
        sortOrder: 2,
        createdAt: DateTime(2026, 7, 1),
      ),
      YoutubeRecommendationModel(
        id: 'yt3',
        title: 'SQL 입문 — SELECT부터 JOIN까지',
        youtubeUrl: 'https://www.youtube.com/watch?v=HXV3zeQKqGY',
        videoId: 'HXV3zeQKqGY',
        tags: const ['SQL', 'MySQL', 'PostgreSQL'],
        description: 'SQL 기초 쿼리',
        isPublished: true,
        sortOrder: 3,
        createdAt: DateTime(2026, 7, 1),
      ),
      YoutubeRecommendationModel(
        id: 'yt4',
        title: 'Docker 컨테이너 개념 한눈에',
        youtubeUrl: 'https://www.youtube.com/watch?v=fqMOX6JJhGo',
        videoId: 'fqMOX6JJhGo',
        tags: const ['Docker', 'CI/CD', 'AWS'],
        description: 'Docker 입문',
        isPublished: true,
        sortOrder: 4,
        createdAt: DateTime(2026, 7, 1),
      ),
    ];
    _assessmentSubmissions = [
      AssessmentSubmissionModel(
        id: 'a1_${DemoAccounts.studentUid}',
        assessmentId: 'a1',
        userId: DemoAccounts.studentUid,
        userDisplayName: DemoAccounts.student.displayName,
        answers: {
          'q1': const AssessmentAnswerEntry(
            value: 1,
            autoScore: 5,
            finalScore: 5,
            isCorrect: true,
          ),
          'q2': const AssessmentAnswerEntry(
            value: 'label',
            autoScore: 5,
            finalScore: 5,
            isCorrect: true,
          ),
        },
        autoTotalScore: 10,
        totalScore: 10,
        submittedAt: DateTime(2026, 8, 10),
      ),
    ];
    _curriculumSheets = [
      CurriculumSheetModel(
        id: 'cs1',
        title: '34기 커리큘럼',
        fileName: 'curriculum_34.csv',
        uploadedBy: DemoAccounts.instructorUid,
        uploadedByName: DemoAccounts.instructor.displayName,
        uploadedAt: DateTime(2026, 6, 1),
        rows: const [
          CurriculumRowModel(
            dayIndex: 1,
            dateLabel: '2026년 6월 16일 화요일',
            subject: '프로그래밍과 데이터 기초',
            topic: 'Python',
            detail: '변수, 자료형, 조건문, 반복문',
            order: 0,
          ),
          CurriculumRowModel(
            dayIndex: 2,
            dateLabel: '2026년 6월 17일 수요일',
            subject: '프로그래밍과 데이터 기초',
            topic: 'Python',
            detail: '함수, 모듈, 파일 I/O',
            order: 1,
          ),
          CurriculumRowModel(
            dayIndex: 8,
            dateLabel: '2026년 6월 25일 목요일',
            subject: '프로그래밍과 데이터 기초',
            topic: 'Database',
            detail: 'SQL 기초, JOIN',
            order: 2,
          ),
          CurriculumRowModel(
            dayIndex: 11,
            dateLabel: '2026년 6월 30일 화요일',
            subject: '프로그래밍과 데이터 기초',
            topic: 'Web Crawling',
            detail: 'requests, BeautifulSoup',
            order: 3,
          ),
        ],
      ),
    ];
    _alertPopups = [];
    _formTasks = [
      FormTaskModel(
        id: 'form1',
        title: '34기 OT 참여 설문',
        description: '온보딩 설문입니다. 노션 가이드를 참고해 작성해 주세요.',
        formUrl: 'https://docs.google.com/forms/d/e/example/viewform',
        notionGuideUrl: 'https://notion.so/example-guide',
        dueAt: DateTime.now().add(const Duration(days: 7)),
        published: true,
        createdAt: DateTime.now(),
      ),
    ];
    _formResponses.clear();
  }

  void _emit() {
    if (!_todoController.isClosed) _todoController.add(List.from(_todos));
    if (!_postController.isClosed) _postController.add(List.from(_posts));
    if (!_submissionController.isClosed) {
      _submissionController.add(List.from(_submissions));
    }
    if (!_assessmentController.isClosed) {
      _assessmentController.add(List.from(_assessments));
    }
    if (!_inflearnPackageController.isClosed) {
      _inflearnPackageController.add(List.from(_inflearnPackages));
    }
    if (!_youtubeRecommendationController.isClosed) {
      _youtubeRecommendationController.add(List.from(_youtubeRecommendations));
    }
    if (!_assessmentSubmissionController.isClosed) {
      _assessmentSubmissionController.add(List.from(_assessmentSubmissions));
    }
    if (!_curriculumSheetController.isClosed) {
      _curriculumSheetController.add(List.from(_curriculumSheets));
    }
  }

  /// broadcast 스트림은 구독 전에 보낸 값을 다시 주지 않는다. 화면이 늦게 구독해도
  /// 로딩에 멈추지 않도록 현재 값을 앞에 붙인다.
  Stream<T> _startWith<T>(T current, Stream<T> updates) async* {
    yield current;
    yield* updates;
  }

  Stream<List<TodoModel>> watchTodos(String uid) =>
      _startWith(List.of(_todos), _todoController.stream);

  Future<void> addTodo(String uid, String title) async {
    _todos.insert(
      0,
      TodoModel(
        id: 't${_todos.length}',
        title: title,
        isCompleted: false,
        createdAt: DateTime.now(),
      ),
    );
    _emit();
  }

  Future<void> toggleTodo(String uid, TodoModel todo) async {
    final i = _todos.indexWhere((t) => t.id == todo.id);
    if (i >= 0) {
      _todos[i] = TodoModel(
        id: todo.id,
        title: todo.title,
        isCompleted: !todo.isCompleted,
        createdAt: todo.createdAt,
      );
      _emit();
    }
  }

  Future<void> deleteTodo(String uid, String todoId) async {
    _todos.removeWhere((t) => t.id == todoId);
    _emit();
  }

  Stream<List<PostModel>> watchPosts(String cohortId, {int limit = 20}) =>
      _startWith(List.of(_posts), _postController.stream);

  Future<void> createPost({
    required String cohortId,
    required String authorId,
    required String authorName,
    required String content,
  }) async {
    _posts.insert(
      0,
      PostModel(
        id: 'p${_posts.length}',
        authorId: authorId,
        authorName: authorName,
        content: content,
        createdAt: DateTime.now(),
      ),
    );
    _emit();
  }

  Future<void> deletePost(String cohortId, String postId) async {
    _posts.removeWhere((p) => p.id == postId);
    _emit();
  }

  Stream<List<NoticeModel>> watchNotices(String cohortId) async* {
    yield _notices;
  }

  Stream<List<AlertPopupModel>> watchAlertPopups(String cohortId) async* {
    yield List.of(_alertPopups);
  }

  Stream<List<AlertPopupModel>> watchActiveAlertPopups(String cohortId) async* {
    yield _alertPopups.where((p) => p.isActive).toList();
  }

  Future<String> createAlertPopup({
    required String cohortId,
    required AlertPopupModel popup,
    required String authorId,
    required String authorName,
  }) async {
    final id = 'ap${_alertPopups.length}';
    _alertPopups.add(
      popup.copyWith(
        id: id,
        authorId: authorId,
        authorName: authorName,
        createdAt: DateTime.now(),
      ),
    );
    return id;
  }

  Future<void> updateAlertPopup({
    required String cohortId,
    required AlertPopupModel popup,
    required String authorId,
    required String authorName,
  }) async {
    final i = _alertPopups.indexWhere((p) => p.id == popup.id);
    if (i < 0) return;
    _alertPopups[i] = popup.copyWith(
      authorId: authorId,
      authorName: authorName,
      updatedAt: DateTime.now(),
      clearStartTime: popup.startTime == null,
      clearEndTime: popup.endTime == null,
    );
  }

  Future<void> toggleAlertPopupActive({
    required String cohortId,
    required String popupId,
    required bool isActive,
  }) async {
    final i = _alertPopups.indexWhere((p) => p.id == popupId);
    if (i < 0) return;
    _alertPopups[i] = _alertPopups[i].copyWith(isActive: isActive);
  }

  Future<void> deleteAlertPopup(String cohortId, String popupId) async {
    _alertPopups.removeWhere((p) => p.id == popupId);
  }

  final Map<String, Map<String, String>> _alertPopupDismissals = {};

  Stream<Map<String, String>> watchAlertPopupDismissals(String uid) async* {
    yield Map.of(_alertPopupDismissals[uid] ?? const {});
  }

  Future<void> dismissAlertPopupToday({
    required String uid,
    required String popupId,
    required String dateKey,
  }) async {
    final map = _alertPopupDismissals.putIfAbsent(uid, () => {});
    map[popupId] = dateKey;
  }

  Future<String> createNotice({
    required String cohortId,
    required NoticeModel notice,
    required String authorId,
    required String authorName,
  }) async {
    _notices.insert(
      0,
      NoticeModel(
        id: 'n${_notices.length}',
        title: notice.title,
        content: notice.content,
        authorName: authorName,
        isFavorite: notice.isFavorite,
        createdAt: DateTime.now(),
      ),
    );
    return 'n${_notices.length - 1}';
  }

  Stream<List<SubmissionModel>> watchMySubmissions(
    String cohortId,
    String userId,
  ) {
    return _startWith(
      List.of(_submissions),
      _submissionController.stream,
    ).map((list) => list.where((s) => s.userId == userId).toList());
  }

  Stream<List<SubmissionModel>> watchAllSubmissions(String cohortId) {
    return _startWith(List.of(_submissions), _submissionController.stream);
  }

  Future<String> createSubmission({
    required String cohortId,
    required SubmissionModel submission,
  }) async {
    final id = submission.id.isNotEmpty
        ? submission.id
        : 'sub${_submissions.length}';
    _submissions.insert(
      0,
      SubmissionModel(
        id: id,
        userId: submission.userId,
        userDisplayName: submission.userDisplayName,
        title: submission.title,
        type: submission.type,
        status: submission.status,
        submittedAt: DateTime.now(),
        certType: submission.certType,
        fileUrls: submission.fileUrls,
        startAt: submission.startAt,
        endAt: submission.endAt,
        weekNumber: submission.weekNumber,
        weekLabel: submission.weekLabel,
        link: submission.link,
      ),
    );
    _emit();
    return id;
  }

  Future<void> reviewSubmission({
    required String cohortId,
    required String submissionId,
    required String status,
    String? reviewComment,
  }) async {
    final i = _submissions.indexWhere((s) => s.id == submissionId);
    if (i < 0) return;
    final s = _submissions[i];
    _submissions[i] = SubmissionModel(
      id: s.id,
      userId: s.userId,
      userDisplayName: s.userDisplayName,
      title: s.title,
      type: s.type,
      status: status,
      submittedAt: s.submittedAt,
      reviewComment: reviewComment,
      certType: s.certType,
      fileUrls: s.fileUrls,
      startAt: s.startAt,
      endAt: s.endAt,
      weekNumber: s.weekNumber,
      weekLabel: s.weekLabel,
      link: s.link,
      quizScore: s.quizScore,
      learningDate: s.learningDate,
      learningContent: s.learningContent,
      isTeamStudy: s.isTeamStudy,
      mileageGranted: status == 'approved' ? true : s.mileageGranted,
      mileageAmount: s.mileageAmount,
    );
    _emit();
  }

  Stream<WeeklyTaskModel?> watchCurrentWeeklyTask(String cohortId) async* {
    yield null;
  }

  Stream<UserProgressModel?> watchUserProgress(
    String cohortId,
    String userId,
  ) async* {
    yield null;
  }

  static final _demoCohorts = [
    CohortModel(
      cohortId: 'cohort_34',
      name: 'SK네트웍스 Family AI 캠프 34기',
      termNumber: 34,
      status: CohortStatus.active,
      studentCount: 1,
      startDate: DateTime(2026, 5, 1),
      endDate: DateTime(2026, 12, 31),
    ),
    CohortModel(
      cohortId: 'cohort_35',
      name: 'SK네트웍스 Family AI 캠프 35기',
      termNumber: 35,
      status: CohortStatus.upcoming,
      studentCount: 0,
      startDate: DateTime(2027, 1, 1),
      endDate: DateTime(2027, 8, 31),
    ),
  ];

  Stream<List<CohortModel>> watchCohorts() async* {
    yield _demoCohorts.where((c) => c.isSelectable).toList();
  }

  Stream<List<CohortModel>> watchAllCohorts() async* {
    yield List.from(_demoCohorts);
  }

  Future<String> createCohort(CohortModel cohort) async {
    _demoCohorts.insert(0, cohort);
    return cohort.cohortId;
  }

  Future<void> updateCohort(CohortModel cohort) async {
    final i = _demoCohorts.indexWhere((c) => c.cohortId == cohort.cohortId);
    if (i >= 0) _demoCohorts[i] = cohort;
  }

  Stream<List<CohortWithResumes>> watchAllCohortsWithResumes() async* {
    yield [
      CohortWithResumes(cohort: _demoCohorts[0], resumes: List.from(_resumes)),
      CohortWithResumes(cohort: _demoCohorts[1], resumes: const []),
    ];
  }

  Stream<List<ResumeModel>> watchMyResumes(
    String cohortId,
    String userId,
  ) async* {
    yield _resumes.where((r) => r.userId == userId).toList();
  }

  Stream<List<ResumeModel>> watchCohortResumes(String cohortId) async* {
    yield _resumes;
  }

  Future<String> createResume({
    required String cohortId,
    required String userId,
    required String title,
    bool isBaseResume = false,
  }) async {
    final id = 'r${_resumes.length}';
    _resumes.add(
      ResumeModel(
        id: id,
        userId: userId,
        title: title,
        status: 'writing',
        sections: const {},
        isBaseResume: isBaseResume,
      ),
    );
    return id;
  }

  Future<void> setBaseResume({
    required String cohortId,
    required String userId,
    required String resumeId,
  }) async {
    for (var index = 0; index < _resumes.length; index++) {
      final resume = _resumes[index];
      if (resume.userId == userId) {
        _resumes[index] = resume.copyWith(isBaseResume: resume.id == resumeId);
      }
    }
    _emit();
  }

  Future<void> updateResumeSections({
    required String cohortId,
    required String resumeId,
    required Map<String, bool> sections,
    required String status,
  }) async {
    await updateResume(
      cohortId: cohortId,
      resumeId: resumeId,
      sections: sections,
      status: status,
    );
  }

  Stream<ResumeModel?> watchResume(String cohortId, String resumeId) async* {
    yield _findResume(resumeId);
  }

  ResumeModel? _findResume(String resumeId) {
    try {
      return _resumes.firstWhere((r) => r.id == resumeId);
    } catch (_) {
      return null;
    }
  }

  Future<void> updateResume({
    required String cohortId,
    required String resumeId,
    String? title,
    ResumeContent? content,
    Map<String, bool>? sections,
    String? status,
    bool incrementRevision = false,
  }) async {
    final i = _resumes.indexWhere((r) => r.id == resumeId);
    if (i < 0) return;
    final current = _resumes[i];
    final newContent = content ?? current.content;
    _resumes[i] = current.copyWith(
      title: title,
      content: newContent,
      sections: sections ?? newContent.computeSections(),
      status: status,
      revisionCount: incrementRevision
          ? current.revisionCount + 1
          : current.revisionCount,
    );
  }

  /// Firebase 구현과 동일하게 승인 전 이력서의 생년월일을 프로필 값으로 맞춘다.
  Future<int> syncBirthDateToMyResumes({
    required String cohortId,
    required String userId,
    required String birthDate,
  }) async {
    final normalized = birthDate.trim();
    if (normalized.isEmpty) return 0;
    var updated = 0;
    for (var i = 0; i < _resumes.length; i++) {
      final resume = _resumes[i];
      if (resume.userId != userId ||
          resume.isApproved ||
          resume.content.basicInfo.birthDate == normalized) {
        continue;
      }
      _resumes[i] = resume.copyWith(
        content: resume.content.copyWith(
          basicInfo: resume.content.basicInfo.copyWith(birthDate: normalized),
        ),
      );
      updated++;
    }
    if (updated > 0) _emit();
    return updated;
  }

  Future<void> approveResume({
    required String cohortId,
    required String resumeId,
  }) async {
    await updateResume(
      cohortId: cohortId,
      resumeId: resumeId,
      status: 'approved',
    );
  }

  Future<void> deleteResume(String cohortId, String resumeId) async {
    _resumes.removeWhere((r) => r.id == resumeId);
  }

  Stream<List<ResumeFeedbackModel>> watchResumeFeedback(
    String cohortId,
    String resumeId,
  ) async* {
    yield [];
  }

  Future<void> addResumeFeedback({
    required String cohortId,
    required String resumeId,
    required ResumeFeedbackModel feedback,
    required String authorId,
    required String authorName,
  }) async {
    final i = _resumes.indexWhere((r) => r.id == resumeId);
    if (i < 0) return;
    final current = _resumes[i];
    _resumes[i] = current.copyWith(
      feedbackCount: current.feedbackCount + 1,
    );
  }

  Future<void> deleteResumeFeedback({
    required String cohortId,
    required String resumeId,
    required String feedbackId,
  }) async {
    final i = _resumes.indexWhere((r) => r.id == resumeId);
    if (i < 0) return;
    final current = _resumes[i];
    _resumes[i] = current.copyWith(
      feedbackCount: current.feedbackCount > 0 ? current.feedbackCount - 1 : 0,
    );
  }

  Future<void> markResumeFeedbackRead({
    required String cohortId,
    required String resumeId,
    required List<String> feedbackIds,
    required bool asReviewer,
    String? viewerId,
  }) async {
    final i = _resumes.indexWhere((r) => r.id == resumeId);
    if (i < 0 || feedbackIds.isEmpty) return;
    final before = asReviewer
        ? _resumes[i].reviewerReadFeedbackIds
        : _resumes[i].readFeedbackIds;
    final after = {
      ...before,
      for (final id in feedbackIds)
        asReviewer ? reviewerReadKey(viewerId, id) : id,
    }.toList();
    _resumes[i] = asReviewer
        ? _resumes[i].copyWith(reviewerReadFeedbackIds: after)
        : _resumes[i].copyWith(readFeedbackIds: after);
  }

  Future<void> markResumeFeedbackSeen({
    required String cohortId,
    required String resumeId,
    required int feedbackCount,
  }) async {
    final i = _resumes.indexWhere((r) => r.id == resumeId);
    if (i < 0) return;
    _resumes[i] = _resumes[i].copyWith(lastSeenFeedbackCount: feedbackCount);
  }

  Stream<List<AttendanceModel>> watchUserAttendances(
    String cohortId,
    String userId,
  ) async* {
    yield _attendances.where((a) => a.userId == userId).toList();
  }

  Stream<List<AttendanceModel>> watchMyAttendances(
    String cohortId,
    String userId,
  ) async* {
    yield _attendances.where((a) => a.userId == userId).toList();
  }

  Stream<List<UserModel>> watchCohortStudents(String cohortId) async* {
    yield [
      DemoAccounts.student,
      // 자리 확인·출석부 시연용 예시 학생. 기록실 예시 기록의 제출자와 같다.
      for (final (uid, name) in const [
        ('demo-student-002', '김하늘'),
        ('demo-student-003', '이도윤'),
        ('demo-student-004', '박서연'),
      ])
        UserModel(
          uid: uid,
          email: '$uid@playdata.co.kr',
          displayName: name,
          role: UserRole.student,
          cohortId: DemoConfig.cohortId,
          cohortName: DemoConfig.cohortName,
        ),
    ];
  }

  Stream<List<UserModel>> watchInstructors() async* {
    yield [DemoAccounts.instructor];
  }

  Stream<List<AttendanceModel>> watchAttendancesByDate(
    String cohortId,
    String dateKey,
  ) async* {
    yield _attendances.where((a) => a.dateKey == dateKey).toList();
  }

  final Map<String, Set<String>> _rollCallConfirmed = {};
  final Map<String, Set<String>> _rollCallHeld = {};
  final Set<String> _rollCallDocs = {};

  String _rollCallKey(String cohortId, String dateKey, String periodId) =>
      '$cohortId|$dateKey|$periodId';

  /// 확인·보류를 누르면 화면의 집계가 바로 바뀌도록 변경을 알린다.
  final _rollCallChanges = StreamController<void>.broadcast();

  Stream<Set<String>> watchRollCallConfirmed(
    String cohortId,
    String dateKey,
    String periodId,
  ) async* {
    final key = _rollCallKey(cohortId, dateKey, periodId);
    yield Set.of(_rollCallConfirmed[key] ?? const {});
    await for (final _ in _rollCallChanges.stream) {
      yield Set.of(_rollCallConfirmed[key] ?? const {});
    }
  }

  Stream<Set<String>> watchRollCallHeld(
    String cohortId,
    String dateKey,
    String periodId,
  ) async* {
    final key = _rollCallKey(cohortId, dateKey, periodId);
    yield Set.of(_rollCallHeld[key] ?? const {});
    await for (final _ in _rollCallChanges.stream) {
      yield Set.of(_rollCallHeld[key] ?? const {});
    }
  }

  Future<void> ensureRollCallCarriedForward({
    required String cohortId,
    required String dateKey,
    required String periodId,
    required String updatedBy,
  }) async {
    final key = _rollCallKey(cohortId, dateKey, periodId);
    if (_rollCallDocs.contains(key)) return;

    var prev = ClassPeriodUtils.previousPeriod(periodId);
    while (prev != null) {
      final prevKey = _rollCallKey(cohortId, dateKey, prev.id);
      if (_rollCallDocs.contains(prevKey)) {
        _rollCallConfirmed[key] = Set<String>.of(
          _rollCallConfirmed[prevKey] ?? const {},
        );
        _rollCallHeld[key] = <String>{};
        _rollCallDocs.add(key);
        return;
      }
      prev = ClassPeriodUtils.previousPeriod(prev.id);
    }
  }

  Future<void> setRollCallConfirmed({
    required String cohortId,
    required String dateKey,
    required String periodId,
    required String userId,
    required bool confirmed,
    required String updatedBy,
  }) async {
    await ensureRollCallCarriedForward(
      cohortId: cohortId,
      dateKey: dateKey,
      periodId: periodId,
      updatedBy: updatedBy,
    );
    final key = _rollCallKey(cohortId, dateKey, periodId);
    _rollCallDocs.add(key);
    final set = _rollCallConfirmed.putIfAbsent(key, () => <String>{});
    final held = _rollCallHeld.putIfAbsent(key, () => <String>{});
    if (confirmed) {
      set.add(userId);
      held.remove(userId);
    } else {
      set.remove(userId);
    }
    _rollCallChanges.add(null);
  }

  Future<void> setRollCallHeld({
    required String cohortId,
    required String dateKey,
    required String periodId,
    required String userId,
    required bool held,
    required String updatedBy,
  }) async {
    await ensureRollCallCarriedForward(
      cohortId: cohortId,
      dateKey: dateKey,
      periodId: periodId,
      updatedBy: updatedBy,
    );
    final key = _rollCallKey(cohortId, dateKey, periodId);
    _rollCallDocs.add(key);
    final heldSet = _rollCallHeld.putIfAbsent(key, () => <String>{});
    final confirmed = _rollCallConfirmed.putIfAbsent(key, () => <String>{});
    if (held) {
      heldSet.add(userId);
      confirmed.remove(userId);
    } else {
      heldSet.remove(userId);
    }
    _rollCallChanges.add(null);
  }

  Future<int> seedDemoAttendances({
    required String cohortId,
    required String dateKey,
    required List<UserModel> students,
    required DemoAttendanceSeed seed,
  }) async {
    var written = 0;
    for (final student in students) {
      final i = _attendances.indexWhere(
        (a) => a.userId == student.uid && a.dateKey == dateKey,
      );
      final source = i >= 0 ? _attendances[i].statusSource : null;
      if (source == 'form' || source == 'manual') continue;

      final hash = student.uid.hashCode.abs() + dateKey.hashCode.abs();
      final missing = hash % 17 == 0;
      final prev = i >= 0 ? _attendances[i] : null;
      final inMin = 8 * 60 + 48 + (hash % 18);
      final outMin = 17 * 60 + 50 + (hash % 20);
      final inTime =
          '${(inMin ~/ 60).toString().padLeft(2, '0')}:${(inMin % 60).toString().padLeft(2, '0')}';
      final outTime =
          '${(outMin ~/ 60).toString().padLeft(2, '0')}:${(outMin % 60).toString().padLeft(2, '0')}';

      String? checkInTime = prev?.checkInTime;
      String? checkOutTime = prev?.checkOutTime;
      String? status = prev?.status;

      if (seed == DemoAttendanceSeed.checkIn) {
        checkInTime = missing ? null : inTime;
        status = missing ? AttendanceStatus.absent : AttendanceStatus.present;
      } else {
        if (missing) continue;
        checkOutTime = outTime;
        status ??= AttendanceStatus.present;
      }

      final model = AttendanceModel(
        id: '${student.uid}_$dateKey',
        userId: student.uid,
        type: 'status',
        dateKey: dateKey,
        status: status,
        userDisplayName: student.displayName,
        timestamp: DateTime.now(),
        checkInTime: checkInTime,
        checkOutTime: checkOutTime,
        statusSource: 'demo',
        formAttendanceType: prev?.formAttendanceType,
        officialLeaveUsed: prev?.officialLeaveUsed,
        officialLeaveType: prev?.officialLeaveType,
        officialLeaveOther: prev?.officialLeaveOther,
      );
      if (i >= 0) {
        _attendances[i] = model;
      } else {
        _attendances.add(model);
      }
      written++;
    }
    return written;
  }

  bool _dailyAttendanceNoticeEnsured = false;

  Future<bool> ensureDailyAttendanceFormNotice({
    required String cohortId,
    required String authorId,
    required String authorName,
  }) async {
    if (_dailyAttendanceNoticeEnsured) return false;
    _dailyAttendanceNoticeEnsured = true;
    return true;
  }

  Future<void> upsertAttendanceStatus({
    required String cohortId,
    required String userId,
    required String userDisplayName,
    required String dateKey,
    required String status,
  }) async {
    final i = _attendances.indexWhere(
      (a) => a.userId == userId && a.dateKey == dateKey,
    );
    if (i >= 0) {
      final cur = _attendances[i];
      _attendances[i] = AttendanceModel(
        id: cur.id,
        userId: userId,
        type: 'status',
        dateKey: dateKey,
        status: status,
        userDisplayName: userDisplayName,
        timestamp: DateTime.now(),
        statusSource: 'manual',
        checkInTime: cur.checkInTime,
        checkOutTime: cur.checkOutTime,
        formAttendanceType: cur.formAttendanceType,
        officialLeaveUsed: cur.officialLeaveUsed,
        officialLeaveType: cur.officialLeaveType,
        officialLeaveOther: cur.officialLeaveOther,
      );
    } else {
      _attendances.insert(
        0,
        AttendanceModel(
          id: 'a${_attendances.length}',
          userId: userId,
          type: 'status',
          dateKey: dateKey,
          status: status,
          userDisplayName: userDisplayName,
          timestamp: DateTime.now(),
          statusSource: 'manual',
        ),
      );
    }
  }

  Future<void> clearAttendanceStatus({
    required String cohortId,
    required String userId,
    required String dateKey,
  }) async {
    _attendances.removeWhere(
      (a) => a.userId == userId && a.dateKey == dateKey,
    );
  }

  Future<void> recordAttendance({
    required String cohortId,
    required String userId,
    required String userDisplayName,
    required String type,
    required String dateKey,
  }) async {
    _attendances.insert(
      0,
      AttendanceModel(
        id: 'a${_attendances.length}',
        userId: userId,
        type: type,
        dateKey: dateKey,
        timestamp: DateTime.now(),
      ),
    );
  }

  Stream<List<MileageTransactionModel>> watchMyMileageTransactions(
    String cohortId,
    String userId,
  ) async* {
    yield _mileageTx.where((t) => t.userId == userId).toList();
  }

  Stream<ScheduleModel?> watchSchedule(String cohortId, String dateKey) async* {
    yield null;
  }

  Stream<List<String>> watchScheduleDateKeys(String cohortId) async* {
    yield [];
  }

  Stream<List<MaterialModel>> watchMaterials(String cohortId) async* {
    yield [];
  }

  Stream<List<AssignmentModel>> watchAssignments(String cohortId) async* {
    yield [];
  }

  Stream<List<InflearnPackageModel>> watchInflearnPackages(String cohortId) {
    return _startWith(
      List.of(_inflearnPackages),
      _inflearnPackageController.stream,
    );
  }

  Stream<List<InflearnPackageModel>> watchPublishedInflearnPackages(
    String cohortId,
  ) {
    return _startWith(
      List.of(_inflearnPackages),
      _inflearnPackageController.stream,
    ).map((list) => list.where((p) => p.isPublished).toList());
  }

  Future<String> createInflearnPackage({
    required String cohortId,
    required InflearnPackageModel package,
  }) async {
    final id = 'pkg${_inflearnPackages.length}';
    _inflearnPackages.insert(
      0,
      InflearnPackageModel(
        id: id,
        title: package.title,
        subject: package.subject,
        type: package.type,
        summary: package.summary,
        units: package.units,
        courses: package.courses,
        isPublished: package.isPublished,
        sortOrder: package.sortOrder,
        publishedAt: package.publishedAt,
      ),
    );
    _emit();
    return id;
  }

  Future<void> updateInflearnPackage({
    required String cohortId,
    required String packageId,
    required Map<String, dynamic> updates,
  }) async {
    final i = _inflearnPackages.indexWhere((p) => p.id == packageId);
    if (i < 0) return;
    final p = _inflearnPackages[i];

    List<InflearnUnitModel>? units;
    if (updates['units'] is List) {
      units = (updates['units'] as List)
          .map((u) => InflearnUnitModel.fromMap(u as Map<String, dynamic>))
          .toList();
    }
    List<InflearnCourseModel>? courses;
    if (updates['courses'] is List) {
      courses = (updates['courses'] as List)
          .map((c) => InflearnCourseModel.fromMap(c as Map<String, dynamic>))
          .toList();
    }

    _inflearnPackages[i] = p.copyWith(
      title: updates['title'] as String? ?? p.title,
      subject: updates['subject'] as String? ?? p.subject,
      type: updates['type'] != null
          ? InflearnPackageType.fromString(updates['type'] as String)
          : p.type,
      summary: updates.containsKey('summary')
          ? updates['summary'] as String?
          : p.summary,
      units: units ?? p.units,
      courses: courses ?? p.courses,
      isPublished: updates['isPublished'] as bool? ?? p.isPublished,
      sortOrder: (updates['sortOrder'] as num?)?.toInt() ?? p.sortOrder,
      publishedAt: updates['publishedAt'] is DateTime
          ? updates['publishedAt'] as DateTime
          : p.publishedAt,
    );
    _emit();
  }

  Future<void> deleteInflearnPackage({
    required String cohortId,
    required String packageId,
  }) async {
    _inflearnPackages.removeWhere((p) => p.id == packageId);
    _emit();
  }

  List<StudySourceModel> get _demoStudySources => const [
    StudySourceModel(
      id: 'demo-llm',
      title: 'LLM파트',
      repoUrl: 'https://github.com/skn-ai34-260616/LLM',
      allowedPrefixes: ['LLM'],
      sortOrder: 0,
    ),
    StudySourceModel(
      id: 'demo-multimodal',
      title: 'Multimodal',
      repoUrl: 'https://github.com/skn-ai34-260616/multimodal',
      allowedPrefixes: ['multimodal'],
      sortOrder: 1,
    ),
    StudySourceModel(
      id: 'demo-nlp',
      title: 'NLP',
      repoUrl: 'https://github.com/skn-ai34-260616/NLP',
      allowedPrefixes: ['NLP'],
      sortOrder: 2,
    ),
  ];

  Stream<List<StudySourceModel>> watchStudySources(String cohortId) async* {
    yield _demoStudySources;
  }

  Stream<List<StudySourceModel>> watchActiveStudySources(
    String cohortId,
  ) async* {
    yield _demoStudySources;
  }

  Stream<List<StudyNoteModel>> watchReadyStudyNotes(String uid) async* {
    yield const [
      StudyNoteModel(
        id: 'demo-note-0915',
        status: 'ready',
        sourceId: 'demo-llm',
        scopeType: 'date',
        scopeValue: '2026-09-15',
        files: [
          StudyNoteFileRef(
            path: 'LLM/02_video_rag_frame_extraction.ipynb',
            commit: 'demo',
          ),
          StudyNoteFileRef(
            path: 'LLM/03_vector_search.ipynb',
            commit: 'demo',
          ),
        ],
      ),
    ];
  }

  Future<String> createStudySource({
    required String cohortId,
    required StudySourceModel source,
  }) async {
    return 'demo-source';
  }

  Future<void> updateStudySource({
    required String cohortId,
    required String sourceId,
    required Map<String, dynamic> updates,
  }) async {}

  Stream<List<YoutubeRecommendationModel>> watchYoutubeRecommendations(
    String cohortId,
  ) {
    return _startWith(
      List.of(_youtubeRecommendations),
      _youtubeRecommendationController.stream,
    );
  }

  Stream<List<YoutubeRecommendationModel>> watchPublishedYoutubeRecommendations(
    String cohortId,
  ) {
    return watchYoutubeRecommendations(cohortId).map(
      (list) => list.where((v) => v.isPublished).toList(),
    );
  }

  Future<String> createYoutubeRecommendation({
    required String cohortId,
    required YoutubeRecommendationModel video,
  }) async {
    final id = 'yt${_youtubeRecommendations.length + 1}';
    _youtubeRecommendations.add(
      YoutubeRecommendationModel(
        id: id,
        title: video.title,
        youtubeUrl: video.youtubeUrl,
        videoId: video.effectiveVideoId,
        thumbnailUrl: video.effectiveThumbnailUrl,
        description: video.description,
        tags: video.tags,
        isPublished: video.isPublished,
        sortOrder: video.sortOrder,
        createdAt: DateTime.now(),
      ),
    );
    _emit();
    return id;
  }

  Future<void> updateYoutubeRecommendation({
    required String cohortId,
    required String videoId,
    required Map<String, dynamic> updates,
  }) async {
    final i = _youtubeRecommendations.indexWhere((v) => v.id == videoId);
    if (i < 0) return;
    final cur = _youtubeRecommendations[i];
    final nextUrl = updates['youtubeUrl'] as String? ?? cur.youtubeUrl;
    _youtubeRecommendations[i] = cur.copyWith(
      title: updates['title'] as String? ?? cur.title,
      youtubeUrl: nextUrl,
      videoId:
          updates['videoId'] as String? ??
          extractYoutubeVideoId(nextUrl) ??
          cur.videoId,
      thumbnailUrl: updates['thumbnailUrl'] as String? ?? cur.thumbnailUrl,
      description: updates['description'] as String? ?? cur.description,
      tags: updates['tags'] != null
          ? List<String>.from(updates['tags'] as List)
          : cur.tags,
      isPublished: updates['isPublished'] as bool? ?? cur.isPublished,
      sortOrder: (updates['sortOrder'] as num?)?.toInt() ?? cur.sortOrder,
    );
    _emit();
  }

  Future<void> deleteYoutubeRecommendation({
    required String cohortId,
    required String videoId,
  }) async {
    _youtubeRecommendations.removeWhere((v) => v.id == videoId);
    _emit();
  }

  Future<void> logRecommendationEvent({
    required String cohortId,
    required String userId,
    required String videoDocId,
    required String youtubeVideoId,
    required List<String> userSkills,
    required List<String> matchedTags,
    String action = 'open',
  }) async {
    // demo: no-op
  }

  Stream<List<AssessmentModel>> watchAssessments(String cohortId) {
    return _startWith(List.of(_assessments), _assessmentController.stream);
  }

  Stream<List<AssessmentModel>> watchPublishedAssessments(String cohortId) {
    return _startWith(
      List.of(_assessments),
      _assessmentController.stream,
    ).map((list) => list.where((a) => a.published).toList());
  }

  Stream<AssessmentModel?> watchAssessment(
    String cohortId,
    String assessmentId,
  ) async* {
    yield _assessments.where((a) => a.id == assessmentId).firstOrNull;
    yield* _assessmentController.stream.map(
      (list) => list.where((a) => a.id == assessmentId).firstOrNull,
    );
  }

  Future<String> createAssessment({
    required String cohortId,
    required AssessmentModel assessment,
  }) async {
    final id = 'a${_assessments.length + 1}';
    _assessments.insert(
      0,
      assessment.copyWith(id: id, createdAt: DateTime.now()),
    );
    _assessmentQuestions[id] = [];
    _emit();
    return id;
  }

  Future<void> updateAssessment({
    required String cohortId,
    required String assessmentId,
    required Map<String, dynamic> updates,
  }) async {
    final i = _assessments.indexWhere((a) => a.id == assessmentId);
    if (i < 0) return;
    final a = _assessments[i];
    _assessments[i] = a.copyWith(
      title: updates['title'] as String? ?? a.title,
      tags: updates['tags'] != null
          ? List<String>.from(updates['tags'] as List)
          : a.tags,
      questionCount: updates['questionCount'] as int? ?? a.questionCount,
      maxScore: updates['maxScore'] as int? ?? a.maxScore,
      startAt: updates['startAt'] as DateTime? ?? a.startAt,
      endAt: updates['endAt'] as DateTime? ?? a.endAt,
      thumbnailUrl: updates['thumbnailUrl'] as String? ?? a.thumbnailUrl,
      thumbnailPath: updates['thumbnailPath'] as String? ?? a.thumbnailPath,
      published: updates['published'] as bool? ?? a.published,
      updatedAt: DateTime.now(),
    );
    _emit();
  }

  Future<void> publishAssessment({
    required String cohortId,
    required String assessmentId,
    bool published = true,
  }) async {
    await updateAssessment(
      cohortId: cohortId,
      assessmentId: assessmentId,
      updates: {'published': published},
    );
  }

  Future<void> deleteAssessment({
    required String cohortId,
    required String assessmentId,
  }) async {
    _assessments.removeWhere((a) => a.id == assessmentId);
    _assessmentQuestions.remove(assessmentId);
    _assessmentSubmissions.removeWhere((s) => s.assessmentId == assessmentId);
    _emit();
  }

  Stream<List<AssessmentQuestionModel>> watchAssessmentQuestions(
    String cohortId,
    String assessmentId,
  ) async* {
    yield List.of(_assessmentQuestions[assessmentId] ?? const []);
    yield* _assessmentController.stream.map(
      (_) => List.of(_assessmentQuestions[assessmentId] ?? const []),
    );
  }

  Future<void> replaceAssessmentQuestions({
    required String cohortId,
    required String assessmentId,
    required List<AssessmentQuestionModel> questions,
  }) async {
    final normalized = <AssessmentQuestionModel>[];
    var maxScore = 0;
    for (var i = 0; i < questions.length; i++) {
      final id = questions[i].id.isEmpty || questions[i].id.startsWith('draft_')
          ? 'q${i + 1}'
          : questions[i].id;
      final q = questions[i].copyWith(id: id, order: i);
      normalized.add(q);
      maxScore += q.points;
    }
    _assessmentQuestions[assessmentId] = normalized;
    await updateAssessment(
      cohortId: cohortId,
      assessmentId: assessmentId,
      updates: {
        'questionCount': normalized.length,
        'maxScore': maxScore,
      },
    );
  }

  Stream<List<AssessmentSubmissionModel>> watchMyAssessmentSubmissions(
    String cohortId,
    String userId,
  ) {
    return _startWith(
      List.of(_assessmentSubmissions),
      _assessmentSubmissionController.stream,
    ).map((list) => list.where((s) => s.userId == userId).toList());
  }

  Stream<List<AssessmentSubmissionModel>> watchAssessmentSubmissions(
    String cohortId,
    String assessmentId,
  ) {
    return _startWith(
      List.of(_assessmentSubmissions),
      _assessmentSubmissionController.stream,
    ).map((list) => list.where((s) => s.assessmentId == assessmentId).toList());
  }

  Stream<AssessmentSubmissionModel?> watchAssessmentSubmission(
    String cohortId,
    String submissionId,
  ) async* {
    yield _assessmentSubmissions.where((s) => s.id == submissionId).firstOrNull;
    yield* _assessmentSubmissionController.stream.map(
      (list) => list.where((s) => s.id == submissionId).firstOrNull,
    );
  }

  /// Demo: 로컬 채점 제출
  Future<Map<String, dynamic>> demoSubmitAssessment({
    required String assessmentId,
    required String userId,
    required String userDisplayName,
    required Map<String, dynamic> answers,
  }) async {
    final id = '${assessmentId}_$userId';
    if (_assessmentSubmissions.any((s) => s.id == id)) {
      throw StateError('이미 응시한 평가입니다.');
    }
    final questions = _assessmentQuestions[assessmentId] ?? [];
    final graded = <String, AssessmentAnswerEntry>{};
    var total = 0;
    for (final q in questions) {
      final raw = answers[q.id];
      var score = 0;
      var correct = false;
      if (q.type == AssessmentQuestionType.multipleChoice) {
        final selected = raw is int ? raw : int.tryParse('$raw');
        correct = selected != null && selected == q.correctIndex;
        score = correct ? q.points : 0;
      } else {
        final norm = '$raw'.trim().toLowerCase();
        correct = q.acceptedAnswers.any((a) => a.trim().toLowerCase() == norm);
        score = correct ? q.points : 0;
      }
      graded[q.id] = AssessmentAnswerEntry(
        value: raw,
        autoScore: score,
        finalScore: score,
        isCorrect: correct,
      );
      total += score;
    }
    _assessmentSubmissions.add(
      AssessmentSubmissionModel(
        id: id,
        assessmentId: assessmentId,
        userId: userId,
        userDisplayName: userDisplayName,
        answers: graded,
        autoTotalScore: total,
        totalScore: total,
        submittedAt: DateTime.now(),
      ),
    );
    _emit();
    return {
      'totalScore': total,
      'autoTotalScore': total,
      'submissionId': id,
    };
  }

  Future<Map<String, dynamic>> demoAdjustScores({
    required String submissionId,
    required List<Map<String, dynamic>> adjustments,
    required String by,
    String? byName,
    String? note,
  }) async {
    final i = _assessmentSubmissions.indexWhere((s) => s.id == submissionId);
    if (i < 0) throw StateError('제출 없음');
    final s = _assessmentSubmissions[i];
    final answers = Map<String, AssessmentAnswerEntry>.from(s.answers);
    final history = [...s.scoreAdjustments];
    for (final adj in adjustments) {
      final qid = adj['questionId'] as String?;
      if (qid == null || answers[qid] == null) continue;
      final previous = answers[qid]!.finalScore;
      final next = (adj['finalScore'] as num).toInt().clamp(0, 9999);
      if (previous == next) continue;
      answers[qid] = AssessmentAnswerEntry(
        value: answers[qid]!.value,
        autoScore: answers[qid]!.autoScore,
        finalScore: next,
        isCorrect: next > 0,
      );
      history.add(
        AssessmentScoreAdjustment(
          questionId: qid,
          previous: previous,
          next: next,
          by: by,
          byName: byName,
          at: DateTime.now(),
          note: note,
        ),
      );
    }
    final total = answers.values.fold<int>(0, (sum, e) => sum + e.finalScore);
    _assessmentSubmissions[i] = AssessmentSubmissionModel(
      id: s.id,
      assessmentId: s.assessmentId,
      userId: s.userId,
      userDisplayName: s.userDisplayName,
      answers: answers,
      autoTotalScore: s.autoTotalScore,
      totalScore: total,
      status: s.status,
      submittedAt: s.submittedAt,
      scoreAdjustments: history,
    );
    _emit();
    return {'totalScore': total, 'submissionId': submissionId};
  }

  Stream<List<CurriculumSheetModel>> watchCurriculumSheets(String cohortId) {
    return _startWith(
      List.of(_curriculumSheets),
      _curriculumSheetController.stream,
    );
  }

  Stream<CurriculumSheetModel?> watchLatestCurriculumSheet(String cohortId) {
    return _startWith(
      List.of(_curriculumSheets),
      _curriculumSheetController.stream,
    ).map((list) => list.isEmpty ? null : list.first);
  }

  Stream<CurriculumSheetModel?> watchCurriculumSheet(
    String cohortId,
    String sheetId,
  ) {
    return _startWith(
      List.of(_curriculumSheets),
      _curriculumSheetController.stream,
    ).map(
      (list) => list.where((s) => s.id == sheetId).firstOrNull,
    );
  }

  Future<String> saveCurriculumSheet({
    required String cohortId,
    required CurriculumSheetModel sheet,
    String? replaceSheetId,
  }) async {
    final id = replaceSheetId ?? 'cs${_curriculumSheets.length + 1}';
    final saved = CurriculumSheetModel(
      id: id,
      title: sheet.title,
      fileName: sheet.fileName,
      rows: sheet.rows,
      uploadedBy: sheet.uploadedBy,
      uploadedByName: sheet.uploadedByName,
      uploadedAt: DateTime.now(),
      storagePath: sheet.storagePath,
      source: sheet.source,
    );
    _curriculumSheets.removeWhere((s) => s.id == id);
    _curriculumSheets.insert(0, saved);
    _emit();
    return id;
  }

  Future<void> deleteCurriculumSheet({
    required String cohortId,
    required String sheetId,
  }) async {
    _curriculumSheets.removeWhere((s) => s.id == sheetId);
    _emit();
  }

  Future<void> submitAssignment({
    required String cohortId,
    required String assignmentId,
    required String userId,
    required String userDisplayName,
    required String fileUrl,
    required String fileName,
    required int fileSizeBytes,
  }) async {}

  Future<void> updateProfile({
    required String uid,
    String? motto,
    List<String>? skills,
    Map<String, String>? socialLinks,
    String? birthDate,
    String? personalEmail,
    String? photoUrl,
    String? photoStoragePath,
  }) async {
    final session = DemoSession.instance;
    if (session.currentUser?.uid != uid) return;
    session.updateCurrentUser(
      session.currentUser!.copyWith(
        motto: motto,
        skills: skills,
        socialLinks: socialLinks,
        birthDate: birthDate,
        personalEmail: personalEmail,
        photoUrl: photoUrl,
        photoStoragePath: photoStoragePath,
      ),
    );
  }

  Future<void> updatePersonalEmail({
    required String uid,
    required String personalEmail,
  }) async {
    await updateProfile(
      uid: uid,
      personalEmail: personalEmail.trim().toLowerCase(),
    );
  }

  Stream<List<FormTaskModel>> watchFormTasks(String cohortId) async* {
    final list = _formTasks.where((t) => t.published).toList()
      ..sort((a, b) => a.dueAt.compareTo(b.dueAt));
    yield list;
  }

  Stream<List<FormTaskModel>> watchAllFormTasks(String cohortId) async* {
    yield List.from(_formTasks)..sort((a, b) => a.dueAt.compareTo(b.dueAt));
  }

  Stream<FormTaskModel?> watchFormTask(String cohortId, String taskId) async* {
    try {
      yield _formTasks.firstWhere((t) => t.id == taskId);
    } catch (_) {
      yield null;
    }
  }

  Stream<List<FormResponseModel>> watchFormTaskResponses(
    String cohortId,
    String taskId,
  ) async* {
    yield List.from(_formResponses[taskId] ?? []);
  }

  Stream<List<FormResponseModel>> watchMyFormResponses(
    String cohortId,
    String userId,
  ) async* {
    final all = _formResponses.values.expand((list) => list);
    yield all
        .where((r) => r.cohortId == cohortId && r.userId == userId)
        .toList();
  }

  Stream<List<FormTaskWithStatus>> watchFormTasksWithStatus(
    String cohortId,
    String userId,
  ) async* {
    final tasks = _formTasks.where((t) => t.published).toList()
      ..sort((a, b) => a.dueAt.compareTo(b.dueAt));
    yield tasks.map((task) {
      FormResponseModel? response;
      for (final r in _formResponses[task.id] ?? const []) {
        if (r.userId == userId) {
          response = r;
          break;
        }
      }
      return FormTaskWithStatus(task: task, myResponse: response);
    }).toList();
  }

  Future<String> createFormTask({
    required String cohortId,
    required FormTaskModel task,
    required String authorId,
  }) async {
    final id = 'form${_formTasks.length + 1}';
    _formTasks.add(
      FormTaskModel(
        id: id,
        title: task.title,
        description: task.description,
        formUrl: task.formUrl,
        notionGuideUrl: task.notionGuideUrl,
        dueAt: task.dueAt,
        published: task.published,
        createdAt: DateTime.now(),
      ),
    );
    return id;
  }

  Future<void> updateFormTask({
    required String cohortId,
    required String taskId,
    required FormTaskModel task,
    required String authorId,
  }) async {
    final i = _formTasks.indexWhere((t) => t.id == taskId);
    if (i >= 0) {
      final prev = _formTasks[i];
      _formTasks[i] = FormTaskModel(
        id: taskId,
        title: task.title,
        description: task.description,
        formUrl: task.formUrl,
        notionGuideUrl: task.notionGuideUrl,
        dueAt: task.dueAt,
        published: task.published,
        responseCount: prev.responseCount,
        createdAt: prev.createdAt,
        updatedAt: DateTime.now(),
      );
    }
  }

  Future<void> deleteFormTask(String cohortId, String taskId) async {
    _formTasks.removeWhere((t) => t.id == taskId);
    _formResponses.remove(taskId);
  }
}

/// 싱글톤 — 앱 전체에서 동일 데이터 공유
DemoLmsRepository? _demoLmsInstance;
DemoLmsRepository get demoLmsRepository =>
    _demoLmsInstance ??= DemoLmsRepository();
