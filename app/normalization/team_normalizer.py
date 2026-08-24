import re

def normalize_team_name(source_name: str) -> str:
    """
    Normalizes a team name deterministically while preserving the original intent.
    Only obvious formatting differences are removed (e.g. extra spaces, lowercase).
    """
    if not source_name:
        return ""
        
    # Trim spaces
    normalized = source_name.strip()
    
    # Replace multiple spaces with a single space
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Capitalize the first letter of each word
    normalized = normalized.title()
    
    return normalized
