# Telegram Personal Device Utility — v3

Owner-controlled Telegram utility for a Termux device. It only operates for
`OWNER_ID` and only reads the explicitly configured shared-storage folders.

## Security
- No private Telegram-chat extraction.
- No password/OTP/cookie/token harvesting.
- No Android permission bypass.
- No hidden camera/microphone surveillance.
- Bot token is read from the `BOT_TOKEN` environment variable instead of being
  stored in `config.py`.
- File sending is restricted by configured folders, extension, maximum file
  size, and per-request count.

## Install on Termux

```bash
pkg update -y
pkg install python -y
termux-setup-storage
pip install -r requirements.txt
```

Set credentials in the shell:

```bash
export BOT_TOKEN="YOUR_NEW_BOT_TOKEN"
export OWNER_ID="YOUR_TELEGRAM_USER_ID"
python main.py
```

For battery/Wi-Fi commands, install the Termux:API app and package if needed.

## Commands

`/start` `/menu` `/help` `/info` `/battery` `/network` `/apps` `/photos`
`/videos` `/files` `/list` `/status` `/ping`

## Storage

The bot checks:
- `~/storage/shared/Pictures`
- `~/storage/shared/DCIM`
- `~/storage/shared/Movies`
- `~/storage/shared/Download`

Project-local folders can be enabled with `INCLUDE_PROJECT_DIRS=1`.

## Important

This v3 does not include the old unused admin-panel configuration. If a web
admin panel is needed, it should be added separately with authentication and
local-only binding by default.
