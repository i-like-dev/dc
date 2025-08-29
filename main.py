# main.py - 超完整整合版（Slash Command Tree / Render: PORT=8080）
# 功能：
# - 私訊轉發（兩按鈕：回覆 / 中斷對話；中斷時清除頻道中對話訊息、保留終止紀錄）
# - /say （「某某某說：」）
# - 經濟系統：/balance /profile /work（掃地/寫作業出題）/daily /pay(含確認) /shop /scratch /lottery
# - 票務系統：/ticket 建立私有客訴頻道 + 關閉按鈕
# - 等級：訊息給 XP，自動升級公告；/level 查看
# - 列表與排行：/leaderboard
# - 管理：/warn /warnings /reset_warnings /timeout（d/h/m/s + 原因）
# - 權限：/grant_feature /revoke_feature（啟用一般使用者可用功能）
# - 公告：/announce_admin（送到固定頻道）
# - DM：/dm（管理員/擁有者可私訊任一成員）
# - 機器人狀態：/set_status /reset_status（僅擁有者）+ 自動顯示服務人數
# - 票券：/ticket_claim（按鈕領票），儲存在 users.json 的 tickets 欄位
# - 娛樂：/coinflip /dice /8ball /truth /dare /joke
# - Render Flask 保活：PORT 環境變數（預設 8080）

import os
import json
import random
import asyncio
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask

# =========================
# Configuration
# =========================
GUILD_ID = 1227929105018912839
ADMIN_ROLE_ID = 1227938559130861578
ANNOUNCE_CHANNEL_ID = 1228485979090718720
DM_FORWARD_CHANNEL_ID = 1410490139297452042
OWNER_ID = 1213418744685273100
PORT = int(os.environ.get("PORT", 8080))
DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)

# JSON files
USERS_FILE = os.path.join(DATA_DIR, "users.json")        # money/xp/level/tickets/items
WARN_FILE = os.path.join(DATA_DIR, "warnings.json")      # warnings logs
PERMS_FILE = os.path.join(DATA_DIR, "feature_perms.json")
DAILY_FILE = os.path.join(DATA_DIR, "daily.json")

# Token
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("環境變數 DISCORD_TOKEN 未設定")

# =========================
# Helper functions for JSON
# =========================

def load_json(path, default):
    try:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, ensure_ascii=False, indent=2)
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# load state
USERS: Dict[str, dict] = load_json(USERS_FILE, {})
WARNINGS: Dict[str, List[str]] = load_json(WARN_FILE, {})
FEATURE_PERMS: Dict[str, bool] = load_json(PERMS_FILE, {})
DAILY: Dict[str, str] = load_json(DAILY_FILE, {})

# 追蹤 DM 轉發會話：使用者 ID -> {"channel": int, "messages": [message_ids]}
DM_SESSIONS: Dict[int, dict] = {}

# =========================
# Bot setup
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)

# Presence updater
@tasks.loop(minutes=5)
async def update_presence():
    guild = bot.get_guild(GUILD_ID)
    served = guild.member_count if guild else 0
    await bot.change_presence(status=discord.Status.idle,
                              activity=discord.Game(f"HFG 機器人 服務了{served}人"))

@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game("HFG 機器人 服務了0人"))
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ 已同步 {len(synced)} 個 Slash 指令 到 guild {GUILD_ID}")
    except Exception as e:
        print("❌ 同步失敗:", e)
    update_presence.start()
    print("🟢 Bot ready:", bot.user)

# =========================
# Permissions / decorators
# =========================

def is_admin_member(member: discord.Member) -> bool:
    if OWNER_ID and member.id == OWNER_ID:
        return True
    return any(r.id == ADMIN_ROLE_ID for r in member.roles)


def require_admin():
    async def pred(inter: discord.Interaction):
        if is_admin_member(inter.user):
            return True
        await inter.response.send_message('🚫 你沒有管理員權限。', ephemeral=True)
        return False
    return app_commands.check(pred)


def require_feature_permission():
    async def pred(inter: discord.Interaction):
        if is_admin_member(inter.user):
            return True
        if FEATURE_PERMS.get(str(inter.user.id), False):
            return True
        await inter.response.send_message('🚫 你沒有權限，請聯絡管理員開通。', ephemeral=True)
        return False
    return app_commands.check(pred)

# =========================
# Utilities
# =========================

def ensure_user(uid: str):
    if uid not in USERS:
        USERS[uid] = {"money": 0, "xp": 0, "level": 1, "tickets": 0, "items": {}}


def save_all():
    save_json(USERS_FILE, USERS)
    save_json(WARN_FILE, WARNINGS)
    save_json(PERMS_FILE, FEATURE_PERMS)
    save_json(DAILY_FILE, DAILY)


def parse_duration(text: str) -> int:
    """將 '1d2h30m15s' 轉為秒數。"""
    total = 0
    num = ''
    units = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}
    for ch in text:
        if ch.isdigit():
            num += ch
        elif ch in units and num:
            total += int(num) * units[ch]
            num = ''
    return total

async def gen_math_questions(n: int) -> List[dict]:
    qs = []
    for _ in range(max(1, min(10, n))):
        a, b = random.randint(1, 99), random.randint(1, 99)
        op = random.choice(['+','-','*'])
        ans = a+b if op=='+' else a-b if op=='-' else a*b
        qs.append({'q': f"{a} {op} {b} = ?", 'a': ans})
    return qs

# =========================
# Slash commands
# =========================

@bot.tree.command(name='help', description='顯示可用指令列表', guild=discord.Object(id=GUILD_ID))
async def help_cmd(inter: discord.Interaction):
    cmds = bot.tree.get_commands(guild=discord.Object(id=GUILD_ID))
    lines = [f"/{c.name} — {c.description}" for c in cmds]
    await inter.response.send_message(''.join(['📜 指令清單:'] + lines), ephemeral=True)

# ----- Economy / Profile -----
@bot.tree.command(name='balance', description='查看你的金錢/等級', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def balance(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    uid = str(m.id)
    ensure_user(uid)
    await inter.response.send_message(f'💰 {m.display_name}：{USERS[uid]["money"]} 金幣 | 等級：{USERS[uid]["level"]} | XP：{USERS[uid]["xp"]}')

@bot.tree.command(name='profile', description='查看個人資料（錢/等級/道具/票券）', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def profile(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    uid = str(m.id)
    ensure_user(uid)
    items = ', '.join([f"{k}x{v}" for k, v in USERS[uid]['items'].items()]) or '無'
    await inter.response.send_message(f"""👤 {m.display_name}
    💰 金幣: {USERS[uid]['money']}
    ⭐ 等級: {USERS[uid]['level']} (XP {USERS[uid]['xp']})
    🎟️ 票券: {USERS[uid]['tickets']}
    🎁 道具: {items}"""
        )

@bot.tree.command(name='leaderboard', description='金錢排行榜（前 10）', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def leaderboard(inter: discord.Interaction):
    data = sorted(USERS.items(), key=lambda kv: kv[1].get('money', 0), reverse=True)[:10]
    lines = []
    for i,(uid,ud) in enumerate(data, start=1):
        member = inter.guild.get_member(int(uid))
        name = member.display_name if member else uid
        lines.append(f"#{i} {name} — {ud.get('money',0)} 金幣")
    await inter.response.send_message(''.join(lines) or '目前沒有資料')

# --- work（掃地/寫作業出題）---
@bot.tree.command(name='work', description='工作賺錢（掃地/寫作業）', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def work(inter: discord.Interaction, questions: int = 0):
    uid = str(inter.user.id)
    ensure_user(uid)
    job = random.choice(['掃地','寫作業'])
    earn = random.randint(20, 150)
    xp = random.randint(5, 30)
    USERS[uid]['money'] += earn
    USERS[uid]['xp'] += xp

    detail = ''
    if job == '寫作業':
        qs = await gen_math_questions(questions if questions>0 else random.randint(3,5))
        detail = "" + ''.join([f"➤ {q['q']} 答案: {q['a']}" for q in qs])
    else:
        # 掃地：有機率重複髒污（演示文字）
        repeat = random.choice([True, False])
        detail = "掃地完成！" + ("（又弄髒了再清一次✔）" if repeat else '')

    levelup = ''
    while USERS[uid]['xp'] >= USERS[uid]['level'] * 100:
        USERS[uid]['xp'] -= USERS[uid]['level'] * 100
        USERS[uid]['level'] += 1
        levelup += f"
🎉 升級到 {USERS[uid]['level']} 級！"

    save_all()
    await inter.response.send_message(f"✅ {inter.user.display_name}{job}獲得 {earn} 金幣、{xp} XP{levelup}{detail}")

# --- daily ---
@bot.tree.command(name='daily', description='每日領取獎勵', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def daily(inter: discord.Interaction):
    uid = str(inter.user.id)
    today = datetime.utcnow().date().isoformat()
    if DAILY.get(uid) == today:
        await inter.response.send_message('⏳ 今天已領取過每日獎勵', ephemeral=True)
        return
    ensure_user(uid)
    gain = random.randint(80, 200)
    USERS[uid]['money'] += gain
    DAILY[uid] = today
    save_all()
    await inter.response.send_message(f'🎁 已領取每日 {gain} 金幣')

# --- pay (含確認按鈕) ---
class PayConfirmView(discord.ui.View):
    def __init__(self, payer: int, target: int, amount: int):
        super().__init__(timeout=60)
        self.payer = payer
        self.target = target
        self.amount = amount

    @discord.ui.button(label='確認轉帳', style=discord.ButtonStyle.green)
    async def confirm(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id != self.payer:
            await inter.response.send_message('只有付款者可按確認', ephemeral=True)
            return
        p = str(self.payer)
        t = str(self.target)
        ensure_user(p)
        ensure_user(t)
        if USERS[p]['money'] < self.amount:
            await inter.response.send_message('餘額不足', ephemeral=True)
            return
        USERS[p]['money'] -= self.amount
        USERS[t]['money'] += self.amount
        save_all()
        await inter.response.edit_message(content=f'✅ 轉帳成功：{self.amount} 金幣 已轉給 <@{self.target}>', view=None)

    @discord.ui.button(label='取消', style=discord.ButtonStyle.red)
    async def cancel(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id != self.payer:
            await inter.response.send_message('只有付款者可按取消', ephemeral=True)
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

# --- lottery / scratch ---
class LotteryView(discord.ui.View):
    def __init__(self, cost=10):
        super().__init__(timeout=None)
        self.cost = cost

    @discord.ui.button(label='參加抽獎', style=discord.ButtonStyle.primary)
    async def join(self, inter: discord.Interaction, button: discord.ui.Button):
        uid = str(inter.user.id)
        ensure_user(uid)
        if USERS[uid]['money'] < self.cost:
            await inter.response.send_message('金幣不足參加抽獎', ephemeral=True)
            return
        USERS[uid]['money'] -= self.cost
        roll = random.random()
        if roll < 0.03: prize = 2000
        elif roll < 0.15: prize = 300
        elif roll < 0.5: prize = 50
        else: prize = 0
        USERS[uid]['money'] += prize
        save_all()
        msg = f'🎉 恭喜你中獎！獲得 {prize} 金幣' if prize else '未中獎，下次再試！'
        await inter.response.send_message(msg, ephemeral=True)

@bot.tree.command(name='lottery', description='參加抽獎', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def lottery(inter: discord.Interaction):
    await inter.response.send_message('按下「參加抽獎」按鈕報名（費用 10 金幣）', view=LotteryView(), ephemeral=True)

@bot.tree.command(name='scratch', description='刮刮樂抽獎（20 金幣/次）', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def scratch(inter: discord.Interaction):
    uid = str(inter.user.id)
    ensure_user(uid)
    cost = 20
    if USERS[uid]['money'] < cost:
        await inter.response.send_message('金幣不足刮刮樂', ephemeral=True)
        return
    USERS[uid]['money'] -= cost
    roll = random.random()
    prize = 1000 if roll < 0.02 else 200 if roll < 0.1 else 50 if roll < 0.4 else 0
    USERS[uid]['money'] += prize
    save_all()
    msg = f'🎉 刮中 {prize} 金幣！' if prize else '😢 沒中獎，下次再試！'
    await inter.response.send_message(msg, ephemeral=True)

# --- shop ---
SHOP_ITEMS = {"VIP卡": 500, "道具A": 150, "道具B": 300, "神秘箱": 1000}

@bot.tree.command(name='shop', description='購買商店道具（/shop item_name）', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def shop(inter: discord.Interaction, item_name: str):
    uid = str(inter.user.id)
    ensure_user(uid)
    if item_name not in SHOP_ITEMS:
        await inter.response.send_message('❌ 商店沒有這個道具', ephemeral=True)
        return
    price = SHOP_ITEMS[item_name]
    if USERS[uid]['money'] < price:
        await inter.response.send_message('❌ 金幣不足購買', ephemeral=True)
        return
    USERS[uid]['money'] -= price
    USERS[uid]['items'][item_name] = USERS[uid]['items'].get(item_name, 0) + 1
    save_all()
    await inter.response.send_message(f'✅ 購買成功！你擁有 {USERS[uid]["items"][item_name]} 個 {item_name}')

# --- level 查看 ---
@bot.tree.command(name='level', description='查看當前等級與 XP', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def level(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    uid = str(m.id)
    ensure_user(uid)
    need = USERS[uid]['level'] * 100
    await inter.response.send_message(f"{m.display_name} 等級 {USERS[uid]['level']}｜XP {USERS[uid]['xp']}/{need}")

# --- tickets 領票按鈕 ---
class TicketClaimView(discord.ui.View):
    @discord.ui.button(label='領取票券', style=discord.ButtonStyle.success)
    async def claim(self, inter: discord.Interaction, button: discord.ui.Button):
        uid = str(inter.user.id)
        ensure_user(uid)
        USERS[uid]['tickets'] += 1
        save_all()
        await inter.response.send_message('🎟️ 已領取 1 張票券！', ephemeral=True)

@bot.tree.command(name='ticket_claim', description='發布領票按鈕（管理）', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def ticket_claim(inter: discord.Interaction, message: str = '點擊按鈕領票'): 
    await inter.response.send_message(message, view=TicketClaimView())

# ----- Warnings & moderation -----
@bot.tree.command(name='warn', description='警告用戶（管理）', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def warn_cmd(inter: discord.Interaction, member: discord.Member, reason: str):
    uid = str(member.id)
    entry = f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} - {reason} - by {inter.user.display_name}"
    WARNINGS.setdefault(uid, []).append(entry)
    save_all()
    count = len(WARNINGS[uid])
    try:
        await member.send(f'⚠️ 你在 {inter.guild.name} 被警告（第 {count} 次）：{reason}')
    except discord.Forbidden:
        pass
    await inter.response.send_message(f'⚠️ 已警告 {member.display_name}（第 {count} 次）')

@bot.tree.command(name='warnings', description='查看警告記錄（管理）', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def warnings_cmd(inter: discord.Interaction, member: discord.Member):
    uid = str(member.id)
    logs = WARNINGS.get(uid, [])
    if not logs:
        await inter.response.send_message(f'✅ {member.display_name} 沒有任何警告')
    else:
        text = '
'.join(logs[-20:])
        await inter.response.send_message(f'⚠️ {member.display_name} 的警告紀錄:
{text}', ephemeral=True)

@bot.tree.command(name='reset_warnings', description='重置警告（管理）', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def reset_warnings(inter: discord.Interaction, member: discord.Member):
    uid = str(member.id)
    WARNINGS[uid] = []
    save_all()
    await inter.response.send_message(f'✅ 已重置 {member.display_name} 的警告')

@bot.tree.command(name='timeout', description='禁言（管理） 例如 /timeout @user 1h30m 違規', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def timeout_cmd(inter: discord.Interaction, member: discord.Member, duration: str, reason: str):
    seconds = parse_duration(duration)
    if seconds <= 0:
        await inter.response.send_message('❌ 時長格式錯誤，例：1d2h30m15s', ephemeral=True)
        return
    until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    try:
        await member.edit(communication_disabled_until=until, reason=reason)
        await inter.response.send_message(f'⏰ 已禁言 {member.display_name} {duration}，原因：{reason}')
    except Exception:
        await inter.response.send_message('❌ 禁言失敗，請確認 BOT 權限/身分組位置', ephemeral=True)

# ----- Announce -----
@bot.tree.command(name='announce_admin', description='管理員發布公告（送到指定頻道）', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def announce_admin(inter: discord.Interaction, subject: str, content: str):
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if not ch:
        await inter.response.send_message('❌ 找不到公告頻道', ephemeral=True)
        return
    embed = discord.Embed(title=subject, description=content, color=discord.Color.blurple(), timestamp=datetime.utcnow())
    embed.set_footer(text=f'發布人：{inter.user.display_name}')
    await ch.send(embed=embed)
    await inter.response.send_message('✅ 公告已發佈', ephemeral=True)

# ----- /dm （管理員/擁有者主動私訊）-----
@bot.tree.command(name='dm', description='管理員/擁有者 私訊用戶', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def dm(inter: discord.Interaction, user: discord.User, message: str):
    try:
        await user.send(f'📩 來自管理員 {inter.user.display_name}：{message}')
        await inter.response.send_message('✅ 已發送私訊', ephemeral=True)
    except discord.Forbidden:
        await inter.response.send_message('❌ 用戶關閉私訊或無法傳送', ephemeral=True)

# ----- /say 讓機器人說話 -----
@bot.tree.command(name='say', description='讓 bot 發送訊息：「某某某說：內容」', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def say_cmd(inter: discord.Interaction, message: str):
    await inter.response.send_message(f'🗣️ {inter.user.display_name}說：{message}')

# ----- 權限開通/撤銷 -----
@bot.tree.command(name='grant_feature', description='開通使用者功能權限（管理）', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def grant_feature(inter: discord.Interaction, member: discord.Member):
    FEATURE_PERMS[str(member.id)] = True
    save_all()
    await inter.response.send_message(f'✅ 已開通 {member.display_name} 的功能權限')

@bot.tree.command(name='revoke_feature', description='撤銷使用者功能權限（管理）', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def revoke_feature(inter: discord.Interaction, member: discord.Member):
    FEATURE_PERMS[str(member.id)] = False
    save_all()
    await inter.response.send_message(f'✅ 已撤銷 {member.display_name} 的功能權限')

# ----- 擁有者：狀態設定/重置 -----
@bot.tree.command(name='set_status', description='(擁有者) 自訂機器人狀態文字', guild=discord.Object(id=GUILD_ID))
async def set_status(inter: discord.Interaction, text: str):
    if inter.user.id != OWNER_ID:
        await inter.response.send_message('🚫 僅擁有者可用', ephemeral=True)
        return
    await bot.change_presence(status=discord.Status.online, activity=discord.Game(text))
    await inter.response.send_message('✅ 已更新狀態文字', ephemeral=True)

@bot.tree.command(name='reset_status', description='(擁有者) 重置機器人狀態為服務人數', guild=discord.Object(id=GUILD_ID))
async def reset_status(inter: discord.Interaction):
    if inter.user.id != OWNER_ID:
        await inter.response.send_message('🚫 僅擁有者可用', ephemeral=True)
        return
    await update_presence()
    await inter.response.send_message('✅ 已重置狀態', ephemeral=True)

# ----- 娛樂 -----
@bot.tree.command(name='coinflip', description='擲硬幣', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def coinflip(inter: discord.Interaction):
    await inter.response.send_message(f'🪙 {random.choice(["正面","反面"])})')

@bot.tree.command(name='dice', description='擲骰子（預設 6 面）', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def dice(inter: discord.Interaction, sides: int = 6):
    sides = max(2, min(120, sides))
    await inter.response.send_message(f'🎲 結果：{random.randint(1, sides)}')

@bot.tree.command(name='8ball', description='神奇八號球', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def eight_ball(inter: discord.Interaction, question: str):
    answers = ['是', '否', '可能', '再問一次', '不確定']
    await inter.response.send_message(f'🎱 Q: {question} A: {random.choice(answers)}')

@bot.tree.command(name='truth', description='真心話題目', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def truth(inter: discord.Interaction):
    qs = ['你最怕的是什麼?', '你最後悔的事?', '有沒有暗戀過誰?', '說一個你最奇怪的小習慣?', '說一個小時候做過的糗事?']
    await inter.response.send_message('🗣️ ' + random.choice(qs))

@bot.tree.command(name='dare', description='大冒險任務', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def dare(inter: discord.Interaction):
    ds = ['在頻道唱一句歌', '發一張表情包', '用三個表情描述自己', '把你的桌面截圖(開玩笑可跳過)', '用注音打一句話']
    await inter.response.send_message('🎯 ' + random.choice(ds))

@bot.tree.command(name='joke', description='來個冷笑話', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def joke(inter: discord.Interaction):
    jokes = ['我最近在減肥，只吃早午餐和晚餐。', '昨天去跑步，結果電腦當機了——因為我按了「Esc」。', '我不是胖，只是對重力比較尊重。']
    await inter.response.send_message(random.choice(jokes))

# ===== DM 轉發（兩按鈕：回覆 / 中斷對話，且中斷時清除訊息） =====
class AdminReplyModal(discord.ui.Modal, title='回覆用戶'):
    reply = discord.ui.TextInput(label='回覆內容', style=discord.TextStyle.paragraph)

    def __init__(self, target_id: int, log_message_id: int):
        super().__init__()
        self.target_id = target_id
        self.log_message_id = log_message_id

    async def on_submit(self, inter: discord.Interaction):
        user = bot.get_user(self.target_id)
        if not user:
            await inter.response.send_message('找不到使用者', ephemeral=True)
            return
        try:
            await user.send(f'📬 管理員 {inter.user.display_name} 回覆：{self.reply.value}')
        except discord.Forbidden:
            await inter.response.send_message('❌ 無法私訊該用戶', ephemeral=True)
            return
        # 在管理頻道建立回覆紀錄（使用 Discord 的回覆功能）
        ch = bot.get_channel(DM_FORWARD_CHANNEL_ID)
        if ch:
            try:
                ref = await ch.fetch_message(self.log_message_id)
                log = await ch.send(content=f'🗨️ {inter.user.mention} 已回覆：{self.reply.value}', reference=ref)
                # 記錄這則訊息以便日後清理
                sess = DM_SESSIONS.get(self.target_id)
                if sess:
                    sess['messages'].append(log.id)
            except Exception:
                pass
        await inter.response.send_message('✅ 已回覆用戶', ephemeral=True)

class DMForwardView(discord.ui.View):
    def __init__(self, target_id: int, log_message_id: int):
        super().__init__(timeout=None)
        self.target_id = target_id
        self.log_message_id = log_message_id

    @discord.ui.button(label='回覆', style=discord.ButtonStyle.primary)
    async def reply_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        if not is_admin_member(inter.user):
            await inter.response.send_message('你沒有權限回覆', ephemeral=True)
            return
        await inter.response.send_modal(AdminReplyModal(self.target_id, self.log_message_id))

    @discord.ui.button(label='中斷對話', style=discord.ButtonStyle.danger)
    async def end_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        if not is_admin_member(inter.user):
            await inter.response.send_message('你沒有權限中斷', ephemeral=True)
            return
        # DM 使用者通知
        user = bot.get_user(self.target_id)
        if user:
            try:
                await user.send('💬 管理員已中斷對話。')
            except discord.Forbidden:
                pass

        # 清理頻道中該會話的所有訊息
        sess = DM_SESSIONS.get(self.target_id)
        ch = bot.get_channel(DM_FORWARD_CHANNEL_ID)
        if sess and ch:
            ids = sess.get('messages', [])
            for mid in ids:
                try:
                    msg = await ch.fetch_message(mid)
                    await msg.delete()
                except Exception:
                    pass
            # 移除會話
            DM_SESSIONS.pop(self.target_id, None)
            # 留下一條紀錄
            try:
                await ch.send(f'⛔ 與 <@{self.target_id}> 的對話已由 {inter.user.mention} 中斷（紀錄保留）。')
            except Exception:
                pass
        await inter.response.send_message('✅ 已中斷對話並清除訊息', ephemeral=True)

@bot.event
async def on_message(message: discord.Message):
    # 先讓指令能運作
    await bot.process_commands(message)

    if message.author.bot:
        return

    # 私訊 -> 轉發到管理頻道
    if isinstance(message.channel, discord.DMChannel):
        ch = bot.get_channel(DM_FORWARD_CHANNEL_ID)
        if ch:
            embed = discord.Embed(title='用戶私訊轉發', description=message.content or '(無文字)', color=discord.Color.green(), timestamp=datetime.utcnow())
            embed.set_author(name=f'{message.author} (ID: {message.author.id})', icon_url=message.author.display_avatar.url if message.author.display_avatar else discord.Embed.Empty)
            try:
                log = await ch.send(embed=embed)
                # 建立/更新會話追蹤
                sess = DM_SESSIONS.setdefault(message.author.id, {"channel": ch.id, "messages": []})
                sess['messages'].append(log.id)
                # 附上按鈕（使用回覆引用功能）
                view_msg = await ch.send(content=f"請使用下方按鈕處理（回覆 / 中斷）", reference=log)
                sess['messages'].append(view_msg.id)
                await view_msg.edit(view=DMForwardView(message.author.id, log.id))

                try:
                    await message.author.send('✅ 已轉發給管理員，請稍候。')
                except discord.Forbidden:
                    pass
            except Exception:
                pass
        else:
            try:
                await message.author.send('管理員頻道未設定，無法轉發。')
            except discord.Forbidden:
                pass
        return

    # 公會內訊息：給 XP & 少量金錢，自動升級公告
    if message.guild and message.author:
        uid = str(message.author.id)
        ensure_user(uid)
        USERS[uid]['xp'] += 5
        USERS[uid]['money'] += random.randint(0, 2)
        leveled = False
        while USERS[uid]['xp'] >= USERS[uid]['level'] * 100:
            USERS[uid]['xp'] -= USERS[uid]['level'] * 100
            USERS[uid]['level'] += 1
            leveled = True
        if leveled:
            try:
                await message.channel.send(f'🎉 {message.author.mention} 升級到 {USERS[uid]["level"]} 級！')
            except Exception:
                pass
        save_all()

# ===== Flask（Render 保活） =====
app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running.'


def run_web():
    app.run(host='0.0.0.0', port=PORT)

# ===== Entrypoint =====
if __name__ == '__main__':
    # 開一條 Flask 執行緒，讓 Render 偵測埠口
    threading.Thread(target=run_web, daemon=True).start()
    bot.run(TOKEN)
