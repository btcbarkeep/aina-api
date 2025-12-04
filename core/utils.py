# core/utils.py

def sanitize(data: dict) -> dict:
    """
    Sanitize dictionary data:
    - Empty strings → None
    - Preserve booleans, None values
    - Strip string whitespace
    - Convert numeric strings to int/float when appropriate
    """
    clean = {}

    for k, v in data.items():
        # Preserve None
        if v is None:
            clean[k] = None
            continue

        # Preserve booleans
        if isinstance(v, bool):
            clean[k] = v
            continue

        # Empty string → None
        if isinstance(v, str):
            stripped = v.strip()
            if stripped == "":
                clean[k] = None
                continue

            # Numeric strings → integer
            if stripped.isdigit():
                clean[k] = int(stripped)
                continue

            # Float / decimal strings → float
            try:
                float_val = float(stripped)
                # Only convert if it's actually a float representation
                if '.' in stripped or 'e' in stripped.lower():
                    clean[k] = float_val
                    continue
            except ValueError:
                pass

            # Strip and use string
            clean[k] = stripped
            continue

        # For other types, keep as-is
        clean[k] = v

    return clean
