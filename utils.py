#!/usr/bin/env python3
"""
Shared utilities for GitHub issue processing
Contains URL generation, label handling, and issue number extraction utilities
Used by product_status_report.py, generate_business_slide.py, and other analysis tools
"""

import pandas as pd
from typing import Dict, List, Optional, Union, Any


def generate_issue_url(issue: Dict[str, Any], github_owner: Optional[str] = None, github_repo: Optional[str] = None) -> str:
    """
    Generate standardized GitHub issue URL from issue data.

    Args:
        issue: Issue dictionary containing number/issue_number and optionally github_issue_url
        github_owner: GitHub repository owner (optional if github_issue_url is in issue)
        github_repo: GitHub repository name (optional if github_issue_url is in issue)

    Returns:
        Formatted GitHub issue URL or fallback issue reference
    """
    # Try to get issue number from various possible fields
    issue_num = issue.get('number', issue.get('issue_number'))

    # Use pre-computed URL if available
    if 'github_issue_url' in issue:
        return issue['github_issue_url']

    # Generate URL if we have owner/repo
    if github_owner and github_repo and issue_num:
        return f"https://github.com/{github_owner}/{github_repo}/issues/{issue_num}"

    # Fallback to simple issue reference
    return f"Issue #{issue_num}" if issue_num else "Issue #Unknown"


def get_issue_number(issue: Dict[str, Any]) -> Optional[int]:
    """
    Extract issue number from various possible fields in issue data.

    Args:
        issue: Issue dictionary that may contain 'number' or 'issue_number'

    Returns:
        Issue number as integer, or None if not found
    """
    number = issue.get('number', issue.get('issue_number'))
    if number is not None:
        try:
            return int(number)
        except (ValueError, TypeError):
            pass
    return None


def format_labels_for_display(raw_labels: Union[List, str, None], separator: str = ', ') -> str:
    """
    Format labels for display in reports and UI.

    Args:
        raw_labels: Labels in GraphQL format (list of dicts with 'name') or REST format (list of strings)
        separator: String to join labels with (default: ', ')

    Returns:
        Formatted string of label names joined by separator
    """
    if not raw_labels:
        return ""

    if isinstance(raw_labels, list) and raw_labels and isinstance(raw_labels[0], dict):
        # GraphQL format: [{'name': 'product/ai'}, ...]
        return separator.join([label['name'] for label in raw_labels])
    elif isinstance(raw_labels, list):
        # List of strings
        return separator.join([str(label) for label in raw_labels])
    elif raw_labels is not None and not pd.isna(raw_labels):
        # String or other format
        return str(raw_labels)
    else:
        return ""


def format_status_emoji(issue: Dict[str, Any]) -> str:
    """
    Generate status emoji based on issue state and assignment.

    Args:
        issue: Issue dictionary containing state, assignee, project status, etc.

    Returns:
        Appropriate emoji for the issue status
    """
    state = issue.get('state', '').lower()
    assignee = issue.get('assignee') or issue.get('assignees')

    # Closed issues
    if state == 'closed':
        return "✅"

    # Check project board status for more specific states
    project_items = issue.get('project_items', [])
    for item in project_items:
        status = item.get('fields', {}).get('Status', '')
        if status == 'Dev In Progress':
            return "🔄"
        elif status in ['Code Review', 'Testing']:
            return "🔍"
        elif status in ['Ready for Dev', 'Ready to Start']:
            return "📋"

    # Fallback to assignment-based status
    if assignee:
        return "👤"  # Assigned but no specific project status
    else:
        return "📝"  # Unassigned


def extract_issue_summary_data(issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract key data fields from issue for AI analysis and caching.

    Args:
        issue: Full issue dictionary

    Returns:
        Simplified dictionary with key fields for analysis
    """
    return {
        'number': get_issue_number(issue),
        'title': issue.get('title', ''),
        'body': issue.get('body', '')[:500] if issue.get('body') else '',  # First 500 chars
        'labels': issue.get('labels', []),
        'state': issue.get('state', ''),
        'assignee': issue.get('assignee') or issue.get('assignees'),
        'milestone': issue.get('milestone'),
        'created_at': issue.get('created_at'),
        'updated_at': issue.get('updated_at'),
        'closed_at': issue.get('closed_at')
    }


def normalize_issue_data(issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize issue data to ensure consistent field formats across GraphQL/REST sources.

    Args:
        issue: Raw issue data from GitHub API

    Returns:
        Normalized issue dictionary with consistent field formats
    """
    normalized = issue.copy()

    # Normalize labels to consistent format for internal processing
    if 'labels' in normalized:
        labels = normalized['labels']
        if isinstance(labels, list) and labels and isinstance(labels[0], dict):
            # Convert GraphQL format to simple list of names for easier processing
            normalized['labels_names'] = [label['name'] for label in labels]
        elif isinstance(labels, list):
            # Already list of strings
            normalized['labels_names'] = [str(label) for label in labels]
        else:
            # String or other format
            normalized['labels_names'] = [str(labels)] if labels else []

    # Ensure consistent assignee format
    if 'assignees' in normalized and not normalized.get('assignee'):
        assignees = normalized['assignees']
        if assignees and len(assignees) > 0:
            # Use first assignee as primary assignee
            normalized['assignee'] = assignees[0]

    return normalized