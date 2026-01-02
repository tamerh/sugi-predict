"""Drug Name Selection Utilities.

Select the best drug name from alternative names, preferring INN
(International Nonproprietary Names) over codes and IUPAC chemical names.
"""

import re
from typing import List, Optional


# Common drug name suffixes (INN stems) - indicates real drug names
INN_SUFFIXES = [
    'mab', 'nib', 'lib', 'ib', 'tinib', 'ciclib', 'rafenib',  # targeted therapy
    'platin', 'mustine', 'rubicin', 'mycin',  # chemo
    'olol', 'pril', 'sartan', 'dipine', 'statin',  # cardio
    'azole', 'oxacin', 'cillin', 'cycline',  # anti-infective
    'pam', 'lam', 'zepam',  # CNS
    'one', 'ide', 'ate', 'ine',  # general
]


def _name_score(name: str) -> int:
    """
    Score a drug name - lower is better.

    Prefers:
    - INN names (with standard suffixes like -mab, -nib)
    - Capitalized names
    - Names 6-15 characters long

    Penalizes:
    - Code-like names (AVA-1, MDX-1106)
    - IUPAC chemical names (long, with brackets)
    - All caps abbreviations
    - Very short or very long names

    Args:
        name: Drug name to score

    Returns:
        Score (lower is better)
    """
    if not name or len(name) < 2:
        return 1000

    name_lower = name.lower()
    score = 50  # Base score

    # STRONGLY prefer names with INN suffixes (real drug names)
    for suffix in INN_SUFFIXES:
        if name_lower.endswith(suffix):
            score -= 40
            break

    # STRONGLY penalize code-like names (e.g., AVA-1, MDX-1106, ABP-215)
    # Pattern: 2-4 letters followed by dash and numbers
    if re.match(r'^[A-Z]{2,4}-\d+', name):
        score += 100
    # Also penalize: letters followed by numbers (e.g., GSK1120212)
    if re.match(r'^[A-Z]{2,4}\d{4,}', name):
        score += 80

    # Penalize IUPAC-like names (contain brackets, complex patterns)
    if any(c in name for c in ['{', '}', '[', ']']):
        score += 100
    if name.count('(') > 1 or name.count('-') > 3:
        score += 50

    # Penalize very long names (likely IUPAC)
    if len(name) > 50:
        score += 80
    elif len(name) > 30:
        score += 30

    # Penalize names starting with numbers
    if name[0].isdigit():
        score += 60

    # Penalize ALL CAPS (often codes/abbreviations)
    if name.isupper() and len(name) > 3:
        score += 30

    # Prefer capitalized names (e.g., "Bevacizumab" over "bevacizumab")
    if name[0].isupper() and not name.isupper():
        score -= 10

    # Prefer names 6-15 chars (typical drug name length)
    if 6 <= len(name) <= 15:
        score -= 15
    elif len(name) < 4:
        score += 20  # Too short, likely abbreviation

    return score


def get_best_drug_name(alt_names: List[str], fallback: Optional[str] = None) -> str:
    """
    Select the best drug name from altNames list.

    Prefers INN (International Nonproprietary Names) and trade names
    over codes, abbreviations, and IUPAC chemical names.

    Args:
        alt_names: List of alternative names from ChEMBL
        fallback: Fallback name if no good name found

    Returns:
        Best drug name (e.g., "Bevacizumab" not "AVA-1")

    Examples:
        >>> get_best_drug_name(["AVA-1", "BEVACIZUMAB", "Bevacizumab"])
        'Bevacizumab'

        >>> get_best_drug_name(["GSK1120212", "Trametinib"])
        'Trametinib'
    """
    if not alt_names:
        return fallback

    # Score each name and return best (lowest score)
    scored = [(name, _name_score(name)) for name in alt_names if name]
    if scored:
        scored.sort(key=lambda x: x[1])
        return scored[0][0]

    return fallback
