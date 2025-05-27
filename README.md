# DXP Tracker Discord Bot

A Discord bot to track RuneScape players' Double XP (DXP) gains from RunePixels and display leaderboards and skill bests directly in Discord.

## Features

* Add/Remove players (RSN) to be tracked and associate them with Discord users.
* Admin role management for bot commands.
* Fetch current DXP data from RunePixels for registered players concurrently.
* Display an overall DXP leaderboard based on calculated total DXP.
* Display "Skill Best" assignments, showing which player is best in each skill. This calculation:
    * Excludes the "Overall" skill.
    * Limits each player to being "best" in a maximum of 3 skills.
    * Uses a sophisticated assignment logic: #1 players claim their top 3 skills (based on their own DXP in those skills), then unassigned skills are filled via an iterative player-preferred roll-down/upgrade process.
    * Respects a configurable cutoff player name for "Skill Best" eligibility.

## Commands

All commands are initiated using slash (`/`) commands.

### Owner-Only Commands:
(Only the user ID specified as `OWNER_ID` in the script can use these)

* `/addadmin user:<@User>`
    * Adds the mentioned Discord user to the bot's admin list. Admins can use player management and DXP retrieval commands.
* `/removeadmin user:<@User>`
    * Removes the mentioned Discord user from the bot's admin list.

### Admin & Owner Commands:

* `/addplayer user:<@User> rsn:<RuneScapeName>`
    * Associates a RuneScape Name (RSN) with the mentioned Discord user for DXP tracking.
    * Example: `/addplayer user:@Player1 rsn:Zezima`
* `/removeplayer user:<@User>`
    * Removes the specified Discord user and their associated RSN from DXP tracking.
* `/getdxp [user:<@User>]`
    * Fetches and displays DXP information.
    * If a `user` is specified, it shows an embed with that player's DXP for each skill and their total calculated DXP.
    * If no `user` is specified, it displays two embeds for all tracked players:
        1.  **Overall DXP Leaderboard Embed:** Lists all tracked players and their total DXP gained (sum of DXP from individual skills, excluding the "Overall" skill total from RunePixels), sorted from highest to lowest.
        2.  **Skill Best Assignments Embed:** Lists each skill and the player who is currently "best" in that skill based on the complex assignment logic.

## Setup

1.  **Prerequisites:**
    * Python 3.8+
    * Google Chrome browser installed (for Selenium).
    * ChromeDriver installed and in your system's PATH, or its path specified via the `WEBDRIVER_PATH` variable in the script. Ensure ChromeDriver version matches your Chrome browser version.

2.  **Discord Bot Application:**
    * Go to the [Discord Developer Portal](https://discord.com/developers/applications).
    * Create a New Application.
    * Go to the "Bot" tab, add a bot, and **copy the Bot Token**.
    * Under "Privileged Gateway Intents," ensure the **Server Members Intent** is enabled if you plan to frequently resolve user IDs to member objects or use features that require it. The current script has `intents.members = True`.

3.  **Python Dependencies:**
    * Create a `requirements.txt` file with the following content:
        ```
        requests
        beautifulsoup4
        selenium
        nextcord
        # gspread and related google libraries are NOT needed for this version
        ```
    * Install them: `pip install -r requirements.txt`

4.  **Configuration (`bot.py`):**
    * Open `bot.py` and fill in the **REQUIRED** fields in the `--- Configuration ---` section:
        * `BOT_TOKEN`: Your Discord bot token.
        * `OWNER_ID`: Your Discord User ID.
        * `TEST_GUILD_ID`: The ID of your Discord server where you want to test the slash commands instantly. For global commands (which can take up to an hour to register), you can remove the `guild_ids=[TEST_GUILD_ID]` part from command definitions later.
        * (Optional) `WEBDRIVER_PATH`: Set to the full path of your `chromedriver.exe` (or `chromedriver`) if it's not in your system PATH. Otherwise, leave as `None`.
        * Adjust `MAX_CONCURRENT_PLAYERS`, `PAGE_LOAD_DELAY`, and `SKILL_BEST_CUTOFF_PLAYER_NAME` as needed.

5.  **Running the Bot:**
    * Execute the script: `python bot.py`

## Data Files

The bot will create/use the following JSON files in the same directory where it runs:
* `players_data.json`: Stores the mapping of Discord User IDs to their RSNs and other metadata.
* `admins_data.json`: Stores a list of Discord User IDs who are bot admins.

## Acknowledgements

* This bot retrieves DXP data from [RunePixels](https://runepixels.com/). Thank you to RunePixels for providing this valuable data source!
