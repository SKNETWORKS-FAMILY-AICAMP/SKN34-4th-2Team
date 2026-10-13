import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { RoutePaths, instructorBoardNoticeEditPath } from '../../app/routePaths';
import { useNotices } from '../../data/repository';
import { InstructorTargets } from '../../tour/targets';
import { useTourTarget } from '../../tour/useTourTarget';
import { useCurrentUser } from '../auth/session';
import {
  Badge,
  Button,
  Card,
  DataTable,
  PageHeader,
  Row,
  Spacer,
  TextInput,
} from '../../ui/components';
import { formatDateTime } from '../../utils/format';

/** 게시물관리 — features/instructor/presentation/instructor_board_screen.dart */
export function InstructorBoardScreen() {
  const user = useCurrentUser();
  const notices = useNotices();
  const navigate = useNavigate();
  const createRef = useTourTarget(InstructorTargets.boardCreate);
  const [query, setQuery] = useState('');

  const q = query.trim().toLowerCase();
  const rows = q === '' ? notices : notices.filter((n) => n.title.toLowerCase().includes(q));

  return (
    <div className="screen__inner">
      <PageHeader
        title="게시판 관리"
        description={`${user.cohortName} · 본인이 등록한 글만 수정할 수 있습니다.`}
        actions={
          <Link className="btn btn--filled btn--md" ref={createRef} to={RoutePaths.instructorBoardCreate}>
            공지 작성
          </Link>
        }
      />

      <Card
        padded={false}
        title="공지 목록"
        actions={
          <TextInput
            value={query}
            placeholder="제목 검색"
            style={{ width: 180 }}
            onChange={(e) => setQuery(e.target.value)}
          />
        }
      >
        <DataTable
          rows={rows}
          rowKey={(n) => n.id}
          empty="등록된 공지가 없습니다."
          columns={[
            {
              key: 'title',
              header: '제목',
              render: (n) => (
                <Row gap={6}>
                  {n.isFavorite && <Badge tone="error">중요</Badge>}
                  <span>{n.title}</span>
                </Row>
              ),
            },
            {
              key: 'author',
              header: '작성자',
              width: '150px',
              render: (n) => <span style={{ whiteSpace: 'nowrap' }}>{n.authorName}</span>,
            },
            { key: 'date', header: '작성일', width: '160px', render: (n) => formatDateTime(n.createdAt) },
            {
              key: 'actions',
              header: '',
              width: '80px',
              align: 'right',
              render: (n) => n.authorId === user.uid ? (
                <Row gap={4} wrap={false}>
                  <Spacer />
                  <Button size="sm" variant="outline" onClick={() => navigate(instructorBoardNoticeEditPath(n.id))}>
                    수정
                  </Button>
                </Row>
              ) : null,
            },
          ]}
        />
      </Card>
    </div>
  );
}
