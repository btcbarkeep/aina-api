"""
PDF Redaction System for Aina Protocol

This module provides automated PDF redaction capabilities using PyMuPDF (fitz)
to detect and redact sensitive information including emails, phone numbers,
TMK patterns, owner names, addresses, and contractor license numbers.
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
# Pattern Definitions
# ======================================================

# Email pattern
EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    re.IGNORECASE
)

# Phone number patterns (US format)
PHONE_PATTERN = re.compile(
    r'\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b'
)

# TMK pattern (Tax Map Key - Hawaii property identifier)
# Format: X-X-X-XXX-XXX-XXX or similar variations
TMK_PATTERN = re.compile(
    r'\b\d{1,3}[-.\s]?\d{1,3}[-.\s]?\d{1,3}[-.\s]?\d{1,3}[-.\s]?\d{1,3}[-.\s]?\d{1,3}\b'
)

# Contractor license number patterns (various formats)
# Common formats: ABC-12345, ABC12345, 12345-ABC, etc.
CONTRACTOR_LICENSE_PATTERN = re.compile(
    r'\b[A-Z]{2,4}[-.\s]?\d{4,8}\b|\b\d{4,8}[-.\s]?[A-Z]{2,4}\b'
)

# Address patterns (loose matching)
# Matches common address formats
ADDRESS_PATTERN = re.compile(
    r'\b\d+\s+[A-Za-z0-9\s,.-]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|Highway|Hwy)[\s,.-]*(?:[A-Za-z]{2,}\s+)?\d{5}(?:-\d{4})?\b',
    re.IGNORECASE
)

# Owner name patterns (loose matching - common name patterns)
# Matches "Owner:", "Property Owner:", names with titles, etc.
OWNER_NAME_PATTERN = re.compile(
    r'\b(?:Owner|Property Owner|Owner Name)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b',
    re.IGNORECASE
)

# Additional loose name pattern (First Last format)
OWNER_NAME_LOOSE_PATTERN = re.compile(
    r'\b(?:Mr\.|Mrs\.|Ms\.|Dr\.)?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)\b'
)


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
    Find all sensitive patterns in text.
    
    Args:
        text: Text to search
        
    Returns:
        List of tuples: (pattern_type, matched_text)
    """
    matches = []
    
    # Find emails
    for match in EMAIL_PATTERN.finditer(text):
        matches.append(("email", match.group()))
    
    # Find phone numbers
    for match in PHONE_PATTERN.finditer(text):
        matches.append(("phone", match.group()))
    
    # Find TMK patterns
    for match in TMK_PATTERN.finditer(text):
        matches.append(("tmk", match.group()))
    
    # Find contractor license numbers
    for match in CONTRACTOR_LICENSE_PATTERN.finditer(text):
        matches.append(("contractor_license", match.group()))
    
    # Find addresses
    for match in ADDRESS_PATTERN.finditer(text):
        matches.append(("address", match.group()))
    
    # Find owner names (structured)
    for match in OWNER_NAME_PATTERN.finditer(text):
        matches.append(("owner_name", match.group(1)))
    
    # Find owner names (loose)
    for match in OWNER_NAME_LOOSE_PATTERN.finditer(text):
        # Filter out common false positives
        name = match.group(1).strip()
        if len(name.split()) >= 2 and len(name) > 5:
            matches.append(("owner_name", name))
    
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
            logger.info(f"Page {page_num + 1}: No extractable text, attempting OCR...")
            text = ocr_page_to_text(page)
            if not text:
                logger.warning(f"Page {page_num + 1}: No text found via OCR, skipping pattern matching")
                continue
        
        # Find sensitive patterns
        matches = find_sensitive_patterns(text)
        
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
        for pattern_type, search_text in matches:
            try:
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

