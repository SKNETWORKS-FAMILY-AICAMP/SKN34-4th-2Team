from django.db import migrations, models


# The application has many cohort-writing routes besides /command. A database
# guard closes the gap between the deletion manifest and external cleanup for
# every single-column FK to cohorts present at this migration's graph leaf.
GUARD_SQL = r"""
CREATE FUNCTION lms_block_deleting_cohort_write() RETURNS trigger AS $guard$
DECLARE target_id bigint;
BEGIN
    target_id := NULLIF(to_jsonb(NEW)->>TG_ARGV[0], '')::bigint;
    IF target_id IS NULL THEN
        RETURN NEW;
    END IF;
    -- Serialise with _prepare_job's SELECT FOR UPDATE before checking the job.
    PERFORM 1 FROM cohorts WHERE id = target_id FOR KEY SHARE;
    IF EXISTS (SELECT 1 FROM cohort_deletion_jobs
               WHERE cohort_id = target_id AND state <> 'complete') THEN
        RAISE EXCEPTION 'cohort deletion in progress' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$guard$ LANGUAGE plpgsql;

DO $install$
DECLARE target record;
BEGIN
    FOR target IN
        SELECT ns.nspname AS schema_name, rel.relname AS table_name,
               att.attname AS column_name
        FROM pg_constraint fk
        JOIN pg_class rel ON rel.oid = fk.conrelid
        JOIN pg_namespace ns ON ns.oid = rel.relnamespace
        JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = fk.conkey[1]
        WHERE fk.contype = 'f' AND fk.confrelid = 'cohorts'::regclass
          AND array_length(fk.conkey, 1) = 1
    LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE ON %I.%I '
                       || 'FOR EACH ROW EXECUTE FUNCTION lms_block_deleting_cohort_write(%L)',
                       'lms_cohort_deletion_guard_' || target.column_name,
                       target.schema_name, target.table_name, target.column_name);
    END LOOP;
END;
$install$;
"""

UNDO_GUARD_SQL = r"""
DO $uninstall$
DECLARE target record;
BEGIN
    FOR target IN
        SELECT ns.nspname AS schema_name, rel.relname AS table_name,
               att.attname AS column_name
        FROM pg_constraint fk
        JOIN pg_class rel ON rel.oid = fk.conrelid
        JOIN pg_namespace ns ON ns.oid = rel.relnamespace
        JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = fk.conkey[1]
        WHERE fk.contype = 'f' AND fk.confrelid = 'cohorts'::regclass
          AND array_length(fk.conkey, 1) = 1
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I.%I',
                       'lms_cohort_deletion_guard_' || target.column_name,
                       target.schema_name, target.table_name);
    END LOOP;
END;
$uninstall$;
DROP FUNCTION lms_block_deleting_cohort_write();
"""


class Migration(migrations.Migration):
    dependencies = [('lms', '0016_merge_resume_and_push_tokens')]

    operations = [
        migrations.CreateModel(
            name='CohortDeletionJobs',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('cohort_id', models.BigIntegerField(unique=True)),
                ('cohort_code', models.CharField()),
                ('cohort_name', models.CharField()),
                ('state', models.CharField(default='preparing')),
                ('targets', models.JSONField(blank=True, default=None, null=True)),
                ('deleted_vectors', models.JSONField(default=list)),
                ('deleted_objects', models.JSONField(default=list)),
                ('error', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'cohort_deletion_jobs'},
        ),
        migrations.RunSQL(GUARD_SQL, UNDO_GUARD_SQL),
    ]
