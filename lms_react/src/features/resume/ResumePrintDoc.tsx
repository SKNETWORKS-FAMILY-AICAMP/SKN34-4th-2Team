import { SelfIntroKeys, SelfIntroLabels } from '../../domain/constants';
import type { Resume, ResumeContent } from '../../domain/types';

/**
 * 인쇄용 이력서 — features/resume/services/resume_pdf_exporter.dart
 *
 * 화면(Doc 보기)을 그대로 인쇄하지 않는다. 원본은 PDF를 따로 조판한다: 네모 칸
 * 없이 이름·연락처 한 줄로 시작하고, 섹션 제목 아래 실선을 긋고, 항목은
 * 「이름 · 부제 ......... 기간」 한 줄과 본문으로만 적는다. 종이에는 카드 테두리도
 * 라벨(「항목 1」, 「회사명」)도 없다.
 *
 * 치수는 pt 상수 그대로다 — 본문 9.5, 작은 글씨 8.6, 섹션 제목 11, 이름 20.
 */
function contactLine(c: ResumeContent): string {
  const i = c.basicInfo;
  return [i.email, i.phone, i.githubUrl, i.blogUrl]
    .map((v) => v.trim())
    .filter((v) => v !== '')
    .join('  ·  ');
}

/** 기간 표기 — period(startDate, endDate) */
function period(start: string, end: string, isCurrent = false): string {
  const s = start.trim();
  const e = isCurrent ? '현재' : end.trim();
  if (s === '' && e === '') return '';
  if (s === '') return e;
  if (e === '') return s;
  return `${s} ~ ${e}`;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="print-doc__section">
      <h2 className="print-doc__title">{title}</h2>
      {children}
    </section>
  );
}

function Item({
  name,
  sub,
  date,
  meta,
  body,
  footnote,
}: {
  name?: string;
  sub?: string;
  date?: string;
  meta?: string;
  body?: string;
  footnote?: string;
}) {
  return (
    <div className="print-doc__item">
      {name !== undefined && name !== '' && (
        <p className="print-doc__head">
          <span>
            <strong>{name}</strong>
            {sub !== undefined && sub !== '' && <span className="print-doc__muted">  ·  {sub}</span>}
          </span>
          {date !== undefined && date !== '' && <span className="print-doc__date">{date}</span>}
        </p>
      )}
      {meta !== undefined && meta !== '' && <p className="print-doc__meta">{meta}</p>}
      {body !== undefined && body !== '' && <p className="print-doc__body">{body}</p>}
      {footnote !== undefined && footnote !== '' && <p className="print-doc__meta">{footnote}</p>}
    </div>
  );
}

export function ResumePrintDoc({ resume }: { resume: Resume }) {
  const c = resume.content;
  const name = c.basicInfo.name.trim();
  const heading = name === '' ? resume.title : name;
  const showTitle = name !== '' && resume.title !== '' && resume.title !== '새 이력서';
  const contact = contactLine(c);

  // 기술스택은 숙련도별로 한 줄씩 묶는다 — skillRows와 같은 방식.
  const levels = ['고급', '중급', '초급'];
  const techRows = levels
    .map((level) => ({
      level,
      names: c.techStack.filter((t) => t.level === level).map((t) => t.name).join(', '),
    }))
    .filter((row) => row.names !== '');

  const intro = SelfIntroKeys.filter((key) => c.selfIntroduction[key].body.trim() !== '');

  return (
    <div className="print-doc" aria-hidden>
      <h1 className="print-doc__name">{heading}</h1>
      {showTitle && <p className="print-doc__subtitle">{resume.title}</p>}
      {contact !== '' && <p className="print-doc__contact">{contact}</p>}

      {c.coreCompetencies.text.trim() !== '' && (
        <Section title="핵심역량/강점">
          <Item body={c.coreCompetencies.text} />
        </Section>
      )}

      {c.experience.length > 0 && (
        <Section title="경력사항">
          {c.experience.map((e) => (
            <Item
              key={e.id}
              name={e.company}
              sub={e.role}
              date={period(e.startDate, e.endDate, e.isCurrent)}
              body={e.description}
            />
          ))}
        </Section>
      )}

      {c.education.length > 0 && (
        <Section title="학력사항">
          {c.education.map((e) => (
            <Item
              key={e.id}
              name={e.school}
              sub={[e.major, e.status].filter((v) => v.trim() !== '').join(' · ')}
              date={period(e.startDate, e.endDate)}
            />
          ))}
        </Section>
      )}

      {techRows.length > 0 && (
        <Section title="기술스택">
          {techRows.map((row) => (
            <div key={row.level} className="print-doc__skill-row">
              <span className="print-doc__skill-label">{row.level}</span>
              <span>{row.names}</span>
            </div>
          ))}
        </Section>
      )}

      {c.certifications.length > 0 && (
        <Section title="자격사항">
          {c.certifications.map((e) => (
            <Item key={e.id} name={e.name} sub={e.issuer} date={e.acquiredDate} />
          ))}
        </Section>
      )}

      {c.awards.length > 0 && (
        <Section title="수상내역">
          {c.awards.map((e) => (
            <Item key={e.id} name={e.name} sub={e.organization} date={e.date} body={e.description} />
          ))}
        </Section>
      )}

      {c.trainingExperience.length > 0 && (
        <Section title="교육경험">
          {c.trainingExperience.map((e) => (
            <Item
              key={e.id}
              name={e.course}
              sub={e.organization}
              date={period(e.startDate, e.endDate)}
              body={e.description}
            />
          ))}
        </Section>
      )}

      {c.otherActivities.length > 0 && (
        <Section title="기타활동">
          {c.otherActivities.map((e) => (
            <Item key={e.id} name={e.name} date={period(e.startDate, e.endDate)} body={e.description} />
          ))}
        </Section>
      )}

      {c.projects.length > 0 && (
        <Section title="프로젝트 경험">
          {c.projects.map((p) => (
            <Item
              key={p.id}
              name={p.name}
              date={period(p.startDate, p.endDate)}
              meta={[p.role, p.techStack].filter((v) => v.trim() !== '').join(' · ')}
              body={p.description}
              footnote={p.url}
            />
          ))}
        </Section>
      )}

      {intro.length > 0 && (
        <div className="print-doc__intro">
          {intro.map((key) => (
            <Section key={key} title={SelfIntroLabels[key]}>
              <Item
                sub={c.selfIntroduction[key].subtitle}
                body={c.selfIntroduction[key].body}
              />
            </Section>
          ))}
        </div>
      )}
    </div>
  );
}
