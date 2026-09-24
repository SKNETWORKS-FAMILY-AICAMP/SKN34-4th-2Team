# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.db.models.functions import Lower


class AiEvalRuns(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    prompt_version = models.CharField(blank=True, null=True)
    model = models.CharField(blank=True, null=True)
    source = models.CharField(blank=True, null=True)
    total_cases = models.IntegerField(blank=True, null=True)
    passed = models.IntegerField(blank=True, null=True)
    accuracy = models.DecimalField(max_digits=7, decimal_places=4, blank=True, null=True)
    avg_latency_ms = models.IntegerField(blank=True, null=True)
    failed_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
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
        db_table = 'ai_question_feedback'


class AlertPopupDismissals(models.Model):
    pk = models.CompositePrimaryKey('user_id', 'popup_id')
    user = models.ForeignKey('Users', models.PROTECT)
    popup = models.ForeignKey('AlertPopups', models.CASCADE)
    date_key = models.DateField(blank=True, null=True)

    class Meta:
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
        db_table = 'assessment_answers'


class AssessmentQuestions(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    assessment = models.ForeignKey('Assessments', models.CASCADE)
    order = models.IntegerField(blank=True, null=True)
    type = models.CharField(blank=True, null=True)
    prompt = models.TextField(blank=True, null=True)
    points = models.IntegerField(blank=True, null=True)
    choices = models.JSONField(default=list)
    correct_index = models.IntegerField(blank=True, null=True)
    accepted_answers = models.JSONField(default=list)
    explanation = models.TextField(blank=True, null=True)
    origin = models.CharField(blank=True, null=True)
    ai_log = models.ForeignKey(AiGenerationLogs, models.SET_NULL, blank=True, null=True)
    ai_draft_id = models.CharField(blank=True, null=True)
    prompt_version = models.CharField(blank=True, null=True)
    source_day = models.IntegerField(blank=True, null=True)
    source_topic = models.CharField(blank=True, null=True)

    class Meta:
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
        db_table = 'assessment_submissions'
        unique_together = (('assessment', 'user'),)
        indexes = [models.Index(fields=['assessment', 'submitted_at'], name='idx_assessment_submission_at')]


class Assessments(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey('Cohorts', models.PROTECT)
    title = models.CharField(blank=True, null=True)
    tags = models.JSONField(default=list)
    max_score = models.IntegerField(blank=True, null=True)
    start_at = models.DateTimeField(blank=True, null=True)
    end_at = models.DateTimeField(blank=True, null=True)
    thumbnail_storage_key = models.CharField(blank=True, null=True)
    published = models.BooleanField()
    created_by = models.ForeignKey('Users', models.SET_NULL, db_column='created_by', blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    curriculum_sheet = models.ForeignKey('CurriculumSheets', models.SET_NULL, blank=True, null=True)
    day_from = models.IntegerField(blank=True, null=True)
    day_to = models.IntegerField(blank=True, null=True)
    subject_filter = models.CharField(blank=True, null=True)

    class Meta:
        db_table = 'assessments'
        indexes = [models.Index(fields=['cohort', 'published', 'start_at', 'end_at'], name='idx_assessment_cohort_window')]


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
    attendance_date = models.DateField()
    check_in_at = models.DateTimeField(blank=True, null=True)
    check_out_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(blank=True, null=True)
    data_source = models.CharField(blank=True, null=True)
    finalized_by = models.ForeignKey('Users', models.SET_NULL, related_name='finalized_attendances', blank=True, null=True)
    finalized_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'attendances'
        constraints = [models.UniqueConstraint(fields=['user', 'attendance_date'], name='uq_attendance_user_date')]
        indexes = [models.Index(fields=['cohort', 'attendance_date'])]


class AttendanceIssueReports(models.Model):
    user = models.ForeignKey('Users', models.PROTECT)
    cohort = models.ForeignKey('Cohorts', models.PROTECT)
    attendance_date = models.DateField()
    issue_type = models.CharField()
    details = models.JSONField(default=dict, blank=True)
    evidence_storage_key = models.CharField(blank=True, null=True)
    status = models.CharField(default='submitted')
    reviewed_by = models.ForeignKey('Users', models.SET_NULL, related_name='reviewed_attendance_issues', blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'attendance_issue_reports'
        indexes = [models.Index(fields=['cohort', 'attendance_date', 'status'])]


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
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'cohorts'


class CurriculumPdfs(models.Model):
    cohort = models.OneToOneField(Cohorts, models.PROTECT, primary_key=True)
    storage_key = models.CharField(blank=True, null=True)
    original_filename = models.CharField(blank=True, null=True)
    published = models.BooleanField()
    updated_by = models.ForeignKey('Users', models.SET_NULL, db_column='updated_by', blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
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
        db_table = 'curriculum_rows'


class CurriculumSheets(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    title = models.CharField(blank=True, null=True)
    file_name = models.CharField(blank=True, null=True)
    storage_key = models.CharField(blank=True, null=True)
    source = models.CharField(blank=True, null=True)
    uploaded_by = models.ForeignKey('Users', models.SET_NULL, db_column='uploaded_by', blank=True, null=True)
    uploaded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'curriculum_sheets'


class SubmissionTasks(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    title = models.CharField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    submission_type = models.CharField(default='external_form')
    external_url = models.CharField(blank=True, null=True)
    guide_url = models.CharField(blank=True, null=True)
    due_at = models.DateTimeField(blank=True, null=True)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'submission_tasks'
        indexes = [models.Index(fields=['due_at', 'published'])]


class SubmissionTaskCohorts(models.Model):
    task = models.ForeignKey(SubmissionTasks, models.CASCADE)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)

    class Meta:
        db_table = 'submission_task_cohorts'
        constraints = [models.UniqueConstraint(fields=['task', 'cohort'], name='uq_submission_task_cohort')]


class SubmissionResponses(models.Model):
    task = models.ForeignKey(SubmissionTasks, models.CASCADE)
    user = models.ForeignKey('Users', models.PROTECT)
    source = models.CharField(blank=True, null=True)
    external_response_id = models.CharField(unique=True, blank=True, null=True)
    response = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'submission_responses'
        constraints = [models.UniqueConstraint(fields=['task', 'user'], name='uq_submission_response_task_user')]
        indexes = [models.Index(fields=['task', 'submitted_at'])]


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
        db_table = 'inflearn_packages'


class JobRequirementProfiles(models.Model):
    key = models.CharField(primary_key=True)
    requirements = models.JSONField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'job_requirement_profiles'


class Materials(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    title = models.CharField(blank=True, null=True)
    storage_key = models.CharField(blank=True, null=True)
    file_name = models.CharField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
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
        db_table = 'mileage_products'


class MileageSettings(models.Model):
    cohort = models.OneToOneField(Cohorts, models.PROTECT, primary_key=True)
    category_limits = models.JSONField()
    accrual_rules = models.JSONField()
    updated_by = models.ForeignKey('Users', models.SET_NULL, db_column='updated_by', blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
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
        db_table = 'mileage_transactions'
        indexes = [models.Index(fields=['user', '-created_at'], name='idx_mileage_user_created')]


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
    blog_weeks = models.JSONField(default=list)
    blog_units_granted = models.JSONField(default=list)
    study_week_keys = models.JSONField(default=list)
    study_granted = models.BooleanField()
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
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
    image_storage_key = models.CharField(blank=True, null=True)
    vector_chunk_count = models.IntegerField()
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'notices'
        indexes = [models.Index(fields=['cohort', '-created_at'], name='idx_notice_cohort_created')]


class ProjectTeamMembers(models.Model):
    pk = models.CompositePrimaryKey('team_id', 'user_id')
    team = models.ForeignKey('ProjectTeams', models.CASCADE)
    user = models.ForeignKey('Users', models.PROTECT)

    class Meta:
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
        db_table = 'purchase_requests'
        indexes = [models.Index(fields=['cohort', 'status', '-created_at'], name='idx_purchase_cohort_status')]


class RecommendationEvents(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    user = models.ForeignKey('Users', models.SET_NULL, blank=True, null=True)
    recommendation = models.ForeignKey('YoutubeRecommendations', models.SET_NULL, blank=True, null=True)
    youtube_video_id = models.CharField(blank=True, null=True)
    user_skills = models.JSONField(default=list)
    matched_tags = models.JSONField(default=list)
    action = models.CharField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'recommendation_events'


class RecordSubmissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    user = models.ForeignKey('Users', models.PROTECT)
    type = models.CharField()
    status = models.CharField()
    title = models.CharField(blank=True, null=True)
    details = models.JSONField(default=dict, blank=True)
    review_comment = models.TextField(blank=True, null=True)
    reviewed_by = models.ForeignKey('Users', models.SET_NULL, db_column='reviewed_by', related_name='recordsubmissions_reviewed_by_set', blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'record_submissions'
        indexes = [
            models.Index(fields=['user', 'status', 'submitted_at']),
            models.Index(fields=['cohort', 'type', 'status']),
        ]


class RecordSubmissionFiles(models.Model):
    submission = models.ForeignKey(RecordSubmissions, models.CASCADE, related_name='files')
    storage_key = models.CharField()
    original_filename = models.CharField()
    content_type = models.CharField(blank=True, null=True)
    file_size = models.BigIntegerField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'record_submission_files'
        constraints = [
            models.UniqueConstraint(fields=['submission', 'storage_key'], name='uq_record_file_submission_key')
        ]


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
        db_table = 'resume_feedback'
        indexes = [models.Index(fields=['resume', 'created_at'])]


class ResumeFeedbackReads(models.Model):
    pk = models.CompositePrimaryKey('resume_id', 'user_id', 'feedback_id')
    resume = models.ForeignKey('Resumes', models.CASCADE)
    feedback = models.ForeignKey(ResumeFeedback, models.CASCADE)
    user = models.ForeignKey('Users', models.PROTECT)
    read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'resume_feedback_reads'


class ResumeRevisions(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    resume = models.ForeignKey('Resumes', models.CASCADE)
    revision_no = models.PositiveIntegerField()
    content = models.JSONField()
    created_by = models.ForeignKey('Users', models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'resume_revisions'
        constraints = [models.UniqueConstraint(fields=['resume', 'revision_no'], name='uq_resume_revision_no')]


class Resumes(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    user = models.ForeignKey('Users', models.PROTECT)
    title = models.CharField(blank=True, null=True)
    status = models.CharField(blank=True, null=True)
    content = models.JSONField()
    is_base_resume = models.BooleanField(default=False)
    base_resume = models.ForeignKey('self', models.SET_NULL, related_name='tailored_resumes', blank=True, null=True)
    linked_job_id = models.CharField(blank=True, null=True)
    revision_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'resumes'
        constraints = [
            models.CheckConstraint(condition=models.Q(base_resume__isnull=True) | ~models.Q(base_resume=models.F('id')), name='ck_resume_not_own_base'),
            models.CheckConstraint(condition=models.Q(is_base_resume=False) | models.Q(base_resume__isnull=True), name='ck_base_resume_has_no_parent'),
            models.UniqueConstraint(fields=['user'], condition=models.Q(is_base_resume=True), name='uq_user_base_resume'),
        ]
        indexes = [
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['base_resume']),
            models.Index(fields=['linked_job_id']),
        ]


class SeatPresences(models.Model):
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    user = models.ForeignKey('Users', models.PROTECT)
    presence_date = models.DateField()
    period = models.CharField()
    state = models.CharField()
    updated_by = models.ForeignKey(
        'Users', models.SET_NULL, db_column='updated_by', related_name='updated_seat_presences', blank=True, null=True
    )
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'seat_presences'
        constraints = [
            models.UniqueConstraint(fields=['cohort', 'user', 'presence_date', 'period'], name='uq_seat_presence')
        ]
        indexes = [models.Index(fields=['cohort', 'presence_date', 'period'])]


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
        db_table = 'scheduled_notices'
        indexes = [models.Index(fields=['is_active', 'next_publish_at'], name='idx_scheduled_due')]


class Schedules(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    date_key = models.DateField()
    sessions = models.JSONField()
    current_session_index = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = 'schedules'
        unique_together = (('cohort', 'date_key'),)


class CohortSeating(models.Model):
    cohort = models.OneToOneField(Cohorts, models.PROTECT, primary_key=True)
    room_number = models.CharField(blank=True, null=True)
    layout = models.JSONField(default=dict)
    published = models.BooleanField(default=False)
    updated_by = models.ForeignKey('Users', models.SET_NULL, db_column='updated_by', blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'cohort_seating'


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
    updated_at = models.DateTimeField(blank=True, null=True)
    generation_token = models.CharField(blank=True, null=True)

    class Meta:
        db_table = 'study_notes'


class StudySources(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    title = models.CharField(blank=True, null=True)
    repo_url = models.CharField(blank=True, null=True)
    branch = models.CharField(blank=True, null=True)
    allowed_prefixes = models.JSONField(default=list)
    is_active = models.BooleanField()
    sort_order = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'study_sources'


class SystemCache(models.Model):
    key = models.CharField(primary_key=True)
    data = models.JSONField()
    synced_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'system_cache'


class Todos(models.Model):
    id = models.BigAutoField(primary_key=True)
    legacy_id = models.CharField(unique=True, blank=True, null=True)
    user = models.ForeignKey('Users', models.PROTECT)
    title = models.CharField()
    is_completed = models.BooleanField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
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
    social_links = models.JSONField(default=dict, blank=True)
    birth_date = models.DateField(blank=True, null=True)
    photo_storage_key = models.CharField(blank=True, null=True)
    mileage_balance = models.IntegerField(default=0)
    last_login = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'users'
        indexes = [models.Index(fields=['cohort', 'role'])]

    def set_password(self, raw_password: str) -> None:
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password(raw_password, self.password)


class Skills(models.Model):
    canonical_name = models.CharField(unique=True)
    category = models.CharField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'skills'


class UserSkills(models.Model):
    user = models.ForeignKey(Users, models.PROTECT)
    skill = models.ForeignKey(Skills, models.PROTECT)
    proficiency = models.CharField(blank=True, null=True)
    source = models.CharField(blank=True, null=True)
    evidence = models.JSONField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_skills'
        constraints = [models.UniqueConstraint(fields=['user', 'skill'], name='uq_user_skill')]
        indexes = [models.Index(fields=['skill'])]


class UserJobPreferences(models.Model):
    user = models.OneToOneField(Users, models.CASCADE, primary_key=True)
    preferences = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_job_preferences'


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
    tags = models.JSONField(default=list)
    is_published = models.BooleanField()
    sort_order = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'youtube_recommendations'
        unique_together = (('cohort', 'video_id'),)


class PolicyDocuments(models.Model):
    """Stable identity and location of a policy/FAQ source."""

    id = models.BigAutoField(primary_key=True)
    source_key = models.TextField(unique=True)
    source_type = models.CharField(max_length=32)
    source_name = models.TextField()
    source_url = models.TextField(blank=True, default='')
    storage_key = models.TextField(blank=True, null=True)
    title = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'policy_documents'
        indexes = [models.Index(fields=['is_active', 'source_type'], name='idx_policy_active_type')]


class PolicyDocumentRevisions(models.Model):
    """Immutable extracted text snapshot; latest revision_no is current."""

    id = models.BigAutoField(primary_key=True)
    document = models.ForeignKey(PolicyDocuments, models.PROTECT, related_name='revisions')
    revision_no = models.PositiveIntegerField()
    content_sha256 = models.CharField(max_length=64)
    extracted_text = models.TextField()
    source_updated_at = models.DateTimeField(blank=True, null=True)
    ingested_at = models.DateTimeField(auto_now_add=True)
    extraction_metadata = models.JSONField(default=dict)

    class Meta:
        db_table = 'policy_document_revisions'
        constraints = [
            models.UniqueConstraint(fields=['document', 'revision_no'], name='uq_policy_document_revision'),
        ]
        indexes = [models.Index(fields=['document', '-revision_no'], name='idx_policy_document_latest')]


class PracticeSets(models.Model):
    legacy_id = models.CharField(unique=True)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    owner = models.ForeignKey(Users, models.PROTECT, blank=True, null=True, related_name='personal_practice_sets')
    origin = models.CharField(default='lesson', choices=[('lesson', 'lesson'), ('note', 'note'), ('file', 'file')])
    source_title = models.CharField(default='')
    lesson_date = models.DateField()
    day_label = models.CharField(default='')
    title = models.CharField(default='')
    source_files = models.JSONField(default=list)
    generation_model = models.CharField(default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'practice_sets'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(origin__in=('lesson', 'note', 'file')),
                name='ck_practice_set_origin',
            ),
        ]
        indexes = [
            models.Index(fields=['cohort', '-lesson_date']),
        ]


class PracticeProblems(models.Model):
    class Kind(models.TextChoices):
        CONCEPT = 'concept'
        CODE_OUTPUT = 'code_output'
        CODE_BLANK = 'code_blank'
        CODE_FIX = 'code_fix'
        CODE_WRITE = 'code_write'
        CODE_SCRATCH = 'code_scratch'

    problem_set = models.ForeignKey(PracticeSets, models.CASCADE, related_name='problems')
    position = models.PositiveIntegerField()
    kind = models.CharField(choices=Kind.choices)
    topic = models.CharField(default='')
    prompt = models.TextField(default='')
    source_files = models.JSONField(default=list)
    explanation = models.TextField(default='')
    choices = models.JSONField(default=list)
    answer_index = models.IntegerField(blank=True, null=True)
    starter_code = models.TextField(default='')
    expected_stdout = models.TextField(default='')
    blank_answers = models.JSONField(default=list)
    reference_solution = models.TextField(default='')
    hidden_tests = models.TextField(default='')
    packages = models.JSONField(default=list)

    class Meta:
        db_table = 'practice_problems'
        constraints = [
            models.UniqueConstraint(fields=['problem_set', 'position'], name='uq_practice_problem_position'),
            models.CheckConstraint(
                condition=models.Q(kind__in=('concept', 'code_output', 'code_blank', 'code_fix', 'code_write', 'code_scratch')),
                name='ck_practice_problem_kind',
            ),
        ]


class PracticeAttempts(models.Model):
    pk = models.CompositePrimaryKey('user_id', 'problem_id')
    user = models.ForeignKey(Users, models.PROTECT)
    problem = models.ForeignKey(PracticeProblems, models.CASCADE)
    passed = models.BooleanField(default=False)
    tries = models.PositiveIntegerField(default=1)
    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'practice_attempts'
        indexes = [models.Index(fields=['problem'])]


class PracticeReports(models.Model):
    class Reason(models.TextChoices):
        UNCLEAR = 'unclear'
        ANSWER = 'answer'
        TESTS = 'tests'
        OFFTOPIC = 'offtopic'
        OTHER = 'other'

    user = models.ForeignKey(Users, models.PROTECT)
    problem = models.ForeignKey(PracticeProblems, models.CASCADE)
    reason = models.CharField(choices=Reason.choices)
    note = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'practice_reports'
        constraints = [
            models.UniqueConstraint(fields=['user', 'problem'], name='uq_practice_report_user_problem'),
            models.CheckConstraint(
                condition=models.Q(reason__in=('unclear', 'answer', 'tests', 'offtopic', 'other')),
                name='ck_practice_report_reason',
            ),
        ]
        indexes = [models.Index(fields=['problem'])]


class PracticeReviews(models.Model):
    class Decision(models.TextChoices):
        HIDDEN = 'hidden'
        KEPT = 'kept'

    problem = models.OneToOneField(PracticeProblems, models.CASCADE, primary_key=True)
    decision = models.CharField(choices=Decision.choices)
    decided_by = models.ForeignKey(Users, models.PROTECT)
    decided_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'practice_reviews'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(decision__in=('hidden', 'kept')),
                name='ck_practice_review_decision',
            )
        ]


class PracticeCoverage(models.Model):
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    source_title = models.CharField()
    data = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'practice_coverage'
        constraints = [
            models.UniqueConstraint(fields=['cohort', 'source_title'], name='uq_practice_coverage_source')
        ]


class StudyGithubOwners(models.Model):
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    owner = models.CharField()
    added_by = models.ForeignKey(Users, models.SET_NULL, blank=True, null=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)
    last_error = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'study_github_owners'
        constraints = [
            models.UniqueConstraint(models.F('cohort'), Lower('owner'), name='uq_study_github_cohort_owner'),
        ]


class StudyPracticeSettings(models.Model):
    source = models.OneToOneField(StudySources, models.PROTECT, primary_key=True)
    enabled = models.BooleanField(default=True)
    updated_by = models.ForeignKey(Users, models.SET_NULL, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'study_practice_settings'


class StudyPracticeRuns(models.Model):
    class Status(models.TextChoices):
        RUNNING = 'running'
        DONE = 'done'
        FAILED = 'failed'

    class Trigger(models.TextChoices):
        SCHEDULE = 'schedule'
        MANUAL = 'manual'

    source = models.ForeignKey(StudySources, models.PROTECT)
    trigger = models.CharField(default=Trigger.SCHEDULE, choices=Trigger.choices)
    status = models.CharField(default=Status.RUNNING, choices=Status.choices)
    problems = models.PositiveIntegerField(default=0)
    dates = models.JSONField(default=list)
    message = models.TextField(default='')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'study_practice_runs'
        constraints = [
            models.CheckConstraint(condition=models.Q(trigger__in=('schedule', 'manual')), name='ck_study_run_trigger'),
            models.CheckConstraint(condition=models.Q(status__in=('running', 'done', 'failed')), name='ck_study_run_status'),
        ]
        indexes = [models.Index(fields=['source', '-started_at'], name='idx_study_run_source_started')]


class StudyPracticeJobs(models.Model):
    class Origin(models.TextChoices):
        NOTE = 'note'
        FILE = 'file'

    class Status(models.TextChoices):
        RUNNING = 'running'
        DONE = 'done'
        FAILED = 'failed'

    user = models.ForeignKey(Users, models.PROTECT)
    cohort = models.ForeignKey(Cohorts, models.PROTECT)
    origin = models.CharField(choices=Origin.choices)
    label = models.CharField(default='')
    status = models.CharField(default=Status.RUNNING, choices=Status.choices)
    practice_set = models.ForeignKey(PracticeSets, models.SET_NULL, blank=True, null=True)
    message = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'study_practice_jobs'
        constraints = [
            models.CheckConstraint(condition=models.Q(origin__in=('note', 'file')), name='ck_study_job_origin'),
            models.CheckConstraint(condition=models.Q(status__in=('running', 'done', 'failed')), name='ck_study_job_status'),
        ]
        indexes = [models.Index(fields=['user', '-created_at'], name='idx_study_job_user_created')]


class StudyTutorTurns(models.Model):
    class Role(models.TextChoices):
        USER = 'user'
        ASSISTANT = 'assistant'

    user = models.ForeignKey(Users, models.PROTECT)
    problem = models.ForeignKey(PracticeProblems, models.SET_NULL, blank=True, null=True)
    thread_key = models.CharField()
    role = models.CharField(choices=Role.choices)
    text = models.TextField()
    kind = models.CharField(default='')
    hint_level = models.IntegerField(blank=True, null=True)
    lines = models.JSONField(default=list)
    llm = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'study_tutor_turns'
        constraints = [models.CheckConstraint(condition=models.Q(role__in=('user', 'assistant')), name='ck_study_turn_role')]
        indexes = [models.Index(fields=['user', 'thread_key', 'id'], name='idx_study_turn_thread')]
