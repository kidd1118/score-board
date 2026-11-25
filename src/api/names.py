"""Player-name normalization shared by the salary and injury lookups."""
import re
import unicodedata

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def name_key(name):
    """'Nikola Jokić' / 'nikola jokic' -> 'nikola jokic'; drops punctuation and Jr./II/III suffixes."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    words = re.sub(r"[^a-z ]", "", plain.replace("-", " ")).split()
    return " ".join(w for w in words if w not in SUFFIXES)
