"""
PDF Redaction System for Aina Protocol

This module provides automated PDF redaction capabilities using PyMuPDF (fitz)
to detect and redact owner-related sensitive information including owner names,
owner emails, and owner phone numbers when preceded by owner context keywords.
"""

import io
import re
import shutil
import logging
from pathlib import Path
from typing import List, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    raise ImportError("PyMuPDF (fitz) is required. Install with: pip install PyMuPDF")

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logging.warning("pytesseract and/or PIL not available. OCR fallback will be disabled.")

from core.logging_config import logger


# ======================================================
# Pattern Definitions - Owner Context Patterns
# ======================================================

# Only redact when owner-related words are present
OWNER_CONTEXT_PATTERNS = [
    # Owner names when preceded by context words
    r"(?i)(Owner|Unit Owner|Owner Name|Homeowner|Tenant|Contact)\s*[:\-]?\s+[A-Za-z ,.'\-]+",
    
    # Owner email
    r"(?i)(Owner|Contact|Tenant).{0,10}[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    
    # Owner phone
    r"(?i)(Owner|Contact|Tenant).{0,10}\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
]

# Compile all patterns (all are case-insensitive)
COMPILED_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in OWNER_CONTEXT_PATTERNS
]

# Whitelist words - matches containing these words will be skipped
WHITELIST = [
    "Cost", "Prepared", "Contractor License", "LLC", "Lahaina", "HI", "Project", "Roof", "Replacement",
    "Scope", "Description", "Labor", "Equipment", "Flashing",
    "Venting", "Underlayment", "Shingles", "Metal", "Scaffolding"
]


# ======================================================
# Helper Functions
# ======================================================

def has_text(page: fitz.Page) -> bool:
    """
    Check if a PDF page has extractable text.
    
    Args:
        page: PyMuPDF Page object
        
    Returns:
        True if the page has extractable text, False otherwise
    """
    try:
        text = page.get_text().strip()
        return len(text) > 0
    except Exception as e:
        logger.warning(f"Error checking for text on page {page.number}: {e}")
        return False


def ocr_page_to_text(page: fitz.Page) -> str:
    """
    Extract text from a PDF page using OCR (pytesseract).
    
    Args:
        page: PyMuPDF Page object
        
    Returns:
        Extracted text as string, empty string if OCR fails or is unavailable
    """
    if not OCR_AVAILABLE:
        logger.warning("OCR not available. Install pytesseract and PIL to enable OCR.")
        return ""
    
    try:
        # Render page as image
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR quality
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        
        # Run OCR
        text = pytesseract.image_to_string(img)
        logger.info(f"OCR extracted {len(text)} characters from page {page.number}")
        return text
    except Exception as e:
        logger.error(f"OCR failed on page {page.number}: {e}")
        return ""


# ======================================================
# Pattern Matching Functions
# ======================================================

def find_sensitive_patterns(text: str) -> List[Tuple[str, str]]:
    """
    Find all sensitive patterns in text using owner context-based pattern matching.
    Only matches patterns that are preceded by owner-related keywords.
    
    Args:
        text: Text to search
        
    Returns:
        List of tuples: (pattern_type, matched_text)
    """
    matches = []
    pattern_types = ["owner_name", "owner_email", "owner_phone"]
    
    # Iterate through all compiled patterns
    for pattern_type, compiled_pattern in zip(pattern_types, COMPILED_PATTERNS):
        # Ensure we only process owner patterns (safeguard for OCR usage)
        # OCR is ONLY used for owner-related patterns
        if pattern_type not in {"owner_name", "owner_email", "owner_phone"}:
            continue  # skip OCR for non-owner patterns
        
        for match in compiled_pattern.finditer(text):
            matched_text = match.group()
            
            # Extract the actual sensitive data from the match
            if pattern_type == "owner_name":
                # Extract just the name part (after the keyword and colon/dash)
                name_match = re.search(r"[:\-]?\s+([A-Za-z ,.'\-]+)", matched_text, re.IGNORECASE)
                if name_match:
                    extracted_name = name_match.group(1).strip()
                    # Only add if it looks like a name (has at least 2 words)
                    if len(extracted_name.split()) >= 2:
                        matches.append((pattern_type, extracted_name))
            elif pattern_type == "owner_email":
                # Extract just the email part (after the keyword)
                email_match = re.search(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", matched_text, re.IGNORECASE)
                if email_match:
                    matches.append((pattern_type, email_match.group(1)))
            elif pattern_type == "owner_phone":
                # Extract just the phone number part (after the keyword)
                phone_match = re.search(r"(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})", matched_text)
                if phone_match:
                    matches.append((pattern_type, phone_match.group(1)))
    
    return matches


# ======================================================
# Main Redaction Function
# ======================================================

def apply_redactions(input_path: str, output_path: str) -> None:
    """
    Apply redactions to a PDF file based on sensitive pattern detection.
    
    This function:
    1. Loads the PDF using PyMuPDF
    2. Extracts text per page (or uses OCR if no text)
    3. Searches for sensitive patterns
    4. Adds redaction annotations
    5. Applies redactions and saves to output_path
    
    If no sensitive data is found, the file is still copied to output_path.
    
    Args:
        input_path: Path to input PDF file
        output_path: Path to save redacted PDF file
        
    Raises:
        FileNotFoundError: If input_path does not exist
        Exception: For PDF processing errors
    """
    input_path_obj = Path(input_path)
    output_path_obj = Path(output_path)
    
    # Validate input file exists
    if not input_path_obj.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    logger.info(f"Starting PDF redaction: {input_path} -> {output_path}")
    
    # Open PDF
    try:
        doc = fitz.open(input_path)
    except Exception as e:
        logger.error(f"Failed to open PDF: {e}")
        raise
    
    total_redactions = 0
    pages_with_redactions = 0
    
    # Process each page
    for page_num in range(len(doc)):
        page = doc[page_num]
        logger.info(f"Processing page {page_num + 1}/{len(doc)}")
        
        # Extract text
        text = ""
        if has_text(page):
            text = page.get_text()
            logger.debug(f"Page {page_num + 1}: Extracted {len(text)} characters from text layer")
        else:
            # OCR is ONLY used for owner-related patterns
            logger.info(f"Page {page_num + 1}: No extractable text, attempting OCR for owner patterns only...")
            text = ocr_page_to_text(page)
            if not text:
                logger.warning(f"Page {page_num + 1}: No text found via OCR, skipping pattern matching")
                continue
        
        # Find sensitive patterns (only owner-related patterns)
        matches = find_sensitive_patterns(text)
        
        # Filter matches to ensure we only process owner patterns
        # This is a safeguard - OCR should only be used for owner patterns
        owner_pattern_types = {"owner_name", "owner_email", "owner_phone"}
        filtered_matches = []
        for pattern_type, matched_text in matches:
            if pattern_type in owner_pattern_types:
                filtered_matches.append((pattern_type, matched_text))
            else:
                logger.debug(f"Page {page_num + 1}: Skipping non-owner pattern '{pattern_type}' (OCR only for owner patterns)")
                continue  # skip OCR for non-owner patterns
        
        matches = filtered_matches
        
        if not matches:
            logger.debug(f"Page {page_num + 1}: No sensitive patterns found")
            continue
        
        logger.info(f"Page {page_num + 1}: Found {len(matches)} sensitive pattern(s)")
        
        # Group matches by type for logging
        match_types = {}
        for pattern_type, matched_text in matches:
            if pattern_type not in match_types:
                match_types[pattern_type] = []
            match_types[pattern_type].append(matched_text)
        
        for pattern_type, texts in match_types.items():
            logger.info(f"  - {pattern_type}: {len(texts)} match(es)")
            for text_match in texts[:3]:  # Log first 3 examples
                logger.debug(f"    Example: {text_match[:50]}...")
        
        # Locate and redact each match
        page_redactions = 0
        # Context keywords that must be present in the context window
        context_keywords = ["owner", "unit owner", "homeowner", "contact", "tenant"]
        
        for pattern_type, search_text in matches:
            try:
                # Check whitelist - skip if match contains any whitelist word
                if any(word.lower() in search_text.lower() for word in WHITELIST):
                    logger.debug(f"Page {page_num + 1}: Skipping redaction for '{search_text}' - contains whitelist word")
                    continue  # skip
                
                # Find the match position in the text to extract context
                match_pos = text.find(search_text)
                if match_pos == -1:
                    # Try case-insensitive search
                    match_pos = text.lower().find(search_text.lower())
                
                if match_pos == -1:
                    # Match not found in text, skip redaction
                    logger.debug(f"Page {page_num + 1}: Match '{search_text}' not found in text, skipping redaction")
                    continue
                
                # Extract 50-80 character context window around the matched text
                # Using 60 characters as middle ground (50-80 range)
                start_pos = max(0, match_pos - 60)
                end_pos = min(len(text), match_pos + len(search_text) + 60)
                context = text[start_pos:end_pos].lower()
                
                # Check if context includes owner keywords
                has_owner_context = any(c in context for c in context_keywords)
                
                # Check if matched text is purely numeric (allowing commas and periods)
                # Remove commas, periods, and spaces, then check if remaining is all digits
                numeric_text = search_text.replace(",", "").replace(".", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                is_purely_numeric = numeric_text.isdigit() and len(numeric_text) > 0
                
                # If purely numeric and no owner context, skip redaction
                if is_purely_numeric and not has_owner_context:
                    logger.debug(f"Page {page_num + 1}: Skipping redaction for '{search_text}' - purely numeric without owner context")
                    continue  # skip the redaction
                
                # Only allow redaction if ANY of the context keywords appear
                if not has_owner_context:
                    logger.debug(f"Page {page_num + 1}: Skipping redaction for '{search_text}' - no owner context found in window")
                    continue  # DO NOT REDACT OUTSIDE OWNER CONTEXT
                
                logger.debug(f"Page {page_num + 1}: Owner context found for '{search_text}', proceeding with redaction")
                
                # Search for text instances on the page
                text_instances = page.search_for(search_text)
                
                if not text_instances:
                    # Try searching for parts of the text if full match fails
                    words = search_text.split()
                    if len(words) > 1:
                        # Try searching for first few words
                        partial_text = " ".join(words[:2])
                        text_instances = page.search_for(partial_text)
                
                # Add redaction annotation for each instance
                for inst in text_instances:
                    # Create redaction annotation with solid black fill
                    redaction = page.add_redact_annot(inst, fill=(0, 0, 0))  # Black fill
                    page_redactions += 1
                    total_redactions += 1
                    
            except Exception as e:
                logger.warning(f"Failed to redact '{search_text}' on page {page_num + 1}: {e}")
                continue
        
        # Apply redactions on this page
        if page_redactions > 0:
            try:
                page.apply_redactions()
                pages_with_redactions += 1
                logger.info(f"Page {page_num + 1}: Applied {page_redactions} redaction(s)")
            except Exception as e:
                logger.error(f"Failed to apply redactions on page {page_num + 1}: {e}")
    
    # Save or copy the PDF
    try:
        if total_redactions > 0:
            # Save redacted PDF
            doc.save(output_path_obj, garbage=4, deflate=True)
            logger.info(f"Redacted PDF saved: {output_path} ({total_redactions} redactions on {pages_with_redactions} pages)")
        else:
            # No redactions found, copy original file
            logger.info("No sensitive patterns found, copying original file")
            shutil.copy2(input_path, output_path)
            logger.info(f"File copied to: {output_path}")
    except Exception as e:
        logger.error(f"Failed to save PDF: {e}")
        raise
    finally:
        doc.close()

