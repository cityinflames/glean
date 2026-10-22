"""Turn a timestamped transcript into quotes, clip marks, and the verses it actually cites."""

import re

import bible

PROMO = re.compile(r"transcribed by turboscribe", re.I)
HEADER = re.compile(
    r"^\((\d+:\d{2}(?::\d{2})?)\s*-\s*(\d+:\d{2}(?::\d{2})?)\)\s*$"
)
SRT_TIME = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})"
)
LINE_TIME = re.compile(
    r"^[\[\(]?(\d+:\d{2}(?::\d{2})?)[\]\)]?\s+(.*\S)\s*$"
)

ORDINALS = {"first": "1", "second": "2", "third": "3", "1st": "1", "2nd": "2", "3rd": "3"}


def clock_to_seconds(value):
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(value)


def format_clock(seconds):
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _clean_block(text):
    lines = []
    for line in text.splitlines():
        if PROMO.search(line):
            continue
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    return " ".join(lines).strip()


def parse_transcript(text):
    """Accept TurboScribe .txt, SubRip .srt, WebVTT, or lines that start with a time."""
    stripped = text.lstrip("\ufeff")
    if "-->" in stripped or stripped.startswith("WEBVTT"):
        return _parse_srt(stripped)
    if HEADER.search(stripped.splitlines()[0] if stripped.splitlines() else "") or "\n(" in "\n" + stripped:
        blocks = _parse_turboscribe(stripped)
        if blocks:
            return blocks
    lined = _parse_line_times(stripped)
    if lined:
        return lined
    words = _clean_block(stripped)
    if not words:
        return []
    return [{"start": None, "end": None, "text": words}]


def _parse_turboscribe(text):
    blocks = []
    current = None
    body = []
    for line in text.splitlines():
        match = HEADER.match(line.strip())
        if match:
            if current and body:
                spoken = _clean_block("\n".join(body))
                if spoken:
                    blocks.append({**current, "text": spoken})
            current = {
                "start": clock_to_seconds(match.group(1)),
                "end": clock_to_seconds(match.group(2)),
            }
            body = []
        else:
            body.append(line)
    if current and body:
        spoken = _clean_block("\n".join(body))
        if spoken:
            blocks.append({**current, "text": spoken})
    return blocks


def _srt_seconds(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _parse_srt(text):
    blocks = []
    current = None
    body = []
    for line in text.splitlines():
        match = SRT_TIME.search(line.strip())
        if match:
            if current and body:
                spoken = _clean_block("\n".join(body))
                if spoken:
                    blocks.append({**current, "text": spoken})
            current = {
                "start": _srt_seconds(*match.group(1, 2, 3, 4)),
                "end": _srt_seconds(*match.group(5, 6, 7, 8)),
            }
            body = []
        elif line.strip().isdigit():
            continue
        elif line.strip() == "WEBVTT":
            continue
        else:
            body.append(line)
    if current and body:
        spoken = _clean_block("\n".join(body))
        if spoken:
            blocks.append({**current, "text": spoken})
    return blocks


def _parse_line_times(text):
    blocks = []
    for line in text.splitlines():
        if PROMO.search(line):
            continue
        match = LINE_TIME.match(line.strip())
        if not match:
            continue
        start = clock_to_seconds(match.group(1))
        spoken = match.group(2).strip()
        if spoken:
            blocks.append({"start": start, "end": start, "text": spoken})
    return blocks


def _normalize_spoken_books(text):
    def ordinal(match):
        return ORDINALS[match.group(1).lower()] + " "

    return re.sub(r"\b(first|second|third|1st|2nd|3rd)\s+", ordinal, text, flags=re.I)


def _book_pattern():
    names = sorted(bible.ALIASES, key=len, reverse=True)
    return "|".join(re.escape(name) for name in names)


def find_scripture(segments):
    book_re = _book_pattern()
    full = re.compile(
        rf"\b(?P<book>{book_re})\b(?:\s+chapter)?\s+(?P<chapter>\d+)"
        rf"(?:\s*[:.]\s*(?P<verse>\d+)|\s+verses?\s+(?P<verse2>\d+))"
        rf"(?:\s*(?:-|–|—|through|to)\s*(?:verses?\s+)?(?P<end>\d+))?",
        re.I,
    )
    verse_only = re.compile(r"\bverses?\s+(?P<verse>\d+)(?:\s*(?:-|–|—|through|to)\s+(?P<end>\d+))?", re.I)
    chapter_only = re.compile(rf"\b(?P<book>{book_re})\b(?:\s+chapter)?\s+(?P<chapter>\d+)\b", re.I)

    found = []
    seen = set()
    context = {"book": None, "chapter": None}

    for segment in segments:
        text = _normalize_spoken_books(segment["text"])
        cursor = 0
        while cursor < len(text):
            candidates = []
            for kind, pattern in (("full", full), ("chapter", chapter_only), ("verse", verse_only)):
                match = pattern.search(text, cursor)
                if match:
                    candidates.append((match.start(), kind, match))
            if not candidates:
                break
            _, kind, match = min(candidates, key=lambda item: item[0])
            cursor = match.end()
            if kind == "verse":
                if not context["book"] or not context["chapter"]:
                    found.append({
                        "start": segment["start"],
                        "end": segment["end"],
                        "heard": segment["text"].strip(),
                        "ref": None,
                        "verseText": None,
                        "note": f"Verse {match.group('verse')} was spoken here, without a book and chapter in this transcript.",
                    })
                    continue
                book = context["book"]
                chapter = context["chapter"]
                start_verse = int(match.group("verse"))
                end_verse = int(match.group("end") or start_verse)
            else:
                book = bible.resolve_name(match.group("book"))
                if not book:
                    continue
                chapter = int(match.group("chapter"))
                context["book"] = book
                context["chapter"] = chapter
                if kind == "chapter":
                    continue
                start_verse = int(match.group("verse") or match.group("verse2"))
                end_verse = int(match.group("end") or start_verse)
            key = (book, chapter, start_verse, end_verse)
            if key in seen:
                continue
            seen.add(key)
            looked = bible.passage(book, chapter, start_verse, end_verse) if bible.available() else None
            if looked:
                ref, verse_text = looked
            else:
                ref = f"{book} {chapter}:{start_verse}" if start_verse == end_verse else f"{book} {chapter}:{start_verse}-{end_verse}"
                verse_text = None
            found.append({
                "start": segment["start"],
                "end": segment["end"],
                "heard": segment["text"].strip(),
                "ref": ref,
                "verseText": verse_text,
                "note": None if verse_text else "The verse text is not stored on this computer yet. The reference is what was spoken.",
            })
    return found


CUE_NUMBER = re.compile(r"(?<=[A-Za-z,.!?])\s+\d+(?=\s+[A-Za-z])")
TRAILING_CUE = re.compile(r"\s+\d+\s*$")
SETUP = re.compile(
    r"\b(i('d| would) like to|i want us to|another verse|look at verse|"
    r"keep in mind|our text is found|we shall read|the topic|"
    r"good morning|turn with me)\b",
    re.I,
)
IMPERATIVE = re.compile(
    r"\b(do not|don't|never|beware|remember|watch|stop|quit|be not)\b",
    re.I,
)
IMAGE = re.compile(
    r"\b(toenail|nail|rim|cell|cells|body|bodies|flesh|blood|bone|dust|"
    r"grave|glass|fire|ash|ashes|dirt|mud|sweat|tear|tears|wound|"
    r"cross|tomb|graveclothes|thirst|hunger)\b",
    re.I,
)
PARALLEL = re.compile(r"\bnot one\b|\bnot a single\b|\bincluding the\b", re.I)


def _clean_spoken(text):
    text = PROMO.sub("", text)
    text = CUE_NUMBER.sub("", text)
    text = TRAILING_CUE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def sentences_from(segments):
    """Join short caption lines, then split on real sentence ends."""
    parts = []
    spans = []
    cursor = 0
    for segment in segments:
        spoken = _clean_spoken(segment["text"])
        if not spoken:
            continue
        if parts:
            cursor += 1
        start = cursor
        parts.append(spoken)
        cursor += len(spoken)
        spans.append((start, cursor, segment))
    if not parts:
        return []
    blob = " ".join(parts)
    found = []
    for piece in re.split(r"(?<=[.!?])\s+", blob):
        text = piece.strip()
        words = re.findall(r"[A-Za-z']+", text)
        if len(words) < 5:
            continue
        start_at = blob.find(text)
        if start_at < 0:
            continue
        end_at = start_at + len(text)
        involved = [segment for left, right, segment in spans if left < end_at and right > start_at]
        if not involved:
            continue
        found.append({
            "text": text,
            "start": involved[0]["start"],
            "end": involved[-1]["end"] if involved[-1]["end"] is not None else involved[-1]["start"],
            "index": id(involved[0]),
        })
    return found


def _word_weights(segments):
    counts = {}
    for segment in segments:
        for word in re.findall(r"[A-Za-z']+", _clean_spoken(segment["text"]).lower()):
            if len(word) < 4:
                continue
            counts[word] = counts.get(word, 0) + 1
    return counts


def _punch_score(text, weights):
    words = re.findall(r"[A-Za-z']+", text)
    count = len(words)
    if count < 8 or count > 90:
        return 0
    if SETUP.search(text):
        return 0
    score = 1.2
    if 12 <= count <= 45:
        score += 0.8
    if IMPERATIVE.search(text):
        score += 2.2
    if PARALLEL.search(text):
        score += 1.4
    images = IMAGE.findall(text)
    score += min(2.4, 0.55 * len(images))
    if re.search(r"\b(if you don't remember|if you remember nothing)\b", text, re.I):
        score += 1.6
    rare = 0
    for word in {item.lower() for item in words if len(item) >= 5}:
        seen = weights.get(word, 1)
        if seen <= 2:
            rare += 1
    score += min(1.6, 0.35 * rare)
    score -= 0.3 * len(re.findall(r"\b(um+|uh+|you know|kind of|sort of)\b", text, re.I))
    return score


def _image_score(text):
    return len(IMAGE.findall(text)) + (1.5 if PARALLEL.search(text) else 0)


def _hook(text):
    clauses = [piece.strip() for piece in re.split(r"(?<=[.!?])\s+", text) if piece.strip()]
    short = [clause for clause in clauses if 3 <= len(re.findall(r"[A-Za-z']+", clause)) <= 12]
    pictured = [clause for clause in short if IMPERATIVE.search(clause)]
    if pictured:
        return pictured[0].rstrip(".!?")
    including = re.search(r"\bincluding\s+([^.!?]{8,40})", text, re.I)
    if including:
        phrase = including.group(1).strip().rstrip(",;")
        return phrase[0].upper() + phrase[1:]
    pictured = [clause for clause in short if IMAGE.search(clause)]
    if pictured:
        return pictured[-1].rstrip(".!?")
    if short:
        return short[0].rstrip(".!?")
    words = re.findall(r"[A-Za-z']+", text)
    return " ".join(words[:7])


def _expand_punch(spoken, punch):
    if punch["start"] is None:
        return punch
    chosen = [item for item in spoken if item["start"] is not None and item["start"] >= punch["start"] - 0.2 and item["end"] <= (punch["end"] or punch["start"]) + 0.2]
    if not chosen:
        return punch
    first = spoken.index(chosen[0])
    last = spoken.index(chosen[-1])
    while first > 0:
        prev = spoken[first - 1]
        if prev["start"] is None or punch["start"] - (prev["end"] or prev["start"]) > 4:
            break
        if SETUP.search(prev["text"]):
            break
        if (punch["end"] or punch["start"]) - prev["start"] > 32:
            break
        first -= 1
        punch = {
            **punch,
            "start": prev["start"],
            "text": prev["text"] + " " + punch["text"],
        }
    while last + 1 < len(spoken):
        nxt = spoken[last + 1]
        if nxt["start"] is None or nxt["start"] - (punch["end"] or punch["start"]) > 4:
            break
        if SETUP.search(nxt["text"]):
            break
        if (nxt["end"] or nxt["start"]) - punch["start"] > 32:
            break
        last += 1
        punch = {
            **punch,
            "end": nxt["end"],
            "text": punch["text"] + " " + nxt["text"],
        }
    punch["hook"] = _hook(punch["text"])
    return punch


def find_punches(segments):
    spoken = sentences_from(segments)
    if not spoken:
        return []
    weights = _word_weights(segments)
    candidates = []
    for index, _sentence in enumerate(spoken):
        for width in (1, 2, 3):
            group = spoken[index:index + width]
            if len(group) < width:
                continue
            start = group[0]["start"]
            end = group[-1]["end"]
            if start is not None and end is not None and end - start > 40:
                continue
            text = " ".join(item["text"] for item in group)
            score = _punch_score(text, weights)
            if score <= 0:
                continue
            candidates.append({
                "text": text,
                "start": start,
                "end": end,
                "score": score,
                "image": _image_score(text),
                "hook": _hook(text),
                "index": group[0]["index"],
            })
    if not candidates:
        return []

    def take(pool, prefer_image=False):
        ordered = sorted(
            pool,
            key=lambda item: (item["image"] if prefer_image else item["score"], item["score"]),
            reverse=True,
        )
        return ordered[0] if ordered else None

    first = take(candidates)
    leftover = [
        item for item in candidates
        if item is not first and (first["start"] is None or item["start"] is None or abs(item["start"] - first["start"]) >= 70)
    ]
    picture = take(leftover, prefer_image=True) if leftover else None
    if picture and picture["image"] == 0:
        picture = take(leftover)
    used = [item for item in (first, picture) if item]
    third_pool = [
        item for item in leftover
        if item not in used and all(item["start"] is None or other["start"] is None or abs(item["start"] - other["start"]) >= 70 for other in used)
    ]
    third = take(third_pool)
    punches = []
    roles = (
        (first, "hardest", "The hardest punch."),
        (picture, "picture", "The sermon in one picture."),
        (third, "another", "One more, if you want it."),
    )
    for item, role, note in roles:
        if not item:
            continue
        item = _expand_punch(spoken, item)
        punches.append({
            "hook": item["hook"],
            "text": item["text"],
            "start": item["start"],
            "end": item["end"],
            "role": role,
            "note": note,
        })
    return punches


def _sentences(segment):
    pieces = re.split(r"(?<=[.!?])\s+", segment["text"].strip())
    return [piece.strip() for piece in pieces if piece.strip()]


def _score(text):
    words = re.findall(r"[A-Za-z']+", text)
    count = len(words)
    if count < 6 or count > 70:
        return 0
    score = 1
    if 10 <= count <= 40:
        score += 0.6
    if text.endswith("?"):
        score += 0.45
    if re.search(r"\b(I|we|you)\b", text):
        score += 0.15
    fillers = len(re.findall(r"\b(um+|uh+|you know|kind of|sort of)\b", text, re.I))
    score -= 0.25 * fillers
    if PROMO.search(text):
        return 0
    return score


def _windows(segments, seconds=300):
    if not segments:
        return []
    timed = [segment for segment in segments if segment["start"] is not None]
    if not timed:
        return [segments]
    groups = []
    bucket = [timed[0]]
    origin = timed[0]["start"]
    for segment in timed[1:]:
        if segment["start"] - origin >= seconds and bucket:
            groups.append(bucket)
            bucket = [segment]
            origin = segment["start"]
        else:
            bucket.append(segment)
    if bucket:
        groups.append(bucket)
    return groups


def _clip_bounds(segments, index):
    start = segments[index]["start"]
    end = segments[index]["end"] if segments[index]["end"] is not None else start
    texts = [segments[index]["text"].strip()]
    right = index
    while end - start < 12 and right + 1 < len(segments):
        nxt = segments[right + 1]
        if nxt["start"] is None or nxt["start"] - end > 2.5:
            break
        right += 1
        end = nxt["end"] if nxt["end"] is not None else nxt["start"]
        texts.append(nxt["text"].strip())
        if end - start >= 28:
            break
    left = index
    while end - start < 12 and left - 1 >= 0:
        prev = segments[left - 1]
        if prev["start"] is None or start - (prev["end"] or prev["start"]) > 2.5:
            break
        left -= 1
        start = prev["start"]
        texts.insert(0, prev["text"].strip())
        if end - start >= 28:
            break
    if end < start:
        end = start
    wide = (end - start) > 50
    return start, end, " ".join(texts), wide


def glean(segments, title):
    scripture = find_scripture(segments)
    sections = []
    ranked = []
    for group in _windows(segments):
        best = []
        for segment in group:
            for sentence in _sentences(segment):
                score = _score(sentence)
                if score <= 0:
                    continue
                best.append((score, segment, sentence))
        best.sort(key=lambda item: item[0], reverse=True)
        chosen = []
        used = set()
        for score, segment, sentence in best:
            key = sentence.lower()
            if key in used:
                continue
            used.add(key)
            chosen.append({
            "text": sentence,
            "start": segment["start"],
            "end": segment["end"],
            "score": score,
            "index": id(segment),
        })
            if len(chosen) == 2:
                break
        if not chosen:
            continue
        starts = [segment["start"] for segment in group if segment["start"] is not None]
        ends = [segment["end"] for segment in group if segment["end"] is not None]
        sections.append({
            "start": min(starts) if starts else None,
            "end": max(ends) if ends else None,
            "quotes": chosen,
        })
        ranked.extend(chosen)

    ranked.sort(key=lambda item: item["score"], reverse=True)
    clips = []
    taken_at = []
    index_of = {id(segment): index for index, segment in enumerate(segments)}
    for item in ranked:
        if len(clips) >= 8:
            break
        if item["start"] is None:
            continue
        if any(abs(item["start"] - previous) < 75 for previous in taken_at):
            continue
        index = index_of.get(item["index"])
        if index is None:
            continue
        start, end, text, wide = _clip_bounds(segments, index)
        clips.append({
            "start": start,
            "end": end,
            "text": text,
            "wide": wide,
        })
        taken_at.append(item["start"])
    clips.sort(key=lambda item: item["start"])
    for section in sections:
        for quote in section["quotes"]:
            quote.pop("score", None)
            quote.pop("index", None)

    words = sum(len(re.findall(r"[A-Za-z']+", segment["text"])) for segment in segments)
    starts = [segment["start"] for segment in segments if segment["start"] is not None]
    ends = [segment["end"] for segment in segments if segment["end"] is not None]
    return {
        "title": title,
        "wordCount": words,
        "duration": (max(ends) if ends else (max(starts) if starts else 0)) or 0,
        "hasTimes": bool(starts),
        "punches": find_punches(segments),
        "sections": sections,
        "clips": clips,
        "scripture": scripture,
        "transcript": segments,
    }


def to_markdown(result):
    lines = [f"# {result['title']}", ""]
    if result["hasTimes"]:
        lines.append(f"Spoken length about {format_clock(result['duration'])}. {result['wordCount']} words.")
    else:
        lines.append(f"{result['wordCount']} words. This file had no timestamps.")
    lines.append("")
    lines.append("Quotes below are the speaker's words. Times are the transcript's times.")
    lines.append("")
    punches = result.get("punches") or []
    if punches:
        lines.append("## Punches")
        lines.append("")
        for punch in punches:
            when = ""
            if punch["start"] is not None:
                when = f"{format_clock(punch['start'])} – {format_clock(punch['end'] or punch['start'])}"
            lines.append(f"### {punch['hook']}")
            if when:
                lines.append("")
                lines.append(when)
            lines.append("")
            lines.append(f"> {punch['text']}")
            lines.append("")
            lines.append(punch["note"])
            lines.append("")
    if result["clips"]:
        lines.append("## Clips")
        lines.append("")
        for clip in result["clips"]:
            lines.append(f"- {format_clock(clip['start'])} – {format_clock(clip['end'])}")
            lines.append(f"  > {clip['text']}")
            if clip["wide"]:
                lines.append("  > This timestamp covers a longer stretch. The line sits inside it.")
            lines.append("")
    lines.append("## In their words")
    lines.append("")
    for section in result["sections"]:
        if section["start"] is not None:
            lines.append(f"### {format_clock(section['start'])} – {format_clock(section['end'] or section['start'])}")
            lines.append("")
        for quote in section["quotes"]:
            when = ""
            if quote["start"] is not None:
                when = f" ({format_clock(quote['start'])})"
            lines.append(f"> {quote['text']}{when}")
            lines.append("")
    lines.append("## Scripture spoken")
    lines.append("")
    if not result["scripture"]:
        lines.append("No Bible reference was detected in this transcript.")
        lines.append("")
    for item in result["scripture"]:
        when = format_clock(item["start"]) if item["start"] is not None else ""
        if item["ref"]:
            lines.append(f"### {item['ref']}" + (f" · {when}" if when else ""))
            lines.append("")
            if item["verseText"]:
                lines.append(f"King James text: {item['verseText']}")
                lines.append("")
            lines.append(f"> {item['heard']}")
            lines.append("")
            lines.append("Read the verses around this citation, then set them next to the sentence above.")
            lines.append("")
        else:
            lines.append(f"- {when} {item['note']}")
            lines.append(f"  > {item['heard']}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_srt(segments):
    rows = []
    number = 1
    for segment in segments:
        if segment["start"] is None:
            continue
        end = segment["end"] if segment["end"] is not None else segment["start"] + 2
        rows.append(str(number))
        rows.append(f"{_srt_stamp(segment['start'])} --> {_srt_stamp(end)}")
        rows.append(segment["text"].strip())
        rows.append("")
        number += 1
    return "\n".join(rows)


def _srt_stamp(seconds):
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"
