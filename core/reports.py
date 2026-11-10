from collections import Counter
from core.models import Session, Goal, MonthlyReport


def generate_monthly_report_content(beneficiary, year, month):
    """
    Analyzes session records for the specified month and year,
    aggregating strictly facts into 5 clean, coherent sections:
    1. დასწრება, ადაპტაცია და რეგულაციის ზონები
    2. თერაპიული/სენსორული მიმართულებები და ჭკვიანი შეფასების პასუხები
    3. მიზნების SMART დინამიკა და დამოუკიდებლობის იერარქია
    4. ადაპტური შედეგები და გამოწვევები
    5. რეკომენდაციები ოჯახს
    """
    sessions = Session.objects.filter(
        beneficiary=beneficiary,
        date__year=year,
        date__month=month
    ).order_by("date")

    sessions_count = sessions.count()
    month_name = MonthlyReport.MONTH_NAMES.get(month, str(month))
    period_str = f"{year} წლის {month_name}"

    if sessions_count == 0:
        return {
            "sessions_count": 0,
            "section_1_directions": f"საანგარიშო პერიოდში ({period_str}) ბენეფიციართან სესიები არ ჩატარებულა.",
            "section_2_goals": "აქტიური მიზნები განსაზღვრულია ბენეფიციარის პროფილში.",
            "section_3_work_performed": "მონაცემები არ ფიქსირდება.",
            "section_4_sensory_interventions": "",
            "section_5_child_response": "",
            "section_6_quantitative_progress": "",
            "section_7_functional_changes": "",
            "section_8_challenges": "",
            "section_9_recommendations": "",
            "section_10_next_goals": ""
        }

    # 1. Goals
    goals_addressed = Counter()
    goal_objs = {}
    for s in sessions:
        for g in s.goals.all():
            goals_addressed[g.id] += 1
            goal_objs[g.id] = g

    # 2. Clinical Domains, Activities, Smart Evaluation Parameters & Responses
    system_counter = Counter()
    system_slugs = set()
    activity_counter = Counter()
    assistance_counter = Counter()
    responses_counter = Counter()
    smart_eval_counter = Counter()
    outcomes_counter = Counter()

    for s in sessions:
        for fo in s.functional_outcomes.all():
            outcomes_counter[fo.name] += 1
        for sa in s.sensory_activities.select_related("sensory_activity__sensory_system").all():
            sys_obj = sa.sensory_activity.sensory_system
            sys_name = sys_obj.name
            system_slugs.add(sys_obj.slug)
            act_name = sa.sensory_activity.name
            system_counter[sys_name] += 1
            activity_counter[act_name] += 1
            assistance_counter[sa.get_assistance_level_display()] += 1
            for r in sa.responses.all():
                responses_counter[r.name] += 1
            for label, val in sa.smart_badges:
                smart_eval_counter[f"{label}: {val}"] += 1

    # 3. Entry adaptation & State transitions (Alert Program 4 Zones)
    entry_states = Counter(s.get_entry_adaptation_display() for s in sessions if s.entry_adaptation)
    initial_states = Counter(s.get_initial_state_display() for s in sessions)
    final_states = Counter(s.get_final_state_display() for s in sessions)

    # 4. Challenges collected from session checkboxes
    challenges_counter = Counter()
    session_notes = []
    for s in sessions:
        if s.challenges:
            for ch in s.challenges:
                challenges_counter[ch] += 1
        if s.notes and s.notes.strip():
            session_notes.append(s.notes.strip())

    # ==================== BUILD 5 CLEAN SECTIONS ====================

    # Section 1: დასწრება, ადაპტაცია და რეგულაციის ზონები
    sec_1_lines = [
        f"საანგარიშო პერიოდში ({period_str}) ბენეფიციარ {beneficiary.full_name}-თან ჩატარდა სულ {sessions_count} ოკუპაციური თერაპიის სესია.",
    ]
    if entry_states:
        entry_summary = ", ".join(f"{st} ({cnt}x)" for st, cnt in entry_states.most_common())
        sec_1_lines.append(f"სესიაზე შემოსვლა და გარემოსთან ადაპტაცია: {entry_summary}.")
    init_summary = ", ".join(f"{st} ({cnt}x)" for st, cnt in initial_states.items())
    final_summary = ", ".join(f"{st} ({cnt}x)" for st, cnt in final_states.items())
    sec_1_lines.append(f"თვითრეგულაციის საწყისი მდგომარეობა: {init_summary}.")
    sec_1_lines.append(f"თვითრეგულაციის საბოლოო მდგომარეობა: {final_summary}.")
    sec_1 = "\n".join(sec_1_lines)

    # Section 2: თერაპიული მიმართულებები, აქტივობები და ჭკვიანი შეფასება
    sec_2_lines = []
    if system_counter:
        sec_2_lines.append("საანგარიშო პერიოდში დამუშავებული სენსორული სისტემები:")
        for sys_name, count in system_counter.most_common():
            sec_2_lines.append(f"{sys_name}: დამუშავდა {count}-ჯერ.")
        if activity_counter:
            sec_2_lines.append("\nსესიებზე განხორციელებული კონკრეტული აქტივობები:")
            top_acts = [f"{act} ({cnt}x)" for act, cnt in activity_counter.most_common(12)]
            sec_2_lines.append(", ".join(top_acts) + ".")
        if smart_eval_counter:
            sec_2_lines.append("\nკლინიკური შეფასების პარამეტრები:")
            top_evals = [f"{ev} ({cnt}x)" for ev, cnt in smart_eval_counter.most_common(10)]
            sec_2_lines.append("; ".join(top_evals) + ".")
        if responses_counter:
            sec_2_lines.append("\nსტიმულებზე დაფიქსირებული რეაქციები:")
            top_resps = [f"„{r}“ ({cnt})" for r, cnt in responses_counter.most_common(8)]
            sec_2_lines.append(", ".join(top_resps) + ".")
    else:
        sec_2_lines.append("თერაპიული აქტივობები ცალკე არ ყოფილა მონიშნული.")
    sec_2 = "\n".join(sec_2_lines)

    # Section 3: მიზნების დინამიკა (დამოუკიდებლობა)
    sec_3_lines = []
    if goal_objs:
        sec_3_lines.append("თერაპიული მიზნების რაოდენობრივი SMART დინამიკა:")
        for gid, g in goal_objs.items():
            count = goals_addressed[gid]
            prog_info = f"საწყისი: {g.baseline_numeric:.0f}{g.unit_label} → მიმდინარე: {g.current_numeric:.0f}{g.unit_label} (სამიზნე: {g.target_numeric:.0f}{g.unit_label}, {g.progress_percentage}%)"
            sec_3_lines.append(f"{g.get_domain_display()}: {g.description} — {prog_info}. დამუშავდა {count} სესიაზე.")
    else:
        active_goals = beneficiary.goals.filter(status="active")
        if active_goals.exists():
            sec_3_lines.append("მიმდინარე აქტიური მიზნები:")
            for g in active_goals:
                prog_info = f"პროგრესი: {g.current_numeric:.0f}{g.unit_label} / {g.target_numeric:.0f}{g.unit_label} ({g.progress_percentage}%)"
                sec_3_lines.append(f"{g.get_domain_display()}: {g.description} ({prog_info}).")

    if assistance_counter:
        sec_3_lines.append("\nდახმარების დონის (OT Prompt Hierarchy) განაწილება სესიებზე:")
        assist_str = ", ".join(f"{lvl} ({cnt}x)" for lvl, cnt in assistance_counter.most_common())
        sec_3_lines.append(f"{assist_str}.")
    if outcomes_counter:
        sec_3_lines.append("\nმიღწეული ადაპტური პასუხი და ფუნქციური შედეგები:")
        out_str = ", ".join(f"{out} ({cnt}x)" for out, cnt in outcomes_counter.most_common())
        sec_3_lines.append(f"{out_str}.")
    sec_3 = "\n".join(sec_3_lines) if sec_3_lines else "მიზნების დინამიკა იხილეთ ინდივიდუალურ გეგმაში."

    # Section 4: გამოწვევები და კლინიკური ჩანაწერები
    sec_4_lines = []
    if challenges_counter:
        sec_4_lines.append("სესიების დროს დაფიქსირებული გამოწვევები:")
        for ch, count in challenges_counter.most_common():
            sec_4_lines.append(f"{ch} ({count} სესიაზე).")
    if session_notes:
        sec_4_lines.append("\nთერაპევტის დაკვირვებები სესიებიდან:")
        for sn in session_notes[:4]:
            sec_4_lines.append(f"„{sn}“")
    sec_4 = "\n".join(sec_4_lines) if sec_4_lines else ""

    # Section 5: რეკომენდაციები ოჯახს (8 მიმართულების მიხედვით)
    sec_5_lines = []
    if system_slugs:
        sec_5_lines.append("სესიებზე გამოყენებული სენსორული მიმართულებებიდან გამომდინარე, რეკომენდებულია:")
        if "vestibular" in system_slugs:
            sec_5_lines.append("ვესტიბულარული და პოსტურალური მხარდაჭერა: რწევისა და წონასწორობის აქტივობების დოზირებული გაგრძელება ბავშვის ტოლერანტობის გათვალისწინებით.")
        if "proprioceptive" in system_slugs:
            sec_5_lines.append("პროპრიოცეპტული დატვირთვა (Heavy Work): ღრმა წნევის, მძიმე ნივთების გადატანისა და სახსრების კომპრესიის ჩართვა სამაგიდო აქტივობების წინ.")
        if "tactile" in system_slugs:
            sec_5_lines.append("ტაქტილური დესენსიტიზაცია: მშრალი, პლასტიკური და სველი ტექსტურების ეტაპობრივი შეთავაზება იძულების გარეშე.")
        if "sensory_perception" in system_slugs:
            sec_5_lines.append("სენსორული გარემოს მოდულაცია: მშვიდი აკუსტიკურ-ვიზუალური ფონის შენარჩუნება და სუნთქვითი/ორო-მოტორული თამაშების წახალისება.")
        if "praxis_gross" in system_slugs:
            sec_5_lines.append("პრაქსისი და კოორდინაცია: მრავალსაფეხურიანი მოტორული თამაშებისა და ორმხრივი (ბილატერალური) მოძრაობების პრაქტიკა სახლის გარემოში.")
        if "fine_motor" in system_slugs:
            sec_5_lines.append("წვრილი და გრაფომოტორიკა: თითების იზოლირებული მოძრაობის, პინცეტური ჩაჭიდებისა და ბიმანუალური მანიპულაციის (გაჭრა, აცმა, ძერწვა) ყოველდღიური წახალისება.")
        if "adl_play" in system_slugs:
            sec_5_lines.append("თვითმოვლა (ADL) და რუტინა: ჩაცმა-გახდისა და ჰიგიენის პროცესში ვიზუალური მინიშნებების გამოყენება და ფიზიკური დახმარების ეტაპობრივი შემცირება.")
        if "interoceptive" in system_slugs:
            sec_5_lines.append("ინტეროცეფცია და თვითრეგულაცია: სხეულის სიგნალებისა და ემოციური ზონების ვერბალიზაცია და დამამშვიდებელი კუთხის/სტრატეგიის გამოყენება.")
    sec_5 = "\n".join(sec_5_lines) if sec_5_lines else ""

    return {
        "sessions_count": sessions_count,
        "section_1_directions": sec_1,
        "section_2_goals": sec_2,
        "section_3_work_performed": sec_3,
        "section_4_sensory_interventions": "",
        "section_5_child_response": "",
        "section_6_quantitative_progress": "",
        "section_7_functional_changes": "",
        "section_8_challenges": sec_4,
        "section_9_recommendations": sec_5,
        "section_10_next_goals": ""
    }
