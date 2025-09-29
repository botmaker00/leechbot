#!/usr/bin/env python3
"""
Quick Phish Directory API Key Generator

A simple script to get your phish.directory API key for AimLeechBot.

Requirements:
    pip install httpx

Usage:
    python get_phish_api_key.py
"""

import asyncio
import re
import sys
from getpass import getpass

try:
    import httpx
except ImportError:
    print("❌ Error: httpx library not found!")
    print("Please install it with: pip install httpx")
    sys.exit(1)


async def signup_user(client, headers):
    """Handle user signup process"""
    print("� Creating a new account...")
    print()

    # Get user details for signup
    first_name = input("👤 First Name: ").strip()
    if not first_name:
        print("❌ First name is required!")
        return None, None, None

    last_name = input("👤 Last Name: ").strip()
    if not last_name:
        print("❌ Last name is required!")
        return None, None, None

    # Validate email
    while True:
        email = input("📧 Email: ").strip()
        if re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            break
        print("❌ Please enter a valid email!")

    # Get password with validation
    while True:
        password = getpass("🔒 Password (min 8 chars): ")
        if len(password) >= 8:
            break
        print("❌ Password must be at least 8 characters!")

    confirm = getpass("🔒 Confirm Password: ")
    if password != confirm:
        print("❌ Passwords don't match!")
        return None, None, None

    print("\n🚀 Creating account...")

    # Signup API call
    signup_data = {
        "firstName": first_name,
        "lastName": last_name,
        "email": email,
        "password": password,
    }

    response = await client.post(
        "https://api.phish.directory/user/signup",
        json=signup_data,
        headers=headers,
    )

    if response.status_code != 200:
        print(f"❌ Signup failed: {response.status_code}")
        try:
            error = response.json()
            print(f"Error details: {error}")
        except Exception:
            print(f"Error: {response.text}")
        return None, None, None

    signup_result = response.json()
    print(f"✅ Account created: {signup_result.get('message', 'Success')}")

    return email, password, signup_result


async def login_user(client, headers, email=None, password=None):
    """Handle user login process"""
    if not email:
        print("🔐 Login to existing account...")
        print()

        # Get login credentials
        while True:
            email = input("📧 Email: ").strip()
            if re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
                break
            print("❌ Please enter a valid email!")

        password = getpass("🔒 Password: ")

    print("\n🔐 Logging in...")

    login_data = {"email": email, "password": password}

    response = await client.post(
        "https://api.phish.directory/user/login",
        json=login_data,
        headers=headers,
    )

    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code}")
        if response.status_code == 400:
            print("❌ Invalid email or password")
        elif response.status_code == 403:
            print("❌ Account has been deleted")
        else:
            try:
                error = response.json()
                print(f"Error details: {error}")
            except Exception:
                print(f"Error: {response.text}")
        return None

    login_result = response.json()
    api_token = login_result.get("token")

    if not api_token:
        print("❌ No API token received!")
        return None

    print("✅ Login successful!")
    return login_result


async def test_api_access(client, api_token):
    """Test API access with the token"""
    print("🧪 Testing API access...")

    test_headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    }

    response = await client.get(
        "https://api.phish.directory/domain/check?domain=google.com",
        headers=test_headers,
    )

    if response.status_code == 200:
        print("✅ API access confirmed!")
        return True
    print(f"⚠️  API test returned: {response.status_code}")
    print("Your token should still work - this might be normal.")
    return False


def display_success(email, login_result, api_token):
    """Display success message with API key"""
    print("\n" + "=" * 60)
    print("🎉 SUCCESS! Your API key is ready!")
    print("=" * 60)
    print(f"📧 Email: {email}")
    print(f"🆔 UUID: {login_result.get('uuid', 'N/A')}")
    print(f"👤 Name: {login_result.get('name', 'N/A')}")
    print(f"🔑 Permission: {login_result.get('permission', 'N/A')}")
    print()
    print("🔑 YOUR API KEY:")
    print("-" * 60)
    print(api_token)
    print("-" * 60)
    print()

    # Ask if user wants to save to file
    save_choice = input("💾 Save API key to file? (y/n): ").strip().lower()
    if save_choice in ["y", "yes"]:
        try:
            with open("phish_directory_api_key.txt", "w") as f:
                f.write("# Phish Directory API Key\n")
                f.write(f"# Generated for: {email}\n")
                f.write(f"# UUID: {login_result.get('uuid', 'N/A')}\n")
                f.write(f"# Date: {login_result.get('accountCreated', 'N/A')}\n")
                f.write(f'\nPHISH_DIRECTORY_API_KEY = "{api_token}"\n')
            print("✅ API key saved to: phish_directory_api_key.txt")
        except Exception as e:
            print(f"❌ Failed to save file: {e}")

    print()
    print("📋 SETUP INSTRUCTIONS:")
    print("1. Copy the API key above")
    print("2. Add to your bot config:")
    print('   PHISH_DIRECTORY_API_KEY = "your_key_here"')
    print("3. Restart your bot")
    print("4. Test: /phishcheck google.com")
    print()
    print("⚠️  Keep your API key secure!")
    print("=" * 60)


async def get_api_key():
    """Main function to get API key"""

    print("🔐 PHISH DIRECTORY API KEY GENERATOR")
    print("=" * 60)
    print("Get your API key for AimLeechBot's /phishcheck command")
    print()
    print("ℹ️  This script will help you:")
    print("   • Create a new phish.directory account OR")
    print("   • Login to your existing account")
    print("   • Get your JWT token for API access")
    print("   • Test the API to ensure it works")
    print()

    # Selection menu
    print("📋 Please select an option:")
    print("1. 🆕 Create new account (Signup)")
    print("2. 🔐 Login to existing account")
    print("3. ❌ Exit")
    print()

    while True:
        choice = input("👉 Enter your choice (1-3): ").strip()
        if choice in ["1", "2", "3"]:
            break
        print("❌ Please enter 1, 2, or 3")

    if choice == "3":
        print("👋 Goodbye!")
        return

    print()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            email = None
            password = None
            login_result = None

            if choice == "1":
                # Signup flow
                email, password, signup_result = await signup_user(client, headers)
                if not email:
                    return

                # Auto-login after signup
                login_result = await login_user(client, headers, email, password)
                if not login_result:
                    return

            elif choice == "2":
                # Login flow
                login_result = await login_user(client, headers)
                if not login_result:
                    return
                email = login_result.get("email", "N/A")

            # Get API token
            api_token = login_result.get("token")
            if not api_token:
                print("❌ No API token received!")
                return

            # Test API access
            await test_api_access(client, api_token)

            # Display success message
            display_success(email, login_result, api_token)

    except httpx.TimeoutException:
        print("❌ Request timeout - please try again")
    except httpx.RequestError as e:
        print(f"❌ Connection error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(get_api_key())
    except KeyboardInterrupt:
        print("\n❌ Cancelled by user")
    except Exception as e:
        print(f"❌ Error: {e}")
