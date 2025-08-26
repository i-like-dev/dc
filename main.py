import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import random
import os
from datetime import datetime, timedelta
import json

# --------------------------- 設定 ---------------------------
TOKEN = os.environ.get('DISCORD_TOKEN')
GUILD_ID = 1227929105018912839
ADMIN_ROLE_ID = 1227938559130861578
ANNOUNCE_CHANNEL_ID = 1228485979090718720

LEVEL_FILE = 'levels.json'
WARN_FILE = 'warnings.json'
CURRENCY_FILE = 'currency.json'

# --------------------------- Bot ---------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)
tree = bot.tree

# --------------------------- JSON 輔助 ---------------------------
def load_json(filename):
    if not os.path.exists(filename):
        return {}
    with open(filename,'r',encoding='utf-8') as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename,'w',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2)

levels = load_json(LEVEL_FILE)
warnings = load_json(WARN_FILE)
currency = load_json(CURRENCY_FILE)

# --------------------------- Bot 狀態 ---------------------------
@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.online, activity=discord.Game('HFG 機器人 ・ 照亮你的生活'))
    guild = discord.Object(id=GUILD_ID)
    await tree.sync(guild=guild)
    print(f'Logged in as {bot.user} - Slash commands synced!')

# --------------------------- 權限檢查 ---------------------------
def is_admin():
    def predicate(interaction: discord.Interaction) -> bool:
        return any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles)
    return app_commands.check(predicate)

# --------------------------- 等級系統 ---------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    uid = str(message.author.id)
    levels.setdefault(uid, {"xp":0,"level":1})
    levels[uid]["xp"] += 10
    xp = levels[uid]["xp"]
    level = levels[uid]["level"]
    if xp >= level*100:
        levels[uid]["level"] += 1
        await message.channel.send(f'🎉 {message.author.mention} 升到等級 {level+1}!')
    save_json(LEVEL_FILE, levels)
    await bot.process_commands(message)

@tree.command(name='level', description='查看等級')
async def level(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    uid = str(member.id)
    data = levels.get(uid, {"xp":0,"level":1})
    await interaction.response.send_message(f'⭐ {member.mention} 等級: {data["level"]}, XP: {data["xp"]}')

# --------------------------- 警告系統 ---------------------------
async def warn_user(member: discord.Member, reason: str, moderator: discord.Member):
    uid = str(member.id)
    warnings[uid] = warnings.get(uid, 0) + 1
    save_json(WARN_FILE, warnings)
    await member.send(f'⚠️ 你被警告 ({warnings[uid]} 次)，原因: {reason}')
    if warnings[uid] >=5:
        try:
            await member.edit(timed_out_until=datetime.utcnow()+timedelta(minutes=10))
            await member.send('⏱ 你已被禁言 10 分鐘')
            warnings[uid] = 0
            save_json(WARN_FILE, warnings)
        except discord.Forbidden:
            pass

@tree.command(name='warn', description='警告用戶')
@is_admin()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    await warn_user(member, reason, interaction.user)
    await interaction.response.send_message(f'✅ 已警告 {member.display_name} ({warnings[str(member.id)]} 次)', ephemeral=True)

@tree.command(name='warnings', description='查看警告紀錄')
@is_admin()
async def check_warnings(interaction: discord.Interaction, member: discord.Member):
    uid = str(member.id)
    count = warnings.get(uid,0)
    await interaction.response.send_message(f'⚠️ {member.display_name} 被警告次數: {count}')

# --------------------------- 權限管理 ---------------------------
@tree.command(name='grant_admin', description='給予管理權限')
@is_admin()
async def grant_admin(interaction: discord.Interaction, member: discord.Member):
    role = discord.utils.get(interaction.guild.roles, id=ADMIN_ROLE_ID)
    await member.add_roles(role)
    await interaction.response.send_message(f'✅ {member.display_name} 已獲得管理權限', ephemeral=True)

@tree.command(name='revoke_admin', description='撤銷管理權限')
@is_admin()
async def revoke_admin(interaction: discord.Interaction, member: discord.Member):
    role = discord.utils.get(interaction.guild.roles, id=ADMIN_ROLE_ID)
    await member.remove_roles(role)
    await interaction.response.send_message(f'✅ {member.display_name} 已撤銷管理權限', ephemeral=True)

# --------------------------- 公告功能 ---------------------------
@tree.command(name='announce', description='管理員發布公告')
@is_admin()
async def announce(interaction: discord.Interaction, title: str, content: str):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    embed = discord.Embed(title=title, description=content, color=discord.Color.blue(), timestamp=datetime.utcnow())
    embed.set_footer(text=f'發布人: {interaction.user.display_name}')
    await channel.send(embed=embed)
    await interaction.response.send_message('✅ 公告已發佈。', ephemeral=True)

# --------------------------- 私訊 ---------------------------
@tree.command(name='dm_user', description='私訊特定用戶')
@is_admin()
async def dm_user(interaction: discord.Interaction, member: discord.Member, message: str):
    try:
        await member.send(f'📩 管理員訊息 ({interaction.user.display_name}): {message}')
        await interaction.response.send_message(f'訊息已發送給 {member.display_name}.', ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message('無法私訊此用戶。', ephemeral=True)

# --------------------------- 客服單 ---------------------------
@tree.command(name='create_ticket', description='開客服單')
async def create_ticket(interaction: discord.Interaction, reason: str):
    category = discord.utils.get(interaction.guild.categories, name='客服單')
    if not category:
        category = await interaction.guild.create_category('客服單')
    overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                  interaction.user: discord.PermissionOverwrite(view_channel=True)}
    ticket = await interaction.guild.create_text_channel(f'ticket-{interaction.user.name}', category=category, overwrites=overwrites)

    view = discord.ui.View()
    async def close_callback(interaction_close):
        await ticket.delete()
    button = discord.ui.Button(label='關閉客服單', style=discord.ButtonStyle.red)
    button.callback = close_callback
    view.add_item(button)
    await ticket.send(f'{interaction.user.mention} 已開啟客服單，原因: {reason}', view=view)
    await interaction.response.send_message(f'✅ 已建立客服單: {ticket.mention}', ephemeral=True)

# --------------------------- 娛樂互動 ---------------------------
fun_prompts = {
    'truth': ['你最怕什麼?', '最近一次說謊是什麼?', '有沒有偷偷喜歡過伺服器裡的人?'],
    'dare': ['在公開頻道唱一首歌', '發一張搞笑自拍', '在聊天區說三次"我是豬"']
}

@tree.command(name='coinflip', description='擲硬幣')
async def coinflip(interaction: discord.Interaction):
    await interaction.response.send_message(f'🪙 硬幣結果: {random.choice(["正面","反面"])}')

@tree.command(name='roll_dice', description='擲骰子')
async def roll_dice(interaction: discord.Interaction, sides: int):
    await interaction.response.send_message(f'🎲 骰子結果: {random.randint(1,sides)}')

@tree.command(name='truth_or_dare', description='真心話大冒險')
async def truth_or_dare(interaction: discord.Interaction):
    choice = random.choice(['真心話','大冒險'])
    prompt = random.choice(fun_prompts['truth'] if choice=='真心話' else fun_prompts['dare'])
    await interaction.response.send_message(f'🎲 {choice}: {prompt}')

@tree.command(name='hug', description='給予擁抱')
async def hug(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f'🤗 {interaction.user.mention} 擁抱了 {member.mention}!')

@tree.command(name='poll', description='建立投票')
async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str):
    embed = discord.Embed(title=f'📊 {question}', description=f'1️⃣ {option1}\n2️⃣ {option2}', color=0x00ff00)
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction('1️⃣')
    await message.add_reaction('2️⃣')
    await interaction.response.send_message('投票已建立!', ephemeral=True)

@tree.command(name='8ball', description='隨機回答問題')
async def eight_ball(interaction: discord.Interaction, question: str):
    responses = ["是的", "不是", "可能", "再問一次", "絕對是", "我不確定"]
    await interaction.response.send_message(f'🎱 問題: {question}\n答案: {random.choice(responses)}')

@tree.command(name='joke', description='隨機笑話')
async def joke(interaction: discord.Interaction):
    jokes = ["我昨天去看牙醫，他說我需要放鬆，所以他給我了一張帳單。", "電腦最怕什麼？當機！", "為什麼數學課很吵？因為大家都在講題。"]
    await interaction.response.send_message(f'😂 {random.choice(jokes)}')

@tree.command(name='userinfo', description='查看用戶資訊')
async def userinfo(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(title=f'{member.display_name} 的資訊', color=0x95a5a6)
    embed.add_field(name='🆔 ID', value=member.id, inline=False)
    embed.add_field(name='📅 加入伺服器', value=member.joined_at.strftime('%Y-%m-%d'), inline=False)
    embed.add_field(name='📝 建立帳號', value=member.created_at.strftime('%Y-%m-%d'), inline=False)
    await interaction.response.send_message(embed=embed)

# --------------------------- 虛擬貨幣 ---------------------------
@tree.command(name='balance', description='查看虛擬貨幣')
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    uid = str(member.id)
    currency.setdefault(uid, 100)
    save_json(CURRENCY_FILE, currency)
    await interaction.response.send_message(f'💰 {member.display_name} 餘額: {currency[uid]}')

@tree.command(name='give', description='轉帳虛擬貨幣')
async def give(interaction: discord.Interaction, member: discord.Member, amount: int):
    giver = str(interaction.user.id)
    receiver = str(member.id)
    currency.setdefault(giver,100)
    currency.setdefault(receiver,100)
    if currency[giver] < amount:
        await interaction.response.send_message('❌ 餘額不足', ephemeral=True)
        return
    currency[giver] -= amount
    currency[receiver] += amount
    save_json(CURRENCY_FILE, currency)
    await interaction.response.send_message(f'✅ {interaction.user.display_name} 已轉 {amount} 給 {member.display_name}')

# --------------------------- 排行榜 ---------------------------
@tree.command(name='leaderboard', description='查看等級排行榜')
async def leaderboard(interaction: discord.Interaction):
    top = sorted(levels.items(), key=lambda x:x[1]["xp"], reverse=True)[:10]
    msg = ""
    for i, (uid, data) in enumerate(top,1):
        user = bot.get_user(int(uid))
        if user:
            msg += f'{i}. {user.display_name} - 等級 {data["level"]}, XP {data["xp"]}\n'
    await interaction.response.send_message(f'🏆 等級排行榜:\n{msg}')

# --------------------------- 啟動 ---------------------------
bot.run(TOKEN)
