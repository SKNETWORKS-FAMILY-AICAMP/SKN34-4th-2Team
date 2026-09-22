# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class AiEvalRuns(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    prompt_version = models.CharField(blank=True, null=True)
    model = models.CharField(blank=True, null=True)
    source = models.CharField(blank=True, null=True)
    total_cases = models.IntegerField(blank=True, null=True)
    passed = models.IntegerField(blank=True, null=True)
    accuracy = models.DecimalField(blank=True, null=True)
    avg_latency_ms = models.IntegerField(blank=True, null=True)
    failed_ids = models.TextField()  # This field type is a guess.
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ai_eval_runs'


class AiGenerationLogs(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    type = models.CharField(blank=True, null=True)
    cohort = models.ForeignKey('Cohorts', models.PROTECT, blank=True, null=True)
    created_by = models.ForeignKey('Users', models.SET_NULL, db_column='created_by', blank=True, null=True)
    prompt_version = models.CharField(blank=True, null=True)
    model = models.CharField(blank=True, null=True)
    status = models.CharField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    latency_ms = models.IntegerField(blank=True, null=True)
    token_in = models.IntegerField(blank=True, null=True)
    token_out = models.IntegerField(blank=True, null=True)
    details = models.JSONField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ai_generation_logs'


class AiQuestionFeedback(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    log = models.ForeignKey(AiGenerationLogs, models.SET_NULL, blank=True, null=True)
    draft_id = models.CharField(blank=True, null=True)
    cohort = models.ForeignKey('Cohorts', models.PROTECT, blank=True, null=True)
    outcome = models.CharField(blank=True, null=True)
    type = models.CharField(blank=True, null=True)
    prompt_version = models.CharField(blank=True, null=True)
    assessment = models.ForeignKey('Assessments', models.SET_NULL, blank=True, null=True)
    question = models.ForeignKey('AssessmentQuestions', models.SET_NULL, blank=True, null=True)
    source_day = models.IntegerField(blank=True, null=True)
    source_topic = models.CharField(blank=True, null=True)
    actor = models.ForeignKey('Users', models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ai_question_feedback'


class AlertPopupDismissals(models.Model):
    pk = models.CompositePrimaryKey('user_id', 'popup_id')
    user = models.ForeignKey('Users', models.PROTECT)
    popup = models.ForeignKey('AlertPopups', models.CASCADE)
    date_key = models.DateField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'alert_popup_dismissals'


class AlertPopups(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey('Cohorts', models.PROTECT)
    title = models.CharField(blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    author = models.ForeignKey('Users', models.SET_NULL, blank=True, null=True)
    is_active = models.BooleanField()
    sort_order = models.IntegerField(blank=True, null=True)
    link_url = models.CharField(blank=True, null=True)
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'alert_popups'


class AssessmentAnswers(models.Model):
    pk = models.CompositePrimaryKey('submission_id', 'question_id')
    submission = models.ForeignKey('AssessmentSubmissions', models.CASCADE)
    question = models.ForeignKey('AssessmentQuestions', models.CASCADE)
    value = models.JSONField(blank=True, null=True)
    auto_score = models.IntegerField(blank=True, null=True)
    final_score = models.IntegerField(blank=True, null=True)
    is_correct = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'assessment_answers'


class AssessmentQuestions(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    assessment = models.ForeignKey('Assessments', models.CASCADE)
    order = models.IntegerField(blank=True, null=True)
    type = models.CharField(blank=True, null=True)
    prompt = models.TextField(blank=True, null=True)
    points = models.IntegerField(blank=True, null=True)
    choices = models.TextField()  # This field type is a guess.
    correct_index = models.IntegerField(blank=True, null=True)
    accepted_answers = models.TextField()  # This field type is a guess.
    explanation = models.TextField(blank=True, null=True)
    origin = models.CharField(blank=True, null=True)
    ai_log = models.ForeignKey(AiGenerationLogs, models.SET_NULL, blank=True, null=True)
    ai_draft_id = models.CharField(blank=True, null=True)
    prompt_version = models.CharField(blank=True, null=True)
    source_day = models.IntegerField(blank=True, null=True)
    source_topic = models.CharField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'assessment_questions'


class AssessmentScoreAdjustments(models.Model):
    id = models.BigAutoField(primary_key=True)
    submission = models.ForeignKey('AssessmentSubmissions', models.CASCADE)
    question = models.ForeignKey(AssessmentQuestions, models.SET_NULL, blank=True, null=True)
    previous = models.IntegerField(blank=True, null=True)
    next = models.IntegerField(blank=True, null=True)
    adjusted_by = models.ForeignKey('Users', models.SET_NULL, db_column='adjusted_by', blank=True, null=True)
    adjusted_at = models.DateTimeField(blank=True, null=True)
    note = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'assessment_score_adjustments'


class AssessmentSubmissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    assessment = models.ForeignKey('Assessments', models.CASCADE)
    user = models.ForeignKey('Users', models.PROTECT)
    auto_total_score = models.IntegerField(blank=True, null=True)
    total_score = models.IntegerField(blank=True, null=True)
    status = models.CharField(blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'assessment_submissions'
        unique_together = (('assessment', 'user'),)


class Assessments(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey('Cohorts', models.PROTECT)
    title = models.CharField(blank=True, null=True)
    tags = models.TextField()  # This field type is a guess.
    max_score = models.IntegerField(blank=True, null=True)
    start_at = models.DateTimeField(blank=True, null=True)
    end_at = models.DateTimeField(blank=True, null=True)
    thumbnail_url = models.CharField(blank=True, null=True)
    thumbnail_path = models.CharField(blank=True, null=True)
    published = models.BooleanField()
    created_by = models.ForeignKey('Users', models.SET_NULL, db_column='created_by', blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    curriculum_sheet = models.ForeignKey('CurriculumSheets', models.SET_NULL, blank=True, null=True)
    day_from = models.IntegerField(blank=True, null=True)
    day_to = models.IntegerField(blank=True, null=True)
    subject_filter = models.CharField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'assessments'


class AssignmentSubmissions(models.Model):
    pk = models.CompositePrimaryKey('assignment_id', 'user_id')
    assignment = models.ForeignKey('Assignments', models.CASCADE)
    user = models.ForeignKey('Users', models.PROTECT)
    file_url = models.CharField(blank=True, null=True)
    file_name = models.CharField(blank=True, null=True)
    file_size_bytes = models.BigIntegerField(blank=True, null=True)
    status = models.CharField(blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'assignment_submissions'


class Assignments(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey('Cohorts', models.PROTECT)
    title = models.CharField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    due_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'assignments'


class Attendances(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey('Cohorts', models.PROTECT)
    user = models.ForeignKey('Users', models.PROTECT)
    date_key = models.DateField()
    status = models.CharField(blank=True, null=True)
    status_source = models.CharField(blank=True, null=True)
    check_in_time = models.TimeField(blank=True, null=True)
    check_out_time = models.TimeField(blank=True, null=True)
    form_attendance_type = models.CharField(blank=True, null=True)
    official_leave_used = models.BooleanField(blank=True, null=True)
    official_leave_type = models.CharField(blank=True, null=True)
    official_leave_other = models.CharField(blank=True, null=True)
    recorded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'attendances'
        unique_together = (('user', 'date_key'),)


class Cohorts(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True)
    name = models.CharField()
    description = models.TextField(blank=True, null=True)
    term_number = models.IntegerField(blank=True, null=True)
    classroom_name = models.CharField(blank=True, null=True)
    status = models.CharField()
    is_active = models.BooleanField()
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    published_seating_room = models.ForeignKey('SeatingRooms', models.PROTECT, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'cohorts'


class CurriculumPdfs(models.Model):
    cohort = models.OneToOneField(Cohorts, models.PROTECT, primary_key=True)
    full_pdf_url = models.CharField(blank=True, null=True)
    full_pdf_file_name = models.CharField(blank=True, null=True)
    published = models.BooleanField()
    updated_by = models.ForeignKey('Users', models.SET_NULL, db_column='updated_by', blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'curriculum_pdfs'


class CurriculumRows(models.Model):
    id = models.BigAutoField(primary_key=True)
    sheet = models.ForeignKey('CurriculumSheets', models.CASCADE)
    day_index = models.IntegerField(blank=True, null=True)
    date_label = models.CharField(blank=True, null=True)
    subject = models.CharField(blank=True, null=True)
    topic = models.CharField(blank=True, null=True)
    detail = models.TextField(blank=True, null=True)
    order = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'curriculum_rows'


class CurriculumSheets(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    title = models.CharField(blank=True, null=True)
    file_name = models.CharField(blank=True, null=True)
    storage_path = models.CharField(blank=True, null=True)
    source = models.CharField(blank=True, null=True)
    uploaded_by = models.ForeignKey('Users', models.SET_NULL, db_column='uploaded_by', blank=True, null=True)
    uploaded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'curriculum_sheets'


class FormResponses(models.Model):
    pk = models.CompositePrimaryKey('task_id', 'user_id')
    task = models.ForeignKey('FormTasks', models.CASCADE)
    user = models.ForeignKey('Users', models.PROTECT)
    source = models.CharField(blank=True, null=True)
    google_response_id = models.CharField(unique=True, blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'form_responses'


class FormTasks(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    title = models.CharField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    form_url = models.CharField(blank=True, null=True)
    notion_guide_url = models.CharField(blank=True, null=True)
    due_at = models.DateTimeField(blank=True, null=True)
    published = models.BooleanField()
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'form_tasks'


class InflearnPackages(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    title = models.CharField(blank=True, null=True)
    subject = models.CharField(blank=True, null=True)
    type = models.CharField(blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    units = models.JSONField()
    courses = models.JSONField()
    is_published = models.BooleanField()
    sort_order = models.IntegerField(blank=True, null=True)
    published_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'inflearn_packages'


class JobRequirementProfiles(models.Model):
    key = models.CharField(primary_key=True)
    requirements = models.JSONField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'job_requirement_profiles'


class Materials(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    title = models.CharField(blank=True, null=True)
    file_url = models.CharField(blank=True, null=True)
    file_name = models.CharField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'materials'


class MileageCartItems(models.Model):
    pk = models.CompositePrimaryKey('user_id', 'product_id')
    user = models.ForeignKey('Users', models.PROTECT)
    product = models.ForeignKey('MileageProducts', models.CASCADE)
    quantity = models.IntegerField()
    unit_price = models.IntegerField(blank=True, null=True)
    purchase_link = models.CharField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'mileage_cart_items'


class MileageProducts(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    name = models.CharField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    image_url = models.CharField(blank=True, null=True)
    category = models.CharField(blank=True, null=True)
    pricing_type = models.CharField(blank=True, null=True)
    fixed_price = models.IntegerField(blank=True, null=True)
    is_active = models.BooleanField()
    sort_order = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'mileage_products'


class MileageSettings(models.Model):
    cohort = models.OneToOneField(Cohorts, models.PROTECT, primary_key=True)
    category_limits = models.JSONField()
    accrual_rules = models.JSONField()
    updated_by = models.ForeignKey('Users', models.SET_NULL, db_column='updated_by', blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'mileage_settings'


class MileageTransactions(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    user = models.ForeignKey('Users', models.PROTECT)
    amount = models.IntegerField()
    reason = models.CharField(blank=True, null=True)
    type = models.CharField(blank=True, null=True)
    related_id = models.CharField(blank=True, null=True)
    adjusted_by = models.ForeignKey('Users', models.SET_NULL, db_column='adjusted_by', related_name='mileagetransactions_adjusted_by_set', blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'mileage_transactions'


class MissionProgress(models.Model):
    pk = models.CompositePrimaryKey('cohort_id', 'user_id')
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    user = models.ForeignKey('Users', models.PROTECT)
    study_cert_count = models.IntegerField()
    study_cert_granted = models.IntegerField()
    quiz_pass_count = models.IntegerField()
    quiz_granted = models.IntegerField()
    coding_pcce = models.BooleanField()
    coding_pccp = models.BooleanField()
    coding_pcsql = models.BooleanField()
    coding_granted = models.IntegerField()
    blog_weeks = models.TextField()  # This field type is a guess.
    blog_units_granted = models.TextField()  # This field type is a guess.
    study_week_keys = models.TextField()  # This field type is a guess.
    study_granted = models.BooleanField()
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'mission_progress'


class Notices(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    title = models.CharField(blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    author = models.ForeignKey('Users', models.SET_NULL, blank=True, null=True)
    author_name = models.CharField(blank=True, null=True)
    is_favorite = models.BooleanField()
    priority = models.IntegerField()
    source = models.CharField(blank=True, null=True)
    channel_label = models.CharField(blank=True, null=True)
    discord_message_id = models.CharField(unique=True, blank=True, null=True)
    discord_channel_id = models.CharField(blank=True, null=True)
    discord_channel_type = models.CharField(blank=True, null=True)
    scheduled_notice = models.ForeignKey('ScheduledNotices', models.SET_NULL, blank=True, null=True)
    image_url = models.CharField(blank=True, null=True)
    vector_chunk_count = models.IntegerField()
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'notices'


class ProjectTeamMembers(models.Model):
    pk = models.CompositePrimaryKey('team_id', 'user_id')
    team = models.ForeignKey('ProjectTeams', models.CASCADE)
    user = models.ForeignKey('Users', models.PROTECT)

    class Meta:
        managed = False
        db_table = 'project_team_members'


class ProjectTeams(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    name = models.CharField(blank=True, null=True)
    sort_order = models.IntegerField(blank=True, null=True)
    color_index = models.IntegerField(blank=True, null=True)
    updated_by = models.ForeignKey('Users', models.SET_NULL, db_column='updated_by', blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'project_teams'


class PurchaseRequestItems(models.Model):
    id = models.BigAutoField(primary_key=True)
    request = models.ForeignKey('PurchaseRequests', models.CASCADE)
    product = models.ForeignKey(MileageProducts, models.SET_NULL, blank=True, null=True)
    product_name = models.CharField(blank=True, null=True)
    category = models.CharField(blank=True, null=True)
    pricing_type = models.CharField(blank=True, null=True)
    unit_price = models.IntegerField(blank=True, null=True)
    quantity = models.IntegerField(blank=True, null=True)
    purchase_link = models.CharField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'purchase_request_items'


class PurchaseRequests(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    user = models.ForeignKey('Users', models.PROTECT)
    total_amount = models.IntegerField(blank=True, null=True)
    status = models.CharField(blank=True, null=True)
    student_note = models.TextField(blank=True, null=True)
    manager_memo = models.TextField(blank=True, null=True)
    manager_purchase_link = models.CharField(blank=True, null=True)
    processed_by = models.ForeignKey('Users', models.SET_NULL, db_column='processed_by', related_name='purchaserequests_processed_by_set', blank=True, null=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'purchase_requests'


class RecommendationEvents(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    user = models.ForeignKey('Users', models.SET_NULL, blank=True, null=True)
    recommendation = models.ForeignKey('YoutubeRecommendations', models.SET_NULL, blank=True, null=True)
    youtube_video_id = models.CharField(blank=True, null=True)
    user_skills = models.TextField()  # This field type is a guess.
    matched_tags = models.TextField()  # This field type is a guess.
    action = models.CharField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'recommendation_events'


class RecordSubmissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    user = models.ForeignKey('Users', models.PROTECT)
    type = models.CharField()
    status = models.CharField()
    title = models.CharField(blank=True, null=True)
    review_comment = models.TextField(blank=True, null=True)
    reviewed_by = models.ForeignKey('Users', models.SET_NULL, db_column='reviewed_by', related_name='recordsubmissions_reviewed_by_set', blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    cert_type = models.CharField(blank=True, null=True)
    file_urls = models.TextField()  # This field type is a guess.
    start_at = models.DateTimeField(blank=True, null=True)
    end_at = models.DateTimeField(blank=True, null=True)
    week_number = models.IntegerField(blank=True, null=True)
    week_label = models.CharField(blank=True, null=True)
    link = models.CharField(blank=True, null=True)
    quiz_score = models.IntegerField(blank=True, null=True)
    learning_date = models.DateField(blank=True, null=True)
    learning_content = models.TextField(blank=True, null=True)
    is_team_study = models.BooleanField(blank=True, null=True)
    mileage_granted = models.BooleanField()
    mileage_amount = models.IntegerField()
    submitted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'record_submissions'


class ResumeAiApplications(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    resume = models.ForeignKey('Resumes', models.CASCADE)
    user = models.ForeignKey('Users', models.SET_NULL, blank=True, null=True)
    fingerprint = models.CharField(blank=True, null=True)
    kind = models.CharField(blank=True, null=True)
    before = models.JSONField(blank=True, null=True)
    after_hash = models.CharField(blank=True, null=True)
    response = models.JSONField(blank=True, null=True)
    source_id = models.CharField(blank=True, null=True)
    undone_by = models.CharField(blank=True, null=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'resume_ai_applications'


class ResumeAiReviews(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    resume = models.ForeignKey('Resumes', models.CASCADE)
    user = models.ForeignKey('Users', models.SET_NULL, blank=True, null=True)
    fingerprint = models.CharField(blank=True, null=True)
    status = models.CharField(blank=True, null=True)
    response = models.JSONField(blank=True, null=True)
    telemetry = models.JSONField(blank=True, null=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'resume_ai_reviews'


class ResumeFeedback(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    resume = models.ForeignKey('Resumes', models.CASCADE)
    parent = models.ForeignKey('self', models.SET_NULL, blank=True, null=True)
    section_key = models.CharField(blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    author = models.ForeignKey('Users', models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'resume_feedback'


class ResumeFeedbackReads(models.Model):
    pk = models.CompositePrimaryKey('feedback_id', 'user_id')
    feedback = models.ForeignKey(ResumeFeedback, models.CASCADE)
    user = models.ForeignKey('Users', models.PROTECT)
    read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'resume_feedback_reads'


class ResumeRevisions(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    resume = models.ForeignKey('Resumes', models.CASCADE)
    title = models.CharField(blank=True, null=True)
    content = models.JSONField()
    saved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'resume_revisions'


class Resumes(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    user = models.ForeignKey('Users', models.PROTECT)
    title = models.CharField(blank=True, null=True)
    status = models.CharField(blank=True, null=True)
    content = models.JSONField()
    sections = models.JSONField()
    is_base_resume = models.BooleanField()
    base_resume = models.ForeignKey('self', models.SET_NULL, blank=True, null=True)
    source_tailored_resume = models.ForeignKey('self', models.SET_NULL, related_name='resumes_source_tailored_resume_set', blank=True, null=True)
    linked_job_id = models.CharField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'resumes'


class RollCallEntries(models.Model):
    pk = models.CompositePrimaryKey('roll_call_id', 'user_id')
    roll_call = models.ForeignKey('RollCalls', models.CASCADE)
    user = models.ForeignKey('Users', models.PROTECT)
    state = models.CharField()

    class Meta:
        managed = False
        db_table = 'roll_call_entries'


class RollCalls(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    date_key = models.DateField()
    period_id = models.CharField()
    carried_from_period_id = models.CharField(blank=True, null=True)
    updated_by = models.ForeignKey('Users', models.SET_NULL, db_column='updated_by', blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'roll_calls'
        unique_together = (('cohort', 'date_key', 'period_id'),)


class ScheduledNotices(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    title = models.CharField(blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    author = models.ForeignKey('Users', models.SET_NULL, blank=True, null=True)
    is_favorite = models.BooleanField()
    repeat_type = models.CharField(blank=True, null=True)
    publish_time = models.TimeField(blank=True, null=True)
    publish_at = models.DateTimeField(blank=True, null=True)
    weekday = models.IntegerField(blank=True, null=True)
    is_active = models.BooleanField()
    last_published_at = models.DateTimeField(blank=True, null=True)
    next_publish_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'scheduled_notices'


class Schedules(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    date_key = models.DateField()
    sessions = models.JSONField()
    current_session_index = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'schedules'
        unique_together = (('cohort', 'date_key'),)


class SeatAssignments(models.Model):
    pk = models.CompositePrimaryKey('room_id', 'cell_id')
    room = models.ForeignKey('SeatingAssignments', models.CASCADE)
    cell = models.ForeignKey('SeatingCells', models.CASCADE)
    user = models.ForeignKey('Users', models.PROTECT)

    class Meta:
        managed = False
        db_table = 'seat_assignments'
        unique_together = (('room', 'user'),)


class SeatingAssignments(models.Model):
    room = models.OneToOneField('SeatingRooms', models.CASCADE, primary_key=True)
    status = models.CharField()
    published_at = models.DateTimeField(blank=True, null=True)
    published_by = models.ForeignKey('Users', models.SET_NULL, db_column='published_by', blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    updated_by = models.ForeignKey('Users', models.SET_NULL, db_column='updated_by', related_name='seatingassignments_updated_by_set', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'seating_assignments'


class SeatingCells(models.Model):
    id = models.BigAutoField(primary_key=True)
    room = models.ForeignKey('SeatingRooms', models.CASCADE)
    seat_id = models.CharField()
    row = models.IntegerField(blank=True, null=True)
    col = models.IntegerField(blank=True, null=True)
    label = models.CharField(blank=True, null=True)
    type = models.CharField()
    group_id = models.CharField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'seating_cells'
        unique_together = (('room', 'row', 'col'), ('room', 'seat_id'),)


class SeatingRooms(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    room_number = models.CharField(blank=True, null=True)
    rows = models.IntegerField(blank=True, null=True)
    cols = models.IntegerField(blank=True, null=True)
    max_students = models.IntegerField(blank=True, null=True)
    updated_by = models.ForeignKey('Users', models.SET_NULL, db_column='updated_by', blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'seating_rooms'


class StudentIntakes(models.Model):
    user = models.OneToOneField('Users', models.PROTECT, primary_key=True)
    education_major = models.CharField()
    current_status = models.CharField()
    weekly_study_hours = models.CharField()
    programming_level = models.CharField()
    collaboration_tools = models.CharField()
    ai_llm_experience = models.CharField()
    motivation = models.TextField()
    desired_role = models.TextField()
    post_completion_goal = models.TextField()
    awards = models.TextField()
    project_links = models.TextField()
    team_role = models.TextField()
    self_learning_style = models.TextField()
    slump_overcome_experience = models.TextField()
    is_active = models.BooleanField()
    created_by = models.ForeignKey('Users', models.SET_NULL, db_column='created_by', related_name='studentintakes_created_by_set', blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'student_intakes'


class StudyNotes(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    user = models.ForeignKey('Users', models.PROTECT)
    source = models.ForeignKey('StudySources', models.SET_NULL, blank=True, null=True)
    status = models.CharField(blank=True, null=True)
    scope_type = models.CharField(blank=True, null=True)
    scope_value = models.JSONField(blank=True, null=True)
    scope_key = models.CharField(blank=True, null=True)
    report_markdown = models.TextField(blank=True, null=True)
    review_markdown = models.TextField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    message = models.TextField(blank=True, null=True)
    files = models.JSONField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'study_notes'


class StudySources(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    title = models.CharField(blank=True, null=True)
    repo_url = models.CharField(blank=True, null=True)
    branch = models.CharField(blank=True, null=True)
    allowed_prefixes = models.TextField()  # This field type is a guess.
    is_active = models.BooleanField()
    sort_order = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'study_sources'


class SystemCache(models.Model):
    key = models.CharField(primary_key=True)
    data = models.JSONField()
    synced_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'system_cache'


class Todos(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    user = models.ForeignKey('Users', models.PROTECT)
    title = models.CharField()
    is_completed = models.BooleanField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'todos'


class Users(models.Model):
    id = models.BigAutoField(primary_key=True)
    firebase_uid = models.CharField(unique=True, blank=True, null=True)
    email = models.CharField(unique=True, blank=True, null=True)
    password = models.CharField()
    personal_email = models.CharField(blank=True, null=True)
    display_name = models.CharField()
    role = models.CharField()
    cohort = models.ForeignKey(Cohorts, models.PROTECT, blank=True, null=True)
    seat_number = models.IntegerField(blank=True, null=True)
    is_active = models.BooleanField()
    must_change_password = models.BooleanField()
    motto = models.CharField(blank=True, null=True)
    skills = models.TextField()  # This field type is a guess.
    social_links = models.JSONField()
    job_preferences = models.JSONField()
    birth_date = models.DateField(blank=True, null=True)
    photo_url = models.CharField(blank=True, null=True)
    photo_storage_path = models.CharField(blank=True, null=True)
    mileage_balance = models.IntegerField()
    last_login = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'users'


class WeeklyProgress(models.Model):
    pk = models.CompositePrimaryKey('cohort_id', 'user_id')
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    user = models.ForeignKey(Users, models.PROTECT)
    completed_count = models.IntegerField()
    total_count = models.IntegerField()
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'weekly_progress'


class WeeklyTasks(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    title = models.CharField(blank=True, null=True)
    due_date = models.DateTimeField(blank=True, null=True)
    total_count = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'weekly_tasks'


class YoutubeRecommendations(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    video_id = models.CharField(blank=True, null=True)
    title = models.CharField(blank=True, null=True)
    youtube_url = models.CharField(blank=True, null=True)
    thumbnail_url = models.CharField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    tags = models.TextField()  # This field type is a guess.
    is_published = models.BooleanField()
    sort_order = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'youtube_recommendations'
        unique_together = (('cohort', 'video_id'),)
