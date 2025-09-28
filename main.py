import os
import sqlite3
import io
from datetime import datetime, timedelta
import asyncio
from threading import Thread

import discord
from discord.ext import commands
from discord import app_commands, Interaction, ButtonStyle
from discord.ui import View, Button, Modal, TextInput, Select

from flask import Flask

# -------------------------
# Configuration / env vars
# -------------------------
# Required env vars (set these in Render)
REQUIRED_ENVS = [
    "DISCORD_TOKEN",
    "GUILD_ID",
    "DESK_CATEGORY",
    "IA_CATEGORY",
    "HR_CATEGORY",
    "LOG_CHANNEL_ID",
    "MOD_ROLE_ID",
    "SAY_ROLE_ID"
]

missing = [e for e in REQUIRED_ENVS if os.getenv(e) is None]
if missing:
    print("ERROR: Missing required environment variables:", missing)
    print("Define them in Render env before starting the bot.")
    raise SystemExit(1)

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
DESK_CATEGORY_ID = int(os.getenv("DESK_CATEGORY"))
IA_CATEGORY_ID = int(os.getenv("IA_CATEGORY"))
HR_CATEGORY_ID = int(os.getenv("HR_CATEGORY"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))

# Optional
EMOJI_PREFIX = os.getenv("EMOJI_PREFIX", "")  # put :emoji_1: or emoji text here
TICKET_PANEL_CHANNEL = os.getenv("TICKET_PANEL_CHANNEL")  # optional channel ID to auto-post panel

# Embed color
EMBED_COLOR = 0x313D61

# -------------------------
# Flask uptime server
# -------------------------
app = Flask("")

@app.route("/")
def home():
    return "Bot is alive!"

def run_flask():
    # Use port Render gives; default 8080
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

# Start Flask in a thread so discord bot can run in main thread
Thread(target=run_flask, daemon=True).start()

# -------------------------
# Database (SQLite)
# -------------------------
DB_PATH = "tickets.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    opener_id INTEGER,
    category TEXT,
    issue TEXT,
    created_at TEXT,
    claimed_by INTEGER
)
""")
conn.commit()

def db_insert_ticket(channel_id, opener_id, category, issue):
    cur.execute("INSERT OR REPLACE INTO tickets (channel_id, opener_id, category, issue, created_at, claimed_by) VALUES (?, ?, ?, ?, ?, ?)",
                (channel_id, opener_id, category, issue, datetime.utcnow().isoformat(), None))
    conn.commit()

def db_remove_ticket(channel_id):
    cur.execute("DELETE FROM tickets WHERE channel_id = ?", (channel_id,))
    conn.commit()

def db_claim_ticket(channel_id, claimer_id):
    cur.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (claimer_id, channel_id))
    conn.commit()

def db_get_ticket(channel_id):
    cur.execute("SELECT channel_id, opener_id, category, issue, created_at, claimed_by FROM tickets WHERE channel_id = ?", (channel_id,))
    return cur.fetchone()

# -------------------------
# Discord bot setup
# -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

GUILD_OBJ = discord.Object(id=GUILD_ID)

# Helper checks
def is_mod(member: discord.Member) -> bool:
    return any(r.id == MOD_ROLE_ID for r in member.roles) or member.guild_permissions.administrator

def has_say_role(member: discord.Member) -> bool:
    return any(r.id == SAY_ROLE_ID for r in member.roles) or member.guild_permissions.manage_messages

async def log_to_channel(guild: discord.Guild, content: str = None, embed: discord.Embed = None, file: discord.File = None):
    ch = guild.get_channel(LOG_CHANNEL_ID)
    if not ch:
        print("Log channel not found:", LOG_CHANNEL_ID)
        return
    try:
        await ch.send(content=content, embed=embed, file=file)
    except Exception as e:
        print("Failed to send log:", e)

# -------------------------
# Ticket reason modal (required)
# -------------------------
class TicketReasonModal(Modal):
    def __init__(self, category_key: str, category_id: int):
        super().__init__(title=f"{EMOJI_PREFIX} Open Ticket")
        self.category_key = category_key
        self.category_id = category_id
        self.issue = TextInput(label="Issue / Reason (required)", style=discord.TextStyle.paragraph, required=True, max_length=2000)
        self.add_item(self.issue)

    async def on_submit(self, interaction: Interaction):
        guild = interaction.guild
        category_name = {"desk": "Desk Support", "ia": "Internal Affairs", "hr": "HR+ Support"}[self.category_key]
        # Ensure category exists (use provided category_id first)
        category = guild.get_channel(self.category_id)
        if category is None or not isinstance(category, discord.CategoryChannel):
            # Create category with that name if missing
            category = await guild.create_category(category_name)

        # create ticket channel
        safe_name = f"{self.category_key}-ticket-{interaction.user.name}".lower()
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        # give mod role view send perms
        mod_role = guild.get_role(MOD_ROLE_ID)
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)

        ticket_channel = await guild.create_text_channel(safe_name, category=category, overwrites=overwrites)
        # store in db
        db_insert_ticket(ticket_channel.id, interaction.user.id, category_name, self.issue.value)

        # send ticket welcome embed and buttons
        embed = discord.Embed(
            title=f"{EMOJI_PREFIX} Ticket Created",
            description=f"Hello {interaction.user.mention}. A staff member will be with you shortly.",
            color=EMBED_COLOR
        )
        embed.add_field(name="Category", value=category_name, inline=False)
        embed.add_field(name="User", value=interaction.user.mention, inline=False)
        embed.add_field(name="Issue", value=self.issue.value or "No issue provided", inline=False)
        embed.set_footer(text=f"Opened at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        view = TicketButtonsView()
        await ticket_channel.send(embed=embed, view=view)

        # log
        await log_to_channel(guild, embed=discord.Embed(
            title="📥 Ticket Opened",
            color=EMBED_COLOR
        ).add_field(name="User", value=interaction.user.mention, inline=True).add_field(name="Channel", value=ticket_channel.mention, inline=True).add_field(name="Category", value=category_name, inline=True))

        await interaction.response.send_message(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)

# -------------------------
# Ticket panel (buttons for categories)
# -------------------------
class PanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        # Buttons added via decorator methods below

    @discord.ui.button(label="Desk Support", style=ButtonStyle.primary, custom_id="panel_desk")
    async def desk_button(self, interaction: Interaction, button: Button):
        modal = TicketReasonModal("desk", DESK_CATEGORY_ID)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Internal Affairs", style=ButtonStyle.secondary, custom_id="panel_ia")
    async def ia_button(self, interaction: Interaction, button: Button):
        modal = TicketReasonModal("ia", IA_CATEGORY_ID)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="HR+ Support", style=ButtonStyle.primary, custom_id="panel_hr")
    async def hr_button(self, interaction: Interaction, button: Button):
        modal = TicketReasonModal("hr", HR_CATEGORY_ID)
        await interaction.response.send_modal(modal)

# -------------------------
# Ticket buttons inside ticket channels (Claim, Add, Remove, Close)
# Order and colors: Claim=green, Add=blue, Remove=blue, Close=red
# -------------------------
class TicketButtonsView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=ButtonStyle.success, custom_id="ticket_claim")
    async def claim_button(self, interaction: Interaction, button: Button):
        # Only mods should claim (or staff)
        member = interaction.user
        if not is_mod(member):
            await interaction.response.send_message("You need the mod role to claim tickets.", ephemeral=True)
            return
        db_claim_ticket(interaction.channel.id, member.id)
        embed = discord.Embed(title=f"{EMOJI_PREFIX} Ticket Claimed", description=f"{member.mention} has claimed this ticket.", color=EMBED_COLOR)
        await interaction.response.send_message(embed=embed)
        await log_to_channel(interaction.guild, embed=discord.Embed(title="🟢 Ticket Claimed", description=f"{member.mention} claimed {interaction.channel.mention}", color=EMBED_COLOR))

    @discord.ui.button(label="Add User", style=ButtonStyle.primary, custom_id="ticket_add")
    async def add_button(self, interaction: Interaction, button: Button):
        # only mods allowed to add, or the ticket opener
        ticket = db_get_ticket(interaction.channel.id)
        opener_id = ticket[1] if ticket else None
        if not (is_mod(interaction.user) or interaction.user.id == opener_id):
            await interaction.response.send_message("Only the ticket owner or staff can add users.", ephemeral=True)
            return
        modal = AddRemoveModal(action="add")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove User", style=ButtonStyle.primary, custom_id="ticket_remove")
    async def remove_button(self, interaction: Interaction, button: Button):
        ticket = db_get_ticket(interaction.channel.id)
        opener_id = ticket[1] if ticket else None
        if not (is_mod(interaction.user) or interaction.user.id == opener_id):
            await interaction.response.send_message("Only the ticket owner or staff can remove users.", ephemeral=True)
            return
        modal = AddRemoveModal(action="remove")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Close", style=ButtonStyle.danger, custom_id="ticket_close")
    async def close_button(self, interaction: Interaction, button: Button):
        ticket = db_get_ticket(interaction.channel.id)
        opener_id = ticket[1] if ticket else None
        # allow ticket opener or mod to close
        if not (is_mod(interaction.user) or interaction.user.id == opener_id):
            await interaction.response.send_message("Only staff or the ticket opener can close this ticket.", ephemeral=True)
            return
        await close_ticket(interaction.channel, closer=interaction.user)
        await interaction.response.send_message("Ticket closed.", ephemeral=True)

# Modal for Add/Remove user (asks for mention)
class AddRemoveModal(Modal):
    def __init__(self, action: str):
        title = "Add User" if action == "add" else "Remove User"
        super().__init__(title=title)
        self.action = action
        self.user_field = TextInput(label="Mention the user (@username)", style=discord.TextStyle.short, required=True)
        self.add_item(self.user_field)

    async def on_submit(self, interaction: Interaction):
        mention = self.user_field.value.strip()
        # Extract ID from mention
        user_id = None
        if mention.startswith("<@") and mention.endswith(">"):
            mention = mention.strip("<@!>")
            try:
                user_id = int(mention)
            except:
                user_id = None
        else:
            # try parse as plain ID
            try:
                user_id = int(mention)
            except:
                user_id = None

        if user_id is None:
            await interaction.response.send_message("Invalid mention or ID.", ephemeral=True)
            return

        guild = interaction.guild
        member = guild.get_member(user_id)
        if member is None:
            await interaction.response.send_message("User not found in this server.", ephemeral=True)
            return

        channel = interaction.channel
        if self.action == "add":
            await channel.set_permissions(member, view_channel=True, send_messages=True)
            embed = discord.Embed(title=f"{EMOJI_PREFIX} User Added", description=f"{member.mention} has been added to this ticket.", color=EMBED_COLOR)
            await channel.send(embed=embed)
            await log_to_channel(guild, content=f"➕ {member.mention} added to {channel.mention} by {interaction.user.mention}")
            await interaction.response.send_message(f"{member.mention} added to ticket.", ephemeral=True)
        else:
            await channel.set_permissions(member, overwrite=None)
            embed = discord.Embed(title=f"{EMOJI_PREFIX} User Removed", description=f"{member.mention} has been removed from this ticket.", color=EMBED_COLOR)
            await channel.send(embed=embed)
            await log_to_channel(guild, content=f"➖ {member.mention} removed from {channel.mention} by {interaction.user.mention}")
            await interaction.response.send_message(f"{member.mention} removed from ticket.", ephemeral=True)

# -------------------------
# Close ticket helper (create transcript + log + delete channel)
# -------------------------
async def close_ticket(channel: discord.TextChannel, closer: discord.Member):
    guild = channel.guild
    # collect transcript
    messages = []
    async for m in channel.history(limit=None, oldest_first=True):
        ts = m.created_at.strftime("%Y-%m-%d %H:%M")
        author = f"{m.author} ({m.author.id})"
        content = m.content or ""
        # handle attachments simply
        if m.attachments:
            content += " [attachment]"
        messages.append(f"[{ts}] {author}: {content}")

    transcript = "\n".join(messages)[:2000000]  # cap
    transcript_bytes = io.BytesIO(transcript.encode("utf-8"))
    file = discord.File(fp=transcript_bytes, filename=f"{channel.name}-transcript.txt")

    # log
    log_embed = discord.Embed(title=f"{EMOJI_PREFIX} Ticket Closed", description=f"Closed by: {closer.mention}", color=EMBED_COLOR)
    log_embed.add_field(name="Channel", value=channel.name, inline=True)
    ticket_row = db_get_ticket(channel.id)
    if ticket_row:
        log_embed.add_field(name="Issue", value=(ticket_row[3] or "n/a"), inline=True)
    await log_to_channel(guild, embed=log_embed, file=file)

    # remove from DB and delete channel
    db_remove_ticket(channel.id)
    try:
        await channel.delete()
    except Exception as e:
        print("Failed to delete ticket channel:", e)

# -------------------------
# Slash commands (registered to guild for speed)
# -------------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    # auto-post panel if TICKET_PANEL_CHANNEL defined
    if TICKET_PANEL_CHANNEL:
        try:
            ch_id = int(TICKET_PANEL_CHANNEL)
            ch = bot.get_channel(ch_id)
            if ch:
                embed = discord.Embed(title=f"{EMOJI_PREFIX} Guidelines", description="Tickets are for serious support matters only. Select a category below and provide your reason.", color=EMBED_COLOR)
                view = PanelView()
                await ch.send(embed=embed, view=view)
                print("Posted ticket panel to", ch.id)
        except Exception as e:
            print("Auto-post panel failed:", e)

@tree.command(name="panel", description="Post the ticket panel", guild=GUILD_OBJ)
async def cmd_panel(interaction: Interaction):
    embed = discord.Embed(title=f"{EMOJI_PREFIX} Guidelines", description="Tickets are for serious support matters only. Select a category below and provide your reason.", color=EMBED_COLOR)
    view = PanelView()
    await interaction.response.send_message(embed=embed, view=view)
    await log_to_channel(interaction.guild, content=f"📋 Ticket panel posted by {interaction.user.mention}")

# Purge (moderator only)
@tree.command(name="purge", description="Delete a number of messages (moderator only)", guild=GUILD_OBJ)
@app_commands.describe(amount="How many messages to delete")
async def cmd_purge(interaction: Interaction, amount: int):
    if not is_mod(interaction.user):
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)
    await log_to_channel(interaction.guild, content=f"🧹 {interaction.user.mention} purged {len(deleted)} messages in {interaction.channel.mention}")

# Kick / Ban / Timeout (moderator only)
@tree.command(name="kick", description="Kick a member (mod only)", guild=GUILD_OBJ)
async def cmd_kick(interaction: Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not is_mod(interaction.user):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"✅ {member.mention} kicked. Reason: {reason}")
        await log_to_channel(interaction.guild, content=f"👢 {member.mention} was kicked by {interaction.user.mention}. Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message("Failed to kick: " + str(e), ephemeral=True)

@tree.command(name="ban", description="Ban a member (mod only)", guild=GUILD_OBJ)
async def cmd_ban(interaction: Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not is_mod(interaction.user):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"✅ {member.mention} banned. Reason: {reason}")
        await log_to_channel(interaction.guild, content=f"🔨 {member.mention} was banned by {interaction.user.mention}. Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message("Failed to ban: " + str(e), ephemeral=True)

@tree.command(name="timeout", description="Timeout a member in minutes (mod only)", guild=GUILD_OBJ)
async def cmd_timeout(interaction: Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
    if not is_mod(interaction.user):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    try:
        until = datetime.utcnow() + timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        await interaction.response.send_message(f"✅ {member.mention} timed out for {minutes} minutes. Reason: {reason}")
        await log_to_channel(interaction.guild, content=f"⏰ {member.mention} timed out by {interaction.user.mention} for {minutes} minutes. Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message("Failed to timeout: " + str(e), ephemeral=True)

# Mute / Unmute using a Muted role (mod only)
async def get_or_create_muted_role(guild: discord.Guild):
    role = discord.utils.get(guild.roles, name="Muted")
    if role:
        return role
    try:
        role = await guild.create_role(name="Muted", reason="Create muted role for ticket bot")
        # Deny send_messages in all text channels for this role
        for ch in guild.channels:
            try:
                await ch.set_permissions(role, send_messages=False, speak=False)
            except:
                pass
        return role
    except Exception as e:
        print("Failed to create Muted role:", e)
        return None

@tree.command(name="mute", description="Add Muted role to a member (mod only)", guild=GUILD_OBJ)
async def cmd_mute(interaction: Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not is_mod(interaction.user):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    role = await get_or_create_muted_role(interaction.guild)
    if role is None:
        await interaction.response.send_message("Failed to create or find Muted role.", ephemeral=True)
        return
    try:
        await member.add_roles(role, reason=reason)
        await interaction.response.send_message(f"✅ {member.mention} muted. Reason: {reason}")
        await log_to_channel(interaction.guild, content=f"🔇 {member.mention} muted by {interaction.user.mention}. Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message("Failed to mute: " + str(e), ephemeral=True)

@tree.command(name="unmute", description="Remove Muted role from a member (mod only)", guild=GUILD_OBJ)
async def cmd_unmute(interaction: Interaction, member: discord.Member):
    if not is_mod(interaction.user):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    role = discord.utils.get(interaction.guild.roles, name="Muted")
    if role:
        try:
            await member.remove_roles(role)
            await interaction.response.send_message(f"✅ {member.mention} unmuted.")
            await log_to_channel(interaction.guild, content=f"🔊 {member.mention} unmuted by {interaction.user.mention}.")
        except Exception as e:
            await interaction.response.send_message("Failed to unmute: " + str(e), ephemeral=True)
    else:
        await interaction.response.send_message("Muted role not found.", ephemeral=True)

# Lock / Unlock channel (mod only)
@tree.command(name="lock", description="Lock this channel (mod only)", guild=GUILD_OBJ)
async def cmd_lock(interaction: Interaction):
    if not is_mod(interaction.user):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False, view_channel=False)
    await interaction.response.send_message("🔒 Channel locked.")
    await log_to_channel(interaction.guild, content=f"🔒 {interaction.channel.mention} locked by {interaction.user.mention}")

@tree.command(name="unlock", description="Unlock this channel (mod only)", guild=GUILD_OBJ)
async def cmd_unlock(interaction: Interaction):
    if not is_mod(interaction.user):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=None)
    await interaction.response.send_message("🔓 Channel unlocked.")
    await log_to_channel(interaction.guild, content=f"🔓 {interaction.channel.mention} unlocked by {interaction.user.mention}")

# Adduser / Removeuser (mods or ticket owner)
@tree.command(name="adduser", description="Add a user to this ticket", guild=GUILD_OBJ)
async def cmd_adduser(interaction: Interaction, member: discord.Member):
    ticket = db_get_ticket(interaction.channel.id)
    opener = ticket[1] if ticket else None
    if not (is_mod(interaction.user) or interaction.user.id == opener):
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return
    await interaction.channel.set_permissions(member, view_channel=True, send_messages=True)
    await interaction.response.send_message(f"✅ {member.mention} added to this ticket.")
    await log_to_channel(interaction.guild, content=f"➕ {member.mention} added to {interaction.channel.mention} by {interaction.user.mention}")

@tree.command(name="removeuser", description="Remove a user from this ticket", guild=GUILD_OBJ)
async def cmd_removeuser(interaction: Interaction, member: discord.Member):
    ticket = db_get_ticket(interaction.channel.id)
    opener = ticket[1] if ticket else None
    if not (is_mod(interaction.user) or interaction.user.id == opener):
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return
    await interaction.channel.set_permissions(member, overwrite=None)
    await interaction.response.send_message(f"✅ {member.mention} removed from this ticket.")
    await log_to_channel(interaction.guild, content=f"➖ {member.mention} removed from {interaction.channel.mention} by {interaction.user.mention}")

# Close via command
@tree.command(name="close", description="Close this ticket", guild=GUILD_OBJ)
async def cmd_close(interaction: Interaction):
    ticket = db_get_ticket(interaction.channel.id)
    opener = ticket[1] if ticket else None
    if not (is_mod(interaction.user) or interaction.user.id == opener):
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return
    await interaction.response.defer()
    await close_ticket(interaction.channel, closer=interaction.user)
    await interaction.followup.send("✅ Ticket closed.", ephemeral=True)

# Say command (restricted)
@tree.command(name="say", description="Make the bot say something (restricted)", guild=GUILD_OBJ)
async def cmd_say(interaction: Interaction, message: str):
    if not has_say_role(interaction.user):
        await interaction.response.send_message("You are not authorized to use /say.", ephemeral=True)
        return
    await interaction.response.send_message("✅ Message sent.", ephemeral=True)
    await interaction.channel.send(message)
    await log_to_channel(interaction.guild, content=f'🗣️ /say by {interaction.user.mention}: "{message}"')

# Ping and help
@tree.command(name="ping", description="Bot latency", guild=GUILD_OBJ)
async def cmd_ping(interaction: Interaction):
    await interaction.response.send_message(f"🏓 Pong! {round(bot.latency*1000)}ms")

@tree.command(name="help", description="Show commands", guild=GUILD_OBJ)
async def cmd_help(interaction: Interaction):
    commands_list = [
        "/panel - Post ticket panel",
        "/purge <num> - Delete messages (mod)",
        "/kick <member> [reason] (mod)",
        "/ban <member> [reason] (mod)",
        "/timeout <member> <minutes> (mod)",
        "/mute <member> (mod)",
        "/unmute <member> (mod)",
        "/lock /unlock (mod)",
        "/adduser /removeuser - ticket helpers",
        "/close - close ticket",
        "/say - restricted by SAY_ROLE",
        "/ping - everyone"
    ]
    await interaction.response.send_message("**Commands:**\n" + "\n".join(commands_list), ephemeral=True)

# -------------------------
# Run bot
# -------------------------
if __name__ == "__main__":
    bot.loop.create_task(bot.start(TOKEN))
    try:
        bot.loop.run_forever()
    except KeyboardInterrupt:
        print("Shutting down")
