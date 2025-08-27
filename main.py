import os
import json
import random
import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

# ---------- 設定 ----------
GUILD_ID = 123456789012345678  # 你的伺服器 ID
ADMIN_ROLE_ID = 123456789012345678  # 管理員角色 ID
ANNOUNCE_CHANNEL_ID = 123456789012345678  # 公告頻道 ID
OWNER_ID = None  # Bot 擁有者 Discord ID，如果沒有填 None

DATA_DIR = '.'
LEVEL_FILE = os.path.join(DATA_DIR, 'levels.json')
WARN_FILE = os.path.join(DATA_DIR, 'warnings.json')
CURRENCY_FILE = os.path.join(DATA_DIR, 'currency.json')
PERM_FILE = os.path.join(DATA_DIR, 'feature_perms.json')
REMINDER_FILE = os.path.join(DATA_DIR, 'reminders.json')

TOKEN = os.environ.get('DISCORD_TOKEN')
if not TOKEN:
    raise RuntimeError('DISCORD_TOKEN 未設定')

# ---------- JSON 工具 ----------
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- Bot 與 State ----------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

state = {
    'levels': load_json(LEVEL_FILE, {}),
    'warnings': load_json(WARN_FILE, {}),
    'currency': load_json(CURRENCY_FILE, {}),
    'feature_perms': load_json(PERM_FILE, {}),
    'reminders': load_json(REMINDER_FILE, {}),
    'guess_games': {},
}

# ---------- 權限判斷 ----------
def is_admin(member: discord.Member):
    if OWNER_ID and member.id == OWNER_ID:
        return True
    return any(role.id == ADMIN_ROLE_ID for role in member.roles)

def require_admin():
    async def pred(inter: discord.Interaction):
        if is_admin(inter.user):
            return True
        await inter.response.send_message('🚫 你沒有管理員權限', ephemeral=True)
        return False
    return app_commands.check(pred)

def require_feature():
    async def pred(inter: discord.Interaction):
        if is_admin(inter.user):
            return True
        allowed = state['feature_perms'].get(str(inter.user.id), False)
        if not allowed:
            await inter.response.send_message('🚫 你沒有權限，請聯絡管理員開通', ephemeral=True)
            return False
        return True
    return app_commands.check(pred)

# ---------- on_ready ----------
@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game('SuperBot 24/7'))
    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f'✅ Slash Commands 已同步到 Guild {GUILD_ID}')
    except Exception as e:
        print('❌ 同步失敗:', e)
    print('🟢 Bot 已啟動：', bot.user)

# ---------- 等級系統 ----------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    uid = str(message.author.id)
    state['levels'].setdefault(uid, {'xp':0,'level':1})
    state['levels'][uid]['xp'] += 10
    lvl = state['levels'][uid]['level']
    xp = state['levels'][uid]['xp']
    if xp >= lvl*100:
        state['levels'][uid]['level'] += 1
        await message.channel.send(f'🎉 {message.author.mention} 升到等級 {lvl+1}!')
    save_json(LEVEL_FILE, state['levels'])
    await bot.process_commands(message)

# ---------- Reminder Task ----------
@tasks.loop(seconds=60)
async def reminder_task():
    now = datetime.now(timezone.utc).timestamp()
    to_remove = []
    for uid, reminders in state['reminders'].items():
        for r in reminders:
            if now >= r['time']:
                user = bot.get_user(int(uid))
                if user:
                    try:
                        await user.send(f'⏰ 提醒：{r["message"]}')
                    except:
                        pass
                to_remove.append((uid,r))
    for uid,r in to_remove:
        state['reminders'][uid].remove(r)
    save_json(REMINDER_FILE, state['reminders'])

@reminder_task.before_loop
async def before_reminder():
    await bot.wait_until_ready()

reminder_task.start()

# ---------- Slash Commands ----------

# /help
@bot.tree.command(name='help', description='顯示指令清單', guild=discord.Object(id=GUILD_ID))
async def help_cmd(inter: discord.Interaction):
    cmds = bot.tree.get_commands(guild=discord.Object(id=GUILD_ID))
    lines = [f"/{c.name} — {c.description or '無'}" for c in cmds]
    await inter.response.send_message('📜 指令清單:\n' + '\n'.join(lines), ephemeral=True)

# ---------- 權限管理 ----------
@bot.tree.command(name='grant', description='授權功能權限', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def grant(inter: discord.Interaction, member: discord.Member):
    state['feature_perms'][str(member.id)] = True
    save_json(PERM_FILE, state['feature_perms'])
    await inter.response.send_message(f'✅ {member.display_name} 已被授權功能', ephemeral=True)

@bot.tree.command(name='revoke', description='撤銷功能權限', guild=discord.Object(id=GUILD_ID))
@require_admin()
async def revoke(inter: discord.Interaction, member: discord.Member):
    state['feature_perms'][str(member.id)] = False
    save_json(PERM_FILE, state['feature_perms'])
    await inter.response.send_message(f'✅ {member.display_name} 功能權限已撤銷', ephemeral=True)

# ---------- 公告 / DM / Ticket ----------
@bot.tree.command(name='announce', description='發布公告', guild=discord.Object(id=GUILD_ID))
@require_feature()
async def announce(inter: discord.Interaction, title: str, content: str):
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if not ch:
        await inter.response.send_message('❌ 找不到公告頻道', ephemeral=True)
        return
    embed = discord.Embed(title=title, description=content, color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
    embed.set_footer(text=f'發布人：{inter.user.display_name}')
    await ch.send(embed=embed)
    await inter.response.send_message('✅ 公告已發佈', ephemeral=True)

@bot.tree.command(name='dm', description='私訊使用者', guild=discord.Object(id=GUILD_ID))
@require_feature()
async def dm(inter: discord.Interaction, member: discord.Member, message: str):
    try:
        await member.send(f'📩 {inter.user.display_name}：{message}')
        await inter.response.send_message(f'✅ 已私訊 {member.display_name}', ephemeral=True)
    except discord.Forbidden:
        await inter.response.send_message('❌ 無法私訊該使用者', ephemeral=True)

# ---------- 客服單 ----------
class TicketView(discord.ui.View):
    def __init__(self, channel_id:int):
        super().__init__(timeout=None)
        self.channel_id = channel_id
    @discord.ui.button(label='關閉客服單', style=discord.ButtonStyle.danger)
    async def close_button(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.channel.id == self.channel_id:
            await inter.channel.delete()
            await inter.response.send_message('客服單已關閉', ephemeral=True)
        else:
            await inter.response.send_message('此按鈕僅限客服單頻道', ephemeral=True)

@bot.tree.command(name='ticket', description='開啟客服單', guild=discord.Object(id=GUILD_ID))
async def ticket(inter: discord.Interaction, reason: str):
    category = discord.utils.get(inter.guild.categories, name='客服單')
    if not category:
        category = await inter.guild.create_category('客服單')
    overwrites = {inter.guild.default_role: discord.PermissionOverwrite(view_channel=False), inter.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
    ch = await inter.guild.create_text_channel(f'ticket-{inter.user.name}', category=category, overwrites=overwrites)
    await ch.send(f'{inter.user.mention} 開啟客服單，原因：{reason}', view=TicketView(ch.id))
    await inter.response.send_message(f'✅ 客服單已建立：{ch.mention}', ephemeral=True)

# ---------- 娛樂 / 工具 ----------
@bot.tree.command(name='coinflip', description='擲硬幣', guild=discord.Object(id=GUILD_ID))
async def coinflip(inter: discord.Interaction):
    await inter.response.send_message(f'🪙 {random.choice(["正面","反面"])}')

@bot.tree.command(name='roll', description='擲骰子', guild=discord.Object(id=GUILD_ID))
async def roll(inter: discord.Interaction, sides: app_commands.Range[int,2,100]):
    await inter.response.send_message(f'🎲 {random.randint(1,sides)}')

@bot.tree.command(name='hug', description='擁抱', guild=discord.Object(id=GUILD_ID))
async def hug(inter: discord.Interaction, member: discord.Member):
    await inter.response.send_message(f'🤗 {inter.user.mention} 擁抱 {member.mention}')

@bot.tree.command(name='8ball', description='魔法 8 球', guild=discord.Object(id=GUILD_ID))
async def eight_ball(inter: discord.Interaction, question: str):
    responses = ["是的", "不", "可能吧", "不確定", "當然！", "絕不"]
    await inter.response.send_message(f'🎱 問題: {question}\n答案: {random.choice(responses)}')

@bot.tree.command(name='palindrome', description='檢查回文', guild=discord.Object(id=GUILD_ID))
async def palindrome(inter: discord.Interaction, text: str):
    cleaned = ''.join(c.lower() for c in text if c.isalnum())
    await inter.response.send_message(f'✅ {text} 是回文' if cleaned == cleaned[::-1] else f'❌ {text} 不是回文')

# ---------- 經濟 ----------
@bot.tree.command(name='balance', description='查看餘額', guild=discord.Object(id=GUILD_ID))
async def balance(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    uid = str(m.id)
    state['currency'].setdefault(uid, 100)
    save_json(CURRENCY_FILE, state['currency'])
    await inter.response.send_message(f'💰 {m.display_name} 餘額：{state["currency"][uid]}')

@bot.tree.command(name='give', description='轉帳', guild=discord.Object(id=GUILD_ID))
async def give(inter: discord.Interaction, member: discord.Member, amount: app_commands.Range[int,1,1000000]):
    giver = str(inter.user.id)
    recv = str(member.id)
    state['currency'].setdefault(giver,100)
    state['currency'].setdefault(recv,100)
    if state['currency'][giver]<amount:
        await int
