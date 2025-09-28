import discord
from discord.ext import commands
from discord import app_commands, ui
import os
from flask import Flask
import asyncio

# --- Environment Variables ---
TOKEN = os.getenv("DISCORD_TOKEN")           # Your bot token
GUILD_ID = int(os.getenv("GUILD_ID"))        # Server ID
DESK_CATEGORY_ID = int(os.getenv("DESK_CATEGORY_ID"))
IA_CATEGORY_ID = int(os.getenv("IA_CATEGORY_ID"))
HR_CATEGORY_ID = int(os.getenv("HR_CATEGORY_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))

# --- Bot Setup ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# --- Flask App for Uptime ---
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=10000)

# --- Utilities ---
def mod_only(interaction: discord.Interaction):
    return MOD_ROLE_ID in [role.id for role in interaction.user.roles]

async def log_action(embed: discord.Embed):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(embed=embed)

# --- Ticket Dropdown ---
class TicketDropdown(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Desk Support", description="Inquiries, questions. Typically faster responses and age verification.", value="desk"),
            discord.SelectOption(label="Internal Affairs", description="Handling Officer reports, cases. Requires department lawyers.", value="ia"),
            discord.SelectOption(label="HR+ Support", description="Speaking to Director/SHR+, told by HR to open etc.", value="hr")
        ]
        super().__init__(placeholder="Select a category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        category_map = {
            "desk": DESK_CATEGORY_ID,
            "ia": IA_CATEGORY_ID,
            "hr": HR_CATEGORY_ID
        }
        category_id = category_map[self.values[0]]
        guild = interaction.guild
        category = guild.get_channel(category_id)

        # Create ticket channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.get_role(MOD_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        channel_name = f"ticket-{interaction.user.name.lower()}"
        ticket_channel = await guild.create_text_channel(channel_name, overwrites=overwrites, category=category)

        # Ticket embed
        embed = discord.Embed(
            title=":emoji_1: Ticket Created",
            description=f"Ticket opened by {interaction.user} ({interaction.user.id})\nCategory: {self.values[0].title()}",
            color=0x313D61
        )
        await ticket_channel.send(embed=embed)

        # Log
        log_embed = discord.Embed(
            title=":emoji_1: Ticket Opened",
            description=f"User: {interaction.user} ({interaction.user.id})\nCategory: {self.values[0].title()}",
            color=0x313D61
        )
        await log_action(log_embed)
        await interaction.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)

class TicketView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(TicketDropdown())

# --- Commands ---
@bot.tree.command(name="panel", description="Send the ticket panel")
async def panel(interaction: discord.Interaction):
    if not mod_only(interaction):
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
        return
    embed = discord.Embed(
        title=":emoji_1: Ticket Panel",
        description="Select the appropriate ticket category below.",
        color=0x313D61
    )
    await interaction.response.send_message(embed=embed, view=TicketView())

# --- Mod Commands ---
async def mod_action(interaction: discord.Interaction, user: discord.Member, action: str, reason: str, extra=None):
    if not mod_only(interaction):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    # Action embed
    embed = discord.Embed(
        title=f":emoji_1: {action.title()}",
        description=f"User: {user} ({user.id})\nBy: {interaction.user} ({interaction.user.id})\nReason: {reason}",
        color=0x313D61
    )
    await log_action(embed)
    await interaction.response.send_message(f"{action.title()} executed on {user.name}", ephemeral=True)

@bot.tree.command(name="kick", description="Kick a user")
@app_commands.describe(user="The user to kick", reason="Reason for action")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str):
    await mod_action(interaction, user, "Kick", reason)
    await user.kick(reason=reason)

@bot.tree.command(name="ban", description="Ban a user")
@app_commands.describe(user="The user to ban", reason="Reason for action")
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str):
    await mod_action(interaction, user, "Ban", reason)
    await user.ban(reason=reason)

@bot.tree.command(name="timeout", description="Timeout a user")
@app_commands.describe(user="User to timeout", duration="Duration in seconds", reason="Reason for action")
async def timeout(interaction: discord.Interaction, user: discord.Member, duration: int, reason: str):
    await mod_action(interaction, user, "Timeout", reason)
    await user.timeout(discord.Duration(seconds=duration), reason=reason)

@bot.tree.command(name="purge", description="Delete messages in a channel")
@app_commands.describe(amount="Number of messages to delete", reason="Reason for action")
async def purge(interaction: discord.Interaction, amount: int, reason: str):
    if not mod_only(interaction):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    embed = discord.Embed(
        title=":emoji_1: Messages Purged",
        description=f"Deleted {len(deleted)} messages\nBy: {interaction.user} ({interaction.user.id})\nReason: {reason}",
        color=0x313D61
    )
    await log_action(embed)
    await interaction.response.send_message(f"Deleted {len(deleted)} messages.", ephemeral=True)

@bot.tree.command(name="lock", description="Lock a channel")
@app_commands.describe(reason="Reason for locking")
async def lock(interaction: discord.Interaction, reason: str):
    if not mod_only(interaction):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    embed = discord.Embed(
        title=":emoji_1: Channel Locked",
        description=f"Channel: {interaction.channel.name}\nBy: {interaction.user} ({interaction.user.id})\nReason: {reason}",
        color=0x313D61
    )
    await log_action(embed)
    await interaction.response.send_message("Channel locked.", ephemeral=True)

@bot.tree.command(name="unlock", description="Unlock a channel")
@app_commands.describe(reason="Reason for unlocking")
async def unlock(interaction: discord.Interaction, reason: str):
    if not mod_only(interaction):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = True
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    embed = discord.Embed(
        title=":emoji_1: Channel Unlocked",
        description=f"Channel: {interaction.channel.name}\nBy: {interaction.user} ({interaction.user.id})\nReason: {reason}",
        color=0x313D61
    )
    await log_action(embed)
    await interaction.response.send_message("Channel unlocked.", ephemeral=True)

@bot.tree.command(name="say", description="Make the bot say something")
@app_commands.describe(message="Message to send")
async def say(interaction: discord.Interaction, message: str):
    if SAY_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    await interaction.response.send_message(message)

@bot.tree.command(name="ping", description="Check latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms")

# --- Run Bot ---
async def main():
    async with bot:
        await bot.start(TOKEN)

# Run Flask in a background thread
loop = asyncio.get_event_loop()
loop.create_task(bot.start(TOKEN))
loop.run_in_executor(None, run_flask)
loop.run_forever()
