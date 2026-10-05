"""Copy a specified existing target from read-only RDS into the local B database.

Never crawl, recommend, analyze or modify the source database.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from job_matching_bot.env import ensure_loaded
from chatbot.database import connect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--base-resume-id', required=True, type=int)
    parser.add_argument('--local-email', required=True)
    args = parser.parse_args()
    ensure_loaded()
    with connect(row_factory=dict_row, connect_timeout=8) as remote:
        remote.execute('SET TRANSACTION READ ONLY')
        identity = remote.execute('SELECT current_database(),current_user').fetchone()
        if list(identity.values()) != ['lms_migration_replay_20260923', 'project_admin']:
            raise RuntimeError('Unexpected source database identity')
        job = remote.execute('SELECT * FROM jobs.jobs WHERE job_id=%s', (args.job_id,)).fetchone()
        resume = remote.execute('SELECT * FROM resumes WHERE id=%s AND base_resume_id IS NULL', (args.base_resume_id,)).fetchone()
        profiles = remote.execute('SELECT key,requirements,created_at FROM job_requirement_profiles WHERE key LIKE %s', (args.job_id + '__%',)).fetchall()
        if not job or not job.get('description') or not resume:
            raise RuntimeError('Existing source job body/base resume missing; no synthetic fallback')
        remote.rollback()
    with psycopg.connect(host='127.0.0.1', port=55439, dbname='resume_review_v2_test', user='resume_v2_test_admin', row_factory=dict_row) as local:
        ident = local.execute('SELECT current_database(),inet_server_port()').fetchone()
        if list(ident.values()) != ['resume_review_v2_test', 55439]:
            raise RuntimeError('Unexpected destination database')
        user = local.execute('SELECT id,cohort_id FROM users WHERE email=%s', (args.local_email,)).fetchone()
        if not user: raise RuntimeError('Local account missing')
        columns = local.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='jobs' AND table_name='jobs' ORDER BY ordinal_position").fetchall()
        selected = [r for r in columns if r['column_name'] in job]
        names = [r['column_name'] for r in selected]
        values = [Jsonb(job[r['column_name']]) if r['data_type']=='jsonb' and job[r['column_name']] is not None else job[r['column_name']] for r in selected]
        existing = local.execute('SELECT * FROM jobs.jobs WHERE job_id=%s', (args.job_id,)).fetchone()
        if existing and any(existing.get(n) != job[n] for n in names):
            raise RuntimeError('Local job differs; refuse to overwrite')
        if not existing:
            local.execute(sql.SQL('INSERT INTO jobs.jobs ({}) VALUES ({})').format(
                sql.SQL(',').join(map(sql.Identifier,names)), sql.SQL(',').join(sql.Placeholder() for _ in names)), values)
        for profile in profiles:
            local.execute('INSERT INTO job_requirement_profiles (key,requirements,created_at) VALUES (%s,%s,%s) ON CONFLICT (key) DO NOTHING',
                (profile['key'], Jsonb(profile['requirements']), profile['created_at']))
        legacy = f'local-ab-source-resume-{args.base_resume_id}'
        old = local.execute('SELECT id,content FROM resumes WHERE legacy_id=%s', (legacy,)).fetchone()
        if old and old['content'] != resume['content']:
            raise RuntimeError('Local Resume has edits; refuse to overwrite')
        if not old:
            old = local.execute("INSERT INTO resumes (legacy_id,user_id,cohort_id,title,content,status,is_base_resume,revision_count,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,'draft',false,0,now(),now()) RETURNING id",
                (legacy,user['id'],user['cohort_id'],resume['title'],Jsonb(resume['content']))).fetchone()
        # Freeze the chosen A/B target. Existing React reads linked jobs without
        # running recommendation/reranking; applicant content stays byte-equivalent.
        linked = local.execute('SELECT linked_job_id FROM resumes WHERE id=%s', (old['id'],)).fetchone()['linked_job_id']
        if linked not in (None, '', args.job_id):
            raise RuntimeError('Local Resume already linked to another target')
        local.execute('UPDATE resumes SET linked_job_id=%s WHERE id=%s', (args.job_id,old['id']))
        print('Copied job:', args.job_id, '| body chars:', len(job['description']))
        print('Local original Resume id:', old['id'], '| source Resume id:', args.base_resume_id)
        print('Existing profiles copied:', len(profiles), '| RDS writes: 0 | LLM calls: 0')


if __name__ == '__main__': main()
