# core/utils.py

def sanitize(data: dict) -> dict:
    """
    Converts empty strings to None to prevent Supabase errors.
    """
    clean = {}
    for k, v in data.items():
        if isinstance(v, str) and v.strip() == "":
            clean[k] = None
        else:
            clean[k] = v
    return clean
