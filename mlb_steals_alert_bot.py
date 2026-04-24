import os
import logging
import asyncio
from typing import Dict, Any, List, Optional, Set

import requests
import discord
from discord.ext import commands, tasks

# =========================
# MLB STEALS ALERT BOT - V2
# =========================
# Fixes:
# - Prevents reposting old steals on startup/redeploy
# - Stronger dedupe key
# - Only alerts newly discovered steal events after bot is ready
#
# Environment variables:
# DISCORD_TOKEN=your_discord_bot_token
# DISCORD_CHANNEL_ID=your_channel_id
# POLL_SECONDS=15
# ALERT_CAUGHT_STEALING=false
# ALERT_PICKOFF_CAUGHT_STEALING=false
# ALERT_OLD_EVENTS_ON_STARTUP=false


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("mlb_steals_alert_bot")


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "15"))

ALERT_CAUGHT_STEALING = os.getenv("ALERT_CAUGHT_STEALING", "false").lower() == "true"
ALERT_PICKOFF_CAUGHT_STEALING = os.getenv("ALERT_PICKOFF_CAUGHT_STEALING", "false").lower() == "true"
ALERT_OLD_EVENTS_ON_STARTUP = os.getenv("ALERT_OLD_EVENTS_ON_STARTUP", "false").lower() == "true"

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_LIVE_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

seen_steal_events: Set[str] = set()
startup_seed_complete = False


def mlb_logo(team_id: Optional[int]) -> Optional[str]:
    if not team_id:
        return None
    return f"https://www.mlbstatic.com/team-logos/{team_id}.png"


def get_today_game_pks() -> List[int]:
    try:
        r = requests.get(
            MLB_SCHEDULE_URL,
            params={"sportId": 1, "hydrate": "team"},
            timeout=15
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("Failed to fetch MLB schedule: %s", e)
        return []

    game_pks: List[int] = []

    for date_block in data.get("dates", []):
        for game in date_block.get("games", []):
            game_pk = game.get("gamePk")
            status = game.get("status", {}).get("detailedState", "").lower()

            if not game_pk:
                continue

            if status in {
                "postponed",
                "cancelled",
                "canceled",
                "suspended",
                "delayed start",
            }:
                continue

            game_pks.append(int(game_pk))

    return game_pks


def get_live_game(game_pk: int) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(MLB_LIVE_URL.format(game_pk=game_pk), timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("Failed to fetch game %s feed: %s", game_pk, e)
        return None


def team_name(game_data: Dict[str, Any], side: str) -> str:
    return (
        game_data
        .get("gameData", {})
        .get("teams", {})
        .get(side, {})
        .get("name", side.title())
    )


def team_id(game_data: Dict[str, Any], side: Optional[str]) -> Optional[int]:
    if not side:
        return None

    return (
        game_data
        .get("gameData", {})
        .get("teams", {})
        .get(side, {})
        .get("id")
    )


def game_score_line(game_data: Dict[str, Any]) -> str:
    linescore = game_data.get("liveData", {}).get("linescore", {})
    teams = linescore.get("teams", {})

    away_runs = teams.get("away", {}).get("runs", 0)
    home_runs = teams.get("home", {}).get("runs", 0)

    away = team_name(game_data, "away")
    home = team_name(game_data, "home")

    return f"{away} {away_runs} - {home_runs} {home}"


def inning_text(play: Dict[str, Any], game_data: Dict[str, Any]) -> str:
    about = play.get("about", {})
    inning = about.get("inning")
    half = about.get("halfInning")

    if inning and half:
        return f"{half.title()} {inning}"

    linescore = game_data.get("liveData", {}).get("linescore", {})
    current_inning = linescore.get("currentInning")
    current_half = linescore.get("inningHalf")

    if current_inning and current_half:
        return f"{str(current_half).title()} {current_inning}"

    return "Inning unavailable"


def get_player_name(game_data: Dict[str, Any], player_id: Optional[int], fallback: str = "Runner") -> str:
    if not player_id:
        return fallback

    people = game_data.get("gameData", {}).get("players", {})
    player = people.get(f"ID{player_id}", {})

    return player.get("fullName") or player.get("boxscoreName") or fallback


def player_headshot(player_id: Optional[int]) -> Optional[str]:
    if not player_id:
        return None
    return f"https://img.mlbstatic.com/mlb-photos/image/upload/w_240,q_100/v1/people/{player_id}/headshot/67/current"


def offense_side_for_play(play: Dict[str, Any]) -> Optional[str]:
    half = play.get("about", {}).get("halfInning", "").lower()

    if half == "top":
        return "away"

    if half == "bottom":
        return "home"

    return None


def steal_base_label(event: str, movement: Dict[str, Any]) -> str:
    event_l = event.lower()
    end = movement.get("end")

    if end:
        base_map = {
            "1B": "second base",
            "2B": "third base",
            "3B": "home",
            "score": "home",
        }
        return base_map.get(str(end), str(end))

    if "2nd" in event_l or "second" in event_l:
        return "second base"
    if "3rd" in event_l or "third" in event_l:
        return "third base"
    if "home" in event_l:
        return "home"

    return "a base"


def runner_id_from_runner(runner: Dict[str, Any]) -> Optional[int]:
    return runner.get("details", {}).get("runner", {}).get("id")


def make_steal_key(game_pk: int, play: Dict[str, Any], runner: Dict[str, Any]) -> str:
    about = play.get("about", {})
    details = runner.get("details", {})
    movement = runner.get("movement", {})

    at_bat_index = about.get("atBatIndex", "")
    play_id = about.get("playId", "") or about.get("playGuid", "")
    runner_id = runner_id_from_runner(runner) or ""
    event_type = details.get("eventType", "")
    event = details.get("event", "")
    start_base = movement.get("start", "")
    end_base = movement.get("end", "")
    is_out = movement.get("isOut", "")

    return "|".join(
        str(x) for x in [
            game_pk,
            at_bat_index,
            play_id,
            runner_id,
            event_type,
            event,
            start_base,
            end_base,
            is_out,
        ]
    )


def find_steal_events(game_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    plays = (
        game_data
        .get("liveData", {})
        .get("plays", {})
        .get("allPlays", [])
    )

    events: List[Dict[str, Any]] = []
    game_pk = int(game_data.get("gamePk"))

    for play in plays:
        for runner in play.get("runners", []):
            details = runner.get("details", {})
            movement = runner.get("movement", {})

            event = details.get("event", "") or ""
            event_type = details.get("eventType", "") or ""

            event_l = event.lower()
            event_type_l = event_type.lower()

            stolen_base = (
                "stolen base" in event_l
                or event_type_l == "stolen_base"
                or event_type_l.startswith("stolen_base")
            )

            caught_stealing = (
                "caught stealing" in event_l
                or event_type_l == "caught_stealing"
                or event_type_l.startswith("caught_stealing")
            )

            pickoff_caught_stealing = (
                "pickoff caught stealing" in event_l
                or event_type_l == "pickoff_caught_stealing"
                or event_type_l.startswith("pickoff_caught_stealing")
            )

            should_alert = stolen_base

            if ALERT_CAUGHT_STEALING and caught_stealing:
                should_alert = True

            if ALERT_PICKOFF_CAUGHT_STEALING and pickoff_caught_stealing:
                should_alert = True

            if not should_alert:
                continue

            key = make_steal_key(game_pk, play, runner)

            events.append({
                "gamePk": game_pk,
                "key": key,
                "play": play,
                "runner": runner,
                "runnerId": runner_id_from_runner(runner),
                "event": event or event_type or "Stolen Base",
                "eventType": event_type,
                "base": steal_base_label(event, movement),
                "isOut": bool(movement.get("isOut")),
            })

    return events


async def send_steal_alert(channel: discord.TextChannel, game_data: Dict[str, Any], steal: Dict[str, Any]) -> None:
    play = steal["play"]
    runner_id = steal.get("runnerId")
    runner_name = get_player_name(game_data, runner_id, "Runner")

    event = steal.get("event", "Stolen Base")
    base = steal.get("base", "a base")
    is_out = steal.get("isOut", False)

    offense_side = offense_side_for_play(play)
    logo_url = mlb_logo(team_id(game_data, offense_side))

    score = game_score_line(game_data)
    inning = inning_text(play, game_data)

    title = "🚨 MLB Stolen Base Alert"
    description = f"**{runner_name}** stole **{base}**."
    color = 0x2ecc71

    if is_out or "caught stealing" in event.lower():
        title = "🚨 MLB Caught Stealing Alert"
        description = f"**{runner_name}** was caught stealing **{base}**."
        color = 0xe67e22

    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )

    embed.add_field(name="Game", value=score, inline=False)
    embed.add_field(name="Inning", value=inning, inline=True)
    embed.add_field(name="Event", value=event, inline=True)

    game_pk = steal.get("gamePk")
    if game_pk:
        embed.add_field(
            name="Game Link",
            value=f"https://www.mlb.com/gameday/{game_pk}",
            inline=False
        )

    headshot = player_headshot(runner_id)
    if headshot:
        embed.set_thumbnail(url=headshot)

    if logo_url:
        embed.set_footer(text="MLB Steals Alert Bot", icon_url=logo_url)
    else:
        embed.set_footer(text="MLB Steals Alert Bot")

    await channel.send(embed=embed)


def collect_current_steal_keys() -> int:
    count = 0

    for game_pk in get_today_game_pks():
        game_data = get_live_game(game_pk)
        if not game_data:
            continue

        for steal in find_steal_events(game_data):
            seen_steal_events.add(steal["key"])
            count += 1

    return count


@tasks.loop(seconds=POLL_SECONDS)
async def poll_mlb_steals():
    global startup_seed_complete

    if not DISCORD_CHANNEL_ID:
        log.error("Missing DISCORD_CHANNEL_ID")
        return

    if not startup_seed_complete and not ALERT_OLD_EVENTS_ON_STARTUP:
        seeded = collect_current_steal_keys()
        startup_seed_complete = True
        log.info("Startup seed complete. Marked %s existing steal events as already seen.", seeded)
        return

    startup_seed_complete = True

    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(DISCORD_CHANNEL_ID)
        except Exception as e:
            log.error("Could not find Discord channel %s: %s", DISCORD_CHANNEL_ID, e)
            return

    game_pks = get_today_game_pks()

    if not game_pks:
        log.info("No MLB games found today.")
        return

    new_alerts = 0

    for game_pk in game_pks:
        game_data = get_live_game(game_pk)
        if not game_data:
            continue

        steals = find_steal_events(game_data)

        for steal in steals:
            key = steal["key"]

            if key in seen_steal_events:
                continue

            seen_steal_events.add(key)
            new_alerts += 1

            try:
                await send_steal_alert(channel, game_data, steal)
                await asyncio.sleep(0.5)
            except Exception as e:
                log.exception("Failed sending steal alert: %s", e)

    log.info("Poll complete. New steal alerts posted: %s", new_alerts)


@poll_mlb_steals.before_loop
async def before_poll():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    log.info("Logged in as %s (%s)", bot.user, bot.user.id if bot.user else "unknown")

    if not poll_mlb_steals.is_running():
        poll_mlb_steals.start()


@bot.command(name="stealstest")
async def steals_test(ctx):
    embed = discord.Embed(
        title="✅ MLB Steals Alert Bot Test",
        description="Bot is online and ready to post stolen base alerts.",
        color=0x2ecc71
    )
    await ctx.send(embed=embed)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("Missing DISCORD_TOKEN environment variable.")

    if not DISCORD_CHANNEL_ID:
        raise RuntimeError("Missing DISCORD_CHANNEL_ID environment variable.")

    bot.run(DISCORD_TOKEN)
