import '../../../shared/models/resume_content.dart';
import '../../../shared/models/user_model.dart';

/// 마이페이지 프로필로 이력서 기본정보의 **빈 칸만** 채운 결과.
class BasicInfoPrefill {
  const BasicInfoPrefill({required this.info, required this.filledLabels});

  final ResumeBasicInfo info;

  /// 이번에 채운 항목의 한글 라벨. 비어 있으면 바뀐 게 없다.
  final List<String> filledLabels;

  bool get changed => filledLabels.isNotEmpty;
}

/// [primary]의 빈 칸만 [fallback] 값으로 채운다. 이미 적힌 값은 그대로 둔다.
///
/// 목업 이력서를 채울 때 사용자가 적어 둔(또는 프로필에서 채워진) 기본정보를
/// 목업 값으로 덮어쓰지 않기 위해 쓴다.
ResumeBasicInfo mergeBasicInfo(ResumeBasicInfo primary, ResumeBasicInfo fallback) {
  String keep(String current, String candidate) =>
      current.trim().isNotEmpty ? current : candidate;
  return ResumeBasicInfo(
    name: keep(primary.name, fallback.name),
    phone: keep(primary.phone, fallback.phone),
    email: keep(primary.email, fallback.email),
    birthDate: keep(primary.birthDate, fallback.birthDate),
    githubUrl: keep(primary.githubUrl, fallback.githubUrl),
    blogUrl: keep(primary.blogUrl, fallback.blogUrl),
  );
}

/// 프로필(`users/{uid}`)에 있는 이름·이메일·생년월일·GitHub·블로그로 기본정보의 빈 칸을 채운다.
///
/// 사용자가 이미 적어 둔 값은 건드리지 않는다. 연락처는 프로필에 없어서 채우지 않는다.
/// 이메일은 개인 이메일이 있으면 그것을, 없으면 로그인 이메일을 쓴다.
BasicInfoPrefill prefillBasicInfoFromProfile(ResumeBasicInfo info, UserModel user) {
  final filled = <String>[];
  var next = info;

  String? pick(String current, String? candidate, String label) {
    if (current.trim().isNotEmpty) return null;
    final value = candidate?.trim() ?? '';
    if (value.isEmpty) return null;
    filled.add(label);
    return value;
  }

  final name = pick(info.name, user.displayName, '이름');
  if (name != null) next = next.copyWith(name: name);

  final personal = user.personalEmail?.trim() ?? '';
  final email = pick(info.email, personal.isNotEmpty ? personal : user.email, '이메일');
  if (email != null) next = next.copyWith(email: email);

  final birthDate = pick(info.birthDate, user.birthDate, '생년월일');
  if (birthDate != null) next = next.copyWith(birthDate: birthDate);

  final github = pick(info.githubUrl, user.socialLinks['github'], 'GitHub');
  if (github != null) next = next.copyWith(githubUrl: github);

  final blog = pick(info.blogUrl, user.socialLinks['blog'], '블로그');
  if (blog != null) next = next.copyWith(blogUrl: blog);

  return BasicInfoPrefill(info: next, filledLabels: filled);
}
