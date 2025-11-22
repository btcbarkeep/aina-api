# core/utils.py

def sanitize(data: dict) -> dict:
    clean = {}

    for k, v in data.items():

        # Empty string → None
        if isinstance(v, str) and v.strip() == "":
            clean[k] = None
            continue

        # Numeric strings → integer
        if isinstance(v, str) and v.isdigit():
            clean[k] = int(v)
            continue

        # Float / decimal strings → float
        if isinstance(v, str):
            try:
                clean[k] = float(v)
                continue
            except ValueError:
                pass

        clean[k] = v

    return clean
