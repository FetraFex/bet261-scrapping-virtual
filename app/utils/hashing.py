import hashlib

def calculate_hash(data: str) -> str:
    """Calculate SHA-256 hash of a string deterministically."""
    return hashlib.sha256(data.encode('utf-8')).hexdigest()
