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
    # Owner names when preceded by context words - make it greedy to capture full name
    r"(?i)(Owner|Unit Owner|Owner Name|Homeowner|Tenant|Contact)\s*[:\-]\s+[A-Za-z ,.'\-]+(?:$|\n|(?=Social Security|Credit|Phone|Email|Home Address))",
    
    # Owner email (also match standalone Email:) - more flexible to catch partial emails
    r"(?i)(Owner|Contact|Tenant|Email).{0,15}[A-Za-z0-9._%+-]+(?:@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
    
    # Owner phone (also match standalone Phone:)
    r"(?i)(Owner|Contact|Tenant|Phone).{0,10}\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
    
    # SSN (with context)
    r"(?i)(Social Security|SSN|S\.S\.N\.).{0,10}\d{3}[-.\s]?\d{2}[-.\s]?\d{4}",
    
    # Credit card numbers (with context) - more specific pattern
    r"(?i)(Credit Card|Card Number|CC#|CC Number).{0,10}\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}",
    
    # Addresses (with context) - more flexible pattern (street type optional)
    r"(?i)(Home Address|Address)\s*[:\-]?\s+\d+[\s\w,.-]{5,80}",
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
                # The matched_text is like "Owner Name: Michael Andrew Thompson"
                # We need to extract everything after the colon
                # First, try to match the full pattern with capture group
                name_match = re.search(r"(?:Owner|Unit Owner|Owner Name|Homeowner|Tenant|Contact)\s*[:\-]\s+([A-Za-z ,.'\-]+)", matched_text, re.IGNORECASE)
                if name_match:
                    extracted_name = name_match.group(1).strip()
                    # Split by common delimiters to get just the name part
                    extracted_name = re.split(r'\n|Social Security|Credit|Phone|Email|Home Address', extracted_name)[0].strip()
                    # Filter out common label words that might have been captured
                    label_words = ["name", "owner", "owner name", "unit owner", "homeowner", "tenant", "contact"]
                    if extracted_name.lower() in label_words:
                        # Skip if we only extracted a label word
                        pass
                    # Only add if it looks like a name (has at least 2 words and is not just "Name")
                    elif len(extracted_name.split()) >= 2 and extracted_name.lower() not in ["name", "owner name"]:
                        matches.append((pattern_type, extracted_name))
                else:
                    # Fallback: try simple extraction after colon
                    name_match = re.search(r":[:\-]\s+([A-Za-z ,.'\-]{5,})", matched_text, re.IGNORECASE)
                    if name_match:
                        extracted_name = name_match.group(1).strip()
                        extracted_name = re.split(r'\n|Social Security|Credit|Phone|Email|Home Address', extracted_name)[0].strip()
                        # Filter out label words
                        label_words = ["name", "owner", "owner name", "unit owner", "homeowner", "tenant", "contact"]
                        if extracted_name.lower() not in label_words and len(extracted_name.split()) >= 2:
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
                # More flexible - just get everything after "Home Address:" or "Address:"
                addr_match = re.search(r"[:\-]?\s+(\d+[\s\w,.-]{5,80})", matched_text, re.IGNORECASE)
                if addr_match:
                    addr = addr_match.group(1).strip()
                    # Stop at newline or next major keyword to avoid over-capturing
                    addr = re.split(r'\n|Social Security|Credit|Phone|Email|Owner Name', addr)[0].strip()
                    addr = re.sub(r'\s+', ' ', addr)  # Normalize whitespace
                    # Filter out label words that might have been captured
                    label_words = ["address", "home address", "home addres"]
                    # Only add if it looks like an address (has at least a number and some text) and is not just a label
                    if len(addr) >= 5 and re.search(r'\d', addr) and addr.lower() not in label_words:
                        matches.append((pattern_type, addr))
                        
                        # Also add city/state/zip as separate match if present
                        # This helps catch cases where address is split across lines
                        city_state_zip = re.search(r'([A-Za-z]+),\s*([A-Z]{2})\s+(\d{5})', addr)
                        if city_state_zip:
                            city_state = f"{city_state_zip.group(1)}, {city_state_zip.group(2)} {city_state_zip.group(3)}"
                            # Add as separate match to ensure it gets redacted even if split
                            matches.append((pattern_type, city_state))
                            # Also add just the state/zip part
                            state_zip = f"{city_state_zip.group(2)} {city_state_zip.group(3)}"
                            matches.append((pattern_type, state_zip))
    
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
        
        # For addresses, also search for city/state/zip patterns that might be on separate lines
        # This helps catch cases where the address is split (e.g., "a, HI 96734" visible)
        address_matches = [m for m in matches if m[0] == "address"]
        if address_matches:
            for pattern_type, addr_text in address_matches:
                # Extract city/state/zip if present
                city_state_match = re.search(r'([A-Za-z]+),\s*([A-Z]{2})\s+(\d{5})', addr_text)
                if city_state_match:
                    # Add city, state zip as separate match
                    city_state_zip = f"{city_state_match.group(1)}, {city_state_match.group(2)} {city_state_match.group(3)}"
                    if (pattern_type, city_state_zip) not in matches:
                        matches.append((pattern_type, city_state_zip))
                    # Add state zip
                    state_zip = f"{city_state_match.group(2)} {city_state_match.group(3)}"
                    if (pattern_type, state_zip) not in matches:
                        matches.append((pattern_type, state_zip))
                    # Also search for patterns like ", HI 96734" or "a, HI 96734" (partial city)
                    partial_city = re.search(r'([a-z]),\s*([A-Z]{2})\s+(\d{5})', addr_text.lower())
                    if partial_city:
                        partial_pattern = f"{partial_city.group(1)}, {partial_city.group(2).upper()} {partial_city.group(3)}"
                        if (pattern_type, partial_pattern) not in matches:
                            matches.append((pattern_type, partial_pattern))
                
                # Also extract and add any state/zip patterns found anywhere in the address
                state_zip_pattern = re.search(r'([A-Z]{2})\s+(\d{5})', addr_text)
                if state_zip_pattern:
                    state_zip = f"{state_zip_pattern.group(1)} {state_zip_pattern.group(2)}"
                    if (pattern_type, state_zip) not in matches:
                        matches.append((pattern_type, state_zip))
                
                # Extract zip code alone
                zip_pattern = re.search(r'\b(\d{5})\b', addr_text)
                if zip_pattern:
                    zip_code = zip_pattern.group(1)
                    if (pattern_type, zip_code) not in matches:
                        matches.append((pattern_type, zip_code))
        
        # Don't search the entire page for address patterns - too aggressive
        # Only use the patterns we found from the actual address matches
        
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
                
                # For email and address patterns, always allow redaction if the pattern matched
                # (since the pattern itself requires context like "Email:" or "Home Address:")
                if pattern_type in ["owner_email", "address"]:
                    allow_redaction = True
                    logger.debug(f"Page {page_num + 1}: Pattern '{pattern_type}' matched with context, allowing redaction")
                # FIRST: Check sensitive keywords (MUST come before owner-context check)
                elif any(kw in context_lower for kw in SENSITIVE_KEYWORDS):
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
                
                # Validate that search_text doesn't contain label words (safety check)
                # Common label words that should never be redacted
                label_words = ["name", "owner name", "address", "home address", "home addres", "social security", "ssn", "credit card", "credit", "phone", "email"]
                search_lower = search_text.lower().strip()
                
                # Skip if search_text is just a label word or very short label-like text
                if search_lower in label_words:
                    logger.warning(f"Page {page_num + 1}: Skipping redaction for '{search_text}' - appears to be a label word, not data")
                    continue
                
                # Skip if search_text is very short (1-2 words) and contains a label word
                if len(search_text.split()) <= 2 and any(label in search_lower for label in label_words):
                    logger.warning(f"Page {page_num + 1}: Skipping redaction for '{search_text}' - too short and contains label word")
                    continue
                
                # Search for text instances on the page using multiple strategies
                text_instances = []
                
                # Strategy 1: Exact match
                text_instances = page.search_for(search_text)
                logger.debug(f"Page {page_num + 1}: Exact search for '{search_text}' found {len(text_instances)} instance(s)")
                
                # Filter out any instances that might be matching labels instead of data
                # Check if the found text is part of a label (e.g., "Owner Name:" contains "Name")
                if text_instances:
                    filtered_instances = []
                    label_keywords = ["owner name:", "name:", "home address:", "address:", "social security", "ssn:", "credit card", "credit:", "phone:", "email:"]
                    
                    for inst in text_instances:
                        # Get the text around this instance to check context
                        try:
                            # Get a wider area around the instance to check for label keywords
                            rect = fitz.Rect(inst)
                            # Expand significantly to the left to catch labels
                            context_rect = fitz.Rect(max(0, rect.x0 - 150), rect.y0 - 5, rect.x1 + 50, rect.y1 + 5)
                            context_text = page.get_textbox(context_rect).lower()
                            
                            # Check if this instance is part of a label line
                            # A label line would have the pattern: "Label: search_text" or "Label search_text"
                            is_label_match = False
                            
                            # Find where our search text appears in the context
                            search_lower = search_text.lower()
                            search_pos = context_text.find(search_lower)
                            
                            if search_pos != -1:
                                # Get text before our search text (this is where the label would be)
                                text_before = context_text[:search_pos].strip()
                                
                                # Check if any label keyword appears right before our search text
                                for label in label_keywords:
                                    label_lower = label.lower()
                                    # Check if label appears at the end of text_before (immediately before search text)
                                    if text_before.endswith(label_lower) or text_before.endswith(label_lower.rstrip(':')):
                                        # Label is immediately before - this is likely a label match
                                        is_label_match = True
                                        logger.info(f"Page {page_num + 1}: Skipping instance - '{search_text}' appears right after label '{label}'")
                                        break
                                    
                                    # Also check if label appears very close before (within 5 chars)
                                    label_pos = text_before.rfind(label_lower)
                                    if label_pos != -1 and (len(text_before) - label_pos) <= len(label_lower) + 5:
                                        is_label_match = True
                                        logger.info(f"Page {page_num + 1}: Skipping instance - '{search_text}' appears close after label '{label}'")
                                        break
                            
                            if not is_label_match:
                                filtered_instances.append(inst)
                            else:
                                logger.debug(f"Page {page_num + 1}: Filtered out label match for '{search_text}'")
                        except Exception as e:
                            # If we can't check context, be conservative and skip it
                            logger.warning(f"Page {page_num + 1}: Could not check context for instance, skipping to avoid redacting label: {e}")
                            # Don't add to filtered_instances - skip it to be safe
                    
                    text_instances = filtered_instances
                    logger.debug(f"Page {page_num + 1}: After filtering labels, {len(text_instances)} instance(s) remain")
                
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
                # For addresses, ALWAYS run this strategy to catch split address parts
                if not text_instances or pattern_type == "address":
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
                                                if rect not in text_instances:
                                                    text_instances.append(rect)
                                                    logger.debug(f"Page {page_num + 1}: Found '{search_text}' in text block at {bbox}")
                                        
                                        # For addresses, check lines for address patterns BUT only if they're related to our address
                                        # (in case the address is split across lines)
                                        if pattern_type == "address":
                                            # Only redact if this line contains parts that match our search_text
                                            # or if it's clearly a continuation of the address
                                            
                                            # Check if this line contains parts of our address
                                            search_text_lower = search_text.lower()
                                            line_text_lower = line_text.lower()
                                            
                                            # Check for patterns like ", HI 96734" or "a, HI 96734" (partial city name)
                                            has_partial_city_state_zip = re.search(r'[a-z],\s*[A-Z]{2}\s+\d{5}', line_text.lower())
                                            
                                            # Check for state/zip pattern (e.g., "HI 96734")
                                            has_state_zip = re.search(r'\b[A-Z]{2}\s+\d{5}\b', line_text)
                                            
                                            # Extract state/zip from our search_text to compare
                                            search_state_zip = re.search(r'\b([A-Z]{2})\s+(\d{5})\b', search_text)
                                            
                                            line_bbox = line.get("bbox", [])
                                            if len(line_bbox) == 4:
                                                should_redact = False
                                                
                                                # Only redact if:
                                                # 1. The line contains parts of our search_text, OR
                                                # 2. It has state/zip that matches our address's state/zip
                                                if search_text_lower in line_text_lower:
                                                    # Line contains our search text
                                                    should_redact = True
                                                elif search_state_zip and has_state_zip:
                                                    # Check if the state/zip matches
                                                    line_state_zip = re.search(r'\b([A-Z]{2})\s+(\d{5})\b', line_text)
                                                    if line_state_zip:
                                                        if (line_state_zip.group(1) == search_state_zip.group(1) and 
                                                            line_state_zip.group(2) == search_state_zip.group(2)):
                                                            should_redact = True
                                                            logger.info(f"Page {page_num + 1}: Found matching state/zip '{line_text.strip()}' for address, will redact")
                                                elif has_partial_city_state_zip:
                                                    # Check if the state/zip in the partial matches our address
                                                    if search_state_zip:
                                                        partial_state_zip = re.search(r'([A-Z]{2})\s+(\d{5})', line_text)
                                                        if partial_state_zip:
                                                            if (partial_state_zip.group(1) == search_state_zip.group(1) and 
                                                                partial_state_zip.group(2) == search_state_zip.group(2)):
                                                                should_redact = True
                                                                logger.info(f"Page {page_num + 1}: Found matching partial city/state/zip '{line_text.strip()}' for address, will redact")
                                                
                                                if should_redact:
                                                    rect = fitz.Rect(line_bbox)
                                                    # Avoid duplicates
                                                    if rect not in text_instances:
                                                        text_instances.append(rect)
                                                        logger.info(f"Page {page_num + 1}: Added address part redaction for '{line_text.strip()}' at {line_bbox}")
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
                        
                        # Also try searching for city/state/zip pattern
                        if not text_instances:
                            city_state_match = re.search(r'([A-Za-z]+),\s*([A-Z]{2})\s+(\d{5})', search_text)
                            if city_state_match:
                                # Try full city, state zip
                                city_state_zip = f"{city_state_match.group(1)}, {city_state_match.group(2)} {city_state_match.group(3)}"
                                text_instances = page.search_for(city_state_zip)
                                if not text_instances:
                                    # Try just state zip
                                    state_zip = f"{city_state_match.group(2)} {city_state_match.group(3)}"
                                    text_instances = page.search_for(state_zip)
                                if not text_instances:
                                    # Try just the city name
                                    city = city_state_match.group(1)
                                    text_instances = page.search_for(city)
                                logger.debug(f"Page {page_num + 1}: City/state/zip search found {len(text_instances)} instance(s)")
                        
                        # Also search for any remaining address parts that might be visible
                        # Look for patterns like ", HI 96734" or "HI 96734" or just "96734"
                        if not text_instances:
                            zip_match = re.search(r'(\d{5})', search_text)
                            if zip_match:
                                zip_code = zip_match.group(1)
                                text_instances = page.search_for(zip_code)
                                if not text_instances:
                                    # Try with state code if present
                                    state_match = re.search(r'([A-Z]{2})\s+(\d{5})', search_text)
                                    if state_match:
                                        state_zip = f"{state_match.group(1)} {state_match.group(2)}"
                                        text_instances = page.search_for(state_zip)
                                logger.debug(f"Page {page_num + 1}: Zip code search found {len(text_instances)} instance(s)")
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
                            # Double-check that this instance is not part of a label before redacting
                            rect = fitz.Rect(inst)
                            # Get text in a wider area to check for labels
                            check_rect = fitz.Rect(max(0, rect.x0 - 200), rect.y0 - 2, rect.x1 + 50, rect.y1 + 2)
                            check_text = page.get_textbox(check_rect).lower()
                            
                            # Check if this appears to be part of a label
                            label_patterns = [
                                r"owner\s+name\s*:",
                                r"home\s+address\s*:",
                                r"social\s+security\s+(?:number|num)\s*:?",
                                r"ssn\s*:",
                                r"credit\s+(?:card\s+)?(?:number|num)\s*:?",
                                r"phone\s*:",
                                r"email\s*:"
                            ]
                            
                            is_label = False
                            search_lower = search_text.lower()
                            search_pos = check_text.find(search_lower)
                            
                            if search_pos != -1:
                                text_before = check_text[:search_pos].strip()
                                for pattern in label_patterns:
                                    if re.search(pattern + r"\s*$", text_before):
                                        is_label = True
                                        logger.info(f"Page {page_num + 1}: Skipping redaction - '{search_text}' appears after label pattern '{pattern}'")
                                        break
                            
                            if not is_label:
                                # Create redaction annotation with solid black fill
                                redaction = page.add_redact_annot(inst, fill=(0, 0, 0))  # Black fill
                                page_redactions += 1
                                total_redactions += 1
                                logger.info(f"Page {page_num + 1}: Added redaction for '{search_text}' at {inst}")
                            else:
                                logger.debug(f"Page {page_num + 1}: Skipped redaction for '{search_text}' - detected as label")
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

