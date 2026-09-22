from django.core.management.base import BaseCommand
from django.db import connection

from lms import notice_vectors
from lms.services import sync_notice_vector


def run_reindex() -> dict:
    notice_vectors.clear_notice_namespace()
    upserted = 0
    with connection.cursor() as cur:
        cur.execute(
            """SELECT n.id, n.title, n.content, n.author_id, n.author_name, n.is_favorite,
                      n.priority, n.created_at, n.updated_at, c.code
               FROM notices n JOIN cohorts c ON c.id = n.cohort_id"""
        )
        rows = cur.fetchall()
        for row in rows:
            (nid, title, content, author_id, author_name, fav, priority, created, updated, code) = row
            count = sync_notice_vector(
                code,
                nid,
                {
                    "title": title,
                    "content": content,
                    "author_id": author_id,
                    "author_name": author_name,
                    "is_favorite": fav,
                    "priority": priority,
                    "created_at": created,
                    "updated_at": updated,
                },
                previous_chunk_count=0,
            )
            cur.execute("UPDATE notices SET vector_chunk_count = %s WHERE id = %s", [count, nid])
            upserted += count
        smoke = {}
        cur.execute("SELECT c.code FROM cohorts c JOIN notices n ON n.cohort_id = c.id GROUP BY c.code LIMIT 1")
        code_row = cur.fetchone()
        if code_row:
            smoke = {"cohort": code_row[0], "hits": notice_vectors.smoke_search(code_row[0])}
    return {"upserted": upserted, "notices": len(rows), "smoke": smoke}


class Command(BaseCommand):
    help = "Pinecone notice 네임스페이스를 비우고 notices 전체를 재적재한다."

    def handle(self, *args, **options):
        result = run_reindex()
        self.stdout.write(str(result))
