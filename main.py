import os
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
import asyncio

# Environment variables
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
DESK_CAT_ID = int(os.getenv("DESK_CAT_ID"))
IA_CAT_ID = int(os.getenv("IA_CAT_ID"))
HR_CAT_ID = int(os.getenv("HR_CAT_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))

# Bot setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree
guild = discord.Object(id=GUILD_ID)

EMBED_COLOR = discord.Color.from_str("#313D61")
EMOJI_HEADER = ":emoji_1:"

# ---------------------- Logging helper ----------------------
async def log_action(action, user, moderator, reason=None):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        embed = discord.Embed(color=EMBED_COLOR)
        embed.title = f"{EMOJI_HEADER} {action}"
        desc = f"**User:** {user.name}#{user.discriminator} (`{user.id}`)\n**Moderator:** {moderator.name}#{moderator.discriminator}"
        if reason:
            desc += f"\n**Reason:** {reason}"
        embed.description = desc
        await channel.send(embed=embed)

# ---------------------- Ticket Panel ----------------------
@tree.command(name="panel", description="Send the ticket panel", guild=guild)
async def panel(interaction: discord.Interaction):
    mod_role = discord.utils.get(interaction.guild.roles, id=MOD_ROLE_ID)
    if mod_role not in interaction.user.roles:
        await interaction.response.send_message("You cannot use this.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"{EMOJI_HEADER} Ticket Panel",
        description="Select the category to open a ticket",
        color=EMBED_COLOR
    )
    select = discord.ui.Select(
        placeholder="Choose a ticket type...",
        options=[
            discord.SelectOption(label="Desk Support", value="desk"),
            discord.SelectOption(label="Internal Affairs", value="ia"),
            discord.SelectOption(label="HR+ Support", value="hr")
        ]
    )

    async def select_callback(select_interaction):
        reason_modal = discord.ui.Modal(title="Ticket Reason")
        reason_input = discord.ui.TextInput(
            label="Reason for ticket",
            style=discord.TextStyle.paragraph,
            required=True
        )
        reason_modal.add_item(reason_input)

        async def modal_callback(modal_interaction):
            category_map = {
                "desk": DESK_CAT_ID,
                "ia": IA_CAT_ID,
                "hr": HR_CAT_ID
            }
            category_id = category_map.get(select.values[0])
            category = bot.get_channel(category_id)
            ticket_name = f"{interaction.user.name}-{select.values[0]}"
            channel = await interaction.guild.create_text_channel(ticket_name, category=category)
            embed = discord.Embed(title=f"{EMOJI_HEADER} Ticket Created",
                                  description=f"Ticket for {interaction.user.mention}\n**Reason:** {reason_input.value}",
                                  color=EMBED_COLOR)
            await channel.send(embed=embed)
            await modal_interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)

        reason_modal.on_submit = modal_callback
        await select_interaction.response.send_modal(reason_modal)

    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message(embed=embed, view=view)

# ---------------------- Moderation Commands ----------------------
def mod_only(interaction: discord.Interaction):
    mod_role = discord.utils.get(interaction.guild.roles, id=MOD_ROLE_ID)
    return mod_role in interaction.user.roles

@tree.command(name="kick", description="Kick a member", guild=guild)
@app_commands.describe(user="User to kick", reason="Reason for kick")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str):
    if not mod_only(interaction):
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    await user.kick(reason=reason)
    await log_action("Kick", user, interaction.user, reason)
    await interaction.response.send_message(f"{user} has been kicked.", ephemeral=True)

@tree.command(name="ban", description="Ban a member", guild=guild)
@app_commands.describe(user="User to ban", reason="Reason for ban")
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str):
    if not mod_only(interaction):
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    await user.ban(reason=reason)
    await log_action("Ban", user, interaction.user, reason)
    await interaction.response.send_message(f"{user} has been banned.", ephemeral=True)

@tree.command(name="timeout", description="Timeout a member", guild=guild)
@app_commands.describe(user="User to timeout", reason="Reason for timeout", duration="Duration in minutes")
async def timeout(interaction: discord.Interaction, user: discord.Member, reason: str, duration: int):
    if not mod_only(interaction):
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    await user.timeout(duration*60, reason=reason)
    await log_action("Timeout", user, interaction.user, reason)
    await interaction.response.send_message(f"{user} has been timed out.", ephemeral=True)

@tree.command(name="purge", description="Purge messages", guild=guild)
@app_commands.describe(amount="Number of messages to purge")
async def purge(interaction: discord.Interaction, amount: int):
    if not mod_only(interaction):
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await log_action("Purge", interaction.user, interaction.user, f"{len(deleted)} messages")
    await interaction.response.send_message(f"Purged {len(deleted)} messages.", ephemeral=True)

@tree.command(name="lock", description="Lock a channel", guild=guild)
@app_commands.describe(reason="Reason for lock")
async def lock(interaction: discord.Interaction, reason: str):
    if not mod_only(interaction):
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await log_action("Lock", interaction.channel, interaction.user, reason)
    await interaction.response.send_message(f"Channel locked.", ephemeral=True)

@tree.command(name="unlock", description="Unlock a channel", guild=guild)
@app_commands.describe(reason="Reason for unlock")
async def unlock(interaction: discord.Interaction, reason: str):
    if not mod_only(interaction):
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
    await log_action("Unlock", interaction.channel, interaction.user, reason)
    await interaction.response.send_message(f"Channel unlocked.", ephemeral=True)

@tree.command(name="say", description="Say a message", guild=guild)
@app_commands.describe(message="Message to say")
async def say(interaction: discord.Interaction, message: str):
    role = discord.utils.get(interaction.guild.roles, id=SAY_ROLE_ID)
    if role not in interaction.user.roles:
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    await interaction.channel.send(message)
    await interaction.response.send_message("Message sent.", ephemeral=True)

@tree.command(name="ping", description="Bot latency", guild=guild)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms")

# ---------------------- Events ----------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync(guild=guild)
    print("Slash commands synced!")

# ---------------------- Flask for uptime ----------------------
app = Flask("main")

@app.route("/")
def home():
    return "Bot is running."

async def main():
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
    app.run(host="0.0.0.0", port=10000)
