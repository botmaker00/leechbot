#!/usr/bin/env python3
"""
Standalone Zotify Credentials Generator

This script helps generate Zotify credentials file for Spotify authentication.
It's completely standalone and only requires the official Zotify library.

Requirements:
- Spotify Premium account
- Internet connection
- Web browser for OAuth authentication
- Zotify library: pip install git+https://github.com/DraftKinner/zotify.git@dev

Usage:
    python generate_zotify_credentials.py [output_file]

Example:
    python generate_zotify_credentials.py
    python generate_zotify_credentials.py my_credentials.json
"""

import json
import sys
import time
import webbrowser
from pathlib import Path

# Check for Zotify library
try:
    from zotify import OAuth, Session

    print("✅ Zotify library found")
except ImportError:
    print("❌ Error: Zotify library not found!")
    print()
    print("Please install it with:")
    print("  pip install git+https://github.com/DraftKinner/zotify.git@dev")
    print()
    print("Or if you're using conda:")
    print(
        "  conda install -c conda-forge git+https://github.com/DraftKinner/zotify.git@dev"
    )
    print()
    sys.exit(1)


class ZotifyCredentialsGenerator:
    """Generate Zotify credentials using OAuth authentication"""

    def __init__(self, output_file: str = "zotify_credentials.json"):
        self.output_file = Path(output_file)
        self.username: str | None = None
        self.oauth: OAuth | None = None
        self.session: Session | None = None

    def print_banner(self):
        """Print welcome banner"""
        print("=" * 60)
        print("🎵 Zotify Credentials Generator for aimleechbot")
        print("=" * 60)
        print()
        print("This script will help you generate Spotify credentials")
        print("for use with the aimleechbot Zotify feature.")
        print()
        print("⚠️  Requirements:")
        print("   • Spotify Premium account (required)")
        print("   • Web browser for authentication")
        print("   • Internet connection")
        print()

    def get_username(self) -> str:
        """Get Spotify username from user"""
        while True:
            username = input("🔑 Enter your Spotify username/email: ").strip()
            if username:
                return username
            print("❌ Username cannot be empty. Please try again.")

    def start_oauth_flow(self) -> str:
        """Start OAuth authentication flow"""
        print(f"\n🔄 Starting OAuth authentication for: {self.username}")
        print("⏳ Setting up authentication server...")

        try:
            self.oauth = OAuth(self.username)
            auth_url = self.oauth.auth_interactive()

            # Try to open browser automatically
            try:
                webbrowser.open(auth_url)
                print("🌐 Browser opened automatically")
            except Exception:
                print("⚠️  Could not open browser automatically")

            return auth_url
        except Exception as e:
            print(f"❌ Error starting OAuth flow: {e}")
            raise

    def wait_for_authentication(self) -> bool:
        """Wait for user to complete OAuth authentication"""
        print("\n🌐 Please complete the authentication in your browser...")
        print("⏳ Waiting for authentication to complete...")
        print("   (This may take up to 2 minutes)")

        # Wait for OAuth to complete (max 2 minutes)
        max_wait = 120  # 2 minutes
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                # Try to get the token (this will succeed once OAuth is complete)
                token = self.oauth.await_token()
                if token:
                    print("✅ Authentication completed successfully!")
                    return True
            except Exception:
                # OAuth not complete yet, continue waiting
                time.sleep(2)
                print(".", end="", flush=True)

        print("\n❌ Authentication timed out. Please try again.")
        return False

    def create_session(self) -> bool:
        """Create Zotify session with OAuth credentials"""
        try:
            print("\n🔄 Creating Zotify session...")

            # Create session with OAuth and save credentials
            self.session = Session.from_oauth(
                self.oauth, save_file=self.output_file, language="en"
            )

            print("✅ Session created successfully!")
            return True

        except Exception as e:
            print(f"❌ Error creating session: {e}")
            return False

    def validate_credentials(self) -> bool:
        """Validate that credentials file was created and is valid"""
        try:
            if not self.output_file.exists():
                print(f"❌ Credentials file not found: {self.output_file}")
                return False

            # Read and validate JSON
            with open(self.output_file) as f:
                credentials = json.load(f)

            # Basic validation
            if not isinstance(credentials, dict):
                print("❌ Invalid credentials format: not a JSON object")
                return False

            # Check for required fields (basic check)
            if not credentials:
                print("❌ Credentials file is empty")
                return False

            print("✅ Credentials file validated successfully!")
            return True

        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in credentials file: {e}")
            return False
        except Exception as e:
            print(f"❌ Error validating credentials: {e}")
            return False

    def print_success_info(self):
        """Print success information and next steps"""
        file_size = self.output_file.stat().st_size

        print("\n" + "=" * 60)
        print("🎉 SUCCESS! Zotify credentials generated successfully!")
        print("=" * 60)
        print()
        print(f"📁 Credentials saved to: {self.output_file.absolute()}")
        print(f"📊 File size: {file_size} bytes")
        print()
        print("📋 Next steps:")
        print("1. Upload this file to your bot:")
        print(
            "   • Method 1: Bot Settings → Zotify → Authentication → Upload Credentials"
        )
        print(
            "   • Method 2: Bot Settings → Private Files → Upload zotify_credentials.json"
        )
        print()
        print("2. Start downloading music with Zotify commands:")
        print("   • /zotifymirror <spotify_url>")
        print("   • /zotifyleech <spotify_url>")
        print("   • /zrs <search_query>")
        print()
        print("⚠️  Important notes:")
        print("   • Keep this credentials file secure")
        print("   • Don't share it with others")
        print("   • Your Spotify Premium subscription is required")
        print()

    def cleanup_on_error(self):
        """Clean up files if generation failed"""
        try:
            if self.output_file.exists():
                self.output_file.unlink()
                print(f"🧹 Cleaned up incomplete file: {self.output_file}")
        except Exception:
            pass

    def generate(self) -> bool:
        """Main generation process"""
        try:
            # Get username
            self.username = self.get_username()

            # Start OAuth flow
            auth_url = self.start_oauth_flow()

            print("\n🔗 Please open this URL in your browser:")
            print(f"   {auth_url}")
            print()
            print("📋 Steps to complete authentication:")
            print("1. Click the link above or copy-paste it into your browser")
            print("2. Log in to your Spotify Premium account")
            print("3. Click 'Agree' to authorize the application")
            print("4. Wait for the success message")

            # Wait for authentication
            if not self.wait_for_authentication():
                return False

            # Create session and save credentials
            if not self.create_session():
                return False

            # Validate generated credentials
            if not self.validate_credentials():
                return False

            # Print success info
            self.print_success_info()
            return True

        except KeyboardInterrupt:
            print("\n\n⚠️  Process interrupted by user")
            self.cleanup_on_error()
            return False
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            self.cleanup_on_error()
            return False


def print_help():
    """Print help information"""
    print("🎵 Zotify Credentials Generator")
    print()
    print("Usage:")
    print("  python generate_zotify_credentials.py [output_file]")
    print()
    print("Arguments:")
    print("  output_file    Optional. Name of the credentials file to create")
    print("                 Default: zotify_credentials.json")
    print()
    print("Examples:")
    print("  python generate_zotify_credentials.py")
    print("  python generate_zotify_credentials.py my_spotify_creds.json")
    print()
    print("Requirements:")
    print("  • Spotify Premium account (mandatory)")
    print("  • Internet connection")
    print("  • Web browser for OAuth authentication")
    print("  • Zotify library: pip install zotify")
    print()


def main():
    """Main function"""
    # Check for help flag
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help", "help"]:
        print_help()
        return 0

    # Parse command line arguments
    output_file = "zotify_credentials.json"
    if len(sys.argv) > 1:
        output_file = sys.argv[1]

    # Create generator
    generator = ZotifyCredentialsGenerator(output_file)

    # Print banner
    generator.print_banner()

    # Check if output file already exists
    if generator.output_file.exists():
        response = input(
            f"⚠️  File '{output_file}' already exists. Overwrite? (y/N): "
        )
        if response.lower() not in ["y", "yes"]:
            print("❌ Operation cancelled.")
            return 1

    # Generate credentials
    success = generator.generate()

    if success:
        print("🎵 Happy downloading with aimleechbot! 🚀")
        return 0

    print("\n❌ Failed to generate credentials. Please try again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
