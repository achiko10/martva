import json
import uuid
import calendar
from datetime import date, datetime, timedelta, time
from collections import Counter
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.db.models import Count, Q, Prefetch, Max

from .models import (
    TherapistProfile, Beneficiary, OccupationalProfile, SensoryProfile,
    Goal, SensorySystem, SensoryActivity, SensoryResponse, FunctionalOutcome,
    Session, SessionGoal, SessionSensoryActivity, MonthlyReport, ReportRevision,
    ScheduleSlot
)
from .reports import generate_monthly_report_content
from .pdf import generate_report_pdf


def get_or_create_therapist(user):
    """Safely returns TherapistProfile for any authenticated user."""
    if not user or not user.is_authenticated:
        return None
    profile, _ = TherapistProfile.objects.get_or_create(user=user)
    return profile


def is_admin_user(user):
    """Checks whether user has superuser, staff, or admin therapist privileges."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    profile = get_or_create_therapist(user)
    return bool(profile and profile.is_admin_role)


def add_calendar_months(source_date, months):
    """Adds `months` calendar months to `source_date` accurately."""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def get_user_beneficiaries(user):
    """Filter beneficiaries based on user role"""
    if not user.is_authenticated:
        return Beneficiary.objects.none()
    if is_admin_user(user):
        return Beneficiary.objects.all()
    profile = get_or_create_therapist(user)
    return Beneficiary.objects.filter(Q(therapist=profile) | Q(therapist__isnull=True))


def can_access_beneficiary(user, beneficiary):
    if not user.is_authenticated:
        return False
    if is_admin_user(user):
        return True
    if beneficiary.therapist is None:
        return True
    profile = get_or_create_therapist(user)
    if beneficiary.therapist == profile:
        return True
    return False


def custom_login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"მოგესალმებით, {user.get_full_name() or user.username}!")
            return redirect("dashboard")
        else:
            messages.error(request, "მომხმარებლის სახელი ან პაროლი არასწორია.")
    else:
        form = AuthenticationForm()
    return render(request, "auth/login.html", {"form": form})


def custom_logout_view(request):
    logout(request)
    messages.info(request, "თქვენ წარმატებით გამოხვედით სისტემიდან.")
    return redirect("login")


@login_required
def dashboard_view(request):
    user = request.user
    beneficiaries = get_user_beneficiaries(user).filter(is_active=True)
    today = date.today()
    current_year = today.year
    current_month = today.month

    # Sessions queries
    sessions_qs = Session.objects.filter(beneficiary__in=beneficiaries)
    today_sessions = sessions_qs.filter(date=today)
    month_sessions_count = sessions_qs.filter(date__year=current_year, date__month=current_month).count()

    # Beneficiary card stats
    beneficiary_cards = []
    for b in beneficiaries:
        b_sessions_count = b.sessions.filter(date__year=current_year, date__month=current_month).count()
        active_goals_count = b.goals.filter(status="active").count()
        has_finalized_report = b.monthly_reports.filter(year=current_year, month=current_month, is_finalized=True).exists()
        has_draft_report = b.monthly_reports.filter(year=current_year, month=current_month, is_finalized=False).exists()

        if has_finalized_report:
            rep_status = "მზად არის"
            rep_badge_class = "bg-emerald-100 text-emerald-800"
        elif has_draft_report:
            rep_status = "სამუშაო ვერსია"
            rep_badge_class = "bg-amber-100 text-amber-800"
        else:
            rep_status = "დასამუშავებელია"
            rep_badge_class = "bg-slate-100 text-slate-700"

        beneficiary_cards.append({
            "beneficiary": b,
            "month_sessions": b_sessions_count,
            "active_goals": active_goals_count,
            "report_status": rep_status,
            "rep_badge_class": rep_badge_class
        })

    recent_sessions = sessions_qs.order_by("-date", "-created_at")[:6]

    profile = get_or_create_therapist(user)
    if is_admin_user(user):
        today_slots = ScheduleSlot.objects.filter(date=today).select_related("beneficiary").order_by("start_time")
    else:
        today_slots = ScheduleSlot.objects.filter(
            Q(therapist=profile) | Q(therapist__isnull=True),
            date=today
        ).select_related("beneficiary").order_by("start_time")

    context = {
        "beneficiary_cards": beneficiary_cards,
        "beneficiaries_total": beneficiaries.count(),
        "today_sessions_count": today_sessions.count(),
        "today_sessions": today_sessions,
        "today_slots": today_slots,
        "month_sessions_count": month_sessions_count,
        "recent_sessions": recent_sessions,
        "current_month_name": MonthlyReport.MONTH_NAMES.get(current_month, str(current_month)),
        "current_year": current_year,
    }
    return render(request, "core/dashboard.html", context)


@login_required
def beneficiary_list_view(request):
    search_query = request.GET.get("q", "").strip()
    therapist_id = request.GET.get("therapist", "").strip()
    status_filter = request.GET.get("status", "active")

    beneficiaries = get_user_beneficiaries(request.user)

    if status_filter == "active":
        beneficiaries = beneficiaries.filter(is_active=True)
    elif status_filter == "inactive":
        beneficiaries = beneficiaries.filter(is_active=False)

    if search_query:
        beneficiaries = beneficiaries.filter(
            Q(first_name__icontains=search_query) | Q(last_name__icontains=search_query)
        )

    admin_flag = is_admin_user(request.user)
    if therapist_id and admin_flag:
        beneficiaries = beneficiaries.filter(therapist_id=therapist_id)

    all_therapists = TherapistProfile.objects.all() if admin_flag else None

    context = {
        "beneficiaries": beneficiaries,
        "search_query": search_query,
        "status_filter": status_filter,
        "therapist_id": therapist_id,
        "all_therapists": all_therapists,
    }
    return render(request, "core/beneficiary_list.html", context)


@login_required
def beneficiary_create_view(request):
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        dob_str = request.POST.get("date_of_birth", "").strip()
        start_date_str = request.POST.get("start_date", "").strip() or date.today().isoformat()
        session_duration = int(request.POST.get("session_duration_minutes", 50) or 50)
        weekly_sessions = int(request.POST.get("weekly_sessions_planned", 2) or 2)
        notes = request.POST.get("notes", "").strip()

        # Assigned therapist
        therapist_id = request.POST.get("therapist")
        assigned_therapist = None
        if therapist_id:
            assigned_therapist = TherapistProfile.objects.filter(id=therapist_id).first()
        if not assigned_therapist:
            assigned_therapist = get_or_create_therapist(request.user)

        if not first_name or not last_name or not dob_str:
            messages.error(request, "გთხოვთ შეავსოთ სავალდებულო ველები (სახელი, გვარი, დაბადების თარიღი).")
        else:
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            b = Beneficiary.objects.create(
                first_name=first_name,
                last_name=last_name,
                date_of_birth=dob,
                start_date=start_date,
                therapist=assigned_therapist,
                session_duration_minutes=session_duration,
                weekly_sessions_planned=weekly_sessions,
                notes=notes
            )
            # Auto-create empty occupational & sensory profiles
            OccupationalProfile.objects.create(beneficiary=b)
            SensoryProfile.objects.create(beneficiary=b)
            messages.success(request, f"ბენეფიციარი {b.full_name} წარმატებით დაემატა.")
            return redirect("beneficiary_detail", beneficiary_id=b.id)

    therapists = TherapistProfile.objects.all() if is_admin_user(request.user) else None
    return render(request, "core/beneficiary_form.html", {
        "therapists": therapists,
        "is_create": True,
        "today_date": date.today().isoformat(),
    })


@login_required
def beneficiary_detail_view(request, beneficiary_id):
    beneficiary = get_object_or_404(Beneficiary, id=beneficiary_id)
    if not can_access_beneficiary(request.user, beneficiary):
        return HttpResponseForbidden("თქვენ არ გაქვთ ამ ბენეფიციარის მონაცემების ნახვის უფლება.")

    active_tab = request.GET.get("tab", "overview")

    # Ensure profiles exist
    occ_profile, _ = OccupationalProfile.objects.get_or_create(beneficiary=beneficiary)
    sens_profile, _ = SensoryProfile.objects.get_or_create(beneficiary=beneficiary)

    # Handle profile form submissions
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_occupational":
            occ_profile.self_care = request.POST.get("self_care", "").strip()
            occ_profile.play = request.POST.get("play", "").strip()
            occ_profile.attention = request.POST.get("attention", "").strip()
            occ_profile.motor_skills = request.POST.get("motor_skills", "").strip()
            occ_profile.functional_participation = request.POST.get("functional_participation", "").strip()
            occ_profile.general_notes = request.POST.get("general_notes", "").strip()
            occ_profile.save()
            messages.success(request, "ოკუპაციური პროფილი წარმატებით განახლდა.")
            return redirect(f"{request.path}?tab=occupational")

        elif action == "update_sensory":
            sens_profile.tactile = request.POST.get("tactile", "").strip()
            sens_profile.proprioceptive = request.POST.get("proprioceptive", "").strip()
            sens_profile.vestibular = request.POST.get("vestibular", "").strip()
            sens_profile.auditory = request.POST.get("auditory", "").strip()
            sens_profile.visual = request.POST.get("visual", "").strip()
            sens_profile.olfactory = request.POST.get("olfactory", "").strip()
            sens_profile.gustatory = request.POST.get("gustatory", "").strip()
            sens_profile.interoceptive = request.POST.get("interoceptive", "").strip()
            sens_profile.multisensory = request.POST.get("multisensory", "").strip()
            sens_profile.observations = request.POST.get("observations", "").strip()
            sens_profile.save()
            messages.success(request, "სენსორული პროფილი წარმატებით განახლდა.")
            return redirect(f"{request.path}?tab=sensory")

        elif action == "create_goal":
            domain = request.POST.get("domain", "sensory_regulation")
            occupation = request.POST.get("occupation", "").strip()
            environment_context = request.POST.get("environment_context", "").strip()
            criteria_type = request.POST.get("criteria_type", "prompts").strip()

            measurement_type = request.POST.get("measurement_type", "percentage").strip()
            try:
                baseline_numeric = float(request.POST.get("baseline_numeric", 0))
                target_numeric = float(request.POST.get("target_numeric", 100))
            except ValueError:
                baseline_numeric = 0.0
                target_numeric = 100.0
            unit_label = request.POST.get("unit_label", "%").strip()

            target_date_str = request.POST.get("target_date", "").strip()
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date() if target_date_str else None

            # Generated or manual description
            description = request.POST.get("description", "").strip()
            if not description and occupation:
                env_clause = f" ({environment_context})" if environment_context else ""
                target_clause = f" — სამიზნე: {target_numeric}{unit_label}" if unit_label else ""
                description = f"ბენეფიციარი შეძლებს: {occupation}{env_clause}{target_clause}."

            therapist = get_or_create_therapist(request.user)
            g = Goal.objects.create(
                beneficiary=beneficiary,
                therapist=therapist,
                domain=domain,
                occupation=occupation,
                environment_context=environment_context,
                criteria_type=criteria_type,
                measurement_type=measurement_type,
                baseline_numeric=baseline_numeric,
                current_numeric=baseline_numeric,
                target_numeric=target_numeric,
                unit_label=unit_label,
                description=description,
                baseline_state=f"{baseline_numeric}{unit_label}",
                target_state=f"{target_numeric}{unit_label}",
                target_date=target_date,
                status="active"
            )
            g.progress_percentage = g.calculate_progress_percentage()
            g.save()

            messages.success(request, "ახალი გაზომვადი SMART მიზანი წარმატებით დაემატა!")
            return redirect("beneficiary_detail", beneficiary_id=beneficiary.id)

        elif action == "update_goal_status":
            goal_id = request.POST.get("goal_id")
            new_status = request.POST.get("status")
            goal = get_object_or_404(Goal, id=goal_id, beneficiary=beneficiary)
            goal.status = new_status
            goal.save()
            messages.success(request, f"მიზნის სტატუსი შეიცვალა: {goal.get_status_display()}")
            return redirect(f"{request.path}?tab=goals")

    goals = beneficiary.goals.all()
    sessions = beneficiary.sessions.all()[:15]
    reports = beneficiary.monthly_reports.all()

    context = {
        "beneficiary": beneficiary,
        "active_tab": active_tab,
        "occ_profile": occ_profile,
        "sens_profile": sens_profile,
        "goals": goals,
        "sessions": sessions,
        "reports": reports,
        "domain_choices": Goal.DOMAIN_CHOICES,
        "status_choices": Goal.STATUS_CHOICES,
    }
    return render(request, "core/beneficiary_detail.html", context)


@login_required
def beneficiary_edit_view(request, beneficiary_id):
    beneficiary = get_object_or_404(Beneficiary, id=beneficiary_id)
    if not can_access_beneficiary(request.user, beneficiary):
        return HttpResponseForbidden()

    admin_flag = is_admin_user(request.user)

    if request.method == "POST":
        beneficiary.first_name = request.POST.get("first_name", "").strip()
        beneficiary.last_name = request.POST.get("last_name", "").strip()
        dob_str = request.POST.get("date_of_birth", "").strip()
        start_date_str = request.POST.get("start_date", "").strip()
        beneficiary.session_duration_minutes = int(request.POST.get("session_duration_minutes", 50) or 50)
        beneficiary.weekly_sessions_planned = int(request.POST.get("weekly_sessions_planned", 2) or 2)
        beneficiary.notes = request.POST.get("notes", "").strip()
        beneficiary.is_active = "is_active" in request.POST

        if dob_str:
            beneficiary.date_of_birth = datetime.strptime(dob_str, "%Y-%m-%d").date()
        if start_date_str:
            beneficiary.start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()

        if admin_flag:
            t_id = request.POST.get("therapist")
            beneficiary.therapist = TherapistProfile.objects.filter(id=t_id).first() if t_id else None

        beneficiary.save()
        messages.success(request, "მონაცემები განახლდა.")
        return redirect("beneficiary_detail", beneficiary_id=beneficiary.id)

    therapists = TherapistProfile.objects.all() if admin_flag else None
    return render(request, "core/beneficiary_form.html", {
        "beneficiary": beneficiary,
        "therapists": therapists,
        "is_create": False,
        "today_date": date.today().isoformat(),
    })


# ==================== SMART CLINICAL SESSION RECORDING ====================

@login_required
def session_create_view(request, beneficiary_id=None):
    beneficiaries = get_user_beneficiaries(request.user).filter(is_active=True)
    slot_id = request.GET.get("slot_id") or request.POST.get("slot_id")
    slot_obj = ScheduleSlot.objects.filter(id=slot_id).first() if slot_id else None

    selected_beneficiary = None
    if beneficiary_id:
        selected_beneficiary = get_object_or_404(beneficiaries, id=beneficiary_id)
    elif slot_obj and slot_obj.beneficiary:
        selected_beneficiary = slot_obj.beneficiary
    elif beneficiaries.exists():
        selected_beneficiary = beneficiaries.first()

    if request.method == "POST":
        target_b_id = request.POST.get("beneficiary")
        target_beneficiary = get_object_or_404(beneficiaries, id=target_b_id)

        session_date_str = request.POST.get("date", date.today().isoformat())
        session_date = datetime.strptime(session_date_str, "%Y-%m-%d").date()
        duration = int(request.POST.get("duration_minutes", 50) or 50)
        entry_adaptation = request.POST.get("entry_adaptation", "calm_organized")
        initial_state = request.POST.get("initial_state", "green")
        final_state = request.POST.get("final_state", "green")
        challenges = request.POST.getlist("challenges")
        notes = request.POST.get("notes", "").strip()

        therapist = get_or_create_therapist(request.user)

        # 1. Create Session
        session = Session.objects.create(
            beneficiary=target_beneficiary,
            therapist=therapist,
            date=session_date,
            duration_minutes=duration,
            entry_adaptation=entry_adaptation,
            initial_state=initial_state,
            final_state=final_state,
            challenges=challenges,
            notes=notes
        )

        # Functional outcomes (Adaptive Response)
        outcome_ids = request.POST.getlist("functional_outcomes")
        if outcome_ids:
            session.functional_outcomes.set(outcome_ids)

        if slot_obj:
            slot_obj.session = session
            slot_obj.status = "completed"
            slot_obj.save()

        # 2. Add Goals Worked On & Update Progress
        goal_ids = request.POST.getlist("goals")
        for gid in goal_ids:
            goal_obj = Goal.objects.filter(id=gid, beneficiary=target_beneficiary).first()
            if goal_obj:
                g_val = request.POST.get(f"goal_value_{gid}")
                g_prompt = request.POST.get(f"goal_prompt_{gid}", "")
                g_numeric = None
                if g_val is not None and g_val.strip() != "":
                    try:
                        g_numeric = float(g_val.strip())
                        goal_obj.update_progress(g_numeric)
                    except ValueError:
                        pass

                SessionGoal.objects.create(
                    session=session,
                    goal=goal_obj,
                    recorded_numeric=g_numeric,
                    prompt_level=g_prompt,
                    progress_value=f"{g_val}{goal_obj.unit_label}" if g_val else ""
                )

        # 3. Add Smart Clinical Activities with Context-Specific Evaluation Schemas
        activity_ids = request.POST.getlist("activities")
        for aid in activity_ids:
            act_obj = SensoryActivity.objects.select_related("sensory_system").filter(id=aid).first()
            if not act_obj:
                continue

            try:
                act_dur = int(request.POST.get(f"act_duration_{aid}", 10) or 10)
            except ValueError:
                act_dur = 10

            assistance = request.POST.get(f"act_assistance_{aid}", "verbal")
            intensity = request.POST.get(f"act_intensity_{aid}", "medium")
            direction = request.POST.get(f"act_direction_{aid}", "none")
            speed = request.POST.get(f"act_speed_{aid}", "none")
            act_start = request.POST.get(f"act_start_{aid}", "cue")
            interoception = request.POST.get(f"act_interoception_{aid}", "none")
            act_note = request.POST.get(f"act_note_{aid}", "").strip()

            # Collect smart evaluation parameters
            eval_keys = [
                "vector", "tempo", "reaction", "intensity_label", "force_modulation",
                "reg_effect", "contact_form", "tactile_response", "perception_response",
                "praxis_stage", "prompt_label", "motor_quality", "grasp_type",
                "accuracy", "initiation", "awareness", "strategy"
            ]
            eval_data = {}
            for k in eval_keys:
                val = request.POST.get(f"act_{k}_{aid}", "").strip()
                if val:
                    eval_data[k] = val

            sa = SessionSensoryActivity.objects.create(
                session=session,
                sensory_activity=act_obj,
                duration_minutes=act_dur,
                intensity=intensity,
                assistance_level=assistance,
                activity_start=act_start,
                movement_direction=direction,
                speed=speed,
                interoception_mode=interoception,
                evaluation_data=eval_data,
                notes=act_note,
            )

            # Map qualitative reaction tags into SensoryResponse records for analytics/reports
            for resp_key in ["reaction", "tactile_response", "perception_response", "reg_effect"]:
                resp_text = eval_data.get(resp_key)
                if resp_text:
                    r_obj, _ = SensoryResponse.objects.get_or_create(
                        name=resp_text[:150],
                        defaults={"is_active": True}
                    )
                    sa.responses.add(r_obj)

        messages.success(request, f"სესია ({target_beneficiary.full_name}, {session.date}) წარმატებით დაფიქსირდა!")
        return redirect("session_detail", session_id=session.id)

    active_activities_prefetch = Prefetch(
        "activities",
        queryset=SensoryActivity.objects.filter(is_active=True).order_by("id")
    )
    clinical_systems = (
        SensorySystem.objects.filter(order__lte=8)
        .prefetch_related(active_activities_prefetch)
        .order_by("order")
    )
    functional_outcomes = FunctionalOutcome.objects.filter(is_active=True).order_by("order")

    context = {
        "beneficiaries": beneficiaries,
        "selected_beneficiary": selected_beneficiary,
        "clinical_systems": clinical_systems,
        "functional_outcomes": functional_outcomes,
        "entry_adaptation_choices": Session.ENTRY_ADAPTATION_CHOICES,
        "initial_state_choices": Session.INITIAL_STATE_CHOICES,
        "final_state_choices": Session.FINAL_STATE_CHOICES,
        "today_date": slot_obj.date.isoformat() if slot_obj else date.today().isoformat(),
        "slot_id": slot_id,
    }
    return render(request, "core/session_form.html", context)


def htmx_sensory_activities(request):
    """
    HTMX Endpoint: returns sensory activities and rapid parameters
    dynamically based on the selected sensory system slugs.
    """
    system_slugs = request.GET.getlist("systems")
    systems = SensorySystem.objects.filter(slug__in=system_slugs).prefetch_related("activities")
    responses = SensoryResponse.objects.filter(is_active=True)

    context = {
        "systems": systems,
        "responses": responses,
    }
    return render(request, "core/partials/htmx_sensory_activities.html", context)


@login_required
def htmx_beneficiary_goals(request):
    """HTMX Endpoint to load active goals when beneficiary is changed in session form"""
    b_id = request.GET.get("beneficiary_id")
    goals = Goal.objects.filter(beneficiary_id=b_id, status="active") if b_id else Goal.objects.none()
    return render(request, "core/partials/htmx_beneficiary_goals.html", {"goals": goals})


@login_required
def session_detail_view(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    if not can_access_beneficiary(request.user, session.beneficiary):
        return HttpResponseForbidden()

    return render(request, "core/session_detail.html", {"session": session})


# ==================== PROGRESS TRACKING & CHARTS ====================

@login_required
def progress_view(request, beneficiary_id):
    beneficiary = get_object_or_404(Beneficiary, id=beneficiary_id)
    if not can_access_beneficiary(request.user, beneficiary):
        return HttpResponseForbidden()

    sessions = beneficiary.sessions.all().order_by("date")
    sessions_count = sessions.count()

    # 1. Frequency of sensory systems
    system_counts = Counter()
    for s in sessions:
        for sa in s.sensory_activities.all():
            system_counts[sa.sensory_activity.sensory_system.name] += 1

    # 2. Activity frequency
    activity_counts = Counter()
    for s in sessions:
        for sa in s.sensory_activities.all():
            activity_counts[sa.sensory_activity.name] += 1

    # 3. Response distribution
    response_counts = Counter()
    for s in sessions:
        for sa in s.sensory_activities.all():
            for r in sa.responses.all():
                response_counts[r.name] += 1

    # 4. Assistance level over time (6-8 level OT Prompt Hierarchy mapped 1..6)
    assist_weights = {
        "full": 1,
        "maximal": 2,
        "moderate": 3,
        "minimal": 4,
        "gestural_modeling": 4.5,
        "verbal": 5,
        "environmental": 5.5,
        "independent": 6,
    }

    timeline_dates = []
    timeline_durations = []
    timeline_assist = []

    for s in sessions:
        timeline_dates.append(s.date.strftime("%d.%m"))
        acts = s.sensory_activities.all()
        avg_act_dur = round(sum(a.duration_minutes for a in acts) / len(acts), 1) if acts else 0
        timeline_durations.append(avg_act_dur)

        avg_assist = round(sum(assist_weights.get(a.assistance_level, 3) for a in acts) / len(acts), 1) if acts else 3
        timeline_assist.append(avg_assist)

    chart_data = {
        "system_labels": list(system_counts.keys()),
        "system_values": list(system_counts.values()),
        "timeline_dates": timeline_dates,
        "timeline_durations": timeline_durations,
        "timeline_assist": timeline_assist,
        "response_labels": [k for k, _ in response_counts.most_common(6)],
        "response_values": [v for _, v in response_counts.most_common(6)],
    }

    context = {
        "beneficiary": beneficiary,
        "sessions_count": sessions_count,
        "system_counts": system_counts.most_common(),
        "top_activities": activity_counts.most_common(8),
        "top_responses": response_counts.most_common(8),
        "chart_data_json": json.dumps(chart_data, ensure_ascii=False),
        "active_goals": beneficiary.goals.filter(status="active"),
    }
    return render(request, "core/progress.html", context)


# ==================== MONTHLY REPORTS & PDF ====================

@login_required
def monthly_report_create_view(request, beneficiary_id):
    beneficiary = get_object_or_404(Beneficiary, id=beneficiary_id)
    if not can_access_beneficiary(request.user, beneficiary):
        return HttpResponseForbidden()

    today = date.today()
    if request.method == "POST":
        year = int(request.POST.get("year", today.year))
        month = int(request.POST.get("month", today.month))

        existing_report = MonthlyReport.objects.filter(beneficiary=beneficiary, year=year, month=month).first()
        if existing_report:
            messages.info(request, f"{year} წლის {existing_report.month_display}-ის ანგარიში უკვე არსებობს. გადამისამართება რედაქტორზე.")
            return redirect("monthly_report_edit", report_id=existing_report.id)

        content = generate_monthly_report_content(beneficiary, year, month)
        therapist = get_or_create_therapist(request.user) or beneficiary.therapist

        report = MonthlyReport.objects.create(
            beneficiary=beneficiary,
            therapist=therapist,
            year=year,
            month=month,
            **content
        )

        ReportRevision.objects.create(
            report=report,
            revised_by=request.user,
            revision_note="ავტომატური საწყისი გენერაცია",
            snapshot_data=content
        )
        messages.success(request, f"{report.period_display}-ის ანგარიშის მონახაზი შეიქმნა! გთხოვთ გადაამოწმოთ და დაარედაქტიროთ.")
        return redirect("monthly_report_edit", report_id=report.id)

    months = [(m, name) for m, name in MonthlyReport.MONTH_NAMES.items()]
    years = [today.year - 1, today.year, today.year + 1]

    return render(request, "core/report_create.html", {
        "beneficiary": beneficiary,
        "months": months,
        "years": years,
        "selected_month": today.month,
        "selected_year": today.year,
    })


@login_required
def monthly_report_edit_view(request, report_id):
    report = get_object_or_404(MonthlyReport, id=report_id)
    if not can_access_beneficiary(request.user, report.beneficiary):
        return HttpResponseForbidden()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "regenerate":
            content = generate_monthly_report_content(report.beneficiary, report.year, report.month)
            for k, v in content.items():
                setattr(report, k, v)
            report.save()
            ReportRevision.objects.create(
                report=report,
                revised_by=request.user,
                revision_note="მონაცემთა ხელახალი ავტომატური სინქრონიზაცია",
                snapshot_data=content
            )
            messages.success(request, "ანგარიშის ტექსტი ხელახლა დაგენერირდა სესიების უახლესი მონაცემებიდან.")
            return redirect("monthly_report_edit", report_id=report.id)

        report.title = request.POST.get("title", report.title).strip()
        report.section_1_directions = request.POST.get("section_1_directions", "").strip()
        report.section_2_goals = request.POST.get("section_2_goals", "").strip()
        report.section_3_work_performed = request.POST.get("section_3_work_performed", "").strip()
        report.section_4_sensory_interventions = request.POST.get("section_4_sensory_interventions", "").strip()
        report.section_5_child_response = request.POST.get("section_5_child_response", "").strip()
        report.section_6_quantitative_progress = request.POST.get("section_6_quantitative_progress", "").strip()
        report.section_7_functional_changes = request.POST.get("section_7_functional_changes", "").strip()
        report.section_8_challenges = request.POST.get("section_8_challenges", "").strip()
        report.section_9_recommendations = request.POST.get("section_9_recommendations", "").strip()
        report.section_10_next_goals = request.POST.get("section_10_next_goals", "").strip()

        if action == "finalize":
            report.is_finalized = True
            rev_note = "ანგარიშის დამტკიცება და ფინალიზაცია"
            messages.success(request, "ანგარიში ოფიციალურად დამტკიცდა!")
        else:
            report.is_finalized = "is_finalized" in request.POST
            rev_note = "თერაპევტის მიერ რედაქტირებული ვერსიის შენახვა"
            messages.success(request, "ცვლილებები წარმატებით შეინახა.")

        report.save()

        snapshot = {
            "title": report.title,
            "sec1": report.section_1_directions,
            "sec2": report.section_2_goals,
            "sec3": report.section_3_work_performed,
            "sec4": report.section_4_sensory_interventions,
            "sec5": report.section_5_child_response,
            "sec6": report.section_6_quantitative_progress,
            "sec7": report.section_7_functional_changes,
            "sec8": report.section_8_challenges,
            "sec9": report.section_9_recommendations,
            "sec10": report.section_10_next_goals,
            "is_finalized": report.is_finalized,
        }
        ReportRevision.objects.create(
            report=report,
            revised_by=request.user,
            revision_note=rev_note,
            snapshot_data=snapshot
        )

        return redirect("monthly_report_edit", report_id=report.id)

    context = {
        "report": report,
        "revisions": report.revisions.all()[:10],
    }
    return render(request, "core/report_edit.html", context)


@login_required
def monthly_report_view(request, report_id):
    report = get_object_or_404(MonthlyReport, id=report_id)
    if not can_access_beneficiary(request.user, report.beneficiary):
        return HttpResponseForbidden()

    from .pdf import _clean_line, _parse_alert_zone_counts
    beneficiary = report.beneficiary
    therapist = report.therapist
    therapist_name = (
        therapist.user.get_full_name() or therapist.user.username
        if therapist else "—"
    )
    dob_str = str(beneficiary.date_of_birth) if beneficiary.date_of_birth else "—"
    age_str = beneficiary.age_display if hasattr(beneficiary, "age_display") else ""
    total_min = report.sessions_count * 50
    doc_date = report.updated_at.strftime("%d.%m.%Y")
    doc_status = "დამტკიცებული ვერსია" if report.is_finalized else "სამუშაო ვერსია"

    sec1_raw = report.section_1_directions or ""
    alert_zones_dict = _parse_alert_zone_counts(sec1_raw)
    sec1_paragraphs = [
        _clean_line(line) for line in sec1_raw.strip().split("\n")
        if _clean_line(line) and "თვითრეგულაციის საწყისი მდგომარეობა" not in line and "თვითრეგულაციის საბოლოო მდგომარეობა" not in line
    ]

    sec2_raw = report.section_2_goals or ""
    sec2_items = [
        _clean_line(line) for line in sec2_raw.strip().split("\n")
        if _clean_line(line) and not _clean_line(line).startswith("საანგარიშო პერიოდში დამუშავებული")
    ]

    active_goals = beneficiary.goals.filter(status="active")
    goals_ctx = []
    for g in active_goals:
        pct = g.progress_percentage or 0
        unit = g.unit_label or ""
        domain = g.get_domain_display() if hasattr(g, "get_domain_display") else ""
        goals_ctx.append({
            "domain": domain,
            "description": g.description.strip(),
            "baseline": f"{g.baseline_numeric:.0f}",
            "current": f"{g.current_numeric:.0f}",
            "target": f"{g.target_numeric:.0f}",
            "unit": unit,
            "pct": pct,
        })

    sec4_raw = report.section_8_challenges or ""
    sec4_items = [
        _clean_line(line) for line in sec4_raw.strip().split("\n")
        if _clean_line(line) and not _clean_line(line).startswith("სესიების დროს დაფიქსირებული")
        and not _clean_line(line).startswith("თერაპევტის დაკვირვებები")
    ]

    sec5_raw = report.section_9_recommendations or ""
    sec5_items = [
        _clean_line(line) for line in sec5_raw.strip().split("\n")
        if _clean_line(line) and not _clean_line(line).startswith("სესიებზე გამოყენებული")
    ]

    context = {
        "report": report,
        "report_date": doc_date,
        "period_display": report.period_display,
        "beneficiary": beneficiary,
        "beneficiary_name": beneficiary.full_name,
        "dob": dob_str,
        "age": age_str,
        "parent_name": getattr(beneficiary, "parent_name", ""),
        "parent_phone": getattr(beneficiary, "parent_phone", ""),
        "sessions_count": report.sessions_count,
        "total_minutes": total_min,
        "therapist_name": therapist_name,
        "doc_status": doc_status,
        "section1_paragraphs": sec1_paragraphs,
        "alert_zones_dict": alert_zones_dict,
        "section2_items": sec2_items,
        "goals": goals_ctx,
        "section4_items": sec4_items,
        "section5_items": sec5_items,
    }
    return render(request, "core/pdf/report_pdf.html", context)


@login_required
def monthly_report_pdf_view(request, report_id):
    report = get_object_or_404(MonthlyReport, id=report_id)
    if not can_access_beneficiary(request.user, report.beneficiary):
        return HttpResponseForbidden()

    from .pdf import _get_browser_path, generate_report_pdf
    if _get_browser_path():
        try:
            pdf_data = generate_report_pdf(report)
            response = HttpResponse(pdf_data, content_type="application/pdf")
            filename = f"OT_Report_{report.beneficiary.last_name}_{report.year}_{report.month}.pdf"
            disposition = "attachment" if request.GET.get("download") else "inline"
            response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
            return response
        except Exception:
            pass

    from django.urls import reverse
    return redirect(reverse("monthly_report_view", args=[report.id]) + "?autoprint=1")


@login_required
def goal_detail_view(request, goal_id):
    goal = get_object_or_404(Goal, id=goal_id)
    if not can_access_beneficiary(request.user, goal.beneficiary):
        return HttpResponseForbidden("თქვენ არ გაქვთ ამ მიზნის ნახვის უფლება.")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_progress":
            new_val = request.POST.get("current_numeric")
            if new_val is not None and new_val != "":
                try:
                    goal.update_progress(float(new_val))
                    messages.success(request, f"მიზნის პროგრესი წარმატებით განახლდა: {goal.current_numeric}{goal.unit_label} ({goal.progress_percentage}%)")
                except ValueError:
                    messages.error(request, "გთხოვთ შეიყვანოთ სწორი რიცხვითი მაჩვენებელი.")

        elif action == "update_status":
            new_status = request.POST.get("status")
            if new_status in dict(Goal.STATUS_CHOICES):
                goal.status = new_status
                goal.save()
                messages.success(request, f"სტატუსი შეიცვალა: {goal.get_status_display()}")

        elif action == "modify_goal":
            domain = request.POST.get("domain", "").strip()
            if domain and domain in dict(Goal.DOMAIN_CHOICES):
                goal.domain = domain
            goal.occupation = request.POST.get("occupation", "").strip()
            goal.environment_context = request.POST.get("environment_context", "").strip()
            goal.criteria_type = request.POST.get("criteria_type", "").strip()
            try:
                goal.baseline_numeric = float(request.POST.get("baseline_numeric", goal.baseline_numeric))
                goal.target_numeric = float(request.POST.get("target_numeric", goal.target_numeric))
                goal.unit_label = request.POST.get("unit_label", goal.unit_label).strip()
                goal.baseline_state = f"{goal.baseline_numeric}{goal.unit_label}"
                goal.target_state = f"{goal.target_numeric}{goal.unit_label}"
            except ValueError:
                pass
            target_date_str = request.POST.get("target_date", "").strip()
            if target_date_str:
                try:
                    goal.target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
                except ValueError:
                    pass
            goal.progress_percentage = goal.calculate_progress_percentage()
            if goal.progress_percentage >= 100 and goal.status == "active":
                goal.status = "achieved"
            goal.notes = request.POST.get("notes", "").strip()
            goal.description = request.POST.get("description", goal.description).strip()
            goal.save()
            messages.success(request, "მიზნის პარამეტრები წარმატებით მოდიფიცირდა.")

        return redirect("goal_detail", goal_id=goal.id)

    session_goals = SessionGoal.objects.filter(goal=goal).select_related("session").order_by("-session__date")

    context = {
        "goal": goal,
        "beneficiary": goal.beneficiary,
        "session_goals": session_goals,
        "status_choices": Goal.STATUS_CHOICES,
        "domain_choices": Goal.DOMAIN_CHOICES,
    }
    return render(request, "core/goal_detail.html", context)


# ==================== SCHEDULE & TIMETABLE ====================

@login_required
def schedule_view(request):
    user = request.user
    profile = get_or_create_therapist(user)
    today = date.today()
    today_monday = today - timedelta(days=today.weekday())

    # Allow jumping by ?date=YYYY-MM-DD, ?month=YYYY-MM, or ?week_offset=N
    jump_date_str = request.GET.get("date", "").strip()
    jump_month_str = request.GET.get("month", "").strip()
    week_offset = 0

    if jump_date_str:
        try:
            target_d = datetime.strptime(jump_date_str, "%Y-%m-%d").date()
            target_monday = target_d - timedelta(days=target_d.weekday())
            week_offset = (target_monday - today_monday).days // 7
        except ValueError:
            week_offset = 0
    elif jump_month_str:
        try:
            target_d = datetime.strptime(f"{jump_month_str}-01", "%Y-%m-%d").date()
            target_monday = target_d - timedelta(days=target_d.weekday())
            week_offset = (target_monday - today_monday).days // 7
        except ValueError:
            week_offset = 0
    else:
        try:
            week_offset = int(request.GET.get("week_offset", 0))
        except ValueError:
            week_offset = 0

    start_of_week = today_monday + timedelta(weeks=week_offset)
    end_of_week = start_of_week + timedelta(days=5)

    DAYS_GEORGIAN = ["ორშაბათი", "სამშაბათი", "ოთხშაბათი", "ხუთშაბათი", "პარასკევი", "შაბათი"]
    DAYS_SHORT = ["ორშ", "სამ", "ოთხ", "ხუთ", "პარ", "შაბ"]
    MONTH_NAMES = {
        1: "იანვარი", 2: "თებერვალი", 3: "მარტი", 4: "აპრილი",
        5: "მაისი", 6: "ივნისი", 7: "ივლისი", 8: "აგვისტო",
        9: "სექტემბერი", 10: "ოქტომბერი", 11: "ნოემბერი", 12: "დეკემბერი"
    }

    if is_admin_user(user):
        slots = list(
            ScheduleSlot.objects.filter(date__range=[start_of_week, end_of_week])
            .select_related("beneficiary", "therapist")
            .order_by("date", "start_time")
        )
    else:
        slots = list(
            ScheduleSlot.objects.filter(
                Q(therapist=profile) | Q(therapist__isnull=True),
                date__range=[start_of_week, end_of_week]
            )
            .select_related("beneficiary", "therapist")
            .order_by("date", "start_time")
        )

    # Enrich recurring slots with total count and final date of the series
    series_ids = {s.series_id for s in slots if s.series_id}
    series_meta = {}
    if series_ids:
        agg = (
            ScheduleSlot.objects.filter(series_id__in=series_ids)
            .values("series_id")
            .annotate(total_count=Count("id"), max_date=Max("date"))
        )
        for item in agg:
            series_meta[item["series_id"]] = {
                "total": item["total_count"],
                "max_date_str": item["max_date"].strftime("%d.%m.%Y") if item["max_date"] else "",
            }

    for s in slots:
        if s.series_id and s.series_id in series_meta:
            s.series_total = series_meta[s.series_id]["total"]
            s.series_end_str = series_meta[s.series_id]["max_date_str"]
        else:
            s.series_total = 0
            s.series_end_str = ""

    # Build week_days and attach day_slots for mobile agenda view
    week_days = []
    selected_mobile_day_idx = 0
    for i in range(6):
        d = start_of_week + timedelta(days=i)
        day_slots = [s for s in slots if s.date == d]
        is_today_flag = (d == today)
        if is_today_flag:
            selected_mobile_day_idx = i
        week_days.append({
            "index": i,
            "date": d,
            "day_name": DAYS_GEORGIAN[i],
            "day_short": DAYS_SHORT[i],
            "day_num": d.day,
            "month_short": MONTH_NAMES.get(d.month, "")[:3],
            "is_today": is_today_flag,
            "date_str": d.strftime("%Y-%m-%d"),
            "day_slots": day_slots,
            "slots_count": len(day_slots),
        })

    # Dynamic hours range: default 09:00..19:00, expanded if early/late slots exist
    slot_hours = {s.start_time.hour for s in slots}
    min_hour = min([9] + list(slot_hours))
    max_hour = max([18] + list(slot_hours))
    hours_list = [f"{h:02d}:00" for h in range(min_hour, max_hour + 1)]

    timetable_rows = []
    for hour_str in hours_list:
        hour_int = int(hour_str.split(":")[0])
        row_days = []
        for day in week_days:
            day_hour_slots = [
                s for s in day["day_slots"]
                if s.start_time.hour == hour_int
            ]
            row_days.append({
                "day": day,
                "slots": day_hour_slots,
            })
        timetable_rows.append({
            "hour": hour_str,
            "row_days": row_days,
        })

    if start_of_week.month == end_of_week.month:
        period_label = f"{start_of_week.day} — {end_of_week.day} {MONTH_NAMES.get(end_of_week.month, '')}, {end_of_week.year}"
    else:
        period_label = (
            f"{start_of_week.day} {MONTH_NAMES.get(start_of_week.month, '')} — "
            f"{end_of_week.day} {MONTH_NAMES.get(end_of_week.month, '')}, {end_of_week.year}"
        )

    # Build quick month navigation pills (-1 month to +6 months from today)
    viewed_month_anchor = start_of_week + timedelta(days=2)  # Wednesday determines primary month of the week
    quick_months = []
    first_of_current = date(today.year, today.month, 1)
    for m_delta in range(-1, 7):
        m_date = add_calendar_months(first_of_current, m_delta)
        m_name = MONTH_NAMES.get(m_date.month, "")
        label = f"{m_name}" if m_date.year == today.year else f"{m_name} '{str(m_date.year)[2:]}"
        quick_months.append({
            "ym": m_date.strftime("%Y-%m"),
            "label": label,
            "is_active": (m_date.year == viewed_month_anchor.year and m_date.month == viewed_month_anchor.month),
        })

    beneficiaries = get_user_beneficiaries(user).filter(is_active=True)

    context = {
        "week_days": week_days,
        "timetable_rows": timetable_rows,
        "period_label": period_label,
        "week_offset": week_offset,
        "prev_offset": week_offset - 1,
        "next_offset": week_offset + 1,
        "prev_month_offset": week_offset - 4,
        "next_month_offset": week_offset + 4,
        "quick_months": quick_months,
        "viewed_month_ym": viewed_month_anchor.strftime("%Y-%m"),
        "start_of_week_str": start_of_week.strftime("%Y-%m-%d"),
        "selected_mobile_day_idx": selected_mobile_day_idx,
        "week_total_slots": len(slots),
        "beneficiaries": beneficiaries,
        "today_str": today.strftime("%Y-%m-%d"),
        "therapy_types": [t[0] for t in ScheduleSlot.THERAPY_TYPES],
    }
    return render(request, "core/schedule.html", context)


@login_required
def schedule_add_view(request):
    if request.method == "POST":
        beneficiary_id = request.POST.get("beneficiary")
        beneficiary = get_object_or_404(Beneficiary, id=beneficiary_id)
        if not can_access_beneficiary(request.user, beneficiary):
            return HttpResponseForbidden()

        profile = get_or_create_therapist(request.user)
        date_str = request.POST.get("date", date.today().isoformat())
        try:
            slot_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            slot_date = date.today()

        time_str = request.POST.get("start_time", "10:00")
        try:
            start_time = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            start_time = time(10, 0)

        try:
            duration = int(request.POST.get("duration_minutes", 50) or 50)
        except ValueError:
            duration = 50

        therapy_type = request.POST.get("therapy_type", "ოკუპაციური თერაპია")
        notes = request.POST.get("notes", "").strip()

        # Flexible multi-month / multi-week / end-date recurrence + multi-weekday support
        recurrence_mode = request.POST.get("recurrence_mode", "").strip()
        legacy_recurring = request.POST.get("is_recurring") == "on"
        if not recurrence_mode:
            recurrence_mode = "months" if legacy_recurring else "single"

        raw_weekdays = request.POST.getlist("weekdays")
        selected_weekdays = set()
        for w_str in raw_weekdays:
            try:
                w_int = int(w_str)
                if 0 <= w_int <= 5:
                    selected_weekdays.add(w_int)
            except ValueError:
                pass
        if not selected_weekdays:
            selected_weekdays.add(slot_date.weekday() if slot_date.weekday() <= 5 else 0)

        # Determine end_date for slot generation
        if recurrence_mode == "single":
            if len(selected_weekdays) <= 1 and slot_date.weekday() in selected_weekdays:
                target_dates = [slot_date]
            else:
                # Multiple weekdays chosen for a single week
                week_monday = slot_date - timedelta(days=slot_date.weekday())
                target_dates = [
                    week_monday + timedelta(days=wd)
                    for wd in sorted(selected_weekdays)
                    if (week_monday + timedelta(days=wd)) >= slot_date
                ]
                if not target_dates:
                    target_dates = [slot_date]
        else:
            if recurrence_mode == "months":
                try:
                    repeat_months = int(request.POST.get("repeat_months", 1) or 1)
                except ValueError:
                    repeat_months = 1
                repeat_months = max(1, min(24, repeat_months))
                end_date = add_calendar_months(slot_date, repeat_months) - timedelta(days=1)
            elif recurrence_mode == "weeks":
                try:
                    repeat_weeks = int(request.POST.get("repeat_weeks", 4) or 4)
                except ValueError:
                    repeat_weeks = 4
                repeat_weeks = max(1, min(104, repeat_weeks))
                end_date = slot_date + timedelta(weeks=repeat_weeks) - timedelta(days=1)
            elif recurrence_mode == "until_date":
                until_str = request.POST.get("repeat_until", "").strip()
                try:
                    end_date = datetime.strptime(until_str, "%Y-%m-%d").date()
                except ValueError:
                    end_date = add_calendar_months(slot_date, 1) - timedelta(days=1)
                if end_date < slot_date:
                    end_date = slot_date
                # Cap at 2 years max safety
                max_allowed = add_calendar_months(slot_date, 24)
                if end_date > max_allowed:
                    end_date = max_allowed
            else:
                end_date = add_calendar_months(slot_date, 1) - timedelta(days=1)

            target_dates = []
            curr_d = slot_date
            while curr_d <= end_date:
                if curr_d.weekday() in selected_weekdays:
                    target_dates.append(curr_d)
                curr_d += timedelta(days=1)

            if not target_dates:
                target_dates = [slot_date]

        series_id = uuid.uuid4() if len(target_dates) > 1 else None
        created_count = 0

        for d_item in target_dates:
            ScheduleSlot.objects.create(
                therapist=profile,
                beneficiary=beneficiary,
                date=d_item,
                start_time=start_time,
                duration_minutes=duration,
                therapy_type=therapy_type,
                notes=notes,
                status="scheduled",
                series_id=series_id,
            )
            created_count += 1

        if created_count > 1:
            last_d_str = target_dates[-1].strftime("%d.%m.%Y")
            messages.success(
                request,
                f"განრიგში წარმატებით ჩაინიშნა {created_count} ვიზიტი ({beneficiary.full_name}, {start_time.strftime('%H:%M')}, {last_d_str}-მდე)."
            )
        else:
            messages.success(
                request,
                f"ვიზიტი ({beneficiary.full_name}, {slot_date.strftime('%d.%m.%Y')} {start_time.strftime('%H:%M')}) წარმატებით ჩაინიშნა."
            )

        next_url = request.POST.get("next")
        if next_url:
            return redirect(next_url)
        from django.urls import reverse
        return redirect(f"{reverse('schedule')}?date={slot_date.isoformat()}")

    return redirect("schedule")


@login_required
def schedule_edit_view(request, slot_id):
    slot = get_object_or_404(ScheduleSlot, id=slot_id)
    if not can_access_beneficiary(request.user, slot.beneficiary):
        return HttpResponseForbidden()

    if request.method == "POST":
        beneficiary_id = request.POST.get("beneficiary")
        beneficiary = get_object_or_404(Beneficiary, id=beneficiary_id)
        if not can_access_beneficiary(request.user, beneficiary):
            return HttpResponseForbidden()

        date_str = request.POST.get("date")
        if date_str:
            try:
                slot.date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        time_str = request.POST.get("start_time")
        if time_str:
            try:
                slot.start_time = datetime.strptime(time_str, "%H:%M").time()
            except ValueError:
                pass

        try:
            slot.duration_minutes = int(request.POST.get("duration_minutes", 50) or 50)
        except (ValueError, TypeError):
            slot.duration_minutes = 50

        dummy_dt = datetime.combine(datetime.today(), slot.start_time) + timedelta(minutes=slot.duration_minutes)
        slot.end_time = dummy_dt.time()

        slot.beneficiary = beneficiary
        slot.therapy_type = request.POST.get("therapy_type", slot.therapy_type)
        slot.notes = request.POST.get("notes", "").strip()
        slot.save()

        update_series = request.POST.get("update_series") == "on"
        if update_series and slot.series_id:
            future_slots = ScheduleSlot.objects.filter(
                series_id=slot.series_id,
                date__gt=slot.date
            )
            for f_slot in future_slots:
                f_slot.start_time = slot.start_time
                f_slot.duration_minutes = slot.duration_minutes
                f_slot.end_time = slot.end_time
                f_slot.beneficiary = slot.beneficiary
                f_slot.therapy_type = slot.therapy_type
                f_slot.notes = slot.notes
                f_slot.save()

        messages.success(request, "ვიზიტის მონაცემები წარმატებით განახლდა.")

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "schedule"
    return redirect(next_url)


@login_required
def schedule_status_view(request, slot_id):
    slot = get_object_or_404(ScheduleSlot, id=slot_id)
    if not can_access_beneficiary(request.user, slot.beneficiary):
        return HttpResponseForbidden()

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in ["scheduled", "completed", "missed"]:
            slot.status = new_status
            slot.save()
            messages.success(request, "სტატუსი განახლდა.")

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "schedule"
    return redirect(next_url)


@login_required
def schedule_delete_view(request, slot_id):
    slot = get_object_or_404(ScheduleSlot, id=slot_id)
    if not can_access_beneficiary(request.user, slot.beneficiary):
        return HttpResponseForbidden()

    if request.method == "POST":
        delete_mode = request.POST.get("delete_mode", "single")
        if delete_mode == "series" and slot.series_id:
            deleted_count, _ = ScheduleSlot.objects.filter(
                series_id=slot.series_id,
                date__gte=slot.date
            ).delete()
            messages.success(request, f"სერიის {deleted_count} ვიზიტი წარმატებით წაიშალა.")
        else:
            slot.delete()
            messages.success(request, "ვიზიტი წაიშალა განრიგიდან.")

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "schedule"
    return redirect(next_url)
