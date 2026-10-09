# MediVault – Personal Health Record Manager

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/framework-Flask%203.0%2B-000000.svg)](https://flask.palletsprojects.com/)
[![MongoDB](https://img.shields.io/badge/database-MongoDB%20%2F%20PyMongo-47A248.svg)](https://www.mongodb.com/)
[![Bootstrap 5](https://img.shields.io/badge/styling-Bootstrap%205.3-7952B3.svg)](https://getbootstrap.com/)
[![Security: OWASP Isolated](https://img.shields.io/badge/security-IDOR%20Protected-brightgreen.svg)]()
[![AI Features: RAG & Voice](https://img.shields.io/badge/AI-RAG%20Chat%20%26%20Voice%20Agent-4B8BBE.svg)]()

> **MediVault** is a full-stack, classical healthcare management web platform built to securely organize, categorize, and preserve personal health records, diagnostic scan reports, doctor prescriptions, and clinical appointments in a private, high-security environment with integrated **AI Medical Record Chat**, **Automated Report Summarization**, **Multi-Channel Reminders**, and **Interactive Voice Reminder Calls**.

---

## 🌟 Key Platform Features

### 1. 🏛️ Classical Healthcare Design System
- **Professional Aesthetics:** Classical navy-blue (`#0f2942`), clinical teal-blue (`#1e6091`), and subtle health-green (`#2a7e58`) accents on a clean white background.
- **Accessibility & Contrast:** Clear typography, rectangular cards, standard table layouts, and high-contrast light/dark mode.
- **Zero AI Distractions:** No excessive neon gradients, floating widgets, or distracting glassmorphism.

### 2. 🔐 User Authentication & Identity Protection
- **PBKDF2 Password Hashing:** Werkzeug secure cryptographic hashing; plain-text passwords are never stored.
- **Unique Email Indexing:** MongoDB unique index prevents duplicate registration.
- **Password Recovery Flow:** Token-based recovery with 2-hour expiration and single-use invalidation.
- **Account Purge & GDPR/HIPAA Alignment:** One-click account deletion permanently removes user profile, MongoDB collections, and all physical files from disk.

### 3. 📂 Medical Records Management & Document Viewer
- **Universal Medical Formats:** Upload diagnostic reports in PDF, PNG, JPG, JPEG, and WebP (up to 16 MB).
- **Categorization:** Lab Results, Prescriptions, Radiology & Imaging (X-Ray/MRI/CT), Hospital Discharge Summaries, Cardiology/ECG, Vaccination Logs, and General Health.
- **Built-in Document Viewer:** Inline PDF & image rendering directly within the browser.
- **Search & Sort:** Instant query filtering by document title, doctor/facility, notes, category, or report date.

### 4. 🤖 AI Chatbot for Medical Records (RAG Engine)
- **Grounded Retrieval-Augmented Generation (RAG):** Patients can ask natural-language questions about their uploaded lab tests, imaging reports, prescriptions, and visits.
- **Strict User-Level Access Isolation:** The RAG pipeline indexes and queries *only* the authenticated user's authorized health documents.
- **Document Citations & Verification:** Responses include clickable citations pointing to the original document for patient verification.
- **Clinical Safety Disclaimer:** Prominently states that AI assistance does not provide medical diagnoses or replace professional medical advice.

### 5. 📄 AI-Based Medical Report Summarization
- **PDF & Document Parsing:** Extracts textual and clinical data from uploaded diagnostic reports and scans.
- **Structured Clinical Breakdown:** Generates clear summaries with 4 structured sections:
  1. *Key Diagnostic Findings*
  2. *Clinical Biomarkers & Numerical Values*
  3. *Physician Recommendations*
  4. *Patient Action Items*
- **Persistent Storage:** Summaries are saved alongside document metadata in MongoDB for instant review.

### 6. 🔔 Multi-Channel Appointment Reminders & Notifications
- **In-App Notification Center:** Real-time unread badge counter in the top bar with mark as read / delete capabilities.
- **Configurable Delivery Channels:** Enable or disable Email, SMS (via Twilio), or Voice Phone Reminders.
- **Customizable Timing (Lead Times):** Configure alerts for 24 hours prior, 2 hours prior, or 1 week in advance.
- **Background Scheduler:** Automated worker checking upcoming appointments and dispatching due reminders without duplicates (idempotency logging in `reminder_logs`).

### 7. 📞 AI Voice Agent for Automated Appointment Reminders
- **Telephony Integration:** Built on Twilio Voice API and TwiML for automated patient reminder calls.
- **Interactive Voice Response (IVR):** Text-to-Speech (TTS) speaks appointment details and captures keypad (DTMF) or speech input:
  - **Press 1 / Say "Confirm"**: Confirms attendance.
  - **Press 2 / Say "Reschedule"**: Records request to reschedule.
  - **Press 3 / Say "Opt Out"**: Instantly opts out of future automated phone calls.
- **Privacy Standard:** Never speaks detailed diagnostic details or confidential conditions over the telephone.
- **Call Session Logs:** Tracks timestamps, call delivery status (`Initiated`, `Ringing`, `Answered`, `Completed`, `Failed`), and IVR outcomes in MongoDB.

---

## 🏗️ Architecture & MongoDB Database Schema

```
medivault_db
├── users
│   ├── _id: ObjectId
│   ├── full_name: String
│   ├── email: String (Unique Index)
│   ├── password_hash: String
│   ├── phone_number: String
│   ├── ai_consent: Boolean
│   ├── voice_opt_in: Boolean
│   ├── reminder_preferences: Object { email, sms, voice, lead_times }
│   └── created_at / updated_at: Date
│
├── medical_records
│   ├── _id: ObjectId
│   ├── user_id: ObjectId (Index)
│   ├── title: String (Index)
│   ├── category: String (Index)
│   ├── report_date: String / Date (Index)
│   ├── doctor_or_facility: String
│   ├── notes: String
│   ├── file_reference: Object { stored_filename, original_filename, file_size, mime_type }
│   ├── ai_summary: String
│   ├── ai_summary_date: Date
│   └── extracted_text: String
│
├── prescriptions
│   ├── _id: ObjectId
│   ├── user_id: ObjectId (Index)
│   ├── title: String
│   ├── prescription_date: String / Date (Index)
│   ├── clinician_name: String
│   ├── medication_notes: String
│   ├── is_archived: Boolean (Index)
│   └── file_reference: Object
│
├── appointments
│   ├── _id: ObjectId
│   ├── user_id: ObjectId (Index)
│   ├── clinician_or_hospital: String
│   ├── appointment_date: String / Date (Index)
│   ├── appointment_time: String
│   ├── location: String
│   ├── purpose: String
│   └── status: String ("Upcoming" | "Completed" | "Cancelled")
│
├── chat_sessions & chat_messages
│   ├── session_id: ObjectId (Index)
│   ├── user_id: ObjectId (Index)
│   ├── sender: String ("user" | "assistant")
│   ├── content: String
│   └── citations: Array of Objects [{ id, title, type, date, url }]
│
├── notifications
│   ├── user_id: ObjectId (Index)
│   ├── title: String
│   ├── message: String
│   ├── type: String
│   ├── is_read: Boolean (Index)
│   └── created_at: Date
│
├── voice_call_logs
│   ├── user_id: ObjectId (Index)
│   ├── appointment_id: ObjectId (Index)
│   ├── call_sid: String (Index)
│   ├── to_phone: String
│   ├── status: String
│   └── user_response: String
│
└── reminder_logs (Idempotent Deduplication)
    ├── appointment_id: ObjectId
    ├── reminder_type: String
    └── lead_time: String (Unique Compound Index)
```

---

## 🚀 Quickstart & Installation Guide

### Step 1: Clone Repository & Set Up Virtual Environment
```bash
git clone https://github.com/your-org/medivault.git
cd medivault

# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
copy .env.example .env
```
Configure your credentials for MongoDB, AI Services (OpenAI / Gemini), and Telephony (Twilio).

### Step 4: Populate Simulated Demo Patient Data
```bash
python seed.py
```
> **Default Demo Patient Account:**
> - **Email:** `demo.patient@medivault-health.org`
> - **Password:** `DemoPassword123`

### Step 5: Start the Development Server
```bash
python run.py
```
Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in your web browser.

---

## 🧪 Automated Testing Suite

Execute the complete automated test suite (30 unit & integration tests covering all features and security isolation):

```bash
pytest -v
```

### Test Coverage Summary:
- `tests/test_auth.py`: User registration, duplicate emails, password recovery tokens, authentication sessions, and account purge.
- `tests/test_records.py`: File upload magic bytes, file deletion, and cross-user authorization enforcement (403 Forbidden).
- `tests/test_prescriptions.py`: Creation, medication notes, active/archived toggling, and IDOR protection.
- `tests/test_appointments.py`: Scheduling, status lifecycle (`Upcoming` -> `Completed`/`Cancelled`), and ownership isolation.
- `tests/test_ai_chat.py`: RAG question answering, citation verification, patient consent checking, and cross-user chat isolation.
- `tests/test_summarization.py`: Automated structured clinical summary extraction and security isolation.
- `tests/test_notifications.py`: In-app notification center, unread polling, multi-channel preferences, and duplicate prevention deduplication.
- `tests/test_voice_agent.py`: Automated voice call initiation, TwiML `<Gather>` IVR generation, and patient keypad/speech responses.

---

## 🔒 Security & Privacy Summary

| Threat / Requirement | MediVault Implementation |
|---|---|
| **Broken Access Control (IDOR)** | Strict user-id verification on every route, query, and AI retrieval context. |
| **Private Document Storage** | Files stored in isolated directories (`storage/user_<id>/`) outside web roots; served only through authenticated streaming endpoints. |
| **Magic Byte Validation** | Server-side binary header inspection validates authentic PDF, PNG, and JPEG signatures. |
| **Telephony Privacy** | Automated voice calls omit confidential diagnoses; speak only time, physician, and location. |
| **Patient AI Consent** | Explicit consent toggle required before indexing records for AI processing. |
| **Data Retention** | Permanent account deletion cascades to all collections and purges the physical file folder from disk. |

---

## 📄 License
This project is open source and available under the [MIT License](LICENSE).
>>>>>>> 1bb09fb (Initial commit: MediVault Personal Health Record Manager with minimal homepage and OTP authentication)
