import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:intl/intl.dart';

/// Firestore Timestamp ↔ DateTime 변환 및 날짜 키 유틸
abstract final class AppDateUtils {
  static String toDateKey(DateTime date) {
    final y = date.year.toString().padLeft(4, '0');
    final m = date.month.toString().padLeft(2, '0');
    final d = date.day.toString().padLeft(2, '0');
    return '$y-$m-$d';
  }

  static DateTime fromDateKey(String dateKey) =>
      DateFormat('yyyy-MM-dd').parse(dateKey);

  static DateTime? timestampToDateTime(dynamic value) {
    if (value == null) return null;
    if (value is Timestamp) return value.toDate();
    if (value is DateTime) return value;
    return null;
  }

  static String formatDisplay(DateTime date) =>
      DateFormat('yyyy.MM.dd').format(date);

  static String formatDateTime(DateTime date) =>
      DateFormat('yyyy-MM-dd HH:mm').format(date);

  static String formatDetailDateTime(DateTime date) =>
      DateFormat('yyyy.MM.dd HH:mm').format(date);

  /// YYYYMMDD → yyyy.MM.dd
  static String formatYmd(String? ymd) {
    if (ymd == null || ymd.length < 8) return '-';
    return '${ymd.substring(0, 4)}.${ymd.substring(4, 6)}.${ymd.substring(6, 8)}';
  }
}
