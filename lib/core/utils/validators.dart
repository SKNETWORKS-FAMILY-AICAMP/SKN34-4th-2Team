/// 이메일 / 비밀번호 유효성 검사
abstract final class Validators {
  static String? email(String? value) {
    if (value == null || value.trim().isEmpty) {
      return '이메일을 입력해 주세요.';
    }
    final emailRegex = RegExp(r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$');
    if (!emailRegex.hasMatch(value.trim())) {
      return '올바른 이메일 형식이 아닙니다.';
    }
    return null;
  }

  static String? password(String? value) {
    if (value == null || value.isEmpty) {
      return '비밀번호를 입력해 주세요.';
    }
    if (value.length < 6) {
      return '비밀번호는 6자 이상이어야 합니다.';
    }
    return null;
  }

  static String? confirmPassword(String? value, String password) {
    if (value != password) {
      return '비밀번호가 일치하지 않습니다.';
    }
    return null;
  }
}
