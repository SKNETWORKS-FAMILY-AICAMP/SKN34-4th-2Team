import { SelfIntroKeys, SelfIntroLabels } from '../../domain/constants';
import type { Resume, ResumeContent } from '../../domain/types';

/**
 * 인쇄용 이력서 — features/resume/services/resume_pdf_exporter.dart
 *
 * 화면(Doc 보기)을 그대로 인쇄하지 않는다. 원본은 PDF를 따로 조판한다: 네모 칸
 * 없이 이력서 제목(큰 글씨) · 이름 · 연락처로 시작하고, 섹션 제목 아래 실선을 긋고, 항목은
 * 「이름 · 부제 ......... 기간」 한 줄과 본문으로만 적는다. 종이에는 카드 테두리도
 * 라벨(「항목 1」, 「회사명」)도 없다.
 *
 * 치수는 pt 상수 그대로다 — 본문 9.5, 작은 글씨 8.6, 섹션 제목 11, 이력서 제목 19.
 */
/** 연락처는 라벨을 붙여 한 줄에 늘어놓는다. 주소는 https:// 와 끝 / 를 떼어 짧게 */
function contactItems(c: ResumeContent): { label: string; value: string }[] {
  const i = c.basicInfo;
  const short = (url: string) => url.trim().replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/+$/, '');
  return [
    { label: '이메일', value: i.email.trim() },
    { label: '연락처', value: i.phone.trim() },
    { label: 'GitHub', value: short(i.githubUrl) },
    { label: 'Blog', value: short(i.blogUrl) },
  ].filter((item) => item.value !== '');
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
  // 큰 글씨는 이력서 제목, 그 아래 이름. 제목을 안 정했으면(「새 이력서」) 이름이 큰 글씨가 된다
  const title = resume.title.trim();
  const hasTitle = title !== '' && title !== '새 이력서';
  const heading = hasTitle ? title : name;
  const byline = hasTitle ? name : '';
  const contact = contactItems(c);

  // 기술스택은 숙련도별로 한 줄씩 묶는다 — skillRows와 같은 방식.
  // 「입문」과 숙련도를 안 고른 기술은 예전에 빠졌다. 입문은 제 줄, 안 고른 것은 「기타」 줄에 둔다
  const levels = ['고급', '중급', '초급', '입문'];
  const named = c.techStack.filter((t) => t.name.trim() !== '');
  const techRows = [
    ...levels.map((level) => ({ level, names: named.filter((t) => t.level === level).map((t) => t.name).join(', ') })),
    { level: '기타', names: named.filter((t) => !levels.includes(t.level)).map((t) => t.name).join(', ') },
  ].filter((row) => row.names !== '');

  const intro = SelfIntroKeys.filter((key) => c.selfIntroduction[key].body.trim() !== '');

  return (
    <div className="print-doc" aria-hidden>
      <header className="print-doc__header">
        <h1 className="print-doc__heading">{heading}</h1>
        {byline !== '' && <p className="print-doc__byline">{byline}</p>}
        {contact.length > 0 && (
          <ul className="print-doc__contact">
            {contact.map((item) => (
              <li key={item.label}>
                <span className="print-doc__contact-label">{item.label}</span>
                {item.value}
              </li>
            ))}
          </ul>
        )}
      </header>

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

      {/* 문항(자기소개 · 지원동기 …)은 자기소개서 한 섹션 안의 소제목이다. 학력 · 기술스택과 같은 급으로 세우지 않는다 */}
      {intro.length > 0 && (
        <Section title="자기소개서">
          {intro.map((key) => {
            const { subtitle, body } = c.selfIntroduction[key];
            return (
              <div key={key} className="print-doc__qa">
                <h3 className="print-doc__question">{SelfIntroLabels[key]}</h3>
                {subtitle.trim() !== '' && <p className="print-doc__answer-title">{subtitle}</p>}
                <p className="print-doc__body">{body}</p>
              </div>
            );
          })}
        </Section>
      )}
    </div>
  );
}
