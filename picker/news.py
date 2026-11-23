"""Recent headlines per company from the Google News RSS feed."""
from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from .config import MAX_HEADLINES, NEWS_HOURS


def fetch_headlines(name: str, hours: int = NEWS_HOURS, limit: int = MAX_HEADLINES) -> list[dict]:
    q = urllib.parse.quote_plus(f'"{name}" stock when:{max(1, hours // 24)}d')
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    seen, items = set(), []
    for it in ET.fromstring(r.content).iter("item"):
        title = (it.findtext("title") or "").strip()
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate"))
        except (TypeError, ValueError):
            continue
        key = re.sub(r"\W+", "", title.lower())[:60]
        if not title or key in seen or pub < cutoff:
            continue
        seen.add(key)
        items.append({"title": title, "source": it.findtext("source") or "",
                      "published": pub.isoformat()})
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:limit]
