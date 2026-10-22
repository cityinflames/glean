"""Local King James verse text. References the talk did not make are never filled in."""

import json
import re
from pathlib import Path

import paths

DATA_PATH = paths.resource_dir() / "data" / "kjv.json"

# Longest aliases first so "1 john" wins over "john".
ALIASES = {
    "genesis": "Genesis", "gen": "Genesis",
    "exodus": "Exodus", "exod": "Exodus", "exo": "Exodus",
    "leviticus": "Leviticus", "lev": "Leviticus",
    "numbers": "Numbers", "num": "Numbers",
    "deuteronomy": "Deuteronomy", "deut": "Deuteronomy", "deu": "Deuteronomy",
    "joshua": "Joshua", "josh": "Joshua",
    "judges": "Judges", "judg": "Judges",
    "ruth": "Ruth",
    "1 samuel": "1 Samuel", "i samuel": "1 Samuel", "1 sam": "1 Samuel", "1 sa": "1 Samuel",
    "2 samuel": "2 Samuel", "ii samuel": "2 Samuel", "2 sam": "2 Samuel", "2 sa": "2 Samuel",
    "1 kings": "1 Kings", "i kings": "1 Kings", "1 kgs": "1 Kings",
    "2 kings": "2 Kings", "ii kings": "2 Kings", "2 kgs": "2 Kings",
    "1 chronicles": "1 Chronicles", "i chronicles": "1 Chronicles", "1 chron": "1 Chronicles", "1 chr": "1 Chronicles",
    "2 chronicles": "2 Chronicles", "ii chronicles": "2 Chronicles", "2 chron": "2 Chronicles", "2 chr": "2 Chronicles",
    "ezra": "Ezra",
    "nehemiah": "Nehemiah", "neh": "Nehemiah",
    "esther": "Esther", "esth": "Esther",
    "job": "Job",
    "psalm": "Psalms", "psalms": "Psalms", "psa": "Psalms",
    "proverbs": "Proverbs", "prov": "Proverbs", "pro": "Proverbs",
    "ecclesiastes": "Ecclesiastes", "eccl": "Ecclesiastes", "ecc": "Ecclesiastes",
    "song of solomon": "Song of Solomon", "song of songs": "Song of Solomon", "canticles": "Song of Solomon",
    "isaiah": "Isaiah", "isa": "Isaiah",
    "jeremiah": "Jeremiah", "jer": "Jeremiah",
    "lamentations": "Lamentations", "lam": "Lamentations",
    "ezekiel": "Ezekiel", "ezek": "Ezekiel",
    "daniel": "Daniel", "dan": "Daniel",
    "hosea": "Hosea", "hos": "Hosea",
    "joel": "Joel",
    "amos": "Amos",
    "obadiah": "Obadiah", "obad": "Obadiah",
    "jonah": "Jonah",
    "micah": "Micah", "mic": "Micah",
    "nahum": "Nahum", "nah": "Nahum",
    "habakkuk": "Habakkuk", "hab": "Habakkuk",
    "zephaniah": "Zephaniah", "zeph": "Zephaniah",
    "haggai": "Haggai", "hag": "Haggai",
    "zechariah": "Zechariah", "zech": "Zechariah",
    "malachi": "Malachi", "mal": "Malachi",
    "matthew": "Matthew", "matt": "Matthew",
    "mark": "Mark", "mrk": "Mark",
    "luke": "Luke",
    "john": "John", "jn": "John",
    "acts": "Acts",
    "romans": "Romans", "rom": "Romans",
    "1 corinthians": "1 Corinthians", "i corinthians": "1 Corinthians", "1 cor": "1 Corinthians", "1 co": "1 Corinthians",
    "2 corinthians": "2 Corinthians", "ii corinthians": "2 Corinthians", "2 cor": "2 Corinthians", "2 co": "2 Corinthians",
    "galatians": "Galatians", "gal": "Galatians",
    "ephesians": "Ephesians", "eph": "Ephesians",
    "philippians": "Philippians", "phil": "Philippians",
    "colossians": "Colossians", "col": "Colossians",
    "1 thessalonians": "1 Thessalonians", "i thessalonians": "1 Thessalonians", "1 thess": "1 Thessalonians", "1 th": "1 Thessalonians",
    "2 thessalonians": "2 Thessalonians", "ii thessalonians": "2 Thessalonians", "2 thess": "2 Thessalonians", "2 th": "2 Thessalonians",
    "1 timothy": "1 Timothy", "i timothy": "1 Timothy", "1 tim": "1 Timothy",
    "2 timothy": "2 Timothy", "ii timothy": "2 Timothy", "2 tim": "2 Timothy",
    "titus": "Titus",
    "philemon": "Philemon", "phlm": "Philemon",
    "hebrews": "Hebrews", "heb": "Hebrews",
    "james": "James", "jas": "James",
    "1 peter": "1 Peter", "i peter": "1 Peter", "1 pet": "1 Peter", "1 pe": "1 Peter",
    "2 peter": "2 Peter", "ii peter": "2 Peter", "2 pet": "2 Peter", "2 pe": "2 Peter",
    "1 john": "1 John", "i john": "1 John", "1 jn": "1 John",
    "2 john": "2 John", "ii john": "2 John", "2 jn": "2 John",
    "3 john": "3 John", "iii john": "3 John", "3 jn": "3 John",
    "jude": "Jude",
    "revelation": "Revelation", "revelations": "Revelation", "rev": "Revelation",
}

_CANONICAL_NAMES = {}
_BOOKS = {}

# The verse file uses English text with localized book titles, so names follow canon order.
CANON = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua", "Judges", "Ruth",
    "1 Samuel", "2 Samuel", "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra",
    "Nehemiah", "Esther", "Job", "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon",
    "Isaiah", "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah", "Haggai", "Zechariah",
    "Malachi", "Matthew", "Mark", "Luke", "John", "Acts", "Romans", "1 Corinthians",
    "2 Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians", "1 Thessalonians",
    "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews", "James",
    "1 Peter", "2 Peter", "1 John", "2 John", "3 John", "Jude", "Revelation",
]


def load():
    if _BOOKS:
        return
    if not DATA_PATH.exists():
        return
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    books = raw if isinstance(raw, list) else raw.get("books", [])
    for index, book in enumerate(books):
        chapters = book.get("chapters") or []
        if not chapters:
            continue
        name = CANON[index] if index < len(CANON) else (book.get("name") or f"Book {index + 1}")
        _BOOKS[name.lower()] = {"name": name, "chapters": chapters}
        _CANONICAL_NAMES[name.lower()] = name
    for alias, canonical in ALIASES.items():
        key = canonical.lower()
        if key in _BOOKS:
            _CANONICAL_NAMES[alias] = _BOOKS[key]["name"]


def available():
    load()
    return bool(_BOOKS)


def resolve_name(spoken):
    load()
    key = re.sub(r"\s+", " ", spoken.strip().lower())
    key = key.replace(".", "")
    if key in _CANONICAL_NAMES:
        return _CANONICAL_NAMES[key]
    return ALIASES.get(key)


def verse_text(book_name, chapter, verse):
    load()
    book = _BOOKS.get(book_name.lower())
    if not book:
        return None
    chapters = book["chapters"]
    if chapter < 1 or chapter > len(chapters):
        return None
    ch = chapters[chapter - 1]
    if isinstance(ch, dict):
        verses = ch.get("verses") or []
    else:
        verses = ch
    if verse < 1 or verse > len(verses):
        return None
    item = verses[verse - 1]
    if isinstance(item, dict):
        return (item.get("text") or item.get("verse") or "").strip()
    return str(item).strip()


def passage(book_name, chapter, start_verse, end_verse=None):
    end_verse = end_verse or start_verse
    if end_verse < start_verse:
        start_verse, end_verse = end_verse, start_verse
    # A clip citation should stay a reading, not a whole chapter.
    end_verse = min(end_verse, start_verse + 4)
    parts = []
    for number in range(start_verse, end_verse + 1):
        text = verse_text(book_name, chapter, number)
        if not text:
            break
        parts.append(f"{number} {text}")
    if not parts:
        return None
    label_end = start_verse + len(parts) - 1
    if label_end == start_verse:
        ref = f"{book_name} {chapter}:{start_verse}"
    else:
        ref = f"{book_name} {chapter}:{start_verse}-{label_end}"
    return ref, " ".join(parts)
