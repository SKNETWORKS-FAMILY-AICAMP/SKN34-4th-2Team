import 'package:flutter/material.dart';

/// 화면 콘텐츠 폭 토큰 — 역할·기능별 ConstrainedBox에 사용
abstract final class AppLayout {
  /// 관리자/강사 목록·기록실·게시판
  static const list = 860.0;

  /// 응시·채점·마일리지 본문
  static const reading = 720.0;

  /// 좌석 배치 그리드
  static const seating = 900.0;

  /// StudyRoom / 일반 와이드 페이지
  static const page = 960.0;

  /// 출석 표 등 초와이드 테이블
  static const wide = 1100.0;

  /// 마이페이지·자격증·좁은 폼
  static const narrow = 560.0;

  /// 로그인 카드
  static const auth = 400.0;

  static BoxConstraints listConstraints() =>
      const BoxConstraints(maxWidth: list);

  static BoxConstraints readingConstraints() =>
      const BoxConstraints(maxWidth: reading);

  static BoxConstraints seatingConstraints() =>
      const BoxConstraints(maxWidth: seating);

  static BoxConstraints pageConstraints() =>
      const BoxConstraints(maxWidth: page);

  static BoxConstraints wideConstraints() =>
      const BoxConstraints(maxWidth: wide);

  static BoxConstraints narrowConstraints() =>
      const BoxConstraints(maxWidth: narrow);
}
