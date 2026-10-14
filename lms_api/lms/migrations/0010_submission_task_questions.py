from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lms', '0009_alert_popup_end_date_reads'),
    ]

    operations = [
        migrations.AddField(
            model_name='submissiontasks',
            name='questions',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
