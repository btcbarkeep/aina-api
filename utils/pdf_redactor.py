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
from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    import fitz  # PyMuPDF

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False
    fitz = None  # Set to None so the module can still load

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
    
    # Owner email (also match standalone Email:)
    r"(?i)(Owner|Contact|Tenant|Email).{0,10}[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    
    # Owner phone (also match standalone Phone:)
    r"(?i)(Owner|Contact|Tenant|Phone).{0,10}\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
    
    # SSN (with context)
    r"(?i)(Social Security|SSN|S\.S\.N\.).{0,10}\d{3}[-.\s]?\d{2}[-.\s]?\d{4}",
    
    # Credit card numbers (with context) - more specific pattern
    r"(?i)(Credit Card|Card Number|CC#|CC Number).{0,10}\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}",
    
    # Addresses (with context) - more controlled pattern
    r"(?i)(Home Address|Address)\s*[:\-]?\s+\d+[\s\w,.-]{0,50}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Way|Drive|Dr)[\s\w,.-]{0,30}",
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

# Owner Context Keywords
OWNER_CONTEXT_KEYWORDS = [
    "owner", "unit owner", "homeowner", "contact", "tenant"
]

# Sensitive Keywords - always redact if these appear in context, even without owner context
SENSITIVE_KEYWORDS = [
    "social security", "ssn",
    "credit card", "card number", "cc#",
    "home address",
    "routing number", "account number"
]


# ======================================================
# Helper Functions
# ======================================================

def has_text(page) -> bool:
    """
    Check if a PDF page has extractable text.
    
    Args:
        page: PyMuPDF Page object
        
    Returns:
        True if the page has extractable text, False otherwise
    """
    try:
        blocks = page.get_text("blocks")
        page_text = " ".join(b[4] for b in blocks if len(b) > 4)
        return len(page_text.strip()) > 0
    except Exception as e:
        logger.warning(f"Error checking for text on page {page.number}: {e}")
        return False


def ocr_page_to_text(page) -> str:
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
    pattern_types = ["owner_name", "owner_email", "owner_phone", "ssn", "credit_card", "address"]
    
    # Iterate through all compiled patterns
    for pattern_type, compiled_pattern in zip(pattern_types, COMPILED_PATTERNS):
        # Ensure we only process owner patterns for OCR (safeguard for OCR usage)
        # OCR is ONLY used for owner-related patterns
        if pattern_type not in {"owner_name", "owner_email", "owner_phone"}:
            # For non-owner patterns, still check but note they won't use OCR
            pass
        
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
            elif pattern_type == "ssn":
                # Extract just the SSN part (XXX-XX-XXXX format)
                ssn_match = re.search(r"(\d{3}[-.\s]?\d{2}[-.\s]?\d{4})", matched_text)
                if ssn_match:
                    matches.append((pattern_type, ssn_match.group(1)))
            elif pattern_type == "credit_card":
                # Extract just the credit card number part
                # Match digits with optional spaces/dashes between them (13-19 digits total)
                cc_match = re.search(r"([\d][\d\s-]{11,17}[\d])", matched_text)
                if cc_match:
                    # Clean up the card number (normalize spaces)
                    cc_number = re.sub(r"\s+", " ", cc_match.group(1).strip())
                    # Ensure we have at least 13 digits
                    digit_count = len(re.sub(r"[^\d]", "", cc_number))
                    if digit_count >= 13 and digit_count <= 19:
                        matches.append((pattern_type, cc_number))
            elif pattern_type == "address":
                # Extract the address part (after the keyword and colon)
                # Match from number to street type, then optionally city/state/zip
                addr_match = re.search(r"[:\-]?\s+(\d+[\s\w,.-]{0,50}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Way|Drive|Dr)[\s\w,.-]{0,30})", matched_text, re.IGNORECASE)
                if addr_match:
                    addr = addr_match.group(1).strip()
                    # Stop at newline or next major keyword to avoid over-capturing
                    addr = re.split(r'\n|Social Security|Credit Card|Phone|Email', addr)[0].strip()
                    addr = re.sub(r'\s+', ' ', addr)  # Normalize whitespace
                    matches.append((pattern_type, addr))
    
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
        ImportError: If PyMuPDF is not installed
        Exception: For PDF processing errors
    """
    if not FITZ_AVAILABLE:
        raise ImportError("PyMuPDF (fitz) is required. Install with: pip install PyMuPDF")
    
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
        
        # Extract text using block-based extraction
        page_text = ""
        if has_text(page):
            blocks = page.get_text("blocks")
            page_text = " ".join(b[4] for b in blocks if len(b) > 4)
            logger.debug(f"Page {page_num + 1}: Extracted {len(page_text)} characters from text layer")
        else:
            # OCR is ONLY used for owner-related patterns
            logger.info(f"Page {page_num + 1}: No extractable text, attempting OCR for owner patterns only...")
            page_text = ocr_page_to_text(page)
            if not page_text:
                logger.warning(f"Page {page_num + 1}: No text found via OCR, skipping pattern matching")
                continue
        
        # Find sensitive patterns
        matches = find_sensitive_patterns(page_text)
        
        # Only filter matches if we used OCR (OCR should only be used for owner patterns)
        # If we have extractable text, process ALL patterns including SSN, credit card, address
        if not has_text(page):
            # We used OCR, so only process owner patterns
            owner_pattern_types = {"owner_name", "owner_email", "owner_phone"}
            filtered_matches = []
            for pattern_type, matched_text in matches:
                if pattern_type in owner_pattern_types:
                    filtered_matches.append((pattern_type, matched_text))
                else:
                    logger.debug(f"Page {page_num + 1}: Skipping non-owner pattern '{pattern_type}' (OCR only for owner patterns)")
            matches = filtered_matches
        # If we have extractable text, keep ALL matches (including SSN, credit card, address)
        
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
                # Check whitelist - skip if match contains any whitelist word
                if any(word.lower() in search_text.lower() for word in WHITELIST):
                    logger.debug(f"Page {page_num + 1}: Skipping redaction for '{search_text}' - contains whitelist word")
                    continue  # skip
                
                # Find the match position in the page_text to extract context
                match_pos = page_text.find(search_text)
                if match_pos == -1:
                    # Try case-insensitive search
                    match_pos = page_text.lower().find(search_text.lower())
                
                if match_pos == -1:
                    # Match not found in page_text, skip redaction
                    logger.debug(f"Page {page_num + 1}: Match '{search_text}' not found in page_text, skipping redaction")
                    continue
                
                # Extract 50-80 character context window around the matched text
                # Using 60 characters as middle ground (50-80 range)
                start_pos = max(0, match_pos - 60)
                end_pos = min(len(page_text), match_pos + len(search_text) + 60)
                context_lower = page_text[start_pos:end_pos].lower()
                
                # FIRST: Check sensitive keywords (MUST come before owner-context check)
                if any(kw in context_lower for kw in SENSITIVE_KEYWORDS):
                    allow_redaction = True
                    logger.debug(f"Page {page_num + 1}: Sensitive keyword found in context for '{search_text}', allowing redaction")
                # ELSE: Check owner-context
                elif any(w in context_lower for w in OWNER_CONTEXT_KEYWORDS):
                    allow_redaction = True
                    logger.debug(f"Page {page_num + 1}: Owner context found for '{search_text}', allowing redaction")
                # ELSE: No context found
                else:
                    allow_redaction = False
                
                # Check if matched text is purely numeric (allowing commas and periods)
                # Remove commas, periods, and spaces, then check if remaining is all digits
                numeric_text = search_text.replace(",", "").replace(".", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                is_purely_numeric = numeric_text.isdigit() and len(numeric_text) > 0
                
                # If purely numeric and not allowed, skip redaction
                if is_purely_numeric and not allow_redaction:
                    logger.debug(f"Page {page_num + 1}: Skipping redaction for '{search_text}' - purely numeric without owner context or sensitive keywords")
                    continue  # skip the redaction
                
                # If not allow_redaction, continue (ONLY executes after BOTH checks)
                if not allow_redaction:
                    logger.debug(f"Page {page_num + 1}: Skipping redaction for '{search_text}' - no owner context or sensitive keywords found in window")
                    continue  # DO NOT REDACT OUTSIDE OWNER CONTEXT
                
                logger.debug(f"Page {page_num + 1}: Redaction allowed for '{search_text}', proceeding with redaction")
                
                # Search for text instances on the page using multiple strategies
                text_instances = []
                
                # Strategy 1: Exact match
                text_instances = page.search_for(search_text)
                logger.debug(f"Page {page_num + 1}: Exact search for '{search_text}' found {len(text_instances)} instance(s)")
                
                # Strategy 2: Try without special characters (normalize)
                if not text_instances:
                    # Remove special characters and try again
                    normalized = re.sub(r'[^\w\s]', '', search_text)
                    if normalized and normalized != search_text:
                        text_instances = page.search_for(normalized)
                        logger.debug(f"Page {page_num + 1}: Normalized search for '{normalized}' found {len(text_instances)} instance(s)")
                
                # Strategy 3: Search for parts of the text
                if not text_instances:
                    words = search_text.split()
                    if len(words) > 1:
                        # Try searching for first few words
                        partial_text = " ".join(words[:2])
                        text_instances = page.search_for(partial_text)
                        logger.debug(f"Page {page_num + 1}: Partial search for '{partial_text}' found {len(text_instances)} instance(s)")
                
                # Strategy 4: Use text blocks/dicts to find text by content
                if not text_instances:
                    # Get text blocks and search for the text in them
                    try:
                        text_dict = page.get_text("dict")
                        for block in text_dict.get("blocks", []):
                            if "lines" in block:
                                for line in block["lines"]:
                                    if "spans" in line:
                                        line_text = "".join(span.get("text", "") for span in line["spans"])
                                        # Check if our search text is in this line
                                        if search_text.lower() in line_text.lower():
                                            # Get the bounding box of this line
                                            bbox = line.get("bbox", [])
                                            if len(bbox) == 4:
                                                rect = fitz.Rect(bbox)
                                                text_instances.append(rect)
                                                logger.debug(f"Page {page_num + 1}: Found '{search_text}' in text block at {bbox}")
                    except Exception as e:
                        logger.debug(f"Page {page_num + 1}: Text block search failed: {e}")
                
                # Strategy 5: Search for individual words/parts for long text
                if not text_instances and len(search_text) > 10:
                    # For long text like addresses, try searching for key parts
                    if pattern_type == "address":
                        # Try searching for street number and street name
                        addr_parts = re.search(r"(\d+)\s+([A-Za-z]+)", search_text)
                        if addr_parts:
                            street_num = addr_parts.group(1)
                            street_name = addr_parts.group(2)
                            search_term = f"{street_num} {street_name}"
                            text_instances = page.search_for(search_term)
                            logger.debug(f"Page {page_num + 1}: Address part search for '{search_term}' found {len(text_instances)} instance(s)")
                    elif pattern_type in ["ssn", "credit_card"]:
                        # For SSN and credit card, try searching for just the numbers
                        numbers_only = re.sub(r'[^\d]', '', search_text)
                        if numbers_only:
                            # Try searching for the number with different formatting
                            if pattern_type == "ssn" and len(numbers_only) == 9:
                                formatted = f"{numbers_only[:3]}-{numbers_only[3:5]}-{numbers_only[5:]}"
                                text_instances = page.search_for(formatted)
                                if not text_instances:
                                    text_instances = page.search_for(numbers_only)
                            elif pattern_type == "credit_card" and len(numbers_only) >= 13:
                                # Try with spaces every 4 digits
                                formatted = " ".join([numbers_only[i:i+4] for i in range(0, len(numbers_only), 4)])
                                text_instances = page.search_for(formatted)
                                if not text_instances:
                                    text_instances = page.search_for(numbers_only)
                            logger.debug(f"Page {page_num + 1}: Number-only search found {len(text_instances)} instance(s)")
                
                # Add redaction annotation for each instance
                if text_instances:
                    for inst in text_instances:
                        try:
                            # Create redaction annotation with solid black fill
                            redaction = page.add_redact_annot(inst, fill=(0, 0, 0))  # Black fill
                            page_redactions += 1
                            total_redactions += 1
                            logger.info(f"Page {page_num + 1}: Added redaction for '{search_text}' at {inst}")
                        except Exception as e:
                            logger.warning(f"Page {page_num + 1}: Failed to add redaction annotation: {e}")
                else:
                    logger.warning(f"Page {page_num + 1}: Could not locate '{search_text}' on page for redaction")
                    
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

