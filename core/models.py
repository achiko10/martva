from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date
import uuid


class TherapistProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="therapist_profile")
    phone = models.CharField(max_length=50, blank=True, verbose_name="ტელეფონი")
    title = models.CharField(max_length=150, default="ოკუპაციური თერაპევტი", verbose_name="პროფესიული როლი")
    clinic_name = models.CharField(max_length=200, default="ოკუპაციური თერაპიის ცენტრი", verbose_name="ცენტრი / კლინიკა")
    license_number = models.CharField(max_length=100, blank=True, verbose_name="ლიცენზია / სერტიფიკატი")
    is_admin_role = models.BooleanField(default=False, verbose_name="ადმინისტრატორი")

    class Meta:
        verbose_name = "თერაპევტის პროფილი"
        verbose_name_plural = "თერაპევტების პროფილები"

    def __str__(self):
        full_name = self.user.get_full_name()
        return full_name if full_name else self.user.username


class Beneficiary(models.Model):
    first_name = models.CharField(max_length=100, verbose_name="სახელი")
    last_name = models.CharField(max_length=100, verbose_name="გვარი")
    date_of_birth = models.DateField(verbose_name="დაბადების თარიღი")
    start_date = models.DateField(default=timezone.now, verbose_name="თერაპიის დაწყების თარიღი")
    therapist = models.ForeignKey(
        TherapistProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="beneficiaries",
        verbose_name="თერაპევტი"
    )
    session_duration_minutes = models.PositiveIntegerField(default=50, verbose_name="სესიის ხანგრძლივობა (წთ)")
    weekly_sessions_planned = models.PositiveIntegerField(default=2, verbose_name="კვირაში დაგეგმილი სესიები")
    notes = models.TextField(blank=True, verbose_name="დამატებითი მოკლე ინფორმაცია")
    is_active = models.BooleanField(default=True, verbose_name="აქტიურია")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="შექმნის დრო")

    class Meta:
        verbose_name = "ბენეფიციარი"
        verbose_name_plural = "ბენეფიციარები"
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def age_display(self):
        """Calculates age in years and months in Georgian"""
        today = date.today()
        if not self.date_of_birth:
            return ""
        years = today.year - self.date_of_birth.year
        months = today.month - self.date_of_birth.month
        if today.day < self.date_of_birth.day:
            months -= 1
        if months < 0:
            years -= 1
            months += 12

        if years <= 0:
            return f"{months} თვე"
        return f"{years} წელი, {months} თვე" if months > 0 else f"{years} წელი"


class OccupationalProfile(models.Model):
    beneficiary = models.OneToOneField(
        Beneficiary,
        on_delete=models.CASCADE,
        related_name="occupational_profile",
        verbose_name="ბენეფიციარი"
    )
    # თვითმოვლა
    self_care = models.TextField(
        blank=True,
        verbose_name="თვითმოვლა",
        help_text="ჩაცმა, გახდა, კვება, ჭურჭლის გამოყენება, ხელების დაბანა, კბილების გახეხვა, ტუალეტი, ჰიგიენა"
    )
    # თამაში
    play = models.TextField(
        blank=True,
        verbose_name="თამაში",
        help_text="დამოუკიდებელი, ფუნქციური, წარმოსახვითი, დაწყება, გაგრძელება, დასრულება, სხვასთან თამაში"
    )
    # ყურადღება
    attention = models.TextField(
        blank=True,
        verbose_name="ყურადღება",
        help_text="აქტივობის დაწყება, ჩართულობა, შენარჩუნება, დასრულება, ყურადღების გადატანა"
    )
    # მოტორული სფერო
    motor_skills = models.TextField(
        blank=True,
        verbose_name="მოტორული სფერო",
        help_text="წვრილი მოტორიკა, ხელისა და თვალის კოორდინაცია, ორმხრივი, მოტორული დაგეგმვა, სხეულის ცნობიერება, ბალანსი"
    )
    # ფუნქციური მონაწილეობა
    functional_participation = models.TextField(
        blank=True,
        verbose_name="ფუნქციური მონაწილეობა",
        help_text="სასწავლო აქტივობა, თამაში, თვითმოვლა, სოციალური, გადასვლა აქტივობებს შორის, ყოველდღიური რუტინა"
    )
    general_notes = models.TextField(blank=True, verbose_name="ზოგადი კლინიკური დაკვირვებები")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="განახლების დრო")

    class Meta:
        verbose_name = "ოკუპაციური პროფილი"
        verbose_name_plural = "ოკუპაციური პროფილები"

    def __str__(self):
        return f"ოკუპაციური პროფილი: {self.beneficiary.full_name}"


class SensoryProfile(models.Model):
    beneficiary = models.OneToOneField(
        Beneficiary,
        on_delete=models.CASCADE,
        related_name="sensory_profile",
        verbose_name="ბენეფიციარი"
    )
    tactile = models.TextField(blank=True, verbose_name="ტაქტილური (შეხება)")
    proprioceptive = models.TextField(blank=True, verbose_name="პროპრიოცეპტული (სხეულის შეგრძნება)")
    vestibular = models.TextField(blank=True, verbose_name="ვესტიბულარული (მოძრაობა და წონასწორობა)")
    auditory = models.TextField(blank=True, verbose_name="სმენითი")
    visual = models.TextField(blank=True, verbose_name="მხედველობითი")
    olfactory = models.TextField(blank=True, verbose_name="ყნოსვითი")
    gustatory = models.TextField(blank=True, verbose_name="გემოვნებითი")
    interoceptive = models.TextField(blank=True, verbose_name="ინტერცეპციული (შინაგანი ორგანოები)")
    multisensory = models.TextField(blank=True, verbose_name="მულტისენსორული თავისებურებები")
    observations = models.TextField(blank=True, verbose_name="დამუშავების სტილი და რეგულაციის დაკვირვებები")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="განახლების დრო")

    class Meta:
        verbose_name = "სენსორული პროფილი"
        verbose_name_plural = "სენსორული პროფილები"

    def __str__(self):
        return f"სენსორული პროფილი: {self.beneficiary.full_name}"


class Goal(models.Model):
    DOMAIN_CHOICES = [
        ("sensory_regulation", "სენსორული რეგულაცია"),
        ("attention", "ყურადღება"),
        ("fine_motor", "წვრილი მოტორიკა"),
        ("visual_motor", "ვიზუალურ-მოტორული უნარები"),
        ("gross_motor", "უხეში მოტორიკა"),
        ("motor_planning", "მოტორული დაგეგმვა"),
        ("self_care", "თვითმოვლა"),
        ("play", "თამაში"),
        ("transitions", "გადასვლები"),
        ("functional_participation", "ფუნქციური მონაწილეობა"),
        ("other", "სხვა"),
    ]

    STATUS_CHOICES = [
        ("active", "აქტიური"),
        ("achieved", "მიღწეული"),
        ("modified", "მოდიფიცირებული"),
        ("on_hold", "შეჩერებული"),
    ]

    beneficiary = models.ForeignKey(
        Beneficiary,
        on_delete=models.CASCADE,
        related_name="goals",
        verbose_name="ბენეფიციარი"
    )
    therapist = models.ForeignKey(
        TherapistProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="goals",
        verbose_name="თერაპევტი"
    )
    MEASUREMENT_TYPE_CHOICES = [
        ("percentage", "პროცენტული მაჩვენებელი (0-100%)"),
        ("duration", "ხანგრძლივობა / დრო (წუთი/წამი)"),
        ("frequency", "სიხშირე / მცდელობები (რაოდენობა)"),
        ("prompt_level", "დახმარების დონე (დამოუკიდებლობის კიბე)"),
    ]

    domain = models.CharField(max_length=50, choices=DOMAIN_CHOICES, default="sensory_regulation", verbose_name="სფერო")
    description = models.TextField(verbose_name="მიზნის აღწერა")
    # PEO Model & SMART fields
    occupation = models.CharField(max_length=255, blank=True, verbose_name="ოკუპაცია/აქტივობა (O)")
    environment_context = models.CharField(max_length=255, blank=True, verbose_name="გარემო და კონტექსტი (E)")
    criteria_type = models.CharField(
        max_length=50,
        blank=True,
        default="prompts",
        verbose_name="საზომი კრიტერიუმის ტიპი"
    )

    # Live SMART measurable metrics
    measurement_type = models.CharField(
        max_length=30,
        choices=MEASUREMENT_TYPE_CHOICES,
        default="percentage",
        verbose_name="გაზომვის ტიპი"
    )
    baseline_numeric = models.FloatField(default=0.0, verbose_name="საწყისი მაჩვენებელი")
    current_numeric = models.FloatField(default=0.0, verbose_name="მიმდინარე მაჩვენებელი")
    target_numeric = models.FloatField(default=100.0, verbose_name="სამიზნე მაჩვენებელი")
    unit_label = models.CharField(max_length=30, default="%", blank=True, verbose_name="საზომი ერთეული")

    baseline_state = models.CharField(max_length=255, blank=True, verbose_name="საწყისი მდგომარეობა (Baseline)")
    target_state = models.CharField(max_length=255, blank=True, verbose_name="სამიზნე მდგომარეობა")
    metric_unit = models.CharField(
        max_length=50,
        blank=True,
        default="წუთი",
        verbose_name="საზომი ერთეული",
        help_text="წუთი, რაოდენობა, დახმარების დონე, დამოუკიდებლობის %, სიხშირე და ა.შ."
    )
    target_date = models.DateField(null=True, blank=True, verbose_name="სამიზნე ვადა")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active", verbose_name="სტატუსი")
    progress_percentage = models.PositiveIntegerField(default=0, verbose_name="პროგრესის %")
    notes = models.TextField(blank=True, verbose_name="შენიშვნები")
    created_at = models.DateField(auto_now_add=True, verbose_name="შექმნის თარიღი")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="განახლების დრო")

    class Meta:
        verbose_name = "თერაპიული მიზანი"
        verbose_name_plural = "თერაპიული მიზნები"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_domain_display()}: {self.description[:40]}"

    def calculate_progress_percentage(self):
        """Calculates 0-100 progress percentage from baseline to target"""
        if self.target_numeric != self.baseline_numeric:
            ratio = (self.current_numeric - self.baseline_numeric) / (self.target_numeric - self.baseline_numeric)
            pct = max(0, min(100, int(round(ratio * 100))))
            return pct
        return 100 if self.current_numeric >= self.target_numeric else 0

    def update_progress(self, new_val, save=True):
        """Updates current value and recalculates progress percentage"""
        self.current_numeric = float(new_val)
        self.progress_percentage = self.calculate_progress_percentage()
        if self.progress_percentage >= 100:
            self.status = "achieved"
        elif self.status == "achieved" and self.progress_percentage < 100:
            self.status = "active"
        if save:
            self.save()

    @property
    def smart_summary(self):
        """Returns formatted clinical SMART summary or falls back to description"""
        if self.occupation:
            env_part = f" ({self.environment_context})" if self.environment_context else ""
            target_part = f" — სამიზნე: {self.target_numeric}{self.unit_label}" if self.unit_label else ""
            return f"{self.occupation}{env_part}{target_part}"
        return self.description


class SensorySystem(models.Model):
    CATEGORY_CHOICES = [
        ("movement", "მოძრაობა და სხეული"),
        ("tactile_sensory", "შეხება და შეგრძნება"),
        ("environment", "გარემო და აღქმა"),
    ]

    name = models.CharField(max_length=100, unique=True, verbose_name="დასახელება")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="სლაგი")
    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        default="movement",
        verbose_name="კატეგორია"
    )
    icon = models.CharField(max_length=50, blank=True, verbose_name="ხატულა/სიმბოლო")
    description = models.TextField(blank=True, verbose_name="აღწერა")
    order = models.PositiveIntegerField(default=0, verbose_name="თანმიმდევრობა")

    class Meta:
        verbose_name = "სენსორული სისტემა"
        verbose_name_plural = "სენსორული სისტემები"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class SensoryActivity(models.Model):
    sensory_system = models.ForeignKey(
        SensorySystem,
        on_delete=models.CASCADE,
        related_name="activities",
        verbose_name="სენსორული სისტემა"
    )
    name = models.CharField(max_length=150, verbose_name="აქტივობის დასახელება")
    description = models.TextField(blank=True, verbose_name="აღწერა")
    is_active = models.BooleanField(default=True, verbose_name="აქტიურია")

    class Meta:
        verbose_name = "სენსორული აქტივობა"
        verbose_name_plural = "სენსორული აქტივობები"
        ordering = ["sensory_system", "name"]
        unique_together = ["sensory_system", "name"]

    def __str__(self):
        return f"{self.sensory_system.name} - {self.name}"


class SensoryResponse(models.Model):
    name = models.CharField(max_length=150, unique=True, verbose_name="რეაქციის დასახელება")
    is_active = models.BooleanField(default=True, verbose_name="აქტიურია")
    order = models.PositiveIntegerField(default=0, verbose_name="თანმიმდევრობა")

    class Meta:
        verbose_name = "ბავშვის რეაქცია"
        verbose_name_plural = "ბავშვის რეაქციები"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class FunctionalOutcome(models.Model):
    name = models.CharField(max_length=150, unique=True, verbose_name="ფუნქციური შედეგი")
    is_active = models.BooleanField(default=True, verbose_name="აქტიურია")
    order = models.PositiveIntegerField(default=0, verbose_name="თანმიმდევრობა")

    class Meta:
        verbose_name = "ფუნქციური შედეგი"
        verbose_name_plural = "ფუნქციური შედეგები"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class Session(models.Model):
    # Alert Program / Zones of Regulation
    ALERT_ZONE_CHOICES = [
        ("blue", "ლურჯი ზონა (დაბალი ენერგია / ჰიპოაქტიური)"),
        ("green", "მწვანე ზონა (ოპტიმალური / მშვიდი, ფოკუსირებული)"),
        ("yellow", "ყვითელი ზონა (მომატებული / აღგზნებული)"),
        ("red", "წითელი ზონა (კრიზისი / დისტრესი)"),
    ]

    INITIAL_STATE_CHOICES = ALERT_ZONE_CHOICES
    FINAL_STATE_CHOICES = ALERT_ZONE_CHOICES

    beneficiary = models.ForeignKey(
        Beneficiary,
        on_delete=models.CASCADE,
        related_name="sessions",
        verbose_name="ბენეფიციარი"
    )
    therapist = models.ForeignKey(
        TherapistProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name="თერაპევტი"
    )
    date = models.DateField(default=timezone.now, verbose_name="სესიის თარიღი")
    duration_minutes = models.PositiveIntegerField(default=50, verbose_name="ხანგრძლივობა (წთ)")
    initial_state = models.CharField(
        max_length=30,
        choices=INITIAL_STATE_CHOICES,
        default="green",
        verbose_name="საწყისი რეგულაციის ზონა"
    )
    final_state = models.CharField(
        max_length=30,
        choices=FINAL_STATE_CHOICES,
        default="green",
        verbose_name="საბოლოო რეგულაციის ზონა"
    )
    challenges = models.JSONField(default=list, blank=True, verbose_name="სესიის გამოწვევები (ჩეკბოქსები)")
    goals = models.ManyToManyField(
        Goal,
        through="SessionGoal",
        blank=True,
        related_name="sessions",
        verbose_name="სესიის მიზნები"
    )
    functional_outcomes = models.ManyToManyField(
        FunctionalOutcome,
        blank=True,
        related_name="sessions",
        verbose_name="ფუნქციური შედეგები"
    )
    notes = models.TextField(blank=True, verbose_name="მოკლე პროფესიული ჩანაწერი")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="შექმნის დრო")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="განახლების დრო")

    class Meta:
        verbose_name = "სესია"
        verbose_name_plural = "სესიები"
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.beneficiary.full_name} - {self.date}"


class SessionGoal(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="session_goals")
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="session_goals")
    progress_value = models.CharField(max_length=100, blank=True, verbose_name="მიღწეული მაჩვენებელი (ტექსტური)")
    recorded_numeric = models.FloatField(null=True, blank=True, verbose_name="ფიქსირებული რიცხვითი მაჩვენებელი")
    prompt_level = models.CharField(max_length=50, blank=True, verbose_name="დახმარების დონე")
    notes = models.CharField(max_length=255, blank=True, verbose_name="შენიშვნა")

    class Meta:
        verbose_name = "სესიის მიზანი"
        verbose_name_plural = "სესიის მიზნები"
        unique_together = ["session", "goal"]

    def __str__(self):
        return f"{self.session} - {self.goal.description[:20]}"


class SessionSensoryActivity(models.Model):
    INTENSITY_CHOICES = [
        ("low", "დაბალი"),
        ("medium", "საშუალო"),
        ("high", "მაღალი"),
    ]

    ASSISTANCE_CHOICES = [
        ("independent", "დამოუკიდებლად"),
        ("verbal", "სიტყვიერი მითითება"),
        ("minimal", "მცირე დახმარება"),
        ("moderate", "საშუალო დახმარება"),
        ("maximal", "დიდი დახმარება"),
        ("full", "სრული დახმარება"),
    ]

    ACTIVITY_START_CHOICES = [
        ("independent", "დამოუკიდებლად დაიწყო"),
        ("cue", "მითითების შემდეგ"),
        ("assisted", "დახმარებით"),
    ]

    DIRECTION_CHOICES = [
        ("none", "არ გამოიყენება"),
        ("forward", "წინ"),
        ("backward", "უკან"),
        ("left", "მარცხნივ"),
        ("right", "მარჯვნივ"),
        ("up", "ზემოთ"),
        ("down", "ქვემოთ"),
        ("circular", "წრიული"),
        ("various", "სხვადასხვა მიმართულება"),
    ]

    SPEED_CHOICES = [
        ("none", "არ გამოიყენება"),
        ("slow", "ნელი"),
        ("medium", "საშუალო"),
        ("fast", "სწრაფი"),
    ]

    INTEROCEPTION_CHOICES = [
        ("none", "არ გამოიყენება"),
        ("self_expressed", "ბავშვმა თვითონ გამოხატა/დაასახელა"),
        ("observed", "თერაპევტმა დააკვირდა"),
    ]

    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="sensory_activities",
        verbose_name="სესია"
    )
    sensory_activity = models.ForeignKey(
        SensoryActivity,
        on_delete=models.CASCADE,
        related_name="session_activities",
        verbose_name="სენსორული აქტივობა"
    )
    duration_minutes = models.PositiveIntegerField(default=5, verbose_name="ხანგრძლივობა (წთ)")
    intensity = models.CharField(
        max_length=20,
        choices=INTENSITY_CHOICES,
        default="medium",
        verbose_name="ინტენსივობა"
    )
    repetition_count = models.PositiveIntegerField(default=1, verbose_name="გამეორება")
    assistance_level = models.CharField(
        max_length=20,
        choices=ASSISTANCE_CHOICES,
        default="moderate",
        verbose_name="დახმარების დონე"
    )
    activity_start = models.CharField(
        max_length=20,
        choices=ACTIVITY_START_CHOICES,
        default="cue",
        verbose_name="აქტივობის დაწყება"
    )
    movement_direction = models.CharField(
        max_length=20,
        choices=DIRECTION_CHOICES,
        default="none",
        verbose_name="მოძრაობის მიმართულება"
    )
    speed = models.CharField(
        max_length=20,
        choices=SPEED_CHOICES,
        default="none",
        verbose_name="სიჩქარე"
    )
    interoception_mode = models.CharField(
        max_length=20,
        choices=INTEROCEPTION_CHOICES,
        default="none",
        verbose_name="ინტერცეპციის ფიქსაცია"
    )
    responses = models.ManyToManyField(
        SensoryResponse,
        blank=True,
        related_name="session_activities",
        verbose_name="ბავშვის რეაქციები"
    )
    notes = models.CharField(max_length=255, blank=True, verbose_name="შენიშვნა")

    class Meta:
        verbose_name = "სესიის სენსორული აქტივობა"
        verbose_name_plural = "სესიის სენსორული აქტივობები"

    def __str__(self):
        return f"{self.sensory_activity.name} ({self.duration_minutes} წთ)"


class MonthlyReport(models.Model):
    MONTH_NAMES = {
        1: "იანვარი", 2: "თებერვალი", 3: "მარტი", 4: "აპრილი",
        5: "მაისი", 6: "ივნისი", 7: "ივლისი", 8: "აგვისტო",
        9: "სექტემბერი", 10: "ოქტომბერი", 11: "ნოემბერი", 12: "დეკემბერი"
    }

    beneficiary = models.ForeignKey(
        Beneficiary,
        on_delete=models.CASCADE,
        related_name="monthly_reports",
        verbose_name="ბენეფიციარი"
    )
    therapist = models.ForeignKey(
        TherapistProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="monthly_reports",
        verbose_name="თერაპევტი"
    )
    year = models.PositiveIntegerField(verbose_name="წელი")
    month = models.PositiveIntegerField(verbose_name="თვე")
    sessions_count = models.PositiveIntegerField(default=0, verbose_name="სესიების რაოდენობა")
    
    # 10 Professional Sections
    title = models.CharField(
        max_length=255,
        default="ოკუპაციური თერაპიის ყოველთვიური პროგრესის ანგარიში",
        verbose_name="ანგარიშის სათაური"
    )
    section_1_directions = models.TextField(verbose_name="1. თერაპიის ძირითადი მიმართულებები")
    section_2_goals = models.TextField(verbose_name="2. მიმდინარე მიზნები")
    section_3_work_performed = models.TextField(verbose_name="3. შესრულებული სამუშაო")
    section_4_sensory_interventions = models.TextField(verbose_name="4. გამოყენებული სენსორული ინტერვენციები/აქტივობები")
    section_5_child_response = models.TextField(verbose_name="5. ბავშვის რეაქცია და ჩართულობა")
    section_6_quantitative_progress = models.TextField(verbose_name="6. რაოდენობრივი პროგრესი")
    section_7_functional_changes = models.TextField(verbose_name="7. ფუნქციური ცვლილებები")
    section_8_challenges = models.TextField(verbose_name="8. არსებული სირთულეები")
    section_9_recommendations = models.TextField(verbose_name="9. რეკომენდაციები")
    section_10_next_goals = models.TextField(verbose_name="10. შემდეგი პერიოდის მიზნები")

    is_finalized = models.BooleanField(default=False, verbose_name="საბოლოოა / დამტკიცებული")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="შექმნის დრო")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="განახლების დრო")

    class Meta:
        verbose_name = "თვის ანგარიში"
        verbose_name_plural = "თვის ანგარიშები"
        unique_together = ["beneficiary", "year", "month"]
        ordering = ["-year", "-month"]

    def __str__(self):
        return f"{self.beneficiary.full_name} - {self.year} {self.month_display}"

    @property
    def month_display(self):
        return self.MONTH_NAMES.get(self.month, str(self.month))

    @property
    def period_display(self):
        return f"{self.year} წლის {self.month_display}"


class ReportRevision(models.Model):
    report = models.ForeignKey(
        MonthlyReport,
        on_delete=models.CASCADE,
        related_name="revisions",
        verbose_name="ანგარიში"
    )
    revised_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="რედაქტორი"
    )
    revision_note = models.CharField(max_length=255, blank=True, verbose_name="ცვლილების შენიშვნა")
    snapshot_data = models.JSONField(default=dict, verbose_name="მონაცემთა სნეპშოტი")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="რევიზიის დრო")

    class Meta:
        verbose_name = "ანგარიშის რევიზია"
        verbose_name_plural = "ანგარიშის რევიზიები"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.report} - რევიზია {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class ScheduleSlot(models.Model):
    STATUS_CHOICES = [
        ("scheduled", "დაგეგმილი"),
        ("completed", "ჩატარდა"),
        ("missed", "გაცდენა"),
    ]

    THERAPY_TYPES = [
        ("ოკუპაციური თერაპია", "ოკუპაციური თერაპია"),
        ("სენსორული ინტეგრაცია", "სენსორული ინტეგრაცია"),
        ("კვების თერაპია", "კვების თერაპია"),
        ("მოტორული უნარები", "მოტორული უნარები"),
        ("პირველადი შეფასება", "პირველადი შეფასება"),
    ]

    therapist = models.ForeignKey(
        TherapistProfile,
        on_delete=models.CASCADE,
        related_name="schedule_slots",
        verbose_name="თერაპევტი"
    )
    beneficiary = models.ForeignKey(
        Beneficiary,
        on_delete=models.CASCADE,
        related_name="schedule_slots",
        verbose_name="ბენეფიციარი"
    )
    date = models.DateField(default=timezone.now, verbose_name="თარიღი")
    start_time = models.TimeField(verbose_name="დაწყების დრო")
    duration_minutes = models.PositiveIntegerField(default=50, verbose_name="ხანგრძლივობა (წთ)")
    end_time = models.TimeField(null=True, blank=True, verbose_name="დასრულების დრო")
    therapy_type = models.CharField(max_length=100, default="ოკუპაციური თერაპია", verbose_name="თერაპია")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled", verbose_name="სტატუსი")
    notes = models.CharField(max_length=255, blank=True, verbose_name="შენიშვნა")
    session = models.ForeignKey(
        "Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedule_slots",
        verbose_name="მიბმული სესია"
    )
    series_id = models.UUIDField(null=True, blank=True, db_index=True, verbose_name="სერიის ID")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="შექმნის დრო")

    class Meta:
        verbose_name = "განრიგის ვიზიტი"
        verbose_name_plural = "განრიგის ვიზიტები"
        ordering = ["date", "start_time"]

    def save(self, *args, **kwargs):
        if not self.end_time and self.start_time:
            from datetime import datetime, timedelta
            dummy_dt = datetime.combine(datetime.today(), self.start_time) + timedelta(minutes=self.duration_minutes)
            self.end_time = dummy_dt.time()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} {self.start_time.strftime('%H:%M')} - {self.beneficiary.full_name}"

    @property
    def time_range_display(self):
        s = self.start_time.strftime("%H:%M")
        e = self.end_time.strftime("%H:%M") if self.end_time else ""
        return f"{s} - {e}" if e else s


