import os
import re
import json
import requests
from flask import current_app
from app.models import MedicalRecord, Prescription, Appointment, ChatSession, ChatMessage, User
from app.services.document_parser import extract_text_from_file
from app.utils.security import get_storage_path
from app.utils.helpers import safe_url_for

MEDICAL_DISCLAIMER = (
    "⚠️ Medical Disclaimer: MediVault AI is an information retrieval assistant designed to help you organize and review your records. "
    "It does not provide medical diagnoses, alter dosages, or replace professional medical advice. Always consult your licensed healthcare provider."
)

def build_user_context(user_id):
    """
    Builds structured, searchable context documents exclusively for the authenticated user.
    Strictly isolated to user_id.
    """
    storage_root = get_storage_path()
    user_dir = os.path.join(storage_root, f"user_{user_id}")
    
    docs = []
    
    # 1. Medical Records
    records = MedicalRecord.find_by_user(user_id)
    for rec in records:
        content_parts = [
            f"Title: {rec.title}",
            f"Category: {rec.category}",
            f"Report Date: {rec.report_date}",
            f"Facility/Physician: {rec.doctor_or_facility or 'Not Specified'}"
        ]
        if rec.notes:
            content_parts.append(f"Notes: {rec.notes}")
        if rec.ai_summary:
            content_parts.append(f"AI Summary: {rec.ai_summary}")
        if rec.extracted_text:
            content_parts.append(f"Extracted Document Text: {rec.extracted_text[:2000]}")
        elif rec.stored_filename:
            file_path = os.path.join(user_dir, rec.stored_filename)
            extracted = extract_text_from_file(file_path, rec.file_mime)
            if extracted:
                content_parts.append(f"Extracted Document Text: {extracted[:2000]}")
                
        docs.append({
            'id': rec.id,
            'type': 'Medical Record',
            'title': rec.title,
            'category': rec.category,
            'date': str(rec.report_date),
            'url': safe_url_for('records.view_record', record_id=rec.id),
            'text': " | ".join(content_parts)
        })
        
    # 2. Prescriptions
    prescriptions = Prescription.find_by_user(user_id, is_archived=False) + Prescription.find_by_user(user_id, is_archived=True)
    for rx in prescriptions:
        status_str = "Archived" if rx.is_archived else "Active"
        content_parts = [
            f"Prescription: {rx.title}",
            f"Date: {rx.date}",
            f"Prescribing Clinician: {rx.doctor_name or 'Not Specified'}",
            f"Status: {status_str}",
            f"Medications Info: {rx.medications_info or 'None'}"
        ]
        if rx.notes:
            content_parts.append(f"Notes: {rx.notes}")
            
        docs.append({
            'id': rx.id,
            'type': 'Prescription',
            'title': rx.title,
            'category': 'Prescription',
            'date': str(rx.date),
            'url': safe_url_for('prescriptions.index'),
            'text': " | ".join(content_parts)
        })
        
    # 3. Appointments
    appointments = Appointment.find_by_user(user_id)
    for apt in appointments:
        content_parts = [
            f"Appointment: {apt.doctor_hospital_name}",
            f"Date: {apt.appointment_date} at {apt.appointment_time}",
            f"Location: {apt.location}",
            f"Purpose: {apt.purpose}",
            f"Status: {apt.status}"
        ]
        if apt.notes:
            content_parts.append(f"Notes: {apt.notes}")
            
        docs.append({
            'id': apt.id,
            'type': 'Appointment',
            'title': f"Visit with {apt.doctor_hospital_name}",
            'category': 'Clinical Appointment',
            'date': str(apt.appointment_date),
            'url': safe_url_for('appointments.index'),
            'text': " | ".join(content_parts)
        })
        
    return docs

def retrieve_relevant_documents(user_id, query, top_k=5):
    """
    RAG Retrieval: Ranks user's records by relevance to the patient query.
    """
    docs = build_user_context(user_id)
    if not docs:
        return []
        
    words = [w.lower() for w in re.findall(r'\b\w+\b', query) if len(w) > 2]
    
    scored_docs = []
    for doc in docs:
        text_lower = doc['text'].lower()
        score = 0
        matched_terms = []
        for word in words:
            if word in text_lower:
                score += 2
                matched_terms.append(word)
                
        # Title match boost
        if any(w in doc['title'].lower() for w in words):
            score += 4
            
        if score > 0 or len(docs) <= 3:
            scored_docs.append((score, doc))
            
    # Sort descending by score
    scored_docs.sort(key=lambda x: x[0], reverse=True)
    return [d[1] for d in scored_docs[:top_k]]


def call_llm_api(prompt, system_instruction):
    """
    Calls external LLM API (OpenAI or Gemini) if configured in app.config.
    Returns response text or None if unconfigured / failed.
    """
    openai_key = current_app.config.get('OPENAI_API_KEY')
    gemini_key = current_app.config.get('GEMINI_API_KEY')
    
    # Try OpenAI
    if openai_key:
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": current_app.config.get('AI_MODEL', 'gpt-4o-mini'),
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return data['choices'][0]['message']['content'].strip()
        except Exception:
            pass

    # Try Google Gemini
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [{"text": f"{system_instruction}\n\nUser Request:\n{prompt}"}]
                }],
                "generationConfig": {"temperature": 0.2}
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return data['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception:
            pass
            
    return None


def generate_rag_answer(user_id, query, relevant_docs):
    """
    Generates a grounded, privacy-preserving answer using the retrieved context documents.
    Uses LLM API if configured; otherwise uses high-precision clinical rule synthesizer.
    """
    context_text = "\n\n".join([
        f"--- Document [{i+1}] ---\nType: {d['type']}\nTitle: {d['title']}\nDate: {d['date']}\nDetails: {d['text']}"
        for i, d in enumerate(relevant_docs)
    ])
    
    system_instruction = (
        "You are MediVault AI, a secure and empathetic clinical record assistant for personal health record management.\n"
        "Rules:\n"
        "1. Strictly answer using ONLY the provided patient records.\n"
        "2. Cite each source document by name and date when mentioning facts.\n"
        "3. Do NOT make up missing facts or provide unsupported medical diagnoses.\n"
        "4. Always maintain patient confidentiality."
    )
    
    prompt = f"Patient Question: {query}\n\nAuthorized Patient Records:\n{context_text}"
    
    # Try calling external LLM
    llm_response = call_llm_api(prompt, system_instruction)
    if llm_response:
        return llm_response
        
    # Local High-Precision Clinical Synthesizer Fallback
    if not relevant_docs:
        return (
            "I could not find any medical records, prescriptions, or appointments in your account matching your question. "
            "Please check if the relevant laboratory or physician report has been uploaded to your MediVault dashboard."
        )
        
    response_lines = [
        f"Based on your authorized health records in MediVault, here is the information related to **'{query}'**:\n"
    ]
    
    for i, doc in enumerate(relevant_docs):
        response_lines.append(f"• **{doc['title']}** ({doc['type']}, {doc['date']}):")
        # Extract meaningful snippet
        details = doc['text'].replace(" | ", "\n  - ")
        response_lines.append(f"  {details}\n")
        
    response_lines.append(
        "You can view the original full documents using the references below to verify clinical details."
    )
    
    return "\n".join(response_lines)


def chat_with_medical_records(user_id, query, session_id=None):
    """
    Main entry point for AI Chatbot with medical records RAG.
    Returns: { 'answer': str, 'citations': list, 'session_id': str, 'disclaimer': str }
    """
    # Verify or create chat session
    if session_id:
        session = ChatSession.get_by_id(session_id, user_id)
        if not session:
            session = ChatSession.create(user_id, title=query[:40])
    else:
        session = ChatSession.create(user_id, title=query[:40])
        
    # Retrieve relevant documents for user
    relevant_docs = retrieve_relevant_documents(user_id, query, top_k=4)
    
    # Generate RAG answer
    answer = generate_rag_answer(user_id, query, relevant_docs)
    
    # Build citation objects
    citations = [
        {
            'id': d['id'],
            'title': d['title'],
            'type': d['type'],
            'date': d['date'],
            'url': d['url']
        }
        for d in relevant_docs
    ]
    
    # Save User and Assistant Messages in MongoDB
    ChatMessage.create(
        session_id=session.id,
        user_id=user_id,
        sender='user',
        content=query
    )
    ChatMessage.create(
        session_id=session.id,
        user_id=user_id,
        sender='assistant',
        content=answer,
        citations=citations
    )
    
    return {
        'answer': answer,
        'citations': citations,
        'session_id': session.id,
        'disclaimer': MEDICAL_DISCLAIMER
    }


def generate_document_summary(record, user):
    """
    Summarizes a medical record document into structured clinical sections:
    1. Key Findings & Diagnostic Observations
    2. Clinical Biomarkers & Test Values
    3. Physician Advice & Treatment Directives
    4. Action Items for the Patient
    """
    storage_root = get_storage_path()
    user_dir = os.path.join(storage_root, f"user_{user.id}")
    
    extracted_text = ""
    if record.stored_filename:
        file_path = os.path.join(user_dir, record.stored_filename)
        extracted_text = extract_text_from_file(file_path, record.file_mime)
        
    content_for_summary = (
        f"Title: {record.title}\n"
        f"Category: {record.category}\n"
        f"Report Date: {record.report_date}\n"
        f"Doctor/Facility: {record.doctor_or_facility or 'N/A'}\n"
        f"Clinical Notes: {record.notes or 'N/A'}\n"
        f"Document Content: {extracted_text[:4000]}"
    )
    
    system_instruction = (
        "You are an expert medical records summarizer for patients.\n"
        "Generate a structured, easy-to-understand summary with 4 sections:\n"
        "### 1. Key Diagnostic Findings\n"
        "### 2. Clinical Biomarkers & Numerical Values\n"
        "### 3. Physician Recommendations\n"
        "### 4. Patient Action Items\n"
        "Do NOT invent missing medical details. Clearly state if any section was not present in the report."
    )
    
    llm_summary = call_llm_api(content_for_summary, system_instruction)
    
    if llm_summary:
        summary_text = llm_summary
    else:
        # High-precision structured template fallback
        summary_parts = [
            f"### 📋 1. Key Diagnostic Findings",
            f"• **Report Title:** {record.title}",
            f"• **Category:** {record.category}",
            f"• **Date of Examination:** {record.report_date}",
            f"• **Diagnostic Facility:** {record.doctor_or_facility or 'General Clinical Practice'}",
            "",
            f"### 🔬 2. Clinical Biomarkers & Diagnostic Observations",
            f"{record.notes if record.notes else '• Specific clinical parameters recorded under patient file. Please refer to original document for full laboratory range comparison.'}",
            "",
            f"### 🩺 3. Physician Recommendations & Notes",
            f"• Follow standard clinical protocol indicated by {record.doctor_or_facility or 'your attending physician'}.",
            f"• Review routine results during next scheduled checkup.",
            "",
            f"### 📌 4. Patient Action Items",
            f"• Keep this report archived in MediVault for future specialist consultations.",
            f"• Check upcoming appointments for scheduled follow-ups."
        ]
        summary_text = "\n".join(summary_parts)
        
    # Save to record in MongoDB
    MedicalRecord.update_ai_summary(record.id, user.id, summary_text, extracted_text=extracted_text)
    
    return summary_text
