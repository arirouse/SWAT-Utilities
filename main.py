# main.py
# Paste this whole file exactly as-is into your repo's main.py

import os
import io
import sqlite3
from datetime import datetime, timedelta
from threading import Thread
import asyncio

import discord
from discord.ext import commands
from discord import app_commands, Interaction, ButtonStyle
from discord.ui import View, Button, Select, Modal, TextInput

from flask import Flask

# -----------------------
# CONFIG / ENV (required)
# -----------------------
# Required envs (set these in Render)
# DISCORD_TOKEN, GUILD_ID, DESK_CATEGORY_ID, IA_CATEGORY_ID, HR_CATEGORY_ID,
# LOG_CHANNEL_ID, MOD_ROLE_ID, SAY_ROLE_ID
REQUIRED = [
    "DISCORD_TOKEN",
    "GUILD_ID",
    "DESK_CATEGORY_ID",
    "IA_CATEGORY_ID",
    "HR_CATEGORY_ID",
    "LOG_CHANNEL_ID",
    "MOD_ROLE_ID",
    "SAY_ROLE_ID"
]

missing = [k for k in REQUIRED if os.getenv(k) is None]
if missing:
    print("ERROR: Missing environment variables:", missing)
    raise SystemExit(1)

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
DESK_CATEGORY_ID = int(os.getenv("DESK_CATEGORY_ID"))
IA_CATEGORY_ID = int(os.getenv("IA_CATEGORY_ID"))
HR_CATEGORY_ID = int(os.getenv("HR_CATEGORY_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))

# Optional
TICKET_PANEL_CHANNEL = os.getenv("TICKET_PANEL_CHANNEL")  # if set, bot will auto-post the panel there on startup
EMOJI_PREFIX = os.getenv("EMOJI_PREFIX", "")  # e.g. ":emoji_1:" (will prefix titles if provided)

# Visuals
EMBED_COLOR = 0x313D61

# -----------------------
# FLASK (uptime ping)
# -----------------------
app = Flask("")

@app.route("/")
def home():
    return "Bot is alive!"

def run_flask():
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_flask, daemon=True).start()

# -----------------------
# DATABASE (sqlite)
# -----------------------
DB = "tickets.db"
conn = sqlite3.connect(DB, check_same_thread=False)
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
    cur.execute(
        "INSERT OR REPLACE INTO tickets (channel_id, opener_id, category, issue, created_at, claimed_by) VALUES (?, ?, ?, ?, ?, ?)",
        (channel_id, opener_id, category, issue, datetime.utcnow().isoformat(), None)
    )
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

# -----------------------
# DISCORD BOT SETUP
# -----------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True       # required for member operations (mute/timeout)
# we do NOT require message_content for the core features; leave it false unless you need it.
intents.message_content = False

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
GUILD_OBJ = discord.Object(id=GUILD_ID)

# -----------------------
# HELPERS
# -----------------------
def is_mod_member(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(r.id == MOD_ROLE_ID for r in member.roles)

def has_say_role(member: discord.Member) -> bool:
    if member.guild_permissions.manage_messages:
        return True
    return any(r.id == SAY_ROLE_ID for r in member.roles)

async def log_to_channel(guild: discord.Guild, content: str = None, embed: discord.Embed = None, file: discord.File = None):
    ch = guild.get_channel(LOG_CHANNEL_ID)
    if not ch:
        print("Log channel not found:", LOG_CHANNEL_ID)
        return
    try:
        await ch.send(content=content, embed=embed, file=file)
    except Exception as e:
        print("Failed to send log:", e)

def parse_mention_to_id(text: str):
    # Accept <@!123>, <@123>, or raw numeric ID
    text = text.strip()
    if text.startswith("<@") and text.endswith(">"):
        inside = text.strip("<@!>")
        try:
            return int(inside)
        except:
            return None
    try:
        return int(text)
    except:
        return None

# -----------------------
# TICKET MODAL (required reason)
# -----------------------
class TicketReasonModal(Modal):
    def __init__(self, category_key: str, category_id: int):
        title = f"{EMOJI_PREFIX} Open Ticket" if EMOJI_PREFIX else "Open Ticket"
        super().__init__(title=title)
        self.category_key = category_key
        self.category_id = category_id
        self.issue = TextInput(label="Issue / Reason (required)", style=discord.TextStyle.paragraph, required=True, max_length=2000)
        self.add_item(self.issue)

    async def on_submit(self, interaction: Interaction):
        guild = interaction.guild
        # determine category name from key
        name_map = {"desk": "Desk Support", "ia": "Internal Affairs", "hr": "HR+ Support"}
        category_name = name_map.get(self.category_key, "Support")
        # try to get the category by provided ID, else by name, else create
        category = guild.get_channel(self.category_id)
        if category is None or not isinstance(category, discord.CategoryChannel):
            category = discord.utils.get(guild.categories, name=category_name)
            if category is None:
                category = await guild.create_category(category_name)

        # channel name
        safe_name = f"ticket-{self.category_key}-{interaction.user.name}".lower()
        # overwrites
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        mod_role = guild.get_role(MOD_ROLE_ID)
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)

        # create channel
        ticket_channel = await guild.create_text_channel(safe_name, category=category, overwrites=overwrites)

        # DB insert
        db_insert_ticket(ticket_channel.id, interaction.user.id, category_name, self.issue.value)

        # send ticket embed + buttons
        embed = discord.Embed(
            title=f"{EMOJI_PREFIX} Ticket Created" if EMOJI_PREFIX else "Ticket Created",
            description=f"Hello {interaction.user.mention}! A staff member will be with you shortly.",
            color=EMBED_COLOR
        )
        embed.add_field(name="Category", value=category_name, inline=False)
        embed.add_field(name="User", value=interaction.user.mention, inline=False)
        embed.add_field(name="Issue", value=self.issue.value or "No issue provided", inline=False)
        embed.set_footer(text=f"Opened at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

        view = TicketButtonsView()
        await ticket_channel.send(embed=embed, view=view)

        # log
        await log_to_channel(guild, content=f"📥 Ticket opened by {interaction.user.mention} in {ticket_channel.mention} (Category: {category_name})")

        await interaction.response.send_message(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)

# -----------------------
# PANEL (dropdown) - initial selection
# -----------------------
class TicketPanelSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Desk Support", value="desk", description="Inquiries, questions. Faster responses and age verification."),
            discord.SelectOption(label="Internal Affairs", value="ia", description="Officer reports, cases. Requires department lawyers."),
            discord.SelectOption(label="HR+ Support", value="hr", description="Speaking to Director/SHR+, told by HR to open.")
        ]
        super().__init__(placeholder="Select a ticket category...", min_values=1, max_values=1, options=options, custom_id="ticket_category_select")

    async def callback(self, interaction: Interaction):
        choice = self.values[0]  # "desk" / "ia" / "hr"
        id_map = {"desk": DESK_CATEGORY_ID, "ia": IA_CATEGORY_ID, "hr": HR_CATEGORY_ID}
        modal = TicketReasonModal(choice, id_map[choice])
        await interaction.response.send_modal(modal)

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketPanelSelect())

# -----------------------
# TICKET BUTTONS inside ticket channels
# Order & colors: Claim=green, Add=blue, Remove=blue, Close=red
# -----------------------
class AddRemoveModal(Modal):
    def __init__(self, action: str):
        title = "Add User" if action == "add" else "Remove User"
        super().__init__(title=title)
        self.action = action
        self.user_field = TextInput(label="Mention or ID of user", style=discord.TextStyle.short, required=True)
        self.add_item(self.user_field)

    async def on_submit(self, interaction: Interaction):
        mention = self.user_field.value.strip()
        user_id = parse_mention_to_id(mention)
        if user_id is None:
            await interaction.response.send_message("Invalid mention/ID.", ephemeral=True)
            return
        member = interaction.guild.get_member(user_id)
        if member is None:
            await interaction.response.send_message("User not found in server.", ephemeral=True)
            return
        channel = interaction.channel
        if self.action == "add":
            await channel.set_permissions(member, view_channel=True, send_messages=True)
            embed = discord.Embed(title=f"{EMOJI_PREFIX} User Added" if EMOJI_PREFIX else "User Added", description=f"{member.mention} has been added to this ticket.", color=EMBED_COLOR)
            await channel.send(embed=embed)
            await log_to_channel(interaction.guild, content=f"➕ {member.mention} added to {channel.mention} by {interaction.user.mention}")
            await interaction.response.send_message(f"{member.mention} added to ticket.", ephemeral=True)
        else:
            await channel.set_permissions(member, overwrite=None)
            embed = discord.Embed(title=f"{EMOJI_PREFIX} User Removed" if EMOJI_PREFIX else "User Removed", description=f"{member.mention} has been removed from this ticket.", color=EMBED_COLOR)
            await channel.send(embed=embed)
            await log_to_channel(interaction.guild, content=f"➖ {member.mention} removed from {channel.mention} by {interaction.user.mention}")
            await interaction.response.send_message(f"{member.mention} removed from ticket.", ephemeral=True)

class TicketButtonsView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=ButtonStyle.success, custom_id="ticket_claim")
    async def claim(self, interaction: Interaction, button: Button):
        if not is_mod_member(interaction.user):
            await interaction.response.send_message("You need the mod role to claim tickets.", ephemeral=True)
            return
        db_claim_ticket(interaction.channel.id, interaction.user.id)
        embed = discord.Embed(title=f"{EMOJI_PREFIX} Ticket Claimed" if EMOJI_PREFIX else "Ticket Claimed",
                              description=f"{interaction.user.mention} has claimed this ticket.", color=EMBED_COLOR)
        await interaction.response.send_message(embed=embed)
        await log_to_channel(interaction.guild, content=f"🟢 {interaction.user.mention} claimed {interaction.channel.mention}")

    @discord.ui.button(label="Add User", style=ButtonStyle.primary, custom_id="ticket_add")
    async def add_user(self, interaction: Interaction, button: Button):
        ticket = db_get_ticket(interaction.channel.id)
        opener_id = ticket[1] if ticket else None
        if not (is_mod_member(interaction.user) or interaction.user.id == opener_id):
            await interaction.response.send_message("Only the ticket owner or staff can add users.", ephemeral=True)
            return
        modal = AddRemoveModal(action="add")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove User", style=ButtonStyle.primary, custom_id="ticket_remove")
    async def remove_user(self, interaction: Interaction, button: Button):
        ticket = db_get_ticket(interaction.channel.id)
        opener_id = ticket[1] if ticket else None
        if not (is_mod_member(interaction.user) or interaction.user.id == opener_id):
            await interaction.response.send_message("Only the ticket owner or staff can remove users.", ephemeral=True)
            return
        modal = AddRemoveModal(action="remove")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Close", style=ButtonStyle.danger, custom_id="ticket_close")
    async def close_ticket_button(self, interaction: Interaction, button: Button):
        ticket = db_get_ticket(interaction.channel.id)
        opener_id = ticket[1] if ticket else None
        if not (is_mod_member(interaction.user) or interaction.user.id == opener_id):
            await interaction.response.send_message("Only staff or the ticket opener can close this ticket.", ephemeral=True)
            return
        await interaction.response.send_message("Closing ticket...", ephemeral=True)
        await close_ticket(interaction.channel, closer=interaction.user)

# -----------------------
# Close ticket implementation (transcript + log + delete)
# -----------------------
async def close_ticket(channel: discord.TextChannel, closer: discord.Member):
    guild = channel.guild
    # fetch history
    lines = []
    async for m in channel.history(limit=None, oldest_first=True):
        ts = m.created_at.strftime("%Y-%m-%d %H:%M")
        author = f"{m.author} ({m.author.id})"
        content = m.content or ""
        if m.attachments:
            content += " [attachment]"
        lines.append(f"[{ts}] {author}: {content}")
    transcript = "\n".join(lines)
    transcript_bytes = io.BytesIO(transcript.encode("utf-8"))
    file = discord.File(fp=transcript_bytes, filename=f"{channel.name}-transcript.txt")
    # compose embed
    ticket_row = db_get_ticket(channel.id)
    issue_text = ticket_row[3] if ticket_row else "N/A"
    embed = discord.Embed(title=f"{EMOJI_PREFIX} Ticket Closed" if EMOJI_PREFIX else "Ticket Closed",
                          description=f"Closed by {closer.mention}", color=EMBED_COLOR)
    embed.add_field(name="Channel", value=channel.name, inline=True)
    embed.add_field(name="Issue", value=issue_text, inline=True)
    embed.add_field(name="Closed at", value=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), inline=True)
    await log_to_channel(guild, embed=embed, file=file)
    db_remove_ticket(channel.id)
    try:
        await channel.delete()
    except Exception as e:
        print("Failed to delete ticket channel:", e)

# -----------------------
# SLASH COMMANDS
# -----------------------
@tree.command(name="panel", description="Post the ticket panel", guild=GUILD_OBJ)
async def cmd_panel(interaction: Interaction):
    embed = discord.Embed(title=f"{EMOJI_PREFIX} Guidelines" if EMOJI_PREFIX else "Guidelines",
                          description="Tickets are for serious support matters only. Select a category and provide your reason.", color=EMBED_COLOR)
    view = TicketPanelView()
    await interaction.response.send_message(embed=embed, view=view)
    await log_to_channel(interaction.guild, content=f"📋 Ticket panel posted by {interaction.user.mention}")

@tree.command(name="purge", description="Delete messages (mod only)", guild=GUILD_OBJ)
async def cmd_purge(interaction: Interaction, amount: int):
    if not is_mod_member(interaction.user):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)
    await log_to_channel(interaction.guild, content=f"🧹 {interaction.user.mention} purged {len(deleted)} messages in {interaction.channel.mention}")

@tree.command(name="kick", description="Kick a member (mod only)", guild=GUILD_OBJ)
async def cmd_kick(interaction: Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not is_mod_member(interaction.user):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"✅ {member.mention} kicked. Reason: {reason}")
        await log_to_channel(interaction.guild, content=f"👢 {member.mention} was kicked by {interaction.user.mention}. Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Failed to kick: {e}", ephemeral=True)

@tree.command(name="ban", description="Ban a member (mod only)", guild=GUILD_OBJ)
async def cmd_ban(interaction: Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not is_mod_member(interaction.user):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"✅ {member.mention} banned. Reason: {reason}")
        await log_to_channel(interaction.guild, content=f"🔨 {member.mention} was banned by {interaction.user.mention}. Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Failed to ban: {e}", ephemeral=True)

@tree.command(name="timeout", description="Timeout a member in minutes (mod only)", guild=GUILD_OBJ)
async def cmd_timeout(interaction: Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
    if not is_mod_member(interaction.user):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    try:
        until = datetime.utcnow() + timedelta(minutes=minutes)
        await member.timeout(until=until, reason=reason)
        await interaction.response.send_message(f"✅ {member.mention} timed out for {minutes} minutes. Reason: {reason}")
        await log_to_channel(interaction.guild, content=f"⏰ {member.mention} timed out by {interaction.user.mention} for {minutes} minutes. Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Failed to timeout: {e}", ephemeral=True)

@tree.command(name="mute", description="Add Muted role to a member (mod only)", guild=GUILD_OBJ)
async def cmd_mute(interaction: Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not is_mod_member(interaction.user):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    role = discord.utils.get(interaction.guild.roles, name="Muted")
    if role is None:
        try:
            role = await interaction.guild.create_role(name="Muted", reason="Create Muted role for bot")
            for ch in interaction.guild.channels:
                try:
                    await ch.set_permissions(role, send_messages=False, speak=False)
                except:
                    pass
        except Exception as e:
            await interaction.response.send_message("Failed to create Muted role: " + str(e), ephemeral=True)
            return
    try:
        await member.add_roles(role, reason=reason)
        await interaction.response.send_message(f"✅ {member.mention} muted. Reason: {reason}")
        await log_to_channel(interaction.guild, content=f"🔇 {member.mention} muted by {interaction.user.mention}. Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Failed to mute: {e}", ephemeral=True)

@tree.command(name="unmute", description="Remove Muted role from a member (mod only)", guild=GUILD_OBJ)
async def cmd_unmute(interaction: Interaction, member: discord.Member):
    if not is_mod_member(interaction.user):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    role = discord.utils.get(interaction.guild.roles, name="Muted")
    if role:
        try:
            await member.remove_roles(role)
            await interaction.response.send_message(f"✅ {member.mention} unmuted.")
            await log_to_channel(interaction.guild, content=f"🔊 {member.mention} unmuted by {interaction.user.mention}.")
        except Exception as e:
            await interaction.response.send_message(f"Failed to unmute: {e}", ephemeral=True)
    else:
        await interaction.response.send_message("Muted role not found.", ephemeral=True)

@tree.command(name="lock", description="Lock this channel (mod only)", guild=GUILD_OBJ)
async def cmd_lock(interaction: Interaction):
    if not is_mod_member(interaction.user):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, view_channel=False, send_messages=False)
    await interaction.response.send_message("🔒 Channel locked.")
    await log_to_channel(interaction.guild, content=f"🔒 {interaction.channel.mention} locked by {interaction.user.mention}")

@tree.command(name="unlock", description="Unlock this channel (mod only)", guild=GUILD_OBJ)
async def cmd_unlock(interaction: Interaction):
    if not is_mod_member(interaction.user):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=None)
    await interaction.response.send_message("🔓 Channel unlocked.")
    await log_to_channel(interaction.guild, content=f"🔓 {interaction.channel.mention} unlocked by {interaction.user.mention}")

@tree.command(name="adduser", description="Add a user to this ticket", guild=GUILD_OBJ)
async def cmd_adduser(interaction: Interaction, member: discord.Member):
    ticket = db_get_ticket(interaction.channel.id)
    opener = ticket[1] if ticket else None
    if not (is_mod_member(interaction.user) or interaction.user.id == opener):
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return
    await interaction.channel.set_permissions(member, view_channel=True, send_messages=True)
    await interaction.response.send_message(f"✅ {member.mention} added to this ticket.")
    await log_to_channel(interaction.guild, content=f"➕ {member.mention} added to {interaction.channel.mention} by {interaction.user.mention}")

@tree.command(name="removeuser", description="Remove a user from this ticket", guild=GUILD_OBJ)
async def cmd_removeuser(interaction: Interaction, member: discord.Member):
    ticket = db_get_ticket(interaction.channel.id)
    opener = ticket[1] if ticket else None
    if not (is_mod_member(interaction.user) or interaction.user.id == opener):
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return
    await interaction.channel.set_permissions(member, overwrite=None)
    await interaction.response.send_message(f"✅ {member.mention} removed from this ticket.")
    await log_to_channel(interaction.guild, content=f"➖ {member.mention} removed from {interaction.channel.mention} by {interaction.user.mention}")

@tree.command(name="close", description="Close this ticket", guild=GUILD_OBJ)
async def cmd_close(interaction: Interaction):
    ticket = db_get_ticket(interaction.channel.id)
    opener = ticket[1] if ticket else None
    if not (is_mod_member(interaction.user) or interaction.user.id == opener):
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return
    await interaction.response.send_message("Closing ticket...", ephemeral=True)
    await close_ticket(interaction.channel, closer=interaction.user)

@tree.command(name="say", description="Make the bot say something (restricted)", guild=GUILD_OBJ)
async def cmd_say(interaction: Interaction, message: str):
    if not has_say_role(interaction.user):
        await interaction.response.send_message("You are not authorized to use /say.", ephemeral=True)
        return
    await interaction.response.send_message("✅ Message sent.", ephemeral=True)
    await interaction.channel.send(message)
    await log_to_channel(interaction.guild, content=f'🗣️ /say by {interaction.user.mention}: "{message}"')

@tree.command(name="ping", description="Check bot latency", guild=GUILD_OBJ)
async def cmd_ping(interaction: Interaction):
    await interaction.response.send_message(f"🏓 Pong! {round(bot.latency*1000)}ms")

# -----------------------
# ON READY (sync commands, auto-post panel if requested)
# -----------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync(guild=GUILD_OBJ)
    if TICKET_PANEL_CHANNEL:
        try:
            ch = bot.get_channel(int(TICKET_PANEL_CHANNEL))
            if ch:
                embed = discord.Embed(title=f"{EMOJI_PREFIX} Guidelines" if EMOJI_PREFIX else "Guidelines",
                                      description="Tickets are for serious support matters only. Select a category below and provide your reason.",
                                      color=EMBED_COLOR)
                await ch.send(embed=embed, view=TicketPanelView())
                await log_to_channel(ch.guild, content=f"📋 Ticket panel posted by bot on startup.")
        except Exception as e:
            print("Auto-post panel failed:", e)

# -----------------------
# FINAL RUN
# -----------------------
if __name__ == "__main__":
    bot.run(TOKEN)
