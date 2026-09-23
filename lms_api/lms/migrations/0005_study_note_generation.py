from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('lms', '0004_policy_documents')]

    operations = [
        migrations.AddField(
            model_name='studynotes',
            name='updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='studynotes',
            name='generation_token',
            field=models.CharField(blank=True, null=True),
        ),
    ]
