import io
import pytest
from app.models import MedicalRecord
from app.database import get_db

def test_upload_medical_record_pdf(auth_client_a, app, user_a):
    """Test uploading a valid PDF medical record."""
    pdf_content = b"%PDF-1.4\n%Fake PDF content for testing\n%%EOF"
    data = {
        'title': 'Lipid Panel Report',
        'category': 'Laboratory & Blood Tests',
        'report_date': '2026-05-10',
        'doctor_or_facility': 'Quest Diagnostics',
        'notes': 'Normal HDL and LDL levels.',
        'document_file': (io.BytesIO(pdf_content), 'lipid_panel.pdf')
    }

    response = auth_client_a.post('/records/upload', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b"Lipid Panel Report" in response.data

    with app.app_context():
        records = MedicalRecord.find_by_user(user_a)
        assert len(records) == 1
        rec = records[0]
        assert rec.title == 'Lipid Panel Report'
        assert rec.category == 'Laboratory & Blood Tests'
        assert rec.is_pdf is True
        assert rec.doctor_or_facility == 'Quest Diagnostics'

def test_upload_invalid_file_format(auth_client_a):
    """Test rejection of executable or non-allowed file extension."""
    exe_content = b"MZ\x90\x00Fake executable content"
    data = {
        'title': 'Suspicious File',
        'category': 'Other Medical Records',
        'report_date': '2026-05-10',
        'document_file': (io.BytesIO(exe_content), 'malware.exe')
    }

    response = auth_client_a.post('/records/upload', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert b"is not supported" in response.data

def test_idor_protection_record_access(client, user_a, user_b, login_as, app):
    """
    CRITICAL SECURITY TEST:
    Verify that User B cannot view, download, edit, or delete User A's medical records.
    """
    # 1. Login as Alice and upload record
    login_as(client, user_a)
    pdf_content = b"%PDF-1.4\n%Secret health data\n%%EOF"
    client.post('/records/upload', data={
        'title': 'Private Cardiology Report',
        'category': 'Cardiology & ECG Reports',
        'report_date': '2026-06-01',
        'document_file': (io.BytesIO(pdf_content), 'cardiology.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)

    with app.app_context():
        records = MedicalRecord.find_by_user(user_a)
        assert len(records) == 1
        record = records[0]
        assert str(record.user_id) == str(user_a)
        record_id = record.id

    # 2. Login as User B (Bob)
    login_as(client, user_b)

    # 3. User B tries to view User A's record -> Should receive 403 Forbidden
    view_resp = client.get(f'/records/{record_id}')
    assert view_resp.status_code == 403

    # 4. User B tries to download User A's file -> Should receive 403 Forbidden
    download_resp = client.get(f'/records/{record_id}/file')
    assert download_resp.status_code == 403

    # 5. User B tries to edit User A's record -> Should receive 403 Forbidden
    edit_resp = client.post(f'/records/{record_id}/edit', data={
        'title': 'Hacked Title',
        'category': 'Laboratory & Blood Tests',
        'report_date': '2026-06-01'
    })
    assert edit_resp.status_code == 403

    # 6. User B tries to delete User A's record -> Should receive 403 Forbidden
    delete_resp = client.post(f'/records/{record_id}/delete')
    assert delete_resp.status_code == 403

def test_search_and_filter_records(auth_client_a):
    """Test searching and filtering records."""
    pdf_1 = b"%PDF-1.4\n%Doc 1\n%%EOF"
    pdf_2 = b"%PDF-1.4\n%Doc 2\n%%EOF"
    
    auth_client_a.post('/records/upload', data={
        'title': 'Blood Glucose Test',
        'category': 'Laboratory & Blood Tests',
        'report_date': '2026-01-15',
        'document_file': (io.BytesIO(pdf_1), 'glucose.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)

    auth_client_a.post('/records/upload', data={
        'title': 'Chest X-Ray Scan',
        'category': 'Imaging & Radiology (X-Ray/MRI/CT)',
        'report_date': '2026-02-20',
        'document_file': (io.BytesIO(pdf_2), 'xray.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)

    # Search for Glucose
    search_resp = auth_client_a.get('/records/?q=Glucose')
    assert b"Blood Glucose Test" in search_resp.data
    assert b"Chest X-Ray Scan" not in search_resp.data

    # Filter for Imaging
    filter_resp = auth_client_a.get('/records/?category=Imaging+%26+Radiology+(X-Ray%2FMRI%2FCT)')
    assert b"Chest X-Ray Scan" in filter_resp.data
    assert b"Blood Glucose Test" not in filter_resp.data

def test_record_edit_and_delete_cleanup(auth_client_a, app, user_a):
    """Test editing a record, replacing its file, and deleting with physical file cleanup."""
    import os
    pdf_content = b"%PDF-1.4\n%Initial Record\n%%EOF"
    auth_client_a.post('/records/upload', data={
        'title': 'Initial Scan',
        'category': 'Imaging & Radiology (X-Ray/MRI/CT)',
        'report_date': '2026-03-01',
        'document_file': (io.BytesIO(pdf_content), 'scan1.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)

    with app.app_context():
        records = MedicalRecord.find_by_user(user_a)
        assert len(records) == 1
        rec = records[0]
        rec_id = rec.id
        stored_file_1 = rec.stored_filename
        storage_path = os.path.join(app.config['STORAGE_FOLDER'], f"user_{user_a}", stored_file_1)
        assert os.path.exists(storage_path)

    # Edit and replace file
    new_pdf_content = b"%PDF-1.4\n%Updated Scan\n%%EOF"
    edit_resp = auth_client_a.post(f'/records/{rec_id}/edit', data={
        'title': 'Updated Scan Title',
        'category': 'Imaging & Radiology (X-Ray/MRI/CT)',
        'report_date': '2026-03-05',
        'document_file': (io.BytesIO(new_pdf_content), 'scan2.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)
    assert edit_resp.status_code == 200

    with app.app_context():
        rec_updated = MedicalRecord.get_by_id(rec_id)
        assert rec_updated.title == 'Updated Scan Title'
        stored_file_2 = rec_updated.stored_filename
        storage_path_2 = os.path.join(app.config['STORAGE_FOLDER'], f"user_{user_a}", stored_file_2)
        assert os.path.exists(storage_path_2)

    # Delete record
    del_resp = auth_client_a.post(f'/records/{rec_id}/delete', follow_redirects=True)
    assert del_resp.status_code == 200

    with app.app_context():
        assert MedicalRecord.get_by_id(rec_id) is None
        assert not os.path.exists(storage_path_2)

def test_nonexistent_record_404(auth_client_a):
    """Test accessing a non-existent or invalid record ID returns 404."""
    resp = auth_client_a.get('/records/nonexistent_record_id_12345')
    assert resp.status_code == 404

