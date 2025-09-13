#!/usr/bin/env python3
"""
Unit tests for generate_business_slide.py - Business presentation slide generation
"""
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "matplotlib",
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

# Add parent directory to path to import generate_business_slide module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from generate_business_slide import (
    load_cycle_data, categorize_issues_by_time_period, create_business_slide,
    group_by_initiative, get_sprint_periods
)


class TestBusinessSlideGeneration(unittest.TestCase):
    """Test business slide generation functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create sample data with different time periods
        now = datetime.now()
        last_week = now - timedelta(days=7)
        next_month = now + timedelta(days=30)
        
        self.sample_data = {
            "repository": {
                "github_owner": "test_owner",
                "github_repo": "test_repo",
                "sync_date": now.isoformat() + "Z",
                "total_issues_synced": 4
            },
            "issues": [
                {
                    "number": 100,
                    "title": "Payment processing feature completed last week",
                    "state": "closed",
                    "created_at": (now - timedelta(days=14)).isoformat() + "Z",
                    "closed_at": (now - timedelta(days=3)).isoformat() + "Z",
                    "labels": [{"name": "feature"}, {"name": "customer-request"}],
                    "assignee": {"login": "dev1"},
                    "milestone": {"title": "Q1 Release"}
                },
                {
                    "number": 101,
                    "title": "User authentication improvements in progress",
                    "state": "open",
                    "created_at": (now - timedelta(days=10)).isoformat() + "Z",
                    "closed_at": None,
                    "labels": [{"name": "feature"}, {"name": "security"}],
                    "assignee": {"login": "dev2"},
                    "milestone": {"title": "Current Sprint"},
                    "work_started_at": (now - timedelta(days=2)).isoformat() + "Z"
                },
                {
                    "number": 102,
                    "title": "Mobile app redesign planned for next month",
                    "state": "open",
                    "created_at": now.isoformat() + "Z",
                    "closed_at": None,
                    "labels": [{"name": "epic"}, {"name": "mobile"}],
                    "assignee": None,
                    "milestone": {"title": "Q2 Mobile"},
                    "work_started_at": None
                },
                {
                    "number": 103,
                    "title": "Deploy infrastructure updates",
                    "state": "closed", 
                    "created_at": (now - timedelta(days=5)).isoformat() + "Z",
                    "closed_at": (now - timedelta(days=1)).isoformat() + "Z",
                    "labels": [{"name": "chore"}, {"name": "infrastructure"}],
                    "assignee": {"login": "devops1"},
                    "milestone": None
                }
            ]
        }

    @patch('builtins.open', new_callable=mock_open)
    def test_load_cycle_data(self, mock_file):
        """Test loading cycle data with new JSON structure"""
        mock_file.return_value.read.return_value = json.dumps(self.sample_data)
        
        data = load_cycle_data("test_file.json")
        
        self.assertEqual(data["repository"]["github_owner"], "test_owner")
        self.assertEqual(len(data["issues"]), 4)

    def test_get_sprint_periods(self):
        """Test calculation of sprint time periods"""
        periods = get_sprint_periods()
        
        self.assertIn("last_week_start", periods)
        self.assertIn("last_week_end", periods)
        self.assertIn("this_week_start", periods)
        self.assertIn("this_week_end", periods)
        self.assertIn("next_30_days_end", periods)
        
        # Verify the periods make sense
        self.assertLess(periods["last_week_start"], periods["last_week_end"])
        self.assertLess(periods["this_week_start"], periods["this_week_end"])
        self.assertGreater(periods["next_30_days_end"], periods["this_week_end"])

    def test_categorize_issues_by_time_period(self):
        """Test categorization of issues into time periods"""
        issues = self.sample_data["issues"]
        strategic_issues = [issue for issue in issues if issue["number"] != 103]  # Exclude operational
        
        categorized = categorize_issues_by_time_period(strategic_issues)
        
        self.assertIn("last_week", categorized)
        self.assertIn("this_week", categorized)
        self.assertIn("next_30_days", categorized)
        
        # Check that strategic issues are properly distributed
        total_categorized = (len(categorized["last_week"]) + 
                           len(categorized["this_week"]) + 
                           len(categorized["next_30_days"]))
        self.assertGreater(total_categorized, 0)

    def test_group_by_initiative(self):
        """Test grouping issues by initiative/milestone"""
        issues = [
            {"milestone": {"title": "Q1 Release"}, "title": "Feature A", "number": 1},
            {"milestone": {"title": "Q1 Release"}, "title": "Feature B", "number": 2},
            {"milestone": {"title": "Q2 Mobile"}, "title": "Mobile Feature", "number": 3},
            {"milestone": None, "title": "Standalone Feature", "number": 4}
        ]
        
        grouped = group_by_initiative(issues)
        
        self.assertIn("Q1 Release", grouped)
        self.assertIn("Q2 Mobile", grouped)
        self.assertIn("Other", grouped)  # For issues without milestones
        
        self.assertEqual(len(grouped["Q1 Release"]), 2)
        self.assertEqual(len(grouped["Q2 Mobile"]), 1)
        self.assertEqual(len(grouped["Other"]), 1)

    def test_strategic_filtering(self):
        """Test that only strategic work is included in slides"""
        from generate_business_slide import filter_strategic_work
        
        all_issues = self.sample_data["issues"]
        strategic_issues = filter_strategic_work(all_issues)
        
        # Should exclude the infrastructure deployment (operational work)
        self.assertEqual(len(strategic_issues), 3)
        issue_numbers = [issue["number"] for issue in strategic_issues]
        self.assertNotIn(103, issue_numbers)  # Infrastructure deployment should be excluded

    @patch('matplotlib.pyplot.savefig')
    @patch('matplotlib.pyplot.figure')
    def test_create_business_slide_basic(self, mock_figure, mock_savefig):
        """Test basic business slide creation without AI"""
        mock_fig = Mock()
        mock_figure.return_value = mock_fig
        
        issues = [issue for issue in self.sample_data["issues"] if issue["number"] != 103]
        repo_info = self.sample_data["repository"]
        
        create_business_slide(issues, repo_info, ai_client=None, output_file="test_slide.png")
        
        mock_figure.assert_called()
        mock_savefig.assert_called_with("test_slide.png", dpi=300, bbox_inches='tight')

    @patch('matplotlib.pyplot.savefig')
    @patch('matplotlib.pyplot.figure')
    @patch('openai.OpenAI')
    def test_create_business_slide_with_ai(self, mock_openai, mock_figure, mock_savefig):
        """Test business slide creation with AI enhancements"""
        # Mock AI client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "AI-enhanced initiative grouping and prioritization"
        mock_client.chat.completions.create.return_value = mock_response
        
        mock_fig = Mock()
        mock_figure.return_value = mock_fig
        
        issues = [issue for issue in self.sample_data["issues"] if issue["number"] != 103]
        repo_info = self.sample_data["repository"]
        
        create_business_slide(issues, repo_info, ai_client=mock_client, output_file="test_slide.png")
        
        mock_client.chat.completions.create.assert_called()
        mock_figure.assert_called()
        mock_savefig.assert_called()

    def test_issue_priority_classification(self):
        """Test classification of issues by business priority"""
        from generate_business_slide import classify_business_priority
        
        # High priority: customer requests, security, bugs
        high_priority_issue = {
            "labels": [{"name": "customer-request"}, {"name": "high-priority"}],
            "title": "Critical customer feature"
        }
        
        # Medium priority: features, enhancements
        medium_priority_issue = {
            "labels": [{"name": "feature"}, {"name": "enhancement"}],
            "title": "Product improvement"
        }
        
        # Low priority: technical debt, refactoring
        low_priority_issue = {
            "labels": [{"name": "technical-debt"}, {"name": "refactor"}],
            "title": "Code cleanup"
        }
        
        self.assertEqual(classify_business_priority(high_priority_issue), "high")
        self.assertEqual(classify_business_priority(medium_priority_issue), "medium")
        self.assertEqual(classify_business_priority(low_priority_issue), "low")

    def test_sprint_progress_calculation(self):
        """Test calculation of sprint progress metrics"""
        from generate_business_slide import calculate_sprint_progress
        
        # Mix of completed and in-progress work
        sprint_issues = [
            {"state": "closed", "assignee": {"login": "dev1"}},  # Completed
            {"state": "open", "assignee": {"login": "dev2"}, "work_started_at": "2024-01-15T10:00:00Z"},  # In progress
            {"state": "open", "assignee": None, "work_started_at": None}  # Not started
        ]
        
        progress = calculate_sprint_progress(sprint_issues)
        
        self.assertIn("completed", progress)
        self.assertIn("in_progress", progress)
        self.assertIn("not_started", progress)
        self.assertIn("completion_rate", progress)
        
        self.assertEqual(progress["completed"], 1)
        self.assertEqual(progress["in_progress"], 1)
        self.assertEqual(progress["not_started"], 1)
        self.assertAlmostEqual(progress["completion_rate"], 0.33, places=1)

    def test_resource_allocation_analysis(self):
        """Test analysis of resource allocation across initiatives"""
        from generate_business_slide import analyze_resource_allocation
        
        issues_with_assignments = [
            {"assignee": {"login": "dev1"}, "milestone": {"title": "Project A"}},
            {"assignee": {"login": "dev1"}, "milestone": {"title": "Project A"}},
            {"assignee": {"login": "dev2"}, "milestone": {"title": "Project B"}},
            {"assignee": None, "milestone": {"title": "Project C"}}
        ]
        
        allocation = analyze_resource_allocation(issues_with_assignments)
        
        self.assertIn("Project A", allocation)
        self.assertIn("Project B", allocation)
        self.assertIn("Project C", allocation)
        
        # dev1 should have 2 assignments in Project A
        self.assertEqual(allocation["Project A"]["assigned"], 2)
        # Project C should have 1 unassigned item
        self.assertEqual(allocation["Project C"]["unassigned"], 1)

    @patch('sys.argv', ['generate_business_slide.py', 'test_file.json'])
    @patch('builtins.open', new_callable=mock_open)
    @patch('matplotlib.pyplot.savefig')
    def test_command_line_usage(self, mock_savefig, mock_file):
        """Test command line argument parsing and execution with JSON file argument"""
        mock_file.return_value.read.return_value = json.dumps(self.sample_data)
        
        from generate_business_slide import main
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            with patch('matplotlib.pyplot.figure'):
                with patch('builtins.print'):  # Suppress output
                    try:
                        main()
                    except SystemExit:
                        pass  # argparse calls sys.exit(), which is expected

    @patch('sys.argv', ['generate_business_slide.py'])  # No file argument
    @patch('builtins.open', new_callable=mock_open)
    @patch('matplotlib.pyplot.savefig')
    def test_command_line_default_fallback(self, mock_savefig, mock_file):
        """Test command line parsing with default file fallback"""
        mock_file.return_value.read.return_value = json.dumps(self.sample_data)
        
        from generate_business_slide import main
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            with patch('matplotlib.pyplot.figure'):
                with patch('os.path.exists', return_value=True):  # Default file exists
                    with patch('builtins.print'):  # Suppress output
                        try:
                            main()
                        except SystemExit:
                            pass
                        except FileNotFoundError:
                            pass  # Expected when default file doesn't exist

    def test_load_cycle_data_with_file_parameter(self):
        """Test load_cycle_data function accepts file path parameter"""
        with patch('builtins.open', mock_open(read_data=json.dumps(self.sample_data))):
            # Test that load_cycle_data can accept custom file path
            data = load_cycle_data("custom_file.json")
            
            self.assertEqual(data["repository"]["github_owner"], "test_owner")
            self.assertEqual(len(data["issues"]), 4)

    def test_visual_layout_configuration(self):
        """Test configuration of slide visual layout"""
        from generate_business_slide import configure_slide_layout
        
        config = configure_slide_layout()
        
        self.assertIn("title_size", config)
        self.assertIn("section_size", config)
        self.assertIn("body_size", config)
        self.assertIn("color_scheme", config)
        
        # Verify reasonable font sizes
        self.assertGreater(config["title_size"], config["section_size"])
        self.assertGreater(config["section_size"], config["body_size"])


if __name__ == '__main__':
    unittest.main()