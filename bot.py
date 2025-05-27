import requests
from bs4 import BeautifulSoup
import time
import json
import urllib.parse
import datetime
import os
from collections import defaultdict
import concurrent.futures
import threading

import nextcord
from nextcord.ext import commands

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# --- Constants ---
NO_DATA_PLACEHOLDER = "--"
MAX_EMBED_FIELDS = 25       # Max fields per Discord embed
MAX_EMBEDS_PER_MESSAGE = 10 # Max embeds Discord allows in a single message
MAX_SKILLS_FOR_BEST_PLAYER = 3 # For the "Skill Best" calculation
# --- End Constants ---

# --- Configuration ---
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # !!! REQUIRED: Replace with your bot token !!!
OWNER_ID = 123456789012345678      # !!! REQUIRED: Your Discord User ID !!!
# !!! REQUIRED: Your Test Server ID for instant slash command updates during dev !!!
# Remove or set to None for global command registration (takes up to an hour).
TEST_GUILD_ID = 123456789098765432 

# User-Agent for web requests (Selenium also sets its own)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
# Full path to ChromeDriver. Set to None if chromedriver is in system PATH.
WEBDRIVER_PATH = None 

# --- Bot Behavior Configuration ---
# For /getdxp, determines how many players are scraped concurrently
MAX_CONCURRENT_PLAYERS = 4
# Seconds to wait for dynamic content on RunePixels after main table appears
PAGE_LOAD_DELAY = 7 
# Name of a player (their Discord display name as fetched by the bot)
# to use as a cutoff for "Skill Best" eligibility.
# Only players appearing *before* this player in the fetched list (order can vary)
# will be considered. Set to None or "" to include all registered players.
# Note: The order of players fetched can be arbitrary due to concurrency.
# A more robust cutoff might use registration order or RSNs from a defined list if strict order is needed.
# For now, it will filter based on the order players appear in the fetched results if a name is provided.
SKILL_BEST_CUTOFF_PLAYER_DISPLAY_NAME = "Parzival" # Example, set to None or "" for no cutoff

# Data files for persistence
PLAYERS_FILE = "players_data.json" # Stores {discord_user_id_str: {"rsn": "RSN", ...}}
ADMINS_FILE = "admins_data.json"   # Stores [admin_discord_user_id_str, ...]
# --- Configuration Ends ---

# --- Helper Functions: Data Management (JSON) ---
def load_json_data(file_path, default_type_factory=dict):
    """Loads JSON data from a file. Returns default if file not found or error."""
    if not os.path.exists(file_path):
        return default_type_factory()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content.strip(): # Check if content is empty or just whitespace
                return default_type_factory()
            return json.loads(content)
    except json.JSONDecodeError: # Handles empty or malformed JSON
        print(f"Warning: '{file_path}' is empty or contains invalid JSON. Returning default.")
        return default_type_factory()
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return default_type_factory()

def save_json_data(data, file_path):
    """Saves data to a JSON file."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving data to {file_path}: {e}")
        return False

# --- Helper: DXP Value Formatting ---
def _format_dxp_for_display(dxp_raw_val, for_embed_value=False):
    """Helper to format DXP values for display in Discord messages."""
    val_str = str(dxp_raw_val).strip()
    if val_str == NO_DATA_PLACEHOLDER: return f"`{NO_DATA_PLACEHOLDER}`"
    try:
        num_val = int(val_str.replace(' ','').replace(',',''))
        formatted_num = f"`{num_val:,}`"
        return f"**{formatted_num}**" if for_embed_value else formatted_num
    except ValueError: return f"`{val_str[:100]}`" # Truncate if very long non-numeric

# --- Core Logic: DXP Scraping ---
def get_player_dxp_data(rsn: str):
    """Fetches DXP data for an RSN from RunePixels. Manages its own WebDriver."""
    thread_name = threading.current_thread().name 
    player_url = f"https://runepixels.com/players/{urllib.parse.quote(rsn)}/skills"
    print(f"Thread-{thread_name}: Fetching DXP for RSN: {rsn} from {player_url}")

    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    options.add_argument("--log-level=3")

    driver = None
    try:
        if WEBDRIVER_PATH and os.path.isfile(WEBDRIVER_PATH):
            service = ChromeService(executable_path=WEBDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=options)
        else:
            driver = webdriver.Chrome(options=options) # Assumes chromedriver is in PATH
        driver.get(player_url)
        WebDriverWait(driver, 45).until(EC.visibility_of_element_located((By.TAG_NAME, "app-table")))
        time.sleep(PAGE_LOAD_DELAY) # Crucial pause for dynamic content
        page_source = driver.page_source
    except TimeoutException:
        print(f"Thread-{thread_name}: Error - Timeout for RSN: {rsn}.")
        return None
    except WebDriverException as wd_e:
        print(f"Thread-{thread_name}: Error - WebDriverException for RSN: {rsn} - {wd_e}")
        return None
    except Exception as e:
        print(f"Thread-{thread_name}: Error - Unexpected Selenium error for RSN: {rsn} - {e}")
        return None
    finally:
        if driver: driver.quit()

    soup = BeautifulSoup(page_source, 'html.parser')
    app_table = soup.find('app-table')
    if not app_table: 
        print(f"Thread-{thread_name}: Error - No <app-table> found for {rsn}.")
        return None
    skills_table = app_table.find('table')
    if not skills_table: 
        print(f"Thread-{thread_name}: Error - No <table> within <app-table> for {rsn}.")
        return None

    dxp_data = {}
    try:
        tbody = skills_table.find('tbody')
        rows = tbody.find_all('tr') if tbody else skills_table.find_all('tr', recursive=False)
        if not rows and skills_table: rows = skills_table.find_all('tr')
        if not rows: return {}
        data_rows = [r for r in rows if r.find('td')]
        if not data_rows: return {}
        for r in data_rows:
            cols = r.find_all('td')
            if len(cols) > 6: # Skill name in col[0], DXP in col[6]
                skill_name = cols[0].text.strip()
                if skill_name: dxp_data[skill_name] = cols[6].text.strip()
    except Exception as e:
        print(f"Thread-{thread_name}: Error - Parsing table for RSN {rsn}: {e}")
        return None
    return dxp_data

# --- Core Logic: Skill Best Calculation ---
def calculate_skill_best_assignments(all_player_dxp_for_calc: dict, 
                                     all_skill_names_in_data: list):
    """
    Calculates "Skill Best" (v13 logic): 
    1. #1s claim. 
    2. Iterative passes where players fill empty slots or upgrade existing ones.
    Excludes "Overall". Returns {skill_lower: player_discord_name}.
    Player names in all_player_dxp_for_calc are discord_names.
    """
    print("Calculating Skill Best assignments...")
    if not all_player_dxp_for_calc: return {}

    full_skill_player_rankings = defaultdict(list)
    for p_name, p_data in all_player_dxp_for_calc.items():
        if not p_data: continue
        for s_raw, dxp_raw in p_data.items():
            s_l, dxp_s = s_raw.strip().lower(), str(dxp_raw).strip()
            if s_l == "overall" or dxp_s == NO_DATA_PLACEHOLDER: continue
            try:
                d_val = int(dxp_s.replace(" ","").replace(",",""))
                full_skill_player_rankings[s_l].append({'player': p_name, 'dxp': d_val})
            except ValueError: continue
    for s_l in full_skill_player_rankings:
        full_skill_player_rankings[s_l].sort(key=lambda x: x['dxp'], reverse=True)

    raw_skill_best_info = {s_l: r[0] for s_l, r in full_skill_player_rankings.items() if r}
    if not raw_skill_best_info:
        print("Info: No numeric DXP (excl. 'Overall') for raw Skill Bests."); return {}

    player_raw_wins = defaultdict(list)
    for s_l, info in raw_skill_best_info.items():
        if info.get('player'): player_raw_wins[info['player']].append((info['dxp'], s_l))

    final_assignments, player_slots = {}, defaultdict(int)
    for p_name in sorted(list(player_raw_wins.keys())):
        wins = sorted(player_raw_wins[p_name], key=lambda x: x[0], reverse=True)
        for dxp_v, s_l in wins:
            if player_slots[p_name] < MAX_SKILLS_FOR_BEST_PLAYER and s_l not in final_assignments:
                final_assignments[s_l], player_slots[p_name] = p_name, player_slots[p_name]+1
            else: break 
    
    # Iterative Player-Preferred Roll-Down AND Upgrade Pass
    max_passes = len(all_player_dxp_for_calc.keys()) + 5
    for pass_num in range(max_passes):
        made_change = False
        sorted_eligible_player_names = sorted(list(all_player_dxp_for_calc.keys()))

        for p_name_turn in sorted_eligible_player_names:
            best_new_skill_opt = None
            for skill_opt_l in all_skill_names_in_data: # Use all unique skills found in data
                if skill_opt_l == "overall" or skill_opt_l in final_assignments.get(skill_opt_l, "") == p_name_turn : continue
                
                # Is skill_opt_l truly unassigned by *another* player?
                if skill_opt_l in final_assignments and final_assignments[skill_opt_l] != p_name_turn:
                    continue

                if skill_opt_l in full_skill_player_rankings:
                    p_dxp_this_opt, top_avail = 0, False
                    for entry in full_skill_player_rankings[skill_opt_l]:
                        cand_p = entry['player']
                        # Is cand_p available for this skill (has slots OR is current player for upgrade eval)?
                        if player_slots[cand_p] < MAX_SKILLS_FOR_BEST_PLAYER or cand_p == p_name_turn:
                            if cand_p == p_name_turn: # This is our player
                                p_dxp_this_opt = entry['dxp']
                                top_avail = True; break 
                            else: # Another available player is ranked higher for this skill
                                top_avail = False; break 
                    if top_avail:
                        if not best_new_skill_opt or p_dxp_this_opt > best_new_skill_opt['dxp']:
                            best_new_skill_opt = {'skill': skill_opt_l, 'dxp': p_dxp_this_opt}
            
            if best_new_skill_opt:
                new_s, new_dxp = best_new_skill_opt['skill'], best_new_skill_opt['dxp']
                if player_slots[p_name_turn] < MAX_SKILLS_FOR_BEST_PLAYER:
                    if new_s not in final_assignments: # If still unassigned by others in same pass
                        final_assignments[new_s], player_slots[p_name_turn], made_change = p_name_turn, player_slots[p_name_turn]+1, True
                else: # Player is full, check upgrade
                    current_skills = [{'skill':s, 'dxp':next((e['dxp'] for e in full_skill_player_rankings.get(s,[]) if e['player']==p_name_turn),0)} 
                                       for s,p in final_assignments.items() if p==p_name_turn]
                    if current_skills:
                        worst = min(current_skills, key=lambda x:x['dxp'])
                        if new_dxp > worst['dxp'] and (new_s not in final_assignments or final_assignments.get(new_s) == p_name_turn):
                             if worst['skill'] in final_assignments and final_assignments[worst['skill']] == p_name_turn: # Ensure it's still theirs
                                del final_assignments[worst['skill']]
                             final_assignments[new_s], made_change = p_name_turn, True
        if not made_change: break
    return final_assignments

# --- Bot Setup ---
intents = nextcord.Intents.default()
intents.members = True # For resolving Member objects by ID
bot = commands.Bot(owner_id=OWNER_ID, intents=intents) # No command_prefix for slash-only

# --- Permission Checks ---
async def is_owner_check(interaction: nextcord.Interaction) -> bool:
    return interaction.user.id == bot.owner_id

async def is_admin_or_owner_check(interaction: nextcord.Interaction) -> bool:
    if interaction.user.id == bot.owner_id: return True
    admins = load_json_data_corrected(ADMINS_FILE, default_type_factory=list)
    return interaction.user.id in admins

# --- Bot Events ---
@bot.event
async def on_ready():
    print(f'{bot.user.name} ({bot.user.id}) has connected and is ready.')
    print(f"Owner ID: {bot.owner_id}")
    # Initialize data files if they don't exist
    if not os.path.exists(PLAYERS_FILE): save_json_data({}, PLAYERS_FILE)
    if not os.path.exists(ADMINS_FILE): save_json_data([], ADMINS_FILE)
    guild_text = f"guild {TEST_GUILD_ID}" if TEST_GUILD_ID else "globally"
    print(f"Slash commands will attempt to register for {guild_text}.")

# --- Slash Commands ---
@bot.slash_command(name="addadmin", description="OWNER: Adds a bot admin.", guild_ids=[TEST_GUILD_ID] if TEST_GUILD_ID else None)
async def add_admin_slash(interaction: nextcord.Interaction, user: nextcord.Member = nextcord.SlashOption(description="The user to make an admin.")):
    if not await is_owner_check(interaction):
        await interaction.response.send_message("⛔ Only the bot owner can use this command.", ephemeral=True); return
    admins = load_json_data_corrected(ADMINS_FILE, default_type_factory=list)
    if user.id not in admins:
        admins.append(user.id); save_json_data(admins, ADMINS_FILE)
        await interaction.response.send_message(f"✅ {user.mention} is now an admin.", ephemeral=True)
    else: await interaction.response.send_message(f"⚠️ {user.mention} is already an admin.", ephemeral=True)

@bot.slash_command(name="removeadmin", description="OWNER: Removes a bot admin.", guild_ids=[TEST_GUILD_ID] if TEST_GUILD_ID else None)
async def remove_admin_slash(interaction: nextcord.Interaction, user: nextcord.Member = nextcord.SlashOption(description="The admin to remove.")):
    if not await is_owner_check(interaction):
        await interaction.response.send_message("⛔ Only the bot owner can use this command.", ephemeral=True); return
    admins = load_json_data_corrected(ADMINS_FILE, default_type_factory=list)
    if user.id in admins:
        try: admins.remove(user.id); save_json_data(admins, ADMINS_FILE)
        except ValueError: pass 
        await interaction.response.send_message(f"✅ {user.mention} is no longer an admin.", ephemeral=True)
    else: await interaction.response.send_message(f"⚠️ {user.mention} is not an admin.", ephemeral=True)

@bot.slash_command(name="addplayer", description="ADMIN: Adds/updates a player's RSN for DXP tracking.", guild_ids=[TEST_GUILD_ID] if TEST_GUILD_ID else None)
async def add_player_slash(interaction: nextcord.Interaction, 
                           user: nextcord.Member = nextcord.SlashOption(description="The Discord user."), 
                           rsn: str = nextcord.SlashOption(description="The RuneScape Name (RSN).")):
    if not await is_admin_or_owner_check(interaction):
        await interaction.response.send_message("⛔ You don't have permission for this command.", ephemeral=True); return
    players = load_json_data_corrected(PLAYERS_FILE, default_type_factory=dict)
    players[str(user.id)] = {"rsn": rsn.strip(), "added_by": str(interaction.user.id), "date_added": datetime.datetime.utcnow().isoformat()}
    save_json_data(players, PLAYERS_FILE)
    await interaction.response.send_message(f"✅ Player **{rsn.strip()}** set for {user.mention}.", ephemeral=True)

@bot.slash_command(name="removeplayer", description="ADMIN: Removes a player from DXP tracking.", guild_ids=[TEST_GUILD_ID] if TEST_GUILD_ID else None)
async def remove_player_slash(interaction: nextcord.Interaction, 
                              user: nextcord.Member = nextcord.SlashOption(description="The Discord user whose RSN to remove.")):
    if not await is_admin_or_owner_check(interaction):
        await interaction.response.send_message("⛔ You don't have permission for this command.", ephemeral=True); return
    players = load_json_data_corrected(PLAYERS_FILE, default_type_factory=dict)
    uid_str = str(user.id)
    if uid_str in players:
        removed_entry = players.pop(uid_str); save_json_data(players, PLAYERS_FILE)
        rsn_val = removed_entry.get("rsn", "Unknown RSN")
        await interaction.response.send_message(f"✅ Player **{rsn_val}** for {user.mention} removed from tracking.", ephemeral=True)
    else: await interaction.response.send_message(f"⚠️ {user.mention} not found in tracking list.", ephemeral=True)

async def fetch_dxp_for_command(bot_instance: commands.Bot, target_discord_id_str: str = None):
    """Helper to fetch DXP data for target(s) using ThreadPoolExecutor."""
    results = {}
    player_data_store = load_json_data_corrected(PLAYERS_FILE, default_type_factory=dict)
    if not player_data_store: return {"error": "No players are registered yet."} if target_discord_id_str else {}

    tasks_to_run = []
    if target_discord_id_str:
        player_entry = player_data_store.get(target_discord_id_str)
        if player_entry and isinstance(player_entry, dict) and player_entry.get("rsn"):
            tasks_to_run.append({'discord_id': target_discord_id_str, 'rsn': player_entry["rsn"]})
        else:
            target_member_for_error_msg = f"User ID {target_discord_id_str}"
            try: user_obj = await bot_instance.fetch_user(int(target_discord_id_str)); target_member_for_error_msg = user_obj.mention
            except: pass
            return {"error": f"{target_member_for_error_msg} is not registered or has no RSN set."}
    else: # Fetch for all
        for did, p_info in player_data_store.items():
            if isinstance(p_info, dict) and p_info.get("rsn"):
                 tasks_to_run.append({'discord_id': did, 'rsn': p_info["rsn"]})
    
    if not tasks_to_run: return {} if not target_discord_id_str else {"error": "No valid RSN found for the specified user."}

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PLAYERS) as executor:
        future_to_task = {loop.run_in_executor(executor, get_player_dxp_data, t['rsn']): t for t in tasks_to_run}
        for future in concurrent.futures.as_completed(future_to_task):
            task = future_to_task[future]; did_s, rsn_s = task['discord_id'], task['rsn']
            d_name = did_s 
            try: user_o = await bot_instance.fetch_user(int(did_s)); d_name = user_o.display_name if user_o else did_s
            except: pass
            try:
                dxp_res = await future
                results[did_s] = {'rsn': rsn_s, 'discord_name': d_name, 'dxp_data': dxp_res}
            except Exception as e:
                print(f"Error processing future for RSN {rsn_s}: {e}")
                results[did_s] = {'rsn': rsn_s, 'discord_name': d_name, 'dxp_data': None}
    return results

@bot.slash_command(name="getdxp", description="ADMIN: Retrieves DXP stats for players.", guild_ids=[TEST_GUILD_ID] if TEST_GUILD_ID else None)
async def get_dxp_slash(interaction: nextcord.Interaction,
    target_user: nextcord.Member = nextcord.SlashOption(name="user", description="Optional: User for specific DXP. Blank for all.", required=False, default=None)
):
    if not await is_admin_or_owner_check(interaction):
        await interaction.response.send_message("⛔ You don't have permission.", ephemeral=True); return
    
    await interaction.response.defer(ephemeral=False) # Defer response immediately

    target_id_str = str(target_user.id) if target_user else None
    initial_message = f"Fetching DXP for {target_user.display_name if target_user else 'all registered players'}..."
    await interaction.followup.send(f"⏳ {initial_message} This may take a moment.")

    fetched_player_dxp_results = await fetch_dxp_for_command(bot, target_id_str)

    if not fetched_player_dxp_results or "error" in fetched_player_dxp_results:
        error_msg = fetched_player_dxp_results.get("error", "No data fetched or no players registered.")
        await interaction.edit_original_message(content=f"⚠️ {error_msg}"); return # Edit initial message

    utc_now_for_embeds = datetime.datetime.now(datetime.timezone.utc)

    if target_user: # Single player display
        player_result = fetched_player_dxp_results.get(str(target_user.id))
        if not player_result or player_result.get('dxp_data') is None:
            await interaction.edit_original_message(content=f"⚠️ Could not display DXP for {target_user.display_name}. Data missing or fetch error."); return
        
        title = f"Event DXP: {player_result['discord_name']} (RSN: {player_result['rsn']})"
        desc, total_dxp = "", 0
        dxp_entries = player_result['dxp_data'] if player_result['dxp_data'] else {}
        for skill, dxp_s in sorted(dxp_entries.items()):
            if skill.lower() == "overall": continue
            desc += f"**{skill.capitalize()}**: {_format_dxp_for_display(dxp_s, True)}\n"
            if dxp_s != NO_DATA_PLACEHOLDER:
                try: total_dxp += int(dxp_s.replace(" ","").replace(",",""))
                except: pass
        desc += f"\n**Total Event DXP (Calculated):** `{total_dxp:,}`"
        if not dxp_entries or not any(s.lower() != "overall" for s in dxp_entries): desc = "No specific skill DXP data found."
        
        embed = nextcord.Embed(title=title, description=desc[:4090]+"..." if len(desc)>4096 else desc, color=nextcord.Color.green(), timestamp=utc_now_for_embeds)
        await interaction.edit_original_message(content=None, embed=embed) # Edit initial message with embed
    
    else: # All players display
        # Embed 1: Overall DXP Leaderboard
        leaderboard = []
        for uid, data in fetched_player_dxp_results.items():
            if data.get('dxp_data'):
                total = sum(int(d.replace(" ","").replace(",","")) for s,d in data['dxp_data'].items() if s.lower()!="overall" and d!=NO_DATA_PLACEHOLDER and d.replace(" ","").replace(",","").isdigit())
                leaderboard.append({'name': data['discord_name'], 'total': total, 'rsn': data['rsn']})
        leaderboard.sort(key=lambda x:x['total'], reverse=True)
        desc1 = "\n".join(f"{i+1}. **{e['name']}** ({e['rsn']}): `{e['total']:,}` DXP" for i,e in enumerate(leaderboard))
        if not desc1: desc1 = "No DXP data for leaderboard."
        embed1 = nextcord.Embed(title="🏆 Overall DXP Leaderboard (Calculated)", description=desc1[:4090]+"..." if len(desc1)>4096 else desc1, color=nextcord.Color.gold(), timestamp=utc_now_for_embeds)
        await interaction.edit_original_message(content=None, embed=embed1) # Edit initial message with first embed

        # Embed 2: Skill Best Assignments
        data_for_skill_best_calc = {data['discord_name']: data['dxp_data'] for discord_id, data in fetched_player_dxp_results.items() if data.get('dxp_data')}
        
        # --- Apply SKILL_BEST_CUTOFF_PLAYER_DISPLAY_NAME ---
        eligible_for_sb_discord = {}
        if SKILL_BEST_CUTOFF_PLAYER_DISPLAY_NAME and SKILL_BEST_CUTOFF_PLAYER_DISPLAY_NAME.strip():
            cutoff_name_lower = SKILL_BEST_CUTOFF_PLAYER_DISPLAY_NAME.strip().lower()
            # We need a way to get players in their configured order to apply cutoff
            # For now, this cutoff might be tricky if player_data_store isn't ordered or if discord_name isn't unique
            # A simple approach: exclude players at or after the cutoff name if found.
            # This assumes unique discord_names from fetched_player_dxp_results for simplicity of example.
            # A more robust solution would map PLAYER_SHEET_COLUMN_NAMES (if they are Discord names) to RSNs/Discord IDs.
            
            # Simpler filter: iterate through players in the order they are in PLAYER_SHEET_COLUMN_NAMES
            # and stop if cutoff is reached. This requires PLAYER_SHEET_COLUMN_NAMES to be discord_names
            # or a mapping. For this example, the current cutoff is based on player *display names*.
            
            temp_player_list_for_cutoff = [] # List of (discord_name, data_dict)
            # Attempt to get a somewhat consistent order for cutoff, though dict iteration isn't guaranteed
            for p_name_key_in_calc in sorted(data_for_skill_best_calc.keys()): # p_name_key_in_calc is discord_name
                if p_name_key_in_calc.lower() == cutoff_name_lower:
                    break # Stop adding players once cutoff is reached
                temp_player_list_for_cutoff.append((p_name_key_in_calc, data_for_skill_best_calc[p_name_key_in_calc]))
            
            if len(temp_player_list_for_cutoff) < len(data_for_skill_best_calc) and \
               any(p_name.lower() == cutoff_name_lower for p_name in data_for_skill_best_calc.keys()):
                eligible_for_sb_discord = dict(temp_player_list_for_cutoff)
                print(f"Info: For Discord Skill Best, considering {len(eligible_for_sb_discord)} players appearing before '{SKILL_BEST_CUTOFF_PLAYER_DISPLAY_NAME}'.")
            else: # Cutoff name not found or no one before it
                print(f"Warning: Cutoff player '{SKILL_BEST_CUTOFF_PLAYER_DISPLAY_NAME}' not effective or not found. Considering all for Discord Skill Best.")
                eligible_for_sb_discord = data_for_skill_best_calc
        else:
            print("Info: No cutoff player for Discord Skill Best. Considering all.")
            eligible_for_sb_discord = data_for_skill_best_calc

        all_skill_names = set(s.lower().strip() for p_data in eligible_for_sb_discord.values() if p_data for s in p_data.keys())
        
        if eligible_for_sb_discord and all_skill_names:
            skill_best_assignments = calculate_skill_best_assignments(eligible_for_sb_discord, list(all_skill_names - {"overall"}))
            desc2 = ""
            for skill_l in sorted(list(skill_best_assignments.keys())):
                bp_name = skill_best_assignments.get(skill_l)
                if bp_name:
                    # Find this player's DXP for this skill from eligible_for_sb_discord
                    bp_dxp_val = NO_DATA_PLACEHOLDER
                    if bp_name in eligible_for_sb_discord and eligible_for_sb_discord[bp_name]:
                        # Need to match skill_l (lowercase) with original case key from DXP data
                        original_skill_key = next((k for k in eligible_for_sb_discord[bp_name].keys() if k.lower().strip() == skill_l), None)
                        if original_skill_key:
                            bp_dxp_val = eligible_for_sb_discord[bp_name].get(original_skill_key, NO_DATA_PLACEHOLDER)
                    
                    formatted_dxp_val = _format_dxp_for_display(bp_dxp_val, True)
                    desc2 += f"**{skill_l.capitalize()}**: {bp_name} ({formatted_dxp_val})\n"
                else: desc2 += f"**{skill_l.capitalize()}**: N/A\n"
            if not desc2: desc2 = "No Skill Best data to display."
            if len(desc2) > 4096: desc2 = desc2[:4090] + "\n..."
            embed2 = nextcord.Embed(title="✨ Skill Best Assignments (Event DXP)", description=desc2, color=nextcord.Color.purple(), timestamp=utc_now_for_embeds)
            await interaction.followup.send(embed=embed2) # Send as another followup
        else:
            await interaction.followup.send("Could not calculate Skill Best assignments (no eligible players or skills).")

# --- Run the Bot ---
if __name__ == "__main__":
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("CRITICAL ERROR: BOT_TOKEN is not set in the script.")
    elif OWNER_ID == 123456789012345678: # Default placeholder
        print("CRITICAL ERROR: OWNER_ID is not set. Please set it to your Discord User ID.")
    elif TEST_GUILD_ID == ... or str(TEST_GUILD_ID).lower().startswith("your"): # Placeholder check
        print("WARNING: TEST_GUILD_ID is not set to your actual server ID. Slash commands may take time to register globally or fail if not set for testing.")
        bot.run(BOT_TOKEN)
    else:
        bot.run(BOT_TOKEN)