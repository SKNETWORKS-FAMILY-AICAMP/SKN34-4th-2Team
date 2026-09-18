// 이력서에서 학력을 읽는 규칙.
//
// 예전에는 학력 항목이 한 줄이라도 있으면 무조건 `대졸`이었다. 전공을 적었다는 것과
// 그 학위를 받았다는 것은 다른 이야기인데 둘을 같이 봤다. 그래서 전문학사도 대졸로
// 나가 대졸 필수 공고(저장소 기준 모집 중 6,877건)를 전부 통과했고, 대학교 재학 중인
// 사람도 마찬가지였다. 반대로 석사는 대졸로 낮춰져 석사 필수 공고에서 떨어졌다.
//
// 값은 서버 하드 필터의 `EDUCATION_RANK` 와 같아야 한다.
// 파이썬 판은 job_matching_bot/evaluation/app_resume.py 에 같은 규칙으로 있다.
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/features/resume/ai_coach/data/resume_profile.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';

ResumeEducationItem edu(String school, {String major = '', String status = '졸업'}) =>
    ResumeEducationItem(id: 'e', school: school, major: major, status: status);

void main() {
  group('학교 이름으로 학위를 읽는다', () {
    test('대학교 졸업은 대졸', () {
      expect(educationLevelOf([edu('한국대학교', major: '컴퓨터공학과')]), '대졸');
    });

    test('전문대학은 초대졸 — `전문대학`이 `대학`을 품고 있어 먼저 봐야 한다', () {
      expect(educationLevelOf([edu('경기전문대학', major: '빅데이터과')]), '초대졸');
    });

    test('전공에 (3년제)라고 적어도 초대졸로 본다', () {
      expect(educationLevelOf([edu('경기대학', major: '빅데이터과(3년제)')]), '초대졸');
    });

    test('대학원은 석사', () {
      expect(educationLevelOf([edu('한국대학교 대학원', major: '컴퓨터공학과')]), '석사');
    });

    test('박사과정이라 적으면 박사', () {
      expect(educationLevelOf([edu('한국대학교 대학원', major: '컴퓨터공학 박사과정')]), '박사');
    });

    test('고등학교는 고졸', () {
      expect(educationLevelOf([edu('서울고등학교')]), '고졸');
    });

    test('무엇인지 못 읽으면 세지 않는다', () {
      expect(educationLevelOf([edu('어딘가 교육원')]), '미기재');
    });
  });

  group('학위를 받았는지 본다', () {
    test('재학 중인 대학교는 아직 고졸', () {
      expect(educationLevelOf([edu('한국대학교', status: '재학')]), '고졸');
    });

    test('중퇴도 고졸 — 한 칸 내리면 초대졸이 되어 틀린다', () {
      expect(educationLevelOf([edu('한국대학교', status: '중퇴')]), '고졸');
    });

    test('대학원 수료는 석사가 아니라 대졸', () {
      expect(educationLevelOf([edu('한국대학교 대학원', status: '수료')]), '대졸');
    });

    test('졸업예정은 졸업으로 본다 — 대졸 공고에 지원할 수 있다', () {
      expect(educationLevelOf([edu('한국대학교', status: '졸업예정')]), '대졸');
    });

    test('상태를 비워 두면 졸업으로 본다', () {
      expect(educationLevelOf([edu('한국대학교', status: '')]), '대졸');
    });

    test('고등학교 재학은 미기재', () {
      expect(educationLevelOf([edu('서울고등학교', status: '재학')]), '미기재');
    });
  });

  group('여러 줄이면', () {
    test('가장 높은 학력을 쓴다', () {
      final level = educationLevelOf([
        edu('서울고등학교'),
        edu('한국대학교', major: '컴퓨터공학과'),
        edu('한국대학교 대학원', major: '컴퓨터공학과'),
      ]);
      expect(level, '석사');
    });

    test('순서가 뒤바뀌어도 같다', () {
      final level = educationLevelOf([
        edu('한국대학교 대학원', major: '컴퓨터공학과'),
        edu('서울고등학교'),
      ]);
      expect(level, '석사');
    });

    test('진행 중인 대학원이 졸업한 대학교를 끌어내리지 않는다', () {
      final level = educationLevelOf([
        edu('한국대학교', major: '컴퓨터공학과'),
        edu('한국대학교 대학원', status: '재학'),
      ]);
      expect(level, '대졸');
    });

    test('빈 줄은 건너뛴다', () {
      expect(educationLevelOf([edu(''), edu('한국대학교')]), '대졸');
    });

    test('학력사항이 아예 없으면 미기재', () {
      expect(educationLevelOf([]), '미기재');
    });
  });

  test('전공과 학력은 따로 나간다', () {
    final content = ResumeContent.empty().copyWith(
      education: [edu('경기전문대학', major: '빅데이터과')],
    );
    final profile = RecommendResumeProfile.fromContent(content);
    expect(profile.educationLevel, '초대졸');
    expect(profile.majors, ['빅데이터과'], reason: '전공은 전공대로 실려야 한다');
  });
}
