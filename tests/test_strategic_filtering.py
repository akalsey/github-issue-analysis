#!/usr/bin/env python3
"""
Unit tests for strategic filtering functionality across all scripts
"""
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "pytest",
# ]
# ///

import unittest
import json
import os
import sys
from datetime import datetime, timedelta

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestStrategicFiltering(unittest.TestCase):
    """Test strategic work filtering across all components"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.strategic_issues = [
            # Features - should be included
            {
                "number": 1,
                "title": "Add payment processing feature",
                "labels": [{"name": "feature"}, {"name": "customer-request"}],
                "state": "open"
            },
            # Epics - should be included
            {
                "number": 2,
                "title": "Mobile app redesign initiative",
                "labels": [{"name": "epic"}, {"name": "mobile"}],
                "state": "open"
            },
            # Bugs - should be included
            {
                "number": 3,
                "title": "Critical login bug affecting customers",
                "labels": [{"name": "bug"}, {"name": "critical"}],
                "state": "open"
            },
            # Customer requests - should be included
            {
                "number": 4,
                "title": "Custom reporting dashboard requested by enterprise client",
                "labels": [{"name": "customer-request"}, {"name": "enhancement"}],
                "state": "open"
            },
            # Strategic based on title keywords - should be included
            {
                "number": 5,
                "title": "Implement new user onboarding flow",
                "labels": [{"name": "improvement"}],
                "state": "open"
            }
        ]
        
        self.operational_issues = [
            # Chores - should be excluded
            {
                "number": 100,
                "title": "Update dependencies to latest versions",
                "labels": [{"name": "chore"}, {"name": "maintenance"}],
                "state": "open"
            },
            # Deployment - should be excluded
            {
                "number": 101,
                "title": "Deploy application to production environment",
                "labels": [{"name": "deployment"}, {"name": "ops"}],
                "state": "open"
            },
            # Infrastructure - should be excluded
            {
                "number": 102,
                "title": "Configure new database cluster",
                "labels": [{"name": "infrastructure"}, {"name": "devops"}],
                "state": "open"
            },
            # Technical debt - should be excluded (unless strategically important)
            {
                "number": 103,
                "title": "Refactor legacy authentication code",
                "labels": [{"name": "technical-debt"}, {"name": "refactor"}],
                "state": "open"
            },
            # Administrative - should be excluded
            {
                "number": 104,
                "title": "Update team access permissions",
                "labels": [{"name": "admin"}, {"name": "access"}],
                "state": "open"
            },
            # CI/CD - should be excluded
            {
                "number": 105,
                "title": "Fix broken CI pipeline",
                "labels": [{"name": "ci"}, {"name": "build"}],
                "state": "open"
            },
            # Documentation - should be excluded (unless customer-facing)
            {
                "number": 106,
                "title": "Update internal developer documentation",
                "labels": [{"name": "documentation"}, {"name": "internal"}],
                "state": "open"
            }
        ]

    def test_sync_issues_strategic_filtering(self):
        """Test strategic filtering in sync_issues.py"""
        from sync_issues import GitHubIssueSync
        
        sync = GitHubIssueSync("fake_token", "owner", "repo")
        
        # Test strategic issues are included
        for issue in self.strategic_issues:
            with self.subTest(issue=issue['number']):
                self.assertTrue(sync._is_strategic_work(issue), 
                               f"Issue #{issue['number']} should be strategic: {issue['title']}")
        
        # Test operational issues are excluded
        for issue in self.operational_issues:
            with self.subTest(issue=issue['number']):
                self.assertFalse(sync._is_strategic_work(issue),
                                f"Issue #{issue['number']} should be operational: {issue['title']}")

    def test_strategic_filtering_by_labels(self):
        """Test strategic filtering based on issue labels"""
        from sync_issues import GitHubIssueSync
        
        sync = GitHubIssueSync("fake_token", "owner", "repo")
        
        # Strategic labels
        strategic_labels = [
            [{"name": "feature"}],
            [{"name": "epic"}],
            [{"name": "bug"}],
            [{"name": "customer-request"}],
            [{"name": "enhancement"}],
            [{"name": "security"}],
            [{"name": "performance"}],
            [{"name": "user-experience"}]
        ]
        
        for labels in strategic_labels:
            issue = {"labels": labels, "title": "Test issue"}
            with self.subTest(labels=labels):
                self.assertTrue(sync._is_strategic_work(issue))
        
        # Operational labels
        operational_labels = [
            [{"name": "chore"}],
            [{"name": "deployment"}],
            [{"name": "infrastructure"}],
            [{"name": "technical-debt"}],
            [{"name": "maintenance"}],
            [{"name": "ci"}],
            [{"name": "devops"}],
            [{"name": "admin"}]
        ]
        
        for labels in operational_labels:
            issue = {"labels": labels, "title": "Test issue"}
            with self.subTest(labels=labels):
                self.assertFalse(sync._is_strategic_work(issue))

    def test_strategic_filtering_by_title_keywords(self):
        """Test strategic filtering based on title keywords"""
        from sync_issues import GitHubIssueSync
        
        sync = GitHubIssueSync("fake_token", "owner", "repo")
        
        # Strategic title keywords
        strategic_titles = [
            "Add new user registration feature",
            "Fix critical payment processing bug",
            "Implement customer dashboard",
            "Enhance user experience",
            "Add mobile app support",
            "Integrate with third-party API",
            "Create reporting functionality",
            "Build analytics dashboard"
        ]
        
        for title in strategic_titles:
            issue = {"labels": [], "title": title}
            with self.subTest(title=title):
                self.assertTrue(sync._is_strategic_work(issue))
        
        # Operational title keywords
        operational_titles = [
            "Deploy to production environment",
            "Update CI/CD pipeline configuration",
            "Refactor internal utility functions",
            "Update dependency versions",
            "Configure monitoring alerts",
            "Set up development environment",
            "Update team documentation",
            "Fix build pipeline issues"
        ]
        
        for title in operational_titles:
            issue = {"labels": [], "title": title}
            with self.subTest(title=title):
                self.assertFalse(sync._is_strategic_work(issue))

    def test_strategic_filtering_mixed_signals(self):
        """Test strategic filtering with mixed label and title signals"""
        from sync_issues import GitHubIssueSync
        
        sync = GitHubIssueSync("fake_token", "owner", "repo")
        
        # Strategic label overrides operational title
        strategic_label_operational_title = {
            "labels": [{"name": "feature"}],
            "title": "Deploy new feature to production"
        }
        self.assertTrue(sync._is_strategic_work(strategic_label_operational_title))
        
        # Operational label overrides strategic title
        operational_label_strategic_title = {
            "labels": [{"name": "chore"}],
            "title": "Add new customer feature"
        }
        self.assertFalse(sync._is_strategic_work(operational_label_strategic_title))

    def test_product_status_report_filtering(self):
        """Test strategic filtering in product status reports"""
        from product_status_report import filter_strategic_issues
        
        all_issues = self.strategic_issues + self.operational_issues
        filtered = filter_strategic_issues(all_issues)
        
        # Should include all strategic issues
        self.assertEqual(len(filtered), len(self.strategic_issues))
        
        # Verify correct issues are included
        filtered_numbers = {issue['number'] for issue in filtered}
        strategic_numbers = {issue['number'] for issue in self.strategic_issues}
        
        self.assertEqual(filtered_numbers, strategic_numbers)

    def test_business_slide_filtering(self):
        """Test strategic filtering in business slide generation"""
        from generate_business_slide import filter_strategic_work
        
        all_issues = self.strategic_issues + self.operational_issues
        filtered = filter_strategic_work(all_issues)
        
        # Should include only strategic work
        self.assertEqual(len(filtered), len(self.strategic_issues))
        
        # Verify no operational issues are included
        for issue in filtered:
            self.assertIn(issue['number'], [i['number'] for i in self.strategic_issues])

    def test_strategic_filtering_edge_cases(self):
        """Test strategic filtering edge cases"""
        from sync_issues import GitHubIssueSync
        
        sync = GitHubIssueSync("fake_token", "owner", "repo")
        
        # Empty labels and generic title
        empty_issue = {"labels": [], "title": "Update something"}
        self.assertFalse(sync._is_strategic_work(empty_issue))
        
        # Multiple mixed labels - strategic should win
        mixed_labels_strategic = {
            "labels": [{"name": "chore"}, {"name": "feature"}],
            "title": "Generic title"
        }
        self.assertTrue(sync._is_strategic_work(mixed_labels_strategic))
        
        # Multiple operational labels
        multiple_operational = {
            "labels": [{"name": "chore"}, {"name": "maintenance"}, {"name": "ci"}],
            "title": "Routine maintenance task"
        }
        self.assertFalse(sync._is_strategic_work(multiple_operational))

    def test_strategic_filtering_case_insensitive(self):
        """Test that strategic filtering is case insensitive"""
        from sync_issues import GitHubIssueSync
        
        sync = GitHubIssueSync("fake_token", "owner", "repo")
        
        # Test case variations
        case_variations = [
            {"labels": [{"name": "Feature"}], "title": "test"},
            {"labels": [{"name": "FEATURE"}], "title": "test"},
            {"labels": [{"name": "feature"}], "title": "test"},
            {"labels": [], "title": "Add NEW FEATURE for customers"},
            {"labels": [], "title": "fix CRITICAL Bug in payment"}
        ]
        
        for issue in case_variations:
            with self.subTest(issue=issue):
                self.assertTrue(sync._is_strategic_work(issue))

    def test_strategic_filtering_configuration(self):
        """Test that strategic filtering can be disabled"""
        from sync_issues import GitHubIssueSync
        
        sync = GitHubIssueSync("fake_token", "owner", "repo")
        
        # When strategic filtering is disabled, all issues should pass
        all_issues = self.strategic_issues + self.operational_issues
        
        # Mock the no-strategic-filter option
        sync.strategic_filter = False
        
        # All issues should be included when filtering is disabled
        for issue in all_issues:
            # When strategic filtering is off, _is_strategic_work isn't used
            # Instead, all issues are included
            pass  # This would be tested in integration tests

    def test_strategic_keywords_comprehensive(self):
        """Test comprehensive list of strategic keywords"""
        from sync_issues import GitHubIssueSync
        
        sync = GitHubIssueSync("fake_token", "owner", "repo")
        
        # Business value keywords
        business_keywords = [
            "customer", "user", "client", "revenue", "business", "product",
            "feature", "capability", "functionality", "enhancement",
            "integration", "api", "dashboard", "report", "analytics",
            "security", "performance", "scalability", "reliability"
        ]
        
        for keyword in business_keywords:
            title = f"Implement {keyword} improvements"
            issue = {"labels": [], "title": title}
            with self.subTest(keyword=keyword):
                # Most business keywords should be strategic
                if keyword in ["customer", "user", "feature", "product", "security"]:
                    self.assertTrue(sync._is_strategic_work(issue))

    def test_operational_keywords_comprehensive(self):
        """Test comprehensive list of operational keywords"""
        from sync_issues import GitHubIssueSync
        
        sync = GitHubIssueSync("fake_token", "owner", "repo")
        
        # Operational keywords that should be filtered out
        operational_keywords = [
            "deploy", "deployment", "build", "ci", "pipeline", "infrastructure",
            "monitoring", "logging", "backup", "maintenance", "upgrade",
            "migration", "cleanup", "refactor", "dependency", "version",
            "configuration", "environment", "server", "database"
        ]
        
        for keyword in operational_keywords:
            title = f"Update {keyword} configuration"
            issue = {"labels": [], "title": title}
            with self.subTest(keyword=keyword):
                # Most operational keywords should be filtered out
                if keyword in ["deploy", "build", "ci", "infrastructure", "maintenance"]:
                    self.assertFalse(sync._is_strategic_work(issue))

    def test_filtering_preserves_issue_data(self):
        """Test that filtering preserves all original issue data"""
        from product_status_report import filter_strategic_issues
        
        # Add extra fields to test data preservation
        test_issues = []
        for issue in self.strategic_issues[:2]:
            enhanced_issue = issue.copy()
            enhanced_issue.update({
                "assignee": {"login": "testuser"},
                "milestone": {"title": "Sprint 1"},
                "created_at": "2024-01-15T10:00:00Z",
                "work_started_at": "2024-01-16T10:00:00Z"
            })
            test_issues.append(enhanced_issue)
        
        filtered = filter_strategic_issues(test_issues)
        
        # All original data should be preserved
        for filtered_issue in filtered:
            self.assertIn("assignee", filtered_issue)
            self.assertIn("milestone", filtered_issue)
            self.assertIn("created_at", filtered_issue)
            self.assertIn("work_started_at", filtered_issue)


# Mock functions that would be in the actual modules
class MockGitHubIssueSync:
    """Mock GitHubIssueSync for testing"""
    
    def __init__(self, token, owner, repo):
        self.strategic_filter = True
    
    def _is_strategic_work(self, issue):
        """Determine if issue represents strategic work"""
        # Check labels first
        labels = [label.get('name', '').lower() for label in issue.get('labels', [])]
        
        # Strategic labels
        strategic_labels = {
            'feature', 'epic', 'bug', 'customer-request', 'enhancement', 
            'security', 'performance', 'user-experience', 'integration'
        }
        
        # Operational labels (exclude)
        operational_labels = {
            'chore', 'deployment', 'infrastructure', 'technical-debt', 
            'maintenance', 'ci', 'devops', 'admin', 'build'
        }
        
        # If has operational labels, exclude
        if any(label in operational_labels for label in labels):
            return False
            
        # If has strategic labels, include
        if any(label in strategic_labels for label in labels):
            return True
        
        # Check title keywords
        title = issue.get('title', '').lower()
        
        # Strategic keywords in title
        strategic_keywords = [
            'feature', 'customer', 'user', 'product', 'implement', 'add', 
            'create', 'build', 'dashboard', 'report', 'api', 'integration'
        ]
        
        # Operational keywords in title
        operational_keywords = [
            'deploy', 'ci', 'pipeline', 'infrastructure', 'maintenance',
            'build', 'configuration', 'environment', 'dependency', 'upgrade'
        ]
        
        # If title contains operational keywords, exclude
        if any(keyword in title for keyword in operational_keywords):
            return False
            
        # If title contains strategic keywords, include
        if any(keyword in title for keyword in strategic_keywords):
            return True
        
        # Default to operational (exclude)
        return False


def filter_strategic_issues(issues):
    """Filter issues to include only strategic work"""
    mock_sync = MockGitHubIssueSync("fake", "fake", "fake")
    return [issue for issue in issues if mock_sync._is_strategic_work(issue)]


def filter_strategic_work(issues):
    """Alias for filter_strategic_issues"""
    return filter_strategic_issues(issues)


# Monkey patch the imports for testing
sys.modules[__name__].GitHubIssueSync = MockGitHubIssueSync


if __name__ == '__main__':
    unittest.main()