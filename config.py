"""Configuration for Telegram Personal Device Utility v3.

Prefer environment variables so secrets are not stored in source control.
"""
import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

HOME = "/data/data/com.termux/files/home"
SHARED = HOME + "/storage/shared"

PHOTO_DIRS = [SHARED + "/Pictures", SHARED + "/DCIM"]
VIDEO_DIRS = [SHARED + "/Movies", SHARED + "/DCIM"]
FILE_DIRS = [SHARED + "/Download"]

# Maximum file size to attempt sending (Telegram/account limits can vary).
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "999999"))
MAX_FILES_PER_REQUEST = int(os.getenv("MAX_FILES_PER_REQUEST", "99999"))

# Optional project-local folders. Enable only if desired.
INCLUDE_PROJECT_DIRS = os.getenv("INCLUDE_PROJECT_DIRS", "1") == "1"
if INCLUDE_PROJECT_DIRS:
    BASE = os.path.dirname(os.path.abspath(__file__))
    PHOTO_DIRS.append(os.path.join(BASE, "photos"))
    VIDEO_DIRS.append(os.path.join(BASE, "videos"))
    FILE_DIRS.append(os.path.join(BASE, "files"))
