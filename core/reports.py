from collections import Counter

from core.models import MonthlyReport
from core.report_data import aggregate_month, ZONE_META


def _join(items, sep=", "):
    return sep.join(i for i in items if i)


def generate_monthly_report_content(beneficiary, year, month):
    """
    Generates a full clinical narrative for the month from the smart session
    checklists (regulation zones, entry adaptation, domain-specific smart
    evaluation parameters, OT prompt hierarchy, SMART goal measurements,
    adaptive outcomes, challenges and therapist notes).

    Sections (therapist-editable):
      section_1_directions        — დასწრება, ადაპტაცია და თვითრეგულაცია
      section_2_goals             — კლინიკური მიმართულებები და ჭკვიანი შეფასება
      section_3_work_performed    — SMART მიზნები და დამოუკიდებლობის დინამიკა
      section_8_challenges        — ადაპტური შედეგები, ბარიერები, დაკვირვებები
      section_9_recommendations   — რეკომენდაციები ოჯახს
      section_10_next_goals       — შემდეგი პერიოდის თერაპიული ფოკუსი
    """
    agg = aggregate_month(beneficiary, year, month)
    n = agg["sessions_count"]
    period_str = agg["period_str"]

    empty = {
        "section_4_sensory_interventions": "",
        "section_5_child_response": "",
        "section_6_quantitative_progress": "",
        "section_7_functional_changes": "",
    }

    if n == 0:
        return {
            "sessions_count": 0,
            "section_1_directions": f"საანგარიშო პერიოდში ({period_str}) ბენეფიციართან სესიები არ ჩატარებულა.",
            "section_2_goals": "თერაპიული ინტერვენციები საანგარიშო პერიოდში არ დაფიქსირებულა.",
            "section_3_work_performed": "მიზნების დინამიკა იხილეთ ინდივიდუალურ თერაპიულ გეგმაში.",
            "section_8_challenges": "",
            "section_9_recommendations": "",
            "section_10_next_goals": "",
            **empty,
        }

    # ── Section 1: Attendance, adaptation & regulation ─────────────────
    s1 = []
    att = (
        f" დაგეგმილი ვიზიტებიდან ჩატარდა {agg['completed_slots']}, გაცდენა — {agg['missed_slots']} "
        f"(დასწრება {agg['attendance_rate']}%)."
        if agg["attendance_rate"] is not None else ""
    )
    s1.append(
        f"საანგარიშო პერიოდში ({period_str}) {beneficiary.full_name}-თან ჩატარდა {n} ოკუპაციური თერაპიის "
        f"სესია, ჯამური ხანგრძლივობით {agg['total_minutes']} წუთი (საშუალოდ {agg['avg_minutes']} წთ).{att}"
    )
    if agg["entry_rows"]:
        top_entry = agg["entry_rows"][0]
        entry_txt = _join([f"{r['label'].split('(')[0].strip()} — {r['count']}x" for r in agg["entry_rows"]], "; ")
        s1.append(
            f"სესიაზე შემოსვლისა და გარემოსთან ადაპტაციის დომინანტური პატერნი: "
            f"{top_entry['label'].split('(')[0].strip().lower()} ({top_entry['count']} სესიაზე). სრული განაწილება: {entry_txt}."
        )
    init_top = max(agg["zones"], key=lambda z: z["init"])
    final_top = max(agg["zones"], key=lambda z: z["final"])
    s1.append(
        f"სესიის დასაწყისში ყველაზე ხშირად ფიქსირდებოდა {init_top['label']} ({init_top['sub']}, {init_top['init']}x), "
        f"სესიის დასასრულს — {final_top['label']} ({final_top['sub']}, {final_top['final']}x)."
    )
    reg_parts = []
    if agg["reg_improved"]:
        reg_parts.append(f"რეგულაცია გაუმჯობესდა {agg['reg_improved']} სესიაზე")
    if agg["reg_stable_optimal"]:
        reg_parts.append(f"ოპტიმალური მდგომარეობა შენარჩუნდა {agg['reg_stable_optimal']} სესიაზე")
    if agg["reg_unchanged"]:
        reg_parts.append(f"არაოპტიმალური ზონა უცვლელი დარჩა {agg['reg_unchanged']} სესიაზე")
    if agg["reg_worsened"]:
        reg_parts.append(f"გაუარესება დაფიქსირდა {agg['reg_worsened']} სესიაზე")
    if reg_parts:
        s1.append(
            "Alert Program®-ის მიხედვით: " + _join(reg_parts, "; ") +
            f". სესიების {agg['reg_positive_pct']}%-ში სენსორული ინტერვენციები ხელს უწყობდა ოპტიმალური აგზნებადობის მიღწევას/შენარჩუნებას."
        )

    # ── Section 2: Domains & smart evaluation ──────────────────────────
    s2 = []
    if agg["domains"]:
        s2.append(
            f"თვის განმავლობაში განხორციელდა {agg['total_interventions']} სტრუქტურირებული ინტერვენცია "
            f"{len(agg['domains'])} კლინიკური მიმართულებით."
        )
        for d in agg["domains"]:
            acts = _join([f"{a['name']} ({a['count']}x)" for a in d["activities"][:4]])
            evals = []
            for ev in d["evals"]:
                if ev["label"] == "დახმარება" or not ev["values"]:
                    continue
                top = ev["values"][0]
                evals.append(f"{ev['label'].lower()} — „{top['value']}“ ({top['count']}x)")
            resp = _join([f"„{r['name']}“" for r in d["responses"][:2]])
            sentence = (
                f"{d['name']}: {d['count']} ინტერვენცია {d['sessions']} სესიაზე ({d['minutes']} წთ). "
                f"აქტივობები: {acts}."
            )
            if evals:
                sentence += " შეფასება: " + _join(evals, "; ") + "."
            if d["index"] is not None:
                sentence += f" დახმარების დომინანტური დონე: {d['dominant_assist'].lower()} (ინდექსი {d['index']:.1f}/6)."
            if resp:
                sentence += f" დაფიქსირებული რეაქცია: {resp}."
            s2.append(sentence)
    else:
        s2.append("თერაპიული აქტივობები სესიებზე ცალკე არ ყოფილა მონიშნული.")

    # ── Section 3: SMART goals & independence ──────────────────────────
    s3 = []
    for g in agg["goals"]:
        if g["sessions_worked"]:
            move = (
                f"თვის დასაწყისში {g['month_start']}{g['unit']} → თვის ბოლოს {g['month_end']}{g['unit']} "
                f"(ცვლილება {g['month_delta_str']}{g['unit']})"
                if g["month_delta"] is not None else f"მიმდინარე მაჩვენებელი {g['current']}{g['unit']}"
            )
            s3.append(
                f"{g['domain']}: {g['description']} — {move}; საწყისი {g['baseline']}{g['unit']}, "
                f"სამიზნე {g['target']}{g['unit']}, მიღწეულია {g['pct']}%. დამუშავდა {g['sessions_worked']} სესიაზე."
            )
        else:
            s3.append(
                f"{g['domain']}: {g['description']} — ამ თვეში ცალკე არ გაზომილა "
                f"(მიმდინარე {g['current']}{g['unit']} / სამიზნე {g['target']}{g['unit']}, {g['pct']}%)."
            )
    if agg["overall_index"] is not None:
        line = (
            f"დამოუკიდებლობის საშუალო ინდექსი (OT Prompt Hierarchy, 1–6): {agg['overall_index']:.2f} — "
            f"{agg['overall_index_label'].lower()}."
        )
        if agg["index_delta"] is not None:
            if agg["index_delta"] >= 0.25:
                line += (f" თვის პირველ ნახევართან ({agg['first_half_index']:.2f}) შედარებით მეორე ნახევარში "
                         f"({agg['second_half_index']:.2f}) დახმარების საჭიროება შემცირდა.")
            elif agg["index_delta"] <= -0.25:
                line += (f" თვის მეორე ნახევარში ({agg['second_half_index']:.2f}) დახმარების საჭიროება გაიზარდა "
                         f"პირველ ნახევართან ({agg['first_half_index']:.2f}) შედარებით.")
            else:
                line += " დახმარების დონე თვის განმავლობაში სტაბილური იყო."
        s3.append(line)
        if agg["assist_rows"]:
            s3.append("დახმარების დონეების განაწილება: " + _join(
                [f"{r['label']} — {r['count']}x ({r['pct']}%)" for r in agg["assist_rows"]], "; ") + ".")

    # ── Section 7: Clinical Results & Functional Outcomes (შედეგი) ──────
    s7 = []
    if agg["findings"]:
        s7.extend(agg["findings"])
    else:
        if agg["outcomes"]:
            s7.append("მიღწეული ადაპტური შედეგები: " + _join([f"„{o['name']}“ ({o['count']} სესიაზე)" for o in agg["outcomes"]], "; ") + ".")
        if agg["overall_index"] is not None:
            s7.append(f"დამოუკიდებლობის საერთო მაჩვენებელი: {agg['overall_index']:.2f}/6 — {agg['overall_index_label']}.")

    # ── Section 8: Outcomes, challenges & therapist observations ───────
    s8 = []
    if agg["outcomes"]:
        s8.append("მიღწეული ადაპტური პასუხები: " + _join(
            [f"{o['name']} ({o['count']}x)" for o in agg["outcomes"]], "; ") + ".")
    if agg["challenges"]:
        s8.append("სესიებზე გამოვლენილი ბარიერები: " + _join(
            [f"{c['name']} ({c['count']} სესიაზე)" for c in agg["challenges"]], "; ") + ".")
    notes = [s.notes.strip() for s in agg["sessions"] if s.notes and s.notes.strip()]
    if notes:
        s8.append(f"თერაპევტის ბოლო დაკვირვება: {notes[-1]}")

    # ── Section 9: Recommendations (context-aware) ─────────────────────
    s9 = []
    slugs = {d["slug"]: d for d in agg["domains"]}
    responses_all = Counter()
    for d in agg["domains"]:
        for r in d["responses"]:
            responses_all[r["name"]] += r["count"]
    hyper = any("ჰიპერმგრძნობელობა" in r or "დაცვითობა" in r for r in responses_all)
    seeking = any("ძიება" in r for r in responses_all)

    if "vestibular" in slugs:
        s9.append("ვესტიბულარული მხარდაჭერა: ყოველდღიური დოზირებული რწევა/ტრიალი და წონასწორობის თამაშები "
                  "ბავშვის ტოლერანტობის ფარგლებში; ნელი, რიტმული მოძრაობა — დასამშვიდებლად.")
    if "proprioceptive" in slugs or seeking:
        s9.append("პროპრიოცეპტული „მძიმე სამუშაო“: ნივთების ტარება, მიწოლა-გაწევა, ხტომა და ღრმა წნევა — "
                  "განსაკუთრებით სამაგიდო აქტივობებისა და გადასვლების წინ.")
    if "tactile" in slugs or hyper:
        s9.append("ტაქტილური დესენსიტიზაცია: ტექსტურების ეტაპობრივი შეთავაზება (მშრალი → პლასტიკური → სველი), "
                  "იძულების გარეშე, ბავშვის ინიციატივის მხარდაჭერით.")
    if "sensory_perception" in slugs:
        s9.append("სენსორული გარემოს მოდულაცია: აკუსტიკური/ვიზუალური გადატვირთვის შემცირება, სუნთქვითი და "
                  "ორო-მოტორული თამაშები (ბუშტები, საწრუპი).")
    if "praxis_gross" in slugs:
        s9.append("პრაქსისი და კოორდინაცია: მრავალსაფეხურიანი მოძრაობითი თამაშები, დაბრკოლებების ბილიკი და "
                  "ორმხრივი (ბილატერალური) მოძრაობების პრაქტიკა სახლში.")
    if "fine_motor" in slugs:
        s9.append("წვრილი მოტორიკა: ყოველდღიური 10–15 წუთი ძერწვა, აცმა, მაკრატლით ჭრა და ხაზების გავლება; "
                  "პინცეტური ჩაჭიდების წახალისება.")
    if "adl_play" in slugs:
        s9.append("თვითმოვლა და რუტინა: ვიზუალური განრიგის გამოყენება ჩაცმა-გახდისა და ჰიგიენის დროს, "
                  "ფიზიკური დახმარების ეტაპობრივი შემცირება (უკუ-ჯაჭვის მეთოდი).")
    if "interoceptive" in slugs:
        s9.append("ინტეროცეფცია და თვითრეგულაცია: სხეულის სიგნალებისა და ემოციური ზონის ყოველდღიური "
                  "ვერბალიზაცია, მშვიდი კუთხე და შერჩეული დამამშვიდებელი სტრატეგია.")
    if agg["challenges"]:
        top_ch = agg["challenges"][0]["name"]
        if "გადასვლ" in top_ch:
            s9.append("გადასვლების მხარდაჭერა: წინასწარი გაფრთხილება (ტაიმერი/ვიზუალური ბარათი) აქტივობის შეცვლამდე.")
        elif "გადატვირთვა" in top_ch:
            s9.append("სენსორული გადატვირთვის პრევენცია: შესვენების რეგულარული მოთხოვნის სწავლება და მშვიდი სივრცე.")

    # ── Section 10: Next-period focus ──────────────────────────────────
    s10 = []
    for g in agg["goals"]:
        if g["pct"] >= 100:
            s10.append(f"{g['domain']}: მიზანი მიღწეულია — განისაზღვროს ახალი, უფრო რთული SMART მიზანი "
                       f"(განზოგადება სხვა გარემოში / დამოუკიდებლობის გაზრდა).")
        elif g["sessions_worked"] and g["month_delta"] is not None and g["month_delta"] <= 0:
            s10.append(f"{g['domain']}: პროგრესი შენელებულია — გადაიხედოს სტრატეგია, დახმარების დონე ან "
                       f"აქტივობის სირთულე (მიმდინარე {g['pct']}%).")
        else:
            s10.append(f"{g['domain']}: გაგრძელდეს მუშაობა სამიზნემდე ({g['target']}{g['unit']}; მიმდინარე {g['pct']}%).")
    if agg["overall_index"] is not None and agg["overall_index"] < 5:
        s10.append("დახმარების დონის ეტაპობრივი შემცირება ფიზიკურიდან ვერბალურ/ვიზუალურ მინიშნებამდე.")

    return {
        "sessions_count": n,
        "section_1_directions": "\n".join(s1),
        "section_2_goals": "\n".join(s2),
        "section_3_work_performed": "\n".join(s3) if s3 else "მიზნების დინამიკა იხილეთ ინდივიდუალურ გეგმაში.",
        "section_7_functional_changes": "\n".join(s7),
        "section_8_challenges": "\n".join(s8),
        "section_9_recommendations": "\n".join(s9),
        "section_10_next_goals": "\n".join(s10),
        **empty,
    }
