/// 커리큘럼 CSV 파서 — 한글/영문 헤더 동의어 지원
class CurriculumCsvParser {
  CurriculumCsvParser._();

  static const _dateKeys = {'수업일자', '일자', 'date', '날짜'};
  static const _dayKeys = {'일수', 'day', 'sn', '#', '순서'};
  static const _subjectKeys = {'교과목', 'subject', '과목'};
  static const _topicKeys = {'내용', '주제', 'topic', 'content'};
  static const _detailKeys = {'세부', '세부사항', '상세', 'description', 'detail', '설명'};

  /// [csvText] → 파싱된 행 맵 리스트 (dayIndex, dateLabel, subject, topic, detail, order)
  static List<Map<String, dynamic>> parse(String csvText) {
    final text = _stripBom(csvText).trim();
    if (text.isEmpty) {
      throw FormatException('CSV가 비어 있습니다.');
    }

    final rows = _parseCsvRows(text);
    if (rows.isEmpty) {
      throw FormatException('CSV 행이 없습니다.');
    }

    final header = rows.first.map((c) => c.trim()).toList();
    final col = _mapColumns(header);
    if (col.topic < 0 && col.subject < 0) {
      throw FormatException(
        '헤더에 교과목/내용 열이 필요합니다. (예: 수업일자, 일수, 교과목, 내용)',
      );
    }

    final result = <Map<String, dynamic>>[];
    for (var i = 1; i < rows.length; i++) {
      final cells = rows[i];
      if (cells.every((c) => c.trim().isEmpty)) continue;

      String cell(int idx) =>
          (idx >= 0 && idx < cells.length) ? cells[idx].trim() : '';

      final dateLabel = cell(col.date);
      final subject = cell(col.subject);
      final topic = cell(col.topic);
      final detail = cell(col.detail);
      if (subject.isEmpty && topic.isEmpty && detail.isEmpty) continue;

      var dayIndex = int.tryParse(cell(col.day).replaceAll(RegExp(r'[^\d-]'), ''));
      dayIndex ??= result.length + 1;

      result.add({
        'dayIndex': dayIndex,
        'dateLabel': dateLabel,
        'subject': subject,
        'topic': topic.isEmpty ? detail : topic,
        'detail': detail.isEmpty ? topic : detail,
        'order': result.length,
      });
    }

    if (result.isEmpty) {
      throw FormatException('유효한 데이터 행이 없습니다.');
    }
    return result;
  }

  static String _stripBom(String s) {
    if (s.isNotEmpty && s.codeUnitAt(0) == 0xFEFF) {
      return s.substring(1);
    }
    return s;
  }

  static _ColMap _mapColumns(List<String> header) {
    int find(Set<String> keys) {
      for (var i = 0; i < header.length; i++) {
        final h = header[i].toLowerCase();
        for (final k in keys) {
          if (h == k.toLowerCase() || header[i] == k) return i;
        }
      }
      return -1;
    }

    return _ColMap(
      date: find(_dateKeys),
      day: find(_dayKeys),
      subject: find(_subjectKeys),
      topic: find(_topicKeys),
      detail: find(_detailKeys),
    );
  }

  /// RFC4180 스타일 간단 CSV (따옴표·쉼표·개행)
  static List<List<String>> _parseCsvRows(String text) {
    final rows = <List<String>>[];
    var row = <String>[];
    final cell = StringBuffer();
    var inQuotes = false;

    for (var i = 0; i < text.length; i++) {
      final ch = text[i];
      if (inQuotes) {
        if (ch == '"') {
          if (i + 1 < text.length && text[i + 1] == '"') {
            cell.write('"');
            i++;
          } else {
            inQuotes = false;
          }
        } else {
          cell.write(ch);
        }
      } else {
        if (ch == '"') {
          inQuotes = true;
        } else if (ch == ',') {
          row.add(cell.toString());
          cell.clear();
        } else if (ch == '\n') {
          row.add(cell.toString());
          cell.clear();
          rows.add(row);
          row = [];
        } else if (ch == '\r') {
          // skip / handle CRLF
        } else {
          cell.write(ch);
        }
      }
    }
    row.add(cell.toString());
    if (row.any((c) => c.isNotEmpty) || rows.isEmpty) {
      rows.add(row);
    }
    return rows;
  }
}

class _ColMap {
  const _ColMap({
    required this.date,
    required this.day,
    required this.subject,
    required this.topic,
    required this.detail,
  });
  final int date;
  final int day;
  final int subject;
  final int topic;
  final int detail;
}
