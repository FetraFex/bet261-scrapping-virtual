import re

# Common football/soccer acronyms that should remain uppercase
_ACRONYMS = frozenset({
    'USA', 'UK', 'UAE', 'IR', 'DR', 'DRC', 'KSA',
    'PRK', 'ROK', 'RSA', 'COD', 'BRB', 'SLV',
})


def normalize_team_name(source_name: str) -> str:
    """
    Normalizes a team name deterministically while preserving the original intent.

    Steps:
      1. Trim whitespace and collapse multiple spaces
      2. Title-case the name (e.g. "turkiye" -> "Turkiye")
      3. Restore acronyms that .title() incorrectly lowercased
         (e.g. "Usa" -> "USA", "Cote d'ivoire" -> "Cote D'Ivoire")
    """
    if not source_name:
        return ""

    # Trim spaces
    normalized = source_name.strip()

    # Replace multiple spaces with a single space
    normalized = re.sub(r'\s+', ' ', normalized)

    # Split for word-level processing
    title_words = normalized.title().split(' ')
    orig_words = normalized.split(' ')

    # Restore acronyms: if a word matches a known acronym (case-insensitive),
    # force it to the canonical uppercase form regardless of input casing.
    result_words = []
    for orig, titled in zip(orig_words, title_words):
        upper = orig.upper()
        if len(orig) <= 4 and upper in _ACRONYMS:
            result_words.append(upper)  # canonical uppercase form
        else:
            result_words.append(titled)

    return ' '.join(result_words)
