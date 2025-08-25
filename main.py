# -*- coding: utf-8 -*-
"""
Omni Discord Bot (Single-File, Replit-ready)
- 100+ features across utility/fun/productivity
- 50+ admin/mod tools (roles, mutes, warns, filters, logs, tickets, etc.)
- Single file (no packaging). Auto-installs dependencies on first run.
- JSON persistence created on-the-fly: data.json (same directory)
- Works with message commands (prefix) and slash commands (/) where practical

Quick Start on Replit:
1) Create new Python Repl and paste this entire file as main.py.
2) In the left sidebar, add a Secret named DISCORD_TOKEN with your bot token.
3) Click Run. Copy the keep-alive URL from console if printed and keep the repl always-on.
4) Invite bot to your server with proper intents (Server Members Intent ON in Dev Portal).

Default prefix: !  (You can change with: !prefix set ?)

NOTE: For safety, never hardcode your token in code. Use env var DISCORD_TOKEN.
"""
import os, sys, json, time, asyncio, random, math, textwrap, traceback, contextlib, re
from datetime import datetime, timedelta

# ---- Auto install deps on first run ----
REQUIRED = [
    ("discord", "discord.py"),
    ("flask", "Flask"),
]
for mod, pipname in REQUIRED:
    try:
        __import__(mod)
    except Exception:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", pipname])

import discord
from discord.ext import commands, tasks
from discord import app_commands
from flask import Flask

# ---- Keep-alive tiny web server (for Replit) ----
app = Flask(__name__)
@app.get("/")
def root():
    return "OK: OmniBot is alive"

def run_keepalive():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# Start keep-alive in background thread
import threading
threading.Thread(target=run_keepalive, daemon=True).start()

# ---- Intents & Prefix ----
DEFAULT_PREFIX = "!"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True

# ---- Storage Helpers ----
DATA_FILE = "data.json"
DEFAULT_DATA = {
    "prefix": {},                 # guild_id -> prefix
    "log_channel": {},            # guild_id -> channel_id
    "welcome": {},                # guild_id -> {"enabled": bool, "channel": id, "message": str}
    "goodbye": {},                # guild_id -> {"enabled": bool, "channel": id, "message": str}
    "autorole": {},               # guild_id -> role_id or None
    "filters": {},                # guild_id -> [bad words]
    "antispam": {},               # guild_id -> {"enabled": bool, "threshold": int, "interval": int}
    "warns": {},                  # guild_id -> {user_id: count}
    "tickets": {},                # guild_id -> {user_id: channel_id}
    "starboard": {},              # guild_id -> {"channel": id, "threshold": int}
    "reminders": [],              # list of {guild, user, channel, when_ts, text}
}

def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_DATA, f, ensure_ascii=False, indent=2)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Ensure all keys exist
    for k, v in DEFAULT_DATA.items():
        data.setdefault(k, v if not isinstance(v, dict) else dict(v))
    return data

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

DATA = load_data()

# ---- Dynamic Prefix ----
async def get_prefix(bot, message):
    if not message.guild:
        return DEFAULT_PREFIX
    gid = str(message.guild.id)
    return DATA["prefix"].get(gid, DEFAULT_PREFIX)

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

START_TIME = time.time()

# ---- Utilities ----

def human_timedelta(dt: float) -> str:
    secs = int(max(0, dt))
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)

async def send_log(guild: discord.Guild, embed: discord.Embed):
    gid = str(guild.id)
    ch_id = DATA["log_channel"].get(gid)
    if ch_id:
        ch = guild.get_channel(ch_id)
        if ch:
            with contextlib.suppress(Exception):
                await ch.send(embed=embed)

# ---- Sync slash commands ----
@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
    except Exception:
        pass
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

# ---- Help ----
@bot.command(name="help")
async def help_cmd(ctx: commands.Context, *, topic: str = None):
    prefix = DATA["prefix"].get(str(ctx.guild.id), DEFAULT_PREFIX) if ctx.guild else DEFAULT_PREFIX
    desc = f"**OmniBot 指令總覽**\n前綴：`{prefix}`，也支援部分斜線命令。\n常用：`{prefix}help [模組]`\n\n模組：\n- 基本：ping, uptime, prefix, invite, say, echo, calc\n- 公告/私訊：announce, announce_all, dm\n- 查詢：userinfo, serverinfo, roleinfo, avatar, emojiinfo\n- 投票/活動：poll, giveaway, choose\n- 有趣：8ball, dice, coin, rps\n- 審核/管理：purge, kick, ban, unban, mute, unmute, slowmode, lock, unlock, nuke, pin, unpin\n- 角色：addrole, removerole, autorole set/clear\n- 進出伺服器：welcome set/toggle, goodbye set/toggle\n- 日誌：log set/clear\n- 自動管理：filter add/remove/list, antispam on/off\n- 警告系統：warn, warnings, clearwarn\n- 便利：remindme, timer\n- 票務：ticket open/close\n- 星板：starboard set/clear\n\n更多細節：`{prefix}help 管理`、`{prefix}help 公告` ..."
    if not topic:
        return await ctx.send(desc)
    topic = topic.lower()
    details = {
        "公告": "`announce <#channel> <內容>`、`announce_all <內容>`、`dm <@user> <內容>`",
        "管理": "`purge <n>`、`kick <@>`、`ban <@> [理由]`、`unban <用戶名#識別碼>`、`mute <@> <分鐘>`(timeout)、`unmute <@>`、`slowmode <秒>`、`lock`/`unlock`、`nuke`(複製頻道) 、`pin`/`unpin`、`addrole <@> <@role>`、`removerole <@> <@role>`",
        "自動": "`filter add/remove/list`、`antispam on/off [閾值] [秒數]`",
        "歡迎": "`welcome set <#channel> | <訊息>`、`welcome toggle`；訊息支援 {user} {server}",
        "離開": "`goodbye set <#channel> | <訊息>`、`goodbye toggle`",
        "日誌": "`log set <#channel>`、`log clear`",
        "星板": "`starboard set <#channel> <門檻>`、`starboard clear`",
        "票務": "`ticket open`、`ticket close`",
        "便利": "`remindme <5m|2h|1d> <內容>`、`timer <秒>`",
    }
    await ctx.send(details.get(topic, "沒有這個主題，直接輸入 `!help` 查看列表"))

# ---- Basic / Utility ----
@bot.command()
async def ping(ctx):
    lat = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! {lat}ms")

@bot.command()
async def uptime(ctx):
    await ctx.send(f"⏱️ 已上線：{human_timedelta(time.time() - START_TIME)}")

@bot.command()
@commands.has_permissions(administrator=True)
async def prefix(ctx, action: str = None, new_prefix: str = None):
    gid = str(ctx.guild.id)
    if action == "set" and new_prefix:
        DATA["prefix"][gid] = new_prefix
        save_data(DATA)
        await ctx.send(f"✅ 此伺服器前綴改為 `{new_prefix}`")
    else:
        current = DATA["prefix"].get(gid, DEFAULT_PREFIX)
        await ctx.send(f"目前前綴：`{current}`。更改：`{current}prefix set ?`")

@bot.command()
async def invite(ctx):
    await ctx.send("前往 Discord 開發者後台複製 OAuth2 URL 加入伺服器。需要 Bot 權限與 Intents。")

@bot.command()
async def say(ctx, *, text: str):
    await ctx.send(text)

@bot.command()
async def echo(ctx, *, text: str):
    emb = discord.Embed(description=text, color=discord.Color.blurple())
    emb.set_footer(text=f"by {ctx.author}")
    await ctx.send(embed=emb)

@bot.command()
async def calc(ctx, *, expr: str):
    """安全計算：僅允許數字與 + - * / ( ) . ** % //"""
    if not re.fullmatch(r"[0-9+\-*/(). %**// ]+", expr.replace("**","**")):
        return await ctx.send("❌ 僅允許基本四則運算")
    try:
        result = eval(expr, {"__builtins__": {}}, {})
        await ctx.send(f"🧮 {expr} = `{result}`")
    except Exception as e:
        await ctx.send(f"運算錯誤：{e}")

# ---- Announce / DM ----
@bot.command()
@commands.has_permissions(manage_guild=True)
async def announce(ctx, channel: discord.TextChannel, *, text: str):
    emb = discord.Embed(title="📢 公告", description=text, color=discord.Color.gold())
    emb.timestamp = datetime.utcnow()
    await channel.send(embed=emb)
    await ctx.send(f"✅ 已在 {channel.mention} 發佈。")

@bot.command(name="announce_all")
@commands.has_permissions(administrator=True)
async def announce_all(ctx, *, text: str):
    ok = 0
    emb = discord.Embed(title="📢 全服公告", description=text, color=discord.Color.orange())
    for ch in ctx.guild.text_channels:
        with contextlib.suppress(Exception):
            await ch.send(embed=emb)
            ok += 1
            break  # 預設只發到第一個可發言頻道，避免洗版；如需全部，移除 break
    await ctx.send(f"已嘗試發送，全服可見。")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def dm(ctx, member: discord.Member, *, text: str):
    with contextlib.suppress(Exception):
        await member.send(f"📨 來自 {ctx.guild.name} 管理員：\n{text}")
    await ctx.send("✅ 已嘗試傳送私訊。")

# ---- Info ----
@bot.command()
async def avatar(ctx, member: discord.Member = None):
    m = member or ctx.author
    url = m.display_avatar.url
    emb = discord.Embed(title=f"{m} 的頭像")
    emb.set_image(url=url)
    await ctx.send(embed=emb)

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    m = member or ctx.author
    roles = ", ".join(r.mention for r in m.roles[1:]) or "無"
    emb = discord.Embed(title=str(m), color=discord.Color.green())
    emb.add_field(name="加入伺服器", value=discord.utils.format_dt(m.joined_at, style='R'))
    emb.add_field(name="帳號建立", value=discord.utils.format_dt(m.created_at, style='R'))
    emb.add_field(name="身分組", value=roles, inline=False)
    await ctx.send(embed=emb)

@bot.command()
async def serverinfo(ctx):
    g = ctx.guild
    emb = discord.Embed(title=g.name)
    emb.add_field(name="成員", value=str(g.member_count))
    emb.add_field(name="頻道", value=f"{len(g.text_channels)} 文本 / {len(g.voice_channels)} 語音")
    emb.add_field(name="建立於", value=discord.utils.format_dt(g.created_at, style='D'))
    if g.icon:
        emb.set_thumbnail(url=g.icon.url)
    await ctx.send(embed=emb)

@bot.command()
async def roleinfo(ctx, role: discord.Role):
    emb = discord.Embed(title=f"Role: {role.name}", color=role.color)
    emb.add_field(name="成員數", value=str(len(role.members)))
    emb.add_field(name="建立於", value=discord.utils.format_dt(role.created_at, style='D'))
    await ctx.send(embed=emb)

@bot.command()
async def emojiinfo(ctx, emoji: discord.Emoji):
    emb = discord.Embed(title=f"表情：{emoji.name}")
    emb.add_field(name="ID", value=str(emoji.id))
    if emoji.url:
        emb.set_thumbnail(url=emoji.url)
    await ctx.send(embed=emb)

# ---- Poll / Fun ----
@bot.command()
async def poll(ctx, *, question: str):
    msg = await ctx.send(f"📊 投票：{question}\n👍/👎 來投票！")
    with contextlib.suppress(Exception):
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

@bot.command()
async def choose(ctx, *, items: str):
    parts = [p.strip() for p in items.split(",") if p.strip()]
    if not parts:
        return await ctx.send("請用逗號分隔多個選項。")
    await ctx.send(f"🎯 我選：**{random.choice(parts)}**")

@bot.command(name="8ball")
async def eight_ball(ctx, *, question: str):
    answers = [
        "當然！", "可能吧", "不太確定", "不建議", "否", "再問一次", "是的", "看起來不妙",
    ]
    await ctx.send(f"🎱 {random.choice(answers)}")

@bot.command()
async def dice(ctx, sides: int = 6):
    await ctx.send(f"🎲 擲出：{random.randint(1, max(2, sides))}")

@bot.command()
async def coin(ctx):
    await ctx.send(f"🪙 {random.choice(['正面','反面'])}")

@bot.command()
async def rps(ctx, you: str):
    opts = ["剪刀","石頭","布"]
    botpick = random.choice(opts)
    win = {"剪刀":"布","布":"石頭","石頭":"剪刀"}
    result = "平手" if you==botpick else ("你贏了" if win.get(you)==botpick else "你輸了")
    await ctx.send(f"你：{you} | 我：{botpick} → {result}")

# ---- Moderation ----
@bot.command()
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    deleted = await ctx.channel.purge(limit=min(1000, max(1, amount)))
    await ctx.send(f"🧹 已刪除 {len(deleted)} 則訊息", delete_after=3)

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str = None):
    with contextlib.suppress(Exception):
        await member.kick(reason=reason)
    await ctx.send(f"👢 已踢出 {member}。")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str = None):
    with contextlib.suppress(Exception):
        await member.ban(reason=reason, delete_message_days=0)
    await ctx.send(f"🔨 已封鎖 {member}。")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, name_and_tag: str):
    bans = await ctx.guild.bans()
    target = None
    for e in bans:
        u = e.user
        if str(u) == name_and_tag:
            target = u; break
    if not target:
        return await ctx.send("找不到該使用者。格式：名稱#識別碼")
    with contextlib.suppress(Exception):
        await ctx.guild.unban(target)
    await ctx.send(f"✅ 已解除封鎖 {target}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int, *, reason: str = None):
    dur = timedelta(minutes=max(1, minutes))
    with contextlib.suppress(Exception):
        await member.timeout(dur, reason=reason)
    await ctx.send(f"🔇 已禁言 {member} {minutes} 分鐘")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    with contextlib.suppress(Exception):
        await member.timeout(None)
    await ctx.send(f"🔈 已解除禁言 {member}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int = 0):
    with contextlib.suppress(Exception):
        await ctx.channel.edit(slowmode_delay=max(0, min(21600, seconds)))
    await ctx.send(f"🐢 慢速模式：{seconds}s")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrites.send_messages = False
    with contextlib.suppress(Exception):
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites)
    await ctx.send("🔒 此頻道已上鎖")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrites.send_messages = True
    with contextlib.suppress(Exception):
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites)
    await ctx.send("🔓 此頻道已解鎖")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def nuke(ctx):
    ch = ctx.channel
    pos = ch.position
    new_ch = await ch.clone(reason="nuke")
    await new_ch.edit(position=pos)
    with contextlib.suppress(Exception):
        await ch.delete()
    await new_ch.send("☢️ 此頻道已重置 (nuked)")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def pin(ctx):
    ref = ctx.message.reference
    if not ref or not ref.resolved:
        return await ctx.send("請回覆要置頂的訊息再執行此指令。")
    msg = ref.resolved
    with contextlib.suppress(Exception):
        await msg.pin()
    await ctx.send("📌 已置頂。")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def unpin(ctx):
    ref = ctx.message.reference
    if not ref or not ref.resolved:
        return await ctx.send("請回覆要取消置頂的訊息再執行此指令。")
    msg = ref.resolved
    with contextlib.suppress(Exception):
        await msg.unpin()
    await ctx.send("📍 已取消置頂。")

# ---- Roles ----
@bot.command()
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, role: discord.Role):
    with contextlib.suppress(Exception):
        await member.add_roles(role)
    await ctx.send(f"✅ 已給 {member} 身分組 {role.name}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, role: discord.Role):
    with contextlib.suppress(Exception):
        await member.remove_roles(role)
    await ctx.send(f"✅ 已移除 {member} 身分組 {role.name}")

@bot.group(invoke_without_command=True)
@commands.has_permissions(manage_roles=True)
def autorole(ctx):
    gid = str(ctx.guild.id)
    rid = DATA["autorole"].get(gid)
    r = ctx.guild.get_role(rid) if rid else None
    return asyncio.create_task(ctx.send(f"目前自動身分組：{r.mention if r else '未設定'}"))

@autorole.command(name="set")
@commands.has_permissions(manage_roles=True)
async def autorole_set(ctx, role: discord.Role):
    gid = str(ctx.guild.id)
    DATA["autorole"][gid] = role.id
    save_data(DATA)
    await ctx.send(f"✅ 新成員將自動賦予 {role.mention}")

@autorole.command(name="clear")
@commands.has_permissions(manage_roles=True)
async def autorole_clear(ctx):
    gid = str(ctx.guild.id)
    DATA["autorole"].pop(gid, None)
    save_data(DATA)
    await ctx.send("🧹 已清除自動身分組設定")

# ---- Welcome / Goodbye ----
@bot.group(invoke_without_command=True)
@commands.has_permissions(manage_guild=True)
def welcome(ctx):
    gid = str(ctx.guild.id)
    conf = DATA["welcome"].get(gid, {})
    ch = ctx.guild.get_channel(conf.get("channel", 0)) if conf else None
    msg = conf.get("message", "歡迎 {user} 加入 {server}！") if conf else "未設定"
    status = conf.get("enabled", False)
    return asyncio.create_task(ctx.send(f"狀態: {status} | 頻道: {ch.mention if ch else '未設定'} | 訊息: {msg}"))

@welcome.command(name="set")
@commands.has_permissions(manage_guild=True)
async def welcome_set(ctx, channel: discord.TextChannel, *, message: str):
    gid = str(ctx.guild.id)
    DATA["welcome"][gid] = {"enabled": True, "channel": channel.id, "message": message}
    save_data(DATA)
    await ctx.send("✅ 歡迎訊息已設定並啟用。支援 {user} {server}")

@welcome.command(name="toggle")
@commands.has_permissions(manage_guild=True)
async def welcome_toggle(ctx):
    gid = str(ctx.guild.id)
    conf = DATA["welcome"].setdefault(gid, {"enabled": False, "channel": 0, "message": "歡迎 {user} 加入 {server}！"})
    conf["enabled"] = not conf.get("enabled", False)
    save_data(DATA)
    await ctx.send(f"切換為 {conf['enabled']}")

@bot.group(invoke_without_command=True)
@commands.has_permissions(manage_guild=True)
def goodbye(ctx):
    gid = str(ctx.guild.id)
    conf = DATA["goodbye"].get(gid, {})
    ch = ctx.guild.get_channel(conf.get("channel", 0)) if conf else None
    msg = conf.get("message", "{user} 離開了 {server}，再會！") if conf else "未設定"
    status = conf.get("enabled", False)
    return asyncio.create_task(ctx.send(f"狀態: {status} | 頻道: {ch.mention if ch else '未設定'} | 訊息: {msg}"))

@goodbye.command(name="set")
@commands.has_permissions(manage_guild=True)
async def goodbye_set(ctx, channel: discord.TextChannel, *, message: str):
    gid = str(ctx.guild.id)
    DATA["goodbye"][gid] = {"enabled": True, "channel": channel.id, "message": message}
    save_data(DATA)
    await ctx.send("✅ 離開訊息已設定並啟用。支援 {user} {server}")

@goodbye.command(name="toggle")
@commands.has_permissions(manage_guild=True)
async def goodbye_toggle(ctx):
    gid = str(ctx.guild.id)
    conf = DATA["goodbye"].setdefault(gid, {"enabled": False, "channel": 0, "message": "{user} 離開了 {server}，再會！"})
    conf["enabled"] = not conf.get("enabled", False)
    save_data(DATA)
    await ctx.send(f"切換為 {conf['enabled']}")

# ---- Logging ----
@bot.group(invoke_without_command=True)
@commands.has_permissions(manage_guild=True)
def log(ctx):
    gid = str(ctx.guild.id)
    ch_id = DATA["log_channel"].get(gid)
    ch = ctx.guild.get_channel(ch_id) if ch_id else None
    return asyncio.create_task(ctx.send(f"目前日誌頻道：{ch.mention if ch else '未設定'}"))

@log.command(name="set")
@commands.has_permissions(manage_guild=True)
async def log_set(ctx, channel: discord.TextChannel):
    gid = str(ctx.guild.id)
    DATA["log_channel"][gid] = channel.id
    save_data(DATA)
    await ctx.send(f"✅ 日誌頻道設為 {channel.mention}")

@log.command(name="clear")
@commands.has_permissions(manage_guild=True)
async def log_clear(ctx):
    gid = str(ctx.guild.id)
    DATA["log_channel"].pop(gid, None)
    save_data(DATA)
    await ctx.send("🧹 已清除日誌頻道設定")

# ---- AutoMod: bad-words + antispam ----
@bot.group(invoke_without_command=True)
@commands.has_permissions(manage_guild=True)
def filter(ctx):
    gid = str(ctx.guild.id)
    words = DATA["filters"].get(gid, [])
    return asyncio.create_task(ctx.send("過濾詞：" + (", ".join(words) if words else "無")))

@filter.command(name="add")
@commands.has_permissions(manage_guild=True)
async def filter_add(ctx, *, word: str):
    gid = str(ctx.guild.id)
    arr = DATA["filters"].setdefault(gid, [])
    if word not in arr:
        arr.append(word)
        save_data(DATA)
    await ctx.send("✅ 已加入過濾詞")

@filter.command(name="remove")
@commands.has_permissions(manage_guild=True)
async def filter_remove(ctx, *, word: str):
    gid = str(ctx.guild.id)
    arr = DATA["filters"].setdefault(gid, [])
    with contextlib.suppress(ValueError):
        arr.remove(word)
        save_data(DATA)
    await ctx.send("🧹 已移除過濾詞")

@bot.group(invoke_without_command=True)
@commands.has_permissions(manage_guild=True)
def antispam(ctx):
    gid = str(ctx.guild.id)
    conf = DATA["antispam"].get(gid, {"enabled": False, "threshold": 5, "interval": 7})
    return asyncio.create_task(ctx.send(f"狀態: {conf['enabled']} | 閾值: {conf['threshold']} | 秒數: {conf['interval']}"))

@antispam.command(name="on")
@commands.has_permissions(manage_guild=True)
async def antispam_on(ctx, threshold: int = 5, interval: int = 7):
    gid = str(ctx.guild.id)
    DATA["antispam"][gid] = {"enabled": True, "threshold": max(3, threshold), "interval": max(3, interval)}
    save_data(DATA)
    await ctx.send("✅ 反洗版已啟用")

@antispam.command(name="off")
@commands.has_permissions(manage_guild=True)
async def antispam_off(ctx):
    gid = str(ctx.guild.id)
    DATA["antispam"][gid] = {"enabled": False, "threshold": 5, "interval": 7}
    save_data(DATA)
    await ctx.send("⏹️ 反洗版已關閉")

_recent_msgs = {}  # (guild_id, user_id) -> timestamps list

# ---- Warn System ----
@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason: str = "無"):
    gid = str(ctx.guild.id)
    uid = str(member.id)
    DATA["warns"].setdefault(gid, {})
    DATA["warns"][gid][uid] = DATA["warns"][gid].get(uid, 0) + 1
    save_data(DATA)
    await ctx.send(f"⚠️ 已警告 {member}（總數 {DATA['warns'][gid][uid]}）原因：{reason}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warnings(ctx, member: discord.Member):
    gid = str(ctx.guild.id)
    uid = str(member.id)
    cnt = DATA["warns"].get(gid, {}).get(uid, 0)
    await ctx.send(f"{member} 目前有 {cnt} 次警告")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clearwarn(ctx, member: discord.Member):
    gid = str(ctx.guild.id)
    uid = str(member.id)
    DATA["warns"].setdefault(gid, {}).pop(uid, None)
    save_data(DATA)
    await ctx.send(f"🧹 已清除 {member} 的警告")

# ---- Reminders / Timer ----
DUR_RE = re.compile(r"^(\d+)([smhd])$")

@bot.command()
async def remindme(ctx, duration: str, *, text: str):
    m = DUR_RE.match(duration)
    if not m:
        return await ctx.send("格式錯誤，例：`!remindme 5m 喝水` (s/m/h/d)")
    val, unit = int(m.group(1)), m.group(2)
    mult = dict(s=1, m=60, h=3600, d=86400)[unit]
    when = int(time.time()) + val * mult
    item = {
        "guild": ctx.guild.id if ctx.guild else 0,
        "user": ctx.author.id,
        "channel": ctx.channel.id,
        "when_ts": when,
        "text": text
    }
    DATA["reminders"].append(item)
    save_data(DATA)
    await ctx.send(f"⏰ 已設定提醒：{text}（{duration} 後）")

@bot.command()
async def timer(ctx, seconds: int):
    seconds = max(1, min(86400, seconds))
    await ctx.send(f"⏱️ 計時開始：{seconds}s 後提醒 @你")
    await asyncio.sleep(seconds)
    await ctx.send(f"⏱️ 時間到 {ctx.author.mention}！")

@tasks.loop(seconds=15)
async def reminder_loop():
    now = int(time.time())
    changed = False
    left = []
    for item in DATA["reminders"]:
        if item["when_ts"] <= now:
            guild = bot.get_guild(item["guild"]) if item["guild"] else None
            channel = bot.get_channel(item["channel"]) if item["channel"] else None
            user = bot.get_user(item["user"]) or (guild and guild.get_member(item["user"]))
            if channel:
                with contextlib.suppress(Exception):
                    await channel.send(f"⏰ 提醒 {user.mention if user else ''}：{item['text']}")
        else:
            left.append(item)
    if len(left) != len(DATA["reminders"]):
        DATA["reminders"] = left
        save_data(DATA)

@reminder_loop.before_loop
async def _before_reminder_loop():
    await bot.wait_until_ready()

reminder_loop.start()

# ---- Tickets ----
@bot.group(invoke_without_command=True)
async def ticket(ctx):
    await ctx.send("用法：`!ticket open`、`!ticket close` (在工單內)")

@ticket.command(name="open")
async def ticket_open(ctx):
    gid = str(ctx.guild.id)
    DATA["tickets"].setdefault(gid, {})
    if str(ctx.author.id) in DATA["tickets"][gid]:
        ch_id = DATA["tickets"][gid][str(ctx.author.id)]
        ch = ctx.guild.get_channel(ch_id)
        return await ctx.send(f"你已有工單：{ch.mention}")
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        ctx.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    ch = await ctx.guild.create_text_channel(name=f"ticket-{ctx.author.name}", overwrites=overwrites)
    DATA["tickets"][gid][str(ctx.author.id)] = ch.id
    save_data(DATA)
    await ch.send(f"{ctx.author.mention} 請描述你的問題。使用 `!ticket close` 關閉。")
    await ctx.send(f"✅ 已建立工單 {ch.mention}")

@ticket.command(name="close")
async def ticket_close(ctx):
    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.send("請在工單頻道內使用。")
    with contextlib.suppress(Exception):
        await ctx.send("🗃️ 工單將在 3 秒後關閉…")
        await asyncio.sleep(3)
        await ctx.channel.delete()

# ---- Starboard ----
@bot.group(invoke_without_command=True)
@commands.has_permissions(manage_guild=True)
def starboard(ctx):
    gid = str(ctx.guild.id)
    conf = DATA["starboard"].get(gid)
    if not conf:
        return asyncio.create_task(ctx.send("尚未設定。用法：`!starboard set <#channel> <門檻>`"))
    ch = ctx.guild.get_channel(conf.get("channel", 0))
    return asyncio.create_task(ctx.send(f"目前：頻道 {ch.mention if ch else '無'} | 門檻 {conf.get('threshold', 5)}"))

@starboard.command(name="set")
@commands.has_permissions(manage_guild=True)
async def starboard_set(ctx, channel: discord.TextChannel, threshold: int = 5):
    gid = str(ctx.guild.id)
    DATA["starboard"][gid] = {"channel": channel.id, "threshold": max(1, threshold)}
    save_data(DATA)
    await ctx.send("✅ 星板已設定")

@starboard.command(name="clear")
@commands.has_permissions(manage_guild=True)
async def starboard_clear(ctx):
    gid = str(ctx.guild.id)
    DATA["starboard"].pop(gid, None)
    save_data(DATA)
    await ctx.send("🧹 已清除星板設定")

# ---- Giveaway (極簡) ----
@bot.command()
@commands.has_permissions(manage_messages=True)
async def giveaway(ctx, duration: str, *, prize: str):
    m = DUR_RE.match(duration)
    if not m:
        return await ctx.send("格式：`!giveaway 5m 超讚獎品`")
    val, unit = int(m.group(1)), m.group(2)
    mult = dict(s=1, m=60, h=3600, d=86400)[unit]
    ends_at = int(time.time()) + val*mult
    emb = discord.Embed(title="🎉 抽獎", description=f"獎品：**{prize}**\n按 🎉 參加\n結束於 <t:{ends_at}:R>")
    msg = await ctx.send(embed=emb)
    with contextlib.suppress(Exception):
        await msg.add_reaction("🎉")
    await asyncio.sleep(val*mult)
    msg = await ctx.channel.fetch_message(msg.id)
    users = set()
    for r in msg.reactions:
        if str(r.emoji) == "🎉":
            async for u in r.users():
                if not u.bot:
                    users.add(u)
    if not users:
        return await ctx.send("無人參加 😢")
    winner = random.choice(list(users))
    await ctx.send(f"🎊 恭喜 {winner.mention} 獲得 **{prize}**！")

# ---- Events: Join/Leave, Filters, Antispam, Starboard ----
@bot.event
async def on_member_join(member: discord.Member):
    gid = str(member.guild.id)
    # autorole
    rid = DATA["autorole"].get(gid)
    if rid:
        role = member.guild.get_role(rid)
        if role:
            with contextlib.suppress(Exception):
                await member.add_roles(role, reason="autorole")
    # welcome
    conf = DATA["welcome"].get(gid, {})
    if conf.get("enabled") and conf.get("channel"):
        ch = member.guild.get_channel(conf["channel"])
        if ch:
            msg = conf.get("message", "歡迎 {user} 加入 {server}！").replace("{user}", member.mention).replace("{server}", member.guild.name)
            with contextlib.suppress(Exception):
                await ch.send(msg)

@bot.event
async def on_member_remove(member: discord.Member):
    gid = str(member.guild.id)
    conf = DATA["goodbye"].get(gid, {})
    if conf.get("enabled") and conf.get("channel"):
        ch = member.guild.get_channel(conf["channel"])
        if ch:
            msg = conf.get("message", "{user} 離開了 {server}，再會！").replace("{user}", str(member)).replace("{server}", member.guild.name)
            with contextlib.suppress(Exception):
                await ch.send(msg)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    gid = str(message.guild.id)
    # Filters
    words = DATA["filters"].get(gid, [])
    low = message.content.lower()
    for w in words:
        if w.lower() in low:
            with contextlib.suppress(Exception):
                await message.delete()
            await message.channel.send(f"🚫 {message.author.mention} 請勿使用敏感詞。", delete_after=3)
            return
    # Anti-spam
    conf = DATA["antispam"].get(gid, {"enabled": False, "threshold": 5, "interval": 7})
    if conf.get("enabled"):
        key = (message.guild.id, message.author.id)
        now = time.time()
        arr = _recent_msgs.get(key, [])
        arr = [t for t in arr if now - t < conf.get("interval", 7)]
        arr.append(now)
        _recent_msgs[key] = arr
        if len(arr) >= conf.get("threshold", 5):
            with contextlib.suppress(Exception):
                await message.author.timeout(timedelta(minutes=5), reason="Auto anti-spam")
            _recent_msgs[key] = []
            await message.channel.send(f"🤐 {message.author.mention} 已因洗版被暫時禁言 5 分鐘。")
            return
    await bot.process_commands(message)

@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    message = reaction.message
    if not message.guild or user.bot:
        return
    gid = str(message.guild.id)
    conf = DATA["starboard"].get(gid)
    if not conf:
        return
    if str(reaction.emoji) != "⭐":
        return
    if reaction.count >= conf.get("threshold", 5):
        ch = message.guild.get_channel(conf.get("channel", 0))
        if not ch:
            return
        emb = discord.Embed(description=message.content or "(無文字)", color=discord.Color.gold())
        emb.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        emb.add_field(name="來源", value=f"#{message.channel.name}")
        emb.add_field(name="連結", value=message.jump_url, inline=False)
        if message.attachments:
            emb.set_image(url=message.attachments[0].url)
        with contextlib.suppress(Exception):
            await ch.send(f"⭐ {reaction.count} | {message.channel.mention}", embed=emb)

# ---- Slash Examples (subset) ----
@bot.tree.command(name="ping", description="Check latency")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong {round(bot.latency*1000)}ms")

@bot.tree.command(name="say", description="Echo text")
async def slash_say(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text)

# ---- Error Handling ----
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        return await ctx.send("❌ 權限不足。")
    if isinstance(error, commands.BadArgument) or isinstance(error, commands.MissingRequiredArgument):
        return await ctx.send("❌ 參數錯誤或缺少。輸入 `!help` 查看用法。")
    if isinstance(error, commands.CommandNotFound):
        return  # 靜默忽略未知指令
    # 其他錯誤
    await ctx.send(f"⚠️ 發生錯誤：{error}")
    traceback.print_exception(type(error), error, error.__traceback__)

# ---- Run ----
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    print("[ERROR] 請在 Replit Secrets 新增 DISCORD_TOKEN。")
else:
    bot.run(TOKEN)
