import type { RecordType, UserRole } from '@web/domain/types';
import type { ReactNode } from 'react';

import {
  ApplyPage,
  JobPage,
  JobsPage,
  ResumeEditPage,
  ResumeListPage,
} from './extra';
import {
  AdminQuestsPage,
  AiPage,
  AlertsAdminPage,
  AssistantPage,
  AttendanceAdminPage,
  CohortsPage,
  CounselPage,
  CurriculumPage,
  ExamDetailPage,
  ExamEditPage,
  ExamsAdminPage,
  FormsAdminPage,
  GradePage,
  MenuPage,
  MileageAdminPage,
  NoticeAdminPage,
  PeoplePage,
  PersonFormPage,
  PersonPage,
  RoomsPage,
  SourcesPage,
  StudyAdminPage,
  TeamEditPage,
} from './staff';
import {
  AttendancePage,
  ChatPage,
  CoachPage,
  DesktopPage,
  FormFillPage,
  FormsPage,
  MyPage,
  NoticePage,
  PostPage,
  QuestsPage,
  SeatingPage,
  SettingsPage,
  TeamsPage,
} from './student';
import { QualPage, WrongPage } from './learning';
import { NotePage, NotesPage } from './notes';
import { RecordDetailPage, RecordFormPage, RecordNewPage, RecordsBoard } from './records';
import { CartPage, ShopPage } from './shop';
import { ExamResultPage, ExamTakePage, ExamsPage } from './exams';

const recordTypes = new Set(['certification', 'study', 'blog', 'studyCert', 'precourseQuiz']);

export function StudentRoute({ parts }: { parts: string[] }): ReactNode {
  const [a, b, c] = parts;
  if (a === 'notice' && b) return <NoticePage id={b} />;
  if (a === 'post' && b) return <PostPage id={b} />;
  if (a === 'records' && b === 'new') return <RecordNewPage />;
  if (a === 'records' && b === 'form' && c && recordTypes.has(c)) return <RecordFormPage type={c as RecordType} />;
  if (a === 'records' && b === 'view' && c) return <RecordDetailPage id={decodeURIComponent(c)} reviewer={false} />;
  if (a === 'records') return <RecordsBoard reviewer={false} />;
  if (a === 'forms' && b) return <FormFillPage id={b} />;
  if (a === 'forms') return <FormsPage />;
  if (a === 'qual') return <QualPage />;
  if (a === 'seating') return <SeatingPage />;
  if (a === 'teams') return <TeamsPage />;
  if (a === 'attendance') return <AttendancePage />;
  if (a === 'notes' && b) return <NotePage id={b} />;
  if (a === 'notes') return <NotesPage />;
  if (a === 'wrong') return <WrongPage />;
  if (a === 'shop') return <ShopPage />;
  if (a === 'cart') return <CartPage />;
  if (a === 'quests') return <QuestsPage />;
  if (a === 'exams' && b && c === 'take') return <ExamTakePage id={b} />;
  if (a === 'exams' && b && c === 'result') return <ExamResultPage id={b} />;
  if (a === 'exams') return <ExamsPage />;
  if (a === 'resume' && b === 'new') return <ResumeEditPage id="" />;
  if (a === 'resume' && b) return <ResumeEditPage id={decodeURIComponent(b)} />;
  if (a === 'resume') return <ResumeListPage />;
  if (a === 'jobs' && b) return <JobPage id={b} />;
  if (a === 'jobs') return <JobsPage />;
  if (a === 'apply') return <ApplyPage />;
  if (a === 'chat') return <ChatPage />;
  if (a === 'coach') return <CoachPage />;
  if (a === 'mypage') return <MyPage />;
  if (a === 'settings') return <SettingsPage />;
  if (a === 'desktop') return <DesktopPage feature={b === 'playground' ? '연습장' : '이 기능'} />;
  return <DesktopPage feature="이 화면" />;
}

export function InstructorRoute({ parts }: { parts: string[] }): ReactNode {
  const [a, b, c, d] = parts;
  if (a === 'menu') return <MenuPage role="instructor" />;
  if (a === 'resumes') return <ResumeListPage />;
  if (a === 'board' || a === 'notice') return <NoticeAdminPage allowScheduled={false} />;
  if (a === 'exams' && b === 'new') return <ExamEditPage />;
  if (a === 'exams' && c === 'edit') return <ExamEditPage id={b} />;
  if (a === 'exams' && c === 'sub' && d) return <GradePage submissionId={d} />;
  if (a === 'exams' && b) return <ExamDetailPage id={b} />;
  if (a === 'exams') return <ExamsAdminPage />;
  if (a === 'curriculum') return <CurriculumPage />;
  if (a === 'sources') return <SourcesPage />;
  if (a === 'mypage') return <MyPage />;
  if (a === 'settings') return <SettingsPage />;
  if (a === 'desktop') return <DesktopPage feature="복습 문제 출제" />;
  if (a === 'teams') return <TeamEditPage />;
  return <MenuPage role="instructor" />;
}

export function AdminRoute({ parts }: { parts: string[] }): ReactNode {
  const [a, b, c, d] = parts;
  if (a === 'menu') return <MenuPage role="admin" />;
  if (a === 'cohorts') return <CohortsPage />;
  if (a === 'students') return <PeoplePage role="student" />;
  if (a === 'instructors') return <PeoplePage role="instructor" />;
  if (a === 'people' && b === 'new' && c) return <PersonFormPage role={c as UserRole} />;
  if (a === 'people' && b) return <PersonPage uid={b} />;
  if (a === 'counsel') return <CounselPage studentId={b} />;
  if (a === 'quests') return <AdminQuestsPage />;
  if (a === 'attendance') return <AttendanceAdminPage />;
  // 관리자 자리 확인은 없앴다 — 예전 주소는 불시 점검이 있는 출석 관리로 연다
  if (a === 'presence') return <AttendanceAdminPage />;
  if (a === 'rooms') return <RoomsPage />;
  if (a === 'teams') return <TeamEditPage />;
  if (a === 'exams' && c === 'sub' && d) return <GradePage submissionId={d} readOnly />;
  if (a === 'exams' && b) return <ExamDetailPage id={b} readOnly />;
  if (a === 'exams') return <ExamsAdminPage readOnly />;
  if (a === 'records' && b) return <RecordDetailPage id={decodeURIComponent(b)} reviewer />;
  if (a === 'records') return <RecordsBoard reviewer />;
  if (a === 'resumes') return <ResumeListPage canApprove />;
  if (a === 'resume' && b) return <ResumeEditPage id={decodeURIComponent(b)} />;
  if (a === 'forms') return <FormsAdminPage />;
  if (a === 'study') return <StudyAdminPage />;
  if (a === 'board' || a === 'notice') return <NoticeAdminPage />;
  if (a === 'scheduled') return <NoticeAdminPage scheduled />;
  if (a === 'alerts') return <AlertsAdminPage />;
  if (a === 'mileage') return <MileageAdminPage />;
  if (a === 'ai') return <AiPage />;
  if (a === 'assistant') return <AssistantPage />;
  if (a === 'settings') return <SettingsPage />;
  if (a === 'mypage') return <MyPage />;
  if (a === 'desktop') return <DesktopPage feature={b === 'seating' ? '좌석 배치 편집' : '이 기능'} />;
  return <MenuPage role="admin" />;
}
