#!/usr/bin/env python3
"""
Generate detailed executive product status report from cycle time data
Uses OpenAI to create intelligent summaries and groupings of open issues
Focus on business impact, customer issues, and strategic initiatives
"""
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "pandas",
#     "openai",
#     "python-dotenv",
#     "pytz",
# ]
# ///

import pandas as pd
import re
import os
import hashlib
import json
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# Import configuration
from config import (
    CRITICAL_CUSTOMER_INDICATORS,
    MAJOR_CUSTOMER_NAMES,
    HIGH_PRIORITY_PATTERNS,
    AI_ANALYSIS_TEMPERATURE,
    AI_SUMMARY_CACHE_FILE,
    get_openai_model,
    validate_configuration
)

# Import shared utilities
from utils_filtering import (
    normalize_labels,
    is_strategic_work,
    is_scheduled_next_week,
    is_critical_customer_issue,
    is_work_in_progress
)
from utils_dates import (
    is_recently_completed,
    get_date_ranges,
    get_week_boundaries
)
from utils import (
    generate_issue_url,
    get_issue_number,
    format_labels_for_display,
    format_status_emoji
)
from ai_service import AIAnalysisService
from report_generator import ReportGenerator

def display_status_bar(current, total, description, eta_seconds=None, terminal_width=None):
    """Display a progress status bar with description and optional ETA"""
    if terminal_width is None:
        terminal_width = shutil.get_terminal_size().columns

    # Progress percentage
    percentage = (current / total) * 100 if total > 0 else 0

    # ETA formatting
    eta_text = ""
    if eta_seconds is not None and eta_seconds > 0:
        if eta_seconds < 60:
            eta_text = f" ETA: {eta_seconds:.0f}s"
        elif eta_seconds < 3600:
            eta_text = f" ETA: {eta_seconds/60:.1f}m"
        else:
            eta_text = f" ETA: {eta_seconds/3600:.1f}h"

    # Status indicators
    if percentage == 100:
        status_icon = "✅"
    elif current > 0:
        status_icon = "🔄"
    else:
        status_icon = "⏳"

    # Reserve space for percentage, counters, and ETA
    reserved_space = len(f" {percentage:5.1f}% ({current}/{total}){eta_text}")
    available_width = max(20, terminal_width - reserved_space - 4)  # 4 for icon and spacing

    # Truncate description if needed
    if len(description) > available_width:
        description = description[:available_width-3] + "..."

    # Calculate progress bar width (minimum 10 chars)
    bar_width = max(10, available_width - len(description) - 1)
    filled = int((current / total) * bar_width) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_width - filled)

    # Build status line
    status_line = f"\r{status_icon} {description} {bar} {percentage:5.1f}% ({current}/{total}){eta_text}"

    # Ensure we don't exceed terminal width
    if len(status_line) > terminal_width:
        status_line = status_line[:terminal_width-1]

    # Print with carriage return (overwrites current line)
    print(status_line, end='', flush=True)

    # Print newline when complete
    if current >= total:
        print()

class AISummaryCache:
    """Cache for AI-generated issue summaries based on content hash"""

    def __init__(self, cache_file=AI_SUMMARY_CACHE_FILE):
        self.cache_file = cache_file
        self.cache = self._load_cache()

    def _load_cache(self):
        """Load cache from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️  Cache load error: {e}")
        return {}

    def _save_cache(self):
        """Save cache to file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except IOError as e:
            print(f"⚠️  Cache save error: {e}")

    def _get_content_hash(self, issue):
        """Generate hash for issue content to detect changes"""
        # Include key content that affects summary
        content_parts = [
            str(issue.get('number', '')),
            issue.get('title', ''),
            issue.get('body', '')[:500],  # First 500 chars of body
            str(issue.get('labels', [])),
            str(issue.get('state', '')),
            str(issue.get('assignee', ''))
        ]

        # Include recent comments if available
        comment_list = issue.get('comment_list', [])
        if comment_list:
            # Use last 2 comment bodies for hash
            recent_comments = comment_list[-2:]
            for comment in recent_comments:
                if isinstance(comment, dict) and comment.get('body'):
                    content_parts.append(comment['body'][:100])

        content = '|'.join(content_parts)
        return hashlib.md5(content.encode()).hexdigest()

    def get_summary(self, issue):
        """Get cached summary for issue if content hasn't changed"""
        issue_number = str(issue.get('number', issue.get('issue_number', 'unknown')))
        content_hash = self._get_content_hash(issue)

        if issue_number in self.cache:
            cached_entry = self.cache[issue_number]
            if cached_entry.get('content_hash') == content_hash:
                return cached_entry.get('summary')

        return None

    def set_summary(self, issue, summary):
        """Cache summary for issue with content hash"""
        issue_number = str(issue.get('number', issue.get('issue_number', 'unknown')))
        content_hash = self._get_content_hash(issue)

        self.cache[issue_number] = {
            'summary': summary,
            'content_hash': content_hash,
            'generated_at': datetime.now().isoformat()
        }

        self._save_cache()

# is_strategic_work moved to utils_filtering.py

def categorize_issue(row):
    """Categorize issues by business priority and type"""
    labels = normalize_labels(row.labels)
        
    title = str(row.title).lower()
    
    # Customer issues (highest priority)
    if any(x in labels for x in ['area/customer', 'revenue-impact', 'customer-escalation']):
        return 'customer'
    if any(x in title for x in MAJOR_CUSTOMER_NAMES):
        return 'customer'
    
    # Major features/epics - strategic initiatives
    if 'epic' in labels:
        return 'feature'
    if any(x in title for x in ['fabric', 'swml', 'laml', 'ai agent', 'calling api']):
        return 'feature'
        
    # Platform/Infrastructure - operational excellence
    if any(x in labels for x in ['team/platform', 'dev/iac', 'compliance', 'security']):
        return 'platform'
    if any(x in title for x in ['deploy', 'access', 'monitoring', 'infrastructure']):
        return 'platform'
        
    # Product features - core functionality
    if any(x in labels for x in ['product/ai', 'product/voice', 'product/video', 'product/messaging']):
        return 'product'
        
    # Operations and bugs
    if 'type/bug' in labels or 'bug' in title:
        return 'bugs'
        
    return 'other'

def get_work_status(row):
    """Determine work progress for executive reporting"""
    has_assignee = pd.notna(row.assignee) if hasattr(row, 'assignee') else False
    has_work_started = pd.notna(row.work_started_at) if hasattr(row, 'work_started_at') else False
    
    # For GraphQL data, also check if assignees list is not empty
    if not has_assignee and hasattr(row, 'assignees'):
        if isinstance(row.assignees, list) and len(row.assignees) > 0:
            has_assignee = True
    
    if has_assignee and has_work_started:
        return 'active'  # Work in progress
    elif has_assignee or has_work_started:
        return 'started'  # Work started but not fully active
    else:
        return 'planned'  # Not yet started


def analyze_issue_with_ai(client, issue, category, cache=None):
    """Use OpenAI to analyze issue and generate detailed executive summary"""
    if not client:
        return None

    # Check cache first
    if cache:
        cached_summary = cache.get_summary(issue)
        if cached_summary:
            return cached_summary

    title = issue.get('title', '')
    labels = format_labels_for_display(issue.get('labels', []), ' ')

    assignee = issue.get('assignee', 'Unassigned')
    state = issue.get('state', 'unknown')

    # Get truncated issue body
    body = issue.get('body', '')
    # Truncate very long bodies to avoid token limits
    if len(body) > 1000:
        body = body[:1000] + "...[truncated]"

    # Check qualification reasons for context
    qualification_reasons = issue.get('qualification_reason', [])
    context = ""
    if 'recently_completed' in qualification_reasons:
        context = "This issue was recently completed."
    elif 'scheduled_next_week' in qualification_reasons:
        context = "This issue is scheduled for next week or currently in development."
    elif 'critical_customer' in qualification_reasons:
        context = "This is a critical customer issue."

    # Get recent comments for customer issues and bugs
    comments_context = ""
    if ('area/customer' in labels.lower() or 'type/bug' in labels.lower()):
        # First try to get from comment_list (new format with actual content)
        comment_list = issue.get('comment_list', [])
        if comment_list:
            recent_comments = comment_list[-4:]  # Last 4 comments
            comment_texts = []
            for comment in recent_comments:
                if isinstance(comment, dict) and comment.get('body'):
                    comment_body = comment['body'][:200]  # Last 4 comments, 200 chars each
                    # Clean up common noise in comments
                    if not any(noise in comment_body.lower() for noise in ['cc @', '/cc @', 'thanks!', 'thank you']):
                        comment_texts.append(comment_body)
            if comment_texts:
                comments_context = f"\n\nRecent comments: {' | '.join(comment_texts)}"
        elif issue.get('comments', 0) > 0:
            # Fallback: if comments is just a count, note that there are comments but we don't have the content
            comments_context = f"\n\nNote: This issue has {issue.get('comments')} comments (content not available in current data)"

    prompt = f"""
Write a terse 1-2 sentence summary. Be direct and factual. Do NOT start with "This issue" or similar phrases.

Title: {title}
Labels: {labels}
Status: {state}

Description: {body}{comments_context}

State the problem/bug/feature directly. Include specific technical details if available.

Examples:
BAD: "This issue addresses a critical bug where calls disconnect after one hour"
GOOD: "Critical bug where calls disconnect after one hour. Websocket connection closing due to suspected customer VPN network issues."

Format: Direct facts, 1-2 sentences maximum.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "You are a senior business analyst writing detailed executive briefings on technical projects. Your audience is C-level executives who need to understand business impact, strategic value, and risks. Focus on business outcomes, customer impact, revenue implications, and competitive positioning."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=200,
            reasoning_effort="low"
        )
        summary = response.choices[0].message.content.strip()

        # Cache the new summary
        if cache:
            cache.set_summary(issue, summary)

        return summary
    except Exception as e:
        error_message = str(e)
        issue_num = issue.get('number', issue.get('issue_number', 'unknown'))
        print(f"AI analysis failed for issue {issue_num}: {error_message}")

        # If it's a token limit error, try again with much shorter content
        if 'max_tokens' in error_message.lower() or 'output limit' in error_message.lower():
            try:
                print(f"Retrying issue {issue_num} with truncated content...")
                # Create a much shorter prompt for problematic issues
                short_prompt = f"""
Write a terse 1-2 sentence summary. Be direct and factual. Do NOT start with "This issue" or similar phrases.

Title: {title}
Labels: {labels}
Status: {state}

Brief description: {body[:300]}...

State the problem/bug/feature directly.
"""
                response = client.chat.completions.create(
                    model="gpt-5-nano",
                    messages=[
                        {"role": "system", "content": "You are a business analyst writing concise technical summaries."},
                        {"role": "user", "content": short_prompt}
                    ],
                    max_completion_tokens=100,
                    reasoning_effort="low"
                )
                summary = response.choices[0].message.content.strip()

                # Cache the fallback summary
                if cache:
                    cache.set_summary(issue, summary)

                print(f"Successfully generated fallback summary for issue {issue_num}")
                return summary
            except Exception as fallback_error:
                print(f"Fallback AI analysis also failed for issue {issue_num}: {fallback_error}")
                return None

        return None

def group_issues_by_topic_areas(client, issues):
    """Group issues by major topic areas using AI"""
    if not client or not issues:
        return None

    try:
        # Prepare issue data for AI analysis
        issue_data = []
        for issue in issues:
            issue_info = {
                'number': issue.get('number', issue.get('issue_number')),
                'title': issue.get('title', ''),
                'labels': issue.get('labels', [])
            }
            # Extract label names if they're objects
            if isinstance(issue_info['labels'], list) and issue_info['labels'] and isinstance(issue_info['labels'][0], dict):
                issue_info['labels'] = [label['name'] for label in issue_info['labels']]
            issue_data.append(issue_info)

        prompt = f"""Analyze these {len(issues)} issues and group them by major topic areas. Create 3-6 high-level topic groups that capture the main themes. Each group should contain multiple related issues.

Issues to analyze:
{chr(10).join([f"#{item['number']}: {item['title']} (labels: {', '.join(item['labels']) if item['labels'] else 'none'})" for item in issue_data])}

Return a JSON object with this structure:
{{
  "topic_groups": [
    {{
      "topic_name": "Clear topic name (e.g., 'WhatsApp Messaging Features')",
      "description": "Brief description of what this group covers",
      "issue_numbers": [list of issue numbers in this group],
      "summary": "One sentence summary of the work in this area"
    }}
  ]
}}

Focus on major functional areas like messaging, calling, onboarding, infrastructure, etc. Group related technical details under broader themes."""

        response = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": prompt}]
        )

        import json
        result = json.loads(response.choices[0].message.content)
        return result.get('topic_groups', [])

    except Exception as e:
        print(f"⚠️  Topic grouping failed: {e}")
        return None

def generate_backlog_summary_with_ai(client, all_issues, qualifying_issues):
    """Generate executive summary of product backlog themes"""
    if not client:
        return None

    # Get issues that weren't already included in the main report
    qualifying_issue_numbers = set(str(issue.get('number', issue.get('issue_number', ''))) for issue in qualifying_issues)
    backlog_issues = [issue for issue in all_issues
                     if str(issue.get('number', issue.get('issue_number', ''))) not in qualifying_issue_numbers]

    if not backlog_issues:
        return None

    # Limit to prevent overly long prompts - sample representative issues
    sample_size = min(50, len(backlog_issues))
    sample_issues = backlog_issues[:sample_size]

    # Create summary of issue titles and labels for analysis
    issue_summaries = []
    for issue in sample_issues:
        title = issue.get('title', 'Untitled')

        labels = format_labels_for_display(issue.get('labels', [])) or 'No labels'

        issue_summaries.append(f"- {title} ({labels})")

    issues_text = '\n'.join(issue_summaries)

    prompt = f"""
Analyze this product backlog and provide a one-paragraph executive summary for a product executive briefing.

BACKLOG CONTEXT:
- Total backlog size: {len(backlog_issues)} strategic issues
- Sample of {len(sample_issues)} representative issues shown below
- These are issues NOT included in the main status report (not recently completed, not scheduled next week, not critical customer issues)

SAMPLE ISSUES:
{issues_text}

INSTRUCTIONS:
Write ONE comprehensive paragraph (4-6 sentences) that identifies the major themes and strategic initiatives in this product backlog. Focus on:

1. Key product areas and capabilities being developed
2. Major strategic themes or initiatives
3. Technical platform investments
4. Overall portfolio balance (features vs bugs vs infrastructure)

Use executive language suitable for C-level briefings. Don't list individual issues - instead synthesize the major patterns and strategic directions.

Format: One paragraph, plain text.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "You are a senior product strategist writing executive briefings on product roadmaps. Your audience is C-level executives who need to understand strategic direction, resource allocation, and competitive positioning."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=300,
            reasoning_effort="low"
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Backlog summary generation failed: {e}")
        return None

def analyze_group_with_ai(client, group_name, issues, category):
    """Analyze a group of related issues for executive context"""
    if not client or not issues:
        return None
    
    # Create summary of issues in the group
    issue_titles = [issue.get('title', '') for issue in issues[:5]]  # Limit for prompt size
    titles_text = '\n'.join([f"- {title}" for title in issue_titles])
    
    prompt = f"""
Analyze this group of {len(issues)} related issues for executive briefing:

Group: {group_name}
Category: {category}

Sample Issues:
{titles_text}

Provide 1-2 sentences explaining WHAT this group of work addresses - the actual problems being solved or capabilities being built.

Be terse and direct. Describe what is being fixed/built/changed, not why it's important.

Format: 1-2 complete sentences, plain text.
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "You are a strategic business analyst providing executive briefings on product development themes. Focus on business outcomes, competitive positioning, and strategic value."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=150,
            reasoning_effort="low"
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Group analysis failed for {group_name}: {e}")
        return None

def group_issues_intelligently(issues, client=None):
    """Group issues by business theme using AI analysis"""
    groups = defaultdict(list)
    
    for issue in issues:
        title = issue.get('title', '').lower()
        labels = normalize_labels(issue.get('labels', []))
        
        # Smart grouping based on business themes
        if any(x in title for x in MAJOR_CUSTOMER_NAMES):
            if 'salesforce' in title:
                groups['Salesforce Customer Issues'].append(issue)
            elif 'sprinklr' in title:
                groups['Sprinklr Customer Issues'].append(issue)
            elif 'daily' in title:
                groups['Daily Customer Platform Issues'].append(issue)
            else:
                groups['Other Customer Issues'].append(issue)
        elif any(x in title for x in ['fabric', 'calling api']):
            groups['Fabric Integration Platform'].append(issue)
        elif any(x in title for x in ['ai agent', 'swml']):
            groups['AI Agent Platform Evolution'].append(issue)
        elif any(x in title for x in ['access', 'security', 'compliance']):
            groups['Compliance & Security Initiatives'].append(issue)
        elif any(x in title for x in ['deploy', 'infrastructure', 'monitoring']):
            groups['Infrastructure & Operations'].append(issue)
        elif 'epic' in labels:
            groups['Strategic Initiatives'].append(issue)
        else:
            groups['Other'].append(issue)
    
    return groups

def generate_executive_summary(categories, total_issues):
    """Generate comprehensive executive summary with strategic insights"""
    customer_issues = categories.get('customer', {}).get('total', 0)
    feature_issues = categories.get('feature', {}).get('total', 0)
    platform_issues = categories.get('platform', {}).get('total', 0)
    product_issues = categories.get('product', {}).get('total', 0)
    bugs_issues = categories.get('bugs', {}).get('total', 0)
    
    active_work = sum(cat.get('active', 0) for cat in categories.values())
    planned_work = sum(cat.get('planned', 0) for cat in categories.values())
    started_work = sum(cat.get('started', 0) for cat in categories.values())
    
    # Calculate critical metrics
    customer_active = categories.get('customer', {}).get('active', 0)
    customer_planned = categories.get('customer', {}).get('planned', 0)
    
    return f"""**EXECUTIVE BRIEFING: PRODUCT DEVELOPMENT STATUS**

This comprehensive analysis covers **{total_issues:,} strategic initiatives** currently in development .

**RESOURCE ALLOCATION STATUS:**
- **{active_work} initiatives actively under development** (assigned engineers, work in progress)
- **{started_work} initiatives partially started** (some resources allocated)  
- **{planned_work} initiatives awaiting resource assignment** (business impact pending execution)

**BUSINESS IMPACT BREAKDOWN:**
- **{customer_issues} Customer-Critical Issues** ({customer_active} active, {customer_planned} unassigned) - Direct revenue and retention impact
- **{feature_issues} Strategic Product Initiatives** - Competitive differentiation and market expansion
- **{product_issues} Core Product Enhancements** - Platform capability advancement
- **{platform_issues} Infrastructure Investments** - Operational excellence and scalability
- **{bugs_issues} Quality & Reliability Issues** - Customer experience and platform stability

**EXECUTIVE ATTENTION REQUIRED:**
{"🚨 **CRITICAL**: " + str(customer_planned) + " customer issues lack engineering assignment - immediate revenue risk" if customer_planned > 0 else "✅ All customer-critical issues have assigned engineering resources"}"""





# is_recently_completed moved to utils_dates.py

# is_scheduled_next_week moved to utils_filtering.py

# is_critical_customer_issue moved to utils_filtering.py

def get_issue_type_priority(issue_dict: dict) -> int:
    """Get numeric priority for sorting issues by type (lower number = higher priority)."""
    labels_str = normalize_labels(issue_dict.get('labels', []))

    title = issue_dict.get('title', '').lower()

    # Priority order: Lower number = higher priority
    if 'epic' in labels_str:
        return 1  # Epic - Major strategic initiatives
    elif 'type/feature' in labels_str:
        return 2  # Feature - New functionality/capabilities
    elif any(pattern in labels_str for pattern in ['product/ai', 'product/voice', 'product/video', 'product/messaging']):
        return 2  # Product features
    elif 'type/bug' in labels_str or 'bug' in title:
        return 3  # Bug - Customer-affecting defects
    elif any(pattern in labels_str for pattern in ['type/chore', 'deploy/', 'maintenance']):
        return 4  # Chore - Maintenance, deployments, cleanup
    elif any(pattern in labels_str for pattern in ['dev/iac', 'infrastructure', 'platform']):
        return 5  # Infrastructure - Platform/infrastructure work
    elif any(pattern in labels_str for pattern in ['compliance', 'security', 'tech-backlog']):
        return 4  # Technical work
    else:
        return 6  # Other - Default fallback

def get_issue_type_emoji(issue_dict: dict) -> str:
    """Determine the emoji representing the issue type."""
    labels_str = normalize_labels(issue_dict.get('labels', []))

    title = issue_dict.get('title', '').lower()

    # Priority order: Features/Epics first, then Bugs, then operational work
    if 'epic' in labels_str:
        return "🚀"  # Epic - Major strategic initiatives
    elif 'type/feature' in labels_str:
        return "✨"  # Feature - New functionality/capabilities
    elif any(pattern in labels_str for pattern in ['product/ai', 'product/voice', 'product/video', 'product/messaging']):
        return "✨"  # Product features
    elif 'type/bug' in labels_str or 'bug' in title:
        return "🐛"  # Bug - Customer-affecting defects
    elif any(pattern in labels_str for pattern in ['type/chore', 'deploy/', 'maintenance']):
        return "🔧"  # Chore - Maintenance, deployments, cleanup
    elif any(pattern in labels_str for pattern in ['dev/iac', 'infrastructure', 'platform']):
        return "🏗️"  # Infrastructure - Platform/infrastructure work
    elif any(pattern in labels_str for pattern in ['compliance', 'security', 'tech-backlog']):
        return "🔧"  # Technical work
    else:
        return "📋"  # Other - Default fallback

# is_work_in_progress moved to utils_filtering.py

def parse_arguments():
    """Parse command line arguments."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate executive product status report with completed, scheduled, and critical issues")
    parser.add_argument('json_file', nargs='?', default='cycle_time_report/cycle_time_data.json',
                       help='JSON file with issues data (default: cycle_time_report/cycle_time_data.json)')
    return parser.parse_args()


def setup_environment():
    """Setup environment and AI service."""
    load_dotenv()
    ai_service = AIAnalysisService.create_from_api_key(cache_file=AI_SUMMARY_CACHE_FILE)

    if ai_service.is_available():
        print("🤖 OpenAI enabled for intelligent issue analysis")
    else:
        print("⚠️  OPENAI_API_KEY not set - using basic categorization only")

    return ai_service


def load_data(json_file):
    """Load issue data from JSON file."""
    json_data = None
    github_owner = None
    github_repo = None

    if os.path.exists(json_file):
        import json as json_module
        with open(json_file, 'r') as f:
            json_data = json_module.load(f)

        # Check if we have the new JSON structure with metadata
        if 'repository' in json_data and 'issues' in json_data:
            github_owner = json_data['repository'].get('github_owner')
            github_repo = json_data['repository'].get('github_repo')
            # Convert issues list back to DataFrame
            df = pd.DataFrame(json_data['issues'])
        else:
            # Old JSON format - direct list of issues
            df = pd.DataFrame(json_data)
            print("⚠️  Using legacy JSON format - GitHub URLs will be hardcoded")
    elif os.path.exists('cycle_time_report/cycle_time_data.csv'):
        df = pd.read_csv('cycle_time_report/cycle_time_data.csv')
        print("⚠️  Using CSV data - GitHub URLs will need to be inferred or hardcoded")
    else:
        raise FileNotFoundError(f"❌ Error: {json_file} not found. Run 'uv run cycle_time.py <json_file>' first to generate data")

    return df, github_owner, github_repo


def process_issues(df):
    """Process and categorize issues into qualifying categories."""
    print(f"📋 Processing {len(df)} total issues...")
    qualifying_issues = []
    all_strategic_issues = []  # Track all strategic issues for backlog summary
    completed_count = 0
    scheduled_count = 0
    critical_count = 0
    strategic_count = 0

    for i, (_, row) in enumerate(df.iterrows()):
        # Update status bar every 100 issues
        if i % 100 == 0:
            display_status_bar(i, len(df), "Processing issues for strategic work filtering")

        issue_dict = row.to_dict()

        # Apply strategic work filtering first
        if not is_strategic_work(issue_dict):
            continue

        strategic_count += 1
        all_strategic_issues.append(issue_dict)  # Collect all strategic issues

        # Check if issue qualifies for any of the three categories
        is_completed = is_recently_completed(issue_dict)
        is_scheduled = is_scheduled_next_week(issue_dict)
        is_critical = is_critical_customer_issue(issue_dict)

        if is_completed or is_scheduled or is_critical:
            issue_dict['qualification_reason'] = []
            if is_completed:
                issue_dict['qualification_reason'].append('recently_completed')
                completed_count += 1
            if is_scheduled:
                issue_dict['qualification_reason'].append('scheduled_next_week')
                scheduled_count += 1
            if is_critical:
                issue_dict['qualification_reason'].append('critical_customer')
                critical_count += 1
            qualifying_issues.append(issue_dict)

    # Final status bar update for processing
    display_status_bar(len(df), len(df), "Issue processing complete")

    print(f"🎯 Filtering complete:")
    print(f"   • {strategic_count} strategic issues (out of {len(df)} total)")
    print(f"   • {len(qualifying_issues)} qualifying issues found")

    if not qualifying_issues:
        raise ValueError("❌ No issues found matching criteria (completed, scheduled, or critical)")

    print(f"📊 Breakdown of {len(qualifying_issues)} qualifying issues:")
    print(f"   • {completed_count} recently completed (last 7 days)")
    print(f"   • {scheduled_count} scheduled for next week")
    print(f"   • {critical_count} critical customer issues")

    return {
        'qualifying_issues': qualifying_issues,
        'all_strategic_issues': all_strategic_issues,
        'counts': {
            'completed': completed_count,
            'scheduled': scheduled_count,
            'critical': critical_count,
            'strategic': strategic_count
        }
    }


def generate_ai_summaries(ai_service, qualifying_issues):
    """Generate AI summaries for qualifying issues with caching."""
    if not ai_service.is_available():
        print("\n⚠️  OpenAI API key not set - skipping AI summaries")
        for issue in qualifying_issues:
            issue['ai_summary'] = None
        return None

    print(f"\n🤖 Generating AI summaries for {len(qualifying_issues)} issues...")

    # Process issues with the AI service
    cached_count, generated_count = ai_service.process_issues_batch(qualifying_issues, show_progress=True)

    # Generate backlog summary of remaining issues
    print(f"\n🎯 Generating product backlog summary...")
    return ai_service.generate_backlog_summary(qualifying_issues, qualifying_issues)


def generate_executive_summary(client, issues, time_period="this period"):
    """Generate executive summary grouped by topic areas"""
    if not client or not issues:
        return f"No issues to summarize for {time_period}."

    try:
        # Prepare issue data for AI analysis
        issues_text = []
        for issue in issues:
            labels = issue.get('labels', [])
            if isinstance(labels, list) and labels and isinstance(labels[0], dict):
                labels_str = ', '.join([label['name'] for label in labels])
            else:
                labels_str = str(labels) if labels else ''

            issues_text.append(f"#{issue.get('number', 'N/A')}: {issue.get('title', 'Untitled')} (Labels: {labels_str})")

        prompt = f"""You are analyzing GitHub issues for an executive product status report. Create a factual, analytical summary grouped by major topic areas (e.g., Voice & Calling Infrastructure, WhatsApp Integration, Platform APIs, etc.).

For each topic area, provide:
1. A clear topic heading (###)
2. 2-3 sentences stating what was accomplished and its business impact
3. Use objective language - describe capabilities, fixes, and improvements without promotional language
4. Avoid time references ("this week", "we did") - focus on what was accomplished
5. Focus on customer impact, system reliability, and operational capabilities

Issues to analyze:
{chr(10).join(issues_text)}

Format as markdown with ### headings for each topic area. Be factual and analytical, not promotional. Describe the work and its business impact objectively. If there are only 1-2 issues, create a single paragraph summary instead of topic sections."""

        response = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": prompt}]
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Unable to generate executive summary for {time_period}: {str(e)}"


def generate_reports(qualifying_issues, all_strategic_issues, counts, client, github_owner, github_repo):
    """Generate both main and customer reports."""
    # Categorize issues by type
    completed_issues = [i for i in qualifying_issues if 'recently_completed' in i['qualification_reason']]
    scheduled_issues = [i for i in qualifying_issues if 'scheduled_next_week' in i['qualification_reason']]
    critical_issues = [i for i in qualifying_issues if 'critical_customer' in i['qualification_reason']]

    # Generate AI summaries first
    backlog_summary = generate_ai_summaries(client, qualifying_issues)

    # Generate the main report content
    current_date = datetime.now().strftime("%Y-%m-%d")
    repo_display = f"{github_owner}/{github_repo}" if github_owner and github_repo else "Repository"

    report_lines = []
    report_lines.append("# Executive Product Status Report")
    report_lines.append("")
    report_lines.append(f"**Repository:** {repo_display}   ")
    report_lines.append(f"**Report Date:** {current_date}   ")
    report_lines.append(f"**Strategic Issues Analyzed:** {counts['strategic']}")
    report_lines.append("")

    report_lines.append("**Scope:** Recently Completed, Scheduled Next Week, and Critical Customer Issues")
    report_lines.append("")
    report_lines.append("## 📊 **EXECUTIVE SUMMARY**")
    report_lines.append("")
    report_lines.append(f"- **{counts['completed']} issues** completed in the last 7 days")
    report_lines.append(f"- **{counts['scheduled']} issues** scheduled for next week")
    report_lines.append(f"- **{counts['critical']} critical customer issues** requiring attention (see `customer_issues.md`)")
    report_lines.append("")

    # Generate and add executive summaries for completed and planned work
    if completed_issues and client:
        print("🎯 Generating executive summary for completed work...")
        completed_summary = generate_executive_summary(client, completed_issues, "last week")
        report_lines.append("## 🏆 **LAST WEEK'S ACHIEVEMENTS**")
        report_lines.append("")
        report_lines.append(completed_summary)
        report_lines.append("")

    if scheduled_issues and client:
        print("🎯 Generating executive summary for planned work...")
        planned_summary = generate_executive_summary(client, scheduled_issues, "this week")
        report_lines.append("## 🎯 **THIS WEEK'S PLANNED WORK**")
        report_lines.append("")
        report_lines.append(planned_summary)
        report_lines.append("")

    footnotes = []

    # Helper functions for report building
    def add_issue_section_with_topics(title, emoji, issues, topic_groups, status_description=""):
        """Add a section grouped by topic areas"""
        if not issues or not topic_groups:
            return

        report_lines.append(f"## {emoji} **{title}**")
        if status_description:
            report_lines.append(f"*{status_description}*")
        report_lines.append("")

        # Create issue lookup
        issue_lookup = {issue.get('number', issue.get('issue_number')): issue for issue in issues}

        # Group issues that weren't categorized
        categorized_numbers = set()
        for group in topic_groups:
            categorized_numbers.update(group.get('issue_numbers', []))

        for group in topic_groups:
            topic_name = group.get('topic_name', 'Unknown Topic')
            description = group.get('description', '')
            summary = group.get('summary', '')
            issue_numbers = group.get('issue_numbers', [])

            if not issue_numbers:
                continue

            report_lines.append(f"### 🎯 **{topic_name}**")
            if description:
                report_lines.append(f"*{description}*")
            report_lines.append("")

            if summary:
                report_lines.append(f"**Summary:** {summary}")
                report_lines.append("")

            # Get issues for this topic and sort by type priority
            topic_issues = [issue_lookup[num] for num in issue_numbers if num in issue_lookup]
            sorted_topic_issues = sorted(topic_issues, key=get_issue_type_priority)

            # List all issues in this topic with footnotes
            footnote_refs = []
            for issue in sorted_topic_issues:
                issue_num = issue.get('number', issue.get('issue_number'))
                title = issue.get('title', 'Untitled')
                footnote_refs.append(f"[^{issue_num}]")

                # Add footnote
                issue_url = generate_issue_url(issue, github_owner, github_repo)

                footnotes.append(f"[^{issue_num}]: {issue_url} - {title}")

            if footnote_refs:
                report_lines.append(f"**Issues:** {', '.join(footnote_refs)}")
            report_lines.append("")

        # Add any uncategorized issues
        uncategorized = [issue for issue in issues
                        if issue.get('number', issue.get('issue_number')) not in categorized_numbers]

        if uncategorized:
            report_lines.append("### 📋 **Other Items**")
            report_lines.append("")

            # Sort uncategorized issues by type priority
            sorted_uncategorized = sorted(uncategorized, key=get_issue_type_priority)

            footnote_refs = []
            for issue in sorted_uncategorized:
                issue_num = issue.get('number', issue.get('issue_number'))
                title = issue.get('title', 'Untitled')
                footnote_refs.append(f"[^{issue_num}]")

                # Add footnote
                issue_url = generate_issue_url(issue, github_owner, github_repo)

                footnotes.append(f"[^{issue_num}]: {issue_url} - {title}")

            if footnote_refs:
                report_lines.append(f"**Issues:** {', '.join(footnote_refs)}")
            report_lines.append("")

    def add_issue_section(title, emoji, issues, status_description=""):
        """Helper to add a section for a specific type of issue"""
        if not issues:
            return

        # Sort issues by type priority (epics and features first, then bugs)
        sorted_issues = sorted(issues, key=get_issue_type_priority)

        report_lines.append(f"## {emoji} **{title}**")
        if status_description:
            report_lines.append(f"*{status_description}*")
        report_lines.append("")
        for issue in sorted_issues:
            issue_num = issue.get('number', issue.get('issue_number'))
            title = issue.get('title', 'Untitled')
            # Issue type indicator
            type_emoji = get_issue_type_emoji(issue)

            report_lines.append(f"{type_emoji} **{title}**[^{issue_num}]")
            report_lines.append("")

            # Add AI summary if available
            if issue.get('ai_summary'):
                report_lines.append(f"   {issue['ai_summary']}")
            else:
                # Fallback description
                raw_labels = issue.get('labels', [])
                labels_display = format_labels_for_display(raw_labels) or 'No labels'
                report_lines.append(f"   *Labels: {labels_display}*")

            report_lines.append("")

            # Add footnote
            issue_url = generate_issue_url(issue, github_owner, github_repo)

            footnotes.append(f"[^{issue_num}]: {issue_url} - {title}")

    # Add detailed sections header
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## 📋 **DETAILED ISSUE BREAKDOWN**")
    report_lines.append("")

    # Add the main sections (excluding customer issues)
    add_issue_section("RECENTLY COMPLETED", "✅", completed_issues,
                     "Issues that were completed in the last 7 days")

    # Handle scheduled issues with topic grouping
    if scheduled_issues:
        topic_groups = group_issues_by_topic_areas(client, scheduled_issues) if client else None

        if topic_groups:
            add_issue_section_with_topics("SCHEDULED FOR NEXT WEEK", "📅", scheduled_issues, topic_groups,
                                        "Issues with milestones or labels indicating next week delivery")
        else:
            add_issue_section("SCHEDULED FOR NEXT WEEK", "📅", scheduled_issues,
                             "Issues with milestones or labels indicating next week delivery")

    # Add product backlog summary
    if backlog_summary:
        remaining_count = len(all_strategic_issues) - len(qualifying_issues)
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("## 📚 **PRODUCT BACKLOG OVERVIEW**")
        report_lines.append("")
        report_lines.append(f"*Analysis of {remaining_count} strategic issues not included in the above categories*")
        report_lines.append("")
        report_lines.append(backlog_summary)
        report_lines.append("")

    # Add footnotes
    if footnotes:
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("## Footnotes")
        report_lines.append("")
        for footnote in footnotes:
            report_lines.append(footnote)

    # Generate customer report
    customer_report_lines = []
    customer_footnotes = []

    if critical_issues:
        customer_report_lines.append("# Critical Customer Issues Report")
        customer_report_lines.append("")
        customer_report_lines.append(f"**Repository:** {repo_display}   ")
        customer_report_lines.append(f"**Report Date:** {current_date}   ")
        customer_report_lines.append(f"**Total Critical Customer Issues:** {len(critical_issues)}")
        customer_report_lines.append("")
        customer_report_lines.append("---")
        customer_report_lines.append("")
        customer_report_lines.append("## 🚨 **CRITICAL CUSTOMER ISSUES**")
        customer_report_lines.append("*High-priority customer-impacting issues requiring immediate attention*")
        customer_report_lines.append("")

        # Sort critical issues by type priority
        sorted_critical_issues = sorted(critical_issues, key=get_issue_type_priority)

        for issue in sorted_critical_issues:
            issue_num = issue.get('number', issue.get('issue_number'))
            title = issue.get('title', 'Untitled')
            # Issue type indicator
            type_emoji = get_issue_type_emoji(issue)

            customer_report_lines.append(f"{type_emoji} **{title}**[^{issue_num}]")
            customer_report_lines.append("")

            # Add AI summary if available
            if issue.get('ai_summary'):
                customer_report_lines.append(f"   {issue['ai_summary']}")
            else:
                # Fallback description
                raw_labels = issue.get('labels', [])
                labels_display = format_labels_for_display(raw_labels) or 'No labels'
                customer_report_lines.append(f"   *Labels: {labels_display}*")

            customer_report_lines.append("")

            # Add footnote
            issue_url = generate_issue_url(issue, github_owner, github_repo)

            customer_footnotes.append(f"[^{issue_num}]: {issue_url} - {title}")

        # Add customer footnotes
        if customer_footnotes:
            customer_report_lines.append("---")
            customer_report_lines.append("")
            customer_report_lines.append("## Footnotes")
            customer_report_lines.append("")
            customer_report_lines.extend(customer_footnotes)

    return {
        'main_report': '\n'.join(report_lines),
        'customer_report': '\n'.join(customer_report_lines) if critical_issues else None,
        'counts': counts,
        'footnotes_count': len(footnotes),
        'critical_issues_count': len(critical_issues)
    }


def generate_reports_with_services(qualifying_issues, all_strategic_issues, counts, ai_service, github_owner, github_repo):
    """Generate both main and customer reports using new service modules."""
    # Generate AI summaries first to include them in reports
    backlog_summary = generate_ai_summaries(ai_service, qualifying_issues)

    # Separate issues by category for detailed analysis
    completed_issues = [i for i in qualifying_issues if 'recently_completed' in i['qualification_reason']]
    scheduled_issues = [i for i in qualifying_issues if 'scheduled_next_week' in i['qualification_reason']]
    critical_issues = [i for i in all_strategic_issues if is_critical_customer_issue(i)]

    # Generate AI summaries for different periods
    completed_summary = None
    planned_summary = None
    topic_groups = None

    if ai_service.is_available():
        if completed_issues:
            print("🎯 Generating executive summary for completed work...")
            completed_summary = ai_service.generate_executive_summary(completed_issues, "last week")

        if scheduled_issues:
            print("🎯 Generating executive summary for planned work...")
            planned_summary = ai_service.generate_executive_summary(scheduled_issues, "this week")
            # Get topic groups for better organization
            topic_groups = ai_service.group_issues_by_topics(scheduled_issues)

    # Create report generator
    report_generator = ReportGenerator(github_owner, github_repo)

    # Generate reports
    return report_generator.generate_main_report(
        qualifying_issues=qualifying_issues,
        all_strategic_issues=all_strategic_issues,
        counts=counts,
        backlog_summary=backlog_summary,
        completed_summary=completed_summary,
        planned_summary=planned_summary,
        topic_groups=topic_groups
    )


def main():
    args = parse_arguments()
    ai_service = setup_environment()

    # Load issue data
    try:
        df, github_owner, github_repo = load_data(args.json_file)
    except FileNotFoundError as e:
        print(e)
        return

    # Process and categorize issues
    try:
        results = process_issues(df)
        qualifying_issues = results['qualifying_issues']
        all_strategic_issues = results['all_strategic_issues']
        counts = results['counts']
    except ValueError as e:
        print(e)
        return

    # Generate reports using new services
    reports = generate_reports_with_services(qualifying_issues, all_strategic_issues, counts, ai_service, github_owner, github_repo)

    # Write reports to files
    os.makedirs('reports', exist_ok=True)

    with open('reports/product_management_status.md', 'w') as f:
        f.write(reports['main_report'])

    if reports['customer_report']:
        with open('reports/customer_issues.md', 'w') as f:
            f.write(reports['customer_report'])
        print(f"\n✅ Customer issues report written to reports/customer_issues.md")
        print(f"🚨 Included {reports['critical_issues_count']} critical customer issues")

    print(f"\n✅ Executive report written to reports/product_management_status.md")
    print(f"📝 Included {reports['footnotes_count']} issue references with footnotes")
    if client:
        print("🤖 AI-powered analysis included for business impact assessment")


if __name__ == "__main__":
    main()
