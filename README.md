# MLB Steals Alert Bot

Discord bot for Railway that posts MLB stolen base alerts using MLB Stats API live game feeds.

## What it does

- Checks live MLB games every 15 seconds
- Finds stolen base events
- Posts Discord embed alerts
- Includes runner name, inning, score, MLB game link, and player headshot
- Dedupes alerts so the same steal does not post repeatedly

## Files

- `mlb_steals_alert_bot.py` - main bot
- `requirements.txt` - Python dependencies
- `Procfile` - Railway worker start command
- `.env.example` - environment variable example

## Discord setup

### 1. Create the Discord app

1. Go to the Discord Developer Portal.
2. Click **New Application**.
3. Name it something like `MLB Steals Alert Bot`.
4. Go to **Bot**.
5. Click **Add Bot**.
6. Click **Reset Token** or **View Token**.
7. Copy the token. This is your `DISCORD_TOKEN`.

### 2. Turn on bot settings

In the **Bot** section:

- Turn on **Message Content Intent** if you want the `!stealstest` command to work.
- Leave other intents off unless you need them.

### 3. Invite the bot to your server

1. Go to **OAuth2 → URL Generator**.
2. Under **Scopes**, check:
   - `bot`
3. Under **Bot Permissions**, check:
   - `Send Messages`
   - `Embed Links`
   - `Read Message History`
   - `View Channels`
4. Copy the generated URL.
5. Open it in your browser and invite the bot to your server.

### 4. Get your Discord channel ID

1. In Discord, go to **User Settings → Advanced**.
2. Turn on **Developer Mode**.
3. Right-click the channel where alerts should post.
4. Click **Copy Channel ID**.
5. This is your `DISCORD_CHANNEL_ID`.

## GitHub setup

1. Create a new GitHub repository.
2. Upload these files:
   - `mlb_steals_alert_bot.py`
   - `requirements.txt`
   - `Procfile`
   - `.env.example`
   - `README.md`
3. Commit the files.

## Railway setup

### 1. Create project

1. Go to Railway.
2. Click **New Project**.
3. Choose **Deploy from GitHub repo**.
4. Pick your new repository.

### 2. Add variables

In Railway:

1. Open your project.
2. Go to **Variables**.
3. Add:

```env
DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_CHANNEL_ID=your_discord_channel_id_here
POLL_SECONDS=15
ALERT_CAUGHT_STEALING=false
ALERT_PICKOFF_CAUGHT_STEALING=false
```

Do not include quotes around the values.

### 3. Deploy

Railway should detect the `Procfile` and run:

```bash
python mlb_steals_alert_bot.py
```

Check the **Deploy Logs**. You should see something like:

```text
Logged in as MLB Steals Alert Bot
Checking MLB games for steal events...
```

## Test command

In your Discord channel, type:

```text
!stealstest
```

The bot should reply with a test embed.

## Optional settings

### Poll faster or slower

Change:

```env
POLL_SECONDS=15
```

Lower is faster. I recommend keeping it at 10-20 seconds.

### Alert caught stealing too

Change:

```env
ALERT_CAUGHT_STEALING=true
```

### Alert pickoff caught stealing too

Change:

```env
ALERT_PICKOFF_CAUGHT_STEALING=true
```

## Common Railway issues

### Bot says missing token

Make sure Railway has:

```env
DISCORD_TOKEN=...
```

Then redeploy.

### Bot says missing channel ID

Make sure Railway has:

```env
DISCORD_CHANNEL_ID=...
```

The channel ID should be numbers only.

### Bot logs in but does not post

Check:

- Bot is invited to the server
- Bot can view the channel
- Bot has permission to send messages
- Bot has permission to embed links
- Channel ID is correct

### No alerts are posting

There may be no live games or no steals yet. Use:

```text
!stealstest
```

to confirm the bot is online.
