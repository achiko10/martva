from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from datetime import date, timedelta
from core.models import (
    TherapistProfile, Beneficiary, OccupationalProfile, SensoryProfile,
    Goal, SensorySystem, SensoryActivity, SensoryResponse, FunctionalOutcome,
    Session, SessionGoal, SessionSensoryActivity, MonthlyReport
)


class Command(BaseCommand):
    help = "Seed initial sensory catalog, responses, outcomes, users and sample data"

    def handle(self, *args, **options):
        self.stdout.write("Starting catalog seeding...")

        # 1. Create Admin User
        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "first_name": "ადმინისტრატორი",
                "last_name": "სისტემური",
                "email": "admin@otprogress.ge",
                "is_staff": True,
                "is_superuser": True
            }
        )
        if created:
            admin_user.set_password("admin123")
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Created admin user (admin / admin123)"))
        TherapistProfile.objects.get_or_create(
            user=admin_user,
            defaults={"title": "მთავარი ადმინისტრატორი / OT კონსულტანტი", "is_admin_role": True}
        )

        # 2. Create Sample Therapist User
        therapist_user, created = User.objects.get_or_create(
            username="therapist",
            defaults={
                "first_name": "ანა",
                "last_name": "მაისურაძე",
                "email": "ana@otprogress.ge",
                "is_staff": False,
                "is_superuser": False
            }
        )
        if created:
            therapist_user.set_password("therapist123")
            therapist_user.save()
            self.stdout.write(self.style.SUCCESS("Created therapist user (therapist / therapist123)"))
        therapist_profile, _ = TherapistProfile.objects.get_or_create(
            user=therapist_user,
            defaults={
                "title": "ოკუპაციური თერაპევტი",
                "phone": "+995 599 123456",
                "clinic_name": "საბავშვო განვითარებისა და თერაპიის ცენტრი",
                "license_number": "OT-GE-2024-889"
            }
        )

        # 3. Sensory Systems & Activities
        catalog = {
            ("ტაქტილური", "tactile", "", 1): [
                "ქვიშა", "კინეტიკური ქვიშა", "ბრინჯი", "ლობიო", "მაკარონი",
                "პლასტელინი", "თიხა", "ქაფი", "გელი", "წყალი", "ღრუბელი",
                "ბეწვი", "სხვადასხვა ქსოვილი", "ხე", "პლასტმასი", "რეზინი",
                "ლითონი", "სხვადასხვა ტექსტურა", "ტაქტილური ბურთი",
                "ტაქტილური ჯაგრისი", "ხელის მასაჟი", "ფეხის მასაჟი",
                "ღრმა ზეწოლა", "მსუბუქი შეხება", "სხვადასხვა ზედაპირზე შეხება",
                "საგნის დამალვა და ძიება", "სენსორულ ყუთში ძიება",
                "ხელებით მასალასთან მუშაობა", "სხვა"
            ],
            ("პროპრიოცეპტული", "proprioceptive", "", 2): [
                "მძიმე საგნის აწევა", "მძიმე საგნის ტარება", "ნივთის მიწოლა",
                "ნივთის გამოწევა", "რეზინის გაწევა", "წინააღმდეგობის წინააღმდეგ მოძრაობა",
                "კედელზე მიწოლა", "ბიძგები", "ხოხვა", "ცოცვა", "ოთხზე დგომა",
                "ხელებზე დაყრდნობა", "სხეულის წონით დატვირთვა", "ხტომა",
                "მძიმე საგნების გადაადგილება", "ბალიშებს შორის ზეწოლა",
                "ღრმა წნევის აქტივობა", "შეკუმშვის ტიპის აქტივობა",
                "მძიმე საბნის გამოყენება", "სხვა"
            ],
            ("ვესტიბულარული", "vestibular", "", 3): [
                "საქანელა", "ჰამაკი", "სრიალი", "ბრუნვა", "ქანაობა",
                "ხტომა", "სირბილი", "ცოცვა", "ბალანსის აქტივობა",
                "ბალანსის ზედაპირი", "სხეულის პოზიციის ცვლილება",
                "მოძრაობა წინ/უკან", "მოძრაობა მარცხნივ/მარჯვნივ",
                "ზემოთ/ქვემოთ", "წრიული მოძრაობა", "დიაგონალური მოძრაობა", "სხვა"
            ],
            ("სმენითი", "auditory", "", 4): [
                "მუსიკა", "ადამიანის ხმა", "ტაში", "მუსიკალური ინსტრუმენტი",
                "ბუნებრივი ხმები", "თეთრი ხმაური", "მექანიკური ხმა",
                "მაღალი სიხშირის ხმა", "დაბალი სიხშირის ხმა", "ხმაურიანი გარემო",
                "მშვიდი გარემო", "სხვა"
            ],
            ("მხედველობითი", "visual", "", 5): [
                "განათება", "ფერები", "კონტრასტული ფერები", "მოძრავი ობიექტი",
                "განათებული ობიექტი", "ბუშტები", "საპნის ბუშტები", "მოძრავი სათამაშო",
                "ვიზუალური ბარათები", "სარკე", "ვიზუალური ძიება", "თვალით მიდევნება",
                "ფორმები", "ფიგურები", "ვიზუალური ორგანიზების აქტივობები", "სხვა"
            ],
            ("ყნოსვითი", "olfactory", "", 6): [
                "საკვების სუნი", "ხილის სუნი", "ყვავილის სუნი", "მცენარის სუნი",
                "საპნის სუნი", "სხვა"
            ],
            ("გემოვნებითი", "gustatory", "", 7): [
                "ტკბილი საკვები/გემო", "მჟავე გემო", "მარილიანი გემო", "მწარე გემო",
                "ნეიტრალური გემო", "რბილი ტექსტურა", "მყარი ტექსტურა",
                "ხრაშუნა ტექსტურა", "წებოვანი ტექსტურა", "პიურესებრი ტექსტურა",
                "თხევადი საკვები", "სხვა"
            ],
            ("ინტერცეპციული", "interoceptive", "", 8): [
                "შიმშილის ამოცნობა", "წყურვილის ამოცნობა", "ტუალეტის საჭიროების ამოცნობა",
                "დაღლილობის აღქმა", "ძილიანობის აღქმა", "სიცივის შეგრძნება",
                "სიცხის შეგრძნება", "ტკივილის ლოკალიზაცია", "გულისცემის აღქმა",
                "სუნთქვის გაცნობიერება", "სხეულის დაძაბულობის აღქმა",
                "სხეულის მდგომარეობის აღქმა", "ემოციური მდგომარეობის ამოცნობა", "სხვა"
            ],
            ("მულტისენსორული", "multisensory", "", 9): [
                "ტაქტილური + პროპრიოცეპტული კომბინაცია",
                "ვესტიბულარული + პროპრიოცეპტული კომბინაცია",
                "ვესტიბულარული + ვიზუალური კომბინაცია",
                "სენსორული დაბრკოლებების ბილიკი",
                "მულტისენსორული სივრცე / კუთხე", "სხვა"
            ]
        }

        for (sys_name, sys_slug, sys_icon, sys_order), activities in catalog.items():
            system_obj, _ = SensorySystem.objects.get_or_create(
                slug=sys_slug,
                defaults={"name": sys_name, "icon": sys_icon, "order": sys_order}
            )
            for act_name in activities:
                SensoryActivity.objects.get_or_create(
                    sensory_system=system_obj,
                    name=act_name
                )
        self.stdout.write("Sensory systems and activities populated.")

        # 4. Sensory Responses
        responses = [
            "მიიღო სტიმული",
            "უარი თქვა",
            "თავიდან აიცილა",
            "ითხოვა გაგრძელება",
            "თვითონ ეძებდა სტიმულს",
            "საჭიროებდა დახმარებას",
            "ჩართულობა გაიზარდა",
            "ჩართულობა შემცირდა",
            "რეგულაციის გაუმჯობესება შეინიშნა",
            "დისტრესის ნიშნები",
            "ნეიტრალური რეაქცია",
            "სხვა"
        ]
        for idx, resp_name in enumerate(responses):
            SensoryResponse.objects.get_or_create(name=resp_name, defaults={"order": idx})

        # 5. Functional Outcomes
        outcomes = [
            "ყურადღების გაზრდა",
            "აქტივობაში ჩართულობა",
            "თვითრეგულაცია",
            "გადასვლის გამარტივება",
            "თამაშში ჩართულობა",
            "წვრილი მოტორიკისთვის მომზადება",
            "თვითმოვლისთვის მომზადება",
            "სასწავლო აქტივობისთვის მომზადება",
            "სოციალური ჩართულობა",
            "სხეულის ცნობიერება",
            "მოტორული დაგეგმვა",
            "დავალების დასრულება",
            "ფუნქციური დამოუკიდებლობა",
            "სხვა"
        ]
        for idx, out_name in enumerate(outcomes):
            FunctionalOutcome.objects.get_or_create(name=out_name, defaults={"order": idx})

        # 6. Sample Beneficiaries
        b1, created1 = Beneficiary.objects.get_or_create(
            first_name="გიორგი",
            last_name="ბერიძე",
            defaults={
                "date_of_birth": date(2019, 5, 14),
                "start_date": date(2024, 1, 15),
                "therapist": therapist_profile,
                "session_duration_minutes": 45,
                "weekly_sessions_planned": 3,
                "notes": "დიაგნოზი: აუტისტური სპექტრი. სენსორული ძიების მაღალი ტენდენცია (პროპრიოცეპტული/ვესტიბულარული)."
            }
        )
        if created1:
            OccupationalProfile.objects.create(
                beneficiary=b1,
                self_care="ჩაცმა საჭიროებს საშუალო დახმარებას. ჭურჭლის გამოყენება დამოუკიდებელია. ხელების დაბანა სიტყვიერი მითითებით.",
                play="ფუნქციური თამაში განვითარებულია, წარმოსახვითი თამაში საჭიროებს თერაპევტის მოდელირებას.",
                attention="აქტივობაში ჩართულობის საწყისი ხანგრძლივობა 3-4 წუთი. სენსორული ინტერვენციის შემდეგ იზრდება 8 წუთამდე.",
                motor_skills="წვრილი მოტორიკა: ფანქრის სამთითა ჩაჭიდება ჩამოყალიბების პროცესშია. ბალანსი კარგია.",
                functional_participation="სასწავლო აქტივობებში ჩართვა რთულდება ხმაურიან გარემოში. გადასვლები მოითხოვს ვიზუალურ განრიგს."
            )
            SensoryProfile.objects.create(
                beneficiary=b1,
                tactile="იღებს სხვადასხვა ტექსტურას (ქვიშა, პლასტელინი), ერიდება წებოვან მასალებს.",
                proprioceptive="მაღალი ძიება: უყვარს მძიმე საგნების ტარება, კედელზე მიწოლა, ხტომა.",
                vestibular="საქანელაზე ხანგრძლივი რწევა მოსწონს, წრიულ ბრუნვას კარგად იტანს.",
                auditory="მგრძნობიარეა მაღალი სიხშირის მოულოდნელ ხმებზე.",
                visual="კარგად რეაგირებს ვიზუალურ ბარათებსა და მკაფიო კონტრასტზე."
            )
            # Goals for b1
            g1 = Goal.objects.create(
                beneficiary=b1,
                therapist=therapist_profile,
                domain="sensory_regulation",
                description="სენსორული რეგულაციის გაუმჯობესება პროპრიოცეპტული აქტივობების მეშვეობით",
                baseline_state="აღგზნებული, ხშირი მოტორული მოუსვენრობა",
                target_state="სტაბილური მდგომარეობა და თვითრეგულაციის უნარი 20 წუთის განმავლობაში",
                metric_unit="წუთი",
                target_date=date(2026, 12, 31),
                status="active"
            )
            g2 = Goal.objects.create(
                beneficiary=b1,
                therapist=therapist_profile,
                domain="attention",
                description="მაგიდის აქტივობაში ყურადღების შენარჩუნება მინიმალური დახმარებით",
                baseline_state="3 წუთი",
                target_state="8-10 წუთი",
                metric_unit="წუთი",
                target_date=date(2026, 11, 30),
                status="active"
            )
            g3 = Goal.objects.create(
                beneficiary=b1,
                therapist=therapist_profile,
                domain="fine_motor",
                description="მაკრატლით სწორ ხაზზე გაჭრა სიტყვიერი მითითებით",
                baseline_state="სრული დახმარება",
                target_state="მცირე დახმარება / დამოუკიდებლად",
                metric_unit="დახმარების დონე",
                target_date=date(2026, 10, 31),
                status="active"
            )

            # Generate sample sessions for current month (September 2026) to demonstrate progress & report
            today = date(2026, 9, 11)
            resp_accepted = SensoryResponse.objects.get(name="მიიღო სტიმული")
            resp_engaged = SensoryResponse.objects.get(name="ჩართულობა გაიზარდა")
            resp_sought = SensoryResponse.objects.get(name="თვითონ ეძებდა სტიმულს")
            resp_regulated = SensoryResponse.objects.get(name="რეგულაციის გაუმჯობესება შეინიშნა")

            fo_attention = FunctionalOutcome.objects.get(name="ყურადღების გაზრდა")
            fo_engagement = FunctionalOutcome.objects.get(name="აქტივობაში ჩართულობა")
            fo_regulation = FunctionalOutcome.objects.get(name="თვითრეგულაცია")

            act_swing = SensoryActivity.objects.get(name="საქანელა")
            act_heavy = SensoryActivity.objects.get(name="მძიმე საგნის ტარება")
            act_sand = SensoryActivity.objects.get(name="კინეტიკური ქვიშა")

            # Session 1: Sept 1
            s1 = Session.objects.create(
                beneficiary=b1, therapist=therapist_profile,
                date=date(2026, 9, 1), duration_minutes=45,
                initial_state="aroused", final_state="stable",
                notes="სესიის დასაწყისში შეინიშნებოდა მაღალი მოტორული აქტივობა. პროპრიოცეპტული დატვირთვის შემდეგ დამშვიდდა."
            )
            s1.goals.add(g1, g2)
            s1.functional_outcomes.add(fo_regulation, fo_attention)
            sa1 = SessionSensoryActivity.objects.create(
                session=s1, sensory_activity=act_heavy, duration_minutes=6,
                intensity="medium", assistance_level="moderate", activity_start="cue"
            )
            sa1.responses.add(resp_accepted, resp_engaged)
            sa2 = SessionSensoryActivity.objects.create(
                session=s1, sensory_activity=act_swing, duration_minutes=5,
                intensity="low", assistance_level="moderate", movement_direction="forward", speed="slow"
            )
            sa2.responses.add(resp_accepted, resp_regulated)

            # Session 2: Sept 4
            s2 = Session.objects.create(
                beneficiary=b1, therapist=therapist_profile,
                date=date(2026, 9, 4), duration_minutes=45,
                initial_state="active", final_state="calm",
                notes="კინეტიკურ ქვიშასთან მუშაობამ გაზარდა ფოკუსირება. მაგიდის აქტივობა შეასრულა 5 წუთის განმავლობაში."
            )
            s2.goals.add(g2, g3)
            s2.functional_outcomes.add(fo_attention, fo_engagement)
            sa3 = SessionSensoryActivity.objects.create(
                session=s2, sensory_activity=act_sand, duration_minutes=7,
                intensity="low", assistance_level="minimal", activity_start="independent"
            )
            sa3.responses.add(resp_accepted, resp_sought, resp_engaged)

            # Session 3: Sept 8
            s3 = Session.objects.create(
                beneficiary=b1, therapist=therapist_profile,
                date=date(2026, 9, 8), duration_minutes=45,
                initial_state="tense", final_state="more_engaged",
                notes="საქანელისა და მძიმე ტვირთის კომბინაციით მიღწეულ იქნა კარგი ჩართულობა."
            )
            s3.goals.add(g1, g2)
            s3.functional_outcomes.add(fo_regulation, fo_engagement)
            sa4 = SessionSensoryActivity.objects.create(
                session=s3, sensory_activity=act_heavy, duration_minutes=8,
                intensity="high", assistance_level="minimal", activity_start="independent"
            )
            sa4.responses.add(resp_accepted, resp_engaged, resp_regulated)

            # Session 4: Sept 11 (Today)
            s4 = Session.objects.create(
                beneficiary=b1, therapist=therapist_profile,
                date=date(2026, 9, 11), duration_minutes=45,
                initial_state="active", final_state="stable",
                notes="ბავშვმა დამოუკიდებლად გამოხატა ინტერესი პროპრიოცეპტული თამაშის მიმართ. ყურადღება მაგიდასთან შენარჩუნდა 8 წუთი."
            )
            s4.goals.add(g1, g2, g3)
            s4.functional_outcomes.add(fo_attention, fo_regulation)
            sa5 = SessionSensoryActivity.objects.create(
                session=s4, sensory_activity=act_heavy, duration_minutes=8,
                intensity="medium", assistance_level="minimal", activity_start="independent"
            )
            sa5.responses.add(resp_sought, resp_engaged, resp_regulated)

        # Beneficiary 2: Nino
        b2, created2 = Beneficiary.objects.get_or_create(
            first_name="ნინო",
            last_name="კაპანაძე",
            defaults={
                "date_of_birth": date(2020, 8, 20),
                "start_date": date(2024, 3, 1),
                "therapist": therapist_profile,
                "session_duration_minutes": 45,
                "weekly_sessions_planned": 2,
                "notes": "ტაქტილური ჰიპერმგრძნობელობა, ყურადღების დეფიციტი."
            }
        )
        if created2:
            OccupationalProfile.objects.create(
                beneficiary=b2,
                self_care="ხელების დაბანისას ერიდება საპნის შეხებას. ჩაცმა დამოუკიდებელია.",
                play="უპირატესობას ანიჭებს მარტო თამაშს, უყვარს კონსტრუქტორი.",
                attention="ხანმოკლე ჩართულობა (2-3 წთ), საჭიროებს ხშირ სტიმულაციას.",
                motor_skills="მოტორული დაგეგმვა კარგია, წვრილი მოტორიკა ასაკობრივი ნორმის ფარგლებში.",
                functional_participation="ჯგუფურ აქტივობებში უჭირს ხანგრძლივად დარჩენა."
            )
            SensoryProfile.objects.create(
                beneficiary=b2,
                tactile="ტაქტილური დაცვითობა: უარს ამბობს სველ და წებოვან მასალებზე.",
                vestibular="ზომიერი ინტერესი საქანელების მიმართ.",
                auditory="მგრძნობიარეა ხმაურზე."
            )
            Goal.objects.create(
                beneficiary=b2,
                therapist=therapist_profile,
                domain="sensory_regulation",
                description="მშრალი ტაქტილური მასალების (ბრინჯი, მარცვლეული) შეხების ტოლერანტობის გაზრდა",
                baseline_state="უარი შეხებაზე",
                target_state="მასალასთან დამოუკიდებელი თამაში 3-5 წთ",
                metric_unit="წუთი",
                target_date=date(2026, 11, 15),
                status="active"
            )
            Goal.objects.create(
                beneficiary=b2,
                therapist=therapist_profile,
                domain="attention",
                description="დავალების დასრულება 1 სიტყვიერი მითითებით",
                baseline_state="დიდი დახმარება",
                target_state="მცირე დახმარება",
                metric_unit="დახმარების დონე",
                target_date=date(2026, 10, 30),
                status="active"
            )

        self.stdout.write(self.style.SUCCESS("All catalog and sample data loaded successfully!"))
