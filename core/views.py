import json
from datetime import date, datetime
from collections import Counter
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.db.models import Count, Q

from .models import (
    TherapistProfile, Beneficiary, OccupationalProfile, SensoryProfile,
    Goal, SensorySystem, SensoryActivity, SensoryResponse, FunctionalOutcome,
    Session, SessionGoal, SessionSensoryActivity, MonthlyReport, ReportRevision
)
from .reports import generate_monthly_report_content
from .pdf import generate_report_pdf


def get_user_beneficiaries(user):
    """Filter beneficiaries based on user role"""
    if user.is_superuser:
        return Beneficiary.objects.all()
    try:
        profile = user.therapist_profile
        if profile.is_admin_role:
            return Beneficiary.objects.all()
        return Beneficiary.objects.filter(therapist=profile)
    except TherapistProfile.DoesNotExist:
        return Beneficiary.objects.none()


def can_access_beneficiary(user, beneficiary):
    if user.is_superuser:
        return True
    try:
        profile = user.therapist_profile
        if profile.is_admin_role or beneficiary.therapist == profile:
            return True
    except TherapistProfile.DoesNotExist:
        pass
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

    context = {
        "beneficiary_cards": beneficiary_cards,
        "beneficiaries_total": beneficiaries.count(),
        "today_sessions_count": today_sessions.count(),
        "today_sessions": today_sessions,
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

    if therapist_id and request.user.is_superuser:
        beneficiaries = beneficiaries.filter(therapist_id=therapist_id)

    all_therapists = TherapistProfile.objects.all() if request.user.is_superuser else None

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
        session_duration = int(request.POST.get("session_duration_minutes", 45) or 45)
        weekly_sessions = int(request.POST.get("weekly_sessions_planned", 2) or 2)
        notes = request.POST.get("notes", "").strip()

        # Assigned therapist
        therapist_id = request.POST.get("therapist")
        assigned_therapist = None
        if therapist_id and (request.user.is_superuser or request.user.therapist_profile.is_admin_role):
            assigned_therapist = TherapistProfile.objects.filter(id=therapist_id).first()
        else:
            try:
                assigned_therapist = request.user.therapist_profile
            except TherapistProfile.DoesNotExist:
                pass

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

    is_admin = request.user.is_superuser or (
        hasattr(request.user, "therapist_profile") and request.user.therapist_profile.is_admin_role
    )
    therapists = TherapistProfile.objects.all() if is_admin else None
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

            therapist = request.user.therapist_profile if hasattr(request.user, "therapist_profile") else None
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

            messages.success(request, f"ახალი გაზომვადი SMART მიზანი წარმატებით დაემატა!")
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

    if request.method == "POST":
        beneficiary.first_name = request.POST.get("first_name", "").strip()
        beneficiary.last_name = request.POST.get("last_name", "").strip()
        dob_str = request.POST.get("date_of_birth", "").strip()
        start_date_str = request.POST.get("start_date", "").strip()
        beneficiary.session_duration_minutes = int(request.POST.get("session_duration_minutes", 45) or 45)
        beneficiary.weekly_sessions_planned = int(request.POST.get("weekly_sessions_planned", 2) or 2)
        beneficiary.notes = request.POST.get("notes", "").strip()
        beneficiary.is_active = "is_active" in request.POST

        if dob_str:
            beneficiary.date_of_birth = datetime.strptime(dob_str, "%Y-%m-%d").date()
        if start_date_str:
            beneficiary.start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()

        if request.user.is_superuser or request.user.therapist_profile.is_admin_role:
            t_id = request.POST.get("therapist")
            beneficiary.therapist = TherapistProfile.objects.filter(id=t_id).first() if t_id else None

        beneficiary.save()
        messages.success(request, "მონაცემები განახლდა.")
        return redirect("beneficiary_detail", beneficiary_id=beneficiary.id)

    therapists = TherapistProfile.objects.all() if (request.user.is_superuser or request.user.therapist_profile.is_admin_role) else None
    return render(request, "core/beneficiary_form.html", {
        "beneficiary": beneficiary,
        "therapists": therapists,
        "is_create": False,
        "today_date": date.today().isoformat(),
    })


# ==================== RAPID SESSION RECORDING (30-60 SEC) ====================

@login_required
def session_create_view(request, beneficiary_id=None):
    beneficiaries = get_user_beneficiaries(request.user).filter(is_active=True)
    selected_beneficiary = None
    if beneficiary_id:
        selected_beneficiary = get_object_or_404(beneficiaries, id=beneficiary_id)
    elif beneficiaries.exists():
        selected_beneficiary = beneficiaries.first()

    if request.method == "POST":
        target_b_id = request.POST.get("beneficiary")
        target_beneficiary = get_object_or_404(beneficiaries, id=target_b_id)

        session_date_str = request.POST.get("date", date.today().isoformat())
        session_date = datetime.strptime(session_date_str, "%Y-%m-%d").date()
        duration = int(request.POST.get("duration_minutes", 50) or 50)
        initial_state = request.POST.get("initial_state", "green")
        final_state = request.POST.get("final_state", "green")
        challenges = request.POST.getlist("challenges")
        notes = request.POST.get("notes", "").strip()

        therapist = request.user.therapist_profile if hasattr(request.user, "therapist_profile") else None

        # 1. Create Session
        session = Session.objects.create(
            beneficiary=target_beneficiary,
            therapist=therapist,
            date=session_date,
            duration_minutes=duration,
            initial_state=initial_state,
            final_state=final_state,
            challenges=challenges,
            notes=notes
        )

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

        # 3. Add Sensory Activities with Assistance Levels & Optional Responses
        activity_ids = request.POST.getlist("activities")
        for aid in activity_ids:
            act_obj = SensoryActivity.objects.filter(id=aid).first()
            if not act_obj:
                continue
            assistance = request.POST.get(f"act_assistance_{aid}", "verbal")
            sa = SessionSensoryActivity.objects.create(
                session=session,
                sensory_activity=act_obj,
                duration_minutes=duration,
                assistance_level=assistance,
            )

            resp_id = request.POST.get(f"act_response_{aid}")
            if resp_id:
                r_obj = SensoryResponse.objects.filter(id=resp_id).first()
                if r_obj:
                    sa.responses.add(r_obj)

        messages.success(request, f"სესია ({target_beneficiary.full_name}, {session.date}) წარმატებით დაფიქსირდა!")
        return redirect("session_detail", session_id=session.id)

    # 3 Sensory Categories
    movement_systems = SensorySystem.objects.filter(category="movement").prefetch_related("activities").order_by("order")
    tactile_systems = SensorySystem.objects.filter(category="tactile_sensory").prefetch_related("activities").order_by("order")
    environment_systems = SensorySystem.objects.filter(category="environment").prefetch_related("activities").order_by("order")

    context = {
        "beneficiaries": beneficiaries,
        "selected_beneficiary": selected_beneficiary,
        "movement_systems": movement_systems,
        "tactile_systems": tactile_systems,
        "environment_systems": environment_systems,
        "initial_state_choices": Session.INITIAL_STATE_CHOICES,
        "final_state_choices": Session.FINAL_STATE_CHOICES,
        "today_date": date.today().isoformat(),
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

    # 4. Assistance level over time
    assist_weights = {
        "full": 1,
        "maximal": 2,
        "moderate": 3,
        "minimal": 4,
        "verbal": 5,
        "independent": 6
    }
    assist_labels_map = {
        "full": "სრული",
        "maximal": "დიდი",
        "moderate": "საშუალო",
        "minimal": "მცირე",
        "verbal": "სიტყვიერი",
        "independent": "დამოუკიდებელი"
    }

    timeline_dates = []
    timeline_durations = []
    timeline_assist = []

    for s in sessions:
        timeline_dates.append(s.date.strftime("%d.%m"))
        # average activity duration in that session
        acts = s.sensory_activities.all()
        avg_act_dur = round(sum(a.duration_minutes for a in acts) / len(acts), 1) if acts else 0
        timeline_durations.append(avg_act_dur)

        # average assistance score
        avg_assist = round(sum(assist_weights.get(a.assistance_level, 3) for a in acts) / len(acts), 1) if acts else 3
        timeline_assist.append(avg_assist)

    # Convert to JSON for Chart.js
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

        # Check existing
        existing_report = MonthlyReport.objects.filter(beneficiary=beneficiary, year=year, month=month).first()
        if existing_report:
            messages.info(request, f"{year} წლის {existing_report.month_display}-ის ანგარიში უკვე არსებობს. გადამისამართება რედაქტორზე.")
            return redirect("monthly_report_edit", report_id=existing_report.id)

        # Generate fresh content from sessions
        content = generate_monthly_report_content(beneficiary, year, month)
        therapist = request.user.therapist_profile if hasattr(request.user, "therapist_profile") else beneficiary.therapist

        report = MonthlyReport.objects.create(
            beneficiary=beneficiary,
            therapist=therapist,
            year=year,
            month=month,
            **content
        )

        # Create initial revision
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
            # Re-aggregate from current sessions data
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

        # Save edits
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

        # Track revision snapshot
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
    """
    Direct interactive web presentation of the clinical report matching
    the Stitch template. Users can view, zoom, and print directly via browser (window.print()).
    """
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

    pdf_data = generate_report_pdf(report)
    response = HttpResponse(pdf_data, content_type="application/pdf")
    filename = f"OT_Report_{report.beneficiary.last_name}_{report.year}_{report.month}.pdf"
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return response


@login_required
def goal_detail_view(request, goal_id):
    """
    Dedicated interactive workspace for a single SMART Goal:
    - Live progress bar & metric gauges
    - Chronological history of sessions addressing this goal
    - Manual progress update, status change, and modification
    """
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
            goal.occupation = request.POST.get("occupation", "").strip()
            goal.environment_context = request.POST.get("environment_context", "").strip()
            goal.criteria_type = request.POST.get("criteria_type", "").strip()
            try:
                goal.baseline_numeric = float(request.POST.get("baseline_numeric", goal.baseline_numeric))
                goal.target_numeric = float(request.POST.get("target_numeric", goal.target_numeric))
                goal.unit_label = request.POST.get("unit_label", goal.unit_label).strip()
            except ValueError:
                pass
            goal.progress_percentage = goal.calculate_progress_percentage()
            goal.notes = request.POST.get("notes", "").strip()
            goal.description = request.POST.get("description", goal.description).strip()
            goal.save()
            messages.success(request, "მიზნის პარამეტრები წარმატებით მოდიფიცირდა.")

        return redirect("goal_detail", goal_id=goal.id)

    # Session history for this goal
    session_goals = SessionGoal.objects.filter(goal=goal).select_related("session").order_by("-session__date")

    context = {
        "goal": goal,
        "beneficiary": goal.beneficiary,
        "session_goals": session_goals,
        "status_choices": Goal.STATUS_CHOICES,
    }
    return render(request, "core/goal_detail.html", context)


