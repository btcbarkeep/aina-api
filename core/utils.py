# core/utils.py

def sanitize(data: dict) -> dict:
    """
    Converts empty strings to None and converts numeric strings to integers.
    """
    clean = {}

    for k, v in data.items():
        # Convert empty strings to None
        if isinstance(v, str) and v.strip() == "":
            clean[k] = None
            continue

        # Auto-convert numeric strings to integers
        if isinstance(v, str) and v.isdigit():
            clean[k] = int(v)
            continue

        clean[k] = v

    return clean
