"""
Ticket system bot - main.py
Python 3.10+

Features (mapped to your spec):
- /panel -> public embed with dropdown (Desk / IA / HR)
- Dropdown creates ticket channels under configured category IDs
- Ticket embed in the ticket channel with buttons (Claim / Unclaim / Close)
- Claim state persisted in channel.topic (so it survives restarts)
- /add and /remove moderators-only commands (with logs and pings on add/remove)
- /ping command (ephemeral)
- Logs posted to LOG_CHANNEL_ID (no pings except for explicit add/remove or ticket creation)
- Transcript attached as purged_messages_{channel_id}.txt to logs on close
- All embed titles prepend the logo emoji "<:emoji_1:1401614346316021813> "
- Color used: #313D61
- Sanitizes channel names (lowercase, replace spaces with '-', remove disallowed chars)
"""

import os
import re
import json
import asyncio
import os
GUILD_ID = int(os.getenv("GUILD_ID"))  # The server ID where you want commands to update immediately
from io import StringIO
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

# -----------------------------
# Environment variables you'll set in Render (names below must match)
# -----------------------------
# BOT_TOKEN           - bot token string
# MOD_ROLE_ID         - role ID (int) used to restrict moderator commands (also used for permissions)
# DESK_CATEGORY_ID    - category ID (int) for Desk Support tickets
# IA_CATEGORY_ID      - category ID (int) for IA tickets
# HR_CATEGORY_ID      - category ID (int) for HR tickets
# LOG_CHANNEL_ID      - channel ID (int) where logs and transcripts are posted
# NOTIFY_ROLE_ID      - role ID (int) to ping when a ticket is created (this is the single-role ping you requested)
# GUILD_ID            - optional: the guild ID (int) to register commands to a single guild (recommended)
# -----------------------------

# Load env
BOT_TOKEN = os.getenv("BOT_TOKEN")
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID", "0"))
DESK_CATEGORY_ID = int(os.getenv("DESK_CATEGORY_ID", "0"))
IA_CATEGORY_ID = int(os.getenv("IA_CATEGORY_ID", "0"))
HR_CATEGORY_ID = int(os.getenv("HR_CATEGORY_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))
NOTIFY_ROLE_ID = int(os.getenv("NOTIFY_ROLE_ID", "0"))
GUILD_ID = os.getenv("GUILD_ID")
GUILD_ID = int(GUILD_ID) if GUILD_ID else None

# Basic runtime checks
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable not set.")
if MOD_ROLE_ID == 0 or DESK_CATEGORY_ID == 0 or IA_CATEGORY_ID == 0 or HR_CATEGORY_ID == 0 or LOG_CHANNEL_ID == 0:
    raise RuntimeError("One or more required IDs (MOD_ROLE_ID, DESK_CATEGORY_ID, IA_CATEGORY_ID, HR_CATEGORY_ID, LOG_CHANNEL_ID) are not set or zero.")

# ---------- Bot setup ----------
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)
# If you prefer, you can use bot = discord.Client + app_commands tree, but this is simpler.

# Constants used in embeds/UI
LOGO_EMOJI = "<:emoji_1:1401614346316021813>"
ICON_3 = "<:icon3:1420478187917283410>"
ICON_9 = "<:icon9:1420479660222841063>"
ICON_5 = "<:icon5:1420478145307476038>"
ICON_4 = "<:icon4:1420478165754712148>"
ICON_6 = "<:icon6:1420478130157785271>"
EMBED_COLOR = discord.Color(int("313D61", 16))  # hex #313D61

# --- Helpers for ticket metadata stored in channel.topic ---
# We'll store a JSON blob inside the channel.topic prefixed with "ticket_meta:" so it's easily parseable.
def _read_topic_meta(topic: str | None) -> dict:
    if not topic:
        return {}
    try:
        marker = "ticket_meta:"
        idx = topic.find(marker)
        if idx == -1:
            return {}
        json_part = topic[idx + len(marker):].strip()
        return json.loads(json_part)
    except Exception:
        return {}

def _write_topic_meta(meta: dict) -> str:
    # Keep a short human-friendly prefix and then the json blob
    # Be mindful of the 1024 char topic limit.
    return f"ticket_meta:{json.dumps(meta, separators=(',', ':'))}"

def sanitize_channel_name(name: str) -> str:
    # Lowercase, replace spaces with '-', remove characters except alphanum, '-', '_'
    name = name.lower().replace(" ", "-")
    name = re.sub(r"[^a-z0-9\-_]", "", name)
    # collapse multiple dashes
    name = re.sub(r"-{2,}", "-", name)
    return name[:90]  # keep some margin for full channel name

def make_ticket_id() -> str:
    # Timestamp-based ID. No DB required.
    return datetime.utcnow().strftime("%Y%m%d%H%M%S")

async def get_log_channel(bot: commands.Bot) -> discord.TextChannel:
    return bot.get_channel(LOG_CHANNEL_ID) or await bot.fetch_channel(LOG_CHANNEL_ID)

# -------------- Logging helper (centralized) --------------
async def log_action(action: str, user: discord.abc.Snowflake | discord.User, channel: discord.abc.Snowflake | discord.TextChannel, details: str = ""):
    """
    Posts a consistent embed to the log channel. IMPORTANT: unless the action is an add/remove or ticket creation,
    we will NOT ping users (we'll use display_name to avoid pings).
    """
    log_channel = await get_log_channel(bot)
    if not log_channel:
        print("Log channel not found; skipping log.")
        return

    # Use no pings by default in description (display_name instead of mention)
    who = getattr(user, "display_name", str(user))
    channel_display = channel.mention if hasattr(channel, "mention") else f"<#{getattr(channel, 'id', str(channel))}>"

    embed = discord.Embed(title=f"{LOGO_EMOJI} {action}", color=EMBED_COLOR, timestamp=datetime.utcnow())
    embed.description = f"User: {who}\nChannel: {channel_display}"
    if details:
        embed.add_field(name="Details", value=details[:1024], inline=False)
    embed.set_footer(text="Ticket System")
    await log_channel.send(embed=embed)

# ---------- UI: persistent view class ----------
# We will register this view at startup (bot.add_view) so interactions are handled after restarts.
class TicketButtonsView(discord.ui.View):
    def __init__(self, *, timeout=None):
        super().__init__(timeout=timeout)

from discord import ui, Embed, ButtonStyle, Interaction
from datetime import datetime

class TicketButtons(ui.View):
   
    
    # --- Claim Button ---
    @ui.button(label="Claim", style=ButtonStyle.green, custom_id="ticket_claim_button")
    async def claim_button(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        meta = _read_topic_meta(channel.topic)

        # Check if already claimed
        if meta.get("claimed_by"):
            await interaction.followup.send("This ticket is already claimed.", ephemeral=True)
            return

        # Only moderators can claim
        if not any(r.id == MOD_ROLE_ID for r in interaction.user.roles):
            await interaction.followup.send("You do not have permission to claim tickets.", ephemeral=True)
            return

        # Update meta
        meta["claimed_by"] = interaction.user.id
        meta["claimed_by_name"] = interaction.user.display_name
        await channel.edit(topic=_write_topic_meta(meta))

        # Update the ticket embed
        try:
            msg_id = meta.get("ticket_message_id")
            if msg_id:
                msg = await channel.fetch_message(int(msg_id))
                if msg.embeds:
                    old_embed = msg.embeds[0]
                    opener_line = (old_embed.description.splitlines()[0] if old_embed.description else "")
                    claimed_val = f"<@{interaction.user.id}>"

                    new_embed = Embed(
                        title=old_embed.title,
                        description=f"{opener_line}\nClaimed by: {claimed_val}",
                        color=EMBED_COLOR,
                        timestamp=old_embed.timestamp
                    )

                    people_added = meta.get("added", [])
                    new_embed.add_field(name="Claimed by", value=claimed_val, inline=False)
                    new_embed.add_field(name="People added", value=", ".join(f"<@{u}>" for u in people_added) if people_added else "None", inline=False)
                    new_embed.add_field(name="Open date", value=meta.get("opened_at", "Unknown"), inline=True)
                    new_embed.add_field(name="Ticket ID", value=meta.get("ticket_id", "Unknown"), inline=True)

                    await msg.edit(embed=new_embed, view=TicketButtonsViewClaimed())
        except Exception as e:
            print("Error updating ticket embed on claim:", e)

        # Confirmation and logging
        confirm_embed = Embed(
            title=f"{LOGO_EMOJI} Ticket Claimed",
            description=f"{interaction.user.mention} has claimed this ticket.",
            color=EMBED_COLOR,
            timestamp=datetime.utcnow()
        )
        await channel.send(embed=confirm_embed)
        await log_action("Ticket Claimed", interaction.user, channel, details=f"Type: {meta.get('type')}")
        await interaction.followup.send("Ticket claimed successfully.", ephemeral=True)

    # --- Unclaim Button ---
    @ui.button(label="Unclaim", style=ButtonStyle.grey, custom_id="ticket_unclaim_button")
    async def unclaim_button(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        meta = _read_topic_meta(channel.topic)

        claimed_by = meta.get("claimed_by")
        if not claimed_by:
            await interaction.followup.send("Ticket is not claimed.", ephemeral=True)
            return
        if int(claimed_by) != interaction.user.id:
            await interaction.followup.send("You cannot unclaim this ticket (not the claimer).", ephemeral=True)
            return

        # Update meta
        meta["claimed_by"] = None
        meta["claimed_by_name"] = None
        await channel.edit(topic=_write_topic_meta(meta))

        # Update embed back to unclaimed state
        try:
            msg_id = meta.get("ticket_message_id")
            if msg_id:
                msg = await channel.fetch_message(int(msg_id))
                if msg.embeds:
                    old_embed = msg.embeds[0]
                    opener_line = (old_embed.description.splitlines()[0] if old_embed.description else "")

                    new_embed = Embed(
                        title=old_embed.title,
                        description=f"{opener_line}\nClaimed by: None",
                        color=EMBED_COLOR,
                        timestamp=old_embed.timestamp
                    )

                    people_added = meta.get("added", [])
                    new_embed.add_field(name="Claimed by", value="None", inline=False)
                    new_embed.add_field(name="People added", value=", ".join(f"<@{u}>" for u in people_added) if people_added else "None", inline=False)
                    new_embed.add_field(name="Open date", value=meta.get("opened_at", "Unknown"), inline=True)
                    new_embed.add_field(name="Ticket ID", value=meta.get("ticket_id", "Unknown"), inline=True)

                    await msg.edit(embed=new_embed, view=TicketButtonsView())
        except Exception as e:
            print("Error updating ticket embed on unclaim:", e)

        await log_action("Ticket Unclaimed", interaction.user, channel, details=f"Type: {meta.get('type')}")
        await interaction.followup.send("Ticket unclaimed.", ephemeral=True)

    # --- Close Button ---
    @ui.button(label="Close", style=ButtonStyle.red, custom_id="ticket_close_button")
    async def close_button(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer()  # visible to all
        channel = interaction.channel
        meta = _read_topic_meta(channel.topic)

        # Only moderators
        if not any(r.id == MOD_ROLE_ID for r in interaction.user.roles):
            try:
                await interaction.followup.send("You do not have permission to close tickets.", ephemeral=True)
            except:
                pass
            return

        # Collect message history and compile transcript
        transcript_buf = StringIO()
        async for msg in channel.history(limit=None, oldest_first=True):
            ts = msg.created_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            author = f"{msg.author} ({getattr(msg.author, 'id', 'unknown')})"
            content = msg.content or ""
            # Indicate attachments
            if msg.attachments:
                content += " [Attachments: " + ", ".join(a.url for a in msg.attachments) + "]"
            transcript_buf.write(f"{ts} | {author}: {content}\n")

        transcript_buf.seek(0)
        file_name = f"purged_messages_{channel.id}.txt"
        discord_file = discord.File(transcript_buf, filename=file_name)

        # Send to logs channel with embed
        log_channel = await get_log_channel(bot)
        details = f"Type: {meta.get('type')}\nClosed by: {interaction.user.display_name}"
        embed = discord.Embed(title=f"{LOGO_EMOJI} Ticket Closed", color=EMBED_COLOR, timestamp=datetime.utcnow())
        embed.description = f"User: {interaction.user.display_name}\nChannel: {channel.mention}"
        embed.add_field(name="Details", value=details, inline=False)
        await log_channel.send(embed=embed, file=discord_file)

        # Log action with helper (no ping)
        await log_action("Ticket Closed", interaction.user, channel, details=f"Transcript attached: {file_name}")

        # Delete the ticket channel
        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user}")
        except Exception as e:
            print("Failed deleting channel:", e)
            # If deletion fails, notify in-channel
            try:
                await interaction.followup.send("Ticket closed, but failed to delete channel.", ephemeral=True)
            except:
                pass

# Additional view classes to swap buttons when claimed/unclaimed.
class TicketButtonsViewClaimed(TicketButtonsView):
    # When claimed, we want Unclaim + Close visible. We'll hide Claim by leaving it disabled.
    def __init__(self, *, timeout=None):
        super().__init__(timeout=timeout)
        # The base class defines all three buttons; we'll hide the Claim button.
        for item in list(self.children):
            if isinstance(item, discord.ui.Button) and item.custom_id == "ticket_claim_button":
                item.disabled = True

# ---------- Slash commands ----------
@bot.event
async def on_ready():
    # Add persistent view so interactions work after restart
    bot.add_view(TicketButtonsView(timeout=None))
    bot.add_view(TicketButtonsViewClaimed(timeout=None))

    # Set presence
    try:
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Created by RE3"))
    except Exception as e:
        print("Failed to set presence:", e)

    # Optionally, sync commands to a specific guild for immediate availability
    try:
        if GUILD_ID:
            await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        else:
            await bot.tree.sync()
    except Exception as e:
        print("Error syncing commands:", e)

    print(f"Bot ready. Logged in as {bot.user} ({bot.user.id})")

# ---- /ping ----
@bot.tree.command(name="ping", description="Check bot latency (ephemeral)")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! {latency}ms", ephemeral=True)

# ---- /panel ----
class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Desk Support", description="For general issues/questions"),
            discord.SelectOption(label="IA", description="For IA-related issues"),
            discord.SelectOption(label="HR", description="For HR-related issues"),
        ]
        super().__init__(placeholder="Select ticket type...", min_values=1, max_values=1, options=options, custom_id="ticket_dropdown")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ticket_type = self.values[0]
        user = interaction.user
        # Map to category IDs
        type_map = {
            "Desk Support": DESK_CATEGORY_ID,
            "IA": IA_CATEGORY_ID,
            "HR": HR_CATEGORY_ID
        }
        category_id = type_map.get(ticket_type)
        if not category_id:
            await interaction.followup.send("Invalid ticket type selected.", ephemeral=True)
            return
        guild = interaction.guild
        category = guild.get_channel(category_id) or await guild.fetch_channel(category_id)

        # Create channel name sanitized
        raw_channel_name = f"{ticket_type}-{user.name}"
        chan_name = sanitize_channel_name(raw_channel_name)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            discord.Object(id=MOD_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }

        ticket_channel = await guild.create_text_channel(name=chan_name, category=category, overwrites=overwrites, reason=f"Ticket created by {user}")

        # Prepare ticket metadata
        ticket_id = make_ticket_id()
        opened_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        meta = {
            "ticket_id": ticket_id,
            "type": ticket_type,
            "opened_by": user.id,
            "opened_by_name": user.display_name,
            "opened_at": opened_at,
            "claimed_by": None,
            "claimed_by_name": None,
            "added": [],
            # ticket_message_id will be added after message is posted
        }

        # Build initial embed in ticket channel (exact text per spec)
        embed = discord.Embed(title=f"{LOGO_EMOJI} {ticket_type} Ticket", description=f"Ticket opened by {user.mention}\nClaimed by: None", color=EMBED_COLOR, timestamp=datetime.utcnow())
        embed.add_field(name="Claimed by", value="None", inline=False)
        embed.add_field(name="People added", value="None", inline=False)
        embed.add_field(name="Open date", value=opened_at, inline=True)
        embed.add_field(name="Ticket ID", value=ticket_id, inline=True)

        # Send embed with Claim + Close (the view has Claim + Close enabled)
        view = TicketButtonsView()
        ticket_msg = await ticket_channel.send(embed=embed, view=view)

        # Store message ID in meta and write to channel topic (persist)
        meta["ticket_message_id"] = ticket_msg.id
        await ticket_channel.edit(topic=_write_topic_meta(meta))

        # Ephemeral reply to the opener with clickable channel mention (exact string format)
        # Also, per your rule, ping NOTIFY_ROLE_ID on creation (this is the only role ping for creation)
        notify_role_mention = f"<@&{NOTIFY_ROLE_ID}>" if NOTIFY_ROLE_ID else ""
        reply_text = f"{user.mention}, your ticket has been created: {ticket_channel.mention}"
        await interaction.followup.send(reply_text, ephemeral=True)

        # Post a "Ticket Created" log to logs channel and, per spec, ping the notify role in that log message only
        log_channel = await get_log_channel(bot)
        details = f"Type: {ticket_type}\nOpened by: {user.display_name}\nTicket ID: {ticket_id}"
        log_embed = discord.Embed(title=f"{LOGO_EMOJI} Ticket Created", description=f"User: {user.display_name}\nChannel: {ticket_channel.mention}", color=EMBED_COLOR, timestamp=datetime.utcnow())
        log_embed.add_field(name="Details", value=details, inline=False)
        # send with role ping allowed
        if NOTIFY_ROLE_ID:
            await log_channel.send(content=f"<@&{NOTIFY_ROLE_ID}>", embed=log_embed)
        else:
            await log_channel.send(embed=log_embed)

        # Central helper log (no ping)
        await log_action("Ticket Created", user, ticket_channel, details=f"Type: {ticket_type}")

# Panel command creation
@bot.tree.command(name="panel", description="Post the ticket panel (mods only)")
async def panel(interaction: discord.Interaction):
    # Check moderator role
    if not any(r.id == MOD_ROLE_ID for r in interaction.user.roles):
        await interaction.response.send_message("You do not have permission to run this command.", ephemeral=True)
        return

    # Build the panel embed exact multi-line string per your spec
    panel_description = f"""{ICON_3} Guidelines
{ICON_9} Tickets are designed for serious support matters only. Always select the correct category and clearly explain your issue so staff can assist quickly. Misuse of the ticket system, such as trolling or opening tickets without reason, may lead to warnings, ticket closures, or disciplinary action.

{ICON_5} Desk Support
{ICON_9} Inquiries, questions. Typically faster responses and age verification.

{ICON_4} Internal Affairs
{ICON_9} Handling Officer reports, cases. This requires department lawyers.

{ICON_6} HR+ Support
{ICON_9} Speaking to Director/SHR+, told by HR to open and etc.
"""
    embed = discord.Embed(title=f"{LOGO_EMOJI} Open a Ticket", description=panel_description, color=EMBED_COLOR, timestamp=datetime.utcnow())
    view = discord.ui.View()
    view.add_item(TicketDropdown())

    # The panel message is visible to everyone. The fact a moderator ran it is not shown.
    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

# ---- /add and /remove commands (mod-only) ----
@bot.tree.command(name="add", description="Add a user to the current ticket channel (mods only)")
@app_commands.describe(member="Member to add to ticket")
async def add(interaction: discord.Interaction, member: discord.Member):
    # Command only usable in a ticket channel (we'll check topic metadata)
    if not any(r.id == MOD_ROLE_ID for r in interaction.user.roles):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    channel = interaction.channel
    meta = _read_topic_meta(channel.topic)
    if not meta:
        await interaction.response.send_message("This command must be used inside a ticket channel.", ephemeral=True)
        return

    # set permissions
    await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
    # update meta added list
    added = meta.get("added", [])
    if member.id not in added:
        added.append(member.id)
    meta["added"] = added
    await channel.edit(topic=_write_topic_meta(meta))

    # Update ticket embed to show People added field
    try:
        msg_id = meta.get("ticket_message_id")
        if msg_id:
            msg = await channel.fetch_message(int(msg_id))
            if msg.embeds:
                embed = msg.embeds[0]
                opener_line = (embed.description.splitlines()[0] if embed.description else "")
                claimed_val = meta.get("claimed_by_name") or "None"
                new_embed = discord.Embed(title=embed.title, color=EMBED_COLOR, timestamp=embed.timestamp)
                new_embed.description = f"{opener_line}\nClaimed by: {('None' if not meta.get('claimed_by') else f'<@{meta.get('claimed_by')}>' )}"
                new_embed.add_field(name="Claimed by", value=(f"<@{meta.get('claimed_by')}>" if meta.get('claimed_by') else "None"), inline=False)
                people_added = meta.get("added", [])
                new_embed.add_field(name="People added", value=", ".join(f"<@{i}>" for i in people_added) if people_added else "None", inline=False)
                new_embed.add_field(name="Open date", value=meta.get("opened_at", "Unknown"), inline=True)
                new_embed.add_field(name="Ticket ID", value=meta.get("ticket_id", "Unknown"), inline=True)
                await msg.edit(embed=new_embed)
    except Exception as e:
        print("Error updating ticket embed on add:", e)

    # Reply ephemeral to moderator and ping the added member in-channel per your rule
    await interaction.response.send_message(f"{member.mention} has been added to the ticket.", ephemeral=True)
    # post a visible embed in ticket channel confirming add (everyone in ticket sees it)
    confirm_embed = discord.Embed(title=f"{LOGO_EMOJI} User Added to Ticket", description=f"{member.mention} added to ticket by {interaction.user.mention}", color=EMBED_COLOR, timestamp=datetime.utcnow())
    await channel.send(embed=confirm_embed)

    # Log (in logs, this one may mention the member as you allowed pings for add/remove)
    await log_action("User Added to Ticket", interaction.user, channel, details=f"Added {member.mention}")

@bot.tree.command(name="remove", description="Remove a user from the current ticket channel (mods only)")
@app_commands.describe(member="Member to remove from ticket")
async def remove(interaction: discord.Interaction, member: discord.Member):
    if not any(r.id == MOD_ROLE_ID for r in interaction.user.roles):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    channel = interaction.channel
    meta = _read_topic_meta(channel.topic)
    if not meta:
        await interaction.response.send_message("This command must be used inside a ticket channel.", ephemeral=True)
        return

    # remove custom overwrite
    await channel.set_permissions(member, overwrite=None)
    # update meta added list
    added = meta.get("added", [])
    if member.id in added:
        added.remove(member.id)
    meta["added"] = added
    await channel.edit(topic=_write_topic_meta(meta))

    # Update embed
    try:
        msg_id = meta.get("ticket_message_id")
        if msg_id:
            msg = await channel.fetch_message(int(msg_id))
            if msg.embeds:
                embed = msg.embeds[0]
                opener_line = (embed.description.splitlines()[0] if embed.description else "")
                new_embed = discord.Embed(title=embed.title, color=EMBED_COLOR, timestamp=embed.timestamp)
                new_embed.description = f"{opener_line}\nClaimed by: {('None' if not meta.get('claimed_by') else f'<@{meta.get('claimed_by')}>' )}"
                new_embed.add_field(name="Claimed by", value=(f"<@{meta.get('claimed_by')}>" if meta.get('claimed_by') else "None"), inline=False)
                people_added = meta.get("added", [])
                new_embed.add_field(name="People added", value=", ".join(f"<@{i}>" for i in people_added) if people_added else "None", inline=False)
                new_embed.add_field(name="Open date", value=meta.get("opened_at", "Unknown"), inline=True)
                new_embed.add_field(name="Ticket ID", value=meta.get("ticket_id", "Unknown"), inline=True)
                await msg.edit(embed=new_embed)
    except Exception as e:
        print("Error updating ticket embed on remove:", e)

    await interaction.response.send_message(f"{member.mention} has been removed from the ticket.", ephemeral=True)
    confirm_embed = discord.Embed(title=f"{LOGO_EMOJI} User Removed from Ticket", description=f"{member.mention} removed from ticket by {interaction.user.mention}", color=EMBED_COLOR, timestamp=datetime.utcnow())
    await channel.send(embed=confirm_embed)
    await log_action("User Removed from Ticket", interaction.user, channel, details=f"Removed {member.mention}")

# ================================
# MODERATION COMMANDS
# Place this AFTER your /setup command in main.py
# ================================

from discord import app_commands
import io
import datetime

# Utility to log mod actions
async def log_action(interaction: discord.Interaction, action: str):
    log_channel = interaction.guild.get_channel(int(LOG_CHANNEL_ID))
    if log_channel:
        embed = discord.Embed(
            title="🔧 Moderation Action",
            description=action,
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"By {interaction.user.display_name}")
        await log_channel.send(embed=embed)

from datetime import datetime, timezone, timedelta

# ======================
# MOD-ONLY SLASH COMMANDS (ROLE-LOCKED)
# ======================

import datetime

# --- Helper function to log mod actions ---
async def log_mod_action(interaction: discord.Interaction, title: str, description: str):
    log_channel = interaction.guild.get_channel(int(LOG_CHANNEL_ID))
    if log_channel:
        embed = discord.Embed(
            title=f"🔧 {title}",
            description=description,
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"By {interaction.user.display_name}")
        await log_channel.send(embed=embed)

# --- /kick ---
@bot.tree.command(name="kick", description="Kick a member (Mod only)")
@app_commands.checks.has_role(int(MOD_ROLE_ID))
@app_commands.describe(member="The member to kick", reason="Reason for the kick")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str):
    await member.kick(reason=reason)
    description = f"{member.mention} was kicked.\nReason: {reason}"
    embed = discord.Embed(title="👢 Member Kicked", description=description, color=discord.Color.red(), timestamp=datetime.datetime.utcnow())
    await interaction.response.send_message(embed=embed)
    await log_mod_action(interaction, "Kick", description)

# --- /ban ---
@bot.tree.command(name="ban", description="Ban a member (Mod only)")
@app_commands.checks.has_role(int(MOD_ROLE_ID))
@app_commands.describe(member="The member to ban", reason="Reason for the ban")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str):
    await member.ban(reason=reason)
    description = f"{member.mention} was banned.\nReason: {reason}"
    embed = discord.Embed(title="🔨 Member Banned", description=description, color=discord.Color.red(), timestamp=datetime.datetime.utcnow())
    await interaction.response.send_message(embed=embed)
    await log_mod_action(interaction, "Ban", description)

# --- /timeout ---
@bot.tree.command(name="timeout", description="Timeout a member (Mod only)")
@app_commands.checks.has_role(int(MOD_ROLE_ID))
@app_commands.describe(member="The member to timeout", duration="Duration in minutes", reason="Reason for the timeout")
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: int, reason: str):
    until = datetime.datetime.utcnow() + datetime.timedelta(minutes=duration)
    await member.timeout(until=until, reason=reason)
    description = f"{member.mention} timed out for {duration} minutes.\nReason: {reason}"
    embed = discord.Embed(title="⏳ Member Timed Out", description=description, color=discord.Color.orange(), timestamp=datetime.datetime.utcnow())
    await interaction.response.send_message(embed=embed)
    await log_mod_action(interaction, "Timeout", description)

# --- /lock ---
@bot.tree.command(name="lock", description="Lock the current channel (Mod only)")
@app_commands.checks.has_role(int(MOD_ROLE_ID))
async def lock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    description = f"{interaction.channel.mention} has been locked."
    embed = discord.Embed(title="🔒 Channel Locked", description=description, color=discord.Color.dark_gray(), timestamp=datetime.datetime.utcnow())
    await interaction.response.send_message(embed=embed)
    await log_mod_action(interaction, "Lock", description)

# --- /unlock ---
@bot.tree.command(name="unlock", description="Unlock the current channel (Mod only)")
@app_commands.checks.has_role(int(MOD_ROLE_ID))
async def unlock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = True
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    description = f"{interaction.channel.mention} has been unlocked."
    embed = discord.Embed(title="🔓 Channel Unlocked", description=description, color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
    await interaction.response.send_message(embed=embed)
    await log_mod_action(interaction, "Unlock", description)

# --- /purge ---
@bot.tree.command(name="purge", description="Delete messages in bulk.")
@app_commands.checks.has_role(int(MOD_ROLE_ID))
async def purge(interaction: discord.Interaction, amount: int, reason: str):
    import io
    import datetime

    if amount < 1 or amount > 100:
        await interaction.response.send_message("Amount must be between 1 and 100.", ephemeral=True)
        return

    # Defer the response (acknowledge)
    await interaction.response.defer(ephemeral=True)

    # Fetch messages asynchronously using modern async list comprehension
    messages = [msg async for msg in interaction.channel.history(limit=amount, oldest_first=False)]

    # Create transcript text with proper UTC time format
    transcript_text = "\n".join([
        f"{m.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')} | {m.author} ({m.author.id}): {m.content}"
        for m in reversed(messages)  # chronological order
    ])

    # Prepare .txt file
    transcript_file = discord.File(io.BytesIO(transcript_text.encode()), filename=f"purge_log_{interaction.channel.id}.txt")

    # Delete messages
    await interaction.channel.delete_messages(messages)

    # Send ephemeral confirmation
    await interaction.followup.send(f"Purged {amount} messages. Reason: {reason}", ephemeral=True)

    # Log to the log channel
    log_channel = interaction.guild.get_channel(int(LOG_CHANNEL_ID))
    if log_channel:
        embed = discord.Embed(
            title="🔧 Moderation Action: Purge",
            description=f"Channel: {interaction.channel.mention}\nModerator: {interaction.user.mention}\nReason: {reason}",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Ticket System / Mod Action")
        await log_channel.send(embed=embed, file=transcript_file)

# --- /say ---
@bot.tree.command(name="say", description="Make the bot say something as an embed.")
@app_commands.checks.has_role(int(MOD_ROLE_ID))
async def say(interaction: discord.Interaction, text: str):
    embed = discord.Embed(description=text, color=discord.Color.blue())
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("Message sent.", ephemeral=True)
    await log_action(interaction, f"**Say command used by {interaction.user}**\nContent: {text}")

# --- Flask keep-alive for UptimeRobot ---
from flask import Flask
import threading

app = Flask("")

@app.route("/")
def home():
    return "Bot is alive!"

# Start Flask server in a background thread
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# --- ON_READY EVENT (combined) ---


    # Add persistent views
    bot.add_view(TicketButtonsView(timeout=None))
    bot.add_view(TicketButtonsViewClaimed(timeout=None))

    # Set bot presence
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Created by RE3"))

    # Sync commands to guild
    try:
        if GUILD_ID:
            await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        else:
            await bot.tree.sync()
        print("✅ Slash commands synced to guild!")
    except Exception as e:
        print("❌ Failed to sync slash commands:", e)

    print(f"Bot ready as {bot.user} ({bot.user.id})")

# Run bot
if __name__ == "__main__":
    bot.run(BOT_TOKEN)
