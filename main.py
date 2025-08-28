import os
import json
import random
import asyncio
import threading
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask

# =======================
# Configuration
# =======================
GUILD_ID = 1227929105018912839
ADMIN_ROLE_ID = 1227938559130861578
ANNOUNCE_CHANNEL_ID = 1228485979090718720
DM_FORWARD_CHANNEL_ID = 1410490139297452042
OWNER_ID = 1213418744685273100
PORT = int(os.environ.get("PORT", 8080))

DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATA_DIR, "users.json")
WARN_FILE = os.path.join(DATA_DIR, "warnings.json")
PERMS_FILE = os.path.join(DATA_DIR, "feature_perms.json")
DAILY_FILE = os.path.join(DATA_DIR, "daily.json")

TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("環境變數 DISCORD_TOKEN 未設定")

# =======================
# JSON helpers
# =======================

def load_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# load persistent state
USERS = load_json(USERS_FILE, {})          # {user_id: {money, level, xp, tickets}}
WARNINGS = load_json(WARN_FILE, {})        # {user_id: [entries]}
FEATURE_PERMS = load_json(PERMS_FILE, {})  # {user_id: True/False}
DAILY = load_json(DAILY_FILE, {})         # {user_id: 'YYYY-MM-DD'}

# =======================
# Bot setup
# =======================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)

# presence updater task will run every 5 minutes
@bot.event
async def on_ready():
    # set initial presence to idle and the requested game text
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game(f"HFG 機器人 服務了0人"))
    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("✅ Slash commands synced to guild")
    except Exception as e:
        print("⚠️ Sync failed:", e)
    update_presence.start()
    print(f"Bot ready: {bot.user}")


@tasks.loop(minutes=5)
async def update_presence():
    g = bot.get_guild(GUILD_ID)
    if g:
        count = g.member_count
        await bot.change_presence(status=discord.Status.idle, activity=discord.Game(f"HFG 機器人 服務了{count}人"))

# =======================
# Utility functions
# =======================

def ensure_user(uid: str):
    if uid not in USERS:
        USERS[uid] = {"money": 0, "level": 1, "xp": 0, "tickets": 0}


def save_state():
    save_json(USERS_FILE, USERS)
    save_json(WARN_FILE, WARNINGS)
    save_json(PERMS_FILE, FEATURE_PERMS)
    save_json(DAILY_FILE, DAILY)


def is_admin_member(member: discord.Member) -> bool:
    if OWNER_ID and member.id == OWNER_ID:
        return True
    return any(r.id == ADMIN_ROLE_ID for r in member.roles)


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
        if FEATURE_PERMS.get(str(inter.user.id), False):
            return True
        await inter.response.send_message("🚫 你沒有權限，請聯絡管理員開通。", ephemeral=True)
        return False
    return app_commands.check(predicate)

# =======================
# Core Slash Commands
# =======================

@bot.tree.command(name='help', description='顯示可用指令列表', guild=discord.Object(id=GUILD_ID))
async def help_cmd(inter: discord.Interaction):
    cmds = bot.tree.get_commands(guild=discord.Object(id=GUILD_ID))
    lines = [f"/{c.name} — {c.description}" for c in cmds]
    await inter.response.send_message('📜 指令清單:\n' + '\n'.join(lines), ephemeral=True)

# --------- Economy & Daily & Work ---------
@bot.tree.command(name='balance', description='查看你的金錢', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def balance(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    uid = str(m.id)
    ensure_user(uid)
    await inter.response.send_message(f'💰 {m.display_name} 的金錢：{USERS[uid]["money"]}')


@bot.tree.command(name='work', description='工作賺錢（掃地或寫作業）', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def work(inter: discord.Interaction):
    uid = str(inter.user.id)
    ensure_user(uid)
    earn = random.randint(20, 150)
    USERS[uid]['money'] += earn
    USERS[uid]['xp'] += random.randint(5, 25)
    save_state()
    await inter.response.send_message(f'✅ {inter.user.display_name} 工作獲得 {earn} 金幣')


@bot.tree.command(name='daily', description='每日領取獎勵', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def daily(inter: discord.Interaction):
    uid = str(inter.user.id)
    today = datetime.utcnow().date().isoformat()
    last = DAILY.get(uid)
    if last == today:
        await inter.response.send_message('⏳ 你今天已領取過每日獎勵', ephemeral=True)
        return
    ensure_user(uid)
    gain = 100
    USERS[uid]['money'] += gain
    DAILY[uid] = today
    save_state()
    await inter.response.send_message(f'🎁 已領取每日 {gain} 金幣')

# --------- Transfer with confirmation ---------
class PayConfirmView(discord.ui.View):
    def __init__(self, payer_id: int, target_id: int, amount: int):
        super().__init__(timeout=60)
        self.payer_id = payer_id
        self.target_id = target_id
        self.amount = amount

    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.green)
    async def confirm(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id != self.payer_id:
            await inter.response.send_message('只可以付款者本人按確認', ephemeral=True)
            return
        payer = str(self.payer_id)
        target = str(self.target_id)
        if USERS.get(payer, {}).get('money', 0) < self.amount:
            await inter.response.send_message('餘額不足', ephemeral=True)
            return
        USERS[payer]['money'] -= self.amount
        ensure_user(target)
        USERS[target]['money'] += self.amount
        save_state()
        await inter.response.edit_message(content=f'💸 轉帳成功：{self.amount} 金幣 已轉給 <@{self.target_id}>', view=None)

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.red)
    async def cancel(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id != self.payer_id:
            await inter.response.send_message('只可以付款者本人按取消', ephemeral=True)
            return
        await inter.response.edit_message(content='❌ 轉帳已取消', view=None)


@bot.tree.command(name='pay', description='轉帳給他人', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def pay(inter: discord.Interaction, target: discord.Member, amount: int):
    payer = str(inter.user.id)
    ensure_user(payer)
    if amount <= 0:
        await inter.response.send_message('金額需大於 0', ephemeral=True)
        return
    if USERS[payer]['money'] < amount:
        await inter.response.send_message('餘額不足', ephemeral=True)
        return
    view = PayConfirmView(inter.user.id, target.id, amount)
    await inter.response.send_message(f'請確認是否要轉帳 {amount} 金幣 給 {target.display_name}', view=view, ephemeral=True)

# --------- Tickets & Lottery (button-driven) ---------
class LotteryView(discord.ui.View):
    def __init__(self, cost: int = 10):
        super().__init__(timeout=None)
        self.cost = cost

    @discord.ui.button(label='Join Lottery', style=discord.ButtonStyle.primary, custom_id='lottery_join')
    async def join(self, inter: discord.Interaction, button: discord.ui.Button):
        uid = str(inter.user.id)
        ensure_user(uid)
        if USERS[uid]['money'] < self.cost:
            await inter.response.send_message('金幣不足參加抽獎', ephemeral=True)
            return
        USERS[uid]['money'] -= self.cost
        # simple prize
        roll = random.random()
        if roll < 0.05:
            prize = 1000
        elif roll < 0.25:
            prize = 200
        elif roll < 0.6:
            prize = 50
        else:
            prize = 0
        USERS[uid]['money'] += prize
        save_state()
        if prize > 0:
            await inter.response.send_message(f'🎉 恭喜！抽中 {prize} 金幣', ephemeral=True)
        else:
            await inter.response.send_message('未中獎，下次再試', ephemeral=True)


@bot.tree.command(name='lottery', description='參加抽獎（按鈕）', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def lottery_cmd(inter: discord.Interaction):
    view = LotteryView(cost=10)
    await inter.response.send_message('按下 Join Lottery 參加（費用 10 金幣）', view=view, ephemeral=True)

# ticket claim
@bot.tree.command(name='ticket', description='領取票券', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def ticket_cmd(inter: discord.Interaction):
    uid = str(inter.user.id)
    ensure_user(uid)
    USERS[uid]['tickets'] += 1
    save_state()
    await inter.response.send_message('🎟️ 已領取 1 張票券', ephemeral=True)

# --------- Warning system (auto-mute after 5 warnings) ---------
@bot.tree.command(name='warn', description='警告用戶', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def warn_cmd(inter: discord.Interaction, member: discord.Member, reason: str):
    uid = str(member.id)
    entry = f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} - {reason} - by {inter.user.display_name}"
    WARNINGS.setdefault(uid, []).append(entry)
    save_state()
    count = len(WARNINGS[uid])
    # DM user
    try:
        await member.sen
