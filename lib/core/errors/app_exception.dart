/// 앱 전역 예외 — Repository / Service 레이어에서 throw
sealed class AppException implements Exception {
  const AppException(this.message, {this.code});

  final String message;
  final String? code;

  @override
  String toString() => 'AppException($code): $message';
}

/// 인증 관련 예외
final class AuthException extends AppException {
  const AuthException(super.message, {super.code});
}

/// Firestore / 네트워크 관련 예외
final class DataException extends AppException {
  const DataException(super.message, {super.code});
}

/// 권한 부족 예외
final class PermissionException extends AppException {
  const PermissionException([super.message = '접근 권한이 없습니다.']);
}
