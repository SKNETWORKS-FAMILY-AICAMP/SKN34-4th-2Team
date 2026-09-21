import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import {
  createSubmission,
  reviewSubmission,
  useMySubmissions,
  useSubmissions,
} from '../../data/repository';
import {
  CertKinds,
  RecordTypeDescriptions,
  RecordTypeLabels,
  SubmissionStatusLabels,
} from '../../domain/constants';
import { buildMissionGuidance, missionProgressOf } from '../../domain/missions';
import type { RecordType, Submission } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import {
  Badge,
  Button,
  Card,
  Checkbox,
  Dialog,
  Field,
  PageHeader,
  Row,
  Select,
  Spacer,
  TextArea,
  TextInput,
} from '../../ui/components';
import { formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';

/**
 * 기록실 — features/records/presentation/records_screen.dart
 *
 * 검색 한 줄, 필터 칩 한 줄(종류 + 상태), 오른쪽에 「새로운 기록 추가」.
 * 그 아래 「마일리지 미션」 안내가 접히는 카드로 서고, 제출한 기록이 이어진다.
 */
const RECORD_TYPES: RecordType[] = [
  'certification',
  'study',
  'blog',
  'studyCert',
  'precourseQuiz',
];

export function RecordsScreen() {
  return <RecordsBoard reviewer={false} />;
}

/**
 * 기록실 본문 — 학생과 관리자가 같은 화면을 쓴다(records_screen.dart의 isAdmin 가지).
 *
 * 관리자는 모두의 기록을 보고 카드에서 바로 승인·반려한다. 미션 안내와
 * 「새로운 기록 추가」는 학생에게만 있다.
 */
export function RecordsBoard({ reviewer }: { reviewer: boolean }) {
  const user = useCurrentUser();
  const mine = useMySubmissions(user.uid);
  const everyone = useSubmissions();
  const submissions = reviewer ? everyone : mine;

  const [query, setQuery] = useState('');
  const [type, setType] = useState<RecordType | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const q = query.trim().toLowerCase();
  const filtered = submissions.filter((s) => {
    if (type !== null && s.type !== type) return false;
    if (status !== null && s.status !== status) return false;
    if (q === '') return true;
    return (
      s.title.toLowerCase().includes(q) ||
      s.userDisplayName.toLowerCase().includes(q) ||
      (s.certType ?? '').toLowerCase().includes(q)
    );
  });

  return (
    <div className="screen__inner record-page">
      <header className="study-head">
        <div>
          <h1 className="study-head__title">기록실</h1>
          <p className="study-head__desc">블로그, 스터디, 자격증 기록을 제출하고 관리하세요.</p>
        </div>
        <span className="who-chip">
          <span className="who-chip__avatar">{user.displayName.slice(0, 1)}</span>
          <span className="who-chip__text">
            <strong>{user.displayName}</strong>
            <span>{user.cohortName}</span>
          </span>
        </span>
      </header>

      <label className="study-search">
        <Icon name="search" size={20} />
        <input
          className="study-search__input"
          value={query}
          placeholder="제목·이름 검색"
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>

      {/* 종류 칩과 상태 칩이 한 줄에 선다. 상태 칩은 다시 누르면 풀린다. */}
      <div className="rec-filters">
        <button
          type="button"
          className={`rec-chip${type === null ? ' rec-chip--on' : ''}`}
          onClick={() => setType(null)}
        >
          {type === null && <Icon name="check" size={15} />}
          전체
        </button>
        {RECORD_TYPES.map((t) => (
          <button
            key={t}
            type="button"
            className={`rec-chip${type === t ? ' rec-chip--on' : ''}`}
            onClick={() => setType(t)}
          >
            {type === t && <Icon name="check" size={15} />}
            {RecordTypeLabels[t]}
          </button>
        ))}
        <span className="rec-filters__gap" />
        {(
          [
            ['pending', '대기'],
            ['approved', '승인'],
            ['rejected', '반려'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`rec-chip${status === id ? ' rec-chip--on' : ''}`}
            onClick={() => setStatus(status === id ? null : id)}
          >
            {status === id && <Icon name="check" size={15} />}
            {label}
          </button>
        ))}
      </div>

      {!reviewer && (
        <div className="rec-add">
          <Link className="btn btn--filled btn--md" to={RoutePaths.recordsCreate}>
            <Icon name="add" size={18} />
            새로운 기록 추가
          </Link>
        </div>
      )}

      {!reviewer && <MissionGuidancePanel submissions={submissions} />}

      {filtered.length === 0 ? (
        <p className="rec-empty">
          {reviewer ? '제출된 기록이 없습니다' : '아직 제출한 기록이 없습니다'}
        </p>
      ) : (
        <div className="stack">
          {filtered.map((s) => (
            <RecordCard key={s.id} submission={s} reviewer={reviewer} />
          ))}
        </div>
      )}
    </div>
  );
}

/** 마일리지 미션 — widgets/mission_guidance_panel.dart. 처음에는 펼쳐져 있다. */
export function MissionGuidancePanel({ submissions }: { submissions: Submission[] }) {
  const [open, setOpen] = useState(true);
  const items = buildMissionGuidance(missionProgressOf(submissions));

  return (
    <section className="mission-panel">
      <button type="button" className="mission-panel__head" onClick={() => setOpen((v) => !v)}>
        <Icon name="emoji_events" size={20} />
        <strong>마일리지 미션</strong>
        <span className="spacer" />
        <Icon name={open ? 'expand_less' : 'expand_more'} size={20} />
      </button>

      {open && (
        <div className="mission-panel__body">
          <p className="hint">기록실에 제출하고 승인되면 규칙에 따라 자동 적립됩니다.</p>
          {items.map((item) => (
            <div key={item.id} className="mission-tile">
              <strong className="mission-tile__title">{item.title}</strong>
              <span className="mission-tile__progress">{item.progressLabel}</span>
              <span className="mission-tile__status">{item.statusText}</span>
              <span className="mission-tile__hint">{item.hint}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function RecordCard({ submission, reviewer }: { submission: Submission; reviewer: boolean }) {
  const [detailOpen, setDetailOpen] = useState(false);
  const tone =
    submission.status === 'approved'
      ? 'success'
      : submission.status === 'pending'
        ? 'warning'
        : 'error';

  // 원본은 「(이름) · 부제 · 제출 시각」을 한 줄로 이어 붙인다.
  const meta = [
    reviewer ? submission.userDisplayName : null,
    submission.certType,
    submission.submittedAt === undefined ? null : `제출 ${formatDateTime(submission.submittedAt)}`,
  ].filter((v): v is string => v !== null && v !== undefined && v !== '');

  return (
    <article className="rec-card">
      <header className="rec-card__head">
        <span className="rec-card__type">{RecordTypeLabels[submission.type]}</span>
        {submission.link !== undefined && <Icon name="link" size={14} className="rec-card__clip" />}
        {submission.fileUrls.length > 0 && (
          <span className="rec-card__files">
            <Icon name="attach_file" size={14} />
            {submission.fileUrls.length}
          </span>
        )}
        <span className="spacer" />
        <Badge tone={tone}>{SubmissionStatusLabels[submission.status]}</Badge>
      </header>

      <strong className="rec-card__title">{submission.title}</strong>
      {meta.length > 0 && <p className="rec-card__meta">{meta.join(' · ')}</p>}

      {submission.learningContent !== undefined && (
        <p className="muted">{submission.learningContent}</p>
      )}
      {submission.quizScore !== undefined && (
        <span className="hint">점수 {submission.quizScore}점</span>
      )}
      {submission.reviewComment !== undefined && (
        <div className="callout callout--error">반려 사유 · {submission.reviewComment}</div>
      )}
      {submission.mileageGranted && (
        <div className="callout callout--success">
          마일리지 {submission.mileageAmount.toLocaleString()}M 적립
        </div>
      )}

      <footer className="rec-card__foot">
        <button type="button" className="btn btn--text btn--sm" onClick={() => setDetailOpen(true)}>
          상세 보기
        </button>
        <span className="spacer" />
        {reviewer && submission.status === 'pending' && (
          <>
            <button
              type="button"
              className="btn btn--outline btn--sm"
              onClick={() => reviewSubmission(submission.id, 'rejected')}
            >
              반려
            </button>
            <button
              type="button"
              className="btn btn--filled btn--sm rec-card__approve"
              onClick={() => reviewSubmission(submission.id, 'approved')}
            >
              승인
            </button>
          </>
        )}
      </footer>

      {detailOpen && (
        <SubmissionDetailDialog
          submission={submission}
          reviewer={reviewer}
          onClose={() => setDetailOpen(false)}
        />
      )}
    </article>
  );
}

function SubmissionDetailDialog({
  submission,
  reviewer,
  onClose,
}: {
  submission: Submission;
  reviewer: boolean;
  onClose(): void;
}) {
  const review = (status: 'approved' | 'rejected') => {
    reviewSubmission(submission.id, status);
    onClose();
  };

  const rows: Array<[string, string | number | undefined]> = [
    ['제출자', submission.userDisplayName],
    ['제출 시각', submission.submittedAt === undefined ? undefined : formatDateTime(submission.submittedAt)],
    ['자격 종류', submission.certType],
    ['점수', submission.quizScore === undefined ? undefined : `${submission.quizScore}점`],
    ['학습일자', submission.learningDate === undefined ? undefined : formatDateTime(submission.learningDate)],
    ['학습 내용', submission.learningContent],
    ['팀 스터디', submission.isTeamStudy === undefined ? undefined : submission.isTeamStudy ? '예' : '아니오 (개인)'],
    ['주차', submission.weekLabel],
    ['적립', submission.mileageAmount > 0 ? `${submission.mileageAmount.toLocaleString()}M` : undefined],
    ['반려 사유', submission.reviewComment],
  ];

  return (
    <Dialog
      title="제출 상세"
      onClose={onClose}
      actions={
        reviewer && submission.status === 'pending' ? (
          <>
            <Button variant="outline" onClick={() => review('rejected')}>반려</Button>
            <Button onClick={() => review('approved')}>승인</Button>
          </>
        ) : (
          <Button onClick={onClose}>닫기</Button>
        )
      }
    >
      <div className="submission-detail">
        <div className="submission-detail__top">
          <span className="rec-card__type">{RecordTypeLabels[submission.type]}</span>
          <Badge tone={submission.status === 'approved' ? 'success' : submission.status === 'pending' ? 'warning' : 'error'}>
            {SubmissionStatusLabels[submission.status]}
          </Badge>
        </div>
        <h3>{submission.title}</h3>
        <dl className="submission-detail__rows">
          {rows.map(([label, value]) =>
            value === undefined || value === '' ? null : (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ),
          )}
        </dl>

        {submission.link !== undefined && submission.link !== '' && (
          <section className="submission-detail__section">
            <strong>링크</strong>
            <a href={submission.link} target="_blank" rel="noreferrer">
              {submission.link}
              <Icon name="open_in_new" size={15} />
            </a>
          </section>
        )}

        <section className="submission-detail__section">
          <strong>증빙 파일 ({submission.fileUrls.length})</strong>
          {submission.fileUrls.length === 0 ? (
            <p className="hint">첨부된 증빙이 없습니다.</p>
          ) : (
            <div className="submission-detail__files">
              {submission.fileUrls.map((url, index) =>
                url.startsWith('demo://') ? (
                  <span key={url} className="submission-file">
                    <Icon name="image" size={18} /> 데모 파일 {index + 1}
                  </span>
                ) : (
                  <a key={url} className="submission-file" href={url} target="_blank" rel="noreferrer">
                    <Icon name="attach_file" size={18} /> 파일 {index + 1}
                    <Icon name="open_in_new" size={14} />
                  </a>
                ),
              )}
            </div>
          )}
        </section>
      </div>
    </Dialog>
  );
}

/** 기록 종류 고르기 — record_type_select_screen.dart */
export function RecordTypeSelectScreen() {
  const types: RecordType[] = ['certification', 'study', 'blog', 'studyCert', 'precourseQuiz'];
  const paths: Record<RecordType, string> = {
    certification: RoutePaths.recordsCreateCert,
    study: RoutePaths.recordsCreateStudy,
    blog: RoutePaths.recordsCreateBlog,
    studyCert: RoutePaths.recordsCreateStudyCert,
    precourseQuiz: RoutePaths.recordsCreatePrecourseQuiz,
  };

  return (
    <div className="screen__inner">
      <PageHeader title="기록 제출" description="제출할 기록의 종류를 고르세요." />
      <div className="grid grid--2">
        {types.map((type) => (
          <Link key={type} to={paths[type]} className="type-card">
            <strong>{RecordTypeLabels[type]}</strong>
            <p className="muted">{RecordTypeDescriptions[type]}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}

/**
 * 기록 제출 폼 — record_*_form_screen.dart 다섯 화면.
 *
 * Dart에서는 화면 파일이 다섯이었지만 채우는 칸만 달랐다. 종류별 칸만 갈아
 * 끼우고 제출 흐름은 한 곳에 둔다.
 */
export function RecordFormScreen({ type }: { type: RecordType }) {
  const user = useCurrentUser();
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [certType, setCertType] = useState<string>(CertKinds[0]);
  const [link, setLink] = useState('');
  const [weekNumber, setWeekNumber] = useState(1);
  const [isTeamStudy, setTeamStudy] = useState(true);
  const [learningContent, setLearningContent] = useState('');
  const [quizScore, setQuizScore] = useState('');
  const [evidenceFiles, setEvidenceFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    if (title.trim() === '') {
      setError('제목을 입력해 주세요.');
      return;
    }
    if (type === 'blog' && link.trim() === '') {
      setError('블로그 링크를 입력해 주세요.');
      return;
    }
    createSubmission({
      userId: user.uid,
      userDisplayName: user.displayName,
      title: title.trim(),
      type,
      status: 'pending',
      certType: type === 'certification' ? certType : undefined,
      link: type === 'blog' ? link.trim() : undefined,
      weekNumber: type === 'blog' || type === 'study' ? weekNumber : undefined,
      weekLabel: type === 'blog' || type === 'study' ? `${weekNumber}주차` : undefined,
      isTeamStudy: type === 'study' ? isTeamStudy : undefined,
      learningContent: type === 'studyCert' ? learningContent.trim() : undefined,
      learningDate: type === 'studyCert' ? new Date() : undefined,
      quizScore: type === 'precourseQuiz' ? Number(quizScore) : undefined,
      // 실제 Storage 연결 전까지 파일명만 데모 URL로 보존한다.
      fileUrls: evidenceFiles.map((file) => `demo://${encodeURIComponent(file.name)}`),
      mileageGranted: false,
      mileageAmount: 0,
    });
    navigate(RoutePaths.records);
  };

  return (
    <div className="screen__inner">
      <PageHeader title={`${RecordTypeLabels[type]} 제출`} />
      <Card>
        <div className="callout">{RecordTypeDescriptions[type]}</div>

        <Field label="제목">
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} placeholder="예) PCCP Lv.2 취득" />
        </Field>

        {type === 'certification' && (
          <Field label="자격증 종류">
            <Select value={certType} onChange={(e) => setCertType(e.target.value)}>
              {CertKinds.map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </Select>
          </Field>
        )}

        {type === 'blog' && (
          <Field label="블로그 링크">
            <TextInput value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://velog.io/@..." />
          </Field>
        )}

        {(type === 'blog' || type === 'study') && (
          <Field label="주차">
            <Select value={weekNumber} onChange={(e) => setWeekNumber(Number(e.target.value))}>
              {Array.from({ length: 12 }, (_, i) => i + 1).map((w) => (
                <option key={w} value={w}>
                  {w}주차
                </option>
              ))}
            </Select>
          </Field>
        )}

        {type === 'study' && (
          <Checkbox checked={isTeamStudy} onChange={setTeamStudy} label="팀 스터디입니다 (개인 스터디는 인정되지 않습니다)" />
        )}

        {type === 'studyCert' && (
          <Field label="학습 내용">
            <TextArea
              value={learningContent}
              onChange={(e) => setLearningContent(e.target.value)}
              placeholder="무엇을 공부했는지 적어 주세요."
            />
          </Field>
        )}

        {type === 'precourseQuiz' && (
          <Field label="퀴즈 점수" hint="60점 이상만 적립됩니다.">
            <TextInput
              type="number"
              value={quizScore}
              onChange={(e) => setQuizScore(e.target.value)}
              placeholder="85"
            />
          </Field>
        )}

        <Field label="증빙 파일" hint="이미지 또는 PDF를 최대 5개까지 선택할 수 있습니다.">
          <TextInput
            type="file"
            accept="image/*,.pdf"
            multiple
            onChange={(e) => {
              const selected = Array.from(e.target.files ?? []);
              setEvidenceFiles((current) => [...current, ...selected].slice(0, 5));
              e.target.value = '';
            }}
          />
          {evidenceFiles.length > 0 && (
            <div className="evidence-files" aria-label="선택한 증빙 파일">
              {evidenceFiles.map((file, index) => (
                <span key={`${file.name}-${file.lastModified}`} className="evidence-file">
                  <Icon name={file.type === 'application/pdf' ? 'picture_as_pdf' : 'image'} size={17} />
                  <span>{file.name}</span>
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`${file.name} 제거`}
                    onClick={() => setEvidenceFiles((files) => files.filter((_, i) => i !== index))}
                  >
                    <Icon name="close" size={15} />
                  </button>
                </span>
              ))}
            </div>
          )}
        </Field>

        {error !== null && <span className="field__error">{error}</span>}

        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(RoutePaths.records)}>
            취소
          </Button>
          <Button onClick={submit}>제출</Button>
        </Row>
      </Card>
    </div>
  );
}

/** 라우트에서 종류를 받아 폼을 여는 얇은 껍데기 */
export function RecordFormRoute() {
  const { type } = useParams<{ type: string }>();
  const map: Record<string, RecordType> = {
    certification: 'certification',
    study: 'study',
    blog: 'blog',
    'study-cert': 'studyCert',
    'precourse-quiz': 'precourseQuiz',
  };
  return <RecordFormScreen type={map[type ?? 'certification'] ?? 'certification'} />;
}
