#!/usr/bin/env python3
"""
Report Generation Module for GitHub Issues Analysis
Handles formatting and generating markdown reports
Separated from product_status_report.py for better modularity
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict

from utils import generate_issue_url, get_issue_number, format_labels_for_display
from utils_filtering import is_scheduled_next_week, is_critical_customer_issue
from utils_dates import is_recently_completed


class ReportGenerator:
    """Generates markdown reports for GitHub issue analysis"""

    def __init__(self, github_owner: Optional[str] = None, github_repo: Optional[str] = None):
        self.github_owner = github_owner
        self.github_repo = github_repo
        self.footnotes: List[str] = []

    def _get_type_emoji(self, issue: Dict[str, Any]) -> str:
        """Get emoji based on issue type"""
        labels = format_labels_for_display(issue.get('labels', []), ' ').lower()
        title = issue.get('title', '').lower()

        if 'epic' in labels:
            return "🎯"
        elif 'type/feature' in labels:
            return "✨"
        elif any(pattern in labels for pattern in ['product/ai', 'product/voice', 'product/video', 'product/messaging']):
            return "🚀"
        elif 'type/bug' in labels or 'bug' in title:
            return "🐛"
        elif any(pattern in labels for pattern in ['type/chore', 'deploy/', 'maintenance']):
            return "🔧"
        elif any(pattern in labels for pattern in ['dev/iac', 'infrastructure', 'platform']):
            return "🏗️"
        elif any(pattern in labels for pattern in ['compliance', 'security', 'tech-backlog']):
            return "🔒"
        else:
            return "📋"

    def _add_footnote(self, issue: Dict[str, Any]) -> str:
        """Add footnote for issue and return reference"""
        issue_num = get_issue_number(issue)
        title = issue.get('title', 'Untitled')
        issue_url = generate_issue_url(issue, self.github_owner, self.github_repo)

        footnote = f"[^{issue_num}]: {issue_url} - {title}"
        self.footnotes.append(footnote)

        return f"[^{issue_num}]"

    def generate_header(self, counts: Dict[str, int]) -> List[str]:
        """Generate report header with metadata"""
        current_date = datetime.now().strftime("%B %d, %Y")
        repo_display = f"{self.github_owner}/{self.github_repo}" if self.github_owner and self.github_repo else "Repository"

        lines = [
            "# Executive Product Status Report",
            "",
            f"**Repository:** {repo_display}   ",
            f"**Report Date:** {current_date}   ",
            f"**Strategic Issues Analyzed:** {counts['strategic']}",
            "",
            "**Scope:** Recently Completed, Scheduled Next Week, and Critical Customer Issues",
            ""
        ]

        return lines

    def generate_executive_summary(self, counts: Dict[str, int]) -> List[str]:
        """Generate executive summary section"""
        lines = [
            "## 📊 **EXECUTIVE SUMMARY**",
            "",
            f"- **{counts['completed']} issues** completed in the last 7 days",
            f"- **{counts['scheduled']} issues** scheduled for next week",
            f"- **{counts['critical']} critical customer issues** requiring attention (see `customer_issues.md`)",
            ""
        ]

        return lines

    def add_ai_summary_section(self, title: str, summary: str) -> List[str]:
        """Add AI-generated summary section"""
        return [
            f"## {title}",
            "",
            summary,
            ""
        ]

    def add_issue_section(self, title: str, emoji: str, issues: List[Dict[str, Any]], status_description: str = "") -> List[str]:
        """Add standard issue section to report"""
        if not issues:
            return []

        lines = []
        lines.append(f"## {emoji} **{title}**")

        if status_description:
            lines.append(f"*{status_description}*")
        lines.append("")

        # Sort issues by type priority for better organization
        from product_status_report import get_issue_type_priority  # Import here to avoid circular dependency
        sorted_issues = sorted(issues, key=get_issue_type_priority)

        for issue in sorted_issues:
            issue_num = get_issue_number(issue)
            title = issue.get('title', 'Untitled')
            type_emoji = self._get_type_emoji(issue)

            footnote_ref = self._add_footnote(issue)
            lines.append(f"{type_emoji} **{title}**{footnote_ref}")
            lines.append("")

            # Add AI summary if available
            if issue.get('ai_summary'):
                lines.append(f"   {issue['ai_summary']}")

            # Add labels if no AI summary
            if not issue.get('ai_summary'):
                raw_labels = issue.get('labels', [])
                labels_display = format_labels_for_display(raw_labels) or 'No labels'
                lines.append(f"   *Labels: {labels_display}*")

            lines.append("")

        return lines

    def add_topic_grouped_section(self, title: str, emoji: str, issues: List[Dict[str, Any]],
                                 topic_groups: Optional[List[Dict[str, Any]]], status_description: str = "") -> List[str]:
        """Add topic-grouped issue section"""
        if not issues:
            return []

        lines = []
        lines.append(f"## {emoji} **{title}**")

        if status_description:
            lines.append(f"*{status_description}*")
        lines.append("")

        if not topic_groups:
            # Fallback to regular issue section if no topic groups
            return self.add_issue_section(title, emoji, issues, status_description)

        # Track which issues have been categorized
        categorized_numbers = set()

        # Process each topic group
        for topic in topic_groups:
            topic_name = topic.get('name', 'Unknown Topic')
            topic_issue_numbers = topic.get('issues', [])
            description = topic.get('description', '')
            summary = topic.get('summary', '')

            # Find issues that match this topic
            topic_issues = [issue for issue in issues
                          if get_issue_number(issue) in topic_issue_numbers]

            if topic_issues:
                lines.append(f"### 🎯 **{topic_name}**")
                if description:
                    lines.append(f"*{description}*")
                lines.append("")

                if summary:
                    lines.append(f"**Summary:** {summary}")
                    lines.append("")

                # Sort issues within topic by type priority
                from product_status_report import get_issue_type_priority  # Import here to avoid circular dependency
                sorted_topic_issues = sorted(topic_issues, key=get_issue_type_priority)

                # List all issues in this topic with footnotes
                footnote_refs = []
                for issue in sorted_topic_issues:
                    issue_num = get_issue_number(issue)
                    categorized_numbers.add(issue_num)
                    footnote_refs.append(self._add_footnote(issue))

                if footnote_refs:
                    lines.append(f"**Issues:** {', '.join(footnote_refs)}")
                lines.append("")

        # Add any uncategorized issues
        uncategorized = [issue for issue in issues
                        if get_issue_number(issue) not in categorized_numbers]

        if uncategorized:
            lines.append("### 📋 **Other Items**")
            lines.append("")

            # Sort uncategorized issues by type priority
            from product_status_report import get_issue_type_priority  # Import here to avoid circular dependency
            sorted_uncategorized = sorted(uncategorized, key=get_issue_type_priority)

            footnote_refs = []
            for issue in sorted_uncategorized:
                footnote_refs.append(self._add_footnote(issue))

            if footnote_refs:
                lines.append(f"**Issues:** {', '.join(footnote_refs)}")
            lines.append("")

        return lines

    def add_detailed_breakdown_section(self, issues: List[Dict[str, Any]]) -> List[str]:
        """Add detailed issue breakdown section"""
        lines = [
            "---",
            "",
            "## 📋 **DETAILED ISSUE BREAKDOWN**",
            ""
        ]

        return lines

    def add_backlog_overview(self, backlog_summary: str, remaining_count: int) -> List[str]:
        """Add product backlog overview section"""
        if not backlog_summary:
            return []

        lines = [
            "---",
            "",
            "## 📚 **PRODUCT BACKLOG OVERVIEW**",
            "",
            f"*Analysis of {remaining_count} strategic issues not included in the above categories*",
            "",
            backlog_summary,
            ""
        ]

        return lines

    def add_footnotes_section(self) -> List[str]:
        """Add footnotes section"""
        if not self.footnotes:
            return []

        lines = [
            "---",
            "",
            "## Footnotes",
            ""
        ]

        for footnote in self.footnotes:
            lines.append(footnote)

        return lines

    def generate_customer_report(self, critical_issues: List[Dict[str, Any]]) -> Optional[str]:
        """Generate customer issues report"""
        if not critical_issues:
            return None

        current_date = datetime.now().strftime("%B %d, %Y")
        repo_display = f"{self.github_owner}/{self.github_repo}" if self.github_owner and self.github_repo else "Repository"

        customer_footnotes = []
        lines = [
            "# Critical Customer Issues Report",
            "",
            f"**Repository:** {repo_display}   ",
            f"**Report Date:** {current_date}   ",
            f"**Total Critical Customer Issues:** {len(critical_issues)}",
            "",
            "---",
            "",
            "## 🚨 **CRITICAL CUSTOMER ISSUES**",
            "*High-priority customer-impacting issues requiring immediate attention*",
            ""
        ]

        # Sort critical issues by type priority
        from product_status_report import get_issue_type_priority  # Import here to avoid circular dependency
        sorted_issues = sorted(critical_issues, key=get_issue_type_priority)

        for issue in sorted_issues:
            issue_num = get_issue_number(issue)
            title = issue.get('title', 'Untitled')
            type_emoji = self._get_type_emoji(issue)

            lines.append(f"{type_emoji} **{title}**[^{issue_num}]")
            lines.append("")

            # Add AI summary if available
            if issue.get('ai_summary'):
                lines.append(f"   {issue['ai_summary']}")

            # Add labels if no AI summary
            if not issue.get('ai_summary'):
                raw_labels = issue.get('labels', [])
                labels_display = format_labels_for_display(raw_labels) or 'No labels'
                lines.append(f"   *Labels: {labels_display}*")

            lines.append("")

            # Add footnote for customer report
            issue_url = generate_issue_url(issue, self.github_owner, self.github_repo)
            customer_footnotes.append(f"[^{issue_num}]: {issue_url} - {title}")

        # Add customer footnotes
        if customer_footnotes:
            lines.extend([
                "---",
                "",
                "## Footnotes",
                ""
            ])
            lines.extend(customer_footnotes)

        return '\n'.join(lines)

    def generate_main_report(self, qualifying_issues: List[Dict[str, Any]],
                           all_strategic_issues: List[Dict[str, Any]],
                           counts: Dict[str, int],
                           backlog_summary: Optional[str] = None,
                           completed_summary: Optional[str] = None,
                           planned_summary: Optional[str] = None,
                           topic_groups: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Generate main executive report"""

        # Reset footnotes for new report
        self.footnotes = []

        # Separate issues by category
        completed_issues = [issue for issue in qualifying_issues if is_recently_completed(issue)]
        scheduled_issues = [issue for issue in qualifying_issues if is_scheduled_next_week(issue)]
        critical_issues = [issue for issue in all_strategic_issues if is_critical_customer_issue(issue)]

        # Build main report
        report_lines = []

        # Add header
        report_lines.extend(self.generate_header(counts))

        # Add executive summary
        report_lines.extend(self.generate_executive_summary(counts))

        # Add AI summaries if available
        if completed_summary:
            report_lines.extend(self.add_ai_summary_section("## 🏆 **LAST WEEK'S ACHIEVEMENTS**", completed_summary))

        if planned_summary:
            report_lines.extend(self.add_ai_summary_section("## 🎯 **THIS WEEK'S PLANNED WORK**", planned_summary))

        # Add detailed sections
        if completed_issues:
            report_lines.extend(self.add_issue_section(
                "COMPLETED LAST WEEK", "✅", completed_issues,
                "Issues completed in the last 7 days"
            ))

        if scheduled_issues:
            # Use topic grouping for scheduled issues if available
            if topic_groups:
                report_lines.extend(self.add_topic_grouped_section(
                    "SCHEDULED NEXT WEEK", "📅", scheduled_issues, topic_groups,
                    "Issues planned for the upcoming week, grouped by business area"
                ))
            else:
                report_lines.extend(self.add_issue_section(
                    "SCHEDULED NEXT WEEK", "📅", scheduled_issues,
                    "Issues planned for the upcoming week"
                ))

        # Add detailed breakdown section
        report_lines.extend(self.add_detailed_breakdown_section(qualifying_issues))

        # Add backlog overview
        if backlog_summary:
            remaining_count = len(all_strategic_issues) - len(qualifying_issues)
            report_lines.extend(self.add_backlog_overview(backlog_summary, remaining_count))

        # Add footnotes
        report_lines.extend(self.add_footnotes_section())

        # Generate customer report
        customer_report = self.generate_customer_report(critical_issues)

        return {
            'main_report': '\n'.join(report_lines),
            'customer_report': customer_report,
            'counts': counts,
            'footnotes_count': len(self.footnotes),
            'critical_issues_count': len(critical_issues)
        }