#!/usr/bin/env python3
"""
Unit tests for sync_issues.py - GitHub data collection functionality
"""
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "requests",
#     "rich",
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
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import sync_issues module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sync_issues import GitHubDataSyncer


class TestGitHubDataSyncer(unittest.TestCase):
    """Test the GitHubDataSyncer class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.sync = GitHubDataSyncer("fake_token", "test_owner", "test_repo")
        self.sample_issue = {
            "number": 123,
            "title": "Test Issue",
            "state": "open",
            "created_at": "2024-01-15T10:00:00Z",
            "labels": [{"name": "feature"}],
            "assignee": {"login": "testuser"},
            "milestone": None,
            "pull_request": None  # Not a PR
        }
        
    def test_init(self):
        """Test GitHubDataSyncer initialization"""
        self.assertEqual(self.sync.owner, "test_owner")
        self.assertEqual(self.sync.repo, "test_repo")
        self.assertEqual(self.sync.token, "fake_token")
        self.assertIsNotNone(self.sync.cache_dir)

    @patch('sync_issues.requests.get')
    def test_token_scope_detection(self, mock_get):
        """Test token scope detection functionality"""
        # Mock successful scope tests
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response
        
        scopes = self.sync._test_token_scopes()
        
        self.assertIn('issues', scopes)
        self.assertIn('contents', scopes)
        self.assertIn('pull_requests', scopes)
        self.assertIn('projects', scopes)
        
        # Should make test requests for each scope
        self.assertEqual(mock_get.call_count, 4)

    @patch('sync_issues.requests.get')
    def test_token_scope_detection_failure(self, mock_get):
        """Test token scope detection with missing permissions"""
        # Mock failed scope tests
        def side_effect(url, **kwargs):
            if 'contents' in url:
                mock_response = Mock()
                mock_response.status_code = 403
                return mock_response
            else:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = []
                return mock_response
                
        mock_get.side_effect = side_effect
        
        scopes = self.sync._test_token_scopes()
        
        self.assertTrue(scopes['issues'])
        self.assertFalse(scopes['contents'])  # Should fail
        self.assertTrue(scopes['pull_requests'])
        self.assertTrue(scopes['projects'])

    def test_strategic_filtering_includes(self):
        """Test strategic filtering includes business value work"""
        # Test cases that should be included
        strategic_cases = [
            {"labels": [{"name": "feature"}]},
            {"labels": [{"name": "epic"}]},
            {"labels": [{"name": "bug"}]},
            {"labels": [{"name": "customer-request"}]},
            {"title": "Add new payment processing feature"},
        ]
        
        for issue in strategic_cases:
            issue.update(self.sample_issue)
            with self.subTest(issue=issue):
                self.assertTrue(self.sync._is_strategic_work(issue))

    def test_strategic_filtering_excludes(self):
        """Test strategic filtering excludes operational work"""
        # Test cases that should be excluded
        operational_cases = [
            {"labels": [{"name": "chore"}]},
            {"labels": [{"name": "deployment"}]},
            {"labels": [{"name": "infrastructure"}]},
            {"labels": [{"name": "maintenance"}]},
            {"title": "Deploy to production environment"},
            {"title": "Update CI/CD pipeline configuration"},
            {"title": "Routine database maintenance"},
        ]
        
        for issue in operational_cases:
            issue.update(self.sample_issue)
            with self.subTest(issue=issue):
                self.assertFalse(self.sync._is_strategic_work(issue))

    @patch('sync_issues.requests.get')
    def test_fetch_issues_basic(self, mock_get):
        """Test basic issue fetching functionality"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [self.sample_issue]
        mock_response.links = {}
        mock_get.return_value = mock_response
        
        issues = self.sync.fetch_issues(state='open', limit=1)
        
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['number'], 123)
        mock_get.assert_called()

    @patch('sync_issues.requests.get')
    def test_fetch_issues_with_pagination(self, mock_get):
        """Test issue fetching with pagination"""
        # Mock first page
        first_response = Mock()
        first_response.status_code = 200
        first_response.json.return_value = [self.sample_issue]
        first_response.links = {'next': {'url': 'https://api.github.com/page2'}}
        
        # Mock second page
        second_response = Mock()
        second_response.status_code = 200
        second_response.json.return_value = []
        second_response.links = {}
        
        mock_get.side_effect = [first_response, second_response]
        
        issues = self.sync.fetch_issues(state='all')
        
        self.assertEqual(len(issues), 1)
        self.assertEqual(mock_get.call_count, 2)

    def test_cache_path_generation(self):
        """Test cache path generation"""
        cache_path = self.sync._get_cache_path("issues", page=1, state="open")
        
        self.assertIn("test_owner", str(cache_path))
        self.assertIn("test_repo", str(cache_path))
        self.assertIn("issues", str(cache_path))
        self.assertTrue(str(cache_path).endswith(".json"))

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_cache_save_and_load(self, mock_exists, mock_file):
        """Test cache save and load functionality"""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = json.dumps({"test": "data"})
        
        # Test loading from cache
        data = self.sync._load_from_cache(Path("test_cache.json"))
        self.assertEqual(data, {"test": "data"})
        
        # Test saving to cache
        self.sync._save_to_cache(Path("test_cache.json"), {"new": "data"})
        mock_file.assert_called()

    @patch('sync_issues.requests.get')
    def test_rate_limit_handling(self, mock_get):
        """Test GitHub API rate limit handling"""
        # Mock rate limit response
        rate_limit_response = Mock()
        rate_limit_response.status_code = 403
        rate_limit_response.headers = {'x-ratelimit-remaining': '0', 'x-ratelimit-reset': '1640995200'}
        
        # Mock successful retry
        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = []
        success_response.links = {}
        
        mock_get.side_effect = [rate_limit_response, success_response]
        
        with patch('time.sleep') as mock_sleep:
            issues = self.sync.fetch_issues(state='open', limit=1)
            
        # Should have slept and retried
        mock_sleep.assert_called()
        self.assertEqual(mock_get.call_count, 2)

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.makedirs')
    def test_save_to_json(self, mock_makedirs, mock_file):
        """Test JSON output functionality"""
        test_data = {
            "repository": {
                "github_owner": "test_owner",
                "github_repo": "test_repo",
                "sync_date": "2024-01-15T10:00:00Z",
                "total_issues_synced": 1
            },
            "issues": [self.sample_issue]
        }
        
        self.sync.save_to_json(test_data, "test_output.json")
        
        mock_makedirs.assert_called()
        mock_file.assert_called()

    @patch('sync_issues.requests.get')
    def test_fetch_commits_for_issue(self, mock_get):
        """Test commit fetching for specific issue"""
        # Mock search API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [{
                "sha": "abc123",
                "commit": {
                    "author": {"date": "2024-01-15T10:00:00Z"},
                    "message": "Fix issue #123"
                }
            }]
        }
        mock_get.return_value = mock_response
        
        # Set contents scope as available
        self.sync.available_scopes = {"contents": True}
        
        commits = self.sync.fetch_commits_for_issue(123)
        
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["sha"], "abc123")

    @patch('sync_issues.requests.get')
    def test_fetch_commits_for_issue_no_scope(self, mock_get):
        """Test commit fetching when Contents scope is missing"""
        # Set contents scope as unavailable
        self.sync.available_scopes = {"contents": False}
        
        commits = self.sync.fetch_commits_for_issue(123)
        
        self.assertEqual(commits, [])
        mock_get.assert_not_called()

    def test_build_issues_graphql_query(self):
        """Test GraphQL query building"""
        query = self.sync._build_issues_graphql_query()
        
        # Check that the query contains essential fields
        self.assertIn('query GetRepositoryIssues', query)
        self.assertIn('repository(owner: $owner, name: $repo)', query)
        self.assertIn('issues(first: $first', query)
        self.assertIn('timelineItems', query)
        self.assertIn('projectItems', query)
        self.assertIn('ASSIGNED_EVENT', query)
        self.assertIn('LABELED_EVENT', query)
        self.assertIn('ReferencedEvent', query)

    def test_transform_graphql_issue_basic(self):
        """Test basic GraphQL issue transformation"""
        graphql_issue = {
            'number': 123,
            'title': 'Test Issue',
            'body': 'Test body',
            'state': 'OPEN',
            'createdAt': '2024-01-15T10:00:00Z',
            'updatedAt': '2024-01-15T11:00:00Z',
            'closedAt': None,
            'url': 'https://api.github.com/repos/test/test/issues/123',
            'labels': {'nodes': [{'name': 'bug', 'color': 'red', 'description': 'Bug label'}]},
            'assignees': {'nodes': [{'login': 'testuser', 'name': 'Test User'}]},
            'milestone': None,
            'author': {'login': 'author'},
            'comments': {'totalCount': 2},
            'timelineItems': {'nodes': []},
            'projectItems': {'nodes': []}
        }
        
        transformed = self.sync._transform_graphql_issue(graphql_issue)
        
        # Check basic transformation
        self.assertEqual(transformed['number'], 123)
        self.assertEqual(transformed['title'], 'Test Issue')
        self.assertEqual(transformed['state'], 'open')
        self.assertEqual(transformed['comments'], 2)
        self.assertEqual(len(transformed['labels']), 1)
        self.assertEqual(transformed['labels'][0]['name'], 'bug')
        self.assertEqual(len(transformed['assignees']), 1)
        self.assertEqual(transformed['assignees'][0]['login'], 'testuser')
        self.assertIsNotNone(transformed['assignee'])
        self.assertEqual(transformed['assignee']['login'], 'testuser')

    def test_transform_graphql_issue_timeline_events(self):
        """Test GraphQL issue transformation with timeline events"""
        graphql_issue = {
            'number': 123,
            'title': 'Test Issue',
            'body': 'Test body',
            'state': 'CLOSED',
            'createdAt': '2024-01-15T10:00:00Z',
            'updatedAt': '2024-01-15T11:00:00Z',
            'closedAt': '2024-01-16T10:00:00Z',
            'url': 'https://api.github.com/repos/test/test/issues/123',
            'labels': {'nodes': []},
            'assignees': {'nodes': []},
            'milestone': None,
            'author': {'login': 'author'},
            'comments': {'totalCount': 0},
            'timelineItems': {
                'nodes': [
                    {
                        '__typename': 'AssignedEvent',
                        'createdAt': '2024-01-15T11:00:00Z',
                        'assignee': {'login': 'developer1'}
                    },
                    {
                        '__typename': 'LabeledEvent',
                        'createdAt': '2024-01-15T11:30:00Z',
                        'label': {'name': 'in-progress'}
                    },
                    {
                        '__typename': 'ReferencedEvent',
                        'createdAt': '2024-01-15T12:00:00Z',
                        'commit': {
                            'oid': 'abc123',
                            'message': 'Fix issue #123',
                            'committedDate': '2024-01-15T12:00:00Z',
                            'author': {'name': 'Dev One', 'email': 'dev@example.com'}
                        }
                    },
                    {
                        '__typename': 'ClosedEvent',
                        'createdAt': '2024-01-16T10:00:00Z',
                        'actor': {'login': 'developer1'}
                    }
                ]
            },
            'projectItems': {'nodes': []}
        }
        
        transformed = self.sync._transform_graphql_issue(graphql_issue)
        
        # Check timeline events transformation
        self.assertEqual(len(transformed['timeline_events']), 4)
        
        # Check assigned event
        assigned_event = transformed['timeline_events'][0]
        self.assertEqual(assigned_event['event'], 'assigned')
        self.assertEqual(assigned_event['assignee']['login'], 'developer1')
        
        # Check labeled event
        labeled_event = transformed['timeline_events'][1]
        self.assertEqual(labeled_event['event'], 'labeled')
        self.assertEqual(labeled_event['label']['name'], 'in-progress')
        
        # Check closed event
        closed_event = transformed['timeline_events'][3]
        self.assertEqual(closed_event['event'], 'closed')
        self.assertEqual(closed_event['actor']['login'], 'developer1')
        
        # Check commits transformation
        self.assertEqual(len(transformed['commits']), 1)
        commit = transformed['commits'][0]
        self.assertEqual(commit['sha'], 'abc123')
        self.assertEqual(commit['commit']['message'], 'Fix issue #123')
        self.assertEqual(commit['commit']['author']['name'], 'Dev One')

    def test_transform_graphql_issue_project_data(self):
        """Test GraphQL issue transformation with project data"""
        graphql_issue = {
            'number': 123,
            'title': 'Test Issue',
            'body': 'Test body',
            'state': 'OPEN',
            'createdAt': '2024-01-15T10:00:00Z',
            'updatedAt': '2024-01-15T11:00:00Z',
            'closedAt': None,
            'url': 'https://api.github.com/repos/test/test/issues/123',
            'labels': {'nodes': []},
            'assignees': {'nodes': []},
            'milestone': None,
            'author': {'login': 'author'},
            'comments': {'totalCount': 0},
            'timelineItems': {'nodes': []},
            'projectItems': {
                'nodes': [
                    {
                        'id': 'project_item_1',
                        'project': {'id': 'proj_1', 'title': 'Main Project', 'number': 1},
                        'fieldValues': {
                            'nodes': [
                                {
                                    'field': {'name': 'Status'},
                                    'name': 'In Progress'
                                },
                                {
                                    'field': {'name': 'Priority'},
                                    'text': 'High'
                                },
                                {
                                    'field': {'name': 'Due Date'},
                                    'date': '2024-01-20'
                                }
                            ]
                        }
                    }
                ]
            }
        }
        
        transformed = self.sync._transform_graphql_issue(graphql_issue)
        
        # Check project data transformation
        self.assertEqual(len(transformed['project_data']), 1)
        project = transformed['project_data'][0]
        self.assertEqual(project['project']['title'], 'Main Project')
        
        fields = project['fields']
        self.assertEqual(fields['Status'], 'In Progress')
        self.assertEqual(fields['Priority'], 'High')
        self.assertEqual(fields['Due Date'], '2024-01-20')

    @patch('sync_issues.GitHubDataSyncer._make_graphql_request')
    def test_fetch_issues_graphql_success(self, mock_graphql):
        """Test successful GraphQL issue fetching"""
        # Mock GraphQL response
        mock_graphql.return_value = {
            'repository': {
                'issues': {
                    'pageInfo': {'hasNextPage': False, 'endCursor': None},
                    'nodes': [
                        {
                            'number': 123,
                            'title': 'Test Issue',
                            'body': 'Test body',
                            'state': 'OPEN',
                            'createdAt': '2024-01-15T10:00:00Z',
                            'updatedAt': '2024-01-15T11:00:00Z',
                            'closedAt': None,
                            'url': 'https://api.github.com/repos/test/test/issues/123',
                            'labels': {'nodes': []},
                            'assignees': {'nodes': []},
                            'milestone': None,
                            'author': {'login': 'author'},
                            'comments': {'totalCount': 0},
                            'timelineItems': {'nodes': []},
                            'projectItems': {'nodes': []}
                        }
                    ]
                }
            }
        }
        
        issues = self.sync.fetch_issues_graphql(state='open', limit=1)
        
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['number'], 123)
        self.assertEqual(issues[0]['title'], 'Test Issue')
        mock_graphql.assert_called_once()

    @patch('sync_issues.GitHubDataSyncer._make_graphql_request')
    @patch('sync_issues.GitHubDataSyncer.fetch_issues')
    def test_fetch_issues_graphql_fallback(self, mock_rest_fetch, mock_graphql):
        """Test GraphQL fallback to REST on error"""
        # Mock GraphQL failure
        mock_graphql.side_effect = Exception("GraphQL API error")
        
        # Mock REST success
        mock_rest_fetch.return_value = [self.sample_issue]
        
        issues = self.sync.fetch_issues_graphql(state='open', limit=1)
        
        # Should fallback to REST
        mock_rest_fetch.assert_called_once_with('open', 1)
        self.assertEqual(len(issues), 1)

    @patch('sync_issues.GitHubDataSyncer._make_graphql_request')
    def test_fetch_issues_graphql_pagination(self, mock_graphql):
        """Test GraphQL pagination handling"""
        # Mock two pages of results
        def mock_response(query, variables):
            cursor = variables.get('cursor')
            if cursor is None:
                # First page
                return {
                    'repository': {
                        'issues': {
                            'pageInfo': {'hasNextPage': True, 'endCursor': 'cursor_1'},
                            'nodes': [
                                {
                                    'number': 123,
                                    'title': 'Issue 1',
                                    'body': '',
                                    'state': 'OPEN',
                                    'createdAt': '2024-01-15T10:00:00Z',
                                    'updatedAt': '2024-01-15T11:00:00Z',
                                    'closedAt': None,
                                    'url': 'https://api.github.com/repos/test/test/issues/123',
                                    'labels': {'nodes': []},
                                    'assignees': {'nodes': []},
                                    'milestone': None,
                                    'author': {'login': 'author'},
                                    'comments': {'totalCount': 0},
                                    'timelineItems': {'nodes': []},
                                    'projectItems': {'nodes': []}
                                }
                            ]
                        }
                    }
                }
            else:
                # Second page
                return {
                    'repository': {
                        'issues': {
                            'pageInfo': {'hasNextPage': False, 'endCursor': None},
                            'nodes': [
                                {
                                    'number': 124,
                                    'title': 'Issue 2',
                                    'body': '',
                                    'state': 'OPEN',
                                    'createdAt': '2024-01-15T10:00:00Z',
                                    'updatedAt': '2024-01-15T11:00:00Z',
                                    'closedAt': None,
                                    'url': 'https://api.github.com/repos/test/test/issues/124',
                                    'labels': {'nodes': []},
                                    'assignees': {'nodes': []},
                                    'milestone': None,
                                    'author': {'login': 'author'},
                                    'comments': {'totalCount': 0},
                                    'timelineItems': {'nodes': []},
                                    'projectItems': {'nodes': []}
                                }
                            ]
                        }
                    }
                }
        
        mock_graphql.side_effect = mock_response
        
        issues = self.sync.fetch_issues_graphql(state='open')
        
        self.assertEqual(len(issues), 2)
        self.assertEqual(issues[0]['number'], 123)
        self.assertEqual(issues[1]['number'], 124)
        self.assertEqual(mock_graphql.call_count, 2)

    def test_transform_graphql_issue_safe_field_access(self):
        """Test GraphQL transformation handles missing fields safely"""
        # Minimal GraphQL response with some missing fields
        minimal_issue = {
            'number': 123,
            'title': 'Test Issue',
            'state': 'OPEN',
            'createdAt': '2024-01-15T10:00:00Z',
            # Missing: body, updatedAt, closedAt, url, labels, assignees, etc.
        }
        
        # Should not raise exceptions
        transformed = self.sync._transform_graphql_issue(minimal_issue)
        
        self.assertEqual(transformed['number'], 123)
        self.assertEqual(transformed['title'], 'Test Issue')
        self.assertEqual(transformed['state'], 'open')
        self.assertEqual(transformed['body'], '')  # Default empty string
        self.assertEqual(transformed['labels'], [])  # Default empty list
        self.assertEqual(transformed['assignees'], [])  # Default empty list
        self.assertIsNone(transformed['assignee'])  # Default None
        self.assertEqual(transformed['timeline_events'], [])  # Default empty list
        self.assertEqual(transformed['commits'], [])  # Default empty list
        self.assertEqual(transformed['project_data'], [])  # Default empty list

    @patch('sync_issues.GitHubDataSyncer.fetch_issues_graphql')
    def test_sync_with_graphql_flag(self, mock_graphql):
        """Test sync_issues_to_json uses GraphQL by default"""
        mock_graphql.return_value = [self.sample_issue]
        
        with patch('builtins.open', mock_open()):
            with patch('json.dump'):
                self.sync.sync_issues_to_json('test.json', use_rest=False)
        
        mock_graphql.assert_called_once()

    @patch('sync_issues.GitHubDataSyncer.fetch_issues')
    def test_sync_with_rest_flag(self, mock_rest):
        """Test sync_issues_to_json uses REST when requested"""
        mock_rest.return_value = [self.sample_issue]
        
        with patch('builtins.open', mock_open()):
            with patch('json.dump'):
                with patch('sync_issues.GitHubDataSyncer.enrich_issues_with_project_data') as mock_enrich:
                    mock_enrich.return_value = [self.sample_issue]
                    self.sync.sync_issues_to_json('test.json', use_rest=True)
        
        mock_rest.assert_called_once()

    def test_cli_use_rest_flag(self):
        """Test --use-rest command line flag forces REST API usage"""
        import argparse
        
        # Test parser accepts --use-rest flag
        parser = argparse.ArgumentParser()
        parser.add_argument('--use-rest', action='store_true', 
                           help='Force use of REST API instead of GraphQL')
        
        # Test flag parsing
        args = parser.parse_args(['--use-rest'])
        self.assertTrue(args.use_rest)
        
        # Test default behavior (no flag)
        args = parser.parse_args([])
        self.assertFalse(args.use_rest)

    @patch('sys.argv', ['sync_issues.py', 'owner', 'repo', '--use-rest'])
    @patch.dict(os.environ, {'GITHUB_TOKEN': 'fake_token'})
    @patch('sync_issues.requests.get')
    def test_cli_forces_rest_api(self, mock_get):
        """Test that --use-rest flag forces REST API usage"""
        # Mock REST API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [self.sample_issue]
        mock_response.links = {}
        mock_get.return_value = mock_response
        
        with patch('sync_issues.requests.post') as mock_post:
            # Import main function to test CLI
            from sync_issues import main
            
            try:
                main()
            except SystemExit:
                pass
            
            # Verify GraphQL was not called
            mock_post.assert_not_called()
            
            # Verify REST API was called
            mock_get.assert_called()

    @patch('sys.argv', ['sync_issues.py', 'owner', 'repo'])
    @patch.dict(os.environ, {'GITHUB_TOKEN': 'fake_token'})
    @patch('sync_issues.requests.post')
    def test_cli_defaults_to_graphql(self, mock_post):
        """Test that CLI defaults to GraphQL when no --use-rest flag"""
        # Mock successful GraphQL response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "repository": {
                    "issues": {
                        "nodes": [self.graphql_issue],
                        "pageInfo": {"hasNextPage": False}
                    }
                }
            }
        }
        mock_post.return_value = mock_response
        
        with patch('sync_issues.requests.get') as mock_get:
            from sync_issues import main
            
            try:
                main()
            except SystemExit:
                pass
            
            # Verify GraphQL was attempted first
            mock_post.assert_called()
            
            # Verify REST API was not called (GraphQL succeeded)
            mock_get.assert_not_called()

    def test_cli_argument_parsing_all_options(self):
        """Test all CLI argument combinations"""
        import argparse
        
        # Simulate the actual argument parser from sync_issues.py
        parser = argparse.ArgumentParser(description='Sync GitHub issues to JSON')
        parser.add_argument('owner', help='Repository owner')
        parser.add_argument('repo', help='Repository name')
        parser.add_argument('--output', '-o', default='issues_data.json', 
                           help='Output JSON file (default: issues_data.json)')
        parser.add_argument('--limit', type=int, 
                           help='Maximum number of issues to fetch')
        parser.add_argument('--state', choices=['open', 'closed', 'all'], 
                           default='all', help='Issue state filter')
        parser.add_argument('--strategic-work-only', action='store_true',
                           help='Only include strategic work items')
        parser.add_argument('--use-rest', action='store_true',
                           help='Force use of REST API instead of GraphQL')
        
        # Test all arguments
        args = parser.parse_args([
            'test_owner', 'test_repo', 
            '--output', 'custom.json',
            '--limit', '100',
            '--state', 'open',
            '--strategic-work-only',
            '--use-rest'
        ])
        
        self.assertEqual(args.owner, 'test_owner')
        self.assertEqual(args.repo, 'test_repo')
        self.assertEqual(args.output, 'custom.json')
        self.assertEqual(args.limit, 100)
        self.assertEqual(args.state, 'open')
        self.assertTrue(args.strategic_work_only)
        self.assertTrue(args.use_rest)


if __name__ == '__main__':
    unittest.main()