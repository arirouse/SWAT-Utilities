import os
import discord
from discord.ext import commands
from discord import app_commands, ui
from flask import Flask
import asyncio
import time

# ------------------------------
# Load environment variables
# ------------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
DESK_CATEGORY_ID = int(os.getenv("DESK_CATEGORY_ID"))
IA_CATEGORY_ID = int(os.getenv("IA_CATEGORY_ID"))
HR_CATEGORY_ID = int(os.getenv("HR_CATEGORY_ID"))
PORT = int(os.getenv("PORT", 5000))

# ------------------------------
# Discord Bot Setup
# ------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------------------
# Logging Helper
# ------------------------------
async def log_action(action: str, user: discord.Member, channel: discord.TextChannel, reason: str = None):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return
    embed = discord.Embed(title=f":page_facing_up: {action}", color=discord.Color.blue())
    embed.add_field(name="User", value=user.mention, inline=True)
    embed.add_field(name="Channel", value=channel.mention, inline=True)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    await log_channel.send(embed=embed)

# ------------------------------
# Ticket Dropdown
# ------------------------------
class TicketDropdown(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Desk Support", description="For general issues/questions"),
            discord.SelectOption(label="IA", description="For IA-related issues"),
            discord.SelectOption(label="HR", description="For HR-related issues"),
        ]
        super().__init__(placeholder="Select a ticket type...", options=options)

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        category_id = {"Desk Support": DESK_CATEGORY_ID, "IA": IA_CATEGORY_ID, "HR": HR_CATEGORY_ID}[self.values[0]]
        guild = interaction.guild

        # Create private channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.get_role(MOD_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        channel = await guild.create_text_channel(f"{self.values[0]}-{user.name}", category=guild.get_channel(category_id), overwrites=overwrites)

        # Embed + Buttons
        embed = discord.Embed(title=f":ticket: {self.values[0]} Ticket", description=f"Ticket opened by {user.mention}")
        claim_button = ui.Button(label="Claim", style=discord.ButtonStyle.green)
        unclaim_button = ui.Button(label="Unclaim", style=discord.ButtonStyle.gray)
        close_button = ui.Button(label="Close", style=discord.ButtonStyle.red)

        view = ui.View()
        view.add_item(claim_button)
        view.add_item(unclaim_button)
        view.add_item(close_button)

        async def claim_callback(i):
            await i.response.send_message(f"Ticket claimed by {i.user.mention}", ephemeral=True)
            await log_action("Claimed Ticket", i.user, channel)

        async def unclaim_callback(i):
            await i.response.send_message(f"Ticket unclaimed by {i.user.mention}", ephemeral=True)
            await log_action("Unclaimed Ticket", i.user, channel)

        async def close_callback(i):
            await log_action("Closed Ticket", i.user, channel)
            await channel.delete()

        claim_button.callback = claim_callback
        unclaim_button.callback = unclaim_callback
        close_button.callback = close_callback

        await channel.send(embed=embed, view=view)
        await log_action("Created Ticket", user, channel)
        await interaction.response.send_message("Ticket created!", ephemeral=True)

# ------------------------------
# /panel Command
# ------------------------------
@bot.tree.command(name="panel", description="Posts the ticket panel (MOD only)")
async def panel(interaction: discord.Interaction):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this.", ephemeral=True)
        return
    embed = discord.Embed(title=":ticket: Open a Ticket", description="Select your ticket type below.")
    view = ui.View()
    view.add_item(TicketDropdown())
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ------------------------------
# /say Command
# ------------------------------
@bot.tree.command(name="say", description="Bot sends a message (SAY role only)")
@app_commands.describe(message="Message to send")
async def say(interaction: discord.Interaction, message: str):
    if SAY_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this.", ephemeral=True)
        return
    await interaction.channel.send(message)
    await interaction.response.send_message("Message sent.", ephemeral=True)
    await log_action("Say Command", interaction.user, interaction.channel, reason=message)

# ------------------------------
# /ping Command
# ------------------------------
@bot.tree.command(name="ping", description="Check if bot is online")
async def ping(interaction: discord.Interaction):
    start = time.perf_counter()
    msg = await interaction.response.send_message("Pong!", ephemeral=True)
    latency = round((time.perf_counter() - start) * 1000)
    await interaction.edit_original_response(content=f"Pong! {latency}ms")
    await log_action("Ping Command", interaction.user, interaction.channel, reason=f"Latency: {latency}ms")

# ------------------------------
# Mod Commands: lock/unlock/purge
# ------------------------------
@bot.tree.command(name="lock", description="Lock the channel")
@app_commands.describe(reason="Reason for locking")
async def lock(interaction: discord.Interaction, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message(f"Channel locked: {reason}", ephemeral=True)
    await log_action("Locked Channel", interaction.user, interaction.channel, reason=reason)

@bot.tree.command(name="unlock", description="Unlock the channel")
@app_commands.describe(reason="Reason for unlocking")
async def unlock(interaction: discord.Interaction, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
    await interaction.response.send_message(f"Channel unlocked: {reason}", ephemeral=True)
    await log_action("Unlocked Channel", interaction.user, interaction.channel, reason=reason)

@bot.tree.command(name="purge", description="Delete messages")
@app_commands.describe(amount="Number of messages", reason="Reason for deletion")
async def purge(interaction: discord.Interaction, amount: int, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this.", ephemeral=True)
        return
    messages = await interaction.channel.purge(limit=amount)
    with open("purged_messages.txt", "a") as f:
        for msg in messages:
            f.write(f"{msg.author}: {msg.content}\n")
    await interaction.response.send_message(f"Purged {len(messages)} messages: {reason}", ephemeral=True)
    await log_action("Purged Messages", interaction.user, interaction.channel, reason=reason)

# ------------------------------
# /add and /remove for ticket channels
# ------------------------------
@bot.tree.command(name="add", description="Add a user to a ticket channel")
@app_commands.describe(user="User to add")
async def add(interaction: discord.Interaction, user: discord.Member):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this.", ephemeral=True)
        return
    await interaction.channel.set_permissions(user, view_channel=True, send_messages=True)
    await interaction.response.send_message(f"{user.mention} added to the ticket.", ephemeral=True)
    await log_action("Added User to Ticket", interaction.user, interaction.channel, reason=f"Added {user.mention}")

@bot.tree.command(name="remove", description="Remove a user from a ticket channel")
@app_commands.describe(user="User to remove")
async def remove(interaction: discord.Interaction, user: discord.Member):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this.", ephemeral=True)
        return
    await interaction.channel.set_permissions(user, view_channel=False)
    await interaction.response.send_message(f"{user.mention} removed from the ticket.", ephemeral=True)
    await log_action("Removed User from Ticket", interaction.user, interaction.channel, reason=f"Removed {user.mention}")

# ------------------------------
# Flask server for Render health checks
# ------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ------------------------------
# Run bot + Flask
# ------------------------------
async def main():
    await bot.start(TOKEN)

loop = asyncio.get_event_loop()
loop.create_task(main())
loop.create_task(asyncio.to_thread(run_flask))
loop.run_forever()
