import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lms', '0010_submission_task_questions'),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentCounselNotes',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('round', models.PositiveSmallIntegerField()),
                ('counseled_on', models.DateField()),
                ('category', models.CharField(default='regular')),
                ('content', models.TextField()),
                ('follow_up', models.TextField(blank=True, default='')),
                ('follow_up_done', models.BooleanField(default=False)),
                ('next_on', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('cohort', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='lms.cohorts')),
                ('counselor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='counsel_notes_written', to='lms.users')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='counsel_notes', to='lms.users')),
            ],
            options={
                'db_table': 'student_counsel_notes',
                'indexes': [
                    models.Index(fields=['cohort', 'round'], name='student_cou_cohort__a1c0e2_idx'),
                    models.Index(fields=['user', 'counseled_on'], name='student_cou_user_id_5b7d31_idx'),
                ],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(('category__in', ('regular', 'adhoc', 'career', 'other'))), name='ck_counsel_note_category'),
                ],
            },
        ),
    ]
