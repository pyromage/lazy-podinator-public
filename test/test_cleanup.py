#!/usr/bin/env python3
"""
Test the automatic cleanup functionality.
This script creates test episodes with old dates and verifies cleanup works.

Usage:
  python test_cleanup.py
"""

import os
from datetime import datetime, timedelta
from google.cloud import storage

# Configuration
BUCKET_NAME = os.environ.get("BUCKET_NAME")
TEST_SHOW_KEY = "test-cleanup"

def create_test_episodes():
    """Create test episodes with various ages"""
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)

    test_dates = [
        datetime.now() - timedelta(days=5),   # 5 days old (keep)
        datetime.now() - timedelta(days=15),  # 15 days old (keep)
        datetime.now() - timedelta(days=25),  # 25 days old (keep)
        datetime.now() - timedelta(days=35),  # 35 days old (delete)
        datetime.now() - timedelta(days=45),  # 45 days old (delete)
        datetime.now() - timedelta(days=60),  # 60 days old (delete)
    ]

    print(f"Creating {len(test_dates)} test episodes in bucket...")

    for ep_date in test_dates:
        date_str = ep_date.strftime('%Y-%m-%d')
        blob_name = f"{TEST_SHOW_KEY}/{date_str}_update.mp3"
        blob = bucket.blob(blob_name)

        # Upload a small test file
        test_content = f"Test episode from {date_str}".encode('utf-8')
        blob.upload_from_string(test_content, content_type="audio/mpeg")

        age_days = (datetime.now() - ep_date).days
        status = "KEEP" if age_days < 30 else "DELETE"
        print(f"  ✓ Created: {blob_name} (age: {age_days} days) [{status}]")

    print(f"\nTest episodes created in gs://{BUCKET_NAME}/{TEST_SHOW_KEY}/")

def list_episodes():
    """List all episodes in the test show"""
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blobs = bucket.list_blobs(prefix=f"{TEST_SHOW_KEY}/")

    episodes = []
    for blob in blobs:
        if blob.name.endswith('.mp3'):
            filename = blob.name.split('/')[-1]
            date_str = filename.replace('_update.mp3', '')
            try:
                ep_date = datetime.strptime(date_str, '%Y-%m-%d')
                age_days = (datetime.now() - ep_date).days
                episodes.append({
                    'name': blob.name,
                    'date': ep_date,
                    'age_days': age_days
                })
            except ValueError:
                continue

    return sorted(episodes, key=lambda x: x['date'], reverse=True)

def run_cleanup():
    """Run cleanup on test episodes"""
    from main import cleanup_old_episodes

    print("\n" + "="*60)
    print("Running cleanup (deleting episodes older than 30 days)...")
    print("="*60)

    deleted_count = cleanup_old_episodes(TEST_SHOW_KEY, days_to_keep=30)

    print(f"\nCleanup complete! Deleted {deleted_count} episodes.")

def cleanup_test_data():
    """Remove all test episodes"""
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blobs = bucket.list_blobs(prefix=f"{TEST_SHOW_KEY}/")

    count = 0
    for blob in blobs:
        blob.delete()
        count += 1

    print(f"\nCleaned up {count} test files from gs://{BUCKET_NAME}/{TEST_SHOW_KEY}/")

def main():
    print("="*60)
    print("LAZY PODINATOR - Cleanup Test")
    print("="*60)
    print()

    if not BUCKET_NAME:
        print("❌ Error: BUCKET_NAME environment variable not set")
        print("   Run: export BUCKET_NAME=your-bucket-name")
        return

    # Step 1: Create test episodes
    create_test_episodes()

    # Step 2: List episodes before cleanup
    print("\n" + "="*60)
    print("Episodes BEFORE cleanup:")
    print("="*60)
    episodes_before = list_episodes()
    for ep in episodes_before:
        status = "KEEP" if ep['age_days'] < 30 else "DELETE"
        print(f"  • {ep['name']} (age: {ep['age_days']} days) [{status}]")
    print(f"\nTotal episodes: {len(episodes_before)}")

    # Step 3: Run cleanup
    run_cleanup()

    # Step 4: List episodes after cleanup
    print("\n" + "="*60)
    print("Episodes AFTER cleanup:")
    print("="*60)
    episodes_after = list_episodes()
    for ep in episodes_after:
        print(f"  • {ep['name']} (age: {ep['age_days']} days)")
    print(f"\nTotal episodes: {len(episodes_after)}")

    # Step 5: Verify results
    print("\n" + "="*60)
    print("Test Results:")
    print("="*60)

    expected_remaining = sum(1 for ep in episodes_before if ep['age_days'] < 30)
    actual_remaining = len(episodes_after)

    if actual_remaining == expected_remaining:
        print(f"✅ SUCCESS: Cleanup working correctly!")
        print(f"   Expected {expected_remaining} episodes remaining, found {actual_remaining}")
    else:
        print(f"❌ FAILURE: Unexpected results")
        print(f"   Expected {expected_remaining} episodes remaining, found {actual_remaining}")

    # Step 6: Clean up test data
    print("\n" + "="*60)
    print("Cleaning up test data...")
    print("="*60)
    cleanup_test_data()

    print("\n✅ Test complete!")

if __name__ == "__main__":
    main()
