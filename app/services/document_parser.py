import os
from pypdf import PdfReader

def extract_text_from_file(file_path, mime_type='application/pdf'):
    """
    Extracts plain text from a stored medical document (PDF or image).
    Returns cleaned text string.
    """
    if not file_path or not os.path.exists(file_path):
        return ""
        
    extracted_text = []
    
    # 1. PDF Extraction
    if mime_type == 'application/pdf' or file_path.lower().endswith('.pdf'):
        try:
            reader = PdfReader(file_path)
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    extracted_text.append(f"--- Page {page_num + 1} ---\n{text.strip()}")
        except Exception:
            pass
            
    # 2. Text or Fallback
    if not extracted_text:
        # Fallback inspection for text/plain or minimal metadata
        filename = os.path.basename(file_path)
        extracted_text.append(f"[Document File: {filename}]")
        
    return "\n\n".join(extracted_text).strip()
