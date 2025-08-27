import os
import json
import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

# ======================
# Discord 超完整 Bot - main.py
# 使用 Slash Command，狀態 idle
# ======================

# ---------- 設定區 ----------
GUILD_ID = 123456789012345678  # 伺服器 ID
ADMIN_ROLE_ID = 123456789012345678  # 管理員角色 ID
ANNOUNCE_CHANNEL_ID = 123456789012345678  # 公告頻道 ID
OWNER_ID = None  # 限定特權使用者
DATA_DIR = '.'
LEVEL_FILE = os.path.join(DATA_DIR, 'levels.json')
WARN_FILE = os.path.join(DATA_DIR, 'warnings.json')
CURRENCY_FILE = os.path.join(DATA_DIR, 'currency.json')
PERM_FILE = os.path.join(DATA_DIR, 'feature_perms.json')

TOKEN = os.environ.get('DISCORD_TOKEN')
if not TOKEN:
    raise RuntimeError('環境變數 DISCORD_TOKEN 未設定')

# ---------- 工具函式 ----------
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

# ---------- Bot ----------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

state = {
    'levels': load_json(LEVEL_FILE, {}),
    'warnings': load_json(WARN_FILE, {}),
    'currency': load_json(CURRENCY_FILE, {}),
    'feature_perms': load_json(PERM_FILE, {}),
}

# ---------- 權限檢查 ----------
def is_admin_member(member: discord.Member) -> bool:
    if OWNER_ID and member.id == OWNER_ID:
        return True
    return any(role.id == ADMIN_ROLE_ID for role in member.roles)

def require_admin():
    async def predicate(inter: discord.Interaction):
        if is_admin_member(inter.user):
            return True
        await inter.response.send_message('🚫 你沒有管理員權限。', ephemeral=True)
        return False
    return app_commands.check(predicate)

def require_feature_permission():
    async def predicate(inter: discord.Interaction):
        if is_admin_member(inter.user):
            return True
        allowed = state['feature_perms'].get(str(inter.user.id), False)
        if not allowed:
            await inter.response.send_message('🚫 你沒有權限，請聯絡管理員開通。', ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# ---------- on_ready ----------
@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game(f'HFG 服務了 {sum(1 for m in bot.get_guild(GUILD_ID).members if not m.bot)} 人'))
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f'✅ 已同步 {len(synced)} 個 Slash 指令')
    except Exception as e:
        print('❌ 同步失敗:', e)
    print('🟢 Bot 已啟動:', bot.user)

# ---------- 等級系統 ----------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    uid = str(message.author.id)
    state['levels'].setdefault(uid, {'xp':0, 'level':1})
    state['levels'][uid]['xp'] += 10
    xp = state['levels'][uid]['xp']
    lvl = state['levels'][uid]['level']
    if xp >= lvl*100:
        state['levels'][uid]['level'] += 1
        await message.channel.send(f'🎉 {message.author.mention} 升級到 {lvl+1} 級!')
    save_json(LEVEL_FILE, state['levels'])
    await bot.process_commands(message)

# ---------- Slash Command: Help ----------
@bot.tree.command(name='help', description='顯示指令清單', guild=discord.Object(id=GUILD_ID))
async def help_cmd(inter: discord.Interaction):
    cmds = bot.tree.get_commands(guild=discord.Object(id=GUILD_ID))
    lines = [f'/{c.name} — {c.description}' for c in cmds]
    await inter.response.send_message('📜 指令清單:\n' + '\n'.join(lines), ephemeral=True)

# ---------- 管理 ----------
@bot.tree.command(name='clear', description='清除訊息', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def clear(inter: discord.Interaction, amount: app_commands.Range[int,1,200]):
    await inter.response.defer(ephemeral=True)
    deleted = await inter.channel.purge(limit=amount)
    await inter.followup.send(f'🧹 已刪除 {len(deleted)} 則訊息', ephemeral=True)

# ---------- 公告 ----------
@bot.tree.command(name='announce', description='發送公告', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def announce(inter: discord.Interaction, title: str, content: str):
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if not ch:
        await inter.response.send_message('❌ 找不到公告頻道', ephemeral=True)
        return
    embed = discord.Embed(title=title, description=content, color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
    embed.set_footer(text=f'發布人：{inter.user.display_name}')
    await ch.send(embed=embed)
    await inter.response.send_message('✅ 公告已發佈', ephemeral=True)

# ---------- 私訊 ----------
@bot.tree.command(name='dm', description='私訊使用者', guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def dm_cmd(inter: discord.Interaction, member: discord.Member, message: str):
    try:
        await member.send(f'📩 來自 {inter.user.display_name}: {message}')
        await inter.response.send_message(f'✅ 已私訊 {member.display_name}', ephemeral=True)
    except discord.Forbidden:
        await inter.response.send_message('❌ 無法私訊該使用者', ephemeral=True)

# ---------- 經濟 ----------
@bot.tree.command(name='balance', description='查看餘額', guild=discord.Object(id=GUILD_ID))
async def balance(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    uid = str(m.id)
    state['currency'].setdefault(uid, 100)
    save_json(CURRENCY_FILE, state['currency'])
    await inter.response.send_message(f'💰 {m.display_name} 餘額: {state["currency"][uid]}')

# ---------- 娛樂 ----------
@bot.tree.command(name='coinflip', description='擲硬幣', guild=discord.Object(id=GUILD_ID))
async def coinflip(inter: discord.Interaction):
    await inter.response.send_message(f'🪙 {random.choice(["正面","反面"])}')

# ---------- 啟動 ----------
if __name__ == '__main__':
    bot.run(TOKEN)
