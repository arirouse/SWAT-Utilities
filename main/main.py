import os
import sqlite3
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
from discord import app_commands

# ===== Keep-alive =====
app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

# ===== Database =====
conn = sqlite3.connect("tickets.db")
cur = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS tickets (
    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    issue TEXT,
    category TEXT,
    status TEXT
)""")
conn.commit()

# ===== Bot setup =====
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

GUILD_ID = int(os.environ.get("GUILD_ID", "0"))  # optional: restrict to your server
TICKET_CATEGORIES = {
    "desk": "Desk Support",
    "internal": "Internal Affairs",
    "hr": "HR+ Support"
}
EMBED_COLOR = 0x313D61

@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user}")

# ===== Ticket panel command =====
@tree.command(name="panel", description="Show ticket categories panel", guild=discord.Object(id=GUILD_ID))
async def panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Ticket Panel",
        description="Click the buttons below to open a ticket in the proper category.",
        color=EMBED_COLOR
    )
    for key, name in TICKET_CATEGORIES.items():
        embed.add_field(name=name, value=f"Use `/ticket {key} <issue>` to open", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ===== Ticket commands =====
@tree.command(name="ticket", description="Open a ticket", guild=discord.Object(id=GUILD_ID))
async def ticket(interaction: discord.Interaction, category: str, issue: str):
    category_name = TICKET_CATEGORIES.get(category.lower())
    if not category_name:
        await interaction.response.send_message("Invalid category. Options: desk, internal, hr", ephemeral=True)
        return

    guild = interaction.guild
    cat = discord.utils.get(guild.categories, name=category_name)
    if not cat:
        cat = await guild.create_category(category_name)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True)
    }

    channel_name = f"ticket-{interaction.user.name.lower()}"
    channel = await guild.create_text_channel(channel_name, category=cat, overwrites=overwrites)

    cur.execute("INSERT INTO tickets (user_id, issue, category, status) VALUES (?, ?, ?, ?)",
                (interaction.user.id, issue, category_name, "open"))
    conn.commit()

    embed = discord.Embed(
        title=f"Ticket Created: {category_name}",
        description=f"{interaction.user.mention} opened a ticket.\nIssue: {issue}",
        color=EMBED_COLOR
    )
    embed.add_field(name="Channel", value=channel.mention)
    embed.set_footer(text="Staff will respond shortly.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

    ticket_embed = discord.Embed(
        title="Welcome to your ticket!",
        description=f"{interaction.user.mention}, a staff member will be with you shortly.",
        color=EMBED_COLOR
    )
    ticket_embed.add_field(name="Issue", value=issue)
    ticket_embed.add_field(name="Category", value=category_name)
    await channel.send(embed=ticket_embed)

# ===== Claim ticket =====
@tree.command(name="claim", description="Claim a ticket", guild=discord.Object(id=GUILD_ID))
async def claim(interaction: discord.Interaction):
    channel = interaction.channel
    if not channel.name.startswith("ticket-"):
        await interaction.response.send_message("This command can only be used in ticket channels.", ephemeral=True)
        return
    embed = discord.Embed(
        title="Ticket Claimed",
        description=f"{interaction.user.mention} has claimed this ticket.",
        color=EMBED_COLOR
    )
    await interaction.response.send_message(embed=embed)

# ===== Add user =====
@tree.command(name="add", description="Add a user to a ticket", guild=discord.Object(id=GUILD_ID))
async def add(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    if not channel.name.startswith("ticket-"):
        await interaction.response.send_message("This command can only be used in ticket channels.", ephemeral=True)
        return
    await channel.set_permissions(member, read_messages=True)
    embed = discord.Embed(
        title="User Added",
        description=f"{member.mention} has been added to this ticket.",
        color=EMBED_COLOR
    )
    await interaction.response.send_message(embed=embed)

# ===== Remove user =====
@tree.command(name="remove", description="Remove a user from a ticket", guild=discord.Object(id=GUILD_ID))
async def remove(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    if not channel.name.startswith("ticket-"):
        await interaction.response.send_message("This command can only be used in ticket channels.", ephemeral=True)
        return
    await channel.set_permissions(member, overwrite=None)
    embed = discord.Embed(
        title="User Removed",
        description=f"{member.mention} has been removed from this ticket.",
        color=EMBED_COLOR
    )
    await interaction.response.send_message(embed=embed)

# ===== Run bot =====
bot.run(os.environ["TOKEN"])
