"""
MediVault - Sample Demonstration Data Seeder
Populates simulated, non-real demonstration accounts and medical entries in MongoDB for testing.
"""
import os
from datetime import date, timedelta
from app import create_app
from app.models import User, MedicalRecord, Prescription, Appointment, ActivityLog
from app.utils.security import get_storage_path

def seed_demo_data():
    app = create_app()
    with app.app_context():
        demo_email = "demo.patient@medivault-health.org"
        existing = User.get_by_email(demo_email)
        if existing:
            print(f"Demo user '{demo_email}' already exists.")
            return

        print("Creating demonstration user and sample healthcare records in MongoDB...")

        demo_user = User.create_user(
            full_name="Sarah Miller",
            email=demo_email,
            password="DemoPassword123",
            phone_number="(617) 555-0142",
            blood_group="O+",
            emergency_contact="David Miller (Spouse) - (617) 555-0199",
            theme_preference="light"
        )

        today = date.today()
        today_str = today.isoformat()

        # Create user storage folder and dummy PDF / Image file
        storage_root = get_storage_path()
        user_dir = os.path.join(storage_root, f"user_{demo_user.id}")
        os.makedirs(user_dir, exist_ok=True)

        # Sample dummy PDF
        pdf_name = "sample_lab_report.pdf"
        pdf_path = os.path.join(user_dir, pdf_name)
        with open(pdf_path, 'wb') as f:
            f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000053 00000 n \n0000000102 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n178\n%%EOF")

        # Sample dummy PNG
        png_name = "sample_scan.png"
        png_path = os.path.join(user_dir, png_name)
        with open(png_path, 'wb') as f:
            # Minimal 1x1 PNG
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')

        # Add sample medical records
        MedicalRecord.create(
            user_id=demo_user.id,
            title="Comprehensive Metabolic Panel & Lipid Profile",
            category="Laboratory & Blood Tests",
            report_date=(today - timedelta(days=12)).isoformat(),
            doctor_or_facility="Memorial Health Clinical Pathology",
            file_info={
                'stored_filename': pdf_name,
                'original_filename': "CMP_Lipid_Panel_2026.pdf",
                'file_size': os.path.getsize(pdf_path),
                'mime_type': 'application/pdf'
            },
            notes="Fasting glucose: 92 mg/dL. Total Cholesterol: 185 mg/dL. Triglycerides: 130 mg/dL. All metabolic parameters within normal clinical limits."
        )

        MedicalRecord.create(
            user_id=demo_user.id,
            title="Chest X-Ray PA & Lateral View",
            category="Imaging & Radiology (X-Ray/MRI/CT)",
            report_date=(today - timedelta(days=60)).isoformat(),
            doctor_or_facility="City Imaging Diagnostic Center",
            file_info={
                'stored_filename': png_name,
                'original_filename': "Chest_XRay_PA_Lat.png",
                'file_size': os.path.getsize(png_path),
                'mime_type': 'image/png'
            },
            notes="Lungs clear bilaterally. No focal consolidation, pneumothorax, or pleural effusion. Cardiac silhouette normal in size."
        )

        # Add sample appointments
        Appointment.create(
            user_id=demo_user.id,
            doctor_hospital_name="Dr. Eleanor Vance, MD (Cardiology)",
            appointment_date=(today + timedelta(days=7)).isoformat(),
            appointment_time="10:30 AM",
            location="Boston Heart Center, Suite 402",
            purpose="Routine 6-Month Cardiovascular Follow-up & BP Monitoring",
            status="Upcoming",
            notes="Bring 14-day home blood pressure monitoring log."
        )

        Appointment.create(
            user_id=demo_user.id,
            doctor_hospital_name="City Radiology Diagnostic Center",
            appointment_date=(today + timedelta(days=21)).isoformat(),
            appointment_time="02:00 PM",
            location="Imaging Pavilion, Room 104",
            purpose="Routine Preventive Screening Mammogram",
            status="Upcoming",
            notes="No lotions or powders on the morning of scan."
        )

        Appointment.create(
            user_id=demo_user.id,
            doctor_hospital_name="Dr. Kevin Thorne (Dental Care)",
            appointment_date=(today - timedelta(days=45)).isoformat(),
            appointment_time="09:00 AM",
            location="Pinehurst Family Dentistry",
            purpose="Annual Dental Cleaning & Panoramic X-Rays",
            status="Completed",
            notes="All teeth healthy; schedule next cleaning in 6 months."
        )

        # Add sample prescriptions
        Prescription.create(
            user_id=demo_user.id,
            title="Cardiovascular Regimen",
            date_val=(today - timedelta(days=30)).isoformat(),
            doctor_name="Dr. Eleanor Vance, MD",
            medications_info="1. Lisinopril 10mg - Take 1 tablet daily every morning.\n2. Atorvastatin 20mg - Take 1 tablet daily before bedtime.",
            file_info={
                'stored_filename': pdf_name,
                'original_filename': "Rx_Cardiology_Vance.pdf",
                'file_size': os.path.getsize(pdf_path),
                'mime_type': 'application/pdf'
            },
            notes="Refills: 3 remaining at CVS Pharmacy #104."
        )

        Prescription.create(
            user_id=demo_user.id,
            title="Post-Dental Treatment Antibiotics",
            date_val=(today - timedelta(days=45)).isoformat(),
            doctor_name="Dr. Kevin Thorne",
            medications_info="Amoxicillin 500mg - Take 1 capsule 3 times daily for 7 days with meals.",
            notes="Completed 7-day course."
        )

        # Add sample activity logs
        ActivityLog.log(demo_user.id, "Account Created", "User registration and setup completed.")
        ActivityLog.log(demo_user.id, "Uploaded Record", "Added 'Comprehensive Metabolic Panel & Lipid Profile'.")
        ActivityLog.log(demo_user.id, "Added Prescription", "Recorded 'Cardiovascular Regimen'.")
        ActivityLog.log(demo_user.id, "Scheduled Appointment", "Booked visit with Dr. Eleanor Vance.")

        print("Demonstration data seeded into MongoDB successfully!")
        print("Demo Credentials:")
        print("  Email:    demo.patient@medivault-health.org")
        print("  Password: DemoPassword123")

if __name__ == '__main__':
    seed_demo_data()
