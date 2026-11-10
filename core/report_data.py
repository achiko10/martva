"""
Structured clinical aggregation for monthly OT reports.

Builds a rich, checklist-driven data model directly from the month's session
records (smart evaluation parameters, prompt hierarchy, regulation zones,
goal measurements, outcomes, challenges) so that both the auto-generated
report text and the printable PDF reflect the full clinical picture.
"""
import re
from collections import Counter, defaultdict

from django.db.models import Prefetch

from .models import (
    Session, SessionGoal, SessionSensoryActivity, ScheduleSlot, MonthlyReport, Goal
)


ZONE_META = {
    "green": {
        "label": "მწვანე ზონა", "sub": "ოპტიმალური / რეგულირებული", "score": 0,
        "dot": "bg-emerald-500", "bar": "bg-emerald-500", "border": "border-emerald-200",
        "text": "text-emerald-800", "soft": "bg-emerald-50",
    },
    "yellow": {
        "label": "ყვითელი ზონა", "sub": "მომატებული აგზნებადობა", "score": 1,
        "dot": "bg-amber-500", "bar": "bg-amber-500", "border": "border-amber-200",
        "text": "text-amber-800", "soft": "bg-amber-50",
    },
    "blue": {
        "label": "ლურჯი ზონა", "sub": "დაქვეითებული / ჰიპოაქტიური", "score": 1,
        "dot": "bg-blue-500", "bar": "bg-blue-500", "border": "border-blue-200",
        "text": "text-blue-800", "soft": "bg-blue-50",
    },
    "red": {
        "label": "წითელი ზონა", "sub": "დისრეგულაცია / დისტრესი", "score": 2,
        "dot": "bg-rose-500", "bar": "bg-rose-500", "border": "border-rose-200",
        "text": "text-rose-800", "soft": "bg-rose-50",
    },
}
ZONE_ORDER = ["green", "yellow", "blue", "red"]

# OT Prompt Hierarchy → independence index (1 = full assistance … 6 = independent)
ASSIST_WEIGHTS = {
    "full": 1.0,
    "maximal": 2.0,
    "moderate": 3.0,
    "minimal": 4.0,
    "gestural_modeling": 4.5,
    "verbal": 5.0,
    "environmental": 5.5,
    "independent": 6.0,
}
ASSIST_ORDER = [
    "independent", "environmental", "verbal", "gestural_modeling",
    "minimal", "moderate", "maximal", "full",
]
ASSIST_BAR = {
    "independent": "bg-emerald-600",
    "environmental": "bg-teal-500",
    "verbal": "bg-sky-500",
    "gestural_modeling": "bg-indigo-500",
    "minimal": "bg-amber-400",
    "moderate": "bg-amber-600",
    "maximal": "bg-rose-500",
    "full": "bg-rose-700",
}
ASSIST_LABELS = dict(SessionSensoryActivity.ASSISTANCE_CHOICES)


def independence_label(value):
    if value is None:
        return "—"
    if value >= 5.75:
        return "დამოუკიდებელი შესრულება"
    if value >= 4.75:
        return "მინიშნების დონე (ვერბალური/ვიზუალური)"
    if value >= 3.75:
        return "მცირე ფიზიკური დახმარება"
    if value >= 2.75:
        return "ნაწილობრივი ფიზიკური დახმარება"
    if value >= 1.75:
        return "დიდი ფიზიკური დახმარება"
    return "სრული ფიზიკური მართვა"


def _avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def _pct(part, total):
    return int(round(part * 100.0 / total)) if total else 0


def clean_line(line):
    """Strip leading bullet symbols, asterisks, or dashes."""
    line = (line or "").strip()
    return re.sub(r"^[\s•\*\-\–\—\>]+", "", line).strip()


def text_to_paragraphs(text, skip_prefixes=()):
    items = []
    for raw in (text or "").split("\n"):
        line = clean_line(raw)
        if not line:
            continue
        if any(line.startswith(p) for p in skip_prefixes):
            continue
        items.append(line)
    return items


def _fmt_num(v):
    if v is None:
        return "—"
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


def aggregate_month(beneficiary, year, month):
    """Collects all checklist data for one beneficiary and month."""
    sessions = list(
        Session.objects.filter(beneficiary=beneficiary, date__year=year, date__month=month)
        .order_by("date", "created_at")
        .prefetch_related(
            "functional_outcomes",
            Prefetch(
                "sensory_activities",
                queryset=SessionSensoryActivity.objects.select_related(
                    "sensory_activity__sensory_system"
                ).prefetch_related("responses"),
            ),
        )
    )
    n = len(sessions)
    month_name = MonthlyReport.MONTH_NAMES.get(month, str(month))

    # ── Attendance & schedule ───────────────────────────────────────────
    total_minutes = sum(s.duration_minutes or 0 for s in sessions)
    slots = ScheduleSlot.objects.filter(beneficiary=beneficiary, date__year=year, date__month=month)
    slot_status = Counter(slots.values_list("status", flat=True))
    completed_slots = slot_status.get("completed", 0)
    missed_slots = slot_status.get("missed", 0)
    planned_slots = sum(slot_status.values())
    attendance_rate = (
        _pct(completed_slots, completed_slots + missed_slots)
        if (completed_slots + missed_slots) else None
    )

    # ── Regulation zones & entry adaptation ─────────────────────────────
    init_counter = Counter(s.initial_state for s in sessions)
    final_counter = Counter(s.final_state for s in sessions)
    improved = stable_optimal = worsened = unchanged = 0
    for s in sessions:
        i_score = ZONE_META.get(s.initial_state, {}).get("score", 1)
        f_score = ZONE_META.get(s.final_state, {}).get("score", 1)
        if f_score < i_score:
            improved += 1
        elif f_score > i_score:
            worsened += 1
        elif s.initial_state == "green" and s.final_state == "green":
            stable_optimal += 1
        else:
            unchanged += 1

    zones = []
    for key in ZONE_ORDER:
        meta = ZONE_META[key]
        zones.append({
            "key": key, **meta,
            "init": init_counter.get(key, 0),
            "final": final_counter.get(key, 0),
            "init_pct": _pct(init_counter.get(key, 0), n),
            "final_pct": _pct(final_counter.get(key, 0), n),
        })

    entry_labels = dict(Session.ENTRY_ADAPTATION_CHOICES)
    entry_counter = Counter(s.entry_adaptation for s in sessions if s.entry_adaptation)
    entry_rows = [
        {"label": entry_labels.get(k, k), "count": c, "pct": _pct(c, n), "positive": k == "calm_organized"}
        for k, c in entry_counter.most_common()
    ]

    # ── Domains, activities, smart evaluation, assistance ───────────────
    domains = {}
    assist_counter = Counter()
    responses_counter = Counter()
    session_index = []
    for s in sessions:
        s_scores = []
        for sa in s.sensory_activities.all():
            sys_obj = sa.sensory_activity.sensory_system
            d = domains.setdefault(sys_obj.id, {
                "id": sys_obj.id,
                "name": sys_obj.name,
                "icon": sys_obj.icon or "🔹",
                "slug": sys_obj.slug,
                "order": sys_obj.order,
                "count": 0,
                "minutes": 0,
                "session_ids": set(),
                "acts": Counter(),
                "act_minutes": Counter(),
                "evals": defaultdict(Counter),
                "assist": Counter(),
                "scores": [],
                "responses": Counter(),
                "notes": [],
            })
            d["count"] += 1
            d["minutes"] += sa.duration_minutes or 0
            d["session_ids"].add(s.id)
            d["acts"][sa.sensory_activity.name] += 1
            d["act_minutes"][sa.sensory_activity.name] += sa.duration_minutes or 0
            for label, val in sa.smart_badges:
                d["evals"][label][val] += 1
            d["assist"][sa.assistance_level] += 1
            score = ASSIST_WEIGHTS.get(sa.assistance_level)
            if score is not None:
                d["scores"].append(score)
                s_scores.append(score)
            assist_counter[sa.assistance_level] += 1
            for r in sa.responses.all():
                d["responses"][r.name] += 1
                responses_counter[r.name] += 1
            if sa.notes and sa.notes.strip() and len(d["notes"]) < 4:
                d["notes"].append(f"{s.date.strftime('%d.%m')} — {sa.sensory_activity.name}: {sa.notes.strip()}")
        session_index.append({
            "date": s.date,
            "value": _avg(s_scores),
        })

    domain_list = []
    total_interventions = sum(d["count"] for d in domains.values())
    for d in sorted(domains.values(), key=lambda x: (x["order"], x["name"])):
        avg_idx = _avg(d["scores"])
        dominant_assist = d["assist"].most_common(1)[0][0] if d["assist"] else None
        domain_list.append({
            "id": d["id"],
            "name": d["name"],
            "icon": d["icon"],
            "slug": d["slug"],
            "count": d["count"],
            "minutes": d["minutes"],
            "sessions": len(d["session_ids"]),
            "share_pct": _pct(d["count"], total_interventions),
            "activities": [
                {"name": name, "count": c, "minutes": d["act_minutes"][name]}
                for name, c in d["acts"].most_common()
            ],
            "evals": [
                {
                    "label": label,
                    "values": [
                        {"value": v, "count": c, "pct": _pct(c, sum(counter.values()))}
                        for v, c in counter.most_common(4)
                    ],
                }
                for label, counter in d["evals"].items()
            ],
            "assist": [
                {"key": k, "label": ASSIST_LABELS.get(k, k), "count": c,
                 "pct": _pct(c, d["count"]), "bar": ASSIST_BAR.get(k, "bg-slate-400")}
                for k, c in sorted(d["assist"].items(), key=lambda kv: ASSIST_ORDER.index(kv[0]) if kv[0] in ASSIST_ORDER else 99)
            ],
            "dominant_assist": ASSIST_LABELS.get(dominant_assist, "—") if dominant_assist else "—",
            "index": avg_idx,
            "index_label": independence_label(avg_idx),
            "index_pct": _pct((avg_idx or 1) - 1, 5) if avg_idx else 0,
            "responses": [{"name": r, "count": c} for r, c in d["responses"].most_common(5)],
            "notes": d["notes"],
        })

    total_assist = sum(assist_counter.values())
    assist_rows = [
        {
            "key": k,
            "label": ASSIST_LABELS.get(k, k),
            "count": assist_counter.get(k, 0),
            "pct": _pct(assist_counter.get(k, 0), total_assist),
            "bar": ASSIST_BAR.get(k, "bg-slate-400"),
            "level": 6 - i if i < 6 else 0,
        }
        for i, k in enumerate(ASSIST_ORDER)
        if assist_counter.get(k, 0) > 0
    ]

    # Independence trend: first half vs second half of the month
    valid_idx = [x["value"] for x in session_index if x["value"] is not None]
    overall_index = _avg(valid_idx)
    first_half_idx = second_half_idx = index_delta = None
    if len(valid_idx) >= 2:
        half = len(valid_idx) // 2
        first_half_idx = _avg(valid_idx[:half])
        second_half_idx = _avg(valid_idx[half:])
        index_delta = round(second_half_idx - first_half_idx, 2)
    for x in session_index:
        x["pct"] = _pct((x["value"] or 1) - 1, 5) if x["value"] else 0
        x["label"] = independence_label(x["value"])

    # ── Goals ───────────────────────────────────────────────────────────
    month_goal_records = (
        SessionGoal.objects.filter(session__in=[s.id for s in sessions])
        .select_related("goal", "session")
        .order_by("session__date", "session__created_at")
    )
    goal_records = defaultdict(list)
    for sg in month_goal_records:
        goal_records[sg.goal_id].append(sg)

    goal_ids = set(goal_records.keys()) | set(
        beneficiary.goals.filter(status="active").values_list("id", flat=True)
    )
    goals = []
    for g in Goal.objects.filter(id__in=goal_ids).order_by("domain", "id"):
        recs = goal_records.get(g.id, [])
        values = [r.recorded_numeric for r in recs if r.recorded_numeric is not None]
        month_start = values[0] if values else None
        month_end = values[-1] if values else None
        ref_min = min([g.baseline_numeric] + values) if values else g.baseline_numeric
        span = (g.target_numeric - ref_min) if g.target_numeric != ref_min else 0
        spark = []
        for r in recs:
            if r.recorded_numeric is None:
                continue
            if span:
                h = (r.recorded_numeric - ref_min) / span * 100
            else:
                h = 100 if r.recorded_numeric >= g.target_numeric else 10
            spark.append({
                "h": max(6, min(100, int(round(h)))),
                "value": _fmt_num(r.recorded_numeric),
                "date": r.session.date.strftime("%d.%m"),
            })
        prompts = Counter(r.prompt_level for r in recs if r.prompt_level)
        month_delta = (month_end - month_start) if (month_start is not None and month_end is not None) else None
        pct = g.progress_percentage or 0
        goals.append({
            "id": g.id,
            "domain": g.get_domain_display(),
            "description": g.description.strip(),
            "status": g.get_status_display(),
            "status_key": g.status,
            "unit": g.unit_label or "",
            "baseline": _fmt_num(g.baseline_numeric),
            "current": _fmt_num(g.current_numeric),
            "target": _fmt_num(g.target_numeric),
            "month_start": _fmt_num(month_start),
            "month_end": _fmt_num(month_end),
            "month_delta": month_delta,
            "month_delta_str": (("+" if month_delta > 0 else "") + _fmt_num(month_delta)) if month_delta is not None else "—",
            "sessions_worked": len(recs),
            "spark": spark,
            "prompt": prompts.most_common(1)[0][0] if prompts else "",
            "pct": pct,
            "target_date": g.target_date.strftime("%d.%m.%Y") if g.target_date else "",
            "tone": "emerald" if pct >= 70 else ("amber" if pct >= 30 else "rose"),
        })

    # ── Outcomes, challenges, notes ─────────────────────────────────────
    outcomes_counter = Counter()
    challenges_counter = Counter()
    for s in sessions:
        for fo in s.functional_outcomes.all():
            outcomes_counter[fo.name] += 1
        for ch in (s.challenges or []):
            challenges_counter[ch] += 1
    outcome_rows = [{"name": k, "count": c, "pct": _pct(c, n)} for k, c in outcomes_counter.most_common()]
    challenge_rows = [{"name": k, "count": c, "pct": _pct(c, n)} for k, c in challenges_counter.most_common()]

    # ── Session journal ─────────────────────────────────────────────────
    session_log = []
    for s, idx in zip(sessions, session_index):
        acts = list(s.sensory_activities.all())
        session_log.append({
            "date": s.date.strftime("%d.%m.%Y"),
            "duration": s.duration_minutes,
            "init": ZONE_META.get(s.initial_state, {}),
            "final": ZONE_META.get(s.final_state, {}),
            "activities_count": len(acts),
            "domains": sorted({a.sensory_activity.sensory_system.icon or "🔹" for a in acts}),
            "index": idx["value"],
            "index_label": independence_label(idx["value"]),
            "outcomes_count": s.functional_outcomes.count(),
            "challenges_count": len(s.challenges or []),
            "note": (s.notes.strip()[:220] + "…") if s.notes and len(s.notes.strip()) > 220 else (s.notes or "").strip(),
        })

    # ── Key clinical findings ───────────────────────────────────────────
    findings = []
    if n:
        findings.append(
            f"ჩატარდა {n} სესია (ჯამში {total_minutes} წთ)"
            + (f"; დასწრების მაჩვენებელი — {attendance_rate}%." if attendance_rate is not None else ".")
        )
        if improved or stable_optimal:
            findings.append(
                f"სესიის განმავლობაში რეგულაცია გაუმჯობესდა {improved} სესიაზე, "
                f"ოპტიმალური (მწვანე) ზონა შენარჩუნდა {stable_optimal} სესიაზე"
                + (f", გაუარესდა {worsened} სესიაზე." if worsened else ".")
            )
        if domain_list:
            top = max(domain_list, key=lambda d: d["count"])
            findings.append(
                f"ყველაზე ინტენსიურად დამუშავდა მიმართულება: {top['name']} "
                f"({top['count']} ინტერვენცია, {top['minutes']} წთ)."
            )
        if overall_index is not None:
            trend_txt = ""
            if index_delta is not None:
                if index_delta >= 0.25:
                    trend_txt = f"; თვის მეორე ნახევარში დამოუკიდებლობა გაიზარდა (+{index_delta:.2f})"
                elif index_delta <= -0.25:
                    trend_txt = f"; თვის მეორე ნახევარში დახმარების საჭიროება გაიზარდა ({index_delta:.2f})"
                else:
                    trend_txt = "; დახმარების დონე სტაბილური დარჩა"
            findings.append(
                f"დამოუკიდებლობის საშუალო ინდექსი: {overall_index:.2f} / 6 — {independence_label(overall_index)}{trend_txt}."
            )
        progressed = [g for g in goals if g["month_delta"] is not None and g["month_delta"] > 0]
        achieved = [g for g in goals if g["pct"] >= 100]
        if goals:
            findings.append(
                f"SMART მიზნები: თვის განმავლობაში პროგრესი დაფიქსირდა {len(progressed)} მიზანზე"
                + (f", სამიზნე მიღწეულია {len(achieved)} მიზანზე." if achieved else ".")
            )
        if outcome_rows:
            findings.append(f"ყველაზე ხშირი ადაპტური შედეგი: „{outcome_rows[0]['name']}“ ({outcome_rows[0]['count']} სესიაზე).")
        if challenge_rows:
            findings.append(f"ძირითადი ბარიერი: „{challenge_rows[0]['name']}“ ({challenge_rows[0]['count']} სესიაზე).")

    return {
        "sessions": sessions,
        "sessions_count": n,
        "period_str": f"{year} წლის {month_name}",
        "total_minutes": total_minutes,
        "avg_minutes": int(round(total_minutes / n)) if n else 0,
        "planned_slots": planned_slots,
        "completed_slots": completed_slots,
        "missed_slots": missed_slots,
        "attendance_rate": attendance_rate,
        "zones": zones,
        "reg_improved": improved,
        "reg_stable_optimal": stable_optimal,
        "reg_worsened": worsened,
        "reg_unchanged": unchanged,
        "reg_positive_pct": _pct(improved + stable_optimal, n),
        "entry_rows": entry_rows,
        "domains": domain_list,
        "total_interventions": total_interventions,
        "assist_rows": assist_rows,
        "overall_index": overall_index,
        "overall_index_label": independence_label(overall_index),
        "overall_index_pct": _pct((overall_index or 1) - 1, 5) if overall_index else 0,
        "first_half_index": first_half_idx,
        "second_half_index": second_half_idx,
        "index_delta": index_delta,
        "session_index": session_index,
        "responses": [{"name": r, "count": c} for r, c in responses_counter.most_common(8)],
        "goals": goals,
        "outcomes": outcome_rows,
        "challenges": challenge_rows,
        "session_log": session_log,
        "findings": findings,
    }


def build_report_context(report):
    """Full template context for the printable / PDF monthly report."""
    beneficiary = report.beneficiary
    therapist = report.therapist
    agg = aggregate_month(beneficiary, report.year, report.month)

    therapist_name = (therapist.user.get_full_name() or therapist.user.username) if therapist else "—"

    legacy_zone_prefixes = ("თვითრეგულაციის საწყისი მდგომარეობა", "თვითრეგულაციის საბოლოო მდგომარეობა")
    ctx = {
        "report": report,
        "report_date": report.updated_at.strftime("%d.%m.%Y"),
        "period_display": report.period_display,
        "beneficiary": beneficiary,
        "beneficiary_name": beneficiary.full_name,
        "dob": beneficiary.date_of_birth.strftime("%d.%m.%Y") if beneficiary.date_of_birth else "—",
        "age": beneficiary.age_display,
        "therapy_start": beneficiary.start_date.strftime("%d.%m.%Y") if beneficiary.start_date else "—",
        "parent_name": getattr(beneficiary, "parent_name", ""),
        "parent_phone": getattr(beneficiary, "parent_phone", ""),
        "therapist_name": therapist_name,
        "therapist_title": therapist.title if (therapist and therapist.title) else "ოკუპაციური თერაპევტი",
        "clinic_name": therapist.clinic_name if (therapist and therapist.clinic_name) else "",
        "license_number": therapist.license_number if therapist and therapist.license_number else "",
        "doc_status": "დამტკიცებული ვერსია" if report.is_finalized else "სამუშაო ვერსია",
        # Therapist-editable narrative sections
        "section1_paragraphs": text_to_paragraphs(report.section_1_directions, legacy_zone_prefixes),
        "section2_paragraphs": text_to_paragraphs(report.section_2_goals),
        "section3_paragraphs": text_to_paragraphs(report.section_3_work_performed),
        "section4_items": text_to_paragraphs(report.section_8_challenges),
        "section5_items": text_to_paragraphs(report.section_9_recommendations),
        "section6_items": text_to_paragraphs(report.section_10_next_goals),
    }
    ctx.update(agg)
    # Real session count for the period (falls back to stored value)
    ctx["sessions_count"] = agg["sessions_count"] or report.sessions_count
    return ctx
