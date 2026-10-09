from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from app.models import MedicalRecord, ChatSession, ChatMessage, User
from app.services.ai_service import chat_with_medical_records, generate_document_summary, MEDICAL_DISCLAIMER
from app.utils.helpers import log_activity

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')

@ai_bp.route('/chat')
@login_required
def chat():
    """AI Medical Records Chatbot Interface."""
    sessions = ChatSession.get_user_sessions(current_user.id)
    session_id = request.args.get('session_id')
    
    current_session = None
    messages = []
    
    if session_id:
        current_session = ChatSession.get_by_id(session_id, current_user.id)
        if current_session:
            messages = ChatMessage.get_session_messages(current_session.id, current_user.id)
            
    if not current_session and sessions:
        current_session = sessions[0]
        messages = ChatMessage.get_session_messages(current_session.id, current_user.id)
        
    records_count = len(MedicalRecord.find_by_user(current_user.id))
    
    return render_template(
        'ai/chat.html',
        sessions=sessions,
        current_session=current_session,
        messages=messages,
        records_count=records_count,
        disclaimer=MEDICAL_DISCLAIMER
    )


@ai_bp.route('/chat/send', methods=['POST'])
@login_required
def send_message():
    """Process a patient question through the RAG engine and return grounded answer."""
    data = request.get_json() or request.form
    query = data.get('message', '').strip()
    session_id = data.get('session_id')
    
    if not query:
        if request.is_json:
            return jsonify({'error': 'Message content is required.'}), 400
        flash("Please enter a question.", "warning")
        return redirect(url_for('ai.chat', session_id=session_id))
        
    # Check user consent
    if not current_user.ai_consent:
        if request.is_json:
            return jsonify({
                'require_consent': True,
                'message': 'Please provide consent to process your medical documents with MediVault AI.'
            }), 200
            
    result = chat_with_medical_records(current_user.id, query, session_id=session_id)
    log_activity(current_user.id, "AI Medical Query", f"Asked: '{query[:50]}...'")
    
    if request.is_json:
        return jsonify({
            'success': True,
            'answer': result['answer'],
            'citations': result['citations'],
            'session_id': result['session_id'],
            'disclaimer': result['disclaimer']
        })
        
    return redirect(url_for('ai.chat', session_id=result['session_id']))


@ai_bp.route('/chat/consent', methods=['POST'])
@login_required
def update_consent():
    """Toggle user consent for AI medical record analysis."""
    consent = request.form.get('ai_consent') == '1' or (request.get_json() or {}).get('ai_consent', False)
    current_user.update_ai_consent(consent)
    log_activity(current_user.id, "AI Consent Updated", f"Consent set to {consent}")
    
    if request.is_json:
        return jsonify({'success': True, 'ai_consent': consent})
        
    flash("AI processing preferences updated successfully.", "success")
    return redirect(url_for('ai.chat'))


@ai_bp.route('/chat/clear', methods=['POST'])
@login_required
def clear_chat():
    """Clear or delete a chat conversation session."""
    session_id = request.form.get('session_id')
    if session_id:
        ChatSession.delete(session_id, current_user.id)
        flash("Conversation deleted successfully.", "info")
    return redirect(url_for('ai.chat'))


@ai_bp.route('/summarize/<record_id>', methods=['POST'])
@login_required
def summarize_record(record_id):
    """Generate or refresh an AI structured summary for a specific medical document."""
    record = MedicalRecord.get_by_id(record_id, current_user.id)
    if not record:
        abort(404)
        
    if str(record.user_id) != str(current_user.id):
        abort(403)
        
    summary_text = generate_document_summary(record, current_user)
    log_activity(current_user.id, "Generated AI Summary", f"Summarized '{record.title}'")
    
    if request.is_json:
        return jsonify({
            'success': True,
            'summary': summary_text,
            'record_id': record.id
        })
        
    flash("Medical document summary generated successfully.", "success")
    return redirect(url_for('records.view_record', record_id=record.id))
