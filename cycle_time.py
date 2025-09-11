#!/usr/bin/env python3
"""
GitHub Issues Cycle Time Analyzer

Fetches GitHub issues data, calculates cycle times, and generates comprehensive reports.
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
#     "rich",
# ]
# ///

import os
import json
import time
import requests
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import re
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
import argparse
import sys
import random
import signal
import hashlib
import pickle
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
    from rich.live import Live
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

class InterruptedException(Exception):
    """Exception raised when user interrupts the process"""
    pass

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

@dataclass
class StageSegment:
    """Container for stage-based workflow tracking"""
    stage_name: str
    start_time: datetime
    end_time: Optional[datetime]
    duration_days: Optional[float]
    stage_type: str  # 'created', 'planning', 'development', 'review', 'testing', 'deployment', 'closed'
    is_work_time: bool  # True for active work stages, False for waiting stages
    
    # Common stage types:
    # - 'created': Issue created, waiting for planning
    # - 'planning': Requirements review, design, estimation
    # - 'development': Active coding/implementation
    # - 'review': Code review, feedback cycles
    # - 'testing': QA, validation, bug fixes
    # - 'deployment': Release preparation, deployment
    # - 'closed': Issue completed

def is_strategic_work(issue: Dict) -> bool:
    """
    Filter for strategic business value work vs operational maintenance.
    
    INCLUDE: product work, features, customer issues, epics
    EXCLUDE: chores, deployments, infrastructure, compliance tasks
    """
    labels_str = str(issue.get('labels', [])).lower()
    
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

@dataclass
class CycleTimeMetrics:
    """Container for cycle time calculations"""
    issue_number: int
    title: str
    created_at: datetime
    closed_at: Optional[datetime]
    work_started_at: Optional[datetime]
    lead_time_days: Optional[float]
    cycle_time_days: Optional[float]
    labels: List[str]
    assignee: Optional[str]
    milestone: Optional[str]
    state: str
    # Enhanced stage-based workflow analysis
    stage_segments: Optional[List[StageSegment]] = None
    # GitHub Projects data
    project_title: Optional[str] = None
    project_status: Optional[str] = None
    project_iteration: Optional[str] = None
    project_assignees: Optional[List[str]] = None
    total_work_time_days: Optional[float] = None
    total_wait_time_days: Optional[float] = None
    work_efficiency_ratio: Optional[float] = None

class GitHubCycleTimeAnalyzer:
    """Analyze cycle times for GitHub repository issues"""
    
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
        self.status = StatusDisplay()
        self.interrupted = False  # Shared interrupt flag
        self.original_signal_handler = None
        
        # Cache setup
        self.cache_dir = Path(f".cache/{owner}/{repo}")
        cache_existed = self.cache_dir.exists()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_expiry_days = 7  # 1 week
        
        # Inform user about cache status
        if not cache_existed:
            # New cache directory created
            pass  # Don't show message for new cache - will be shown when first cache hit occurs
        else:
            # Using existing cache
            cache_files = list(self.cache_dir.glob("*.cache"))
            if cache_files:
                # Show cache info immediately if we have existing cache
                print(f"💾 Using cache directory: {self.cache_dir.name} ({len(cache_files)} cached files)")
            else:
                print(f"💾 Cache directory exists but empty: {self.cache_dir.name}")
        
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
                cache_files = list(self.cache_dir.glob("*.cache"))
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
    
    def _fetch_issues_simple_pagination(self, state: str, since: Optional[str], limit: Optional[int], 
                                       log_file, sample_logged: int) -> List[Dict]:
        """Fallback method using simple page-based pagination for smaller repositories"""
        issues = []
        page = 1
        
        while True:
            # Check for interrupt at the start of each page
            self._check_interrupted()
            
            # Safety limit to prevent infinite loops - allow for large repos
            if page > 500:  # Allow up to 50,000 issues (500 pages * 100 per page)
                self.status.update("🛑 Reached page limit (500), stopping pagination", style="yellow")
                break
            
            # Update status for current page fetch
            self.status.update(f"📥 Fetching page {page} (fallback mode)...", style="cyan")
            
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
            self.status.update(f"📊 Page {page}: {len(raw_batch)} items ({len(filtered_batch)} issues) | Total: {len(issues)} issues", style="cyan")
            page += 1
            
            # Check if we hit the limit
            if limit and len(issues) >= limit:
                issues = issues[:limit]  # Trim to exact limit
                self.status.update(f"🎯 Reached limit of {limit} issues, stopping", style="yellow")
                break
            
            # Check if we got fewer than requested items (last page)
            if len(raw_batch) < 100:
                break
        
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
    
    def fetch_pr_timeline(self, pr_number: int) -> List[Dict]:
        """Fetch timeline events for a pull request"""
        try:
            url = f"{self.base_url}/repos/{self.owner}/{self.repo}/pulls/{pr_number}/timeline"
            return self._make_request(url)
        except Exception:
            return []
    
    def fetch_pr_reviews(self, pr_number: int) -> List[Dict]:
        """Fetch reviews for a pull request"""
        try:
            url = f"{self.base_url}/repos/{self.owner}/{self.repo}/pulls/{pr_number}/reviews"
            return self._make_request(url)
        except Exception:
            return []
    
    def _make_graphql_request(self, query: str, variables: Dict = None) -> Dict:
        """Make a GraphQL request to GitHub API"""
        url = "https://api.github.com/graphql"
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        response = self.graphql_session.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        
        if "errors" in result:
            raise Exception(f"GraphQL errors: {result['errors']}")
            
        return result.get("data", {})
    
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
                  items(first: 100{cursor_arg}) {{
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
    
    def enrich_issues_with_project_data(self, issues: List[Dict]) -> List[Dict]:
        """Enrich issues with project board information"""
        self.status.print("🔄 Fetching project board data...", style="cyan")
        
        # Fetch all projects (both org and repo level)
        org_projects = self.fetch_organization_projects()
        repo_projects = self.fetch_repository_projects()
        all_projects = org_projects + repo_projects
        
        if not all_projects:
            self.status.print("⚠️  No projects found or accessible", style="yellow")
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
    
    def extract_work_start_date(self, issue: Dict) -> Optional[datetime]:
        """Determine when work actually started on an issue"""
        issue_number = issue['number']
        created_at = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
        
        work_start_candidates = []
        
        # Check for interrupt before potentially long operations
        if self.interrupted:
            return None  # Return None instead of raising exception to allow partial completion
        
        # Fetch events once and reuse (avoids duplicate API calls)
        events = None
        try:
            events = self.fetch_issue_events(issue_number)
        except (InterruptedException, Exception):
            # Continue processing without event data if interrupted or error occurs
            pass
        
        # Check assignment date from events
        if issue.get('assignee') and events:
            try:
                for event in events:
                    if event['event'] == 'assigned':
                        assigned_at = datetime.fromisoformat(event['created_at'].replace('Z', '+00:00'))
                        work_start_candidates.append(assigned_at)
                        break
            except Exception:
                pass
        
        # Check first commit date (only if commit search is available)
        if self.commit_search_available is not False:  # Only try if not explicitly disabled
            try:
                commits = self.fetch_commits_for_issue(issue_number)
                if commits:
                    first_commit_date = datetime.fromisoformat(
                        commits[0]['commit']['committer']['date'].replace('Z', '+00:00')
                    )
                    work_start_candidates.append(first_commit_date)
            except (InterruptedException, Exception):
                # Continue processing without commit data if interrupted or error occurs
                pass
        
        # Check for labeled as "in progress" or similar from cached events
        if events:
            try:
                for event in events:
                    if (event['event'] == 'labeled' and 
                        event.get('label', {}).get('name', '').lower() in 
                        ['in progress', 'in-progress', 'started', 'working']):
                        labeled_at = datetime.fromisoformat(event['created_at'].replace('Z', '+00:00'))
                        work_start_candidates.append(labeled_at)
                        break
            except Exception:
                pass
        
        # Return the earliest valid work start date
        # Work start must be after creation and before closure (if closed)
        closed_at = None
        if issue.get('closed_at'):
            closed_at = datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00'))
        
        valid_dates = []
        for date in work_start_candidates:
            if date >= created_at:  # Must be after creation
                if closed_at is None or date <= closed_at:  # Must be before closure (if closed)
                    valid_dates.append(date)
        
        return min(valid_dates) if valid_dates else None
    
    def _extract_assignment_date(self, events: List[Dict]) -> Optional[datetime]:
        """Extract the first assignment date from events"""
        for event in events:
            if event.get('event') == 'assigned':
                return datetime.fromisoformat(event['created_at'].replace('Z', '+00:00'))
        return None
    
    def _extract_first_commit_date(self, commits: List[Dict]) -> Optional[datetime]:
        """Extract the first commit date"""
        if commits:
            commit_dates = []
            for commit in commits:
                if commit.get('commit', {}).get('author', {}).get('date'):
                    date_str = commit['commit']['author']['date']
                    commit_dates.append(datetime.fromisoformat(date_str.replace('Z', '+00:00')))
            return min(commit_dates) if commit_dates else None
        return None
    
    def _extract_first_pr_date(self, prs: List[Dict]) -> Optional[datetime]:
        """Extract the first PR creation date"""
        if prs:
            pr_dates = []
            for pr in prs:
                if pr.get('created_at'):
                    pr_dates.append(datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')))
            return min(pr_dates) if pr_dates else None
        return None
    
    def _determine_stage_type(self, current_milestone: str, next_milestone: str) -> Tuple[str, str]:
        """Determine stage type (wait/work) and name based on milestone transitions"""
        # Define stage progressions
        stage_mapping = {
            ('created', 'assigned'): ('wait', 'Requirement Review'),
            ('created', 'development_started'): ('wait', 'Planning & Assignment'),
            ('created', 'review_started'): ('wait', 'Planning & Development'),
            ('created', 'closed'): ('wait', 'Complete Lifecycle'),
            ('assigned', 'development_started'): ('work', 'Development Planning'),
            ('assigned', 'review_started'): ('work', 'Development'),
            ('assigned', 'closed'): ('work', 'Development & Deployment'),
            ('development_started', 'review_started'): ('work', 'Active Development'),
            ('development_started', 'closed'): ('work', 'Development & Integration'),
            ('review_started', 'closed'): ('wait', 'Code Review & Deployment'),
        }
        
        key = (current_milestone, next_milestone)
        return stage_mapping.get(key, ('wait', f'{current_milestone.title()} to {next_milestone.title()}'))
    
    def analyze_stage_segments(self, issue: Dict) -> List[StageSegment]:
        """Analyze stage progression for an issue: create -> wait -> stage -> wait -> another stage -> wait..."""
        segments = []
        issue_number = issue['number']
        
        try:
            # Get basic timeline data
            created_at = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
            closed_at = None
            if issue.get('closed_at'):
                closed_at = datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00'))
            
            # Get events, commits, and PRs for milestone detection
            events = self.fetch_issue_events(issue_number)
            commits = self.fetch_commits_for_issue(issue_number)
            prs = self.fetch_pull_requests_for_issue(issue_number)
            
            # Extract key milestone dates
            assignment_date = self._extract_assignment_date(events)
            first_commit_date = self._extract_first_commit_date(commits)
            first_pr_date = self._extract_first_pr_date(prs)
            
            # Build stage progression timeline
            milestones = []
            
            # Always start with creation
            milestones.append(('created', created_at))
            
            # Add assignment if it exists
            if assignment_date:
                milestones.append(('assigned', assignment_date))
            
            # Add first commit if it exists
            if first_commit_date:
                milestones.append(('development_started', first_commit_date))
            
            # Add first PR if it exists
            if first_pr_date:
                milestones.append(('review_started', first_pr_date))
            
            # Add closure if closed
            if closed_at:
                milestones.append(('closed', closed_at))
            
            # Sort milestones by time
            milestones.sort(key=lambda x: x[1])
            
            # Create stage segments from milestone pairs
            for i in range(len(milestones) - 1):
                current_milestone, current_time = milestones[i]
                next_milestone, next_time = milestones[i + 1]
                
                # Determine stage type and name
                stage_type, stage_name = self._determine_stage_type(current_milestone, next_milestone)
                
                duration = (next_time - current_time).total_seconds() / (24 * 3600)
                
                segments.append(StageSegment(
                    stage_name=stage_name,
                    stage_type=stage_type,
                    start_time=current_time,
                    end_time=next_time,
                    duration_days=duration
                ))
            
            return segments
            
        except Exception as e:
            # Return empty list if analysis fails
            return []
    
    def calculate_cycle_times(self, issues: List[Dict], fast_mode: bool = False) -> List[CycleTimeMetrics]:
        """Calculate cycle time metrics for all issues"""
        metrics = []
        
        mode_text = " (fast mode - skipping work start detection)" if fast_mode else ""
        self.status.print(f"🔄 Calculating cycle times for {len(issues)} issues{mode_text}...")
        if not fast_mode:
            self.status.print("⌨️  Press Ctrl+C to interrupt and generate report with issues processed so far")
        
        # Reset interrupt flag for this stage and set up handler
        self.interrupted = False
        self._setup_interrupt_handler()
        
        self.status.start("⏳ Processing cycle times...")
        
        try:
            for i, issue in enumerate(issues):
                # Check for interrupt every 10 issues
                if i % 10 == 0:
                    self._check_interrupted()
                    progress_percent = (i / len(issues)) * 100
                    self.status.update(f"⚙️  Processing issue {i+1}/{len(issues)} ({progress_percent:.1f}%) - #{issue['number']}", style="cyan")
                
                created_at = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
                closed_at = None
                if issue['closed_at']:
                    closed_at = datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00'))
                
                work_started_at = None if fast_mode else self.extract_work_start_date(issue)
                
                # Calculate lead time (creation to closure)
                lead_time_days = None
                if closed_at:
                    lead_time_days = (closed_at - created_at).total_seconds() / (24 * 3600)
                
                # Calculate cycle time (work start to closure)
                cycle_time_days = None
                if closed_at and work_started_at:
                    cycle_time_days = (closed_at - work_started_at).total_seconds() / (24 * 3600)
                    # Safety check: if cycle time is negative, something went wrong - set to None
                    if cycle_time_days < 0:
                        cycle_time_days = None
                
                labels = [label['name'] for label in issue.get('labels', [])]
                assignee = issue.get('assignee', {}).get('login') if issue.get('assignee') else None
                milestone = issue.get('milestone', {}).get('title') if issue.get('milestone') else None
                
                # Analyze stage segments for closed issues
                stage_segments = None
                total_work_time = None
                total_wait_time = None
                work_efficiency_ratio = None
                
                if closed_at:  # Only analyze completed issues
                    stage_segments = self.analyze_stage_segments(issue)
                    if stage_segments:
                        work_times = [seg.duration_days for seg in stage_segments if seg.stage_type == 'work' and seg.duration_days]
                        wait_times = [seg.duration_days for seg in stage_segments if seg.stage_type == 'wait' and seg.duration_days]
                        
                        total_work_time = sum(work_times) if work_times else 0
                        total_wait_time = sum(wait_times) if wait_times else 0
                        
                        if total_work_time + total_wait_time > 0:
                            work_efficiency_ratio = total_work_time / (total_work_time + total_wait_time)
                
                # Extract project data if available
                project_title = None
                project_status = None
                project_iteration = None
                project_assignees = None
                
                project_data = issue.get('project_data', [])
                if project_data:
                    # Use the first project if multiple projects exist
                    first_project = project_data[0]
                    project_title = first_project.get('project_title')
                    
                    # Extract common field values
                    field_values = first_project.get('field_values', {})
                    project_status = field_values.get('Status')
                    project_iteration = field_values.get('Iteration') or field_values.get('Sprint')
                    
                    # Try to get assignees from project data, fall back to issue assignees
                    if 'assignees' in first_project:
                        project_assignees = first_project['assignees']
                
                metrics.append(CycleTimeMetrics(
                    issue_number=issue['number'],
                    title=issue['title'],
                    created_at=created_at,
                    closed_at=closed_at,
                    work_started_at=work_started_at,
                    lead_time_days=lead_time_days,
                    cycle_time_days=cycle_time_days,
                    labels=labels,
                    assignee=assignee,
                    milestone=milestone,
                    state=issue['state'],
                    stage_segments=stage_segments,
                    total_work_time_days=total_work_time,
                    total_wait_time_days=total_wait_time,
                    work_efficiency_ratio=work_efficiency_ratio,
                    project_title=project_title,
                    project_status=project_status,
                    project_iteration=project_iteration,
                    project_assignees=project_assignees
                ))
        
        except InterruptedException:
            self.status.stop()
            self.status.print(f"⚠️  User interrupted cycle time calculation! Proceeding with {len(metrics)} issues processed so far...", style="yellow bold")
        
        finally:
            # Restore original signal handler
            self._restore_interrupt_handler()
            # Stop status display
            self.status.stop()
        
        self.status.print(f"✅ Cycle time calculation complete: {len(metrics)} issues processed", style="green bold")
        return metrics
    
    def _calculate_monthly_cycle_trends(self, closed_issues: pd.DataFrame) -> pd.DataFrame:
        """Calculate monthly cycle time averages with rolling 6-month trends"""
        # Filter issues with cycle time data
        cycle_data = closed_issues[closed_issues['cycle_time_days'].notna()].copy()
        
        if cycle_data.empty:
            return pd.DataFrame()
        
        # Group by month based on closure date
        cycle_data['closed_month'] = pd.to_datetime(cycle_data['closed_at']).dt.to_period('M')
        monthly_avg = cycle_data.groupby('closed_month')['cycle_time_days'].agg(['mean', 'count']).reset_index()
        monthly_avg.columns = ['month', 'monthly_avg', 'issue_count']
        
        # Filter out months with very few issues (less than 3) for more reliable averages
        monthly_avg = monthly_avg[monthly_avg['issue_count'] >= 3]
        
        if len(monthly_avg) < 6:
            return pd.DataFrame()
        
        # Set month as index and calculate 6-month rolling average
        monthly_avg = monthly_avg.set_index('month')
        monthly_avg['rolling_6m'] = monthly_avg['monthly_avg'].rolling(window=6, min_periods=3).mean()
        
        # Convert period index to timestamp for plotting
        monthly_avg.index = monthly_avg.index.to_timestamp()
        
        return monthly_avg
    
    def _extract_issue_type(self, labels: List[str]) -> str:
        """Extract issue type from labels"""
        type_labels = [label for label in labels if label.startswith('type/')]
        if type_labels:
            return type_labels[0].replace('type/', '')
        return 'untyped'
    
    def _extract_team(self, labels: List[str]) -> str:
        """Extract team from labels"""
        team_labels = [label for label in labels if label.startswith('team/')]
        if team_labels:
            return team_labels[0].replace('team/', '')
        return 'unassigned'
    
    def _extract_product_area(self, labels: List[str]) -> str:
        """Extract product area from labels"""
        product_labels = [label for label in labels if label.startswith('product/')]
        if product_labels:
            return product_labels[0].replace('product/', '')
        return 'unspecified'
    
    def _extract_priority(self, labels: List[str]) -> str:
        """Extract priority from labels"""
        priority_labels = [label for label in labels if label.upper() in ['P0', 'P1', 'P2', 'P3', 'P4']]
        if priority_labels:
            return priority_labels[0].upper()
        security_labels = [label for label in labels if 'security' in label.lower()]
        if security_labels:
            return 'SECURITY'
        return 'normal'
    
    def _analyze_cycle_time_segments(self, df: pd.DataFrame) -> Dict:
        """Analyze cycle times by different segments"""
        closed_issues = df[df['state'] == 'closed'].copy()
        
        if len(closed_issues) == 0:
            return {}
        
        # Extract categorization data
        closed_issues['issue_type'] = closed_issues['labels'].apply(
            lambda x: self._extract_issue_type(x.split(', ') if x else [])
        )
        closed_issues['team'] = closed_issues['labels'].apply(
            lambda x: self._extract_team(x.split(', ') if x else [])
        )
        closed_issues['product_area'] = closed_issues['labels'].apply(
            lambda x: self._extract_product_area(x.split(', ') if x else [])
        )
        closed_issues['priority'] = closed_issues['labels'].apply(
            lambda x: self._extract_priority(x.split(', ') if x else [])
        )
        
        analysis = {}
        
        # Cycle time by issue type
        type_analysis = closed_issues.groupby('issue_type')['cycle_time_days'].agg(['count', 'mean', 'median']).round(1)
        type_analysis = type_analysis[type_analysis['count'] >= 2]  # Filter out single-issue types
        analysis['by_issue_type'] = type_analysis.to_dict('index')
        
        # Cycle time by team
        team_analysis = closed_issues.groupby('team')['cycle_time_days'].agg(['count', 'mean', 'median']).round(1)
        team_analysis = team_analysis[team_analysis['count'] >= 2]
        analysis['by_team'] = team_analysis.to_dict('index')
        
        # Cycle time by product area
        product_analysis = closed_issues.groupby('product_area')['cycle_time_days'].agg(['count', 'mean', 'median']).round(1)
        product_analysis = product_analysis[product_analysis['count'] >= 2]
        analysis['by_product_area'] = product_analysis.to_dict('index')
        
        # Cycle time by priority
        priority_analysis = closed_issues.groupby('priority')['cycle_time_days'].agg(['count', 'mean', 'median']).round(1)
        priority_analysis = priority_analysis[priority_analysis['count'] >= 1]  # Keep single P1/security issues
        analysis['by_priority'] = priority_analysis.to_dict('index')
        
        return analysis
    
    def _analyze_assignment_patterns(self, df: pd.DataFrame) -> Dict:
        """Analyze assignment patterns for workflow insights"""
        analysis = {}
        
        # Time to assignment analysis
        df_copy = df.copy()
        df_copy['time_to_assignment'] = None
        df_copy['assignment_changes'] = 0
        df_copy['max_assignees'] = 0
        
        assignment_times = []
        reassignment_counts = []
        collaboration_counts = []
        
        for _, issue in df_copy.iterrows():
            if issue['assignee']:  # Has been assigned
                try:
                    # Get assignment events for this issue
                    events = self.fetch_issue_events(issue['issue_number'])
                    assignment_events = [e for e in events if e.get('event') == 'assigned']
                    
                    if assignment_events:
                        # Time to first assignment
                        first_assignment = min(assignment_events, key=lambda x: x['created_at'])
                        created_at = datetime.fromisoformat(issue['created_at'].isoformat())
                        assigned_at = datetime.fromisoformat(first_assignment['created_at'].replace('Z', '+00:00'))
                        time_to_assign = (assigned_at - created_at).total_seconds() / (24 * 3600)
                        assignment_times.append(time_to_assign)
                        
                        # Assignment stability (number of reassignments)
                        reassignment_counts.append(len(assignment_events) - 1)  # Subtract initial assignment
                        
                        # Max concurrent assignees (collaboration indicator)
                        # This is simplified - would need more complex logic to track concurrent assignments
                        collaboration_counts.append(1)  # Placeholder
                        
                except Exception:
                    # Skip if we can't fetch events for this issue
                    continue
        
        if assignment_times:
            analysis['time_to_assignment'] = {
                'mean_days': round(sum(assignment_times) / len(assignment_times), 1),
                'median_days': round(sorted(assignment_times)[len(assignment_times)//2], 1),
                'max_days': round(max(assignment_times), 1),
                'count': len(assignment_times)
            }
        else:
            analysis['time_to_assignment'] = {'mean_days': 'N/A', 'median_days': 'N/A', 'max_days': 'N/A', 'count': 0}
        
        if reassignment_counts:
            analysis['assignment_stability'] = {
                'mean_reassignments': round(sum(reassignment_counts) / len(reassignment_counts), 1),
                'issues_with_reassignments': sum(1 for x in reassignment_counts if x > 0),
                'total_issues_analyzed': len(reassignment_counts),
                'stability_rate': round((len(reassignment_counts) - sum(1 for x in reassignment_counts if x > 0)) / len(reassignment_counts) * 100, 1)
            }
        else:
            analysis['assignment_stability'] = {'mean_reassignments': 'N/A', 'issues_with_reassignments': 0, 'total_issues_analyzed': 0, 'stability_rate': 'N/A'}
        
        # Team collaboration analysis (issues with multiple assignees)
        multi_assignee_issues = len(df[df['assignee'].str.contains(',', na=False)]) if 'assignee' in df.columns else 0
        total_assigned_issues = len(df[df['assignee'].notna()]) if 'assignee' in df.columns else 0
        
        analysis['team_collaboration'] = {
            'multi_assignee_issues': multi_assignee_issues,
            'total_assigned_issues': total_assigned_issues,
            'collaboration_rate': round(multi_assignee_issues / total_assigned_issues * 100, 1) if total_assigned_issues > 0 else 0
        }
        
        return analysis
    
    def _analyze_status_progression(self, df: pd.DataFrame) -> Dict:
        """Analyze time spent in different status states"""
        analysis = {}
        
        needs_review_times = []
        queue_times = []  # Time from creation to work start
        
        for _, issue in df.iterrows():
            try:
                # Get timeline events for this issue
                events = self.fetch_issue_events(issue['issue_number'])
                
                # Analyze needs-review time
                review_labels = [e for e in events if e.get('event') == 'labeled' and 
                               e.get('label', {}).get('name', '').lower() in ['status/needs-review', 'needs-review']]
                review_removals = [e for e in events if e.get('event') == 'unlabeled' and 
                                 e.get('label', {}).get('name', '').lower() in ['status/needs-review', 'needs-review']]
                
                # Calculate time in review state (simplified - just first review period)
                if review_labels and review_removals:
                    first_review = min(review_labels, key=lambda x: x['created_at'])
                    first_removal = min([r for r in review_removals if r['created_at'] > first_review['created_at']], 
                                      key=lambda x: x['created_at'], default=None)
                    
                    if first_removal:
                        review_start = datetime.fromisoformat(first_review['created_at'].replace('Z', '+00:00'))
                        review_end = datetime.fromisoformat(first_removal['created_at'].replace('Z', '+00:00'))
                        review_time = (review_end - review_start).total_seconds() / (24 * 3600)
                        needs_review_times.append(review_time)
                
                # Analyze queue time (creation to work start)
                if issue['work_started_at'] and issue['created_at']:
                    created_at = datetime.fromisoformat(issue['created_at'].isoformat())
                    work_started_at = datetime.fromisoformat(issue['work_started_at'].isoformat())
                    queue_time = (work_started_at - created_at).total_seconds() / (24 * 3600)
                    queue_times.append(queue_time)
                    
            except Exception:
                # Skip if we can't analyze this issue
                continue
        
        # Status progression analysis
        if needs_review_times:
            analysis['needs_review_time'] = {
                'mean_days': round(sum(needs_review_times) / len(needs_review_times), 1),
                'median_days': round(sorted(needs_review_times)[len(needs_review_times)//2], 1),
                'max_days': round(max(needs_review_times), 1),
                'count': len(needs_review_times)
            }
        else:
            analysis['needs_review_time'] = {'mean_days': 'N/A', 'median_days': 'N/A', 'max_days': 'N/A', 'count': 0}
        
        if queue_times:
            analysis['queue_time'] = {
                'mean_days': round(sum(queue_times) / len(queue_times), 1),
                'median_days': round(sorted(queue_times)[len(queue_times)//2], 1),
                'max_days': round(max(queue_times), 1),
                'count': len(queue_times)
            }
        else:
            analysis['queue_time'] = {'mean_days': 'N/A', 'median_days': 'N/A', 'max_days': 'N/A', 'count': 0}
        
        return analysis
    
    def _create_timeline_visualization(self, df: pd.DataFrame, output_dir: str):
        """Create timeline visualization showing stage progression trends over time"""
        closed_issues = df[df['state'] == 'closed'].copy()
        
        if len(closed_issues) == 0:
            return
        
        # Extract issue types and add closure month for trend analysis
        closed_issues['issue_type'] = closed_issues['labels'].apply(
            lambda x: self._extract_issue_type(x.split(', ') if x else [])
        )
        
        # Add closure month for trend analysis
        closed_issues['closed_at'] = pd.to_datetime(closed_issues['closed_at'])
        closed_issues['closure_month'] = closed_issues['closed_at'].dt.to_period('M')
        
        # Filter to issue types with at least 5 issues for meaningful trends
        type_counts = closed_issues['issue_type'].value_counts()
        valid_types = type_counts[type_counts >= 5].index.tolist()
        closed_issues = closed_issues[closed_issues['issue_type'].isin(valid_types)]
        
        if len(closed_issues) == 0:
            return
        
        # Create timeline data using stage segments
        timeline_data = []
        metrics_by_issue = {metric.issue_number: metric for metric in self.last_analyzed_metrics 
                           if metric.stage_segments and metric.state == 'closed'}
        
        for _, issue in closed_issues.iterrows():
            issue_number = issue['issue_number']
            if issue_number in metrics_by_issue:
                metric = metrics_by_issue[issue_number]
                
                # Aggregate stage data by type (work vs wait)
                total_work_time = 0
                total_wait_time = 0
                stage_breakdown = {}
                
                for segment in metric.stage_segments:
                    duration = segment.duration_days or 0
                    stage_name = segment.stage_name
                    
                    # Track individual stages
                    if stage_name not in stage_breakdown:
                        stage_breakdown[stage_name] = 0
                    stage_breakdown[stage_name] += duration
                    
                    # Aggregate by work/wait type
                    if segment.stage_type == 'work':
                        total_work_time += duration
                    else:
                        total_wait_time += duration
                
                total_time = total_work_time + total_wait_time
                efficiency_ratio = total_work_time / total_time if total_time > 0 else 0
                
                timeline_entry = {
                    'issue_type': issue['issue_type'],
                    'queue_time': total_wait_time,  # Renamed for compatibility
                    'work_time': total_work_time,   # Renamed for compatibility
                    'total_time': total_time,
                    'closure_month': issue['closure_month'],
                    'efficiency_ratio': efficiency_ratio
                }
                
                # Add individual stage data
                timeline_entry.update(stage_breakdown)
                timeline_data.append(timeline_entry)
        
        if not timeline_data:
            return
        
        timeline_df = pd.DataFrame(timeline_data)
        
        # Create temporal trend visualization (3 panels)
        fig, axes = plt.subplots(3, 1, figsize=(15, 16))
        fig.suptitle(f'Stage Progression Trends - {self.owner}/{self.repo}', fontsize=16, fontweight='bold')
        
        # 1. Monthly wait time trends by issue type (last 12 months)
        print("\n📈 Analyzing temporal trends in stage progression times...")
        
        # Get last 12 months of data
        latest_month = timeline_df['closure_month'].max()
        twelve_months_ago = latest_month - 11  # 12 months including current
        recent_data = timeline_df[timeline_df['closure_month'] >= twelve_months_ago]
        
        # 1. Monthly stage progression stacked bar chart
        self._create_monthly_stage_progression_chart(timeline_df, recent_data, axes[0])
        
        # 2. Monthly stage progression by issue type stacked bar chart  
        self._create_monthly_stage_by_type_chart(timeline_df, recent_data, axes[1])
        
        # 3. Detailed stage breakdown by issue type
        self._create_detailed_stage_breakdown_chart(timeline_df, axes[2])
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/timeline_analysis.png", dpi=300, bbox_inches='tight')
        plt.close()
        
        # Generate trend insights for console output
        self._analyze_wait_time_trends(timeline_df)
        
        return timeline_df
    
    def _analyze_wait_time_trends(self, timeline_df: pd.DataFrame):
        """Analyze and report wait time trends"""
        if timeline_df.empty:
            return
        
        print("\n📊 Wait Time Trend Insights:")
        print("=" * 40)
        
        # Overall trend analysis
        latest_month = timeline_df['closure_month'].max()
        six_months_ago = latest_month - 5
        twelve_months_ago = latest_month - 11
        
        # Compare recent 6 months vs previous 6 months
        recent_6m = timeline_df[timeline_df['closure_month'] >= six_months_ago]
        previous_6m = timeline_df[
            (timeline_df['closure_month'] >= twelve_months_ago) & 
            (timeline_df['closure_month'] < six_months_ago)
        ]
        
        if not recent_6m.empty and not previous_6m.empty:
            recent_wait = recent_6m['queue_time'].mean()
            previous_wait = previous_6m['queue_time'].mean()
            recent_efficiency = recent_6m['efficiency_ratio'].mean()
            previous_efficiency = previous_6m['efficiency_ratio'].mean()
            
            wait_change = recent_wait - previous_wait
            efficiency_change = recent_efficiency - previous_efficiency
            
            print(f"📈 Overall Trends (6-month comparison):")
            print(f"  Wait Time: {previous_wait:.1f}d → {recent_wait:.1f}d ({wait_change:+.1f}d)")
            print(f"  Efficiency: {previous_efficiency:.2%} → {recent_efficiency:.2%} ({efficiency_change:+.2%})")
            
            # Determine overall trend
            if wait_change > 2:
                print(f"  🚨 ALERT: Wait times are increasing significantly")
            elif wait_change < -2:
                print(f"  ✅ GOOD: Wait times are decreasing")
            else:
                print(f"  ➡️  STABLE: Wait times are relatively stable")
            
            # Efficiency trend
            if efficiency_change < -0.05:
                print(f"  ⚠️  WARNING: Work efficiency is declining")
            elif efficiency_change > 0.05:
                print(f"  📈 IMPROVING: Work efficiency is increasing")
            
        # Identify problematic issue types
        print(f"\n🎯 Issue Type Performance:")
        type_analysis = timeline_df.groupby('issue_type').agg({
            'queue_time': ['mean', 'count'],
            'efficiency_ratio': 'mean'
        }).round(2)
        
        # Flatten column names
        type_analysis.columns = ['avg_wait', 'count', 'avg_efficiency']
        type_analysis = type_analysis[type_analysis['count'] >= 5].sort_values('avg_wait', ascending=False)
        
        print(f"  Highest Wait Times:")
        for issue_type, data in type_analysis.head(3).iterrows():
            print(f"    • {issue_type}: {data['avg_wait']:.1f}d wait, {data['avg_efficiency']:.1%} efficiency (n={int(data['count'])})")
        
        print(f"  Best Efficiency:")
        best_efficiency = type_analysis.sort_values('avg_efficiency', ascending=False)
        for issue_type, data in best_efficiency.head(3).iterrows():
            print(f"    • {issue_type}: {data['avg_efficiency']:.1%} efficiency, {data['avg_wait']:.1f}d wait (n={int(data['count'])})")
    
    def _generate_ai_recommendations(self, df: pd.DataFrame, lead_time_stats: pd.Series, 
                                   cycle_time_stats: pd.Series, monthly_cycle_data: pd.DataFrame) -> List[str]:
        """Generate AI-powered recommendations based on cycle time analysis"""
        openai_api_key = os.getenv('OPENAI_API_KEY')
        openai_model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        
        if not OPENAI_AVAILABLE or not openai_api_key:
            return [
                "Focus on reducing queue time (creation to work start)",
                "Identify and address bottlenecks in high-cycle-time issues",
                "Consider breaking down large issues (>90th percentile cycle time)",
                "Implement clearer work-in-progress tracking"
            ]
        
        try:
            # Prepare analysis data
            closed_issues = df[df['state'] == 'closed']
            
            analysis_summary = {
                "repository": f"{self.owner}/{self.repo}",
                "total_issues": len(df),
                "closed_issues": len(closed_issues),
                "lead_time_avg": round(lead_time_stats['mean'], 1) if not lead_time_stats.empty else "N/A",
                "lead_time_median": round(lead_time_stats['50%'], 1) if not lead_time_stats.empty else "N/A",
                "cycle_time_avg": round(cycle_time_stats['mean'], 1) if not cycle_time_stats.empty else "N/A",
                "cycle_time_median": round(cycle_time_stats['50%'], 1) if not cycle_time_stats.empty else "N/A",
                "issues_without_assignee": len(df[df['assignee'].isna()]),
                "issues_with_cycle_time": len(df[df['cycle_time_days'].notna()]),
                "avg_comments": round(df['comments'].mean(), 1) if 'comments' in df.columns else "N/A",
                "monthly_trend": "improving" if not monthly_cycle_data.empty and len(monthly_cycle_data) >= 2 and monthly_cycle_data['rolling_6m'].iloc[-1] < monthly_cycle_data['rolling_6m'].iloc[-2] else "stable/worsening",
            }
            
            # Get top assignees by cycle time
            if not cycle_time_stats.empty:
                assignee_stats = closed_issues.groupby('assignee')['cycle_time_days'].agg(['mean', 'count']).sort_values('mean')
                analysis_summary["top_performers"] = assignee_stats.head(3).to_dict() if not assignee_stats.empty else "N/A"
                analysis_summary["bottlenecks"] = assignee_stats.tail(3).to_dict() if not assignee_stats.empty else "N/A"
            
            # Create prompt for AI
            prompt = f"""
            Analyze this GitHub repository's issue cycle time data and provide 4-6 specific, actionable recommendations to improve development velocity and reduce cycle times.

            Data Summary:
            - Repository: {analysis_summary['repository']}
            - Total Issues: {analysis_summary['total_issues']}
            - Closed Issues: {analysis_summary['closed_issues']}
            - Average Lead Time: {analysis_summary['lead_time_avg']} days
            - Average Cycle Time: {analysis_summary['cycle_time_avg']} days
            - Issues without assignee: {analysis_summary['issues_without_assignee']}
            - Issues with detectable work start: {analysis_summary['issues_with_cycle_time']}
            - Monthly trend: {analysis_summary['monthly_trend']}

            Focus on:
            1. Process improvements based on the data patterns
            2. Workflow bottlenecks and how to address them
            3. Assignment and work-in-progress practices
            4. Specific metrics-driven suggestions

            Return only a bullet-point list of recommendations, no other text.
            """

            client = openai.OpenAI(api_key=openai_api_key)
            response = client.chat.completions.create(
                model=openai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7
            )
            
            recommendations_text = response.choices[0].message.content.strip()
            
            # Parse into list
            recommendations = []
            for line in recommendations_text.split('\n'):
                line = line.strip()
                if line and (line.startswith('-') or line.startswith('•') or line.startswith('*')):
                    recommendations.append(line[1:].strip())
                elif line and not line.startswith('#'):
                    recommendations.append(line)
            
            return recommendations[:6]  # Limit to 6 recommendations
            
        except Exception as e:
            print(f"Failed to generate AI recommendations: {e}")
            return [
                "Focus on reducing queue time (creation to work start)",
                "Identify and address bottlenecks in high-cycle-time issues",
                "Consider breaking down large issues (>90th percentile cycle time)",
                "Implement clearer work-in-progress tracking"
            ]
    
    def analyze_project_workflow(self, metrics: List[CycleTimeMetrics]):
        """Analyze GitHub Projects workflow efficiency"""
        workflow_data = []
        
        for metric in metrics:
            if metric.project_title and metric.state == 'open':
                workflow_data.append({
                    'issue_number': metric.issue_number,
                    'title': metric.title,
                    'product_area': self._get_product_area_from_labels(metric.labels),
                    'project_status': metric.project_status or 'Unknown',
                    'created_at': metric.created_at,
                    'assignee': metric.assignee,
                    'age_days': (datetime.now(timezone.utc) - metric.created_at).days
                })
        
        if not workflow_data:
            return None
            
        workflow_stages = [
            'Dev Backlog', 'Dev In Progress', 'Code Review', 
            'To Deploy', 'Verify in Production', 'Done'
        ]
        
        # Analyze workflow distribution
        status_distribution = {}
        total_issues = len(workflow_data)
        
        for stage in workflow_stages:
            count = sum(1 for item in workflow_data if item['project_status'] == stage)
            status_distribution[stage] = {
                'count': count,
                'percentage': (count / total_issues * 100) if total_issues > 0 else 0
            }
        
        # Analyze bottlenecks (>15% of work)
        bottlenecks = []
        bottleneck_threshold = total_issues * 0.15
        
        for stage in workflow_stages[:-1]:  # Exclude 'Done'
            if status_distribution[stage]['count'] > bottleneck_threshold:
                bottlenecks.append({
                    'stage': stage,
                    'count': status_distribution[stage]['count'],
                    'percentage': status_distribution[stage]['percentage']
                })
        
        # Analyze work age by stage
        age_analysis = {}
        for stage in workflow_stages[:-1]:
            stage_items = [item for item in workflow_data if item['project_status'] == stage]
            if stage_items:
                ages = [item['age_days'] for item in stage_items]
                age_analysis[stage] = {
                    'avg_age': sum(ages) / len(ages),
                    'max_age': max(ages),
                    'stale_count': sum(1 for age in ages if age > 30)
                }
        
        # Assignment analysis
        assigned_count = sum(1 for item in workflow_data if item['assignee'])
        unassigned_count = total_issues - assigned_count
        
        return {
            'total_issues': total_issues,
            'status_distribution': status_distribution,
            'bottlenecks': bottlenecks,
            'age_analysis': age_analysis,
            'assignment': {
                'assigned': assigned_count,
                'unassigned': unassigned_count,
                'unassigned_percentage': (unassigned_count / total_issues * 100) if total_issues > 0 else 0
            },
            'workflow_stages': workflow_stages,
            'workflow_data': workflow_data  # Include raw data for detailed analysis
        }
    
    def analyze_project_workflow_detailed(self, metrics: List[CycleTimeMetrics]):
        """Enhanced workflow analysis with detailed console output"""
        workflow_data = []
        
        for metric in metrics:
            if metric.project_title and metric.state == 'open':
                workflow_data.append({
                    'issue_number': metric.issue_number,
                    'title': metric.title,
                    'product_area': self._get_product_area_from_labels(metric.labels),
                    'project_status': metric.project_status or 'Unknown',
                    'created_at': metric.created_at,
                    'labels': metric.labels,
                    'assignee': metric.assignee
                })
        
        if not workflow_data:
            print("No project workflow data found")
            return None
        
        import pandas as pd
        import numpy as np
        df = pd.DataFrame(workflow_data)
        
        # Define workflow stages in order
        workflow_stages = [
            'Dev Backlog',
            'Dev In Progress', 
            'Code Review',
            'To Deploy',
            'Verify in Production',
            'Done'
        ]
        
        print("🔄 GitHub Projects Workflow Analysis")
        print("=" * 50)
        
        # 1. Current Work Distribution
        print("\n📊 Current Work Distribution by Stage:")
        status_counts = df['project_status'].value_counts()
        for status in workflow_stages:
            count = status_counts.get(status, 0)
            percentage = (count / len(df) * 100) if len(df) > 0 else 0
            print(f"  {status:<20}: {count:>3} issues ({percentage:>5.1f}%)")
        
        # 2. Bottleneck Analysis
        print("\n🚨 Potential Bottlenecks:")
        bottleneck_threshold = len(df) * 0.15  # More than 15% of total work
        
        for status in workflow_stages[:-1]:  # Exclude 'Done'
            count = status_counts.get(status, 0)
            if count > bottleneck_threshold:
                print(f"  ⚠️  {status}: {count} issues ({count/len(df)*100:.1f}% of total work)")
        
        # 3. Work Distribution by Product Area
        print("\n🏗️  Work Distribution by Product Area:")
        product_status = df.groupby(['product_area', 'project_status']).size().unstack(fill_value=0)
        
        for area in product_status.index:
            print(f"\n  {area}:")
            for status in workflow_stages:
                if status in product_status.columns:
                    count = product_status.loc[area, status]
                    if count > 0:
                        print(f"    {status:<20}: {count:>2} issues")
        
        # 4. Age Analysis by Stage
        print("\n⏰ Work Age Analysis (days since created):")
        today = datetime.now(timezone.utc)
        
        for status in workflow_stages[:-1]:  # Exclude 'Done'
            stage_issues = df[df['project_status'] == status]
            if not stage_issues.empty:
                ages = [(today - created).days for created in stage_issues['created_at']]
                avg_age = np.mean(ages)
                max_age = max(ages)
                print(f"  {status:<20}: avg {avg_age:>5.1f} days, oldest {max_age:>3} days")
        
        # 5. Assignment Analysis
        print("\n👥 Assignment Status:")
        assigned_count = df[df['assignee'].notna()].shape[0]
        unassigned_count = df[df['assignee'].isna()].shape[0]
        
        print(f"  Assigned:   {assigned_count:>3} issues ({assigned_count/len(df)*100:>5.1f}%)")
        print(f"  Unassigned: {unassigned_count:>3} issues ({unassigned_count/len(df)*100:>5.1f}%)")
        
        # 6. Stale Work Analysis
        print("\n🕰️  Stale Work (>30 days old):")
        stale_threshold = 30
        
        for status in workflow_stages[:-1]:
            stage_issues = df[df['project_status'] == status]
            if not stage_issues.empty:
                stale_issues = stage_issues[
                    [(today - created).days > stale_threshold for created in stage_issues['created_at']]
                ]
                if not stale_issues.empty:
                    print(f"  {status:<20}: {len(stale_issues):>2} stale issues")
                    for _, issue in stale_issues.head(3).iterrows():  # Show top 3
                        age = (today - issue['created_at']).days
                        print(f"    #{issue['issue_number']}: {issue['title'][:50]}... ({age} days)")
        
        # 7. Workflow Efficiency Recommendations
        print("\n💡 Workflow Efficiency Recommendations:")
        
        # Check for bottlenecks
        in_progress = status_counts.get('Dev In Progress', 0)
        code_review = status_counts.get('Code Review', 0)
        backlog = status_counts.get('Dev Backlog', 0)
        
        if code_review > in_progress * 0.5:
            print("  🔍 Code Review bottleneck: Consider more reviewers or pair programming")
        
        if backlog > (in_progress + code_review) * 2:
            print("  📋 Large backlog: Prioritize and break down large items")
        
        if unassigned_count > assigned_count * 0.3:
            print("  👤 High unassigned work: Improve assignment and capacity planning")
        
        # Check for stale work
        total_stale = sum(
            len(df[(df['project_status'] == status) & 
                   [(today - created).days > stale_threshold for created in df['created_at']]])
            for status in workflow_stages[:-1]
        )
        
        if total_stale > len(df) * 0.1:
            print(f"  🕰️  {total_stale} stale issues: Review and close or re-prioritize old work")
        
        return df
    
    def _get_product_area_from_labels(self, labels):
        """Extract product area from issue labels"""
        labels_lower = [label.lower() for label in labels]
        
        for label in labels_lower:
            if label == 'product/ai':
                return 'AI Agent'
            elif label == 'product/voice':
                return 'Call Fabric'
            elif label == 'product/messaging':
                return 'Messaging'
            elif label == 'product/platform':
                return 'Spaces/Platform'
            elif label == 'product/ucaas':
                return 'PUC & SDK'
            elif label == 'product/video':
                return 'Video'
            elif label == 'project/data-zones':
                return 'Data Zones'
        
        return 'Other'
    
    def load_cycle_data_from_json(self, json_file_path: str) -> List[Dict]:
        """Load cycle time data from JSON file"""
        with open(json_file_path, 'r') as f:
            return json.load(f)
    
    def _create_workflow_visualization(self, workflow_data: List[Dict], output_dir: str):
        """Create workflow visualization with 4 panels"""
        if not workflow_data:
            return
        
        import pandas as pd
        import numpy as np
        df = pd.DataFrame(workflow_data)
        
        if df.empty:
            return
        
        # Set up the plot
        plt.style.use('seaborn-v0_8')
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle(f'GitHub Projects Workflow Analysis - {self.owner}/{self.repo}', fontsize=14, fontweight='bold')
        
        # 1. Status Distribution
        status_counts = df['project_status'].value_counts()
        ax1.bar(range(len(status_counts)), status_counts.values)
        ax1.set_xticks(range(len(status_counts)))
        ax1.set_xticklabels(status_counts.index, rotation=45, ha='right')
        ax1.set_title('Work Distribution by Status')
        ax1.set_ylabel('Number of Issues')
        
        # 2. Product Area Distribution
        product_counts = df['product_area'].value_counts()
        ax2.pie(product_counts.values, labels=product_counts.index, autopct='%1.1f%%')
        ax2.set_title('Work Distribution by Product Area')
        
        # 3. Age by Status
        today = datetime.now(timezone.utc)
        workflow_stages = ['Dev Backlog', 'Dev In Progress', 'Code Review', 'To Deploy', 'Verify in Production']
        
        age_data = []
        for status in workflow_stages:
            stage_issues = df[df['project_status'] == status]
            if not stage_issues.empty:
                ages = [(today - created).days for created in stage_issues['created_at']]
                age_data.extend([(status, age) for age in ages])
        
        if age_data:
            age_df = pd.DataFrame(age_data, columns=['Status', 'Age_Days'])
            import seaborn as sns
            sns.boxplot(data=age_df, x='Status', y='Age_Days', ax=ax3)
            ax3.set_xticklabels(ax3.get_xticklabels(), rotation=45, ha='right')
            ax3.set_title('Work Age Distribution by Status')
            ax3.set_ylabel('Days Since Created')
        
        # 4. Assignment Status
        assignment_data = df.groupby('project_status')['assignee'].apply(lambda x: x.notna().sum()).reindex(workflow_stages, fill_value=0)
        unassigned_data = df.groupby('project_status')['assignee'].apply(lambda x: x.isna().sum()).reindex(workflow_stages, fill_value=0)
        
        x = range(len(workflow_stages))
        ax4.bar(x, assignment_data.values, label='Assigned', alpha=0.7)
        ax4.bar(x, unassigned_data.values, bottom=assignment_data.values, label='Unassigned', alpha=0.7)
        ax4.set_xticks(x)
        ax4.set_xticklabels(workflow_stages, rotation=45, ha='right')
        ax4.set_title('Assignment Status by Workflow Stage')
        ax4.set_ylabel('Number of Issues')
        ax4.legend()
        
        plt.tight_layout()
        plt.savefig(f'{output_dir}/workflow_analysis.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"✅ Workflow visualization saved to: {output_dir}/workflow_analysis.png")
        return df

    def _generate_workflow_section(self, workflow_analysis):
        """Generate HTML section for workflow analysis"""
        if not workflow_analysis:
            return ""
        
        # Status distribution table
        status_rows = ""
        for stage in workflow_analysis['workflow_stages']:
            stage_data = workflow_analysis['status_distribution'][stage]
            status_rows += f"""
            <tr>
                <td>{stage}</td>
                <td>{stage_data['count']}</td>
                <td>{stage_data['percentage']:.1f}%</td>
            </tr>"""
        
        # Bottlenecks section
        bottlenecks_html = ""
        if workflow_analysis['bottlenecks']:
            bottlenecks_html = "<h3>🚨 Workflow Bottlenecks</h3><ul>"
            for bottleneck in workflow_analysis['bottlenecks']:
                bottlenecks_html += f"<li><strong>{bottleneck['stage']}</strong>: {bottleneck['count']} issues ({bottleneck['percentage']:.1f}% of total work)</li>"
            bottlenecks_html += "</ul>"
        else:
            bottlenecks_html = "<h3>✅ No Major Bottlenecks Detected</h3><p>Work is well-distributed across workflow stages.</p>"
        
        # Age analysis table
        age_rows = ""
        for stage, data in workflow_analysis['age_analysis'].items():
            age_rows += f"""
            <tr>
                <td>{stage}</td>
                <td>{data['avg_age']:.1f} days</td>
                <td>{data['max_age']} days</td>
                <td>{data['stale_count']}</td>
            </tr>"""
        
        # Assignment analysis
        assignment = workflow_analysis['assignment']
        assignment_html = f"""
        <h3>👥 Work Assignment Analysis</h3>
        <ul>
            <li><strong>Assigned:</strong> {assignment['assigned']} issues ({100-assignment['unassigned_percentage']:.1f}%)</li>
            <li><strong>Unassigned:</strong> {assignment['unassigned']} issues ({assignment['unassigned_percentage']:.1f}%)</li>
        </ul>
        """
        
        if assignment['unassigned_percentage'] > 30:
            assignment_html += "<p><strong>⚠️ Warning:</strong> High percentage of unassigned work may indicate capacity planning issues.</p>"
        
        return f"""
        <h2>📊 GitHub Projects Workflow Analysis</h2>
        <p>Analysis of {workflow_analysis['total_issues']} open issues with project status tracking.</p>
        
        <h3>Work Distribution by Workflow Stage</h3>
        <table border="1" style="border-collapse: collapse; width: 100%;">
            <tr style="background-color: #f0f0f0;">
                <th style="padding: 8px;">Stage</th>
                <th style="padding: 8px;">Count</th>
                <th style="padding: 8px;">Percentage</th>
            </tr>
            {status_rows}
        </table>
        
        {bottlenecks_html}
        
        <h3>⏰ Work Age Analysis</h3>
        <table border="1" style="border-collapse: collapse; width: 100%;">
            <tr style="background-color: #f0f0f0;">
                <th style="padding: 8px;">Stage</th>
                <th style="padding: 8px;">Average Age</th>
                <th style="padding: 8px;">Oldest Item</th>
                <th style="padding: 8px;">Stale Items (>30 days)</th>
            </tr>
            {age_rows}
        </table>
        
        {assignment_html}
        """

    def _create_stage_progression_chart(self, df: pd.DataFrame, metrics: List, ax):
        """Create a stacked bar chart showing time spent in different phases by time period"""
        closed_issues = df[df['state'] == 'closed'].copy()
        
        if len(closed_issues) == 0:
            ax.text(0.5, 0.5, 'No closed issues with stage data', 
                   horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
            ax.set_title('Stage Progression Analysis')
            return
        
        # Extract month-year from closed_at for grouping
        closed_issues['month_year'] = pd.to_datetime(closed_issues['closed_at']).dt.to_period('M')
        
        # Get the metrics objects to access stage_segments
        metrics_by_issue = {}
        total_metrics = len(metrics)
        metrics_with_stages = 0
        for metric in metrics:
            if metric.stage_segments and metric.state == 'closed':
                metrics_by_issue[metric.issue_number] = metric
                metrics_with_stages += 1
        
        print(f"DEBUG: Total metrics: {total_metrics}, with stage segments: {metrics_with_stages}, closed with stages: {len(metrics_by_issue)}")
        
        # Aggregate stage data by month
        monthly_stage_data = {}
        
        for _, issue in closed_issues.iterrows():
            month = issue['month_year']
            issue_number = issue['issue_number']
            
            if issue_number in metrics_by_issue:
                metric = metrics_by_issue[issue_number]
                
                if month not in monthly_stage_data:
                    monthly_stage_data[month] = {}
                
                for segment in metric.stage_segments:
                    stage_name = segment.stage_name
                    duration = segment.duration_days or 0
                    
                    if stage_name not in monthly_stage_data[month]:
                        monthly_stage_data[month][stage_name] = 0
                    monthly_stage_data[month][stage_name] += duration
        
        if not monthly_stage_data:
            ax.text(0.5, 0.5, 'No stage progression data available', 
                   horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
            ax.set_title('Stage Progression Analysis')
            return
        
        # Convert to DataFrame for easier plotting
        stage_df = pd.DataFrame(monthly_stage_data).T.fillna(0)
        
        # Sort months chronologically
        stage_df = stage_df.sort_index()
        
        # Define colors for different stage types
        stage_colors = {
            'Requirements Review': '#ff9999',
            'Planning & Assignment': '#ffcc99', 
            'Development Planning': '#99ff99',
            'Development': '#99ff99',
            'Active Development': '#99ff99',
            'Development & Deployment': '#99ff99',
            'Development & Integration': '#99ff99',
            'Code Review & Deployment': '#9999ff',
            'Complete Lifecycle': '#cccccc',
            'Planning & Development': '#ffff99'
        }
        
        # Create stacked bar chart
        bottom = None
        month_labels = [str(month) for month in stage_df.index]
        
        for stage in stage_df.columns:
            color = stage_colors.get(stage, '#cccccc')
            values = stage_df[stage]
            
            ax.bar(month_labels, values, bottom=bottom, 
                  label=stage, color=color, alpha=0.8)
            
            if bottom is None:
                bottom = values
            else:
                bottom += values
        
        ax.set_title('Time Spent in Different Phases by Month')
        ax.set_xlabel('Month')
        ax.set_ylabel('Total Days')
        ax.tick_params(axis='x', rotation=45)
        
        # Add legend (limit to avoid overcrowding)
        handles, labels = ax.get_legend_handles_labels()
        if len(labels) <= 6:
            ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')
        else:
            # Show only top 6 stages by total time
            stage_totals = stage_df.sum().sort_values(ascending=False)
            top_stages = stage_totals.head(6).index
            filtered_handles = [handles[labels.index(stage)] for stage in top_stages if stage in labels]
            filtered_labels = [stage for stage in top_stages if stage in labels]
            ax.legend(filtered_handles, filtered_labels, bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')
    
    def _create_detailed_stage_breakdown_chart(self, timeline_df: pd.DataFrame, ax):
        """Create a detailed stacked bar chart showing stage breakdown by issue type"""
        # Get all stage columns (exclude standard columns)
        standard_cols = ['issue_type', 'queue_time', 'work_time', 'total_time', 'closure_month', 'efficiency_ratio']
        stage_columns = [col for col in timeline_df.columns if col not in standard_cols]
        
        if not stage_columns:
            ax.text(0.5, 0.5, 'No detailed stage data available', 
                   horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
            ax.set_title('Stage Breakdown by Issue Type')
            return
        
        # Aggregate stage data by issue type
        issue_type_summary = timeline_df.groupby('issue_type')[stage_columns].mean()
        issue_type_counts = timeline_df['issue_type'].value_counts()
        
        # Filter to issue types with at least 5 issues
        valid_types = issue_type_counts[issue_type_counts >= 5].index
        issue_type_summary = issue_type_summary.loc[valid_types]
        
        if issue_type_summary.empty:
            ax.text(0.5, 0.5, 'Insufficient data for stage breakdown', 
                   horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
            ax.set_title('Stage Breakdown by Issue Type')
            return
        
        # Define colors for different stages
        stage_colors = {
            'Requirements Review': '#ff9999',
            'Planning & Assignment': '#ffcc99', 
            'Development Planning': '#99ff99',
            'Development': '#99ff99',
            'Active Development': '#99ff99',
            'Development & Deployment': '#99ff99',
            'Development & Integration': '#99ff99',
            'Code Review & Deployment': '#9999ff',
            'Complete Lifecycle': '#cccccc',
            'Planning & Development': '#ffff99'
        }
        
        # Sort columns by total time across all issue types (most significant first)
        column_totals = issue_type_summary.sum().sort_values(ascending=False)
        sorted_columns = column_totals.head(8).index.tolist()  # Limit to top 8 stages
        
        # Create stacked bar chart
        bottom = None
        issue_types = issue_type_summary.index.tolist()
        
        for stage in sorted_columns:
            if stage in issue_type_summary.columns:
                color = stage_colors.get(stage, '#cccccc')
                values = issue_type_summary[stage]
                
                ax.bar(issue_types, values, bottom=bottom, 
                      label=stage, color=color, alpha=0.8)
                
                if bottom is None:
                    bottom = values
                else:
                    bottom += values
        
        ax.set_title('Average Stage Breakdown by Issue Type (All Time)')
        ax.set_xlabel('Issue Type')
        ax.set_ylabel('Average Days')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3)
        
        # Add count annotations
        for i, issue_type in enumerate(issue_types):
            if issue_type in issue_type_counts:
                count = issue_type_counts[issue_type]
                total_height = bottom.iloc[i] if bottom is not None else 0
                ax.annotate(f'n={count}', 
                           xy=(i, total_height), xytext=(0, 5),
                           textcoords='offset points', ha='center', va='bottom',
                           fontsize=9, color='black')
        
        # Add legend (limit entries)
        handles, labels = ax.get_legend_handles_labels()
        if len(labels) <= 6:
            ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')
        else:
            # Show only top 6 stages
            ax.legend(handles[:6], labels[:6], bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')

    def _create_monthly_stage_progression_chart(self, timeline_df: pd.DataFrame, recent_data: pd.DataFrame, ax):
        """Create monthly stage progression stacked bar chart showing wait -> work -> wait -> work progression"""
        if recent_data.empty:
            ax.text(0.5, 0.5, 'No recent data available', 
                   horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
            ax.set_title('Monthly Stage Progression (Last 12 Months)')
            return
        
        # Get all stage columns (exclude standard columns)
        standard_cols = ['issue_type', 'queue_time', 'work_time', 'total_time', 'closure_month', 'efficiency_ratio']
        stage_columns = [col for col in recent_data.columns if col not in standard_cols]
        
        print(f"DEBUG: Timeline data columns: {list(recent_data.columns)}")
        print(f"DEBUG: Stage columns found: {stage_columns}")
        
        if not stage_columns:
            ax.text(0.5, 0.5, 'No stage data available', 
                   horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
            ax.set_title('Monthly Stage Progression (Last 12 Months)')
            return
        
        # Aggregate stage data by month
        monthly_stage_data = recent_data.groupby('closure_month')[stage_columns].mean()
        
        # Sort by chronological order
        monthly_stage_data = monthly_stage_data.sort_index()
        
        # Define colors for different stages
        stage_colors = {
            'Requirements Review': '#ff9999',
            'Planning & Assignment': '#ffcc99', 
            'Development Planning': '#99ff99',
            'Development': '#99ff99',
            'Active Development': '#99ff99',
            'Development & Deployment': '#99ff99',
            'Development & Integration': '#99ff99',
            'Code Review & Deployment': '#9999ff',
            'Complete Lifecycle': '#cccccc',
            'Planning & Development': '#ffff99'
        }
        
        # Sort stages by total time (most significant first)
        stage_totals = monthly_stage_data.sum().sort_values(ascending=False)
        sorted_stages = stage_totals.head(8).index.tolist()  # Top 8 stages
        
        # Create stacked bar chart
        bottom = None
        month_labels = [str(month) for month in monthly_stage_data.index]
        
        for stage in sorted_stages:
            if stage in monthly_stage_data.columns:
                color = stage_colors.get(stage, '#cccccc')
                values = monthly_stage_data[stage]
                
                ax.bar(month_labels, values, bottom=bottom, 
                      label=stage, color=color, alpha=0.8)
                
                if bottom is None:
                    bottom = values
                else:
                    bottom += values
        
        ax.set_title('Monthly Stage Progression (Last 12 Months)')
        ax.set_xlabel('Month')
        ax.set_ylabel('Average Days per Stage')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3)
        
        # Add legend (limit entries)
        handles, labels = ax.get_legend_handles_labels()
        if len(labels) <= 6:
            ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')
        else:
            ax.legend(handles[:6], labels[:6], bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')

    def _create_monthly_stage_by_type_chart(self, timeline_df: pd.DataFrame, recent_data: pd.DataFrame, ax):
        """Create monthly stage progression by issue type stacked bar chart"""
        if recent_data.empty:
            ax.text(0.5, 0.5, 'No recent data available', 
                   horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
            ax.set_title('Monthly Stage Progression by Issue Type (Last 12 Months)')
            return
        
        # Get top issue types for focus
        top_types = timeline_df['issue_type'].value_counts().head(3).index.tolist()
        
        if not top_types:
            ax.text(0.5, 0.5, 'No issue type data available', 
                   horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
            ax.set_title('Monthly Stage Progression by Issue Type (Last 12 Months)')
            return
        
        # Filter to top issue types and aggregate by month
        filtered_data = recent_data[recent_data['issue_type'].isin(top_types)]
        monthly_type_data = filtered_data.groupby(['closure_month', 'issue_type']).agg({
            'queue_time': 'mean',
            'work_time': 'mean'
        }).reset_index()
        
        # Get unique months
        months = sorted(monthly_type_data['closure_month'].unique())
        month_labels = [str(month) for month in months]
        
        # Create grouped stacked bars
        bar_width = 0.25
        x_positions = np.arange(len(months))
        
        # Colors for work vs wait
        wait_color = '#ff7f7f'
        work_color = '#7fbf7f'
        
        for i, issue_type in enumerate(top_types):
            type_data = monthly_type_data[monthly_type_data['issue_type'] == issue_type]
            
            # Align data with months
            wait_values = []
            work_values = []
            
            for month in months:
                month_data = type_data[type_data['closure_month'] == month]
                if not month_data.empty:
                    wait_values.append(month_data['queue_time'].iloc[0])
                    work_values.append(month_data['work_time'].iloc[0])
                else:
                    wait_values.append(0)
                    work_values.append(0)
            
            # Position bars for this issue type
            pos = x_positions + (i - 1) * bar_width
            
            # Create stacked bars
            ax.bar(pos, wait_values, bar_width, label=f'{issue_type} (Wait)' if i == 0 else '', 
                  color=wait_color, alpha=0.8)
            ax.bar(pos, work_values, bar_width, bottom=wait_values, 
                  label=f'{issue_type} (Work)' if i == 0 else '', color=work_color, alpha=0.8)
            
            # Add issue type labels below bars
            if i == 1:  # Middle position
                for j, pos_val in enumerate(pos):
                    total_height = wait_values[j] + work_values[j]
                    if total_height > 0:
                        ax.text(pos_val, -total_height * 0.1, issue_type, 
                               rotation=45, ha='center', va='top', fontsize=8)
        
        ax.set_title('Monthly Work vs Wait Time by Issue Type (Last 12 Months)')
        ax.set_xlabel('Month')
        ax.set_ylabel('Average Days')
        ax.set_xticks(x_positions)
        ax.set_xticklabels(month_labels, rotation=45)
        ax.grid(True, alpha=0.3)
        
        # Custom legend
        wait_patch = plt.Rectangle((0,0),1,1, color=wait_color, alpha=0.8)
        work_patch = plt.Rectangle((0,0),1,1, color=work_color, alpha=0.8)
        ax.legend([wait_patch, work_patch], ['Wait Time', 'Work Time'], 
                 bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')

    def generate_report(self, metrics: List[CycleTimeMetrics], output_dir: str = "cycle_time_report"):
        """Generate comprehensive cycle time report"""
        Path(output_dir).mkdir(exist_ok=True)
        
        # Store metrics for access by chart functions
        self.last_analyzed_metrics = metrics
        
        # Set up interrupt handler for this stage
        self.interrupted = False
        self._setup_interrupt_handler()
        
        try:
            # Check for interrupt before starting report generation
            self._check_interrupted()
            
            # Analyze project workflow if we have project data
            workflow_analysis = self.analyze_project_workflow(metrics)
            
            # Convert to DataFrame for analysis
            df_data = []
            for metric in metrics:
                # Create stage progression summary for CSV
                stage_progression = ""
                if metric.stage_segments:
                    stage_names = [seg.stage_name for seg in metric.stage_segments]
                    stage_progression = " → ".join(stage_names)
                
                df_data.append({
                    'issue_number': metric.issue_number,
                    'title': metric.title,
                    'created_at': metric.created_at,
                    'closed_at': metric.closed_at,
                    'work_started_at': metric.work_started_at,
                    'lead_time_days': metric.lead_time_days,
                    'cycle_time_days': metric.cycle_time_days,
                    'labels': ', '.join(metric.labels),
                    'assignee': metric.assignee,
                    'milestone': metric.milestone,
                    'state': metric.state,
                    'comments': 0,  # Default value, could be enhanced later
                    'total_work_time_days': metric.total_work_time_days,
                    'total_wait_time_days': metric.total_wait_time_days,
                    'work_efficiency_ratio': metric.work_efficiency_ratio,
                    'stage_progression': stage_progression
                })
            
            df = pd.DataFrame(df_data)
            
            # Check for interrupt before file operations
            self._check_interrupted()
            
            # Save raw data
            df.to_csv(f"{output_dir}/cycle_time_data.csv", index=False)
            
            # Save JSON with full project data for complex analysis
            import json
            json_data = []
            for metric in metrics:
                # Include detailed stage segments in JSON
                stage_segments_data = []
                if metric.stage_segments:
                    for seg in metric.stage_segments:
                        stage_segments_data.append({
                            'stage_name': seg.stage_name,
                            'stage_type': seg.stage_type,
                            'start_time': seg.start_time.isoformat(),
                            'end_time': seg.end_time.isoformat(),
                            'duration_days': seg.duration_days
                        })
                
                json_item = {
                    'issue_number': metric.issue_number,
                    'title': metric.title,
                    'created_at': metric.created_at.isoformat(),
                    'closed_at': metric.closed_at.isoformat() if metric.closed_at else None,
                    'work_started_at': metric.work_started_at.isoformat() if metric.work_started_at else None,
                    'lead_time_days': metric.lead_time_days,
                    'cycle_time_days': metric.cycle_time_days,
                    'labels': metric.labels,
                    'assignee': metric.assignee,
                    'milestone': metric.milestone,
                    'state': metric.state,
                    'stage_segments': stage_segments_data,
                    'total_work_time_days': metric.total_work_time_days,
                    'total_wait_time_days': metric.total_wait_time_days,
                    'work_efficiency_ratio': metric.work_efficiency_ratio,
                    'project_title': metric.project_title,
                    'project_status': metric.project_status,
                    'project_iteration': metric.project_iteration,
                    'project_assignees': metric.project_assignees
                }
                json_data.append(json_item)
            
            with open(f"{output_dir}/cycle_time_data.json", 'w') as f:
                json.dump(json_data, f, indent=2)
            
            # Generate summary statistics
            closed_issues = df[df['state'] == 'closed']
            
            if len(closed_issues) == 0:
                print("No closed issues found for analysis - generating report with available data")
                # Still generate a basic report even without closed issues
            
            # Check for interrupt before calculations
            self._check_interrupted()
            
            # Calculate statistics (only if we have closed issues)
            if len(closed_issues) > 0:
                lead_time_stats = closed_issues['lead_time_days'].describe()
                cycle_time_stats = closed_issues['cycle_time_days'].dropna().describe()
            else:
                # Create empty series for when there are no closed issues
                lead_time_stats = pd.Series(dtype='float64')
                cycle_time_stats = pd.Series(dtype='float64')
            
            # Calculate monthly cycle time trend with rolling 6-month average
            monthly_cycle_data = self._calculate_monthly_cycle_trends(closed_issues)
            
            # Generate advanced analyses
            segment_analysis = self._analyze_cycle_time_segments(df)
            assignment_analysis = self._analyze_assignment_patterns(df)
            status_analysis = self._analyze_status_progression(df)
            
            # Check for interrupt before visualization
            self._check_interrupted()
            
            # Generate visualizations
            plt.style.use('seaborn-v0_8')
            fig, axes = plt.subplots(2, 2, figsize=(15, 12))
            fig.suptitle(f'Cycle Time Analysis for {self.owner}/{self.repo}', fontsize=16)
            
            # Lead time distribution
            axes[0, 0].hist(closed_issues['lead_time_days'].dropna(), bins=20, alpha=0.7, color='skyblue')
            axes[0, 0].set_title('Lead Time Distribution (Days)')
            axes[0, 0].set_xlabel('Days')
            axes[0, 0].set_ylabel('Frequency')
            
            # Cycle time distribution
            cycle_times = closed_issues['cycle_time_days'].dropna()
            if len(cycle_times) > 0:
                axes[0, 1].hist(cycle_times, bins=20, alpha=0.7, color='lightgreen')
                axes[0, 1].set_title('Cycle Time Distribution (Days)')
                axes[0, 1].set_xlabel('Days')
                axes[0, 1].set_ylabel('Frequency')
            
            # Monthly cycle time trend with 6-month rolling average
            if not monthly_cycle_data.empty:
                axes[1, 0].plot(monthly_cycle_data.index, monthly_cycle_data['monthly_avg'], 
                               alpha=0.7, marker='o', markersize=4, label='Monthly Average', color='orange')
                axes[1, 0].plot(monthly_cycle_data.index, monthly_cycle_data['rolling_6m'], 
                               linewidth=2, label='6-Month Rolling Average', color='red')
                axes[1, 0].set_title('Monthly Cycle Time Trend')
                axes[1, 0].set_xlabel('Month')
                axes[1, 0].set_ylabel('Cycle Time (Days)')
                axes[1, 0].legend()
                axes[1, 0].tick_params(axis='x', rotation=45)
                axes[1, 0].grid(True, alpha=0.3)
            
            # Stage progression stacked bar chart
            self._create_stage_progression_chart(df, metrics, axes[1, 1])
            
            plt.tight_layout()
            plt.savefig(f"{output_dir}/cycle_time_analysis.png", dpi=300, bbox_inches='tight')
            plt.close()
            
            # Generate timeline visualization
            timeline_data = self._create_timeline_visualization(df, output_dir)
            
            # Generate workflow visualization if we have project data
            if workflow_analysis and workflow_analysis.get('workflow_data'):
                self._create_workflow_visualization(workflow_analysis['workflow_data'], output_dir)
            
            # Check for interrupt before AI recommendations
            self._check_interrupted()
            
            # Generate AI recommendations
            recommendations = self._generate_ai_recommendations(df, lead_time_stats, cycle_time_stats, monthly_cycle_data)
            
            # Check for interrupt before HTML generation
            self._check_interrupted()
            
            # Generate HTML report
            html_report = self._generate_html_report(
                closed_issues, lead_time_stats, cycle_time_stats, monthly_cycle_data, 
                segment_analysis, assignment_analysis, status_analysis, recommendations, 
                workflow_analysis, output_dir
            )
            
            with open(f"{output_dir}/cycle_time_report.html", 'w') as f:
                f.write(html_report)
            
            print(f"\nReport generated in '{output_dir}' directory:")
            print(f"- cycle_time_data.csv: Raw data")
            print(f"- cycle_time_analysis.png: Basic visualizations")
            print(f"- timeline_analysis.png: Stage progression timeline analysis")
            if workflow_analysis:
                print(f"- workflow_analysis.png: GitHub Projects workflow analysis")
            print(f"- cycle_time_report.html: Full HTML report with workflow insights")
            
            # Print summary to console
            print(f"\n=== CYCLE TIME ANALYSIS SUMMARY ===")
            print(f"Repository: {self.owner}/{self.repo}")
            print(f"Total Issues: {len(df)}")
            print(f"Closed Issues: {len(closed_issues)}")
            
            if len(closed_issues) > 0 and not lead_time_stats.empty:
                print(f"\nLead Time Statistics (days):")
                print(f"  Average: {lead_time_stats['mean']:.1f}")
                print(f"  Median: {lead_time_stats['50%']:.1f}")
                print(f"  Min: {lead_time_stats['min']:.1f}")
                print(f"  Max: {lead_time_stats['max']:.1f}")
            else:
                print(f"\nLead Time Statistics: No closed issues available")
            
            if not cycle_time_stats.empty:
                print(f"\nCycle Time Statistics (days):")
                print(f"  Average: {cycle_time_stats['mean']:.1f}")
                print(f"  Median: {cycle_time_stats['50%']:.1f}")
                print(f"  Min: {cycle_time_stats['min']:.1f}")
                print(f"  Max: {cycle_time_stats['max']:.1f}")
                
                # Work/Wait Time Analysis Summary
                work_time_data = closed_issues['total_work_time_days'].dropna()
                wait_time_data = closed_issues['total_wait_time_days'].dropna()
                efficiency_data = closed_issues['work_efficiency_ratio'].dropna()
                
                if not work_time_data.empty and not wait_time_data.empty:
                    print(f"\nWork vs Wait Time Analysis:")
                    print(f"  Average Work Time: {work_time_data.mean():.1f} days")
                    print(f"  Average Wait Time: {wait_time_data.mean():.1f} days")
                    print(f"  Work Efficiency (Work/Total): {efficiency_data.mean()*100:.1f}%")
                    print(f"  Issues with Work/Wait data: {len(efficiency_data)}")
            else:
                print(f"\nCycle Time Statistics: No closed issues with cycle time data available")
        
        except InterruptedException:
            self.status.print(f"⚠️  User interrupted report generation! Partial report may be available in '{output_dir}'", style="yellow bold")
        
        finally:
            # Restore original signal handler
            self._restore_interrupt_handler()
            # Show cache statistics at the end
            self._show_cache_stats()
    
    def _generate_html_report(self, df, lead_time_stats, cycle_time_stats, monthly_cycle_data, 
                             segment_analysis, assignment_analysis, status_analysis, recommendations, 
                             workflow_analysis, output_dir):
        """Generate HTML report"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Cycle Time Report - {self.owner}/{self.repo}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ background-color: #f5f5f5; padding: 20px; border-radius: 8px; }}
        .metric {{ background-color: #e8f4fd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        .chart {{ text-align: center; margin: 20px 0; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Cycle Time Analysis Report</h1>
        <p><strong>Repository:</strong> {self.owner}/{self.repo}</p>
        <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <h2>Executive Summary</h2>
    <div class="metric">
        <h3>Lead Time (Creation to Closure)</h3>
        <p><strong>Average:</strong> {f"{lead_time_stats['mean']:.1f}" if not lead_time_stats.empty else 'N/A'} days</p>
        <p><strong>Median:</strong> {f"{lead_time_stats['50%']:.1f}" if not lead_time_stats.empty else 'N/A'} days</p>
        <p><strong>90th Percentile:</strong> {f"{lead_time_stats['90%']:.1f}" if not lead_time_stats.empty and '90%' in lead_time_stats else 'N/A'} days</p>
    </div>
    
    <div class="metric">
        <h3>Cycle Time (Work Start to Closure)</h3>
        <p><strong>Average:</strong> {f"{cycle_time_stats['mean']:.1f}" if not cycle_time_stats.empty else 'N/A'} days</p>
        <p><strong>Median:</strong> {f"{cycle_time_stats['50%']:.1f}" if not cycle_time_stats.empty else 'N/A'} days</p>
    </div>
    
    {f'''<div class="metric">
        <h3>Monthly Cycle Time Trend (6-Month Rolling Average)</h3>
        <p><strong>Latest 6-Month Average:</strong> {monthly_cycle_data['rolling_6m'].iloc[-1]:.1f} days</p>
        <p><strong>Trend Direction:</strong> {
            "Improving" if len(monthly_cycle_data) >= 2 and monthly_cycle_data['rolling_6m'].iloc[-1] < monthly_cycle_data['rolling_6m'].iloc[-2] 
            else "Worsening" if len(monthly_cycle_data) >= 2 and monthly_cycle_data['rolling_6m'].iloc[-1] > monthly_cycle_data['rolling_6m'].iloc[-2]
            else "Stable"
        }</p>
        <p><strong>Data Points:</strong> {len(monthly_cycle_data)} months</p>
    </div>''' if not monthly_cycle_data.empty else ''}
    
    <div class="chart">
        <img src="cycle_time_analysis.png" alt="Cycle Time Analysis Charts" style="max-width: 100%;">
    </div>
    
    <div class="chart">
        <img src="timeline_analysis.png" alt="Timeline Analysis" style="max-width: 100%;">
    </div>
    
    {f'<div class="chart"><img src="workflow_analysis.png" alt="Workflow Analysis" style="max-width: 100%;"></div>' if workflow_analysis else ''}
    
    <h2>Workflow Analysis</h2>
    
    {f'''<div class="metric">
        <h3>Cycle Time by Issue Type</h3>
        <table>
            <tr><th>Type</th><th>Count</th><th>Mean Days</th><th>Median Days</th></tr>
            {''.join(f"<tr><td>{type_name}</td><td>{data['count']}</td><td>{data['mean']}</td><td>{data['median']}</td></tr>" 
                    for type_name, data in segment_analysis.get('by_issue_type', {}).items())}
        </table>
    </div>''' if segment_analysis.get('by_issue_type') else ''}
    
    {f'''<div class="metric">
        <h3>Cycle Time by Team</h3>
        <table>
            <tr><th>Team</th><th>Count</th><th>Mean Days</th><th>Median Days</th></tr>
            {''.join(f"<tr><td>{team}</td><td>{data['count']}</td><td>{data['mean']}</td><td>{data['median']}</td></tr>" 
                    for team, data in segment_analysis.get('by_team', {}).items())}
        </table>
    </div>''' if segment_analysis.get('by_team') else ''}
    
    {f'''<div class="metric">
        <h3>Cycle Time by Product Area</h3>
        <table>
            <tr><th>Product</th><th>Count</th><th>Mean Days</th><th>Median Days</th></tr>
            {''.join(f"<tr><td>{product}</td><td>{data['count']}</td><td>{data['mean']}</td><td>{data['median']}</td></tr>" 
                    for product, data in segment_analysis.get('by_product_area', {}).items())}
        </table>
    </div>''' if segment_analysis.get('by_product_area') else ''}
    
    {f'''<div class="metric">
        <h3>Cycle Time by Priority</h3>
        <table>
            <tr><th>Priority</th><th>Count</th><th>Mean Days</th><th>Median Days</th></tr>
            {''.join(f"<tr><td>{priority}</td><td>{data['count']}</td><td>{data['mean']}</td><td>{data['median']}</td></tr>" 
                    for priority, data in segment_analysis.get('by_priority', {}).items())}
        </table>
    </div>''' if segment_analysis.get('by_priority') else ''}
    
    <h2>Assignment & Queue Analysis</h2>
    
    <div class="metric">
        <h3>Time to Assignment</h3>
        <p><strong>Average:</strong> {assignment_analysis.get('time_to_assignment', {}).get('mean_days', 'N/A')} days</p>
        <p><strong>Median:</strong> {assignment_analysis.get('time_to_assignment', {}).get('median_days', 'N/A')} days</p>
        <p><strong>Max:</strong> {assignment_analysis.get('time_to_assignment', {}).get('max_days', 'N/A')} days</p>
        <p><strong>Issues analyzed:</strong> {assignment_analysis.get('time_to_assignment', {}).get('count', 0)}</p>
    </div>
    
    <div class="metric">
        <h3>Assignment Stability</h3>
        <p><strong>Average reassignments per issue:</strong> {assignment_analysis.get('assignment_stability', {}).get('mean_reassignments', 'N/A')}</p>
        <p><strong>Issues with reassignments:</strong> {assignment_analysis.get('assignment_stability', {}).get('issues_with_reassignments', 0)}</p>
        <p><strong>Stability rate:</strong> {assignment_analysis.get('assignment_stability', {}).get('stability_rate', 'N/A')}%</p>
    </div>
    
    <div class="metric">
        <h3>Team Collaboration</h3>
        <p><strong>Multi-assignee issues:</strong> {assignment_analysis.get('team_collaboration', {}).get('multi_assignee_issues', 0)}</p>
        <p><strong>Collaboration rate:</strong> {assignment_analysis.get('team_collaboration', {}).get('collaboration_rate', 0)}%</p>
    </div>
    
    <h2>Status & Queue Times</h2>
    
    <div class="metric">
        <h3>Queue Time (Creation to Work Start)</h3>
        <p><strong>Average:</strong> {status_analysis.get('queue_time', {}).get('mean_days', 'N/A')} days</p>
        <p><strong>Median:</strong> {status_analysis.get('queue_time', {}).get('median_days', 'N/A')} days</p>
        <p><strong>Max:</strong> {status_analysis.get('queue_time', {}).get('max_days', 'N/A')} days</p>
    </div>
    
    <div class="metric">
        <h3>Time in Review Status</h3>
        <p><strong>Average:</strong> {status_analysis.get('needs_review_time', {}).get('mean_days', 'N/A')} days</p>
        <p><strong>Median:</strong> {status_analysis.get('needs_review_time', {}).get('median_days', 'N/A')} days</p>
        <p><strong>Max:</strong> {status_analysis.get('needs_review_time', {}).get('max_days', 'N/A')} days</p>
    </div>
    
    <h2>Key Insights</h2>
    <ul>
        <li>Total issues analyzed: {len(df)}</li>
        <li>Issues with calculable cycle time: {len(df[df['cycle_time_days'].notna()])}</li>
        <li>Average time from creation to work start: {f"{((df['work_started_at'] - df['created_at']).dt.total_seconds() / (24*3600)).mean():.1f}" if df['work_started_at'].notna().any() else 'N/A'} days</li>
    </ul>
    
    {self._generate_workflow_section(workflow_analysis) if workflow_analysis else ''}
    
    <h2>Recommendations</h2>
    <ul>
        {chr(10).join(f"<li>{rec}</li>" for rec in recommendations)}
    </ul>
    {f'<p><em>Recommendations generated using AI analysis of repository data.</em></p>' if os.getenv('OPENAI_API_KEY') else '<p><em>Set OPENAI_API_KEY and OPENAI_MODEL environment variables for AI-generated recommendations.</em></p>'}
    
    <p><em>For detailed data, see cycle_time_data.csv</em></p>
</body>
</html>
        """

def main():
    """Main execution function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Analyze GitHub repository cycle times',
        epilog='''
Strategic Work Focus:
  Analysis focuses on strategic business value work only:
  INCLUDES: product features, customer issues, epics
  EXCLUDES: chores, deployments, infrastructure tasks

Cache Management:
  API responses are cached for 1 week to speed up subsequent runs.
  Cache directory: .cache/OWNER/REPO/
  
  To clear cache:
    --clear-cache           Clear cache for specified repository
    --clear-all-caches      Clear all GitHub caches
    
  Or manually delete the cache directory.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('owner', nargs='?', help='Repository owner/organization')
    parser.add_argument('repo', nargs='?', help='Repository name')
    parser.add_argument('--limit', type=int, help='Limit number of issues to process (for debugging)')
    parser.add_argument('--fast', action='store_true', help='Skip work start detection for faster processing (only basic lead times)')
    parser.add_argument('--workflow-analysis', action='store_true', help='Run detailed workflow analysis with console output')
    parser.add_argument('--load-json', type=str, help='Load existing cycle time data from JSON file instead of fetching from GitHub')
    parser.add_argument('--clear-cache', action='store_true', help='Clear cache for this repository and exit')
    parser.add_argument('--clear-all-caches', action='store_true', help='Clear all GitHub caches and exit')
    args = parser.parse_args()
    
    # Handle cache clearing commands
    if args.clear_all_caches:
        GitHubCycleTimeAnalyzer.clear_all_caches()
        return
    
    if args.clear_cache:
        if args.owner and args.repo:
            GitHubCycleTimeAnalyzer.clear_cache_for_repo(args.owner, args.repo)
        else:
            print("Error: --clear-cache requires owner and repo arguments")
            print("Usage: python cycle_time.py owner repo --clear-cache")
        return
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Configuration
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
    if not GITHUB_TOKEN:
        print("Please set GITHUB_TOKEN environment variable")
        return
    
    # Optional AI recommendations
    openai_key = os.getenv('OPENAI_API_KEY')
    openai_model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    console = Console() if RICH_AVAILABLE else None
    
    if console:
        if openai_key:
            console.print(f"🤖 AI recommendations enabled using model: {openai_model}", style="green")
        else:
            console.print("🤖 AI recommendations disabled. Set OPENAI_API_KEY environment variable to enable.", style="dim")
    else:
        if openai_key:
            print(f"AI recommendations enabled using model: {openai_model}")
        else:
            print("AI recommendations disabled. Set OPENAI_API_KEY environment variable to enable.")
    
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
    
    print(f"Analyzing repository: {OWNER}/{REPO}")
    
    # Initialize analyzer
    analyzer = GitHubCycleTimeAnalyzer(GITHUB_TOKEN, OWNER, REPO)
    
    # Handle workflow analysis mode
    if args.load_json:
        try:
            print(f"Loading cycle time data from {args.load_json}...")
            json_data = analyzer.load_cycle_data_from_json(args.load_json)
            
            if args.workflow_analysis:
                # Convert JSON data to metrics for workflow analysis
                metrics = []
                for item in json_data:
                    # Create simplified metrics for workflow analysis
                    metric = type('CycleTimeMetrics', (), {
                        'issue_number': item.get('issue_number'),
                        'title': item.get('title', ''),
                        'labels': item.get('labels', []),
                        'project_title': item.get('project_title'),
                        'project_status': item.get('project_status'),
                        'state': item.get('state', 'open'),
                        'assignee': item.get('assignee'),
                        'created_at': datetime.fromisoformat(item['created_at']) if item.get('created_at') else datetime.now(timezone.utc)
                    })()
                    metrics.append(metric)
                
                print(f"Running detailed workflow analysis on {len(metrics)} issues...")
                analyzer.analyze_project_workflow_detailed(metrics)
            else:
                print("Use --workflow-analysis flag to run detailed analysis on loaded data")
            return
        except Exception as e:
            print(f"Error loading JSON data: {e}")
            return
    
    # Fetch issues
    try:
        issues = analyzer.fetch_issues(state='all', limit=args.limit)
        
        if not issues:
            print("No issues found in repository")
            return
            
        # Enrich with GitHub Projects data
        print("Enriching issues with GitHub Projects data...")
        issues = analyzer.enrich_issues_with_project_data(issues)
        
        # Apply strategic work filtering (always enabled)
        original_count = len(issues)
        issues = [issue for issue in issues if is_strategic_work(issue)]
        filtered_count = len(issues)
        print(f"🎯 Strategic work focus: analyzing {filtered_count:,} strategic issues (filtered out {original_count - filtered_count:,} operational tasks)")
        
        if not issues:
            print("No strategic work issues found after filtering")
            return
        
        # Calculate cycle times
        metrics = analyzer.calculate_cycle_times(issues, fast_mode=args.fast)
        
        if not metrics:
            print("No metrics calculated - unable to generate report")
            return
        
        # Run detailed workflow analysis if requested
        if args.workflow_analysis:
            print("\n" + "=" * 60)
            print("DETAILED WORKFLOW ANALYSIS")
            print("=" * 60)
            analyzer.analyze_project_workflow_detailed(metrics)
            print("=" * 60)
        
        if console:
            console.print(f"📈 Generating report for {len(metrics)} issues...", style="blue bold")
        else:
            print(f"\nGenerating report for {len(metrics)} issues...")
        
        # Generate report
        analyzer.generate_report(metrics)
        
    except InterruptedException:
        print("\n\n⚠️  Process interrupted by user. Partial results may have been generated.")
        return
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user. No report generated.")
        return
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        return

if __name__ == "__main__":
    main()