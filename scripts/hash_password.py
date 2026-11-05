"""Generate a password_hash value for .streamlit/secrets.toml.

Usage: python scripts/hash_password.py
The password is read with getpass (not echoed, not stored in shell history).
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicepilot.auth import hash_password  # noqa: E402

first = getpass.getpass("New admin password: ")
if len(first) < 12:
    sys.exit("Use at least 12 characters.")
if first != getpass.getpass("Repeat password: "):
    sys.exit("Passwords do not match.")

print("\nPut this in .streamlit/secrets.toml:\n")
print("[admin]")
print(f'password_hash = "{hash_password(first)}"')
