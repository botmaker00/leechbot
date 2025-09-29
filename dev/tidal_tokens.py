"""
Script to get tidal tokens using tidalapi

Requirements: pip install tidalapi

"""

import sys
import time

import tidalapi

session = tidalapi.Session()

print("Logging in via Tidal device code method...")
try:
    login, future = session.login_oauth()
    print(f"Visit {login.verification_uri_complete} to log in")
    print(f"Or go to {login.verification_uri} and enter code: {login.user_code}")
    print(f"The code will expire in {login.expires_in} seconds")

    print("Waiting for authentication...")
    future.result()

except Exception as e:
    print(f"OAuth login failed: {e}")
    print("Trying simple login method...")

    def custom_print(message):
        print(f"Login info: {message}")

    try:
        session.login_oauth_simple(fn_print=custom_print)
    except Exception as e2:
        print(f"Simple login also failed: {e2}")
        sys.exit(1)

if session.check_login():
    print("\n✅ Authentication successful!")

    print(f"Username: {session.user.username if session.user else 'N/A'}")
    print(f"User ID: {session.user.id if session.user else 'N/A'}")
    print(f"Token Type: {session.token_type}")
    print(f"Access Token: {session.access_token}")
    print(f"Refresh Token: {session.refresh_token}")
    print(f"Expiry (epoch): {session.expiry_time}")

    try:
        if session.user:
            if hasattr(session.user, "country_code"):
                print(f"Country Code: {session.user.country_code}")
            elif hasattr(session.user, "country"):
                print(f"Country: {session.user.country}")

            if hasattr(session.user, "subscription") and session.user.subscription:
                print(f"Subscription type: {session.user.subscription.type}")
            elif hasattr(session.user, "subscription_type"):
                print(f"Subscription type: {session.user.subscription_type}")
    except Exception as e:
        print(f"Could not get additional user info: {e}")

    with open("tidal_tokens.txt", "w") as f:
        f.write(f"Access Token: {session.access_token}\n")
        f.write(f"Refresh Token: {session.refresh_token}\n")
        f.write(f"Token Type: {session.token_type}\n")
        f.write(f"Expiry Time: {session.expiry_time}\n")

        if session.expiry_time:
            if hasattr(session.expiry_time, "timestamp"):
                f.write(
                    f"Expires At: {session.expiry_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                )
                f.write(
                    f"Expiry Timestamp: {int(session.expiry_time.timestamp())}\n"
                )
            else:
                f.write(f"Expires At: {time.ctime(session.expiry_time)}\n")
                f.write(f"Expiry Timestamp: {session.expiry_time}\n")
        else:
            f.write("Expires At: N/A\n")

        if session.user:
            f.write(f"User ID: {session.user.id}\n")
            f.write(f"Username: {session.user.username}\n")

            if hasattr(session.user, "country_code"):
                f.write(f"Country Code: {session.user.country_code}\n")
            elif hasattr(session.user, "country"):
                f.write(f"Country: {session.user.country}\n")

    print("\n💾 Tokens saved to 'tidal_tokens.txt'")

else:
    print("❌ Authentication failed!")
    sys.exit(1)
