import 'package:flutter_test/flutter_test.dart';

import 'package:playdata_lms/core/constants/role.dart';
import 'package:playdata_lms/features/resume/data/basic_info_prefill.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';
import 'package:playdata_lms/shared/models/user_model.dart';

UserModel _user({
  String? personalEmail = 'hong@gmail.com',
  String? birthDate = '2000-01-02',
  Map<String, String> socialLinks = const {
    'github': 'https://github.com/hong',
    'blog': 'https://hong.dev',
  },
}) => UserModel(
  uid: 'u1',
  email: 'hong@school.ac.kr',
  personalEmail: personalEmail,
  displayName: '홍길동',
  role: UserRole.student,
  cohortId: 'c34',
  cohortName: '34기',
  birthDate: birthDate,
  socialLinks: socialLinks,
);

void main() {
  test('빈 기본정보는 프로필로 모두 채워지고 개인 이메일이 우선한다', () {
    final result = prefillBasicInfoFromProfile(const ResumeBasicInfo(), _user());
    expect(result.changed, isTrue);
    expect(result.info.name, '홍길동');
    expect(result.info.email, 'hong@gmail.com');
    expect(result.info.birthDate, '2000-01-02');
    expect(result.info.githubUrl, 'https://github.com/hong');
    expect(result.info.blogUrl, 'https://hong.dev');
    expect(result.info.phone, '');
    expect(result.filledLabels, ['이름', '이메일', '생년월일', 'GitHub', '블로그']);
  });

  test('이미 적힌 값은 덮어쓰지 않는다', () {
    const existing = ResumeBasicInfo(
      name: '김철수',
      email: 'kim@example.com',
      githubUrl: 'https://github.com/kim',
    );
    final result = prefillBasicInfoFromProfile(existing, _user());
    expect(result.info.name, '김철수');
    expect(result.info.email, 'kim@example.com');
    expect(result.info.githubUrl, 'https://github.com/kim');
    expect(result.filledLabels, ['생년월일', '블로그']);
  });

  test('목업 병합은 적힌 값을 지키고 빈 칸만 목업 값으로 채운다', () {
    const mine = ResumeBasicInfo(name: '홍길동', email: 'hong@gmail.com', phone: '');
    const mock = ResumeBasicInfo(name: '목업', email: 'mock@x.com', phone: '010-0000-0000', birthDate: '1999-09-09');
    final merged = mergeBasicInfo(mine, mock);
    expect(merged.name, '홍길동');
    expect(merged.email, 'hong@gmail.com');
    expect(merged.phone, '010-0000-0000');
    expect(merged.birthDate, '1999-09-09');
  });

  test('개인 이메일이 없으면 로그인 이메일을 쓰고, 프로필이 비어 있으면 바뀌지 않는다', () {
    final fallback = prefillBasicInfoFromProfile(
      const ResumeBasicInfo(),
      _user(personalEmail: null, birthDate: null, socialLinks: const {}),
    );
    expect(fallback.info.email, 'hong@school.ac.kr');
    expect(fallback.filledLabels, ['이름', '이메일']);

    final full = prefillBasicInfoFromProfile(
      const ResumeBasicInfo(name: 'a', email: 'b', birthDate: 'c', githubUrl: 'd', blogUrl: 'e'),
      _user(),
    );
    expect(full.changed, isFalse);
  });
}
