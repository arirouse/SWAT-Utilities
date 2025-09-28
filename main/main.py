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

# ===== Database setup =====
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

GUILD_ID = int(os.environ.get("GUILD_ID", "0"))  # Optional, restrict commands to your server
TICKET_CATEGORIES = {
    "desk": "Desk Support",
    "internal": "Internal Affairs",
    "hr": "HR+ Support"
}
EMBED_COLOR = 0x313D61

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# ===== Commands =====

@bot.command()
async def ticket(ctx, category="desk", *, issue="No issue provided"):
    """Open a ticket in the proper category."""
    category_name = TICKET_CATEGORIES.get(category.lower())
    if not category_name:
        await ctx.send("Invalid category. Options: desk, internal, hr")
        return

    guild = ctx.guild
    cat = discord.utils.get(guild.categories, name=category_name)
    if not cat:
        cat = await guild.create_category(category_name)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True)
    }

    channel_name = f"ticket-{ctx.author.name.lower()}"
    channel = await guild.create_text_channel(channel_name, category=cat, overwrites=overwrites)

    cur.execute("INSERT INTO tickets (user_id, issue, category, status) VALUES (?, ?, ?, ?)",
                (ctx.author.id, issue, category_name, "open"))
    conn.commit()

    embed = discord.Embed(
        title=f"Ticket Opened: {category_name}",
        description=issue,
        color=EMBED_COLOR
    )
    embed.set_footer(text=f"Opened by {ctx.author}")
    await channel.send(embed=embed)
    await ctx.send(f"Ticket created: {channel.mention}")

@bot.command()
async def claim(ctx):
    """Claim a ticket."""
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("This command can only be used inside a ticket channel.")
        return
    embed = discord.Embed(
        title="Ticket Claimed",
        description=f"{ctx.author.mention} has claimed this ticket.",
        color=EMBED_COLOR
    )
    await ctx.send(embed=embed)

@bot.command()
async def add(ctx, member: discord.Member):
    """Add a user to a ticket."""
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("This command can only be used inside a ticket channel.")
        return
    await ctx.channel.set_permissions(member, read_messages=True)
    embed = discord.Embed(
        title="User Added",
        description=f"{member.mention} has been added to this ticket.",
        color=EMBED_COLOR
    )
    await ctx.send(embed=embed)

@bot.command()
async def remove(ctx, member: discord.Member):
    """Remove a user from a ticket."""
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("This command can only be used inside a ticket channel.")
        return
    await ctx.channel.set_permissions(member, overwrite=None)
    embed = discord.Embed(
        title="User Removed",
        description=f"{member.mention} has been removed from this ticket.",
        color=EMBED_COLOR
    )
    await ctx.send(embed=embed)

# ===== Run bot =====
bot.run(os.environ["TOKEN"])
