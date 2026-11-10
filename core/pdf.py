import os
import io
import shutil
import tempfile
import subprocess
from django.template.loader import render_to_string

from .report_data import build_report_context, clean_line as _clean_line  # noqa: F401 (backward compat)


def _get_browser_path():
    """Find installed Chromium browser (Google Chrome or Microsoft Edge) on Windows/Linux."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def generate_report_pdf(report):
    """
    Generates the full structured clinical monthly report PDF (smart checklist
    aggregation + therapist narrative) using headless Chromium.
    Returns PDF bytes.
    """
    context = build_report_context(report)
    context["pdf_mode"] = True
    html_string = render_to_string("core/pdf/report_pdf.html", context)

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
                "--disable-sync",
                "--disable-default-apps",
                "--mute-audio",
                "--no-first-run",
                "--no-pdf-header-footer",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=8000",
                f"--user-data-dir={user_data_dir}",
                f"--print-to-pdf={temp_pdf}",
                temp_html,
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            if os.path.exists(temp_pdf) and os.path.getsize(temp_pdf) > 0:
                with open(temp_pdf, "rb") as pf:
                    return pf.read()
        except Exception:
            pass
        finally:
            for path in (temp_html, temp_pdf):
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            shutil.rmtree(user_data_dir, ignore_errors=True)

    # ── Fallback via xhtml2pdf if browser execution fails ───────────────────
    from xhtml2pdf import pisa
    buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(src=html_string.encode("utf-8"), dest=buffer, encoding="utf-8")
    if not pisa_status.err:
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    raise RuntimeError("Failed to generate PDF document.")
