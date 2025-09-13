#!/usr/bin/env python3
"""
Unit tests for product_status_report.py - Executive product status reporting functionality
"""
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "openai",
#     "python-dotenv",
#     "pytest",
# ]
# ///

import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path to import product_status_report module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from product_status_report import (
    load_cycle_data, categorize_issue, is_work_started, group_issues_by_feature,
    create_business_impact_summary, create_markdown_footnote, format_status_report
)


class TestProductStatusReport(unittest.TestCase):
    """Test product status report functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.sample_issues_data = {
            "repository": {
                "github_owner": "test_owner",
                "github_repo": "test_repo",
                "sync_date": "2024-01-15T10:00:00Z",
                "total_issues_synced": 3
            },
            "issues": [
                {
                    "number": 123,
                    "title": "Add payment processing feature",
                    "state": "open",
                    "created_at": "2024-01-10T10:00:00Z",
                    "labels": [{"name": "feature"}, {"name": "customer-request"}],
                    "assignee": {"login": "developer1"},
                    "milestone": None,
                    "work_started_at": "2024-01-12T10:00:00Z"
                },
                {
                    "number": 124,
                    "title": "Fix login bug affecting customers",
                    "state": "open", 
                    "created_at": "2024-01-11T10:00:00Z",
                    "labels": [{"name": "bug"}, {"name": "high-priority"}],
                    "assignee": None,
                    "milestone": None,
                    "work_started_at": None
                },
                {
                    "number": 125,
                    "title": "Update deployment pipeline",
                    "state": "open",
                    "created_at": "2024-01-12T10:00:00Z", 
                    "labels": [{"name": "chore"}, {"name": "infrastructure"}],
                    "assignee": {"login": "devops1"},
                    "milestone": None,
                    "work_started_at": "2024-01-13T10:00:00Z"
                }
            ]
        }

    @patch('builtins.open', new_callable=mock_open)
    def test_load_cycle_data(self, mock_file):
        """Test loading cycle time data from JSON file"""
        mock_file.return_value.read.return_value = json.dumps(self.sample_issues_data)
        
        data = load_cycle_data("test_file.json")
        
        self.assertEqual(data["repository"]["github_owner"], "test_owner")
        self.assertEqual(len(data["issues"]), 3)

    def test_categorize_issue_customer(self):
        """Test issue categorization for customer impact"""
        customer_issue = {
            "labels": [{"name": "customer-request"}, {"name": "feature"}],
            "title": "Add customer requested feature"
        }
        
        category = categorize_issue(customer_issue)
        self.assertEqual(category, "customer")

    def test_categorize_issue_feature(self):
        """Test issue categorization for product features"""
        feature_issue = {
            "labels": [{"name": "feature"}, {"name": "enhancement"}],
            "title": "New product capability"
        }
        
        category = categorize_issue(feature_issue)
        self.assertEqual(category, "feature")

    def test_categorize_issue_product(self):
        """Test issue categorization for product improvements"""
        product_issue = {
            "labels": [{"name": "bug"}, {"name": "high-priority"}],
            "title": "Critical system bug"
        }
        
        category = categorize_issue(product_issue)
        self.assertEqual(category, "product")

    def test_categorize_issue_platform(self):
        """Test issue categorization for platform work"""
        platform_issue = {
            "labels": [{"name": "technical-debt"}, {"name": "refactor"}],
            "title": "Refactor authentication system"
        }
        
        category = categorize_issue(platform_issue)
        self.assertEqual(category, "platform")

    def test_is_work_started_with_assignee_and_date(self):
        """Test work started detection with assignee and start date"""
        issue = {
            "assignee": {"login": "developer1"},
            "work_started_at": "2024-01-12T10:00:00Z"
        }
        
        self.assertTrue(is_work_started(issue))

    def test_is_work_started_assignee_only(self):
        """Test work started detection with assignee but no start date"""
        issue = {
            "assignee": {"login": "developer1"},
            "work_started_at": None
        }
        
        self.assertFalse(is_work_started(issue))

    def test_is_work_started_no_assignee(self):
        """Test work started detection with no assignee"""
        issue = {
            "assignee": None,
            "work_started_at": None
        }
        
        self.assertFalse(is_work_started(issue))

    def test_group_issues_by_feature(self):
        """Test grouping issues by feature/initiative"""
        issues = self.sample_issues_data["issues"]
        
        grouped = group_issues_by_feature(issues)
        
        # Should create groups based on labels or titles
        self.assertIsInstance(grouped, dict)
        self.assertGreater(len(grouped), 0)

    def test_create_business_impact_summary(self):
        """Test creating business impact summary"""
        issues = [issue for issue in self.sample_issues_data["issues"] 
                 if issue["number"] != 125]  # Exclude operational work
        
        summary = create_business_impact_summary(issues)
        
        self.assertIn("customer", summary)
        self.assertIn("feature", summary)
        self.assertIn("product", summary)
        self.assertIsInstance(summary["customer"], dict)

    def test_create_markdown_footnote(self):
        """Test creating markdown footnotes for GitHub issues"""
        issue = {
            "number": 123,
            "title": "Test Issue",
            "html_url": "https://github.com/owner/repo/issues/123"
        }
        
        footnote = create_markdown_footnote(issue, "owner", "repo")
        
        self.assertIn("[^123]", footnote)
        self.assertIn("https://github.com/owner/repo/issues/123", footnote)
        self.assertIn("Test Issue", footnote)

    def test_format_status_report_basic(self):
        """Test basic status report formatting"""
        issues = [issue for issue in self.sample_issues_data["issues"] 
                 if issue["number"] != 125]  # Exclude operational work
        repo_info = self.sample_issues_data["repository"]
        
        report = format_status_report(issues, repo_info, ai_client=None)
        
        self.assertIn("Product Status Report", report)
        self.assertIn("test_owner/test_repo", report)
        self.assertIn("## Work Status Summary", report)

    @patch('openai.OpenAI')
    def test_format_status_report_with_ai(self, mock_openai):
        """Test status report formatting with AI enhancements"""
        # Mock AI client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "AI-enhanced strategic summary"
        mock_client.chat.completions.create.return_value = mock_response
        
        issues = [issue for issue in self.sample_issues_data["issues"] 
                 if issue["number"] != 125]  # Exclude operational work
        repo_info = self.sample_issues_data["repository"]
        
        report = format_status_report(issues, repo_info, ai_client=mock_client)
        
        self.assertIn("AI-enhanced strategic summary", report)
        mock_client.chat.completions.create.assert_called()

    def test_filter_strategic_issues(self):
        """Test filtering to include only strategic work"""
        from product_status_report import filter_strategic_issues
        
        filtered = filter_strategic_issues(self.sample_issues_data["issues"])
        
        # Should exclude the deployment pipeline issue (operational)
        self.assertEqual(len(filtered), 2)
        issue_numbers = [issue["number"] for issue in filtered]
        self.assertIn(123, issue_numbers)  # Payment feature
        self.assertIn(124, issue_numbers)  # Login bug
        self.assertNotIn(125, issue_numbers)  # Deployment pipeline

    def test_work_progress_classification(self):
        """Test classification of work progress states"""
        issues = self.sample_issues_data["issues"]
        
        # Payment processing (assigned + started)
        payment_issue = issues[0]
        self.assertTrue(is_work_started(payment_issue))
        
        # Login bug (unassigned, not started)
        login_bug = issues[1]
        self.assertFalse(is_work_started(login_bug))

    def test_assignee_workload_analysis(self):
        """Test analysis of individual assignee workloads"""
        from product_status_report import analyze_assignee_workloads
        
        strategic_issues = [issue for issue in self.sample_issues_data["issues"] 
                           if issue["number"] != 125]  # Exclude operational
        
        workloads = analyze_assignee_workloads(strategic_issues)
        
        self.assertIn("developer1", workloads)
        self.assertIn("unassigned", workloads)
        self.assertEqual(workloads["developer1"], 1)  # One assigned issue
        self.assertEqual(workloads["unassigned"], 1)  # One unassigned issue

    @patch('sys.argv', ['product_status_report.py', 'test_file.json'])
    @patch('builtins.open', new_callable=mock_open)
    def test_command_line_argument_parsing(self, mock_file):
        """Test command line argument parsing with JSON file argument"""
        mock_file.return_value.read.return_value = json.dumps(self.sample_issues_data)
        
        # Test the argparse functionality with explicit file argument
        from product_status_report import main
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            with patch('builtins.print'):  # Suppress output
                # Should accept the JSON file argument and process it
                try:
                    main()
                except SystemExit:
                    pass  # argparse calls sys.exit(), which is expected

    @patch('sys.argv', ['product_status_report.py'])  # No file argument
    @patch('builtins.open', new_callable=mock_open)
    def test_command_line_default_fallback(self, mock_file):
        """Test command line parsing with default file fallback"""
        mock_file.return_value.read.return_value = json.dumps(self.sample_issues_data)
        
        # Test the argparse functionality with default file fallback
        from product_status_report import main
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            with patch('builtins.print'):  # Suppress output
                with patch('os.path.exists', return_value=True):  # Default file exists
                    try:
                        main()
                    except SystemExit:
                        pass
                    except FileNotFoundError:
                        pass  # Expected when default file doesn't exist

    def test_load_cycle_data_with_file_parameter(self):
        """Test load_cycle_data function accepts file path parameter"""
        with patch('builtins.open', mock_open(read_data=json.dumps(self.sample_issues_data))):
            # Test that load_cycle_data can accept custom file path
            data = load_cycle_data("custom_file.json")
            
            self.assertEqual(data["repository"]["github_owner"], "test_owner")
            self.assertEqual(len(data["issues"]), 3)


if __name__ == '__main__':
    unittest.main()