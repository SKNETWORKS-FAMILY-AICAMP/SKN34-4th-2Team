"""Copy existing v2 Bindings with a Resume copy in the same psycopg transaction.

Deployments before migration 0011 have no v2 bindings to copy. No Django setup is
required in the AI process; all applicant ownership checks remain explicit.
"""

import uuid

from psycopg.types.json import Jsonb


SECTIONS = ('projects', 'experience', 'education', 'trainingExperience', 'otherActivities')


def clone_existing_bindings(conn, *, user_id, source_resume_id, target_resume_id):
    if conn.execute("SELECT to_regclass('public.resume_experience_bindings')").fetchone()[0] is None:
        return 0
    rows = conn.execute(
        """SELECT id, user_id, base_resume_id, source_tailored_resume_id, content
           FROM resumes WHERE id = ANY(%s) ORDER BY id FOR UPDATE""",
        ([source_resume_id, target_resume_id],),
    ).fetchall()
    by_id = {row[0]: row for row in rows}
    if len(by_id) != 2 or any(row[1] != user_id for row in rows):
        raise ValueError('owned source and target resumes required for binding copy')
    target = by_id[target_resume_id]
    if source_resume_id not in (target[2], target[3]):
        raise ValueError('resume copy relationship not established')
    locations = {}
    for section in SECTIONS:
        for index, item in enumerate((target[4] or {}).get(section, [])):
            if not isinstance(item, dict):
                continue
            native_id = item.get('id')
            key = f'{section}:{native_id}' if isinstance(native_id, str) and native_id else item.get('_experience_item_key')
            if not key:
                continue
            if key in locations:
                raise ValueError('duplicate stable item key in copied resume')
            locations[key] = (f'{section}[{index}].description', index)
    bindings = conn.execute(
        """SELECT b.item_key, b.experience_id, e.user_id FROM resume_experience_bindings b
           JOIN resume_experiences e ON e.id = b.experience_id WHERE b.resume_id = %s""",
        (source_resume_id,),
    ).fetchall()
    payload = []
    for key, experience_id, owner_id in bindings:
        if owner_id != user_id:
            raise ValueError('binding experience owner mismatch')
        if key in locations:
            path, order = locations[key]
            payload.append(dict(id=str(uuid.uuid4()), resume_id=target_resume_id,
                                experience_id=str(experience_id), item_key=key,
                                field_path=path, display_order=order))
    if not payload:
        return 0
    inserted = conn.execute(
        """INSERT INTO resume_experience_bindings
           (id, resume_id, experience_id, item_key, field_path, display_order, created_at, updated_at)
           SELECT x.id, x.resume_id, x.experience_id, x.item_key, x.field_path, x.display_order, now(), now()
           FROM jsonb_to_recordset(%s::jsonb) AS x(
             id uuid, resume_id bigint, experience_id uuid, item_key text, field_path text, display_order integer)
           ON CONFLICT (resume_id, item_key) DO UPDATE
             SET field_path=EXCLUDED.field_path, display_order=EXCLUDED.display_order, updated_at=now()
             WHERE resume_experience_bindings.experience_id = EXCLUDED.experience_id
           RETURNING id""", (Jsonb(payload),),
    ).fetchall()
    if len(inserted) != len(payload):
        raise ValueError('copy item already belongs to a different Experience')
    return len(inserted)
