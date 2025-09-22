#!/usr/bin/env python3
"""
AI Analysis Service for GitHub Issues
Handles OpenAI integration, caching, and issue analysis
Separated from product_status_report.py for better modularity
"""

import os
import json
import hashlib
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from openai import OpenAI

from config import (
    AI_ANALYSIS_TEMPERATURE,
    AI_SUMMARY_CACHE_FILE,
    get_openai_model
)
from utils import format_labels_for_display, get_issue_number


class AISummaryCache:
    """Cache for AI-generated issue summaries based on content hash"""

    def __init__(self, cache_file: str = AI_SUMMARY_CACHE_FILE):
        self.cache_file = cache_file
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict:
        """Load cache from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️  Cache load error: {e}")
        return {}

    def _save_cache(self) -> None:
        """Save cache to file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except IOError as e:
            print(f"⚠️  Cache save error: {e}")

    def _get_content_hash(self, issue: Dict[str, Any]) -> str:
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

    def get_summary(self, issue: Dict[str, Any]) -> Optional[str]:
        """Get cached summary for issue if content hasn't changed"""
        issue_number = str(get_issue_number(issue) or 'unknown')
        content_hash = self._get_content_hash(issue)

        if issue_number in self.cache:
            cached_entry = self.cache[issue_number]
            if cached_entry.get('content_hash') == content_hash:
                return cached_entry.get('summary')

        return None

    def set_summary(self, issue: Dict[str, Any], summary: str) -> None:
        """Cache summary for issue with content hash"""
        issue_number = str(get_issue_number(issue) or 'unknown')
        content_hash = self._get_content_hash(issue)

        self.cache[issue_number] = {
            'summary': summary,
            'content_hash': content_hash,
            'generated_at': datetime.now().isoformat()
        }

        self._save_cache()


class AIAnalysisService:
    """Service for AI-powered issue analysis using OpenAI"""

    def __init__(self, client: Optional[OpenAI] = None, cache_file: Optional[str] = None):
        self.client = client
        self.cache = AISummaryCache(cache_file) if cache_file else None

    @classmethod
    def create_from_api_key(cls, api_key: Optional[str] = None, cache_file: Optional[str] = None) -> 'AIAnalysisService':
        """Create service instance from API key (or environment variable)"""
        if not api_key:
            api_key = os.getenv('OPENAI_API_KEY')

        client = OpenAI(api_key=api_key) if api_key else None
        return cls(client, cache_file)

    def is_available(self) -> bool:
        """Check if AI service is available (has valid client)"""
        return self.client is not None

    def analyze_issue(self, issue: Dict[str, Any], category: str = 'executive') -> Optional[str]:
        """Use OpenAI to analyze issue and generate detailed executive summary"""
        if not self.client:
            return None

        # Check cache first
        if self.cache:
            cached_summary = self.cache.get_summary(issue)
            if cached_summary:
                return cached_summary

        title = issue.get('title', '')
        labels = format_labels_for_display(issue.get('labels', []), ' ')

        assignee = issue.get('assignee', 'Unassigned')
        state = issue.get('state', 'unknown')

        # Get truncated issue body
        body = issue.get('body', '')
        if body and len(body) > 800:
            body = body[:800] + "..."

        # Get recent comments if available
        recent_comments = ""
        comment_list = issue.get('comment_list', [])
        if comment_list:
            # Get last 2 comments
            for comment in comment_list[-2:]:
                if isinstance(comment, dict) and comment.get('body'):
                    recent_comments += f"\nRecent comment: {comment['body'][:200]}..."

        # Create prompts based on category
        if category == 'executive':
            prompt = f"""You are analyzing a GitHub issue for an executive product status report.

Issue: {title}
Labels: {labels}
Assignee: {assignee}
State: {state}
Description: {body}
{recent_comments}

Write a terse 1-2 sentence summary. Be direct and factual. Do NOT start with "This issue" or similar phrases.
Focus on what work is being done and business impact, not technical implementation details."""

        try:
            response = self.client.chat.completions.create(
                model=get_openai_model('short'),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=AI_ANALYSIS_TEMPERATURE
            )

            summary = response.choices[0].message.content.strip()

            # Cache the new summary
            if self.cache:
                self.cache.set_summary(issue, summary)

            return summary

        except Exception as e:
            issue_num = get_issue_number(issue)
            print(f"⚠️  AI analysis failed for issue {issue_num}: {e}")

            # Try a simpler fallback prompt
            fallback_prompt = f"""Issue: {title}
Labels: {labels}

Write a terse 1-2 sentence summary. Be direct and factual. Do NOT start with "This issue" or similar phrases.
Focus on what work is being done and business impact, not technical implementation details."""

            try:
                response = self.client.chat.completions.create(
                    model=get_openai_model('short'),
                    messages=[{"role": "user", "content": fallback_prompt}],
                    max_tokens=100,
                    temperature=AI_ANALYSIS_TEMPERATURE
                )

                summary = response.choices[0].message.content.strip()

                # Cache the fallback summary
                if self.cache:
                    self.cache.set_summary(issue, summary)

                print(f"Successfully generated fallback summary for issue {issue_num}")
                return summary

            except Exception as e2:
                print(f"⚠️  Fallback AI analysis also failed for issue {issue_num}: {e2}")
                return None

    def group_issues_by_topics(self, issues: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Group issues by major topic areas using AI analysis"""
        if not self.client or not issues:
            return None

        # Create issue summaries for grouping
        issue_info = []
        for issue in issues:
            issue_num = get_issue_number(issue)
            title = issue.get('title', 'Untitled')
            labels = format_labels_for_display(issue.get('labels', []))

            # Handle both GraphQL and REST label formats for backwards compatibility
            if isinstance(issue.get('labels'), list) and issue.get('labels') and isinstance(issue.get('labels')[0], dict):
                issue['labels'] = [label['name'] for label in issue.get('labels')]

            issue_info.append(f"#{issue_num}: {title} (Labels: {labels})")

        issues_text = "\n".join(issue_info)

        prompt = f"""Group these GitHub issues by major topic areas or themes. Return as JSON array with this structure:
[
  {{
    "name": "Topic Area Name",
    "issues": [1, 2, 3],
    "summary": "One sentence summary of the work in this area"
  }}
]

Issues:
{issues_text}

Focus on business themes like platform capabilities, integrations, user experience, etc. Create 3-5 groups maximum."""

        try:
            response = self.client.chat.completions.create(
                model=get_openai_model('long'),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.3
            )

            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"⚠️  Topic grouping failed: {e}")
            return None

    def generate_backlog_summary(self, all_issues: List[Dict[str, Any]], qualifying_issues: List[Dict[str, Any]]) -> Optional[str]:
        """Generate executive summary of product backlog themes"""
        if not self.client:
            return None

        print(f"🎯 Generating executive summary of {len(qualifying_issues)} qualifying issues from {len(all_issues)} total strategic issues...")

        # Limit to prevent overwhelming the model
        summary_issues = qualifying_issues[:30] if len(qualifying_issues) > 30 else qualifying_issues

        # Create summary of issue titles and labels for analysis
        issue_summaries = []
        for issue in summary_issues:
            title = issue.get('title', 'Untitled')
            labels = format_labels_for_display(issue.get('labels', []))
            issue_summaries.append(f"• {title} (Labels: {labels})")

        issues_text = "\n".join(issue_summaries)

        prompt = f"""Analyze this product backlog and provide a one-paragraph executive summary for a product executive briefing.

Issues ({len(summary_issues)} items):
{issues_text}

Focus on:
- What major themes or initiatives are represented
- What business capabilities are being built or improved
- Any customer-facing improvements or new features
- Technical improvements that enable business outcomes

Write 3-4 sentences maximum. Be factual and analytical, not promotional. Describe what work is planned and why it matters for the business."""

        try:
            response = self.client.chat.completions.create(
                model=get_openai_model('long'),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=AI_ANALYSIS_TEMPERATURE
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"Backlog summary generation failed: {e}")
            return None

    def analyze_group(self, group_name: str, issues: List[Dict[str, Any]], category: str = 'executive') -> Optional[str]:
        """Analyze a group of issues and generate a summary"""
        if not self.client or not issues:
            return None

        # Create summary of issues in the group
        issue_descriptions = []
        for issue in issues:
            title = issue.get('title', 'Untitled')
            labels = format_labels_for_display(issue.get('labels', []))
            issue_descriptions.append(f"• {title} (Labels: {labels})")

        issues_text = "\n".join(issue_descriptions)

        prompt = f"""Analyze these GitHub issues in the "{group_name}" area and provide a 1-2 sentence summary for an executive briefing.

Issues:
{issues_text}

Focus on what business capabilities or improvements are being delivered in this area. Be direct and factual."""

        try:
            response = self.client.chat.completions.create(
                model=get_openai_model('short'),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=AI_ANALYSIS_TEMPERATURE
            )

            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"⚠️  Group analysis failed for {group_name}: {e}")
            return None

    def generate_executive_summary(self, issues: List[Dict[str, Any]], time_period: str = "this period") -> str:
        """Generate executive summary grouped by topic areas"""
        if not self.client or not issues:
            return f"No AI analysis available for {time_period}."

        # Limit issues for analysis
        analysis_issues = issues[:20] if len(issues) > 20 else issues

        # Create issue summaries
        issue_summaries = []
        for issue in analysis_issues:
            title = issue.get('title', 'Untitled')
            labels = format_labels_for_display(issue.get('labels', []))
            issue_summaries.append(f"• {title} (Labels: {labels})")

        issues_text = "\n".join(issue_summaries)

        prompt = f"""You are analyzing GitHub issues for an executive product status report. Create a factual, analytical summary grouped by major topic areas (e.g., Voice & Calling Infrastructure, WhatsApp Integration, Platform APIs, etc.).

Issues for {time_period} ({len(analysis_issues)} items):
{issues_text}

Requirements:
- Group related issues by business capability or product area
- 1-2 sentences per topic area describing the work and business impact
- Focus on customer value and business outcomes, not technical implementation
- Be factual and direct, avoid promotional language

Format as markdown with ### headings for each topic area. Be factual and analytical, not promotional. Describe the work and its business impact objectively. If there are only 1-2 issues, create a single paragraph summary instead of topic sections."""

        try:
            response = self.client.chat.completions.create(
                model=get_openai_model('long'),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=AI_ANALYSIS_TEMPERATURE
            )

            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Unable to generate executive summary for {time_period}: {str(e)}"

    def process_issues_batch(self, issues: List[Dict[str, Any]], show_progress: bool = True) -> Tuple[int, int]:
        """
        Process multiple issues with AI analysis and caching.

        Returns:
            Tuple of (cached_count, generated_count)
        """
        if not self.client:
            if show_progress:
                print("\n⚠️  OpenAI API key not set - skipping AI summaries")
            for issue in issues:
                issue['ai_summary'] = None
            return 0, 0

        cached_count = 0
        generated_count = 0

        for i, issue in enumerate(issues):
            issue_num = get_issue_number(issue)

            if show_progress:
                # Calculate ETA based on processing rate
                if i > 0:
                    elapsed_time = time.time() - start_time if i == 1 else time.time() - start_time
                    rate = i / elapsed_time if elapsed_time > 0 else 0
                    remaining = len(issues) - i
                    eta_seconds = remaining / rate if rate > 0 else None
                else:
                    start_time = time.time()
                    eta_seconds = None

                # Display progress with status bar including cache miss percentage
                total_processed = cached_count + generated_count
                cache_miss_pct = (generated_count / total_processed * 100) if total_processed > 0 else 0
                # Display progress (simplified to avoid circular dependency)
                print(f"\r🤖 Processing issue #{issue_num} ({i+1}/{len(issues)}) - cache miss: {cache_miss_pct:.0f}%", end='', flush=True)

            # Check if we have a cached summary first
            if self.cache:
                cached_summary = self.cache.get_summary(issue)
                if cached_summary:
                    issue['ai_summary'] = cached_summary
                    cached_count += 1
                    continue

            # Generate new summary
            summary = self.analyze_issue(issue, 'executive')
            issue['ai_summary'] = summary
            if summary:
                generated_count += 1

        if show_progress:
            # Final status update
            total_processed = cached_count + generated_count
            cache_miss_pct = (generated_count / total_processed * 100) if total_processed > 0 else 0
            print(f"\n✅ AI summary generation complete (cache miss: {cache_miss_pct:.0f}%)")
            print(f"📋 Cache stats: {cached_count} cached, {generated_count} newly generated")

        return cached_count, generated_count