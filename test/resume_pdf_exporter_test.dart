import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:playdata_lms/core/theme/app_space.dart';
import 'package:playdata_lms/features/resume/services/resume_pdf_exporter.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';
import 'package:playdata_lms/shared/models/resume_model.dart';

/// 실제 앱은 Noto Sans KR을 내려받는다. 시험에서는 내려받지 않고 저장소에 있는
/// 한글 글꼴을 쓴다. 기본 글꼴은 한글이 없어 쪽 나눔을 제대로 잴 수 없다.
pw.ThemeData _theme() {
  pw.Font load(String file) => pw.Font.ttf(
    ByteData.sublistView(
      File('assets/fonts/Paperlogy/$file').readAsBytesSync(),
    ),
  );
  return pw.ThemeData.withFont(
    base: load('Paperlogy-4Regular.ttf'),
    bold: load('Paperlogy-7Bold.ttf'),
  );
}

ResumeModel _resume(ResumeContent content, {String title = '네이버클라우드 지원'}) =>
    ResumeModel(
      id: 'r1',
      userId: 'u1',
      title: title,
      status: 'draft',
      sections: const {},
      content: content,
    );

int _pages(ResumeModel resume) => ResumePdfExporter.buildDocument(
  resume,
  theme: _theme(),
).document.pdfPageList.pages.length;

const _sentence = '추천 점검 스크립트로 상위 다섯 개 적중률을 재고 규칙을 고쳤습니다. ';

void main() {
  tearDown(() => AppSpace.apply(compact: false));

  group('글자 정리', () {
    test('dates read as year.month and ongoing ends with 현재', () {
      expect(
        ResumePdfExporter.period('2023-07-01', '2023-12-31'),
        '2023.07 – 2023.12',
      );
      expect(ResumePdfExporter.period('2023.7', ''), '2023.07');
      expect(
        ResumePdfExporter.period('2024-03-01', '', isCurrent: true),
        '2024.03 – 현재',
      );
      // 날짜 모양이 아니면 적은 그대로 둔다.
      expect(ResumePdfExporter.period('2023년 봄', ''), '2023년 봄');
      expect(ResumePdfExporter.period('', ''), '');
    });

    test('contact line keeps only what was filled', () {
      // 예전에는 비어 있어도 "김하늘 ·  · "처럼 점이 남았다.
      expect(
        ResumePdfExporter.contactLine(
          const ResumeBasicInfo(
            name: '김하늘',
            phone: '010-1234-5678',
            githubUrl: ' ',
          ),
        ),
        '010-1234-5678',
      );
      expect(ResumePdfExporter.contactLine(const ResumeBasicInfo()), '');
    });

    test('self-intro subtitles get one pair of brackets', () {
      expect(ResumePdfExporter.bracketed(' 끝까지 뜯어보던 아이 '), '[끝까지 뜯어보던 아이]');
      // 학생이 이미 괄호를 쳤으면 [[…]]가 되지 않게 한다.
      expect(ResumePdfExporter.bracketed('[끝까지 뜯어보던 아이]'), '[끝까지 뜯어보던 아이]');
      expect(ResumePdfExporter.bracketed('「데이터시트를 읽습니다」'), '[데이터시트를 읽습니다]');
    });

    test('skills group by the five levels, highest first, others last', () {
      final rows = ResumePdfExporter.skillRows(const [
        ResumeTechStackItem(id: '1', name: 'Docker', level: '초급'),
        ResumeTechStackItem(id: '2', name: 'Python', level: '고급'),
        ResumeTechStackItem(id: '3', name: 'SQL', level: '고급'),
        ResumeTechStackItem(id: '4', name: 'Rust', level: '관심'),
        ResumeTechStackItem(id: '5', name: 'Go'),
        ResumeTechStackItem(id: '6', name: ' '),
      ]);
      expect(rows.map((r) => r.label), ['고급', '초급', '기타']);
      expect(rows.first.names, 'Python, SQL');
      expect(rows.last.names, 'Rust, Go');
    });
  });

  test('every filled section is printed, empty ones are skipped', () {
    // 예전 PDF에는 자격·수상·교육·기타활동이 아예 없었다.
    const content = ResumeContent(
      coreCompetencies: ResumeCoreCompetencies(text: '검색 품질 개선'),
      experience: [ResumeExperienceItem(id: 'e', company: '데이터랩스')],
      education: [ResumeEducationItem(id: 'd', school: '한국대학교')],
      techStack: [ResumeTechStackItem(id: 't', name: 'Python')],
      certifications: [ResumeCertificationItem(id: 'c', name: 'SQLD')],
      awards: [ResumeAwardItem(id: 'a', name: '우수상')],
      trainingExperience: [ResumeTrainingItem(id: 'tr', course: 'AI 캠프')],
      otherActivities: [ResumeActivityItem(id: 'o', name: '번역 스터디')],
      projects: [ResumeProjectItem(id: 'p', name: '커리어 챗봇')],
      selfIntroduction: ResumeSelfIntroduction(
        motivation: ResumeIntroSection(body: '지원동기'),
      ),
    );
    expect(ResumePdfExporter.printedSections(content), [
      'coreCompetencies',
      'experience',
      'education',
      'techStack',
      'certifications',
      'awards',
      'trainingExperience',
      'otherActivities',
      'projects',
      'selfIntroduction',
    ]);
    expect(
      ResumePdfExporter.printedSections(
        const ResumeContent(
          awards: [ResumeAwardItem(id: 'a')],
          projects: [ResumeProjectItem(id: 'p', name: '커리어 챗봇')],
        ),
      ),
      ['projects'],
    );
    expect(_pages(_resume(content)), 2);
  });

  test('a description longer than a page flows on instead of failing', () {
    // 예전에는 한 칸이 한 쪽을 넘으면 "Widget won't fit into the page"로
    // PDF가 아예 만들어지지 않았다.
    final content = ResumeContent(
      basicInfo: const ResumeBasicInfo(name: '김하늘'),
      experience: [
        ResumeExperienceItem(
          id: 'e',
          company: '데이터랩스',
          role: '인턴',
          description: _sentence * 120,
        ),
      ],
      selfIntroduction: ResumeSelfIntroduction(
        growth: ResumeIntroSection(
          subtitle: '끝까지 뜯어보던 아이',
          body: _sentence * 120,
        ),
      ),
    );
    expect(_pages(_resume(content)), greaterThanOrEqualTo(4));
  });

  test('self introduction alone does not leave a blank first page', () {
    const content = ResumeContent(
      basicInfo: ResumeBasicInfo(name: '김하늘'),
      selfIntroduction: ResumeSelfIntroduction(
        motivation: ResumeIntroSection(body: '검색 품질을 숫자로 말하는 개발자입니다.'),
      ),
    );
    expect(_pages(_resume(content)), 1);
  });

  test('compact density does not change the PDF', () {
    // 간격을 화면용 AppSpace로 재던 때는 '좁게'면 PDF 간격까지 줄었다.
    final content = ResumeContent(
      basicInfo: const ResumeBasicInfo(name: '김하늘'),
      projects: [
        for (var i = 0; i < 40; i++)
          ResumeProjectItem(
            id: 'p$i',
            name: '프로젝트 $i',
            startDate: '2026-01-01',
            role: '백엔드',
            description: _sentence * 2,
          ),
      ],
    );
    AppSpace.apply(compact: false);
    final roomy = _pages(_resume(content));
    AppSpace.apply(compact: true);
    final tight = _pages(_resume(content));
    expect(roomy, greaterThan(1));
    expect(tight, roomy);
  });
}
