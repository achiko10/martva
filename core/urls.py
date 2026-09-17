from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path("login/", views.custom_login_view, name="login"),
    path("logout/", views.custom_logout_view, name="logout"),

    # Dashboard
    path("", views.dashboard_view, name="dashboard"),

    # Beneficiaries
    path("beneficiaries/", views.beneficiary_list_view, name="beneficiary_list"),
    path("beneficiaries/new/", views.beneficiary_create_view, name="beneficiary_create"),
    path("beneficiaries/<int:beneficiary_id>/", views.beneficiary_detail_view, name="beneficiary_detail"),
    path("beneficiaries/<int:beneficiary_id>/edit/", views.beneficiary_edit_view, name="beneficiary_edit"),
    path("beneficiaries/<int:beneficiary_id>/progress/", views.progress_view, name="progress"),
    path("beneficiaries/<int:beneficiary_id>/reports/new/", views.monthly_report_create_view, name="monthly_report_create"),
    path("beneficiaries/<int:beneficiary_id>/sessions/new/", views.session_create_view, name="beneficiary_session_create"),

    # Sessions
    path("sessions/new/", views.session_create_view, name="session_create"),
    path("sessions/<int:session_id>/", views.session_detail_view, name="session_detail"),

    # Goals
    path("goals/<int:goal_id>/", views.goal_detail_view, name="goal_detail"),

    # HTMX endpoints
    path("htmx/sensory-activities/", views.htmx_sensory_activities, name="htmx_sensory_activities"),
    path("htmx/beneficiary-goals/", views.htmx_beneficiary_goals, name="htmx_beneficiary_goals"),

    # Reports & PDF
    path("reports/<int:report_id>/edit/", views.monthly_report_edit_view, name="monthly_report_edit"),
    path("reports/<int:report_id>/view/", views.monthly_report_view, name="monthly_report_view"),
    path("reports/<int:report_id>/pdf/", views.monthly_report_pdf_view, name="monthly_report_pdf"),

    # Schedule & Timetable
    path("schedule/", views.schedule_view, name="schedule"),
    path("schedule/add/", views.schedule_add_view, name="schedule_add"),
    path("schedule/<int:slot_id>/edit/", views.schedule_edit_view, name="schedule_edit"),
    path("schedule/<int:slot_id>/status/", views.schedule_status_view, name="schedule_status"),
    path("schedule/<int:slot_id>/delete/", views.schedule_delete_view, name="schedule_delete"),
]
