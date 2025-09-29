#!/usr/bin/env python3
"""
Debrid-Link OAuth2 Setup Utility (Standalone)

This script helps you set up OAuth2 authentication for Debrid-Link API.
It implements the device flow which is suitable for bots and limited input devices.

Usage:
    python debrid_oauth_setup.py

Requirements:
    1. Create a Debrid-Link app at: https://debrid-link.com/webapp/apikey
    2. Get your client_id from the app settings
    3. Run this script and follow the instructions

The script will output the tokens you need to add to your config.

Dependencies: Only Python standard library (no external packages required)
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request


class DebridLinkException(Exception):
    """Custom exception for Debrid-Link API errors"""


def make_request(url, data=None, headers=None, timeout=30):
    """Make HTTP request using urllib (no external dependencies)"""
    if headers is None:
        headers = {}

    # Set default headers
    headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    )

    try:
        if data is not None:
            # POST request
            if isinstance(data, dict):
                data = urllib.parse.urlencode(data).encode("utf-8")
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

            req = urllib.request.Request(url, data=data, headers=headers)
        else:
            # GET request
            req = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(req, timeout=timeout) as response:
            response_data = response.read().decode("utf-8")
            return json.loads(response_data)

    except urllib.error.HTTPError as e:
        # Handle HTTP errors
        try:
            error_data = json.loads(e.read().decode("utf-8"))
            error_msg = error_data.get("error", f"HTTP {e.code}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            error_msg = f"HTTP {e.code}"
        raise DebridLinkException(f"HTTP Error: {error_msg}")

    except urllib.error.URLError as e:
        raise DebridLinkException(f"Network Error: {e!s}")

    except json.JSONDecodeError as e:
        raise DebridLinkException(f"Invalid JSON response: {e!s}")

    except Exception as e:
        raise DebridLinkException(f"Request failed: {e!s}")


def get_debrid_oauth_device_code(client_id, scope="get.post.downloader get.account"):
    """Get device code for OAuth2 device flow"""
    data = {"client_id": client_id, "scope": scope}

    try:
        return make_request(
            "https://debrid-link.com/api/oauth/device/code", data=data
        )
    except Exception as e:
        raise DebridLinkException(f"Device code request failed: {e!s}")


def poll_debrid_oauth_token(client_id, device_code):
    """Poll for OAuth2 tokens using device code"""
    data = {
        "client_id": client_id,
        "code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }

    try:
        return make_request("https://debrid-link.com/api/oauth/token", data=data)
    except DebridLinkException as e:
        if "HTTP Error: authorization_pending" in str(e):
            raise DebridLinkException("authorization_pending") from e
        raise e


def setup_debrid_oauth_device_flow(client_id):
    """Complete OAuth2 device flow setup for Debrid-Link"""
    try:
        # Step 1: Get device code
        print("Getting device code...")
        device_data = get_debrid_oauth_device_code(client_id)

        device_code = device_data["device_code"]
        user_code = device_data["user_code"]
        verification_url = device_data["verification_url"]
        expires_in = device_data["expires_in"]
        interval = device_data["interval"]

        print(f"\nPlease visit: {verification_url}")
        print(f"Enter this code: {user_code}")
        print(f"You have {expires_in // 60} minutes to complete authorization.")
        print(f"Polling for authorization every {interval} seconds...\n")

        # Step 2: Poll for tokens
        start_time = time.time()

        while time.time() - start_time < expires_in:
            try:
                token_data = poll_debrid_oauth_token(client_id, device_code)

                # Success! Return token data
                print("✅ Authorization successful!")
                print(f"Access Token: {token_data['access_token'][:20]}...")
                print(f"Refresh Token: {token_data['refresh_token'][:20]}...")
                print(f"Expires in: {token_data['expires_in']} seconds")

                return token_data

            except DebridLinkException as e:
                if "authorization_pending" in str(e):
                    print("⏳ Waiting for user authorization...")
                    time.sleep(interval)
                    continue
                raise e

        raise DebridLinkException("Authorization timeout - device code expired")

    except Exception as e:
        raise DebridLinkException(f"OAuth setup failed: {e!s}") from e


def main():
    print("🔗 Debrid-Link OAuth2 Setup Utility")
    print("=" * 50)

    # Get client ID from user
    print("\n📋 Prerequisites:")
    print("1. Create a Debrid-Link app at: https://debrid-link.com/webapp/apikey")
    print("2. Note down your client_id from the app settings")
    print("3. For public apps, you'll also need client_secret")

    client_id = input("\n🔑 Enter your Debrid-Link client_id: ").strip()

    if not client_id:
        print("❌ Client ID is required!")
        return

    try:
        print(f"\n🚀 Starting OAuth2 device flow for client: {client_id}")

        # Run the OAuth2 device flow
        token_data = setup_debrid_oauth_device_flow(client_id)

        # Display configuration instructions
        print("\n" + "=" * 50)
        print("✅ SUCCESS! Add these to your config:")
        print("=" * 50)

        print(f'DEBRID_LINK_CLIENT_ID = "{client_id}"')
        print(f'DEBRID_LINK_ACCESS_TOKEN = "{token_data["access_token"]}"')
        print(f'DEBRID_LINK_REFRESH_TOKEN = "{token_data["refresh_token"]}"')

        # Calculate expiration timestamp
        expires_timestamp = (
            int(time.time()) + token_data["expires_in"] - 300
        )  # 5 min buffer
        print(f"DEBRID_LINK_TOKEN_EXPIRES = {expires_timestamp}")

        print("\n📝 Notes:")
        print("- The access_token expires in 24 hours by default")
        print("- The bot will automatically refresh it using the refresh_token")
        print("- Keep the refresh_token secure and private")
        print(
            "- You can also set DEBRID_LINK_API to the access_token for legacy compatibility"
        )

        print("\n🔧 For config_sample.py or environment variables:")
        print(f'export DEBRID_LINK_CLIENT_ID="{client_id}"')
        print(f'export DEBRID_LINK_ACCESS_TOKEN="{token_data["access_token"]}"')
        print(f'export DEBRID_LINK_REFRESH_TOKEN="{token_data["refresh_token"]}"')
        print(f'export DEBRID_LINK_TOKEN_EXPIRES="{expires_timestamp}"')

    except DebridLinkException as e:
        print(f"\n❌ Setup failed: {e}")
        return
    except KeyboardInterrupt:
        print("\n\n⏹️ Setup cancelled by user")
        return
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        return


if __name__ == "__main__":
    main()
