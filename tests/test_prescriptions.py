import io
import pytest
from app.models import Prescription

def test_add_and_view_prescription(auth_client_a, app, user_a):
    """Test creating and viewing a prescription."""
    pdf_content = b"%PDF-1.4\n%Prescription Scan\n%%EOF"
    data = {
        'title': 'Amoxicillin Antibiotic Course',
        'date': '2026-03-15',
        'doctor_name': 'Dr. Henderson, DDS',
        'medications_info': 'Amoxicillin 500mg - Take 1 capsule three times daily for 7 days.',
        'notes': 'Take with food to prevent stomach upset.',
        'document_file': (io.BytesIO(pdf_content), 'rx_amoxicillin.pdf')
    }

    response = auth_client_a.post('/prescriptions/add', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b"Amoxicillin Antibiotic Course" in response.data

    with app.app_context():
        prescriptions = Prescription.find_by_user(user_a, is_archived=False)
        assert len(prescriptions) == 1
        rx = prescriptions[0]
        assert rx.doctor_name == 'Dr. Henderson, DDS'
        assert rx.is_archived is False

def test_toggle_prescription_archive(auth_client_a, app, user_a):
    """Test archiving and unarchiving prescriptions."""
    auth_client_a.post('/prescriptions/add', data={
        'title': 'Past Allergy Medication',
        'date': '2025-08-01',
        'doctor_name': 'Dr. Allison',
        'medications_info': 'Cetirizine 10mg once daily.'
    }, follow_redirects=True)

    with app.app_context():
        prescriptions = Prescription.find_by_user(user_a, is_archived=False)
        rx = prescriptions[0]
        rx_id = rx.id
        assert rx.is_archived is False

    # Toggle to archived
    auth_client_a.post(f'/prescriptions/{rx_id}/toggle-archive', follow_redirects=True)

    with app.app_context():
        rx = Prescription.get_by_id(rx_id)
        assert rx.is_archived is True

    # Active view should not contain archived item
    active_resp = auth_client_a.get('/prescriptions/?archived=0')
    assert b"Past Allergy Medication" not in active_resp.data

    # Archived view should contain it
    archived_resp = auth_client_a.get('/prescriptions/?archived=1')
    assert b"Past Allergy Medication" in archived_resp.data

def test_prescription_idor_protection(client, user_a, user_b, login_as, app):
    """Test that User B cannot edit or delete User A's prescription."""
    # 1. Login as Alice and add prescription
    login_as(client, user_a)
    client.post('/prescriptions/add', data={
        'title': 'Confidential Prescription',
        'date': '2026-04-10',
        'doctor_name': 'Dr. Secret'
    }, follow_redirects=True)

    with app.app_context():
        prescriptions = Prescription.find_by_user(user_a, is_archived=False)
        rx = prescriptions[0]
        assert str(rx.user_id) == str(user_a)
        rx_id = rx.id

    # 2. Login as User B (Bob)
    login_as(client, user_b)

    # 3. User B attempts to edit User A's rx -> 403 Forbidden
    edit_resp = client.post(f'/prescriptions/{rx_id}/edit', data={
        'title': 'Hacked RX',
        'date': '2026-04-10'
    })
    assert edit_resp.status_code == 403

    # 4. User B attempts to delete User A's rx -> 403 Forbidden
    del_resp = client.post(f'/prescriptions/{rx_id}/delete')
    assert del_resp.status_code == 403

def test_prescription_edit_and_delete(auth_client_a, app, user_a):
    """Test editing prescription details and deleting prescription."""
    auth_client_a.post('/prescriptions/add', data={
        'title': 'Original Rx',
        'date': '2026-01-10',
        'doctor_name': 'Dr. First',
        'medications_info': 'Meds info'
    }, follow_redirects=True)

    with app.app_context():
        rxs = Prescription.find_by_user(user_a)
        assert len(rxs) == 1
        rx_id = rxs[0].id

    # Edit
    edit_resp = auth_client_a.post(f'/prescriptions/{rx_id}/edit', data={
        'title': 'Modified Rx Title',
        'date': '2026-01-15',
        'doctor_name': 'Dr. Updated',
        'medications_info': 'Updated meds info'
    }, follow_redirects=True)
    assert edit_resp.status_code == 200

    with app.app_context():
        rx = Prescription.get_by_id(rx_id)
        assert rx.title == 'Modified Rx Title'
        assert rx.doctor_name == 'Dr. Updated'

    # Delete
    del_resp = auth_client_a.post(f'/prescriptions/{rx_id}/delete', follow_redirects=True)
    assert del_resp.status_code == 200

    with app.app_context():
        assert Prescription.get_by_id(rx_id) is None

