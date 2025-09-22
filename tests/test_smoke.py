#!/usr/bin/env python3
"""
Smoke tests for basic functionality validation
Quick tests to ensure core functionality works after changes
Run with: uv run tests/test_smoke.py
"""
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "pandas",
#     "openai",
#     "python-dotenv",
#     "matplotlib",
#     "seaborn",
# ]
# ///

import sys
import os
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_core_imports():
    """Test that all core modules can be imported"""
    print("🧪 Testing core imports...")

    try:
        import product_status_report
        import generate_business_slide
        from utils import generate_issue_url, format_labels_for_display
        from utils_filtering import normalize_labels, is_strategic_work
        from utils_dates import get_week_boundaries, is_recently_completed
        from ai_service import AIAnalysisService
        from report_generator import ReportGenerator

        print("✅ All core modules import successfully")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_utility_functions():
    """Test core utility functions with basic inputs"""
    print("🧪 Testing utility functions...")

    try:
        from utils_filtering import normalize_labels, is_strategic_work
        from utils import generate_issue_url, format_labels_for_display

        # Test normalize_labels
        labels = [{'name': 'Product/AI'}, {'name': 'Type/Bug'}]
        result = normalize_labels(labels)
        assert result == 'product/ai type/bug'

        # Test format_labels_for_display
        result = format_labels_for_display(labels)
        assert result == 'Product/AI, Type/Bug'

        # Test is_strategic_work
        issue = {'labels': [{'name': 'product/ai'}]}
        assert is_strategic_work(issue) == True

        # Test generate_issue_url
        issue = {'number': 123}
        result = generate_issue_url(issue, 'owner', 'repo')
        assert result == 'https://github.com/owner/repo/issues/123'

        print("✅ Utility functions work correctly")
        return True
    except Exception as e:
        print(f"❌ Utility function error: {e}")
        return False

def test_cli_interfaces():
    """Test that CLI interfaces respond correctly"""
    print("🧪 Testing CLI interfaces...")

    try:
        # Test product_status_report help
        result = subprocess.run(
            ['uv', 'run', 'product_status_report.py', '--help'],
            capture_output=True, text=True, timeout=30, cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 0
        assert 'Generate executive product status report' in result.stdout

        # Test generate_business_slide help
        result = subprocess.run(
            ['uv', 'run', 'generate_business_slide.py', '--help'],
            capture_output=True, text=True, timeout=30, cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 0
        assert 'Generate business-focused' in result.stdout

        print("✅ CLI interfaces work correctly")
        return True
    except Exception as e:
        print(f"❌ CLI interface error: {e}")
        return False

def test_service_classes():
    """Test that service classes can be instantiated"""
    print("🧪 Testing service classes...")

    try:
        from ai_service import AIAnalysisService
        from report_generator import ReportGenerator

        # Test AI service creation
        ai_service = AIAnalysisService.create_from_api_key()
        assert hasattr(ai_service, 'is_available')

        # Test report generator creation
        generator = ReportGenerator('owner', 'repo')
        assert generator.github_owner == 'owner'
        assert generator.github_repo == 'repo'

        print("✅ Service classes instantiate correctly")
        return True
    except Exception as e:
        print(f"❌ Service class error: {e}")
        return False

def main():
    """Run all smoke tests"""
    print("🚀 Running smoke tests...")
    print("=" * 50)

    tests = [
        test_core_imports,
        test_utility_functions,
        test_cli_interfaces,
        test_service_classes
    ]

    passed = 0
    for test in tests:
        if test():
            passed += 1
        print()

    print("=" * 50)
    if passed == len(tests):
        print(f"🎉 ALL {len(tests)} SMOKE TESTS PASSED!")
        print("✅ Core functionality verified")
        return 0
    else:
        print(f"❌ {len(tests) - passed}/{len(tests)} TESTS FAILED!")
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)