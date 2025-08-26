import discord
from discord import app_commands
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

# --------------------------- Bot ---------------------------
class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents, loop=asyncio.get_event_loop())
        self.tree = app_commands.CommandTree(self)
        self.levels = {}
        self.warnings = {}
        try:
            with open(LEVEL_FILE,'r',encoding='utf-8') as f:
                self.levels = json.load(f)
        except:
            self.levels = {}
        try:
            with open(WARN_FILE,'r',encoding='utf-8') as f:
                self.warnings = json.load(f)
        except:
            self.warnings = {}

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        await self.tree.sync(guild=guild)
        print("✅ Slash commands synced to the guild!")

    def save_json(self, filename, data):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

bot = MyBot()

# --------------------------- Bot 狀態 ---------------------------
@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.online, activity=discord.Game('HFG 機器人 ・ 照亮你的生活'))
    print(f'Logged in as {bot.user}')

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
    bot.levels.setdefault(uid, {"xp":0, "level":1})
    bot.levels[uid]["xp"] += 10
    xp = bot.levels[uid]["xp"]
    level = bot.levels[uid]["level"]
    if xp >= level*100:
        bot.levels[uid]["level"] += 1
        await message.channel.send(f'🎉 {message.author.mention} 升到等級 {level+1}!')
    bot.save_json(LEVEL_FILE, bot.levels)
    await bot.process_commands(message)

@bot.tree.command(name='level', description='查看等級')
async def level(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    uid = str(member.id)
    data = bot.levels.get(uid, {"xp":0,"level":1})
    await interaction.response.send_message(f'⭐ {member.mention} 等級: {data["level"]}, XP: {data["xp"]}')

# --------------------------- 警告系統 ---------------------------
async def warn_user(member: discord.Member, reason: str, moderator: discord.Member):
    uid = str(member.id)
    bot.warnings[uid] = bot.warnings.get(uid, 0) + 1
    bot.save_json(WARN_FILE, bot.warnings)
    await member.send(f'⚠️ 你被警告 ({bot.warnings[uid]} 次)，原因: {reason}')
    if bot.warnings[uid] >= 5:
        try:
            await member.edit(timed_out_until=datetime.utcnow()+timedelta(minutes=10))
            await member.send('⏱ 你已被禁言 10 分鐘')
            bot.warnings[uid] = 0
            bot.save_json(WARN_FILE, bot.warnings)
        except discord.Forbidden:
            pass

@bot.tree.command(name='warn', description='警告用戶')
@is_admin()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    await warn_user(member, reason, interaction.user)
    await interaction.response.send_message(f'✅ 已警告 {member.display_name} ({bot.warnings[str(member.id)]} 次)', ephemeral=True)

# --------------------------- 權限管理 ---------------------------
@bot.tree.command(name='grant_admin', description='給予管理權限')
@is_admin()
async def grant_admin(interaction: discord.Interaction, member: discord.Member):
    role = discord.utils.get(interaction.guild.roles, id=ADMIN_ROLE_ID)
    await member.add_roles(role)
    await interaction.response.send_message(f'✅ {member.display_name} 已獲得管理權限', ephemeral=True)

@bot.tree.command(name='revoke_admin', description='撤銷管理權限')
@is_admin()
async def revoke_admin(interaction: discord.Interaction, member: discord.Member):
    role = discord.utils.get(interaction.guild.roles, id=ADMIN_ROLE_ID)
    await member.remove_roles(role)
    await interaction.response.send_message(f'✅ {member.display_name} 已撤銷管理權限', ephemeral=True)

# --------------------------- 公告功能 ---------------------------
@bot.tree.command(name='announce', description='管理員發布公告')
@is_admin()
async def announce(interaction: discord.Interaction, title: str, content: str):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    embed = discord.Embed(title=title, description=content, color=discord.Color.blue(), timestamp=datetime.utcnow())
    embed.set_footer(text=f'發布人: {interaction.user.display_name}')
    await channel.send(embed=embed)
    await interaction.response.send_message('✅ 公告已發佈。', ephemeral=True)

# --------------------------- 私訊功能 ---------------------------
@bot.tree.command(name='dm_user', description='私訊特定用戶')
@is_admin()
async def dm_user(interaction: discord.Interaction, member: discord.Member, message: str):
    try:
        await member.send(f'📩 管理員訊息 ({interaction.user.display_name}): {message}')
        await interaction.response.send_message(f'訊息已發送給 {member.display_name}.', ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message('無法私訊此用戶。', ephemeral=True)

# --------------------------- 客服單 ---------------------------
@bot.tree.command(name='create_ticket', description='開客服單')
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

# --------------------------- 娛樂/互動功能 ---------------------------
fun_prompts = {
    'truth': ['你最怕什麼?', '最近一次說謊是什麼?', '有沒有偷偷喜歡過伺服器裡的人?'],
    'dare': ['在公開頻道唱一首歌', '發一張搞笑自拍', '在聊天區說三次"我是豬"']
}

@bot.tree.command(name='coinflip', description='擲硬幣')
async def coinflip(interaction: discord.Interaction):
    await interaction.response.send_message(f'🪙 硬幣結果: {random.choice(["正面","反面"])}')

@bot.tree.command(name='roll_dice', description='擲骰子')
async def roll_dice(interaction: discord.Interaction, sides: int):
    await interaction.response.send_message(f'🎲 骰子結果: {random.randint(1,sides)}')

@bot.tree.command(name='truth_or_dare', description='真心話大冒險')
async def truth_or_dare(interaction: discord.Interaction):
    choice = random.choice(['真心話','大冒險'])
    prompt = random.choice(fun_prompts['truth'] if choice=='真心話' else fun_prompts['dare'])
    await interaction.response.send_message(f'🎲 {choice}: {prompt}')

@bot.tree.command(name='hug', description='給予擁抱')
async def hug(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f'🤗 {interaction.user.mention} 擁抱了 {member.mention}!')

@bot.tree.command(name='8ball', description='隨機回答問題')
async def eight_ball(interaction: discord.Interaction, question: str):
    responses = ["是的", "不是", "可能", "再問一次", "絕對是", "我不確定"]
    await interaction.response.send_message(f'🎱 問題: {question}\n答案: {random.choice(responses)}')

@bot.tree.command(name='joke', description='隨機笑話')
async def joke(interaction: discord.Interaction):
    jokes = ["我昨天去看牙醫，他說我需要放鬆，所以他給我了一張帳單。", "電腦最怕什麼？當機！", "為什麼數學課很吵？因為大家都在講題。"]
    await interaction.response.send_message(f'😂 {random.choice(jokes)}')

@bot.tree.command(name='quote', description='隨機勵志語錄')
async def quote(interaction: discord.Interaction):
    quotes = ["成功不是終點，失敗也不是末日，最重要的是勇氣。", "保持微笑，世界會因你而更美好。", "每天進步一點點，就是成功的一大步。"]
    await interaction.response.send_message(f'💡 {random.choice(quotes)}')

# --------------------------- 啟動 Bot ---------------------------
bot.run(TOKEN, host='0.0.0.0')
