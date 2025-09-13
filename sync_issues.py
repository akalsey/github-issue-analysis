#!/usr/bin/env python3
"""
GitHub Issues Data Sync

Fetches GitHub issues data, caches API responses, and saves comprehensive JSON data
for analysis by cycle_time.py. This script handles all GitHub API interactions.
"""
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "requests",
#     "python-dotenv",
#     "rich",
# ]
# ///

import os
import json
import time
import requests
import hashlib
import pickle
import signal
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv
import argparse

try:
    from rich.console import Console
    from rich.text import Text
    from rich.live import Live
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

class InterruptedException(Exception):
    """Exception raised when user interrupts the process"""
    pass

def graphql_retry(max_retries=3, base_delay=1.0, max_delay=60.0, backoff_factor=2.0):
    """
    Decorator for GraphQL requests with exponential backoff retry logic
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds  
        backoff_factor: Multiplier for exponential backoff
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except Exception as e:
                    last_exception = e
                    error_message = str(e).lower()
                    
                    # Don't retry on non-recoverable errors
                    if any(err in error_message for err in [
                        'unauthorized', 'forbidden', 'not found', 
                        'bad credentials', 'validation failed'
                    ]):
                        raise e
                    
                    # This is the last attempt
                    if attempt == max_retries:
                        raise e
                    
                    # Calculate delay with jitter
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    jitter = random.uniform(0.1, 0.3) * delay
                    total_delay = delay + jitter
                    
                    print(f"⚠️  GraphQL request failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
                    print(f"🔄 Retrying in {total_delay:.1f} seconds...")
                    time.sleep(total_delay)
            
            # This should never be reached, but just in case
            raise last_exception
            
        return wrapper
    return decorator

class StatusDisplay:
    """Handle status updates with rich UI or fallback to simple print"""
    
    def __init__(self):
        self.console = Console() if RICH_AVAILABLE else None
        self.live = None
        self.current_status = ""
        
    def start(self, initial_message: str = "Starting..."):
        """Start the status display"""
        if RICH_AVAILABLE:
            self.current_status = initial_message
            text = Text(initial_message, style="cyan")
            self.live = Live(text, console=self.console, refresh_per_second=4)
            self.live.start()
        else:
            print(initial_message)
    
    def update(self, message: str, style: str = "cyan"):
        """Update the status message"""
        self.current_status = message
        if self.live:
            text = Text(message, style=style)
            self.live.update(text)
        else:
            # Simple fallback - overwrite the line
            print(f"\r{message}", end="", flush=True)
    
    def stop(self, final_message: str = None):
        """Stop the status display"""
        if self.live:
            self.live.stop()
            if final_message:
                self.console.print(final_message)
        else:
            if final_message:
                print(f"\r{final_message}")
            else:
                print()  # New line to finish the status line
    
    def print(self, message: str, style: str = None):
        """Print a message without disrupting status display"""
        if self.console:
            if self.live:
                self.live.stop()
                self.console.print(message, style=style)
                if self.current_status:
                    text = Text(self.current_status, style="cyan")
                    self.live = Live(text, console=self.console, refresh_per_second=4)
                    self.live.start()
            else:
                self.console.print(message, style=style)
        else:
            print(f"\r{message}")  # Clear current line and print message

def is_strategic_work(issue: Dict) -> bool:
    """
    Filter for strategic business value work vs operational maintenance.
    
    INCLUDE: product work, features, customer issues, epics
    EXCLUDE: chores, deployments, infrastructure, compliance tasks
    """
    # Extract just the label names, not the full objects
    labels = issue.get('labels', [])
    if isinstance(labels, list) and labels and isinstance(labels[0], dict):
        # GraphQL/REST format: list of label objects
        label_names = [label.get('name', '') for label in labels]
    else:
        # Simple format: list of strings or other format
        label_names = labels
    
    labels_str = ' '.join(label_names).lower()
    
    # INCLUDE: Strategic business value work
    include_patterns = [
        'product/',      # All product work (voice, messaging, ai, video, etc.)
        'epic',          # Major strategic initiatives
        'area/customer', # Customer-impacting issues
        'type/feature',  # New functionality/capabilities  
        'type/bug',      # Customer-affecting defects
    ]
    
    # EXCLUDE: Operational/maintenance work
    exclude_patterns = [
        'type/chore',     # Maintenance, deployments, cleanup
        'dev/iac',        # Infrastructure as code
        'deploy/',        # Deployment tasks
        'compliance',     # Regulatory/security tasks
        'tech-backlog',   # Technical debt
        'status/',        # Workflow states, not deliverables
        'area/internal',  # Internal tooling
    ]
    
    # Check for exclusion patterns first (higher priority)
    for pattern in exclude_patterns:
        if pattern in labels_str:
            return False
    
    # Check for inclusion patterns
    for pattern in include_patterns:
        if pattern in labels_str:
            return True
    
    # Default: exclude unlabeled or unclear work
    return False

class GitHubDataSyncer:
    """Sync GitHub repository data to JSON files"""
    
    def __init__(self, token: str, owner: str, repo: str):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        })
        
        # Separate session for GraphQL API (Projects v2)
        self.graphql_session = requests.Session()
        self.graphql_session.headers.update({
            'Authorization': f'bearer {token}',
            'Content-Type': 'application/json'
        })
        self.commit_search_available = None  # Will be tested on first use
        self.projects_available = None  # Will be tested on first use
        self.status = StatusDisplay()
        self.interrupted = False  # Shared interrupt flag
        self.original_signal_handler = None
        
        # Cache setup (must be before scope testing since GraphQL requests use cache)
        self.cache_dir = Path(f".cache/{owner}/{repo}")
        cache_existed = self.cache_dir.exists()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_expiry_days = 7  # 1 week
        
        # Test token capabilities on initialization
        self.available_scopes = self._test_token_scopes()
        
        # Inform user about cache status
        if not cache_existed:
            # New cache directory created
            pass  # Don't show message for new cache - will be shown when first cache hit occurs
        else:
            # Using existing cache
            cache_files = list(self.cache_dir.glob("**/*.cache"))
            if cache_files:
                # Show cache info immediately if we have existing cache
                print(f"💾 Using cache directory: {self.cache_dir.name} ({len(cache_files)} cached files)")
            else:
                print(f"💾 Cache directory exists but empty: {self.cache_dir.name}")
    
    def _test_token_scopes(self) -> Dict[str, bool]:
        """Test what scopes/capabilities are available with current token"""
        scopes = {
            'issues': True,  # Assume issues are always available (basic requirement)
            'contents': False,
            'pull_requests': False,
            'projects': False
        }
        
        try:
            # Test basic repo access (should work with any valid token)
            url = f"{self.base_url}/repos/{self.owner}/{self.repo}"
            response = self.session.get(url)
            
            if response.status_code == 404:
                print(f"⚠️  Repository {self.owner}/{self.repo} not found or not accessible")
                return scopes
            elif response.status_code == 403:
                print(f"⚠️  Access forbidden to {self.owner}/{self.repo} - check token permissions")
                return scopes
            elif response.status_code != 200:
                print(f"⚠️  Unexpected response ({response.status_code}) testing repository access")
                return scopes
            
            # Test contents scope (needed for commit search)
            try:
                url = f"{self.base_url}/repos/{self.owner}/{self.repo}/contents"
                response = self.session.get(url)
                if response.status_code in [200, 404]:  # 404 is OK (empty repo)
                    scopes['contents'] = True
            except:
                pass
            
            # Test pull requests scope  
            try:
                url = f"{self.base_url}/repos/{self.owner}/{self.repo}/pulls"
                params = {'state': 'all', 'per_page': 1}
                response = self.session.get(url, params=params)
                if response.status_code == 200:
                    scopes['pull_requests'] = True
            except:
                pass
            
            # Test projects scope (GraphQL)
            try:
                test_query = """
                query($owner: String!, $repo: String!) {
                  repository(owner: $owner, name: $repo) {
                    name
                  }
                }
                """
                result = self._make_graphql_request(test_query, {"owner": self.owner, "repo": self.repo})
                if result and 'repository' in result:
                    scopes['projects'] = True
            except:
                pass
            
            # Show scope status
            print(f"🔑 Token capabilities detected:")
            print(f"   ✅ Issues: {'Available' if scopes['issues'] else 'Not available'}")
            print(f"   {'✅' if scopes['contents'] else '❌'} Contents: {'Available' if scopes['contents'] else 'Not available (commit search disabled)'}")
            print(f"   {'✅' if scopes['pull_requests'] else '❌'} Pull Requests: {'Available' if scopes['pull_requests'] else 'Not available'}")
            print(f"   {'✅' if scopes['projects'] else '❌'} Projects: {'Available' if scopes['projects'] else 'Not available'}")
            
        except Exception as e:
            print(f"⚠️  Error testing token scopes: {e}")
        
        return scopes
        
    def _get_cache_key(self, url: str, params: Dict = None) -> str:
        """Generate a cache key for a request"""
        # Create a unique key based on URL and parameters
        # Sort params to ensure consistent key generation
        params_str = ""
        if params:
            sorted_params = sorted(params.items())
            params_str = "&".join(f"{k}={v}" for k, v in sorted_params)
        key_data = f"{url}?{params_str}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _get_cache_file(self, cache_key: str) -> Path:
        """Get the cache file path for a given key with subdirectory structure"""
        # Create subdirectory based on first two characters to avoid OS file limits
        subdir = cache_key[:2]
        cache_subdir = self.cache_dir / subdir
        cache_subdir.mkdir(exist_ok=True)  # Create subdirectory if it doesn't exist
        return cache_subdir / f"{cache_key}.cache"
    
    def _is_cache_valid(self, cache_file: Path) -> bool:
        """Check if cache file exists and is not expired"""
        if not cache_file.exists():
            return False
        
        # Check if cache is older than expiry time
        cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        return cache_age.days < self.cache_expiry_days
    
    def _save_to_cache(self, cache_key: str, data: Dict):
        """Save data to cache"""
        try:
            cache_file = self._get_cache_file(cache_key)
            with open(cache_file, 'wb') as f:
                pickle.dump(data, f)
            # Count saves for statistics but don't spam output
            if not hasattr(self, '_cache_save_count'):
                self._cache_save_count = 0
            self._cache_save_count += 1
        except Exception as e:
            # Cache failures shouldn't break the application - only show critical errors
            if not hasattr(self, '_cache_error_shown'):
                self._cache_error_shown = True
                self.status.print(f"⚠️  Cache save failed: {e}", style="yellow")
    
    def _load_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Load data from cache"""
        try:
            cache_file = self._get_cache_file(cache_key)
            if self._is_cache_valid(cache_file):
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)
                # Count loads for statistics but don't spam output
                if not hasattr(self, '_cache_load_count'):
                    self._cache_load_count = 0
                self._cache_load_count += 1
                return data
        except Exception as e:
            # Only show cache errors once to avoid spam
            if not hasattr(self, '_cache_load_error_shown'):
                self._cache_load_error_shown = True
                self.status.print(f"⚠️  Cache load failed: {e}", style="yellow")
        return None
    
    def clear_cache(self):
        """Clear all cached data for this repository"""
        try:
            import shutil
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(exist_ok=True)
                print(f"✅ Cache cleared for {self.owner}/{self.repo}")
            else:
                print(f"ℹ️  No cache found for {self.owner}/{self.repo}")
        except Exception as e:
            print(f"❌ Failed to clear cache: {e}")
    
    @staticmethod
    def clear_cache_for_repo(owner: str, repo: str):
        """Static method to clear cache for a specific repository"""
        cache_dir = Path(f".cache/{owner}/{repo}")
        try:
            import shutil
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
                print(f"✅ Cache cleared for {owner}/{repo}")
            else:
                print(f"ℹ️  No cache found for {owner}/{repo}")
        except Exception as e:
            print(f"❌ Failed to clear cache: {e}")
    
    @staticmethod
    def clear_all_caches():
        """Static method to clear all GitHub caches"""
        try:
            import shutil
            cache_base = Path(".cache")
            if cache_base.exists():
                shutil.rmtree(cache_base)
                print(f"✅ Cleared all cache directories (.cache/)")
            else:
                print("ℹ️  No cache directories found")
        except Exception as e:
            print(f"❌ Failed to clear caches: {e}")
    
    def _show_cache_stats(self):
        """Show cache usage statistics"""
        try:
            cache_hits = getattr(self, '_cache_hit_count', 0)
            cache_saves = getattr(self, '_cache_save_count', 0)
            cache_loads = getattr(self, '_cache_load_count', 0)
            
            if cache_hits > 0 or cache_saves > 0:
                print(f"\n💾 Cache Statistics:")
                print(f"   Cache hits: {cache_hits}")
                print(f"   New cache saves: {cache_saves}")
                print(f"   Cache directory: {self.cache_dir.name}")
                
                # Count current cache files
                cache_files = list(self.cache_dir.glob("**/*.cache"))
                total_size = sum(f.stat().st_size for f in cache_files) / (1024 * 1024)  # MB
                print(f"   Total cached files: {len(cache_files)} ({total_size:.1f} MB)")
            else:
                print(f"\n💾 No cache usage (cache directory: {self.cache_dir.name})")
        except Exception:
            # Don't fail if cache stats can't be shown
            pass
        
    def _setup_interrupt_handler(self):
        """Set up interrupt handler that sets the shared flag"""
        def signal_handler(signum, frame):
            self.interrupted = True
        
        self.original_signal_handler = signal.signal(signal.SIGINT, signal_handler)
    
    def _restore_interrupt_handler(self):
        """Restore the original interrupt handler"""
        if self.original_signal_handler is not None:
            signal.signal(signal.SIGINT, self.original_signal_handler)
            self.original_signal_handler = None
    
    def _check_interrupted(self):
        """Check if user has interrupted and raise exception if so"""
        if self.interrupted:
            raise InterruptedException("User interrupted the process")
        
    def _make_request(self, url: str, params: Dict = None) -> Dict:
        """Make GitHub API request with caching and rate limiting"""
        # Check cache first
        cache_key = self._get_cache_key(url, params)
        cached_data = self._load_from_cache(cache_key)
        if cached_data is not None:
            # Track cache hits for statistics but don't spam output
            if not hasattr(self, '_cache_hit_count'):
                self._cache_hit_count = 0
            self._cache_hit_count += 1
            return cached_data
        
        response = self.session.get(url, params=params)
        
        # Handle 403 errors - could be rate limiting or permissions
        if response.status_code == 403:
            # Check if this is rate limiting
            if 'rate limit' in response.text.lower():
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                sleep_time = max(reset_time - time.time(), 0) + 1
                
                # Update status with rate limit info and check for interrupt during sleep
                for i in range(int(sleep_time)):
                    # Check for interrupt every second during rate limit wait
                    if self.interrupted:
                        raise InterruptedException("User interrupted during rate limit wait")
                    remaining = int(sleep_time - i)
                    self.status.update(f"⏳ Rate limited - waiting {remaining}s before retry...", style="yellow")
                    time.sleep(1)
                
                response = self.session.get(url, params=params)
            else:
                # This is a permissions/access error - let it fall through to raise_for_status()
                pass
        
        # Handle 422 errors (validation failures, pagination limits, etc.)
        if response.status_code == 422:
            # Don't spam logs with expected 422s from commit search tests
            if '/search/commits' in url and params and params.get('per_page') == 1:
                # This is likely a capability test, fail silently
                return {}
            else:
                print(f"API request failed with 422: {url} - {params}")
                print(f"Response: {response.text}")
                return {}  # Return empty dict to stop pagination
            # Note: Don't cache 422 errors - they could be temporary
        
        # Check for other error status codes before processing
        if response.status_code >= 400:
            # Don't cache error responses - they could be temporary
            response.raise_for_status()  # This will raise an exception
        
        data = response.json()
        
        # Only cache successful responses (2xx status codes)
        if 200 <= response.status_code < 300:
            self._save_to_cache(cache_key, data)
        
        return data
    
    def fetch_issues(self, state: str = 'all', since: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]:
        """Fetch all issues from the repository using page-based pagination"""
        issues = []
        sample_logged = 0
        page = 1  # Start with page 1 for page-based pagination
        
        # Create sample log file
        sample_log_file = f"sample_issues_{self.owner}_{self.repo}.log"
        
        self.status.print(f"🔍 Fetching {state} issues from {self.owner}/{self.repo}...")
        if limit:
            self.status.print(f"⚠️  Limiting to first {limit} issues for debugging")
        self.status.print(f"📝 Sample issue data (5% random sample) will be written to: {sample_log_file}")
        self.status.print("⌨️  Press Ctrl+C to interrupt fetching and proceed with analysis of data collected so far")
        
        self.status.start("🔄 Initializing issue fetch...")
        
        # Set up interrupt handler for this stage
        self._setup_interrupt_handler()
        
        try:
            with open(sample_log_file, 'w', encoding='utf-8') as log_file:
                log_file.write(f"=== SAMPLE ISSUE DATA FOR ANALYSIS ===\n")
                log_file.write(f"Repository: {self.owner}/{self.repo}\n")
                log_file.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.write(f"Sample Rate: 5% random sample\n")
                log_file.write("=" * 70 + "\n\n")
                
                while True:
                    # Check for interrupt at the start of each page
                    self._check_interrupted()
                    
                    # Safety limit to prevent infinite loops - allow for large repos
                    if page > 500:  # Allow up to 50,000 issues (500 pages * 100 per page)
                        self.status.update("🛑 Reached page limit (500), stopping pagination", style="yellow")
                        break
                    
                    # Update status for current page fetch
                    self.status.update(f"📥 Fetching page {page}...", style="cyan")
                    
                    params = {
                        'state': state,
                        'per_page': 100,
                        'page': page,
                        'sort': 'created',
                        'direction': 'desc'
                    }
                    if since:
                        params['since'] = since
                    
                    url = f"{self.base_url}/repos/{self.owner}/{self.repo}/issues"
                    
                    raw_batch = self._make_request(url, params)
                    
                    if not raw_batch:
                        self.status.update(f"✅ No more data at page {page}, fetch complete", style="green")
                        break
                        
                    # Filter out pull requests (they appear as issues in GitHub API)
                    filtered_batch = [issue for issue in raw_batch if 'pull_request' not in issue]
                    
                    # Log 5% sample of issues for analysis
                    for issue in filtered_batch:
                        if random.random() < 0.05:  # 5% probability
                            sample_logged += 1
                            self._log_structured_issue_sample(log_file, issue, sample_logged)
                    
                    issues.extend(filtered_batch)
                    
                    # Update status with progress
                    self.status.update(f"📊 Page {page}: {len(raw_batch)} items ({len(filtered_batch)} issues) | Total: {len(issues)} issues, {sample_logged} samples", style="cyan")
                    
                    # Move to next page
                    page += 1
                    
                    # Check if we hit the limit
                    if limit and len(issues) >= limit:
                        issues = issues[:limit]  # Trim to exact limit
                        self.status.update(f"🎯 Reached limit of {limit} issues, stopping", style="yellow")
                        break
                    
                    # Check if we got fewer than requested items (last page)
                    if len(raw_batch) < 100:
                        self.status.update("✅ Received partial page, fetch complete", style="green")
                        break
                
                log_file.write(f"\n=== SUMMARY ===\n")
                log_file.write(f"Total issues fetched: {len(issues)}\n")
                log_file.write(f"Sample issues logged: {sample_logged} ({sample_logged/len(issues)*100:.1f}%)\n")
        
        except InterruptedException:
            self.status.stop()
            self.status.print(f"⚠️  User interrupted! Proceeding with analysis of {len(issues)} issues collected so far...", style="yellow bold")
            # Update log file with interruption notice
            try:
                with open(sample_log_file, 'a', encoding='utf-8') as log_file:
                    log_file.write(f"\n=== INTERRUPTED BY USER ===\n")
                    log_file.write(f"Analysis stopped early by user request\n")
                    log_file.write(f"Issues collected: {len(issues)}\n")
                    log_file.write(f"Sample issues logged: {sample_logged}\n")
            except:
                pass  # Don't fail if we can't update log file
        
        finally:
            # Restore original signal handler
            self._restore_interrupt_handler()
            # Stop status display if it's still running
            if hasattr(self, 'status'):
                self.status.stop()
            # Show cache statistics
            self._show_cache_stats()
        
        # Final summary
        self.status.print(f"✅ Total issues fetched: {len(issues)}", style="green bold")
        self.status.print(f"📊 Sample issues logged: {sample_logged} ({sample_logged/len(issues)*100:.1f}% of fetched issues)", style="blue")
        self.status.print(f"💾 Sample data written to: {sample_log_file}", style="blue")
        
        return issues
    
    def _log_structured_issue_sample(self, log_file, issue: Dict, sample_number: int):
        """Log a structured sample of an issue with commit data"""
        try:
            log_file.write(f"\n{'='*80}\n")
            log_file.write(f"SAMPLE #{sample_number}: Issue #{issue['number']}\n")
            log_file.write(f"{'='*80}\n")
            
            # Basic issue information
            log_file.write("BASIC INFO:\n")
            log_file.write(f"  Title: {issue['title']}\n")
            log_file.write(f"  State: {issue['state']}\n")
            log_file.write(f"  Created: {issue['created_at']}\n")
            log_file.write(f"  Updated: {issue['updated_at']}\n")
            log_file.write(f"  Closed: {issue.get('closed_at', 'N/A')}\n")
            log_file.write(f"  Author: {issue.get('user', {}).get('login', 'N/A')}\n")
            log_file.write(f"  Assignee: {issue.get('assignee', {}).get('login', 'N/A') if issue.get('assignee') else 'None'}\n")
            log_file.write(f"  Comments: {issue.get('comments', 0)}\n")
            
            # Labels
            labels = [label['name'] if isinstance(label, dict) else str(label) for label in issue.get('labels', [])]
            log_file.write(f"  Labels: {', '.join(labels) if labels else 'None'}\n")
            
            # Milestone
            milestone = issue.get('milestone', {})
            if milestone:
                log_file.write(f"  Milestone: {milestone.get('title', 'N/A')}\n")
            else:
                log_file.write(f"  Milestone: None\n")
            
            # Issue body preview (first 200 chars)
            body = issue.get('body', '')
            if body:
                body_preview = body.replace('\n', ' ').strip()[:200]
                if len(body) > 200:
                    body_preview += "..."
                log_file.write(f"  Body Preview: {body_preview}\n")
            
            # Try to get timeline events for work start detection (skip if interrupted)
            log_file.write("\nTIMELINE EVENTS:\n")
            if not self.interrupted:
                try:
                    events = self.fetch_issue_events(issue['number'])
                    relevant_events = []
                    for event in events[:10]:  # Limit to first 10 events
                        if event.get('event') in ['assigned', 'labeled', 'unlabeled', 'closed', 'reopened']:
                            event_desc = f"  {event['created_at']}: {event['event']}"
                            if event.get('assignee'):
                                event_desc += f" -> {event['assignee']['login']}"
                            if event.get('label'):
                                event_desc += f" -> {event['label']['name']}"
                            relevant_events.append(event_desc)
                    
                    if relevant_events:
                        for event_desc in relevant_events[:5]:  # Show max 5 events
                            log_file.write(f"{event_desc}\n")
                    else:
                        log_file.write("  No relevant timeline events found\n")
                        
                except (InterruptedException, Exception) as e:
                    log_file.write(f"  Error fetching events: {str(e)}\n")
            else:
                log_file.write("  Skipped due to user interrupt\n")
            
            # Try to get commit data (skip if interrupted)
            log_file.write("\nCOMMIT DATA:\n")
            if not self.interrupted:
                try:
                    commits = self.fetch_commits_for_issue(issue['number'])
                    if commits:
                        log_file.write(f"  Found {len(commits)} commits referencing this issue:\n")
                        for i, commit in enumerate(commits[:3]):  # Show max 3 commits
                            commit_info = commit.get('commit', {})
                            author = commit_info.get('author', {})
                            log_file.write(f"    [{i+1}] SHA: {commit.get('sha', 'N/A')[:8]}...\n")
                            log_file.write(f"        Date: {commit_info.get('committer', {}).get('date', 'N/A')}\n")
                            log_file.write(f"        Author: {author.get('name', 'N/A')} <{author.get('email', 'N/A')}>\n")
                            log_file.write(f"        Message: {commit_info.get('message', '')[:100]}{'...' if len(commit_info.get('message', '')) > 100 else ''}\n")
                        
                        if len(commits) > 3:
                            log_file.write(f"    ... and {len(commits) - 3} more commits\n")
                    else:
                        log_file.write("  No commits found referencing this issue\n")
                        
                except (InterruptedException, Exception) as e:
                    log_file.write(f"  Error fetching commits: {str(e)}\n")
            else:
                log_file.write("  Skipped due to user interrupt\n")
            
            # Dependencies and sub-issues if available
            if 'sub_issues_summary' in issue:
                sub_summary = issue['sub_issues_summary']
                log_file.write(f"\nSUB-ISSUES: {sub_summary.get('completed', 0)}/{sub_summary.get('total', 0)} completed\n")
            
            if 'issue_dependencies_summary' in issue:
                dep_summary = issue['issue_dependencies_summary']
                log_file.write(f"DEPENDENCIES: Blocked by {dep_summary.get('blocked_by', 0)}, Blocking {dep_summary.get('blocking', 0)}\n")
            
            # Raw data section for advanced analysis
            log_file.write("\nRAW FIELD SUMMARY:\n")
            for key, value in issue.items():
                if isinstance(value, (dict, list)) and len(str(value)) > 200:
                    log_file.write(f"  {key}: {type(value).__name__} (length: {len(value) if isinstance(value, list) else 'complex'})\n")
                elif key not in ['title', 'state', 'created_at', 'updated_at', 'closed_at', 'user', 'assignee', 'comments', 'labels', 'milestone', 'body']:
                    log_file.write(f"  {key}: {str(value)[:100]}{'...' if len(str(value)) > 100 else ''}\n")
            
        except Exception as e:
            log_file.write(f"ERROR logging structured sample: {str(e)}\n")
            # Fallback to simple logging
            log_file.write(f"--- Sample Issue #{issue['number']}: {issue['title']} ---\n")
            for key, value in issue.items():
                if isinstance(value, (dict, list)) and len(str(value)) > 200:
                    log_file.write(f"  {key}: {type(value).__name__} (length: {len(value) if isinstance(value, list) else 'complex'})\n")
                else:
                    log_file.write(f"  {key}: {value}\n")
            log_file.write("\n")
    
    def fetch_issue_events(self, issue_number: int) -> List[Dict]:
        """Fetch timeline events for a specific issue"""
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/issues/{issue_number}/events"
        return self._make_request(url)
    
    def _test_commit_search_capability(self) -> bool:
        """Test if commit search is available for this repository"""
        # Cache the result so we only test once per session
        if hasattr(self, '_commit_search_tested'):
            return self._commit_search_tested
        
        # Check if contents scope is available first
        if not self.available_scopes.get('contents', False):
            self._commit_search_tested = False
            return False
        
        # Try a single, very generic search term first
        test_query = f"repo:{self.owner}/{self.repo}"
        
        try:
            url = f"{self.base_url}/search/commits"
            params = {'q': test_query, 'per_page': 1}
            
            result = self._make_request(url, params)
            # If we get any results or even an empty result set, search is working
            if isinstance(result, dict) and 'total_count' in result:
                self._commit_search_tested = True
                return True
            # If we get here without exception, search API is accessible
            self._commit_search_tested = True
            return True
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in [422, 403]:
                # Search not available for this repo
                self._commit_search_tested = False
                return False
            else:
                self._commit_search_tested = False
                return False  # Other HTTP errors mean unavailable
        except Exception:
            self._commit_search_tested = False
            return False

    def fetch_commits_for_issue(self, issue_number: int) -> List[Dict]:
        """Find commits that reference an issue"""
        # Test commit search capability on first use
        if self.commit_search_available is None:
            self.commit_search_available = self._test_commit_search_capability()
            if not self.commit_search_available:
                self.status.print(f"ℹ️  Commit search not available for {self.owner}/{self.repo} - skipping commit analysis", style="yellow")
        
        # Skip if we know commit search doesn't work
        if not self.commit_search_available:
            return []
            
        try:
            # Search for commits that mention this issue
            query = f"repo:{self.owner}/{self.repo} #{issue_number}"
            url = f"{self.base_url}/search/commits"
            params = {'q': query, 'sort': 'committer-date', 'order': 'asc', 'per_page': 10}
            
            result = self._make_request(url, params)
            return result.get('items', [])
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in [422, 403]:
                # Disable further attempts if we get 422 or 403
                self.commit_search_available = False
                self.status.print(f"⚠️  Commit search failed for {self.owner}/{self.repo} (HTTP {e.response.status_code}) - disabling for remaining issues", style="yellow")
                return []
            else:
                print(f"HTTP error fetching commits for issue #{issue_number}: {e.response.status_code} - {e}")
                return []
        except Exception as e:
            print(f"Error fetching commits for issue #{issue_number}: {e}")
            return []
    
    def fetch_pull_requests_for_issue(self, issue_number: int) -> List[Dict]:
        """Find pull requests that reference an issue"""
        # Check if pull requests scope is available
        if not self.available_scopes.get('pull_requests', False):
            return []
            
        try:
            # GitHub search for PRs mentioning the issue
            query = f"repo:{self.owner}/{self.repo} #{issue_number} type:pr"
            url = f"{self.base_url}/search/issues"
            params = {'q': query, 'sort': 'created', 'order': 'asc', 'per_page': 10}
            
            result = self._make_request(url, params)
            return result.get('items', [])
            
        except Exception as e:
            # Don't break analysis if PR search fails
            return []
    
    @graphql_retry(max_retries=3, base_delay=2.0, max_delay=30.0)
    def _make_graphql_request(self, query: str, variables: Dict = None) -> Dict:
        """Make a GraphQL request to GitHub API with caching and enhanced error handling"""
        url = "https://api.github.com/graphql"
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        # Check cache first for GraphQL requests
        cache_key = self._get_cache_key(url, payload)
        cached_data = self._load_from_cache(cache_key)
        if cached_data is not None:
            # Track cache hits for statistics
            if not hasattr(self, '_cache_hit_count'):
                self._cache_hit_count = 0
            self._cache_hit_count += 1
            return cached_data
        
        try:
            response = self.graphql_session.post(url, json=payload)
            
            # Handle GitHub rate limiting specifically
            if response.status_code == 403:
                # Check if it's a rate limit issue
                rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', '0')
                if rate_limit_remaining == '0':
                    reset_time = response.headers.get('X-RateLimit-Reset', '0')
                    wait_time = max(60, int(reset_time) - int(time.time()) + 5)
                    raise Exception(f"Rate limit exceeded. Reset in {wait_time} seconds")
            
            response.raise_for_status()
            result = response.json()
            
            # Check for GraphQL-specific errors
            if "errors" in result:
                errors = result['errors']
                
                # Handle specific GitHub GraphQL error types
                for error in errors:
                    error_type = error.get('type', '')
                    message = error.get('message', '')
                    
                    if 'timeout' in message.lower() or 'too complex' in message.lower():
                        raise Exception(f"Query too complex or timeout: {message}")
                    elif 'rate limit' in message.lower():
                        raise Exception(f"GraphQL rate limit: {message}")
                
                raise Exception(f"GraphQL errors: {errors}")
            
            # Check rate limit status from response
            if 'rateLimit' in result:
                rate_limit = result['rateLimit']
                remaining = rate_limit.get('remaining', 0)
                if remaining < 100:  # Less than 100 points remaining
                    reset_at = rate_limit.get('resetAt', '')
                    print(f"⚠️  GraphQL rate limit low: {remaining} points remaining (resets at {reset_at})")
                
        except requests.exceptions.Timeout:
            raise Exception("Request timeout - server took too long to respond")
        except requests.exceptions.ConnectionError:
            raise Exception("Connection error - unable to reach GitHub API")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 502:
                raise Exception("502 Bad Gateway - GitHub API temporarily unavailable")
            elif e.response.status_code == 504:
                raise Exception("504 Gateway Timeout - GitHub API request timed out")
            else:
                raise Exception(f"HTTP {e.response.status_code}: {e.response.text}")
        
        # Cache successful GraphQL responses
        data = result.get("data", {})
        self._save_to_cache(cache_key, data)
        
        return data
    
    def fetch_organization_projects(self) -> List[Dict]:
        """Fetch organization projects using GraphQL"""
        query = """
        query($owner: String!) {
          organization(login: $owner) {
            projectsV2(first: 20) {
              nodes {
                id
                title
                shortDescription
                url
                closed
                createdAt
                updatedAt
              }
            }
          }
        }
        """
        try:
            result = self._make_graphql_request(query, {"owner": self.owner})
            org_data = result.get("organization", {})
            projects_data = org_data.get("projectsV2", {})
            return projects_data.get("nodes", [])
        except Exception as e:
            self.status.print(f"⚠️  Could not fetch organization projects: {e}", style="yellow")
            return []
    
    def fetch_repository_projects(self) -> List[Dict]:
        """Fetch repository projects using GraphQL"""
        query = """
        query($owner: String!, $repo: String!) {
          repository(owner: $owner, name: $repo) {
            projectsV2(first: 20) {
              nodes {
                id
                title
                shortDescription
                url
                closed
                createdAt
                updatedAt
              }
            }
          }
        }
        """
        try:
            result = self._make_graphql_request(query, {"owner": self.owner, "repo": self.repo})
            repo_data = result.get("repository", {})
            projects_data = repo_data.get("projectsV2", {})
            return projects_data.get("nodes", [])
        except Exception as e:
            self.status.print(f"⚠️  Could not fetch repository projects: {e}", style="yellow")
            return []
    
    def fetch_project_items(self, project_id: str) -> List[Dict]:
        """Fetch items from a specific project with pagination"""
        all_items = []
        cursor = None
        page = 0
        
        while True:
            page += 1
            cursor_arg = f', after: "{cursor}"' if cursor else ""
            
            query = f"""
            query($projectId: ID!) {{
              node(id: $projectId) {{
                ... on ProjectV2 {{
                  items(first: 50{cursor_arg}) {{
                    pageInfo {{
                      hasNextPage
                      endCursor
                    }}
                    nodes {{
                      id
                      createdAt
                      updatedAt
                      content {{
                        ... on Issue {{
                          number
                          title
                          url
                          state
                          createdAt
                          closedAt
                          assignees(first: 5) {{
                            nodes {{
                              login
                            }}
                          }}
                          labels(first: 10) {{
                            nodes {{
                              name
                            }}
                          }}
                        }}
                        ... on PullRequest {{
                          number
                          title
                          url
                          state
                          createdAt
                          closedAt
                        }}
                      }}
                      fieldValues(first: 20) {{
                        nodes {{
                          ... on ProjectV2ItemFieldTextValue {{
                            text
                            field {{
                              ... on ProjectV2FieldCommon {{
                                name
                              }}
                            }}
                          }}
                          ... on ProjectV2ItemFieldSingleSelectValue {{
                            name
                            field {{
                              ... on ProjectV2FieldCommon {{
                                name
                              }}
                            }}
                          }}
                          ... on ProjectV2ItemFieldDateValue {{
                            date
                            field {{
                              ... on ProjectV2FieldCommon {{
                                name
                              }}
                            }}
                          }}
                        }}
                      }}
                    }}
                  }}
                }}
              }}
            }}
            """
            
            try:
                result = self._make_graphql_request(query, {"projectId": project_id})
                project_data = result.get("node", {})
                items_data = project_data.get("items", {})
                page_info = items_data.get("pageInfo", {})
                nodes = items_data.get("nodes", [])
                
                all_items.extend(nodes)
                
                if not page_info.get("hasNextPage", False):
                    break
                    
                cursor = page_info.get("endCursor")
                if not cursor:
                    break
                    
            except Exception as e:
                self.status.print(f"⚠️  Could not fetch project items (page {page}): {e}", style="yellow")
                break
        
        return all_items
    
    def _build_issues_graphql_query(self, batch_size=50) -> str:
        """Build comprehensive GraphQL query for issues with all related data"""
        return """
        query GetRepositoryIssues($owner: String!, $repo: String!, $cursor: String, $first: Int, $states: [IssueState!]) {
          repository(owner: $owner, name: $repo) {
            issues(first: $first, after: $cursor, states: $states, orderBy: {field: CREATED_AT, direction: DESC}) {
              pageInfo {
                hasNextPage
                endCursor
              }
              totalCount
              nodes {
                # Basic issue data
                number
                title
                body
                state
                createdAt
                updatedAt
                closedAt
                url
                
                # Labels
                labels(first: 50) {
                  nodes {
                    name
                    color
                    description
                  }
                }
                
                # Assignment
                assignees(first: 10) {
                  nodes {
                    login
                    name
                  }
                }
                
                # Milestone
                milestone {
                  title
                  description
                  dueOn
                  state
                }
                
                # Author
                author {
                  login
                  ... on User {
                    name
                  }
                }
                
                # Timeline events (replaces fetch_issue_events)
                timelineItems(first: 50, itemTypes: [
                  ASSIGNED_EVENT,
                  UNASSIGNED_EVENT, 
                  LABELED_EVENT,
                  UNLABELED_EVENT,
                  CLOSED_EVENT,
                  REOPENED_EVENT,
                  REFERENCED_EVENT,
                  CROSS_REFERENCED_EVENT
                ]) {
                  nodes {
                    __typename
                    ... on AssignedEvent {
                      createdAt
                      assignee {
                        ... on User {
                          login
                        }
                      }
                    }
                    ... on UnassignedEvent {
                      createdAt
                      assignee {
                        ... on User {
                          login  
                        }
                      }
                    }
                    ... on LabeledEvent {
                      createdAt
                      label {
                        name
                      }
                    }
                    ... on UnlabeledEvent {
                      createdAt
                      label {
                        name
                      }
                    }
                    ... on ClosedEvent {
                      createdAt
                      actor {
                        login
                      }
                    }
                    ... on ReopenedEvent {
                      createdAt
                      actor {
                        login
                      }
                    }
                    ... on ReferencedEvent {
                      createdAt
                      commit {
                        oid
                        message
                        committedDate
                        author {
                          name
                          email
                        }
                      }
                    }
                    ... on CrossReferencedEvent {
                      createdAt
                      source {
                        ... on PullRequest {
                          number
                          title
                          state
                        }
                      }
                    }
                  }
                }
                
                # Project data (if available)
                projectItems(first: 10) {
                  nodes {
                    id
                    project {
                      id
                      title
                      number
                    }
                    fieldValues(first: 20) {
                      nodes {
                        ... on ProjectV2ItemFieldTextValue {
                          text
                          field {
                            ... on ProjectV2FieldCommon {
                              name
                            }
                          }
                        }
                        ... on ProjectV2ItemFieldSingleSelectValue {
                          name
                          field {
                            ... on ProjectV2FieldCommon {
                              name
                            }
                          }
                        }
                        ... on ProjectV2ItemFieldDateValue {
                          date
                          field {
                            ... on ProjectV2FieldCommon {
                              name
                            }
                          }
                        }
                      }
                    }
                  }
                }
                
                # Comments count
                comments {
                  totalCount
                }
                
                # Reactions
                reactions {
                  totalCount
                }
              }
            }
          }
          
          # Rate limit information
          rateLimit {
            remaining
            resetAt
            cost
            limit
          }
        }
        """
    
    def _transform_graphql_issue(self, issue_node: Dict) -> Dict:
        """Transform GraphQL issue response to match REST API format"""
        
        # Extract timeline events and convert to work start detection format
        timeline_events = []
        commits = []
        
        for timeline_item in issue_node.get('timelineItems', {}).get('nodes', []):
            event_type = timeline_item['__typename']
            
            if event_type == 'AssignedEvent':
                timeline_events.append({
                    'event': 'assigned',
                    'created_at': timeline_item['createdAt'],
                    'assignee': timeline_item['assignee']
                })
            elif event_type == 'UnassignedEvent':
                timeline_events.append({
                    'event': 'unassigned',
                    'created_at': timeline_item['createdAt'],
                    'assignee': timeline_item['assignee']
                })
            elif event_type == 'LabeledEvent':
                timeline_events.append({
                    'event': 'labeled',
                    'created_at': timeline_item['createdAt'],
                    'label': timeline_item['label']
                })
            elif event_type == 'UnlabeledEvent':
                timeline_events.append({
                    'event': 'unlabeled',
                    'created_at': timeline_item['createdAt'],
                    'label': timeline_item['label']
                })
            elif event_type == 'ClosedEvent':
                timeline_events.append({
                    'event': 'closed',
                    'created_at': timeline_item['createdAt'],
                    'actor': timeline_item['actor']
                })
            elif event_type == 'ReopenedEvent':
                timeline_events.append({
                    'event': 'reopened',
                    'created_at': timeline_item['createdAt'],
                    'actor': timeline_item['actor']
                })
            elif event_type == 'ReferencedEvent' and timeline_item.get('commit'):
                commit = timeline_item['commit']
                commits.append({
                    'sha': commit['oid'],
                    'commit': {
                        'message': commit['message'],
                        'author': {
                            'date': commit['committedDate'],
                            'name': commit['author']['name'],
                            'email': commit['author']['email']
                        }
                    }
                })
        
        # Extract project data
        project_data = []
        for project_item in issue_node.get('projectItems', {}).get('nodes', []):
            project_info = {
                'project': project_item.get('project', {}),
                'fields': {}
            }
            
            for field_value in project_item.get('fieldValues', {}).get('nodes', []):
                # Safely get field name
                field = field_value.get('field')
                if not field:
                    continue
                    
                field_name = field.get('name')
                if not field_name:
                    continue
                
                if 'text' in field_value:
                    project_info['fields'][field_name] = field_value['text']
                elif 'name' in field_value:
                    project_info['fields'][field_name] = field_value['name']
                elif 'date' in field_value:
                    project_info['fields'][field_name] = field_value['date']
                    
            project_data.append(project_info)
        
        # Transform to REST API compatible format
        issue = {
            'number': issue_node.get('number'),
            'title': issue_node.get('title', ''),
            'body': issue_node.get('body') or '',
            'state': issue_node.get('state', '').lower(),
            'created_at': issue_node.get('createdAt'),
            'updated_at': issue_node.get('updatedAt'),
            'closed_at': issue_node.get('closedAt'),
            'html_url': f"https://github.com/{self.owner}/{self.repo}/issues/{issue_node.get('number')}",
            'url': issue_node.get('url', ''),
            'id': issue_node.get('number'),  # Use number as ID for simplicity
            
            # Labels
            'labels': [
                {
                    'name': label.get('name', ''),
                    'color': label.get('color', ''),
                    'description': label.get('description', '')
                }
                for label in issue_node.get('labels', {}).get('nodes', [])
            ],
            
            # Assignees
            'assignees': [
                {'login': assignee.get('login', ''), 'name': assignee.get('name', '')}
                for assignee in issue_node.get('assignees', {}).get('nodes', [])
            ],
            'assignee': None,  # Will be set below
            
            # Milestone
            'milestone': issue_node.get('milestone'),
            
            # Author
            'user': issue_node.get('author'),
            
            # Counts
            'comments': issue_node.get('comments', {}).get('totalCount', 0),
            
            # Enhanced data (from GraphQL, not available in basic REST)
            'timeline_events': timeline_events,
            'commits': commits,
            'project_data': project_data,
            
            # Additional fields for compatibility
            'locked': False,
            'author_association': 'NONE',
            'pull_request': None  # This is an issue, not a PR
        }
        
        # Safely set assignee
        assignees_nodes = issue_node.get('assignees', {}).get('nodes', [])
        if assignees_nodes:
            issue['assignee'] = assignees_nodes[0]
        
        return issue
    
    def fetch_issues_graphql(self, state='all', limit=None, batch_size=50) -> List[Dict]:
        """
        Fetch issues using GraphQL - much more efficient than REST
        
        Benefits:
        - Single query gets issues + timeline + projects + commits
        - No need for separate API calls per issue
        - Better rate limiting (points vs requests)
        - Exact data needed, no over-fetching
        """
        
        # Map REST state parameter to GraphQL states
        state_mapping = {
            'open': ['OPEN'],
            'closed': ['CLOSED'], 
            'all': ['OPEN', 'CLOSED']
        }
        
        graphql_states = state_mapping.get(state, ['OPEN', 'CLOSED'])
        
        issues = []
        cursor = None
        total_fetched = 0
        
        # Build the query with dynamic batch size
        query = self._build_issues_graphql_query(batch_size)
        
        self.status.print("🚀 Using GraphQL API for comprehensive issue fetching...", style="cyan")
        
        while True:
            # Determine page size
            page_size = 100  # GraphQL max
            if limit and (total_fetched + page_size) > limit:
                page_size = limit - total_fetched
                
            variables = {
                "owner": self.owner,
                "repo": self.repo,
                "cursor": cursor,
                "first": min(page_size, batch_size),  # Use the smaller of the two
                "states": graphql_states
            }
            
            try:
                result = self._make_graphql_request(query, variables)
                
                repository = result.get('repository')
                if not repository:
                    raise Exception("Repository not found or not accessible")
                
                issues_data = repository['issues']
                
                # Process issues
                for issue_node in issues_data['nodes']:
                    # Transform GraphQL response to match REST API format
                    issue = self._transform_graphql_issue(issue_node)
                    issues.append(issue)
                    
                total_fetched += len(issues_data['nodes'])
                
                # Check pagination
                page_info = issues_data['pageInfo']
                if not page_info['hasNextPage'] or (limit and total_fetched >= limit):
                    break
                    
                cursor = page_info['endCursor']
                
                self.status.update(f"📥 Fetched {total_fetched} issues via GraphQL (with timeline & commits)...")
                
            except Exception as e:
                error_message = str(e)
                
                # If it's a timeout/size issue, try smaller batch sizes first
                if "504" in error_message or "timeout" in error_message.lower() or "too large" in error_message.lower():
                    self.status.print(f"❌ GraphQL query failed (likely too large): {e}", style="red")
                    
                    # Try with smaller batch size
                    if batch_size > 25:
                        self.status.print("🔄 Retrying GraphQL with smaller batch size (25)...", style="yellow")
                        return self.fetch_issues_graphql(state, limit, batch_size=25)
                    elif batch_size > 10:
                        self.status.print("🔄 Retrying GraphQL with minimal batch size (10)...", style="yellow")
                        return self.fetch_issues_graphql(state, limit, batch_size=10)
                
                # For other errors or if small batches still fail, fall back to REST
                self.status.print(f"❌ GraphQL query failed: {e}", style="red")
                self.status.print("🔄 Falling back to REST API (without timeline/commit data)...", style="yellow")
                # Fall back to REST API
                return self.fetch_issues(state, limit)
        
        self.status.print(f"✅ GraphQL fetch complete: {len(issues)} issues with comprehensive data", style="green")
        return issues

    def enrich_issues_with_project_data(self, issues: List[Dict]) -> List[Dict]:
        """Enrich issues with project board information"""
        # Check if projects scope is available
        if not self.available_scopes.get('projects', False):
            self.status.print("ℹ️  Projects scope not available - skipping project data enrichment", style="blue")
            # Return issues with empty project_data
            for issue in issues:
                issue['project_data'] = []
            return issues
            
        self.status.print("🔄 Fetching project board data...", style="cyan")
        
        # Fetch all projects (both org and repo level)
        org_projects = self.fetch_organization_projects()
        repo_projects = self.fetch_repository_projects()
        all_projects = org_projects + repo_projects
        
        if not all_projects:
            self.status.print("⚠️  No projects found or accessible", style="yellow")
            # Add empty project_data to all issues
            for issue in issues:
                issue['project_data'] = []
            return issues
            
        # Create a mapping of issue numbers to project data
        issue_project_map = {}
        
        for project in all_projects:
            if project.get("closed"):
                continue  # Skip closed projects
                
            project_items = self.fetch_project_items(project["id"])
            
            for item in project_items:
                content = item.get("content", {})
                if content and "number" in content:
                    issue_number = content["number"]
                    
                    # Extract field values
                    field_values = {}
                    for field_value in item.get("fieldValues", {}).get("nodes", []):
                        field_name = field_value.get("field", {}).get("name", "")
                        
                        if "text" in field_value:
                            field_values[field_name] = field_value["text"]
                        elif "name" in field_value:
                            field_values[field_name] = field_value["name"]
                        elif "date" in field_value:
                            field_values[field_name] = field_value["date"]
                    
                    if issue_number not in issue_project_map:
                        issue_project_map[issue_number] = []
                    
                    issue_project_map[issue_number].append({
                        "project_title": project["title"],
                        "project_url": project["url"],
                        "project_id": project["id"],
                        "item_id": item["id"],
                        "field_values": field_values
                    })
        
        # Enrich issues with project data
        enriched_issues = []
        for issue in issues:
            issue_copy = issue.copy()
            issue_number = issue["number"]
            
            if issue_number in issue_project_map:
                issue_copy["project_data"] = issue_project_map[issue_number]
            else:
                issue_copy["project_data"] = []
            
            enriched_issues.append(issue_copy)
        
        self.status.print(f"✅ Enriched {len([i for i in enriched_issues if i['project_data']])} issues with project data", style="green")
        return enriched_issues
    
    def sync_issues_to_json(self, output_file: str, state: str = 'all', limit: Optional[int] = None, strategic_only: bool = True, use_rest: bool = False):
        """Sync all GitHub issues data to a comprehensive JSON file"""
        try:
            # Fetch issues using GraphQL by default, REST if requested
            if use_rest:
                self.status.print("🔄 Using REST API (legacy mode)...", style="yellow")
                issues = self.fetch_issues(state=state, limit=limit)
            else:
                # Use GraphQL by default - much more efficient
                issues = self.fetch_issues_graphql(state=state, limit=limit)
            
            if not issues:
                print("No issues found in repository")
                return
            
            # Apply strategic work filtering if requested
            if strategic_only:
                original_count = len(issues)
                issues = [issue for issue in issues if is_strategic_work(issue)]
                filtered_count = len(issues)
                print(f"🎯 Strategic work focus: syncing {filtered_count:,} strategic issues (filtered out {original_count - filtered_count:,} operational tasks)")
            
            if not issues:
                print("No issues found after filtering")
                return
            
            # For REST API, we need to enrich with additional data
            # For GraphQL API, data is already included
            if use_rest:
                # Enrich with GitHub Projects data
                print("Enriching issues with GitHub Projects data...")
                issues = self.enrich_issues_with_project_data(issues)
                
                # Enhance each issue with additional GitHub data
                self.status.print("🔄 Fetching detailed issue data...", style="cyan")
                self._setup_interrupt_handler()
                
                try:
                    enhanced_issues = []
                    for i, issue in enumerate(issues):
                        # Check for interrupt every 10 issues
                        if i % 10 == 0:
                            self._check_interrupted()
                            progress = (i / len(issues)) * 100
                            self.status.update(f"⚙️  Processing issue {i+1}/{len(issues)} ({progress:.1f}%) - #{issue['number']}", style="cyan")
                        
                        # Enhance with timeline events and commit data
                        enhanced_issue = issue.copy()
                        
                        # Add timeline events (for work start detection)
                        try:
                            events = self.fetch_issue_events(issue['number'])
                            enhanced_issue['timeline_events'] = events
                        except Exception:
                            enhanced_issue['timeline_events'] = []
                        
                        # Add commit data (for work start detection)
                        try:
                            commits = self.fetch_commits_for_issue(issue['number'])
                            enhanced_issue['commits'] = commits
                        except Exception:
                            enhanced_issue['commits'] = []
                        
                        # Add pull request data
                        try:
                            prs = self.fetch_pull_requests_for_issue(issue['number'])
                            enhanced_issue['pull_requests'] = prs
                        except Exception:
                            enhanced_issue['pull_requests'] = []
                        
                        enhanced_issues.append(enhanced_issue)
                    
                    issues = enhanced_issues  # Use enhanced issues
                    
                except InterruptedException:
                    self.status.print(f"⚠️  User interrupted! Syncing {len(enhanced_issues)} issues processed so far...", style="yellow bold")
                    issues = enhanced_issues  # Use what we have
                
                finally:
                    self._restore_interrupt_handler()
                    self.status.stop()
            else:
                # GraphQL already includes all needed data
                self.status.print("✅ Using GraphQL - all data already included", style="green")
            
            # For both REST and GraphQL, issues are ready to use
            final_issues = issues
            
            # Create final JSON structure with metadata
            json_data = {
                'repository': {
                    'github_owner': self.owner,
                    'github_repo': self.repo,
                    'github_url': f'https://github.com/{self.owner}/{self.repo}',
                    'sync_date': datetime.now(timezone.utc).isoformat(),
                    'total_issues_synced': len(final_issues),
                    'strategic_work_filter': strategic_only,
                    'state_filter': state
                },
                'issues': final_issues
            }
            
            # Write to JSON file
            with open(output_file, 'w') as f:
                json.dump(json_data, f, indent=2, default=str)
            
            self.status.print(f"✅ Synced {len(final_issues)} issues to {output_file}", style="green bold")
            self.status.print(f"📊 Strategic work: {len(final_issues)} issues included", style="blue")
            self.status.print(f"💾 JSON data written to: {output_file}", style="blue")
            
        except InterruptedException:
            self.status.print(f"⚠️  User interrupted sync process!", style="yellow bold")
        except Exception as e:
            self.status.print(f"❌ Error during sync: {e}", style="red")
            raise

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description='Sync GitHub repository issues data to JSON files',
        epilog='''
Strategic Work Focus:
  By default, syncs only strategic business value work:
  INCLUDES: product features, customer issues, epics
  EXCLUDES: chores, deployments, infrastructure tasks
  Use --no-strategic-filter to include all issues.

Cache Management:
  API responses are cached for 1 week to speed up subsequent runs.
  Cache directory: .cache/OWNER/REPO/
  
  To clear cache:
    --clear-cache           Clear cache for specified repository
    --clear-all-caches      Clear all GitHub caches
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('owner', nargs='?', help='Repository owner/organization')
    parser.add_argument('repo', nargs='?', help='Repository name')
    parser.add_argument('--output', '-o', default='issues_data.json', help='Output JSON file name (default: issues_data.json)')
    parser.add_argument('--state', choices=['open', 'closed', 'all'], default='all', help='Issue state filter (default: all)')
    parser.add_argument('--limit', type=int, help='Limit number of issues to sync (for debugging)')
    parser.add_argument('--no-strategic-filter', action='store_true', help='Include all issues, not just strategic work')
    parser.add_argument('--use-rest', action='store_true', help='Use REST API instead of GraphQL (slower but more compatible)')
    parser.add_argument('--clear-cache', action='store_true', help='Clear cache for this repository and exit')
    parser.add_argument('--clear-all-caches', action='store_true', help='Clear all GitHub caches and exit')
    args = parser.parse_args()
    
    # Handle cache clearing commands
    if args.clear_all_caches:
        GitHubDataSyncer.clear_all_caches()
        return
    
    if args.clear_cache:
        if args.owner and args.repo:
            GitHubDataSyncer.clear_cache_for_repo(args.owner, args.repo)
        else:
            print("Error: --clear-cache requires owner and repo arguments")
            print("Usage: python sync_issues.py owner repo --clear-cache")
        return
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Configuration
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
    if not GITHUB_TOKEN:
        print("Please set GITHUB_TOKEN environment variable")
        return
    
    # Repository configuration - use command line args or prompt
    OWNER = args.owner
    REPO = args.repo
    
    if not OWNER:
        OWNER = input("Enter repository owner: ").strip()
    if not REPO:
        REPO = input("Enter repository name: ").strip()
    
    if not OWNER or not REPO:
        print("Owner and repository name are required")
        return
    
    print(f"Syncing repository: {OWNER}/{REPO}")
    
    # Initialize syncer
    syncer = GitHubDataSyncer(GITHUB_TOKEN, OWNER, REPO)
    
    # Sync issues to JSON
    try:
        syncer.sync_issues_to_json(
            output_file=args.output,
            state=args.state,
            limit=args.limit,
            strategic_only=not args.no_strategic_filter,
            use_rest=args.use_rest
        )
        
    except InterruptedException:
        print("\n\n⚠️  Process interrupted by user. Partial results may have been saved.")
        return
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user. No data synced.")
        return
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        return

if __name__ == "__main__":
    main()