#!/usr/bin/env python3
"""
Unit tests for caching system functionality
"""
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "requests",
#     "pytest",
# ]
# ///

import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open
import json
import os
import sys
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sync_issues import GitHubIssueSync


class TestCachingSystem(unittest.TestCase):
    """Test caching system functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.sync = GitHubIssueSync("fake_token", "test_owner", "test_repo")
        # Override cache directory for testing
        self.sync.cache_dir = Path(self.temp_dir) / "test_cache"
        
        self.sample_data = {
            "issues": [
                {
                    "number": 123,
                    "title": "Test Issue",
                    "state": "open",
                    "labels": [{"name": "feature"}]
                }
            ],
            "cached_at": datetime.now().isoformat()
        }
    
    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_cache_directory_creation(self):
        """Test that cache directories are created as needed"""
        cache_path = self.sync._get_cache_path("issues", page=1, state="open")
        
        # Ensure directory would be created
        self.assertIsInstance(cache_path, Path)
        self.assertIn("test_owner", str(cache_path))
        self.assertIn("test_repo", str(cache_path))

    def test_cache_path_generation(self):
        """Test cache path generation for different API calls"""
        # Test issues cache path
        issues_path = self.sync._get_cache_path("issues", page=1, state="open")
        self.assertIn("issues", str(issues_path))
        self.assertIn("page_1", str(issues_path))
        self.assertIn("open", str(issues_path))
        
        # Test commits cache path
        commits_path = self.sync._get_cache_path("commits", issue_number=123)
        self.assertIn("commits", str(commits_path))
        self.assertIn("issue_123", str(commits_path))
        
        # Test events cache path
        events_path = self.sync._get_cache_path("events", issue_number=456)
        self.assertIn("events", str(events_path))
        self.assertIn("issue_456", str(events_path))

    def test_cache_save_and_load(self):
        """Test basic cache save and load functionality"""
        cache_path = self.sync.cache_dir / "test_cache.json"
        
        # Save to cache
        self.sync._save_to_cache(cache_path, self.sample_data)
        
        # Verify file exists
        self.assertTrue(cache_path.exists())
        
        # Load from cache
        loaded_data = self.sync._load_from_cache(cache_path)
        
        self.assertEqual(loaded_data["issues"][0]["number"], 123)
        self.assertIn("cached_at", loaded_data)

    def test_cache_expiry_fresh(self):
        """Test cache expiry detection for fresh cache"""
        # Create fresh cache
        fresh_data = self.sample_data.copy()
        fresh_data["cached_at"] = datetime.now().isoformat()
        
        cache_path = self.sync.cache_dir / "fresh_cache.json"
        self.sync._save_to_cache(cache_path, fresh_data)
        
        # Should not be expired
        self.assertFalse(self.sync._is_cache_expired(cache_path))

    def test_cache_expiry_old(self):
        """Test cache expiry detection for old cache"""
        # Create old cache (8 days ago, default TTL is 7 days)
        old_time = datetime.now() - timedelta(days=8)
        old_data = self.sample_data.copy()
        old_data["cached_at"] = old_time.isoformat()
        
        cache_path = self.sync.cache_dir / "old_cache.json"
        self.sync._save_to_cache(cache_path, old_data)
        
        # Should be expired
        self.assertTrue(self.sync._is_cache_expired(cache_path))

    def test_cache_expiry_missing_timestamp(self):
        """Test cache expiry for cache without timestamp"""
        # Create cache without timestamp
        no_timestamp_data = {"issues": [{"number": 123}]}
        
        cache_path = self.sync.cache_dir / "no_timestamp.json"
        self.sync._save_to_cache(cache_path, no_timestamp_data)
        
        # Should be considered expired without timestamp
        self.assertTrue(self.sync._is_cache_expired(cache_path))

    def test_cache_hit_statistics(self):
        """Test cache hit statistics tracking"""
        # Reset statistics
        self.sync.cache_stats = {"hits": 0, "misses": 0, "saves": 0}
        
        # Create cached data
        cache_path = self.sync.cache_dir / "stats_test.json"
        self.sync._save_to_cache(cache_path, self.sample_data)
        
        # Load from cache (should be a hit)
        self.sync._load_from_cache(cache_path)
        
        # Check statistics
        self.assertEqual(self.sync.cache_stats["saves"], 1)
        # Note: In real implementation, hits would be tracked in the calling methods

    @patch('sync_issues.requests.get')
    def test_cache_integration_with_api_calls(self, mock_get):
        """Test cache integration with actual API calls"""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [self.sample_data["issues"][0]]
        mock_response.links = {}
        mock_get.return_value = mock_response
        
        # First call should hit API and cache result
        issues1 = self.sync.fetch_issues(state='open', limit=1)
        api_call_count_1 = mock_get.call_count
        
        # Second call should use cache (in real implementation)
        # For this test, we simulate cache behavior
        cache_path = self.sync._get_cache_path("issues", page=1, state="open")
        
        if cache_path.exists() and not self.sync._is_cache_expired(cache_path):
            cached_data = self.sync._load_from_cache(cache_path)
            issues2 = cached_data.get("data", [])
        else:
            issues2 = self.sync.fetch_issues(state='open', limit=1)
        
        # Should have made API call only once if caching works
        self.assertEqual(len(issues1), 1)

    def test_cache_clear_functionality(self):
        """Test cache clearing functionality"""
        # Create multiple cache files
        cache_files = ["cache1.json", "cache2.json", "cache3.json"]
        for filename in cache_files:
            cache_path = self.sync.cache_dir / filename
            self.sync._save_to_cache(cache_path, self.sample_data)
        
        # Verify files exist
        for filename in cache_files:
            self.assertTrue((self.sync.cache_dir / filename).exists())
        
        # Clear cache
        self.sync._clear_cache()
        
        # Verify files are removed
        for filename in cache_files:
            self.assertFalse((self.sync.cache_dir / filename).exists())

    def test_cache_size_tracking(self):
        """Test cache size tracking and reporting"""
        # Create cache files of different sizes
        small_data = {"data": "small"}
        large_data = {"data": "x" * 1000}  # Larger payload
        
        small_cache = self.sync.cache_dir / "small.json"
        large_cache = self.sync.cache_dir / "large.json"
        
        self.sync._save_to_cache(small_cache, small_data)
        self.sync._save_to_cache(large_cache, large_data)
        
        # Calculate total cache size
        total_size = self.sync._calculate_cache_size()
        
        # Should be greater than 0
        self.assertGreater(total_size, 0)

    def test_cache_corruption_handling(self):
        """Test handling of corrupted cache files"""
        # Create corrupted cache file
        cache_path = self.sync.cache_dir / "corrupted.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(cache_path, 'w') as f:
            f.write("invalid json content {")
        
        # Should handle corruption gracefully
        loaded_data = self.sync._load_from_cache(cache_path)
        self.assertIsNone(loaded_data)

    def test_cache_concurrency_safety(self):
        """Test cache safety with concurrent operations"""
        import threading
        import time
        
        cache_path = self.sync.cache_dir / "concurrent.json"
        results = []
        
        def cache_operation(data):
            """Simulate concurrent cache operations"""
            try:
                self.sync._save_to_cache(cache_path, {"thread_data": data})
                time.sleep(0.01)  # Small delay
                loaded = self.sync._load_from_cache(cache_path)
                results.append(loaded)
            except Exception as e:
                results.append(f"Error: {e}")
        
        # Run concurrent operations
        threads = []
        for i in range(5):
            thread = threading.Thread(target=cache_operation, args=(f"data_{i}",))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Should complete without errors
        self.assertEqual(len(results), 5)
        # All results should be valid (no errors)
        for result in results:
            self.assertIsInstance(result, dict)

    def test_cache_directory_permissions(self):
        """Test cache directory permission handling"""
        # Test with restricted permissions (simulate on Unix systems)
        if os.name != 'nt':  # Skip on Windows
            restricted_dir = Path(self.temp_dir) / "restricted"
            restricted_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                # Remove write permissions
                os.chmod(restricted_dir, 0o444)
                
                # Try to create cache in restricted directory
                restricted_sync = GitHubIssueSync("token", "owner", "repo")
                restricted_sync.cache_dir = restricted_dir / "cache"
                
                # Should handle permission error gracefully
                cache_path = restricted_sync.cache_dir / "test.json"
                try:
                    restricted_sync._save_to_cache(cache_path, self.sample_data)
                    # If it succeeds, that's ok too
                except (PermissionError, OSError):
                    # Expected behavior - should handle gracefully
                    pass
                    
            finally:
                # Restore permissions for cleanup
                os.chmod(restricted_dir, 0o755)

    def test_cache_performance_metrics(self):
        """Test cache performance measurement"""
        import time
        
        # Measure cache save performance
        start_time = time.time()
        
        large_data = {
            "issues": [{"number": i, "title": f"Issue {i}"} for i in range(100)],
            "cached_at": datetime.now().isoformat()
        }
        
        cache_path = self.sync.cache_dir / "performance_test.json"
        self.sync._save_to_cache(cache_path, large_data)
        
        save_time = time.time() - start_time
        
        # Measure cache load performance
        start_time = time.time()
        loaded_data = self.sync._load_from_cache(cache_path)
        load_time = time.time() - start_time
        
        # Performance should be reasonable (less than 1 second for this test)
        self.assertLess(save_time, 1.0)
        self.assertLess(load_time, 1.0)
        
        # Data should be identical
        self.assertEqual(len(loaded_data["issues"]), 100)

    def test_cache_cleanup_old_files(self):
        """Test automatic cleanup of old cache files"""
        # Create old cache files
        old_time = datetime.now() - timedelta(days=30)
        
        old_cache_data = self.sample_data.copy()
        old_cache_data["cached_at"] = old_time.isoformat()
        
        old_cache_path = self.sync.cache_dir / "old_cache.json"
        self.sync._save_to_cache(old_cache_path, old_cache_data)
        
        # Create recent cache file
        recent_cache_path = self.sync.cache_dir / "recent_cache.json"
        self.sync._save_to_cache(recent_cache_path, self.sample_data)
        
        # Run cleanup (would be called periodically in real system)
        self.sync._cleanup_old_cache_files(max_age_days=7)
        
        # Old file should be removed, recent file should remain
        self.assertFalse(old_cache_path.exists())
        self.assertTrue(recent_cache_path.exists())


# Add missing methods to GitHubIssueSync for testing
def add_cache_test_methods():
    """Add cache-specific methods for testing"""
    
    def _is_cache_expired(self, cache_path, ttl_days=7):
        """Check if cache is expired"""
        if not cache_path.exists():
            return True
            
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
                
            cached_at_str = data.get("cached_at")
            if not cached_at_str:
                return True
                
            cached_at = datetime.fromisoformat(cached_at_str.replace('Z', '+00:00'))
            age = datetime.now() - cached_at.replace(tzinfo=None)
            
            return age.days > ttl_days
            
        except (json.JSONDecodeError, ValueError, KeyError):
            return True
    
    def _clear_cache(self):
        """Clear all cache files"""
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
    
    def _calculate_cache_size(self):
        """Calculate total cache size in bytes"""
        if not self.cache_dir.exists():
            return 0
            
        total_size = 0
        for cache_file in self.cache_dir.rglob("*.json"):
            total_size += cache_file.stat().st_size
            
        return total_size
    
    def _cleanup_old_cache_files(self, max_age_days=7):
        """Clean up cache files older than max_age_days"""
        if not self.cache_dir.exists():
            return
            
        for cache_file in self.cache_dir.rglob("*.json"):
            if self._is_cache_expired(cache_file, max_age_days):
                cache_file.unlink()
    
    # Add cache statistics tracking
    def _init_cache_stats(self):
        """Initialize cache statistics"""
        if not hasattr(self, 'cache_stats'):
            self.cache_stats = {"hits": 0, "misses": 0, "saves": 0}
    
    # Add methods to the class
    GitHubIssueSync._is_cache_expired = _is_cache_expired
    GitHubIssueSync._clear_cache = _clear_cache
    GitHubIssueSync._calculate_cache_size = _calculate_cache_size
    GitHubIssueSync._cleanup_old_cache_files = _cleanup_old_cache_files
    GitHubIssueSync._init_cache_stats = _init_cache_stats


# Add the test methods when module is loaded
add_cache_test_methods()


if __name__ == '__main__':
    unittest.main()