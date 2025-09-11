#!/usr/bin/env python3
"""
Unit tests for GitHub Cycle Time Analyzer
"""
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "requests",
#     "pandas",
#     "matplotlib",
#     "seaborn",
#     "python-dotenv",
#     "openai",
# ]
# ///

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import json
import tempfile
import os
import sys
import pandas as pd
from pathlib import Path

# Add parent directory to path to import cycle_time module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cycle_time import GitHubCycleTimeAnalyzer, CycleTimeMetrics


class TestCycleTimeMetrics(unittest.TestCase):
    """Test the CycleTimeMetrics dataclass"""
    
    def test_cycle_time_metrics_creation(self):
        """Test creating a CycleTimeMetrics instance"""
        created = datetime.now()
        closed = created + timedelta(days=5)
        work_started = created + timedelta(days=1)
        
        metrics = CycleTimeMetrics(
            issue_number=123,
            title="Test Issue",
            created_at=created,
            closed_at=closed,
            work_started_at=work_started,
            lead_time_days=5.0,
            cycle_time_days=4.0,
            labels=["bug", "high-priority"],
            assignee="testuser",
            milestone="v1.0",
            state="closed"
        )
        
        self.assertEqual(metrics.issue_number, 123)
        self.assertEqual(metrics.title, "Test Issue")
        self.assertEqual(metrics.lead_time_days, 5.0)
        self.assertEqual(metrics.cycle_time_days, 4.0)
        self.assertEqual(len(metrics.labels), 2)


class TestGitHubCycleTimeAnalyzer(unittest.TestCase):
    """Test the main GitHubCycleTimeAnalyzer class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.token = "test_token"
        self.owner = "test_owner"
        self.repo = "test_repo"
        self.analyzer = GitHubCycleTimeAnalyzer(self.token, self.owner, self.repo)
    
    def test_analyzer_initialization(self):
        """Test analyzer is properly initialized"""
        self.assertEqual(self.analyzer.token, self.token)
        self.assertEqual(self.analyzer.owner, self.owner)
        self.assertEqual(self.analyzer.repo, self.repo)
        self.assertEqual(self.analyzer.base_url, "https://api.github.com")
        self.assertIsNotNone(self.analyzer.session)
        self.assertIn('Authorization', self.analyzer.session.headers)
        self.assertIsNone(self.analyzer.commit_search_available)
    
    @patch('requests.Session.get')
    def test_make_request_success(self, mock_get):
        """Test successful API request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}
        mock_get.return_value = mock_response
        
        result = self.analyzer._make_request("https://api.github.com/test")
        
        self.assertEqual(result, {"test": "data"})
        mock_get.assert_called_once()
    
    @patch('time.sleep')
    @patch('time.time')
    @patch('requests.Session.get')
    def test_make_request_rate_limit(self, mock_get, mock_time, mock_sleep):
        """Test rate limit handling"""
        # First call returns rate limit error
        rate_limit_response = Mock()
        rate_limit_response.status_code = 403
        rate_limit_response.text = "rate limit exceeded"
        rate_limit_response.headers = {'X-RateLimit-Reset': '1609459200'}
        
        # Second call succeeds
        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {"success": True}
        
        mock_get.side_effect = [rate_limit_response, success_response]
        mock_time.return_value = 1609459000  # 200 seconds before reset
        
        result = self.analyzer._make_request("https://api.github.com/test")
        
        self.assertEqual(result, {"success": True})
        mock_sleep.assert_called_once_with(201)  # 200 + 1 second buffer
    
    @patch('requests.Session.get')
    def test_make_request_422_error(self, mock_get):
        """Test 422 error handling"""
        mock_response = Mock()
        mock_response.status_code = 422
        mock_response.text = "Validation Failed"
        mock_get.return_value = mock_response
        
        result = self.analyzer._make_request("https://api.github.com/test")
        
        self.assertEqual(result, {})  # Should return empty dict for 422
        mock_get.assert_called_once()
    
    @patch.object(GitHubCycleTimeAnalyzer, '_make_request')
    def test_commit_search_capability_available(self, mock_request):
        """Test commit search capability detection when available"""
        mock_request.return_value = {"total_count": 0, "items": []}
        
        result = self.analyzer._test_commit_search_capability()
        
        self.assertTrue(result)
        mock_request.assert_called_once()
    
    @patch.object(GitHubCycleTimeAnalyzer, '_make_request')
    def test_commit_search_capability_unavailable(self, mock_request):
        """Test commit search capability detection when unavailable"""
        from requests.exceptions import HTTPError
        
        # Mock 422 error
        mock_response = Mock()
        mock_response.status_code = 422
        
        http_error = HTTPError()
        http_error.response = mock_response
        mock_request.side_effect = http_error
        
        result = self.analyzer._test_commit_search_capability()
        
        self.assertFalse(result)
    
    @patch.object(GitHubCycleTimeAnalyzer, '_test_commit_search_capability')
    def test_fetch_commits_disabled(self, mock_test):
        """Test commit fetching when search is disabled"""
        mock_test.return_value = False
        
        commits = self.analyzer.fetch_commits_for_issue(123)
        
        self.assertEqual(commits, [])
        self.assertFalse(self.analyzer.commit_search_available)
    
    def test_sample_issue_data(self):
        """Test with sample issue data structure"""
        sample_issue = {
            "number": 1,
            "title": "Sample Issue",
            "created_at": "2024-01-01T10:00:00Z",
            "closed_at": "2024-01-05T15:00:00Z",
            "state": "closed",
            "labels": [{"name": "bug"}, {"name": "high-priority"}],
            "assignee": {"login": "testuser"},
            "milestone": {"title": "v1.0"}
        }
        
        # Test that issue data structure matches expectations
        self.assertEqual(sample_issue["number"], 1)
        self.assertIn("created_at", sample_issue)
        self.assertIn("closed_at", sample_issue)
        self.assertEqual(len(sample_issue["labels"]), 2)


class TestWorkStartDetection(unittest.TestCase):
    """Test work start time detection logic"""
    
    def setUp(self):
        self.analyzer = GitHubCycleTimeAnalyzer("token", "owner", "repo")
    
    @patch.object(GitHubCycleTimeAnalyzer, 'fetch_issue_events')
    @patch.object(GitHubCycleTimeAnalyzer, 'fetch_commits_for_issue')
    def test_extract_work_start_date_assignment(self, mock_commits, mock_events):
        """Test work start detection via assignment"""
        issue = {
            "number": 1,
            "created_at": "2024-01-01T10:00:00Z",
            "assignee": {"login": "testuser"}
        }
        
        mock_events.return_value = [
            {
                "event": "assigned",
                "created_at": "2024-01-02T09:00:00Z"
            }
        ]
        mock_commits.return_value = []
        
        work_start = self.analyzer.extract_work_start_date(issue)
        
        self.assertIsNotNone(work_start)
        self.assertEqual(work_start.day, 2)
    
    @patch.object(GitHubCycleTimeAnalyzer, 'fetch_issue_events')
    @patch.object(GitHubCycleTimeAnalyzer, 'fetch_commits_for_issue')
    def test_extract_work_start_date_commit(self, mock_commits, mock_events):
        """Test work start detection via first commit"""
        issue = {
            "number": 1,
            "created_at": "2024-01-01T10:00:00Z",
            "assignee": None
        }
        
        mock_events.return_value = []
        mock_commits.return_value = [
            {
                "commit": {
                    "committer": {
                        "date": "2024-01-03T14:00:00Z"
                    }
                }
            }
        ]
        
        work_start = self.analyzer.extract_work_start_date(issue)
        
        self.assertIsNotNone(work_start)
        self.assertEqual(work_start.day, 3)
    
    @patch.object(GitHubCycleTimeAnalyzer, 'fetch_issue_events')
    @patch.object(GitHubCycleTimeAnalyzer, 'fetch_commits_for_issue')
    def test_extract_work_start_date_label(self, mock_commits, mock_events):
        """Test work start detection via progress label"""
        issue = {
            "number": 1,
            "created_at": "2024-01-01T10:00:00Z",
            "assignee": None
        }
        
        mock_events.return_value = [
            {
                "event": "labeled",
                "created_at": "2024-01-01T16:00:00Z",
                "label": {"name": "in progress"}
            }
        ]
        mock_commits.return_value = []
        
        work_start = self.analyzer.extract_work_start_date(issue)
        
        self.assertIsNotNone(work_start)
        self.assertEqual(work_start.hour, 16)


class TestCycleTimeCalculation(unittest.TestCase):
    """Test cycle time calculation logic"""
    
    def setUp(self):
        self.analyzer = GitHubCycleTimeAnalyzer("token", "owner", "repo")
    
    @patch.object(GitHubCycleTimeAnalyzer, 'extract_work_start_date')
    def test_calculate_cycle_times(self, mock_work_start):
        """Test cycle time calculation for multiple issues"""
        issues = [
            {
                "number": 1,
                "title": "Test Issue 1",
                "created_at": "2024-01-01T10:00:00Z",
                "closed_at": "2024-01-05T10:00:00Z",
                "state": "closed",
                "labels": [],
                "assignee": None,
                "milestone": None
            },
            {
                "number": 2,
                "title": "Test Issue 2",
                "created_at": "2024-01-02T10:00:00Z",
                "closed_at": None,
                "state": "open",
                "labels": [{"name": "bug"}],
                "assignee": {"login": "testuser"},
                "milestone": {"title": "v1.0"}
            }
        ]
        
        # Mock work start dates - need timezone-aware datetimes to match cycle_time.py
        from datetime import timezone
        mock_work_start.side_effect = [
            datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc),  # Issue 1: work started 1 day after creation
            None  # Issue 2: no work start detected
        ]
        
        metrics = self.analyzer.calculate_cycle_times(issues)
        
        self.assertEqual(len(metrics), 2)
        
        # Check first issue (closed)
        self.assertEqual(metrics[0].issue_number, 1)
        self.assertEqual(metrics[0].lead_time_days, 4.0)  # 4 days from creation to closure
        self.assertEqual(metrics[0].cycle_time_days, 3.0)  # 3 days from work start to closure
        
        # Check second issue (open)
        self.assertEqual(metrics[1].issue_number, 2)
        self.assertIsNone(metrics[1].lead_time_days)  # Not closed
        self.assertIsNone(metrics[1].cycle_time_days)  # Not closed
        self.assertEqual(metrics[1].assignee, "testuser")
        self.assertEqual(metrics[1].milestone, "v1.0")


class TestMonthlyCycleTrends(unittest.TestCase):
    """Test monthly cycle time trend calculation"""
    
    def setUp(self):
        self.analyzer = GitHubCycleTimeAnalyzer("token", "owner", "repo")
        
        # Create sample DataFrame with closed issues across multiple months
        import pandas as pd
        from datetime import timezone
        
        self.sample_df = pd.DataFrame({
            'closed_at': [
                datetime(2024, 1, 15, tzinfo=timezone.utc),
                datetime(2024, 1, 20, tzinfo=timezone.utc),
                datetime(2024, 2, 10, tzinfo=timezone.utc),
                datetime(2024, 2, 25, tzinfo=timezone.utc),
                datetime(2024, 3, 5, tzinfo=timezone.utc),
                datetime(2024, 3, 15, tzinfo=timezone.utc),
                datetime(2024, 4, 1, tzinfo=timezone.utc),
            ],
            'cycle_time_days': [5.0, 7.0, 3.0, 4.0, 6.0, 8.0, 2.0],
            'state': ['closed'] * 7
        })
    
    def test_calculate_monthly_cycle_trends(self):
        """Test monthly cycle time trend calculation"""
        result = self.analyzer._calculate_monthly_cycle_trends(self.sample_df)
        
        self.assertFalse(result.empty)
        self.assertIn('monthly_avg', result.columns)
        self.assertIn('rolling_6m', result.columns)
        self.assertIn('issue_count', result.columns)
    
    def test_monthly_trends_insufficient_data(self):
        """Test monthly trends with insufficient data"""
        # Only 2 issues, should return empty DataFrame
        small_df = self.sample_df.head(2)
        result = self.analyzer._calculate_monthly_cycle_trends(small_df)
        
        self.assertTrue(result.empty)
    
    def test_monthly_trends_no_cycle_time(self):
        """Test monthly trends with no cycle time data"""
        import pandas as pd
        no_cycle_df = pd.DataFrame({
            'closed_at': [datetime.now()] * 5,
            'cycle_time_days': [None] * 5,
            'state': ['closed'] * 5
        })
        
        result = self.analyzer._calculate_monthly_cycle_trends(no_cycle_df)
        
        self.assertTrue(result.empty)


class TestAIRecommendations(unittest.TestCase):
    """Test AI-powered recommendations"""
    
    def setUp(self):
        self.analyzer = GitHubCycleTimeAnalyzer("token", "owner", "repo")
        
        # Create sample data
        import pandas as pd
        self.sample_df = pd.DataFrame({
            'state': ['closed'] * 5,
            'cycle_time_days': [1.0, 2.0, 3.0, 4.0, 5.0],
            'assignee': ['user1', None, 'user2', None, 'user1'],
            'comments': [0, 1, 2, 3, 4]
        })
        
        self.sample_stats = self.sample_df['cycle_time_days'].describe()
    
    @patch.dict(os.environ, {}, clear=True)
    def test_ai_recommendations_no_api_key(self):
        """Test fallback recommendations when no OpenAI API key"""
        result = self.analyzer._generate_ai_recommendations(
            self.sample_df, self.sample_stats, self.sample_stats, pd.DataFrame()
        )
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertIn("Focus on reducing queue time", result[0])
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('openai.OpenAI')
    def test_ai_recommendations_with_api_key(self, mock_openai):
        """Test AI recommendations when API key is available"""
        # Mock OpenAI response
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "- Improve assignment process\n- Reduce cycle time variance\n- Implement better tracking"
        
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        result = self.analyzer._generate_ai_recommendations(
            self.sample_df, self.sample_stats, self.sample_stats, pd.DataFrame()
        )
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertIn("Improve assignment process", result[0])
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('openai.OpenAI')
    def test_ai_recommendations_api_failure(self, mock_openai):
        """Test AI recommendations fallback when API fails"""
        # Mock OpenAI failure
        mock_openai.side_effect = Exception("API Error")
        
        result = self.analyzer._generate_ai_recommendations(
            self.sample_df, self.sample_stats, self.sample_stats, pd.DataFrame()
        )
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertIn("Focus on reducing queue time", result[0])  # Should fall back to defaults


class TestReportGeneration(unittest.TestCase):
    """Test report generation functionality"""
    
    def setUp(self):
        self.analyzer = GitHubCycleTimeAnalyzer("token", "owner", "repo")
        
        # Create sample metrics with timezone-aware datetimes
        from datetime import timezone
        self.sample_metrics = [
            CycleTimeMetrics(
                issue_number=1,
                title="Test Issue 1",
                created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                closed_at=datetime(2024, 1, 5, tzinfo=timezone.utc),
                work_started_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
                lead_time_days=4.0,
                cycle_time_days=3.0,
                labels=["bug"],
                assignee="user1",
                milestone="v1.0",
                state="closed"
            ),
            CycleTimeMetrics(
                issue_number=2,
                title="Test Issue 2",
                created_at=datetime(2024, 1, 3, tzinfo=timezone.utc),
                closed_at=datetime(2024, 1, 8, tzinfo=timezone.utc),
                work_started_at=datetime(2024, 1, 4, tzinfo=timezone.utc),
                lead_time_days=5.0,
                cycle_time_days=4.0,
                labels=["feature"],
                assignee="user2",
                milestone="v1.1",
                state="closed"
            )
        ]
    
    @patch('matplotlib.pyplot.savefig')
    @patch('matplotlib.pyplot.close')
    @patch.dict(os.environ, {}, clear=True)  # Clear environment to avoid OpenAI calls
    def test_generate_report(self, mock_close, mock_savefig):
        """Test report generation creates expected files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            self.analyzer.generate_report(self.sample_metrics, temp_dir)
            
            # Check that expected files are created
            csv_file = Path(temp_dir) / "cycle_time_data.csv"
            html_file = Path(temp_dir) / "cycle_time_report.html"
            
            self.assertTrue(csv_file.exists())
            self.assertTrue(html_file.exists())
            
            # Verify CSV content
            with open(csv_file, 'r') as f:
                content = f.read()
                self.assertIn("issue_number,title,created_at", content)
                self.assertIn("Test Issue 1", content)
                self.assertIn("Test Issue 2", content)
            
            # Verify HTML content
            with open(html_file, 'r') as f:
                html_content = f.read()
                self.assertIn("Cycle Time Analysis Report", html_content)
                self.assertIn("owner/repo", html_content)
                self.assertIn("Lead Time", html_content)
                self.assertIn("Recommendations", html_content)
    
    def test_html_report_generation(self):
        """Test HTML report contains expected elements"""
        # Mock DataFrame for statistics
        import pandas as pd
        df_data = []
        for metric in self.sample_metrics:
            df_data.append({
                'lead_time_days': metric.lead_time_days,
                'cycle_time_days': metric.cycle_time_days,
                'work_started_at': metric.work_started_at,
                'created_at': metric.created_at
            })
        
        df = pd.DataFrame(df_data)
        lead_time_stats = df['lead_time_days'].describe()
        cycle_time_stats = df['cycle_time_days'].describe()
        
        # Mock monthly cycle data and recommendations
        monthly_data = pd.DataFrame()
        recommendations = ["Test recommendation 1", "Test recommendation 2"]
        
        html_report = self.analyzer._generate_html_report(
            df, lead_time_stats, cycle_time_stats, monthly_data, recommendations, "test_dir"
        )
        
        self.assertIn("<!DOCTYPE html>", html_report)
        self.assertIn("Cycle Time Analysis Report", html_report)
        self.assertIn("owner/repo", html_report)
        self.assertIn("Lead Time", html_report)
        self.assertIn("Cycle Time", html_report)


class TestIntegrationMocked(unittest.TestCase):
    """Integration tests with mocked API responses"""
    
    @patch.object(GitHubCycleTimeAnalyzer, '_make_request')
    def test_fetch_issues_integration(self, mock_request):
        """Test fetching issues with mocked API response"""
        analyzer = GitHubCycleTimeAnalyzer("token", "owner", "repo")
        
        # Mock API responses
        mock_request.side_effect = [
            [  # First page
                {
                    "number": 1,
                    "title": "Issue 1",
                    "created_at": "2024-01-01T10:00:00Z",
                    "closed_at": "2024-01-05T10:00:00Z",
                    "state": "closed",
                    "labels": [],
                    "assignee": None,
                    "milestone": None
                }
            ],
            []  # Empty second page (end of results)
        ]
        
        issues = analyzer.fetch_issues()
        
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["number"], 1)
        # Note: mock_request call count depends on pagination logic
    
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch.object(GitHubCycleTimeAnalyzer, '_make_request')
    def test_fetch_issues_with_limit(self, mock_request, mock_open):
        """Test fetching issues with limit parameter"""
        analyzer = GitHubCycleTimeAnalyzer("token", "owner", "repo")
        
        # Mock API response with more issues than limit
        mock_request.return_value = [
            {"number": i, "title": f"Issue {i}", "created_at": "2024-01-01T10:00:00Z",
             "closed_at": None, "state": "open", "labels": [], "assignee": None, "milestone": None}
            for i in range(1, 11)  # 10 issues
        ]
        
        issues = analyzer.fetch_issues(limit=5)
        
        self.assertEqual(len(issues), 5)  # Should be limited to 5
        self.assertEqual(issues[0]["number"], 1)
        self.assertEqual(issues[4]["number"], 5)
    
    @patch.object(GitHubCycleTimeAnalyzer, '_make_request')
    def test_fetch_issue_events_integration(self, mock_request):
        """Test fetching issue events"""
        analyzer = GitHubCycleTimeAnalyzer("token", "owner", "repo")
        
        mock_request.return_value = [
            {
                "event": "assigned",
                "created_at": "2024-01-02T09:00:00Z",
                "assignee": {"login": "testuser"}
            }
        ]
        
        events = analyzer.fetch_issue_events(1)
        
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "assigned")


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)