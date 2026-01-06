"""
Date parsing utilities for various formats.
"""

import re
from datetime import datetime, timedelta
from typing import Optional
import logging

from dateutil import parser as date_parser
from dateutil.tz import tzutc

logger = logging.getLogger(__name__)


def parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse a date string in various formats.

    Args:
        date_str: Date string to parse

    Returns:
        datetime object or None if parsing failed
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # Try relative date first
    relative = parse_relative_date(date_str)
    if relative:
        return relative

    # Try standard parsing
    try:
        dt = date_parser.parse(date_str, fuzzy=True)
        # Remove timezone if present for consistency
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        return dt
    except (ValueError, TypeError) as e:
        logger.debug(f"Could not parse date '{date_str}': {e}")
        return None


def parse_relative_date(date_str: str) -> Optional[datetime]:
    """
    Parse relative date strings like "5 hours ago", "2 days ago".

    Args:
        date_str: Relative date string

    Returns:
        datetime object or None if not a relative date
    """
    if not date_str:
        return None

    date_str = date_str.strip().lower()
    now = datetime.now()

    # Patterns for relative dates
    patterns = [
        (r'(\d+)\s*seconds?\s*ago', lambda m: now - timedelta(seconds=int(m.group(1)))),
        (r'(\d+)\s*minutes?\s*ago', lambda m: now - timedelta(minutes=int(m.group(1)))),
        (r'(\d+)\s*hours?\s*ago', lambda m: now - timedelta(hours=int(m.group(1)))),
        (r'(\d+)\s*days?\s*ago', lambda m: now - timedelta(days=int(m.group(1)))),
        (r'(\d+)\s*weeks?\s*ago', lambda m: now - timedelta(weeks=int(m.group(1)))),
        (r'(\d+)\s*months?\s*ago', lambda m: now - timedelta(days=int(m.group(1)) * 30)),
        (r'(\d+)\s*years?\s*ago', lambda m: now - timedelta(days=int(m.group(1)) * 365)),
        (r'just now', lambda m: now),
        (r'a minute ago', lambda m: now - timedelta(minutes=1)),
        (r'an hour ago', lambda m: now - timedelta(hours=1)),
        (r'a day ago', lambda m: now - timedelta(days=1)),
        (r'yesterday', lambda m: now - timedelta(days=1)),
        (r'a week ago', lambda m: now - timedelta(weeks=1)),
        (r'a month ago', lambda m: now - timedelta(days=30)),
        (r'a year ago', lambda m: now - timedelta(days=365)),
    ]

    for pattern, converter in patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                return converter(match)
            except Exception:
                continue

    return None


def parse_wordpress_date(date_str: str) -> Optional[datetime]:
    """
    Parse WordPress-style date formats.

    Common formats:
    - "January 20, 2017"
    - "2017-01-20"
    - "2017-01-20T15:30:00+00:00"
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # Common WordPress formats
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",  # ISO with timezone
        "%Y-%m-%dT%H:%M:%S",    # ISO without timezone
        "%Y-%m-%d %H:%M:%S",    # SQL-style
        "%Y-%m-%d",             # Date only
        "%B %d, %Y",            # "January 20, 2017"
        "%b %d, %Y",            # "Jan 20, 2017"
        "%d %B %Y",             # "20 January 2017"
        "%d %b %Y",             # "20 Jan 2017"
        "%m/%d/%Y",             # US format
        "%d/%m/%Y",             # EU format
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return dt
        except ValueError:
            continue

    # Fall back to dateutil
    return parse_date(date_str)


def format_date_for_output(dt: datetime, include_time: bool = True) -> str:
    """
    Format datetime for output.

    Args:
        dt: datetime object
        include_time: Whether to include time component

    Returns:
        Formatted date string
    """
    if not dt:
        return ""

    if include_time:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        return dt.strftime("%Y-%m-%d")
