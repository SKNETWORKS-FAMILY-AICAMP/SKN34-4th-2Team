import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

/// 일별 출석 상태
abstract final class AttendanceStatus {
  static const present = 'present';
  static const late = 'late';
  static const absent = 'absent';
  static const officialLeave = 'officialLeave';
  static const earlyLeave = 'earlyLeave';
  static const outing = 'outing';

  static const all = [
    present,
    late,
    absent,
    officialLeave,
    earlyLeave,
    outing,
  ];

  static const labels = {
    present: '출석',
    late: '지각',
    absent: '결석',
    officialLeave: '공가',
    earlyLeave: '조퇴',
    outing: '외출',
  };

  /// 어두운 화면에서는 같은 이름이 다른 색을 준다. 표를 미리 굳히지 않는다.
  static Map<String, Color> get colors => {
    present: AppColors.success,
    late: AppColors.warning,
    absent: AppColors.error,
    officialLeave: AppColors.info,
    earlyLeave: AppColors.primary,
    outing: const Color(0xFF0F766E),
  };

  static String labelOf(String? status) => labels[status] ?? status ?? '-';

  static Color colorOf(String? status) => colors[status] ?? AppColors.border;

  /// legacy checkIn → 출석
  static String? normalize(String? status, {String? legacyType}) {
    if (status != null && status.isNotEmpty) return status;
    if (legacyType == 'checkIn') return present;
    return null;
  }
}

/// 관리자 예시 출석 채우기 — 입실/퇴실 분리
enum DemoAttendanceSeed { checkIn, checkOut }

/// 구글폼 공가 유형
abstract final class OfficialLeaveType {
  static const vacation = 'vacation';
  static const sick = 'sick';
  static const interview = 'interview';
  static const reserve = 'reserve';
  static const cert = 'cert';
  static const other = 'other';

  static const labels = {
    vacation: '휴가',
    sick: '병가',
    interview: '면접',
    reserve: '예비군/민방위',
    cert: '자격증 응시',
    other: '기타',
  };

  static String labelOf(String? type) => labels[type] ?? type ?? '-';
}

abstract final class AttendanceForm {
  static const url = 'https://forms.gle/HFraX15h7PB7iMic7';
  static const dailyNoticeTitle = '[출결] 오늘 예외 출결 제출';
  static const dailyNoticePresetKey = 'daily_attendance_form';
  static const dailyNoticeContent =
      '정상 출석 외에 지각 / 조퇴 / 외출 / 결석(공가 포함) 예정이 있으면 '
      '반드시 오늘 날짜로 구글폼을 제출해 주세요.\n\n$url';
}
