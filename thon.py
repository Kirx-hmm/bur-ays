import discord, asyncio, json, datetime
from discord.ext import commands
from discord import app_commands

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "vouches.json"
CONFIG_FILE = "vouch_config.json"

# Helpers
def now_str():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except:
        return {"trusted_role": 0, "log_channel": 0, "vouch_channel": 0}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)

async def update_trusted_role(member, total):
    cfg = load_config()
    role = member.guild.get_role(cfg.get("trusted_role", 0))
    if not role:
        return
    if total >= 10 and role not in member.roles:
        await member.add_roles(role, reason="Reached 10 vouches")
    elif total < 10 and role in member.roles:
        await member.remove_roles(role, reason="Below 10 vouches")

async def log_vouch(guild, embed):
    cfg = load_config()
    ch = guild.get_channel(cfg.get("log_channel", 0))
    if ch:
        await ch.send(embed=embed)

@bot.event
async def on_ready():
    synced = await bot.tree.sync()
    print(f"✅ Bot is ready. Synced {len(synced)} commands:")
    for cmd in synced:
        print(f" - /{cmd.name}")

# Slash Commands
@bot.tree.command(name="vouch", description="Submit a vouch with image proof")
@app_commands.describe(user="User to vouch", image="Image proof")
async def vouch(inter: discord.Interaction, user: discord.User, image: discord.Attachment):
    if user.id == inter.user.id:
        return await inter.response.send_message("You can't vouch yourself.", ephemeral=True)
    if not image.content_type.startswith("image"):
        return await inter.response.send_message("Please attach a valid image.", ephemeral=True)

    data = load_data()
    uid = str(user.id)
    now = now_str()
    d = data.get(uid, {})
    d["total"] = d.get("total", 0) + 1
    d.setdefault("daily", {})[now] = d["daily"].get(now, 0) + 1
    last = d.get("last_day", "")
    streak = d.get("streak", 0)
    if last == (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%d"):
        streak += 1
    elif last != now:
        streak = 1
    d["streak"] = streak
    d["last_day"] = now
    data[uid] = d
    save_data(data)

    await update_trusted_role(inter.guild.get_member(user.id), d["total"])

    embed = discord.Embed(title="✅ Vouch Submitted", color=discord.Color.green())
    embed.description = f"**From:** {inter.user.mention}\n**To:** {user.mention}"
    embed.add_field(name="Total Vouches", value=f"{d['total']}", inline=True)
    embed.add_field(name="Streak", value=f"{streak} days", inline=True)
    embed.set_image(url=image.url)
    await inter.response.send_message(embed=embed)
    await log_vouch(inter.guild, embed)

@bot.tree.command(name="vouches", description="Check a user's vouches")
@app_commands.describe(user="User to check")
async def vouches(inter: discord.Interaction, user: discord.User):
    d = load_data().get(str(user.id), {})
    embed = discord.Embed(title=f"📊 Vouch Stats for {user.name}", color=discord.Color.blurple())
    embed.add_field(name="Total", value=f"{d.get('total', 0)}", inline=True)
    embed.add_field(name="Today", value=f"{d.get('daily', {}).get(now_str(), 0)}", inline=True)
    embed.add_field(name="Streak", value=f"{d.get('streak', 0)} days", inline=True)
    await inter.response.send_message(embed=embed)

@bot.tree.command(name="top10_today", description="Show today's top 10 vouched users")
async def top10_today(inter: discord.Interaction):
    data = load_data()
    today = now_str()
    scores = [(uid, d.get("daily", {}).get(today, 0)) for uid, d in data.items()]
    scores = sorted([x for x in scores if x[1] > 0], key=lambda x: x[1], reverse=True)[:10]
    embed = discord.Embed(title="🏆 Top 10 Today", color=discord.Color.gold())
    for i, (uid, count) in enumerate(scores, 1):
        embed.add_field(name=f"#{i}", value=f"<@{uid}> — {count} vouches", inline=False)
    await inter.response.send_message(embed=embed)

@bot.tree.command(name="vouch_add", description="Admin: Add vouches")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="User", amount="How many")
async def vouch_add(inter: discord.Interaction, user: discord.User, amount: int):
    data = load_data()
    uid = str(user.id)
    d = data.get(uid, {})
    d["total"] = d.get("total", 0) + amount
    data[uid] = d
    save_data(data)
    await update_trusted_role(inter.guild.get_member(user.id), d["total"])
    await inter.response.send_message(f"✅ Added {amount} vouches to {user.mention}")

@bot.tree.command(name="vouch_revoke", description="Admin: Revoke vouches")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="User", amount="Amount")
async def vouch_revoke(inter: discord.Interaction, user: discord.User, amount: int):
    data = load_data()
    uid = str(user.id)
    d = data.get(uid, {})
    d["total"] = max(0, d.get("total", 0) - amount)
    data[uid] = d
    save_data(data)
    await update_trusted_role(inter.guild.get_member(user.id), d["total"])
    await inter.response.send_message(f"❌ Removed {amount} vouches from {user.mention}")

@bot.tree.command(name="vouch_reset", description="Admin: Reset user vouches")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="User")
async def vouch_reset(inter: discord.Interaction, user: discord.User):
    data = load_data()
    if str(user.id) in data:
        del data[str(user.id)]
        save_data(data)
        await inter.response.send_message(f"🔁 Reset vouch data for {user.mention}")
    else:
        await inter.response.send_message("❌ No vouch data found.")

@bot.tree.command(name="set_trusted_role", description="Admin: Set trusted role")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(role="Trusted trader role")
async def set_trusted_role(inter: discord.Interaction, role: discord.Role):
    cfg = load_config()
    cfg["trusted_role"] = role.id
    save_config(cfg)
    await inter.response.send_message(f"🔐 Trusted role set to {role.mention}", ephemeral=True)

@bot.tree.command(name="set_vouch_log_channel", description="Admin: Set log channel")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Log channel")
async def set_vouch_log_channel(inter: discord.Interaction, channel: discord.TextChannel):
    cfg = load_config()
    cfg["log_channel"] = channel.id
    save_config(cfg)
    await inter.response.send_message(f"📋 Log channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="set_vouch_channel", description="Admin: Set vouch listener channel")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Channel where bot scans vouches")
async def set_vouch_channel(inter: discord.Interaction, channel: discord.TextChannel):
    cfg = load_config()
    cfg["vouch_channel"] = channel.id
    save_config(cfg)
    await inter.response.send_message(f"📡 Listening to vouches in {channel.mention}", ephemeral=True)

@bot.tree.command(name="ping", description="Check bot latency")
async def ping(inter: discord.Interaction):
    await inter.response.send_message(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.tree.command(name="vouch_status", description="See vouch statistics")
async def vouch_status(inter: discord.Interaction):
    data = load_data()
    total = sum(d.get("total", 0) for d in data.values())
    users = len(data)
    today = now_str()
    today_total = sum(d.get("daily", {}).get(today, 0) for d in data.values())
    embed = discord.Embed(title="📈 Vouch Stats", color=discord.Color.purple())
    embed.add_field(name="Total Vouches", value=f"{total}")
    embed.add_field(name="Users", value=f"{users}")
    embed.add_field(name="Today", value=f"{today_total}")
    await inter.response.send_message(embed=embed)

@bot.tree.command(name="ping_check", description="Scan a channel for vouch-like mentions and count pings")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Channel to scan")
async def ping_check(inter: discord.Interaction, channel: discord.TextChannel):
    await inter.response.send_message("🔍 Scanning... This may take a while for large channels.", ephemeral=True)
    keywords = ["vouch", "vouched", "vouches", "legit", "trusted"]
    ping_count = {}
    async for message in channel.history(limit=None, oldest_first=True):
        if message.author.bot or not message.mentions:
            continue
        if not any(word in message.content.lower() for word in keywords):
            continue
        for user in message.mentions:
            if user.bot:
                continue
            uid = str(user.id)
            ping_count[uid] = ping_count.get(uid, 0) + 1
    if not ping_count:
        return await inter.followup.send("❌ No valid vouch pings found.")
    sorted_pings = sorted(ping_count.items(), key=lambda x: x[1], reverse=True)
    description = ""
    for i, (uid, count) in enumerate(sorted_pings[:25], 1):
        description += f"#{i} <@{uid}> — `{count}` vouch ping(s)\n"
    embed = discord.Embed(title="📡 Vouch Ping Leaderboard", description=description, color=discord.Color.teal())
    embed.set_footer(text="Scanned full channel history.")
    await inter.followup.send(embed=embed)

@bot.event
async def on_message(msg):
    if msg.author.bot:
        return
    cfg = load_config()
    if msg.channel.id != cfg.get("vouch_channel", 0):
        return
    keys = ["vouch", "vouched", "vouches", "legit", "trusted"]
    if any(k in msg.content.lower() for k in keys) and msg.mentions:
        data = load_data()
        today = now_str()
        for u in msg.mentions:
            if u.id == msg.author.id:
                continue
            d = data.get(str(u.id), {})
            d["total"] = d.get("total", 0) + 1
            daily = d.get("daily", {})
            daily[today] = daily.get(today, 0) + 1
            d["daily"] = daily
            last = d.get("last_day", "")
            streak = d.get("streak", 0)
            if last == (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%d"):
                streak += 1
            elif last != today:
                streak = 1
            d["streak"] = streak
            d["last_day"] = today
            data[str(u.id)] = d
            await update_trusted_role(msg.guild.get_member(u.id), d["total"])
        save_data(data)
        try:
            await msg.channel.send("✅ Vouch recorded.", delete_after=10)
        except:
            pass
    await bot.process_commands(msg)

import os
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)

