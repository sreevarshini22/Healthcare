import io
import pytest
from app.models import MedicalRecord, Prescription, ChatSession, ChatMessage, User
from app.services.ai_service import chat_with_medical_records, retrieve_relevant_documents

def test_ai_chat_consent_check(auth_client_a, app, user_a):
    """Test that chat requires user consent before processing."""
    with app.app_context():
        user = User.get_by_id(user_a)
        user.update_ai_consent(False)
        
    response = auth_client_a.post('/ai/chat/send', json={'message': 'What are my lab results?'})
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('require_consent') is True

def test_ai_chat_query_with_citations(auth_client_a, app, user_a):
    """Test asking questions about uploaded medical records and receiving grounded citations."""
    # 1. Enable AI consent
    auth_client_a.post('/ai/chat/consent', json={'ai_consent': True})
    
    # 2. Upload test records
    pdf_content = b"%PDF-1.4\n%Fasting Blood Glucose: 92 mg/dL. Total Cholesterol: 185 mg/dL.\n%%EOF"
    auth_client_a.post('/records/upload', data={
        'title': 'Metabolic Panel & Cholesterol',
        'category': 'Laboratory & Blood Tests',
        'report_date': '2026-05-15',
        'doctor_or_facility': 'Quest Lab Diagnostics',
        'notes': 'Fasting glucose 92 mg/dL and cholesterol 185 mg/dL normal.',
        'document_file': (io.BytesIO(pdf_content), 'metabolic_test.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)

    # 3. Ask AI about glucose and cholesterol
    response = auth_client_a.post('/ai/chat/send', json={
        'message': 'What were my cholesterol and glucose test values?'
    })
    
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('success') is True
    assert 'answer' in data
    assert len(data.get('citations', [])) > 0
    assert any('Metabolic Panel' in cit['title'] for cit in data['citations'])

def test_ai_chat_idor_isolation(client, user_a, user_b, login_as, app):
    """
    CRITICAL SECURITY TEST:
    Verify that User B cannot retrieve or search User A's private medical records using the AI Chatbot.
    """
    # 1. User A (Alice) logs in and uploads private record
    login_as(client, user_a)
    client.post('/ai/chat/consent', json={'ai_consent': True})
    
    pdf_content = b"%PDF-1.4\n%Confidential Diagnosis: Secret Condition XYZ\n%%EOF"
    client.post('/records/upload', data={
        'title': 'Confidential Patient Alpha Record',
        'category': 'Other Medical Records',
        'report_date': '2026-06-01',
        'notes': 'Highly confidential diagnosis details Alpha.',
        'document_file': (io.BytesIO(pdf_content), 'confidential_alpha.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)

    # 2. User B (Bob) logs in
    login_as(client, user_b)
    client.post('/ai/chat/consent', json={'ai_consent': True})

    # 3. User B queries AI about Alpha Record
    with app.app_context():
        docs = retrieve_relevant_documents(user_b, "Confidential Patient Alpha Record")
        # Should not find any of User A's documents
        assert len(docs) == 0

    response = client.post('/ai/chat/send', json={'message': 'Tell me about Confidential Patient Alpha Record'})
    data = response.get_json()
    assert data.get('success') is True
    # Verify no citations from User A
    assert len(data.get('citations', [])) == 0
    assert "could not find any medical records" in data.get('answer').lower()
