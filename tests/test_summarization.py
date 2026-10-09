import io
import pytest
from app.models import MedicalRecord, User

def test_generate_document_summary(auth_client_a, app, user_a):
    """Test generating a structured AI summary for an uploaded medical record."""
    pdf_content = b"%PDF-1.4\n%Electrocardiogram normal sinus rhythm at 72 bpm. PR interval: 160ms. QRS: 88ms.\n%%EOF"
    auth_client_a.post('/records/upload', data={
        'title': '12-Lead Resting ECG Report',
        'category': 'Cardiology & ECG Reports',
        'report_date': '2026-04-20',
        'doctor_or_facility': 'Boston Cardiology Associates',
        'notes': 'Normal sinus rhythm 72 bpm without ischemic ST-T changes.',
        'document_file': (io.BytesIO(pdf_content), 'ecg_test.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)

    with app.app_context():
        records = MedicalRecord.find_by_user(user_a)
        assert len(records) == 1
        rec = records[0]
        rec_id = rec.id

    # Trigger AI summarization
    response = auth_client_a.post(f'/ai/summarize/{rec_id}', json={})
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('success') is True
    assert 'summary' in data
    assert 'Key Diagnostic Findings' in data['summary']

    with app.app_context():
        updated_rec = MedicalRecord.get_by_id(rec_id)
        assert updated_rec.ai_summary is not None
        assert updated_rec.ai_summary_date is not None

def test_summarization_idor_protection(client, user_a, user_b, login_as, app):
    """
    CRITICAL SECURITY TEST:
    Verify that User B cannot trigger summarization on User A's medical record.
    """
    # 1. Login as User A and upload record
    login_as(client, user_a)
    pdf_content = b"%PDF-1.4\n%Private Ultrasound Scan\n%%EOF"
    client.post('/records/upload', data={
        'title': 'Abdominal Ultrasound',
        'category': 'Imaging & Radiology (X-Ray/MRI/CT)',
        'report_date': '2026-05-10',
        'document_file': (io.BytesIO(pdf_content), 'us_scan.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)

    with app.app_context():
        records = MedicalRecord.find_by_user(user_a)
        assert len(records) == 1
        rec_id = records[0].id

    # 2. Login as User B (Bob)
    login_as(client, user_b)

    # 3. User B attempts to summarize User A's record -> Should receive 403 Forbidden
    response = client.post(f'/ai/summarize/{rec_id}')
    assert response.status_code in [403, 404]
