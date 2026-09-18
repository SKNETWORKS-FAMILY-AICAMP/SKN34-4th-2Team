/// 사용자 역할 — Firestore `users.role` 필드와 1:1 매핑
enum UserRole {
  admin('admin'),
  instructor('instructor'),
  student('student');

  const UserRole(this.value);

  final String value;

  static UserRole fromString(String value) {
    return UserRole.values.firstWhere(
      (role) => role.value == value,
      orElse: () => UserRole.student,
    );
  }

  bool get isAdmin => this == UserRole.admin;
  bool get isInstructor => this == UserRole.instructor;
  bool get isStudent => this == UserRole.student;
  bool get canReviewResumes => isAdmin || isInstructor;
  bool get canWriteNotices => isAdmin || isInstructor;
}
