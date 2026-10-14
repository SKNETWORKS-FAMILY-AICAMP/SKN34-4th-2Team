import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lms', '0100_student_counsel_notes'),
    ]

    operations = [
        migrations.CreateModel(
            name='Quests',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField()),
                ('description', models.TextField(blank=True, default='')),
                ('reward', models.IntegerField()),
                ('evidence_type', models.CharField(default='none')),
                ('approval', models.CharField(default='manual')),
                ('max_completions', models.PositiveSmallIntegerField(default=1)),
                ('start_on', models.DateField(blank=True, null=True)),
                ('end_on', models.DateField(blank=True, null=True)),
                ('published', models.BooleanField(default=False)),
                ('closed', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('cohort', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='lms.cohorts')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='quests_created', to='lms.users')),
            ],
            options={
                'db_table': 'quests',
                'indexes': [models.Index(fields=['cohort', 'published'], name='quests_cohort_published_idx')],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(('reward__gt', 0)), name='ck_quest_reward_positive'),
                    models.CheckConstraint(condition=models.Q(('evidence_type__in', ('none', 'text', 'link', 'file'))), name='ck_quest_evidence_type'),
                    models.CheckConstraint(condition=models.Q(('approval__in', ('manual', 'auto'))), name='ck_quest_approval'),
                ],
            },
        ),
        migrations.CreateModel(
            name='QuestSubmissions',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(default='pending')),
                ('text', models.TextField(blank=True, default='')),
                ('link', models.CharField(blank=True, default='')),
                ('file_keys', models.JSONField(blank=True, default=list)),
                ('review_comment', models.TextField(blank=True, default='')),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('granted_amount', models.IntegerField(default=0)),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('cohort', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='lms.cohorts')),
                ('quest', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='submissions', to='lms.quests')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='quest_reviews', to='lms.users')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='quest_submissions', to='lms.users')),
            ],
            options={
                'db_table': 'quest_submissions',
                'indexes': [
                    models.Index(fields=['quest', 'user'], name='quest_sub_quest_user_idx'),
                    models.Index(fields=['cohort', 'status'], name='quest_sub_cohort_status_idx'),
                ],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(('status__in', ('pending', 'approved', 'rejected', 'revoked'))), name='ck_quest_submission_status'),
                ],
            },
        ),
    ]
