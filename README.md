# DXP Tracker Discord Bot

A Discord bot to track RuneScape players' Double XP (DXP) gains from RunePixels and display leaderboards and skill bests.

## Features

* Add/Remove players (RSN) to be tracked and associate them with Discord users.
* Admin role management for bot commands.
* Fetch current DXP data from RunePixels for registered players.
* Display an overall DXP leaderboard.
* Display "Skill Best" assignments, showing which player is best in each skill based on complex logic (3-skill limit per player, player-preferred upgrades, exclusion of "Overall" skill, and an optional cutoff player).
* Optional integration with Google Sheets for DXP data logging and "Skill Best" column updates (if `ENABLE_GOOGLE_SHEETS_UPDATE` is True in the script).

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
    * If a `user` is specified, it shows a breakdown of that player's DXP for each skill and their total calculated DXP.
    * If no `user` is specified, it displays for all tracked players:
        1.  **Overall DXP Leaderboard Embed:** Lists all tracked players and their total DXP gained (sum of DXP from individual skills, excluding the "Overall" skill total from RunePixels), sorted from highest to lowest.
        2.  **Skill Best Assignments Embed:** Lists each skill and the player who is currently "best" in that skill. This calculation:
            * Excludes the "Overall" skill from being a category.
            * Limits each player to being "best" in a maximum of 3 skills.
            * Uses a sophisticated assignment logic where players who are #1 in skills get to pick their top 3 based on their own DXP, and then unassigned skills are filled via an iterative player-preferred roll-down/upgrade process.
            * Respects the `SKILL_BEST_CUTOFF_PLAYER_NAME` configured in the script (players at or after this name in the configured list are not eligible for "Skill Best").

## Setup

1.  **Prerequisites:**
    * Python 3.8+
    * Google Chrome browser installed (for Selenium)
    * ChromeDriver installed and in your system's PATH, or path specified in `WEBDRIVER_PATH` in the script. Ensure ChromeDriver version matches your Chrome browser version.

2.  **Discord Bot Application:**
    * Go to the [Discord Developer Portal](https://discord.com/developers/applications).
    * Create a New Application.
    * Go to the "Bot" tab, add a bot, and **copy the Bot Token**.
    * Enable "Privileged Gateway Intents" if needed (Server Members Intent, Message Content Intent - though slash commands reduce the need for Message Content). The current script enables `intents.members = True`.

3.  **Python Dependencies:**
    * Create a `requirements.txt` file with the following content:
        ```
        requests
        beautifulsoup4
        selenium
        nextcord
        gspread 
        # google-auth-httplib2 and google-api-python-client are often installed as gspread dependencies
        ```
    * Install them: `pip install -r requirements.txt`
        *(Note: If `ENABLE_GOOGLE_SHEETS_UPDATE` is `False`, `gspread` and its dependencies are not strictly required by the bot's core Discord functionality, but the script will try to import `gspread` if enabled).*

4.  **Configuration (`bot.py`):**
    * Open `bot.py` and fill in the **REQUIRED** fields in the `--- Configuration ---` section:
        * `BOT_TOKEN`: Your Discord bot token.
        * `OWNER_ID`: Your Discord User ID.
        * `TEST_GUILD_ID`: The ID of your Discord server where you want to test the slash commands instantly. Remove or set to `None` for global registration (can take up to an hour).
        * `PLAYER_RSN_LIST` and `PLAYER_SHEET_COLUMN_NAMES`: While player data is primarily managed via bot commands and `players_data.json`, these lists can serve as an initial seed or for reference. The Google Sheets functionality (if enabled) uses `PLAYER_SHEET_COLUMN_NAMES` to map to sheet headers.
        * `WEBDRIVER_PATH`: Set to the full path of your `chromedriver.exe` (or `chromedriver`) if it's not in your system PATH. Otherwise, leave as `None`.
        * Set `ENABLE_DISCORD_NOTIFICATIONS` and `ENABLE_GOOGLE_SHEETS_UPDATE` as needed.
        * If `ENABLE_GOOGLE_SHEETS_UPDATE = True`, you **must** also configure:
            * `GOOGLE_SHEETS_CREDENTIALS_PATH`: Path to your Google Cloud service account JSON key file.
            * `GOOGLE_SHEET_TITLE`: The exact title of your Google Spreadsheet.
            * `DXP_WORKSHEET_NAME`, `DXP_PLAYER_HEADER_ROW`, `DXP_SKILL_COLUMN_LETTER`, `SKILL_BEST_COLUMN_LETTER`.
        * Adjust `SKILL_BEST_CUTOFF_PLAYER_NAME` if desired.

5.  **Google Sheets API Setup (if using Google Sheets integration):**
    * Go to the [Google Cloud Console](https://console.cloud.google.com/).
    * Create a new project or use an existing one.
    * Enable the "Google Sheets API" and "Google Drive API".
    * Create Service Account credentials (JSON key file). Download this file and update `GOOGLE_SHEETS_CREDENTIALS_PATH` in the script.
    * Share your target Google Sheet with the `client_email` found in the service account JSON file, giving it "Editor" permissions.

6.  **Running the Bot:**
    * Execute the script: `python bot.py`

## Data Files

The bot will create/use the following JSON files in the same directory:
* `players_data.json`: Stores the mapping of Discord User IDs to their RSNs.
* `admins_data.json`: Stores a list of Discord User IDs who are bot admins.

## Acknowledgements

* This bot retrieves DXP data from [RunePixels](https://runepixels.com/). Thank you to RunePixels for providing this valuable data source!

---
