from django.contrib import admin
from .models import (
    TherapistProfile, Beneficiary, OccupationalProfile, SensoryProfile,
    Goal, SensorySystem, SensoryActivity, SensoryResponse, FunctionalOutcome,
    Session, SessionGoal, SessionSensoryActivity, MonthlyReport, ReportRevision
)


@admin.register(TherapistProfile)
class TherapistProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "title", "clinic_name", "phone", "is_admin_role"]
    list_filter = ["is_admin_role", "clinic_name"]
    search_fields = ["user__username", "user__first_name", "user__last_name", "title"]


class OccupationalProfileInline(admin.StackedInline):
    model = OccupationalProfile
    extra = 0


class SensoryProfileInline(admin.StackedInline):
    model = SensoryProfile
    extra = 0


class GoalInline(admin.TabularInline):
    model = Goal
    extra = 0
    fields = ["domain", "description", "status", "target_date"]


@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display = ["first_name", "last_name", "date_of_birth", "age_display", "therapist", "is_active", "start_date"]
    list_filter = ["is_active", "therapist", "start_date"]
    search_fields = ["first_name", "last_name", "notes"]
    inlines = [OccupationalProfileInline, SensoryProfileInline, GoalInline]


@admin.register(OccupationalProfile)
class OccupationalProfileAdmin(admin.ModelAdmin):
    list_display = ["beneficiary", "updated_at"]
    search_fields = ["beneficiary__first_name", "beneficiary__last_name"]


@admin.register(SensoryProfile)
class SensoryProfileAdmin(admin.ModelAdmin):
    list_display = ["beneficiary", "updated_at"]
    search_fields = ["beneficiary__first_name", "beneficiary__last_name"]


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ["beneficiary", "domain", "description", "metric_unit", "target_date", "status"]
    list_filter = ["status", "domain", "beneficiary__therapist"]
    search_fields = ["beneficiary__first_name", "beneficiary__last_name", "description"]


class SensoryActivityInline(admin.TabularInline):
    model = SensoryActivity
    extra = 1


@admin.register(SensorySystem)
class SensorySystemAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "icon", "order"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [SensoryActivityInline]


@admin.register(SensoryActivity)
class SensoryActivityAdmin(admin.ModelAdmin):
    list_display = ["name", "sensory_system", "is_active"]
    list_filter = ["sensory_system", "is_active"]
    search_fields = ["name", "sensory_system__name"]


@admin.register(SensoryResponse)
class SensoryResponseAdmin(admin.ModelAdmin):
    list_display = ["name", "order", "is_active"]
    list_editable = ["order", "is_active"]
    search_fields = ["name"]


@admin.register(FunctionalOutcome)
class FunctionalOutcomeAdmin(admin.ModelAdmin):
    list_display = ["name", "order", "is_active"]
    list_editable = ["order", "is_active"]
    search_fields = ["name"]


class SessionSensoryActivityInline(admin.TabularInline):
    model = SessionSensoryActivity
    extra = 0
    filter_horizontal = ["responses"]


class SessionGoalInline(admin.TabularInline):
    model = SessionGoal
    extra = 0


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ["beneficiary", "therapist", "date", "duration_minutes", "initial_state", "final_state"]
    list_filter = ["date", "therapist", "initial_state", "final_state"]
    search_fields = ["beneficiary__first_name", "beneficiary__last_name", "notes"]
    filter_horizontal = ["functional_outcomes"]
    inlines = [SessionSensoryActivityInline, SessionGoalInline]


class ReportRevisionInline(admin.TabularInline):
    model = ReportRevision
    extra = 0
    readonly_fields = ["revised_by", "created_at"]


@admin.register(MonthlyReport)
class MonthlyReportAdmin(admin.ModelAdmin):
    list_display = ["beneficiary", "therapist", "year", "month_display", "sessions_count", "is_finalized", "created_at"]
    list_filter = ["year", "month", "is_finalized", "therapist"]
    search_fields = ["beneficiary__first_name", "beneficiary__last_name", "section_1_directions"]
    inlines = [ReportRevisionInline]

