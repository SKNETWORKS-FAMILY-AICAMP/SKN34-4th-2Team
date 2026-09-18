import 'package:flutter/foundation.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';

import '../../../core/constants/app_constants.dart';
import '../../../shared/models/resume_content.dart';
import '../../../shared/models/resume_model.dart';
import '../../../shared/models/tech_skill_level.dart';

/// 이력서 Doc 모드 → PDF 미리보기/인쇄
///
/// 간격은 모두 pt 상수다. 화면용 `AppSpace`를 쓰면 설정의 밀도를 '좁게'로 둔
/// 사람의 PDF만 간격이 줄어든다. 종이는 누가 뽑아도 같은 모양이어야 한다.
///
/// 쪽 넘김 규칙([MultiPage]):
/// - 쪽보다 긴 글도 줄 단위로 이어지도록 본문은 `TextOverflow.span`으로 둔다.
///   기본값이면 쪼갤 수 없어, 한 칸이 한 쪽을 넘는 순간 PDF가 만들어지지 않는다.
/// - 섹션 제목과 항목 제목줄 앞에는 `NewPage(freeSpace:)`를 둔다. 남은 칸에
///   제목과 본문 첫 몇 줄이 들어가지 않으면 그때만 새 쪽을 연다. 그래서 제목만
///   쪽 끝에 홀로 남지 않는다.
abstract final class ResumePdfExporter {
  /// 한 번 받아 두고 다시 쓴다. 내보낼 때마다 내려받지 않는다.
  static pw.ThemeData? _theme;

  /// PDF 기본 글꼴에는 한글 글자가 없어 그냥 두면 전부 네모로 나온다.
  /// 본문·굵은 글씨 둘 다 한글 글꼴로 깔아 둔다.
  static Future<pw.ThemeData> _koreanTheme() async {
    final cached = _theme;
    if (cached != null) return cached;
    final [base, bold] = await Future.wait([
      PdfGoogleFonts.notoSansKRRegular(),
      PdfGoogleFonts.notoSansKRBold(),
    ]);
    return _theme = pw.ThemeData.withFont(base: base, bold: bold);
  }

  static Future<void> showPrintPreview(ResumeModel resume) async {
    final doc = buildDocument(resume, theme: await _koreanTheme());
    await Printing.layoutPdf(onLayout: (_) async => doc.save());
  }

  // ── 치수(pt) ──────────────────────────────────────────────
  static const _format = PdfPageFormat.a4;
  static const _marginH = 48.0;
  static const _marginTop = 42.0;
  static const _marginBottom = 34.0;
  static const _contentWidth = 595.28 - _marginH * 2;

  static const _body = 9.5;
  static const _small = 8.6;
  static const _lineSpacing = 2.6;

  /// 한 줄 높이 어림값. 한글 글꼴은 글자 높이가 커서 넉넉히 잡는다.
  /// 모자라게 잡으면 제목이 쪽 끝에 남고, 넉넉하면 조금 일찍 넘어갈 뿐이다.
  static double _lineHeight(double size) => size * 1.45 + _lineSpacing;

  /// 제목과 함께 다음 쪽으로 넘길 본문 줄 수
  static const _keepLines = 3;

  /// 이보다 짧은 항목은 쪼개지 않고 통째로 넘긴다.
  static const _keepWholeUpTo = 150.0;

  static const _ink = PdfColor.fromInt(0xFF111111);
  static const _text = PdfColor.fromInt(0xFF2A2F37);
  static const _muted = PdfColor.fromInt(0xFF5B6270);
  static const _rule = PdfColor.fromInt(0xFF1F2937);

  @visibleForTesting
  static pw.Document buildDocument(ResumeModel resume, {pw.ThemeData? theme}) {
    final doc = pw.Document(theme: theme);
    final c = resume.content;
    final name = c.basicInfo.name.trim();

    doc.addPage(
      pw.MultiPage(
        pageFormat: _format,
        margin: const pw.EdgeInsets.fromLTRB(
          _marginH,
          _marginTop,
          _marginH,
          _marginBottom,
        ),
        // 문서 전체 기본 글자. 섹션마다 따로 적지 않아도 된다.
        theme: theme?.copyWith(
          defaultTextStyle: theme.defaultTextStyle.copyWith(
            fontSize: _body,
            lineSpacing: _lineSpacing,
            color: _text,
          ),
        ),
        maxPages: 60,
        footer: (context) => pw.Container(
          alignment: pw.Alignment.centerRight,
          margin: const pw.EdgeInsets.only(top: 10),
          child: pw.Text(
            [
              if (name.isNotEmpty) name,
              '${context.pageNumber} / ${context.pagesCount}',
            ].join(' · '),
            style: const pw.TextStyle(fontSize: 7.5, color: _muted),
          ),
        ),
        build: (context) => [
          ..._header(resume),
          for (final key in printedSections(c))
            if (key == 'selfIntroduction')
              ..._selfIntroduction(
                c.selfIntroduction,
                // 앞에 다른 섹션이 없으면 1쪽이 이름만 남은 빈 종이가 된다.
                newPage: printedSections(c).length > 1,
              )
            else
              ..._section(
                AppConstants.resumeSectionLabels[key]!,
                _items(key, c),
              ),
        ],
      ),
    );
    return doc;
  }

  /// PDF에 실을 섹션. 순서는 편집 화면과 같고, 빈 섹션은 뺀다.
  /// 기본정보는 머리말로 따로 그린다.
  @visibleForTesting
  static List<String> printedSections(ResumeContent c) => [
    for (final key in AppConstants.resumeSections)
      if (key != 'basicInfo' && (c.computeSections()[key] ?? false)) key,
  ];

  // ── 머리말 ────────────────────────────────────────────────

  static List<pw.Widget> _header(ResumeModel resume) {
    final info = resume.content.basicInfo;
    final name = info.name.trim();
    final title = resume.title.trim();
    // 이름이 없으면 이력서 제목이라도 맨 위에 둔다.
    final heading = name.isNotEmpty ? name : title;
    final showTitle = name.isNotEmpty && title.isNotEmpty && title != '새 이력서';
    final contact = contactLine(info);

    return [
      pw.Text(
        heading,
        style: pw.TextStyle(
          fontSize: 20,
          fontWeight: pw.FontWeight.bold,
          color: _ink,
        ),
      ),
      if (showTitle) ...[
        pw.SizedBox(height: 3),
        pw.Text(title, style: const pw.TextStyle(fontSize: 9, color: _muted)),
      ],
      if (contact.isNotEmpty) ...[
        pw.SizedBox(height: 6),
        pw.Text(contact, style: const pw.TextStyle(fontSize: _small)),
      ],
    ];
  }

  /// 채운 연락처만 한 줄로. 비어 있으면 점만 남지 않게 아예 뺀다.
  @visibleForTesting
  static String contactLine(ResumeBasicInfo info) => [
    info.email,
    info.phone,
    info.githubUrl,
    info.blogUrl,
  ].map((v) => v.trim()).where((v) => v.isNotEmpty).join('  ·  ');

  // ── 섹션 ──────────────────────────────────────────────────

  /// 섹션 제목은 선을 줄 끝까지 긋는다. 자기소개서 질문은 글자 폭만큼 옅게 그어
  /// 한 단계 아래로 보이게 한다.
  static pw.Widget _sectionTitle(String title) => pw.Container(
    width: double.infinity,
    padding: const pw.EdgeInsets.only(bottom: 3),
    decoration: const pw.BoxDecoration(
      border: pw.Border(bottom: pw.BorderSide(color: _rule, width: 1)),
    ),
    child: pw.Text(
      title,
      style: pw.TextStyle(
        fontSize: 11,
        fontWeight: pw.FontWeight.bold,
        color: _ink,
      ),
    ),
  );

  static const _sectionGap = 16.0;
  static const _titleGap = 7.0;
  static const _itemGap = 8.0;
  static const _titleHeight = 11 * 1.45 + 4 + _titleGap;

  static List<pw.Widget> _section(String title, List<_Item> items) {
    if (items.isEmpty) return const [];
    return [
      pw.SizedBox(height: _sectionGap),
      // 제목은 첫 항목(또는 그 첫 몇 줄)과 같은 쪽에 둔다.
      pw.NewPage(freeSpace: _titleHeight + items.first.keepHeight),
      _sectionTitle(title),
      pw.SizedBox(height: _titleGap),
      for (var i = 0; i < items.length; i++) ...[
        if (i > 0) ...[
          // 기술스택 숙련도 줄은 한 덩어리라 항목 사이만큼 벌리지 않는다.
          pw.SizedBox(height: items[i].label == null ? _itemGap : 3),
          pw.NewPage(freeSpace: items[i].keepHeight),
        ],
        ...items[i].widgets,
      ],
    ];
  }

  static List<_Item> _items(String key, ResumeContent c) => switch (key) {
    'coreCompetencies' => [_Item(body: c.coreCompetencies.text)],
    'experience' => [
      for (final e in c.experience.where((e) => e.isFilled))
        _Item(
          name: e.company,
          sub: e.role,
          date: period(e.startDate, e.endDate, isCurrent: e.isCurrent),
          body: e.description,
        ),
    ],
    'education' => [
      for (final e in c.education.where((e) => e.isFilled))
        _Item(
          name: e.school,
          sub: _joined([e.major, e.status]),
          date: period(e.startDate, e.endDate),
        ),
    ],
    'techStack' => [
      for (final row in skillRows(c.techStack))
        _Item(label: row.label, body: row.names),
    ],
    'certifications' => [
      for (final e in c.certifications.where((e) => e.isFilled))
        _Item(name: e.name, sub: e.issuer, date: period(e.acquiredDate, '')),
    ],
    'awards' => [
      for (final e in c.awards.where((e) => e.isFilled))
        _Item(
          name: e.name,
          sub: e.organization,
          date: period(e.date, ''),
          body: e.description,
        ),
    ],
    'trainingExperience' => [
      for (final e in c.trainingExperience.where((e) => e.isFilled))
        _Item(
          name: e.course,
          sub: e.organization,
          date: period(e.startDate, e.endDate),
          body: e.description,
        ),
    ],
    'otherActivities' => [
      for (final e in c.otherActivities.where((e) => e.isFilled))
        _Item(
          name: e.name,
          date: period(e.startDate, e.endDate),
          body: e.description,
        ),
    ],
    'projects' => [
      for (final e in c.projects.where((e) => e.isFilled))
        _Item(
          name: e.name,
          date: period(e.startDate, e.endDate),
          meta: _joined([e.role, e.techStack]),
          body: e.description,
          footnote: e.url,
        ),
    ],
    _ => const [],
  };

  static List<pw.Widget> _selfIntroduction(
    ResumeSelfIntroduction intro, {
    required bool newPage,
  }) {
    final parts = [
      for (final key in ResumeSelfIntroLabels.keys)
        if (intro.sectionByKey(key).isFilled)
          (ResumeSelfIntroLabels.labels[key] ?? key, intro.sectionByKey(key)),
    ];
    if (parts.isEmpty) return const [];

    return [
      // 자기소개서는 새 쪽에서 시작한다.
      if (newPage) pw.NewPage() else pw.SizedBox(height: _sectionGap),
      for (var i = 0; i < parts.length; i++) ...[
        if (i > 0) pw.SizedBox(height: 14),
        pw.NewPage(
          freeSpace:
              (i == 0 ? _titleHeight : 0) +
              _questionHeight +
              (parts[i].$2.subtitle.trim().isEmpty ? 0 : _lineHeight(_body)) +
              _keepLines * _lineHeight(_body),
        ),
        if (i == 0) ...[
          _sectionTitle(AppConstants.resumeSectionLabels['selfIntroduction']!),
          pw.SizedBox(height: _titleGap),
        ],
        // 질문은 머리말, 소제목은 학생이 쓴 첫 줄이다. 둘 다 같은 굵은 글씨면
        // 어느 쪽이 머리말인지 구분되지 않았다.
        pw.Container(
          padding: const pw.EdgeInsets.only(bottom: 2.5),
          decoration: const pw.BoxDecoration(
            border: pw.Border(
              bottom: pw.BorderSide(color: _hairline, width: 0.6),
            ),
          ),
          child: pw.Text(
            parts[i].$1,
            style: pw.TextStyle(
              fontSize: 10.5,
              fontWeight: pw.FontWeight.bold,
              color: _ink,
            ),
          ),
        ),
        pw.SizedBox(height: 5),
        if (parts[i].$2.subtitle.trim().isNotEmpty) ...[
          pw.Text(
            bracketed(parts[i].$2.subtitle),
            style: pw.TextStyle(fontWeight: pw.FontWeight.bold, color: _rule),
          ),
          pw.SizedBox(height: 2),
        ],
        _spanText(parts[i].$2.body.trim(), align: pw.TextAlign.justify),
      ],
    ];
  }

  static const _hairline = PdfColor.fromInt(0xFFD1D5DB);
  static const _questionHeight = 10.5 * 1.45 + 2.5 + 5;

  // ── 글자 도우미 ───────────────────────────────────────────

  /// 자기소개서 소제목을 `[소제목]`으로. 학생이 이미 괄호를 쳤으면 겹치지 않게 벗긴다.
  @visibleForTesting
  static String bracketed(String subtitle) {
    var s = subtitle.trim();
    const pairs = {'[': ']', '「': '」', '『': '』', '<': '>', '"': '"', '“': '”'};
    for (final entry in pairs.entries) {
      if (s.length > 1 && s.startsWith(entry.key) && s.endsWith(entry.value)) {
        s = s.substring(1, s.length - 1).trim();
        break;
      }
    }
    return '[$s]';
  }

  /// 쪽 끝에서 줄 단위로 끊겨 다음 쪽으로 이어지는 본문.
  static pw.Widget _spanText(
    String text, {
    pw.TextStyle? style,
    pw.TextAlign align = pw.TextAlign.left,
  }) => pw.Text(
    text,
    style: style,
    textAlign: align,
    overflow: pw.TextOverflow.span,
  );

  static String _joined(List<String> values) =>
      values.map((v) => v.trim()).where((v) => v.isNotEmpty).join(' · ');

  /// 입력 형식과 상관없이 `2023.07`로. 재직 중이면 끝을 `현재`로 적는다.
  @visibleForTesting
  static String period(String start, String end, {bool isCurrent = false}) {
    final s = _month(start);
    final e = isCurrent ? '현재' : _month(end);
    if (s.isEmpty) return e;
    if (e.isEmpty) return s;
    return '$s – $e';
  }

  static final _datePattern = RegExp(r'^(\d{4})\D+(\d{1,2})(\D+\d{1,2})?\D*$');

  static String _month(String raw) {
    final value = raw.trim();
    final m = _datePattern.firstMatch(value);
    if (m == null) return value;
    return '${m.group(1)}.${m.group(2)!.padLeft(2, '0')}';
  }

  /// 숙련도가 높은 단계부터 한 줄씩. 기술이 없는 단계는 뺀다.
  /// 숙련도를 안 고른 기술과 예전 자유 입력 값은 맨 아래 '기타'로 모은다.
  @visibleForTesting
  static List<({String label, String names})> skillRows(
    List<ResumeTechStackItem> items,
  ) {
    final filled = items.where((e) => e.isFilled).toList();
    String names(Iterable<ResumeTechStackItem> list) =>
        list.map((e) => e.name.trim()).join(', ');
    final rows = [
      for (final level in techSkillLevels.reversed)
        if (filled.any((e) => techSkillLevelOf(e.level)?.label == level.label))
          (
            label: level.label,
            names: names(
              filled.where(
                (e) => techSkillLevelOf(e.level)?.label == level.label,
              ),
            ),
          ),
    ];
    final others = filled.where((e) => techSkillLevelOf(e.level) == null);
    if (others.isNotEmpty) rows.add((label: '기타', names: names(others)));
    return rows;
  }
}

/// 섹션 안의 항목 하나. 제목줄(이름·기간)과 본문으로 나뉜다.
class _Item {
  _Item({
    this.name = '',
    this.sub = '',
    this.date = '',
    this.meta = '',
    this.body = '',
    this.footnote = '',
    this.label,
  });

  final String name;
  final String sub;
  final String date;
  final String meta;
  final String body;
  final String footnote;

  /// 기술스택처럼 왼쪽에 짧은 이름표를 두는 줄
  final String? label;

  static const _bodyWidth = ResumePdfExporter._contentWidth;

  bool get _hasHead => name.trim().isNotEmpty;

  /// 본문 줄 수 어림값. 한글은 글자 폭이 글자 크기와 거의 같다.
  int get _bodyLines {
    final text = body.trim();
    if (text.isEmpty) return 0;
    final width = label == null ? _bodyWidth : _bodyWidth - 44;
    final perLine = (width / (ResumePdfExporter._body * 0.92)).floor();
    return text
        .split('\n')
        .map((p) => p.isEmpty ? 1 : (p.length / perLine).ceil())
        .fold(0, (a, b) => a + b);
  }

  double get _headHeight =>
      (_hasHead ? ResumePdfExporter._lineHeight(ResumePdfExporter._body) : 0) +
      (meta.trim().isEmpty
          ? 0
          : ResumePdfExporter._lineHeight(ResumePdfExporter._small)) +
      (footnote.trim().isEmpty
          ? 0
          : ResumePdfExporter._lineHeight(ResumePdfExporter._small));

  /// 다음 쪽으로 함께 넘길 높이. 짧으면 항목 전체, 길면 제목줄과 첫 몇 줄.
  double get keepHeight {
    final line = ResumePdfExporter._lineHeight(ResumePdfExporter._body);
    final whole = _headHeight + _bodyLines * line + 2;
    if (whole <= ResumePdfExporter._keepWholeUpTo) return whole;
    return _headHeight + ResumePdfExporter._keepLines * line + 2;
  }

  List<pw.Widget> get widgets {
    final text = body.trim();
    if (label != null) {
      return [
        pw.Row(
          crossAxisAlignment: pw.CrossAxisAlignment.start,
          children: [
            pw.SizedBox(
              width: 44,
              child: pw.Text(
                label!,
                style: const pw.TextStyle(
                  fontSize: ResumePdfExporter._small,
                  color: ResumePdfExporter._muted,
                ),
              ),
            ),
            pw.Expanded(child: pw.Text(text)),
          ],
        ),
      ];
    }

    return [
      if (_hasHead)
        pw.Row(
          crossAxisAlignment: pw.CrossAxisAlignment.start,
          children: [
            pw.Expanded(
              child: pw.RichText(
                text: pw.TextSpan(
                  children: [
                    pw.TextSpan(
                      text: name.trim(),
                      style: pw.TextStyle(
                        fontWeight: pw.FontWeight.bold,
                        color: ResumePdfExporter._ink,
                      ),
                    ),
                    if (sub.trim().isNotEmpty)
                      pw.TextSpan(
                        text: '  ·  ${sub.trim()}',
                        style: const pw.TextStyle(
                          color: ResumePdfExporter._muted,
                        ),
                      ),
                  ],
                ),
              ),
            ),
            if (date.isNotEmpty) ...[
              pw.SizedBox(width: 12),
              pw.Text(
                date,
                style: const pw.TextStyle(
                  fontSize: ResumePdfExporter._small,
                  color: ResumePdfExporter._muted,
                ),
              ),
            ],
          ],
        ),
      if (meta.trim().isNotEmpty)
        pw.Text(
          meta.trim(),
          style: const pw.TextStyle(
            fontSize: ResumePdfExporter._small,
            color: ResumePdfExporter._muted,
          ),
        ),
      if (text.isNotEmpty) ...[
        if (_hasHead) pw.SizedBox(height: 2),
        ResumePdfExporter._spanText(text),
      ],
      if (footnote.trim().isNotEmpty)
        pw.Text(
          footnote.trim(),
          style: const pw.TextStyle(
            fontSize: ResumePdfExporter._small,
            color: ResumePdfExporter._muted,
          ),
        ),
    ];
  }
}
