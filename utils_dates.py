#!/usr/bin/env python3
"""
Shared date range utilities for GitHub issue analysis
Used by product_status_report.py and generate_business_slide.py
"""

from datetime import datetime, timedelta, timezone
from config import RECENTLY_COMPLETED_DAYS


def is_recently_completed(issue_dict: dict) -> bool:
    """Check if issue was completed in the configured recent period (default 7 days)"""
    closed_at = issue_dict.get('closed_at')
    if not closed_at or issue_dict.get('state') != 'closed':
        return False

    try:
        # Parse the closed_at date
        if isinstance(closed_at, str):
            # Handle ISO format dates like "2025-09-18T15:25:13Z"
            closed_date = datetime.fromisoformat(closed_at.replace('Z', '+00:00'))
        else:
            closed_date = closed_at

        # Remove timezone info for comparison with timezone-naive datetime
        if closed_date.tzinfo is not None:
            closed_date = closed_date.replace(tzinfo=None)

        # Check if closed within recently completed period
        cutoff_date = datetime.now() - timedelta(days=RECENTLY_COMPLETED_DAYS)
        return closed_date >= cutoff_date
    except (ValueError, AttributeError):
        return False


def get_week_boundaries():
    """
    Get standardized week boundaries for consistent date filtering.

    Returns:
        dict: Dictionary containing week boundary dates
    """
    now = datetime.now(timezone.utc)
    days_since_monday = now.weekday()  # Monday = 0, Sunday = 6

    # Calculate this week's boundaries
    current_week_monday = now - timedelta(days=days_since_monday)
    this_week_sunday = current_week_monday + timedelta(days=6)

    # Calculate last week's boundaries
    last_week_monday = current_week_monday - timedelta(days=7)
    last_week_sunday = current_week_monday - timedelta(days=1)

    # Calculate next week's boundaries
    next_week_monday = current_week_monday + timedelta(days=7)
    next_week_sunday = current_week_monday + timedelta(days=13)

    return {
        'now': now,
        'current_week_monday': current_week_monday,
        'this_week_sunday': this_week_sunday,
        'last_week_monday': last_week_monday,
        'last_week_sunday': last_week_sunday,
        'next_week_monday': next_week_monday,
        'next_week_sunday': next_week_sunday
    }


def get_date_ranges():
    """
    Get date ranges for filtering issues by completion/creation time.

    Returns:
        dict: Dictionary containing various date ranges and boundaries
    """
    boundaries = get_week_boundaries()

    return {
        **boundaries,
        'recently_completed_cutoff': datetime.now() - timedelta(days=RECENTLY_COMPLETED_DAYS)
    }


def is_created_this_week(issue_dict: dict, boundaries: dict = None) -> bool:
    """Check if issue was created this week"""
    if boundaries is None:
        boundaries = get_week_boundaries()

    created_at = issue_dict.get('created_at')
    if not created_at:
        return False

    try:
        created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        return (boundaries['current_week_monday'] <= created_date <= boundaries['this_week_sunday'])
    except (ValueError, AttributeError):
        return False


def is_created_last_week(issue_dict: dict, boundaries: dict = None) -> bool:
    """Check if issue was created last week"""
    if boundaries is None:
        boundaries = get_week_boundaries()

    created_at = issue_dict.get('created_at')
    if not created_at:
        return False

    try:
        created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        return (boundaries['last_week_monday'] <= created_date <= boundaries['last_week_sunday'])
    except (ValueError, AttributeError):
        return False


def is_closed_last_week(issue_dict: dict, boundaries: dict = None) -> bool:
    """Check if issue was closed last week"""
    if boundaries is None:
        boundaries = get_week_boundaries()

    closed_at = issue_dict.get('closed_at')
    if not closed_at or issue_dict.get('state') != 'closed':
        return False

    try:
        closed_date = datetime.fromisoformat(closed_at.replace('Z', '+00:00'))
        return (boundaries['last_week_monday'] <= closed_date <= boundaries['last_week_sunday'])
    except (ValueError, AttributeError):
        return False


def parse_issue_date(date_str: str) -> datetime:
    """
    Parse ISO format date string from GitHub API.

    Args:
        date_str: ISO format date string like "2025-09-18T15:25:13Z"

    Returns:
        datetime object with timezone info
    """
    if isinstance(date_str, str):
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    return date_str