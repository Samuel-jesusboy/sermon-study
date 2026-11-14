"""Bible text from bible-api.com (free, public-domain translations only)."""
import re

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
BASE = "https://bible-api.com"

# Public-domain translations served by bible-api.com. NIV/ESV/NKJV are licensed and need a paid API.
VERSIONS = [
    {"id": "kjv", "name": "King James Version", "short": "KJV"},
    {"id": "web", "name": "World English Bible", "short": "WEB"},
    {"id": "webbe", "name": "World English Bible (British)", "short": "WEBBE"},
    {"id": "bbe", "name": "Bible in Basic English", "short": "BBE"},
    {"id": "oeb-us", "name": "Open English Bible", "short": "OEB"},
]
VERSION_IDS = {v["id"] for v in VERSIONS}

BOOKS = [
    ("Genesis", 50), ("Exodus", 40), ("Leviticus", 27), ("Numbers", 36), ("Deuteronomy", 34), ("Joshua", 24),
    ("Judges", 21), ("Ruth", 4), ("1 Samuel", 31), ("2 Samuel", 24), ("1 Kings", 22), ("2 Kings", 25),
    ("1 Chronicles", 29), ("2 Chronicles", 36), ("Ezra", 10), ("Nehemiah", 13), ("Esther", 10), ("Job", 42),
    ("Psalms", 150), ("Proverbs", 31), ("Ecclesiastes", 12), ("Song of Solomon", 8), ("Isaiah", 66),
    ("Jeremiah", 52), ("Lamentations", 5), ("Ezekiel", 48), ("Daniel", 12), ("Hosea", 14), ("Joel", 3),
    ("Amos", 9), ("Obadiah", 1), ("Jonah", 4), ("Micah", 7), ("Nahum", 3), ("Habakkuk", 3), ("Zephaniah", 3),
    ("Haggai", 2), ("Zechariah", 14), ("Malachi", 4), ("Matthew", 28), ("Mark", 16), ("Luke", 24), ("John", 21),
    ("Acts", 28), ("Romans", 16), ("1 Corinthians", 16), ("2 Corinthians", 13), ("Galatians", 6),
    ("Ephesians", 6), ("Philippians", 4), ("Colossians", 4), ("1 Thessalonians", 5), ("2 Thessalonians", 3),
    ("1 Timothy", 6), ("2 Timothy", 4), ("Titus", 3), ("Philemon", 1), ("Hebrews", 13), ("James", 5),
    ("1 Peter", 5), ("2 Peter", 3), ("1 John", 5), ("2 John", 1), ("3 John", 1), ("Jude", 1), ("Revelation", 22),
]


def _version(v: str) -> str:
    v = (v or "kjv").lower()
    return v if v in VERSION_IDS else "kjv"


async def fetch_passage(ref: str, version: str = "kjv") -> dict:
    ref = re.sub(r"\s+", " ", (ref or "").strip())
    if not ref:
        raise ValueError("empty reference")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{BASE}/{ref}", params={"translation": _version(version)})
        resp.raise_for_status()
        data = resp.json()
    verses = data.get("verses") or []
    return {
        "reference": data.get("reference", ref),
        "book": verses[0]["book_name"] if verses else "",
        "chapter": verses[0]["chapter"] if verses else 0,
        "verses": [{"book": v["book_name"], "chapter": v["chapter"], "verse": v["verse"], "text": v["text"].strip()}
                   for v in verses],
        "version": _version(version).upper(),
    }


@router.get("/versions")
def get_versions():
    return VERSIONS


@router.get("/books")
def get_books(version: str = "kjv"):
    return [{"name": n, "chapters": c} for n, c in BOOKS]


@router.get("/chapter")
async def get_chapter(book: str = Query(...), chapter: int = Query(..., ge=1), version: str = "kjv"):
    try:
        p = await fetch_passage(f"{book} {chapter}", version)
        return {"book": book, "chapter": chapter, "verses": [{"verse": v["verse"], "text": v["text"]} for v in p["verses"]],
                "version": p["version"]}
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=404, detail=f"Could not load {book} {chapter}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"The Bible service is not reachable right now ({e.__class__.__name__}).")


@router.get("/lookup")
async def lookup_reference(ref: str = Query(...), version: str = "kjv"):
    try:
        p = await fetch_passage(ref, version)
        if not p["verses"]:
            raise ValueError("no verses")
        return {**p, "verses": [{"verse": v["verse"], "text": v["text"], "chapter": v["chapter"]} for v in p["verses"]]}
    except Exception:
        raise HTTPException(status_code=404, detail=f"Could not find '{ref}'. Try John 3:16 or Romans 8:28-30.")


@router.get("/search")
async def search_bible(q: str = Query(..., min_length=2), version: str = "kjv"):
    try:
        p = await fetch_passage(q, version)
        results = [{"reference": f"{v['book']} {v['chapter']}:{v['verse']}", "text": v["text"], "book": v["book"],
                    "chapter": v["chapter"], "verse": v["verse"]} for v in p["verses"]]
        return {"results": results, "total": len(results), "query": q}
    except Exception:
        raise HTTPException(status_code=400, detail='Search by reference, like "John 3:16" or "Psalms 23".')
