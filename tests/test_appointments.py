import pytest
from datetime import date, timedelta
from app.models import Appointment

def test_schedule_and_view_appointment(auth_client_a, app, user_a):
    """Test scheduling and viewing an appointment in MongoDB."""
    future_date = (date.today() + timedelta(days=14)).isoformat()
    data = {
        'doctor_hospital_name': 'Dr. Robert Vance, Neurologist',
        'appointment_date': future_date,
        'appointment_time': '14:30',
        'location': 'Neuroscience Center, Floor 4',
        'purpose': 'Migraine evaluation and treatment plan review',
        'status': 'Upcoming',
        'notes': 'Bring headache diary from the past 3 months.'
    }

    response = auth_client_a.post('/appointments/add', data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Dr. Robert Vance, Neurologist" in response.data

    with app.app_context():
        appointments = Appointment.find_by_user(user_a)
        assert len(appointments) == 1
        apt = appointments[0]
        assert apt.doctor_hospital_name == 'Dr. Robert Vance, Neurologist'
        assert apt.status == 'Upcoming'
        assert apt.appointment_time == '14:30'

def test_appointment_status_update(auth_client_a, app, user_a):
    """Test changing status from Upcoming to Completed / Cancelled."""
    apt_date = (date.today() + timedelta(days=2)).isoformat()
    auth_client_a.post('/appointments/add', data={
        'doctor_hospital_name': 'City Vision Clinic',
        'appointment_date': apt_date,
        'appointment_time': '11:00',
        'location': 'Suite 100',
        'purpose': 'Eye Exam',
        'status': 'Upcoming'
    }, follow_redirects=True)

    with app.app_context():
        appointments = Appointment.find_by_user(user_a)
        apt = appointments[0]
        apt_id = apt.id

    # Update status to Completed
    auth_client_a.post(f'/appointments/{apt_id}/status', data={'status': 'Completed'}, follow_redirects=True)

    with app.app_context():
        apt = Appointment.get_by_id(apt_id)
        assert apt.status == 'Completed'

def test_appointment_idor_protection(client, user_a, user_b, login_as, app):
    """Test that User B cannot edit or delete User A's appointment."""
    # 1. Login as Alice and schedule appointment
    login_as(client, user_a)
    apt_date = (date.today() + timedelta(days=5)).isoformat()
    client.post('/appointments/add', data={
        'doctor_hospital_name': 'Private Orthopedic Consult',
        'appointment_date': apt_date,
        'appointment_time': '09:00',
        'location': 'West Wing Room 202',
        'purpose': 'Knee MRI review',
        'status': 'Upcoming'
    }, follow_redirects=True)

    with app.app_context():
        appointments = Appointment.find_by_user(user_a)
        apt = appointments[0]
        assert str(apt.user_id) == str(user_a)
        apt_id = apt.id

    # 2. Login as User B (Bob)
    login_as(client, user_b)

    # 3. User B attempts to edit User A's appointment -> 403 Forbidden
    edit_resp = client.post(f'/appointments/{apt_id}/edit', data={
        'doctor_hospital_name': 'Hacked',
        'appointment_date': apt_date,
        'appointment_time': '09:00',
        'location': 'Hacked',
        'purpose': 'Hacked'
    })
    assert edit_resp.status_code == 403

    # 4. User B attempts to delete User A's appointment -> 403 Forbidden
    del_resp = client.post(f'/appointments/{apt_id}/delete')
    assert del_resp.status_code == 403

def test_appointment_edit_and_delete(auth_client_a, app, user_a):
    """Test editing appointment details and deleting an appointment."""
    future_date = (date.today() + timedelta(days=10)).isoformat()
    auth_client_a.post('/appointments/add', data={
        'doctor_hospital_name': 'Original Clinic',
        'appointment_date': future_date,
        'appointment_time': '10:00',
        'location': 'Room 101',
        'purpose': 'Consult',
        'status': 'Upcoming'
    }, follow_redirects=True)

    with app.app_context():
        apts = Appointment.find_by_user(user_a)
        assert len(apts) == 1
        apt_id = apts[0].id

    # Edit
    new_date = (date.today() + timedelta(days=12)).isoformat()
    edit_resp = auth_client_a.post(f'/appointments/{apt_id}/edit', data={
        'doctor_hospital_name': 'Updated Clinic',
        'appointment_date': new_date,
        'appointment_time': '11:30',
        'location': 'Room 202',
        'purpose': 'Follow-up Consult',
        'status': 'Upcoming'
    }, follow_redirects=True)
    assert edit_resp.status_code == 200

    with app.app_context():
        apt = Appointment.get_by_id(apt_id)
        assert apt.doctor_hospital_name == 'Updated Clinic'
        assert apt.appointment_time == '11:30'

    # Delete
    del_resp = auth_client_a.post(f'/appointments/{apt_id}/delete', follow_redirects=True)
    assert del_resp.status_code == 200

    with app.app_context():
        assert Appointment.get_by_id(apt_id) is None

