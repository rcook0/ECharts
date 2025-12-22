import os, hmac, hashlib, json
SECRET = (os.getenv("WL_SIGN_SECRET") or os.getenv("WL_JWT_SECRET") or "change-me").encode()

def canonical(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",",":")).encode()

def sign_event(payload: dict) -> str:
    return hmac.new(SECRET, canonical(payload), hashlib.sha256).hexdigest()

def verify_event(payload: dict, sig: str|None) -> bool:
    if not sig: return False
    try:
        calc = sign_event(payload)
        return hmac.compare_digest(calc, sig)
    except Exception:
        return False
