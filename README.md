# MLB Steals Alert Bot V2

Railway-ready Discord bot for MLB stolen base alerts.

## Duplicate-post fix

Make sure Railway only has ONE active service/worker running this bot.

This version also includes:
- `runtime.txt` to force Python 3.11.9
- Startup dedupe so old steals do not repost after redeploy/restart
- Stronger dedupe key

## Railway variables

```env
DISCORD_TOKEN=your_bot_token
DISCORD_CHANNEL_ID=your_channel_id
POLL_SECONDS=15
ALERT_CAUGHT_STEALING=false
ALERT_PICKOFF_CAUGHT_STEALING=false
ALERT_OLD_EVENTS_ON_STARTUP=false
```

## Test

In Discord:

```text
!stealstest
```
