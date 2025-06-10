#!/usr/bin/env python3
"""
NetKVMSwitch Test Runner

This script runs all unit tests for the NetKVMSwitch application.
Use this to verify functionality before manual testing.
"""

import sys
import os
import unittest
import logging

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def discover_and_run_tests():
    """Discover and run all unit tests."""
    
    # Suppress logging during tests to reduce noise
    logging.disable(logging.CRITICAL)
    
    # Test discovery
    test_loader = unittest.TestLoader()
    test_suite = test_loader.discover('tests', pattern='test_*.py')
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2, buffer=True)
    result = runner.run(test_suite)
    
    # Re-enable logging
    logging.disable(logging.NOTSET)
    
    return result

def run_specific_module(module_name):
    """Run tests for a specific module."""
    logging.disable(logging.CRITICAL)
    
    try:
        test_suite = unittest.TestLoader().loadTestsFromName(f'tests.unit.{module_name}')
        runner = unittest.TextTestRunner(verbosity=2, buffer=True)
        result = runner.run(test_suite)
        return result
    except Exception as e:
        print(f"Error running tests for {module_name}: {e}")
        return None
    finally:
        logging.disable(logging.NOTSET)

def main():
    """Main test runner function."""
    print("🧪 NetKVMSwitch Test Suite")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        # Run specific module tests
        module_name = sys.argv[1]
        print(f"Running tests for module: {module_name}")
        result = run_specific_module(module_name)
    else:
        # Run all tests
        print("Running all unit tests...")
        result = discover_and_run_tests()
    
    if result is None:
        print("❌ Test execution failed")
        sys.exit(1)
    elif result.wasSuccessful():
        print(f"\n✅ All tests passed!")
        print(f"   Tests run: {result.testsRun}")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
        print(f"   Skipped: {len(result.skipped)}")
    else:
        print(f"\n❌ Some tests failed!")
        print(f"   Tests run: {result.testsRun}")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
        print(f"   Skipped: {len(result.skipped)}")
        
        if result.failures:
            print("\n🔍 Failures:")
            for test, traceback in result.failures:
                print(f"   - {test}: {traceback.split('AssertionError:')[-1].strip()}")
        
        if result.errors:
            print("\n💥 Errors:")
            for test, traceback in result.errors:
                print(f"   - {test}: {traceback.split('Exception:')[-1].strip()}")
        
        sys.exit(1)

if __name__ == '__main__':
    main() 