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

# JSON files (you chose JSON)
USERS_FILE = os.path.join(DATA_DIR, "users.json")        # stores money/xp/level/tickets
WARN_FILE = os.path.join(DATA_DIR, "warnings.json")    # stores warnings
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
USERS = load_json(USERS_FILE, {})
WARNINGS = load_json(WARN_FILE, {})
FEATURE_PERMS = load_json(PERMS_FILE, {})
DAILY = load_json(DAILY_FILE, {})

# =========================
# Bot setup
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)

# Use CommandTree on the bot object (bot.tree)

# Presence updater
@tasks.loop(minutes=5)
async def update_presence():
    guild = bot.get_guild(GUILD_ID)
    if guild:
        served = guild.member_count
        await bot.change_presence(status=discord.Status.idle,
                                  activity=discord.Game(f"HFG 機器人 服務了{served}人"))


@bot.event
async def on_ready():
    # set initial presence
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
# Utility
# =========================

def ensure_user(uid: str):
    if uid not in USERS:
        USERS[uid] = {"money": 0, "xp": 0, "level": 1, "tickets": 0}


def save_all():
    save_json(USERS_FILE, USERS)
    save_json(WARN_FILE, WARNINGS)
    save_json(PERMS_FILE, FEATURE_PERMS)
    save_json(DAILY_FILE, DAILY)


# =========================
# Slash commands
# =========================

@bot.tree.command(name='help', description='顯示可用指令列表', guild=discord.Object(id=GUILD_ID))
async def help_cmd(inter: discord.Interaction):
    cmds = bot.tree.get_commands(guild=discord.Object(id=GUILD_ID))
    lines = [f"/{c.name} — {c.description}" for c in cmds]
    await inter.response.send_message(''.join(['📜 指令清單:'] + lines), ephemeral=True)


# ----- Economy -----
@bot.tree.command(name='balance', description='查看你的金錢/等級', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def balance(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    uid = str(m.id)
    ensure_user(uid)
    await inter.response.send_message(f'💰 {m.display_name}：{USERS[uid]["money"]} 金幣 | 等級：{USERS[uid]["level"]} | XP：{USERS[uid]["xp"]}')


@bot.tree.command(name='work', description='工作賺錢（掃地/寫作業）', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def work(inter: discord.Interaction):
    uid = str(inter.user.id)
    ensure_user(uid)
    earn = random.randint(20, 150)
    xp = random.randint(5, 30)
    USERS[uid]['money'] += earn
    USERS[uid]['xp'] += xp
    # level up check
    if USERS[uid]['xp'] >= USERS[uid]['level'] * 100:
        USERS[uid]['xp'] -= USERS[uid]['level'] * 100
        USERS[uid]['level'] += 1
        await inter.response.send_message(f'🎉 {inter.user.display_name} 工作獲得 {earn} 金幣、{xp} XP，並升級到 {USERS[uid]["level"]}！')
    else:
        await inter.response.send_message(f'✅ 工作獲得 {earn} 金幣、{xp} XP')
    save_all()


@bot.tree.command(name='daily', description='每日領取獎勵', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def daily(inter: discord.Interaction):
    uid = str(inter.user.id)
    today = datetime.utcnow().date().isoformat()
    last = DAILY.get(uid)
    if last == today:
        await inter.response.send_message('⏳ 今天已領取過每日獎勵', ephemeral=True)
        return
    ensure_user(uid)
    gain = random.randint(80, 200)
    USERS[uid]['money'] += gain
    DAILY[uid] = today
    save_all()
    await inter.response.send_message(f'🎁 已領取每日 {gain} 金幣')


# pay with confirmation buttons
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


# ----- Lottery -----
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
        if roll < 0.03:
            prize = 2000
        elif roll < 0.15:
            prize = 300
        elif roll < 0.5:
            prize = 50
        else:
            prize = 0
        USERS[uid]['money'] += prize
        save_all()
        if prize:
            await inter.response.send_message(f'🎉 恭喜你中獎！獲得 {prize} 金幣', ephemeral=True)
        else:
            await inter.response.send_message('未中獎，下次再試！', ephemeral=True)


@bot.tree.command(name='lottery', description='參加抽獎（按鈕）', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def lottery(inter: discord.Interaction):
    view = LotteryView(cost=10)
    await inter.response.send_message('按下「參加抽獎」按鈕報名（費用 10 金幣）', view=view, ephemeral=True)


# ----- Ticket system -----
class CloseTicketView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=None)
        self.owner_id = owner_id

    @discord.ui.button(label='關閉客服單', style=discord.ButtonStyle.danger)
    async def close_ticket(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id != self.owner_id and not is_admin_member(inter.user):
            await inter.response.send_message('只有開啟者或管理可關閉', ephemeral=True)
            return
        await inter.response.send_message('頻道將在 3 秒後關閉', ephemeral=True)
        await asyncio.sleep(3)
        try:
            await inter.channel.delete(reason=f'客服單關閉 by {inter.user}')
        except Exception:
            await inter.followup.send('關閉失敗，請檢查權限', ephemeral=True)


@bot.tree.command(name='ticket', description='建立客服單（會建立私人頻道）', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def ticket(inter: discord.Interaction, reason: str):
    category = discord.utils.get(inter.guild.categories, name='客服單')
    if not category:
        category = await inter.guild.create_category('客服單')
    overwrites = {
        inter.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        inter.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }
    name = f'ticket-{inter.user.name}'[:90]
    ch = await inter.guild.create_text_channel(name=name, category=category, overwrites=overwrites)
    await ch.send(f'{inter.user.mention} 已建立客服單，原因：{reason}', view=CloseTicketView(inter.user.id))
    await inter.response.send_message(f'✅ 已建立客服單：{ch.mention}', ephemeral=True)


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
    if count >= 5:
        until = datetime.utcnow() + timedelta(minutes=10)
        try:
            await member.edit(communication_disabled_until=until)
            try:
                await member.send('你已被禁言 10 分鐘（累積 5 次警告）。')
            except discord.Forbidden:
                pass
        except Exception:
            await inter.followup.send('❌ 禁言失敗，請確認 bot 權限', ephemeral=True)


@bot.tree.command(name='warnings', description='查看警告記錄（管理）', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def warnings_cmd(inter: discord.Interaction, member: discord.Member):
    uid = str(member.id)
    logs = WARNINGS.get(uid, [])
    if not logs:
        await inter.response.send_message(f'✅ {member.display_name} 沒有任何警告')
    else:
        text = ''.join(logs[-20:])
        await inter.response.send_message(f'⚠️ {member.display_name} 的警告紀錄:{text}', ephemeral=True)


@bot.tree.command(name='reset_warnings', description='重置警告（管理）', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def reset_warnings(inter: discord.Interaction, member: discord.Member):
    uid = str(member.id)
    WARNINGS[uid] = []
    save_all()
    await inter.response.send_message(f'✅ 已重置 {member.display_name} 的警告')


# ----- Announce (embed to fixed channel) -----
@bot.tree.command(name='announce_admin', description='管理員發布公告（只發到指定頻道）', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def announce_admin(inter: discord.Interaction, subject: str, content: str):
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if not ch:
        await inter.response.send_message('❌ 找不到公告頻道', ephemeral=True)
        return
    embed = discord.Embed(title=subject, description=content, color=discord.Color.blurple(), timestamp=datetime.utcnow())
    embed.set_footer(text=f'發布人：{inter.user.display_name} | {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")})')
    await ch.send(embed=embed)
    await inter.response.send_message('✅ 公告已發佈', ephemeral=True)


# ----- DM forward & admin reply flow -----
class AdminReplyModal(discord.ui.Modal, title='回覆用戶'):
    reply = discord.ui.TextInput(label='回覆內容', style=discord.TextStyle.paragraph)

    def __init__(self, target_id: int):
        super().__init__()
        self.target_id = target_id

    async def on_submit(self, inter: discord.Interaction):
        user = bot.get_user(self.target_id)
        if not user:
            await inter.response.send_message('找不到使用者', ephemeral=True)
            return
        try:
            await user.send(f'📬 管理員 {inter.user.display_name} 回覆：{self.reply.value}')
            await inter.response.send_message('✅ 已回覆用戶', ephemeral=True)
        except discord.Forbidden:
            await inter.response.send_message('❌ 無法私訊該用戶', ephemeral=True)


class DMForwardView(discord.ui.View):
    def __init__(self, target_id: int):
        super().__init__(timeout=None)
        self.target_id = target_id

    @discord.ui.button(label='回覆', style=discord.ButtonStyle.primary)
    async def reply_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        if not is_admin_member(inter.user):
            await inter.response.send_message('你沒有權限回覆', ephemeral=True)
            return
        modal = AdminReplyModal(self.target_id)
        await inter.response.send_modal(modal)

    @discord.ui.button(label='中斷對話', style=discord.ButtonStyle.danger)
    async def end_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        if not is_admin_member(inter.user):
            await inter.response.send_message('你沒有權限中斷', ephemeral=True)
            return
        user = bot.get_user(self.target_id)
        if user:
            try:
                await user.send('💬 管理員已中斷對話。')
            except discord.Forbidden:
                pass
        await inter.response.send_message('✅ 已中斷對話', ephemeral=True)


@bot.event
async def on_message(message: discord.Message):
    # ensure commands still processed
    await bot.process_commands(message)

    if message.author.bot:
        return

    # DM -> forward to admin channel with buttons
    if isinstance(message.channel, discord.DMChannel):
        ch = bot.get_channel(DM_FORWARD_CHANNEL_ID)
        if ch:
            embed = discord.Embed(title='用戶私訊轉發', description=message.content, color=discord.Color.green(), timestamp=datetime.utcnow())
            embed.set_author(name=f'{message.author} (ID: {message.author.id})')
            try:
                await ch.send(embed=embed, view=DMForwardView(message.author.id))
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

    # message in guild: XP & currency
    if message.guild and message.author:
        uid = str(message.author.id)
        ensure_user(uid)
        USERS[uid]['xp'] += 5
        USERS[uid]['money'] += random.randint(0, 2)  # passive tiny gain
        # level up
        if USERS[uid]['xp'] >= USERS[uid]['level'] * 100:
            USERS[uid]['xp'] -= USERS[uid]['level'] * 100
            USERS[uid]['level'] += 1
            try:
                await message.channel.send(f'🎉 {message.author.mention} 升級到 {USERS[uid]["level"]} 級！')
            except Exception:
                pass
        save_all()


# ----- Misc entertainment / utilities -----
@bot.tree.command(name='coinflip', description='擲硬幣', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def coinflip(inter: discord.Interaction):
    await inter.response.send_message(f'🪙 {random.choice(["正面","反面"])}')


@bot.tree.command(name='dice', description='擲骰子', guild=discord.Object(id=GUILD_ID))
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
    qs = ['你最怕的是什麼?', '你最後悔的事?', '有沒有暗戀過誰?']
    await inter.response.send_message('🗣️ ' + random.choice(qs))


@bot.tree.command(name='dare', description='大冒險任務', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def dare(inter: discord.Interaction):
    ds = ['在頻道唱一句歌', '發張搞笑自拍（開玩笑）', '用三個表情描述自己']
    await inter.response.send_message('🎯 ' + random.choice(ds))


# ====== Flask (bind port for Render) ======
app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running.'


def run_web():
    app.run(host='0.0.0.0', port=PORT)


# ====== Entrypoint ======
if __name__ == '__main__':
    # start flask thread so Render detects open port
    threading.Thread(target=run_web, daemon=True).start()
    bot.run(TOKEN)
