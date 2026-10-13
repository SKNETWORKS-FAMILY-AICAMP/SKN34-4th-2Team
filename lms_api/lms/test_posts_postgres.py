"""소통 피드 — 실제 PostgreSQL 에서 기수 경계 · 권한 · 좋아요 · 댓글. Run only with resume_v2_postgres_test_settings."""
from unittest import skipUnless

from django.db import connection, transaction
from django.test import TransactionTestCase

from lms.models import Cohorts, PostComments, PostLikes, Posts, Users
from lms.post_service import (
    MAX_POST_CHARS, PostError, create_comment, create_post, delete_comment, delete_post, list_comments,
    list_posts, toggle_like,
)

if connection.vendor == 'postgresql':
    config = connection.settings_dict
    if (config['HOST'], str(config['PORT']), config['USER']) != ('127.0.0.1', '55439', 'resume_v2_test_admin'):
        raise RuntimeError('PostgreSQL verification must use resume_v2_postgres_test_settings')


def _user(row: Users) -> dict:
    return {'id': row.pk, 'role': row.role, 'cohort_id': row.cohort_id, 'cohort_code': row.cohort.code,
            'firebase_uid': row.firebase_uid, 'is_active': True}


@skipUnless(connection.vendor == 'postgresql', 'requires real PostgreSQL')
class PostFeedTests(TransactionTestCase):
    def setUp(self):
        self.c34 = Cohorts.objects.create(code='34', name='34기', status='active', is_active=True)
        self.c35 = Cohorts.objects.create(code='35', name='35기', status='active', is_active=True)
        def make(uid, role, cohort):
            return _user(Users.objects.create(firebase_uid=uid, password='x', display_name=uid, role=role,
                                              cohort=cohort, is_active=True, must_change_password=False))
        self.a, self.b = make('a', 'student', self.c34), make('b', 'student', self.c34)
        self.other = make('other', 'student', self.c35)
        self.teacher = make('t', 'instructor', self.c34)

    def call(self, fn, *args):
        with transaction.atomic(), connection.cursor() as cur:
            return fn(cur, *args)

    def test_post_shows_only_in_its_cohort_with_author_and_counts(self):
        post = self.call(create_post, self.a, {'content': '  오늘 스터디 같이 하실 분  '})
        self.assertEqual((post['content'], post['authorId'], post['authorName']), ('오늘 스터디 같이 하실 분', 'a', 'a'))
        self.assertEqual((post['likeCount'], post['commentCount'], post['canDelete']), (0, 0, True))
        self.assertEqual([p['id'] for p in self.call(list_posts, self.b)['posts']], [post['id']])
        self.assertFalse(self.call(list_posts, self.b)['posts'][0]['canDelete'])
        self.assertEqual(self.call(list_posts, self.other)['posts'], [])
        with self.assertRaises(PostError) as hidden:
            self.call(toggle_like, self.other, int(post['id']))
        self.assertEqual(hidden.exception.status, 404)

    def test_like_toggles_once_per_person(self):
        post = int(self.call(create_post, self.a, {'content': '좋아요'})['id'])
        self.assertEqual(self.call(toggle_like, self.b, post)['likeCount'], 1)
        liked = self.call(toggle_like, self.a, post)
        self.assertEqual((liked['likeCount'], liked['likedByMe']), (2, True))
        undone = self.call(toggle_like, self.b, post)
        self.assertEqual((undone['likeCount'], undone['likedByMe']), (1, False))

    def test_comments_and_delete_permissions(self):
        post = int(self.call(create_post, self.a, {'content': '질문'})['id'])
        mine = self.call(create_comment, self.b, post, {'content': '저도요'})
        self.assertEqual(self.call(list_posts, self.a)['posts'][0]['commentCount'], 1)
        self.assertEqual([c['content'] for c in self.call(list_comments, self.a, post)['comments']], ['저도요'])
        with self.assertRaises(PermissionError):
            self.call(delete_comment, self.a, post, int(mine['id']))
        self.call(delete_comment, self.teacher, post, int(mine['id']))  # Moderation.
        with self.assertRaises(PermissionError):
            self.call(delete_post, self.b, post)
        self.call(toggle_like, self.b, post)
        self.call(create_comment, self.b, post, {'content': '하나 더'})
        self.call(delete_post, self.a, post)
        self.assertEqual((Posts.objects.count(), PostComments.objects.count(), PostLikes.objects.count()), (0, 0, 0))

    def test_empty_or_too_long_content_is_rejected(self):
        with self.assertRaises(PostError):
            self.call(create_post, self.a, {'content': '   '})
        with self.assertRaises(PostError):
            self.call(create_post, self.a, {'content': '가' * (MAX_POST_CHARS + 1)})
        with self.assertRaises(PermissionError):  # An instructor cannot post into another cohort.
            self.call(create_post, self.teacher, {'content': '공지', 'cohort': '35'})
