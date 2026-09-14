import os
import io
import re
import shutil
import tempfile
import subprocess
from django.template.loader import render_to_string


def _get_browser_path():
    """Find installed Chromium browser (Google Chrome or Microsoft Edge) on Windows."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _clean_line(line):
    """Strip any leading bullet symbols, asterisks, or dashes."""
    line = line.strip()
    return re.sub(r"^[\s•\*\-\–\—\>]+", "", line).strip()


def _parse_alert_zone_counts(text):
    """Parse alert program counts into structured dictionary."""
    result = {
        "green_init": 0, "green_final": 0,
        "yellow_init": 0, "yellow_final": 0,
        "blue_init": 0, "blue_final": 0,
        "red_init": 0, "red_final": 0,
    }
    
    for line in text.split("\n"):
        line_lower = line.lower()
        is_init = "საწყისი" in line_lower
        is_final = "საბოლოო" in line_lower
        
        matches = re.findall(r"([^,():]+)\s*\((\d+)x?\)", line, re.UNICODE)
        for name, cnt_str in matches:
            cnt = int(cnt_str)
            name_l = name.lower()
            if "მწვანე" in name_l:
                if is_init: result["green_init"] += cnt
                if is_final: result["green_final"] += cnt
            elif "ყვითელი" in name_l:
                if is_init: result["yellow_init"] += cnt
                if is_final: result["yellow_final"] += cnt
            elif "ლურჯი" in name_l:
                if is_init: result["blue_init"] += cnt
                if is_final: result["blue_final"] += cnt
            elif "წითელი" in name_l:
                if is_init: result["red_init"] += cnt
                if is_final: result["red_final"] += cnt

    return result


def generate_report_pdf(report):
    """
    Generates a pixel-perfect, premium Executive Clinical Report PDF matching
    the Stitch clinical assessment template using headless Chromium (Chrome/Edge).
    Returns PDF bytes.
    """
    beneficiary = report.beneficiary
    therapist = report.therapist

    # ── Basic metadata ──────────────────────────────────────────────────────
    therapist_name = (
        therapist.user.get_full_name() or therapist.user.username
        if therapist else "—"
    )
    dob_str = str(beneficiary.date_of_birth) if beneficiary.date_of_birth else "—"
    age_str = beneficiary.age_display if hasattr(beneficiary, "age_display") else ""
    total_min = report.sessions_count * 50
    doc_date = report.updated_at.strftime("%d.%m.%Y")
    doc_status = "დამტკიცებული ვერსია" if report.is_finalized else "სამუშაო ვერსია"

    # ── Section 1 (Attendance & Alert Program) ──────────────────────────────
    sec1_raw = report.section_1_directions or ""
    alert_zones_dict = _parse_alert_zone_counts(sec1_raw)
    
    sec1_paragraphs = []
    for line in sec1_raw.strip().split("\n"):
        clean = _clean_line(line)
        if not clean:
            continue
        if "თვითრეგულაციის საწყისი მდგომარეობა" in clean or "თვითრეგულაციის საბოლოო მდგომარეობა" in clean:
            continue
        sec1_paragraphs.append(clean)

    # ── Section 2 (Sensory Profile) ─────────────────────────────────────────
    sec2_raw = report.section_2_goals or ""
    sec2_items = []
    for line in sec2_raw.strip().split("\n"):
        clean = _clean_line(line)
        if clean and not clean.startswith("საანგარიშო პერიოდში დამუშავებული"):
            sec2_items.append(clean)

    # ── Section 3 (SMART Goals Matrix) ──────────────────────────────────────
    active_goals = beneficiary.goals.filter(status="active")
    goals_ctx = []
    for g in active_goals:
        pct = g.progress_percentage or 0
        unit = g.unit_label or ""
        domain = g.get_domain_display() if hasattr(g, "get_domain_display") else ""
        desc = g.description.strip()
        goals_ctx.append({
            "domain": domain,
            "description": desc,
            "baseline": f"{g.baseline_numeric:.0f}",
            "current": f"{g.current_numeric:.0f}",
            "target": f"{g.target_numeric:.0f}",
            "unit": unit,
            "pct": pct,
        })

    # ── Section 4 (Challenges) ──────────────────────────────────────────────
    sec4_raw = report.section_8_challenges or ""
    sec4_items = [
        _clean_line(line) for line in sec4_raw.strip().split("\n")
        if _clean_line(line) and not _clean_line(line).startswith("სესიების დროს დაფიქსირებული")
        and not _clean_line(line).startswith("თერაპევტის დაკვირვებები")
    ]

    # ── Section 5 (Recommendations) ─────────────────────────────────────────
    sec5_raw = report.section_9_recommendations or ""
    sec5_items = [
        _clean_line(line) for line in sec5_raw.strip().split("\n")
        if _clean_line(line) and not _clean_line(line).startswith("სესიებზე გამოყენებული")
    ]

    # ── Template Context ────────────────────────────────────────────────────
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

    html_string = render_to_string("core/pdf/report_pdf.html", context)

    # ── Render via Chromium Headless (Chrome / Edge) ─────────────────────────
    browser_path = _get_browser_path()
    if browser_path:
        with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as f:
            f.write(html_string)
            temp_html = f.name

        user_data_dir = tempfile.mkdtemp()
        temp_pdf = os.path.join(tempfile.gettempdir(), f"report_{report.id}_{os.getpid()}.pdf")
        if os.path.exists(temp_pdf):
            try:
                os.remove(temp_pdf)
            except OSError:
                pass

        try:
            cmd = [
                browser_path,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-default-apps",
                "--mute-audio",
                "--no-first-run",
                "--no-pdf-header-footer",
                f"--user-data-dir={user_data_dir}",
                f"--print-to-pdf={temp_pdf}",
                temp_html,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if os.path.exists(temp_pdf) and os.path.getsize(temp_pdf) > 0:
                with open(temp_pdf, "rb") as pf:
                    pdf_bytes = pf.read()
                return pdf_bytes
        except Exception:
            pass
        finally:
            if os.path.exists(temp_html):
                try:
                    os.remove(temp_html)
                except OSError:
                    pass
            if os.path.exists(temp_pdf):
                try:
                    os.remove(temp_pdf)
                except OSError:
                    pass
            if os.path.exists(user_data_dir):
                try:
                    shutil.rmtree(user_data_dir, ignore_errors=True)
                except Exception:
                    pass

    # ── Fallback via xhtml2pdf if browser execution fails ───────────────────
    from xhtml2pdf import pisa
    buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(src=html_string.encode("utf-8"), dest=buffer, encoding="utf-8")
    if not pisa_status.err:
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    raise RuntimeError("Failed to generate PDF document.")
