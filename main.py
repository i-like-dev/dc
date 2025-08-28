import os
import json
import random
import asyncio
from datetime import datetime, timedelta, timezone
import threading

import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask

# ===================== 基本設定 =====================
GUILD_ID = 1227929105018912839
ADMIN_ROLE_ID = 1227938559130861578
ANNOUNCE_CHANNEL_ID = 1228485979090718720
OWNER_ID = 1213418744685273100

DATA_DIR = "."
LEVEL_FILE = os.path.join(DATA_DIR, "levels.json")
WARN_FILE = os.path.join(DATA_DIR, "warnings.json")
CURRENCY_FILE = os.path.join(DATA_DIR, "currency.json")
PERM_FILE = os.path.join(DATA_DIR, "feature_perms.json")
TICKET_FILE = os.path.join(DATA_DIR, "tickets.json")

TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("環境變數 DISCORD_TOKEN 未設定")

# ===================== JSON 工具 =====================
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ===================== Bot & 狀態 =====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

state = {
    "levels": load_json(LEVEL_FILE, {}),
    "warnings": load_json(WARN_FILE, {}),
    "currency": load_json(CURRENCY_FILE, {}),
    "feature_perms": load_json(PERM_FILE, {}),
    "guess_games": {},
    "tickets": load_json(TICKET_FILE, {}),
}

# ===================== 權限判斷 =====================
def is_admin_member(member: discord.Member):
    if member.id == OWNER_ID:
        return True
    return any(role.id == ADMIN_ROLE_ID for role in member.roles)

def require_admin():
    async def predicate(inter: discord.Interaction):
        if is_admin_member(inter.user):
            return True
        await inter.response.send_message("🚫 你沒有管理員權限。", ephemeral=True)
        return False
    return app_commands.check(predicate)

def require_feature_permission():
    async def predicate(inter: discord.Interaction):
        if is_admin_member(inter.user):
            return True
        allowed = state["feature_perms"].get(str(inter.user.id), False)
        if not allowed:
            await inter.response.send_message("🚫 你沒有權限，請聯絡管理員開通。", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# ===================== on_ready / Slash 同步 / 狀態更新 =====================
@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game("HFG 機器人 服務了0人"))
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ 已同步 {len(synced)} 個 Slash 指令")
    except Exception as e:
        print("❌ 同步失敗:", e)
    update_presence.start()
    print("🟢 Bot 已啟動:", bot.user)

@tasks.loop(minutes=5)
async def update_presence():
    guild = bot.get_guild(GUILD_ID)
    if guild:
        served = guild.member_count
        await bot.change_presence(status=discord.Status.idle, activity=discord.Game(f"HFG 機器人 服務了{served}人"))

# ===================== 等級系統 =====================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # 等級
    if message.guild:
        uid = str(message.author.id)
        lv = state["levels"].setdefault(uid, {"xp": 0, "level": 1})
        lv["xp"] += 10
        if lv["xp"] >= lv["level"] * 100:
            lv["level"] += 1
            try:
                await message.channel.send(f"🎉 {message.author.mention} 升級到 {lv['level']} 級!")
            except Exception:
                pass
        save_json(LEVEL_FILE, state["levels"])

        # 猜數字
        ans = state["guess_games"].get(message.channel.id)
        if ans and message.content.isdigit():
            n = int(message.content)
            if n == ans:
                await message.channel.send(f"🎉 {message.author.mention} 猜對了！答案就是 {ans}")
                del state["guess_games"][message.channel.id]
            elif n < ans:
                await message.channel.send("太小了！")
            else:
                await message.channel.send("太大了！")

    await bot.process_commands(message)

# ===================== /help =====================
@bot.tree.command(name="help", description="顯示可用指令清單", guild=discord.Object(id=GUILD_ID))
async def help_cmd(inter: discord.Interaction):
    cmds = bot.tree.get_commands(guild=discord.Object(id=GUILD_ID))
    lines = [f"/{c.name} — {c.description}" for c in cmds]
    text = "📜 指令清單:\n" + "\n".join(lines)
    await inter.response.send_message(text, ephemeral=True)

# ===================== 管理員指令 =====================
@bot.tree.command(name="clear", description="清除訊息（1-200）", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def clear(inter: discord.Interaction, amount: app_commands.Range[int,1,200]):
    await inter.response.defer(ephemeral=True)
    deleted = await inter.channel.purge(limit=amount)
    await inter.followup.send(f"🧹 已刪除 {len(deleted)} 則訊息", ephemeral=True)

@bot.tree.command(name="kick", description="踢出成員", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def kick(inter: discord.Interaction, member: discord.Member, reason: str = "無理由"):
    await member.kick(reason=reason)
    await inter.response.send_message(f"👢 {member.display_name} 已被踢出（{reason}）")

@bot.tree.command(name="ban", description="封鎖成員", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def ban(inter: discord.Interaction, member: discord.Member, reason: str = "無理由"):
    await member.ban(reason=reason)
    await inter.response.send_message(f"⛔ {member.display_name} 已被封鎖（{reason}）")

@bot.tree.command(name="unban", description="解除封鎖（輸入使用者 ID）", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def unban(inter: discord.Interaction, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await inter.guild.unban(user)
        await inter.response.send_message(f"✅ 已解除封鎖：{user}")
    except Exception:
        await inter.response.send_message("❌ 解除封鎖失敗，請確認 ID")

@bot.tree.command(name="mute", description="禁言用戶（秒）", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def mute(inter: discord.Interaction, member: discord.Member, seconds: app_commands.Range[int,10,604800]):
    until = datetime.now(timezone.utc) + timedelta(seconds=int(seconds))
    await member.edit(communication_disabled_until=until)
    await inter.response.send_message(f"🔇 {member.display_name} 已被禁言 {seconds} 秒")

@bot.tree.command(name="unmute", description="解除禁言", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def unmute(inter: discord.Interaction, member: discord.Member):
    await member.edit(communication_disabled_until=None)
    await inter.response.send_message(f"🔊 {member.display_name} 已解除禁言")

@bot.tree.command(name="slowmode", description="設定頻道慢速模式（秒，0 代表關閉）", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def slowmode(inter: discord.Interaction, seconds: app_commands.Range[int,0,21600]):
    await inter.channel.edit(slowmode_delay=seconds)
    await inter.response.send_message(f"🐢 已設定慢速模式：{seconds} 秒")

@bot.tree.command(name="nick", description="修改成員暱稱", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def nick(inter: discord.Interaction, member: discord.Member, new_nick: str):
    await member.edit(nick=new_nick)
    await inter.response.send_message(f"✏️ {member.display_name} 的暱稱已改為 {new_nick}")

# ===================== 經濟 / 等級 / 權限 / 票務管理 =====================
@bot.tree.command(name="manage_currency", description="管理使用者貨幣", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def manage_currency(inter: discord.Interaction, user: discord.Member, amount: int):
    uid = str(user.id)
    state["currency"][uid] = state["currency"].get(uid, 0) + amount
    save_json(CURRENCY_FILE, state["currency"])
    await inter.response.send_message(f"✅ {user.mention} 的餘額已更新為 {state['currency'][uid]}")

@bot.tree.command(name="manage_level", description="管理使用者等級", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def manage_level(inter: discord.Interaction, user: discord.Member, level: int):
    uid = str(user.id)
    state["levels"][uid] = state["levels"].get(uid, {"xp":0,"level":1})
    state["levels"][uid]["level"] = level
    save_json(LEVEL_FILE, state["levels"])
    await inter.response.send_message(f"✅ {user.mention} 的等級已設定為 {level}")

@bot.tree.command(name="manage_warning", description="管理使用者警告", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def manage_warning(inter: discord.Interaction, user: discord.Member, add: int = 1):
    uid = str(user.id)
    state["warnings"][uid] = state["warnings"].get(uid, 0) + add
    save_json(WARN_FILE, state["warnings"])
    await inter.response.send_message(f"⚠️ {user.mention} 現在有 {state['warnings'][uid]} 次警告")

@bot.tree.command(name="toggle_feature", description="開啟或關閉使用者功能權限", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def toggle_feature(inter: discord.Interaction, user: discord.Member, enable: bool):
    state["feature_perms"][str(user.id)] = enable
    save_json(PERM_FILE, state["feature_perms"])
    await inter.response.send_message(f"✅ {user.mention} 功能權限已 {'開啟' if enable else '關閉'}")

@bot.tree.command(name="manage_ticket", description="管理票券（重置擁有者）", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def manage_ticket(inter: discord.Interaction, ticket_id: str, user: discord.Member = None):
    ticket = state["tickets"].get(ticket_id)
    if not ticket:
        await inter.response.send_message("❌ 找不到票券", ephemeral=True)
        return
    ticket["owner"] = str(user.id) if user else None
    save_json(TICKET_FILE, state["tickets"])
    await inter.response.send_message(f"🎫 票券 {ticket['name']} (ID:{ticket_id}) 已更新擁有者")

# ===================== 猜數字指令 =====================
@bot.tree.command(name="guess_number", description="開始猜數字遊戲", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def guess_number(inter: discord.Interaction, max_number: int = 100):
    state["guess_games"][inter.channel.id] = random.randint(1, max_number)
    await inter.response.send_message(f"🎲 已開始猜數字遊戲（1~{max_number}），快猜吧！")

# ===================== 測試 / Ping =====================
@bot.tree.command(name="ping", description="機器人延遲測試", guild=discord.Object(id=GUILD_ID))
async def ping(inter: discord.Interaction):
    await inter.response.send_message(f"🏓 Pong! 延遲: {round(bot.latency*1000)}ms")

# ===================== Flask 監控 =====================
app = Flask("")

@app.route("/")
def home():
    return "Bot is running."

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask).start()

# ===================== 啟動 Bot =====================
bot.run(TOKEN)
