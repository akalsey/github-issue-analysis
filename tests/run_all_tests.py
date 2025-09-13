#!/usr/bin/env python3
"""
Test runner for all GitHub Cycle Time Analyzer tests
"""
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "requests",
#     "pandas", 
#     "matplotlib",
#     "seaborn",
#     "rich",
#     "openai",
#     "python-dotenv",
#     "pytest",
# ]
# ///

import unittest
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def discover_and_run_tests():
    """Discover and run all tests in the tests directory"""
    
    print("🧪 GitHub Cycle Time Analyzer - Test Suite")
    print("=" * 50)
    
    # Get the tests directory
    tests_dir = Path(__file__).parent
    
    # Discover all test modules
    test_modules = [
        'test_cycle_time',
        'test_enhanced_features', 
        'test_sync_issues',
        'test_product_status_report',
        'test_business_slide_generation',
        'test_ai_integration',
        'test_scope_detection',
        'test_strategic_filtering',
        'test_caching_system'
    ]
    
    # Track results
    total_tests = 0
    total_failures = 0
    total_errors = 0
    
    print(f"\n📋 Running {len(test_modules)} test modules...\n")
    
    # Run each test module
    for module_name in test_modules:
        print(f"🔄 Running {module_name}...")
        
        try:
            # Import the test module
            test_module = __import__(module_name)
            
            # Create test suite
            loader = unittest.TestLoader()
            suite = loader.loadTestsFromModule(test_module)
            
            # Run tests
            runner = unittest.TextTestRunner(
                verbosity=1,
                stream=sys.stdout,
                buffer=True
            )
            
            result = runner.run(suite)
            
            # Track statistics
            total_tests += result.testsRun
            total_failures += len(result.failures)
            total_errors += len(result.errors)
            
            # Print module results
            if result.wasSuccessful():
                print(f"   ✅ {result.testsRun} tests passed\n")
            else:
                print(f"   ❌ {len(result.failures)} failures, {len(result.errors)} errors\n")
                
        except ImportError as e:
            print(f"   ⚠️  Could not import {module_name}: {e}\n")
            total_errors += 1
        except Exception as e:
            print(f"   💥 Error running {module_name}: {e}\n")
            total_errors += 1
    
    # Print final summary
    print("=" * 50)
    print("📊 Test Summary:")
    print(f"   Total Tests: {total_tests}")
    print(f"   Passed: {total_tests - total_failures - total_errors}")
    print(f"   Failed: {total_failures}")
    print(f"   Errors: {total_errors}")
    
    if total_failures == 0 and total_errors == 0:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n💥 {total_failures + total_errors} tests failed")
        return 1


def run_specific_test(test_name):
    """Run a specific test module"""
    print(f"🧪 Running specific test: {test_name}")
    print("=" * 50)
    
    try:
        # Import and run the specific test
        test_module = __import__(test_name)
        
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(test_module)
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        return 0 if result.wasSuccessful() else 1
        
    except ImportError as e:
        print(f"❌ Could not import test module '{test_name}': {e}")
        return 1
    except Exception as e:
        print(f"💥 Error running test '{test_name}': {e}")
        return 1


def list_available_tests():
    """List all available test modules"""
    print("📋 Available test modules:")
    print("-" * 30)
    
    test_modules = [
        ('test_cycle_time', 'Core cycle time analysis functionality'),
        ('test_enhanced_features', 'Enhanced workflow analysis features'),
        ('test_sync_issues', 'GitHub data collection and sync'),
        ('test_product_status_report', 'Executive product status reports'),
        ('test_business_slide_generation', 'Business presentation slides'),
        ('test_ai_integration', 'AI-powered analysis features'),
        ('test_scope_detection', 'Token scope detection and graceful degradation'),
        ('test_strategic_filtering', 'Strategic work filtering'),
        ('test_caching_system', 'Caching and performance optimization')
    ]
    
    for module, description in test_modules:
        print(f"  {module:<30} - {description}")
    
    print(f"\nUsage:")
    print(f"  python run_all_tests.py              # Run all tests")
    print(f"  python run_all_tests.py <test_name>  # Run specific test")
    print(f"  python run_all_tests.py --list       # List available tests")


def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        
        if arg in ['--list', '-l', 'list']:
            list_available_tests()
            return 0
        elif arg in ['--help', '-h', 'help']:
            print("GitHub Cycle Time Analyzer Test Runner")
            print("Usage: python run_all_tests.py [test_name|--list|--help]")
            return 0
        else:
            # Run specific test
            return run_specific_test(arg)
    else:
        # Run all tests
        return discover_and_run_tests()


if __name__ == '__main__':
    sys.exit(main())