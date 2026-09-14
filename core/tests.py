from datetime import date
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from core.models import (
    TherapistProfile, Beneficiary, OccupationalProfile, SensoryProfile,
    Goal, SensorySystem, SensoryActivity, SensoryResponse, FunctionalOutcome,
    Session, SessionGoal, SessionSensoryActivity, MonthlyReport
)
from core.reports import generate_monthly_report_content
from core.pdf import generate_report_pdf


class OTProgressCoreTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.therapist_user = User.objects.create_user(
            username="test_therapist", password="password123", first_name="ანა", last_name="მაისურაძე"
        )
        self.therapist_profile = TherapistProfile.objects.create(
            user=self.therapist_user,
            title="ოკუპაციური თერაპევტი",
            clinic_name="თერაპიის ცენტრი"
        )

        self.other_user = User.objects.create_user(
            username="other_therapist", password="password123", first_name="გიორგი"
        )
        self.other_profile = TherapistProfile.objects.create(
            user=self.other_user,
            title="ოკუპაციური თერაპევტი"
        )

        # Beneficiary
        self.beneficiary = Beneficiary.objects.create(
            first_name="დავით",
            last_name="ლომიძე",
            date_of_birth=date(2020, 4, 10),
            start_date=date(2024, 1, 1),
            therapist=self.therapist_profile,
            session_duration_minutes=45,
            weekly_sessions_planned=2
        )
        OccupationalProfile.objects.create(beneficiary=self.beneficiary)
        SensoryProfile.objects.create(beneficiary=self.beneficiary)

        # Sensory Catalog
        self.sys_vestibular = SensorySystem.objects.create(name="ვესტიბულარული", slug="vestibular", icon="", order=1)
        self.sys_proprio = SensorySystem.objects.create(name="პროპრიოცეპტული", slug="proprioceptive", icon="", order=2)

        self.act_swing = SensoryActivity.objects.create(sensory_system=self.sys_vestibular, name="საქანელა")
        self.act_heavy = SensoryActivity.objects.create(sensory_system=self.sys_proprio, name="მძიმე საგნის ტარება")

        self.resp_accepted = SensoryResponse.objects.create(name="მიიღო სტიმული", order=1)
        self.resp_engaged = SensoryResponse.objects.create(name="ჩართულობა გაიზარდა", order=2)

        self.fo_attention = FunctionalOutcome.objects.create(name="ყურადღების გაზრდა", order=1)
        self.fo_regulation = FunctionalOutcome.objects.create(name="თვითრეგულაცია", order=2)

        # Goal
        self.goal = Goal.objects.create(
            beneficiary=self.beneficiary,
            therapist=self.therapist_profile,
            domain="attention",
            description="მაგიდის აქტივობაში ყურადღების შენარჩუნება 8 წუთით",
            baseline_state="3 წუთი",
            target_state="8 წუთი",
            metric_unit="წუთი",
            status="active"
        )

    def test_beneficiary_age_calculation(self):
        """Test age calculation in Georgian"""
        age_str = self.beneficiary.age_display
        self.assertTrue("წელი" in age_str or "თვე" in age_str)
        self.assertEqual(self.beneficiary.full_name, "დავით ლომიძე")

    def test_session_creation_and_relations(self):
        """Test rapid session recording logic and relationships"""
        session = Session.objects.create(
            beneficiary=self.beneficiary,
            therapist=self.therapist_profile,
            date=date(2026, 9, 5),
            duration_minutes=50,
            initial_state="blue",
            final_state="green",
            challenges=["გადაღლა"],
            notes="კარგი სესია"
        )
        session.goals.add(self.goal)
        session.functional_outcomes.add(self.fo_attention)

        sa = SessionSensoryActivity.objects.create(
            session=session,
            sensory_activity=self.act_swing,
            assistance_level="verbal"
        )
        sa.responses.add(self.resp_accepted, self.resp_engaged)

        self.assertEqual(session.goals.count(), 1)
        self.assertEqual(session.sensory_activities.count(), 1)
        self.assertEqual(sa.responses.count(), 2)

    def test_monthly_report_content_aggregation(self):
        """Test automatic clinical narrative generation in Georgian across 5 sections"""
        # Create 1 session in September 2026
        s1 = Session.objects.create(
            beneficiary=self.beneficiary,
            therapist=self.therapist_profile,
            date=date(2026, 9, 2),
            duration_minutes=50,
            initial_state="yellow",
            final_state="green",
            challenges=["ყურადღების გაფანტვა"]
        )
        s1.goals.add(self.goal)
        sa1 = SessionSensoryActivity.objects.create(
            session=s1,
            sensory_activity=self.act_heavy,
            assistance_level="verbal"
        )
        sa1.responses.add(self.resp_accepted, self.resp_engaged)

        content = generate_monthly_report_content(self.beneficiary, 2026, 9)

        self.assertEqual(content["sessions_count"], 1)
        self.assertIn("დავით ლომიძე", content["section_1_directions"])
        self.assertIn("50 წუთს", content["section_1_directions"])
        self.assertIn("პროპრიოცეპტული", content["section_2_goals"])
        self.assertIn("დახმარების დონის", content["section_3_work_performed"])
        self.assertIn("ყურადღების გაფანტვა", content["section_8_challenges"])

    def test_pdf_generation_succeeds(self):
        """Test ReportLab PDF generation with Georgian characters"""
        content = generate_monthly_report_content(self.beneficiary, 2026, 9)
        report = MonthlyReport.objects.create(
            beneficiary=self.beneficiary,
            therapist=self.therapist_profile,
            year=2026,
            month=9,
            **content
        )
        pdf_bytes = generate_report_pdf(report)
        self.assertTrue(len(pdf_bytes) > 5000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_authenticated_routes(self):
        """Test authentication protection and views access"""
        # Unauthenticated redirect
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)

        # Authenticated as therapist
        self.client.login(username="test_therapist", password="password123")
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "დავით ლომიძე")

        # Beneficiary detail
        resp = self.client.get(reverse("beneficiary_detail", args=[self.beneficiary.id]))
        self.assertEqual(resp.status_code, 200)

        # Progress view
        resp = self.client.get(reverse("progress", args=[self.beneficiary.id]))
        self.assertEqual(resp.status_code, 200)

        # HTMX sensory activities endpoint
        resp = self.client.get(reverse("htmx_sensory_activities"), {"systems": ["vestibular", "proprioceptive"]})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "საქანელა")
        self.assertContains(resp, "მძიმე საგნის ტარება")

    def test_peo_smart_goal_creation(self):
        """Test creating a measurable SMART goal via beneficiary detail POST"""
        self.client.login(username="test_therapist", password="password123")
        url = reverse("beneficiary_detail", args=[self.beneficiary.id])
        resp = self.client.post(url, {
            "action": "create_goal",
            "domain": "self_care",
            "occupation": "კოვზით დამოუკიდებლად კვება",
            "environment_context": "სადილის დროს, ადაპტირებულ სკამზე",
            "criteria_type": "მინიმალური ვერბალური მითითებით",
            "measurement_type": "percentage",
            "baseline_numeric": "20",
            "target_numeric": "80",
            "unit_label": "%",
            "target_date": "2026-12-01",
        })
        self.assertEqual(resp.status_code, 302)
        goal = Goal.objects.filter(occupation="კოვზით დამოუკიდებლად კვება").first()
        self.assertIsNotNone(goal)
        self.assertEqual(goal.domain, "self_care")
        self.assertEqual(goal.baseline_numeric, 20.0)
        self.assertEqual(goal.target_numeric, 80.0)
        self.assertEqual(goal.unit_label, "%")
        self.assertIn("კოვზით დამოუკიდებლად კვება", goal.smart_summary)

        # Test updating progress directly on goal detail view
        goal_url = reverse("goal_detail", args=[goal.id])
        resp = self.client.get(goal_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "კოვზით დამოუკიდებლად კვება")

        # Update progress to 65%
        resp = self.client.post(goal_url, {
            "action": "update_progress",
            "current_numeric": "65"
        })
        self.assertEqual(resp.status_code, 302)
        goal.refresh_from_db()
        self.assertEqual(goal.current_numeric, 65.0)
        self.assertEqual(goal.progress_percentage, 75)  # (65 - 20) / (80 - 20) = 45 / 60 = 75%



