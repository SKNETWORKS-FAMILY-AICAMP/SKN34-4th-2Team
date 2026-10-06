import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lms', '0101_quests'),
    ]

    operations = [
        migrations.CreateModel(
            name='PushTokens',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(unique=True)),
                ('platform', models.CharField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='push_tokens', to='lms.users')),
            ],
            options={
                'db_table': 'push_tokens',
                'indexes': [models.Index(fields=['user'], name='idx_push_token_user')],
            },
        ),
    ]
