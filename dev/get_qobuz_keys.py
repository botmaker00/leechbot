#!/usr/bin/env python3
"""
Script to extract Qobuz app ID and secrets using qobuz-dl

Requirements: pip install qobuz-dl

"""

try:
    from qobuz_dl.bundle import Bundle

    print("🔍 Extracting Qobuz app ID and secrets...")
    print("=" * 50)

    bundle = Bundle()
    app_id = bundle.get_app_id()
    secrets_dict = bundle.get_secrets()

    print(f"✅ App ID: {app_id}")
    print("=" * 50)
    print("🔑 Secrets:")

    for i, (location, secret) in enumerate(secrets_dict.items(), 1):
        print(f"  {i}. {location}: {secret}")

    print("=" * 50)
    print("📋 For streamrip configuration:")
    print(f'app_id = "{app_id}"')

    # Format secrets as a list for streamrip
    secrets_list = list(secrets_dict.values())
    secrets_formatted = '", "'.join(secrets_list)
    print(f'secrets = ["{secrets_formatted}"]')

    print("=" * 50)
    print("💡 Note: Usually the first secret works. Try them in order if one fails.")

except ImportError as e:
    print(f"❌ Error: qobuz-dl not properly installed: {e}")
    print("Please run: pip install qobuz-dl")
except Exception as e:
    print(f"❌ Error extracting keys: {e}")
    print("This might be due to network issues or changes in Qobuz's API.")
