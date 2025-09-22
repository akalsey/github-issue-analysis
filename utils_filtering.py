#!/usr/bin/env python3
"""
Shared filtering utilities for GitHub issue analysis
Used by product_status_report.py and generate_business_slide.py
"""

from config import (
    STRATEGIC_INCLUDE_PATTERNS,
    STRATEGIC_EXCLUDE_PATTERNS,
    NEXT_WEEK_INDICATORS,
    PROJECT_BOARD_ACTIVE_STATUSES,
    COMPLETION_KEYWORDS,
    CRITICAL_CUSTOMER_INDICATORS,
    MAJOR_CUSTOMER_NAMES,
    HIGH_PRIORITY_PATTERNS
)


def normalize_labels(raw_labels) -> str:
    """
    Normalize labels from either GraphQL or REST format to a single string.

    Args:
        raw_labels: Labels in GraphQL format (list of dicts with 'name') or REST format (list of strings)

    Returns:
        Lowercase string of all label names joined by spaces
    """
    if not raw_labels:
        return ""

    if isinstance(raw_labels, list) and raw_labels and isinstance(raw_labels[0], dict):
        # GraphQL format: [{'name': 'product/ai'}, ...]
        return ' '.join([label['name'].lower() for label in raw_labels])
    else:
        # REST format or string format
        return str(raw_labels).lower()


def is_strategic_work(issue_dict: dict) -> bool:
    """
    Filter for strategic business value work vs operational maintenance.
    Same logic as cycle_time.py for consistency.

    INCLUDE: product work, features, customer issues, epics
    EXCLUDE: chores, deployments, infrastructure, compliance tasks
    """
    labels_str = normalize_labels(issue_dict.get('labels', []))

    # Check for exclusion patterns first (higher priority)
    for pattern in STRATEGIC_EXCLUDE_PATTERNS:
        if pattern in labels_str:
            return False

    # Check for inclusion patterns
    for pattern in STRATEGIC_INCLUDE_PATTERNS:
        if pattern in labels_str:
            return True

    # Default: exclude unlabeled or unclear work
    return False


def is_scheduled_next_week(issue_dict: dict) -> bool:
    """Check if issue is scheduled for next week using enhanced prediction logic"""
    # Skip closed issues - they shouldn't be in upcoming list
    if issue_dict.get('state') == 'closed':
        return False

    # Get project board status - strongest predictor
    project_items = issue_dict.get('project_items', [])
    for item in project_items:
        status = item.get('fields', {}).get('Status', '')
        if status in PROJECT_BOARD_ACTIVE_STATUSES:
            return True

    # Check if assigned and high priority (P0, P1, P2)
    assignee = issue_dict.get('assignee') or issue_dict.get('assignees')
    if assignee:
        raw_labels = issue_dict.get('labels', [])
        if isinstance(raw_labels, list) and raw_labels:
            for label in raw_labels:
                label_name = label.get('name', '') if isinstance(label, dict) else str(label)
                if label_name.startswith('P') and len(label_name) == 2 and label_name[1].isdigit():
                    priority_num = int(label_name[1])
                    if priority_num <= 2:  # P0, P1, P2
                        return True

    # Look for completion signals in recent comments
    comment_list = issue_dict.get('comment_list', [])
    if comment_list:
        recent_comments = comment_list[-3:]  # Last 3 comments
        for comment in recent_comments:
            comment_body = comment.get('body', '').lower()
            if any(keyword in comment_body for keyword in COMPLETION_KEYWORDS):
                return True

    # Traditional label-based detection as fallback
    labels_str = normalize_labels(issue_dict.get('labels', []))
    return any(indicator in labels_str for indicator in NEXT_WEEK_INDICATORS)


def is_critical_customer_issue(issue_dict: dict) -> bool:
    """Check if issue is a critical customer issue requiring executive attention"""
    # Skip closed issues - they shouldn't be in customer report
    if issue_dict.get('state') == 'closed':
        return False

    labels_str = normalize_labels(issue_dict.get('labels', []))
    title = issue_dict.get('title', '').lower()

    # Check for critical indicators in labels
    has_critical_label = any(indicator in labels_str for indicator in CRITICAL_CUSTOMER_INDICATORS)

    # Check for customer names in title
    has_customer_name = any(customer in title for customer in MAJOR_CUSTOMER_NAMES)

    # Priority level indicators (P0, P1)
    has_high_priority = any(priority in labels_str for priority in HIGH_PRIORITY_PATTERNS)

    # Bug type issues
    is_bug = 'type/bug' in labels_str

    # Must be a bug OR have customer indicators OR be high priority
    return (is_bug and (has_customer_name or has_critical_label)) or has_high_priority or has_customer_name


def is_work_in_progress(issue_dict: dict) -> bool:
    """Check if issue is currently in progress using project board status"""
    # Skip closed issues - they can't be in progress
    if issue_dict.get('state') == 'closed':
        return False

    project_items = issue_dict.get('project_items', [])
    for item in project_items:
        status = item.get('fields', {}).get('Status', '')
        if status == 'Dev In Progress':
            return True

    # Fallback to assignee check
    return bool(issue_dict.get('assignee') or issue_dict.get('assignees'))