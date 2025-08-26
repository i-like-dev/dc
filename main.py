import discord
from discord import app_commands
import asyncio
import random
import os
from datetime import datetime, timedelta, timezone
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
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.levels = {}
        self.warnings = {}
        self.rpg_players = {}
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
            await member.edit(timed_out_until=datetime.now(timezone.utc)+timedelta(minutes=10))
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

@bot.tree.command(name='warnings', description='查看警告紀錄')
@is_admin()
async def warnings(interaction: discord.Interaction, member: discord.Member):
    warns = bot.warnings.get(str(member.id), 0)
    await interaction.response.send_message(f'⚠️ {member.display_name} 警告次數: {warns}')

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
    embed = discord.Embed(title=title, description=content, color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
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

# --------------------------- 娛樂互動 ---------------------------
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

# --------------------------- RPG / 遊戲系統 ---------------------------
cards = ["火焰龍", "冰雪精靈", "雷電鳥", "光明天使", "暗影刺客"]

@bot.tree.command(name='adventure', description='進行一次冒險，獲得 XP 和金幣')
async def adventure(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    player = bot.rpg_players.setdefault(uid, {"xp":0, "gold":0})
    xp_gained = random.randint(5, 20)
    gold_gained = random.randint(1, 10)
    player["xp"] += xp_gained
    player["gold"] += gold_gained
    await interaction.response.send_message(f"🗡 {interaction.user.mention} 進行冒險!\n獲得 XP: {xp_gained}, 金幣: {gold_gained}")

@bot.tree.command(name='roll_dice_game', description='與 Bot 掷骰子遊戲，數字大者勝')
async def roll_dice_game(interaction: discord.Interaction, sides: int = 6):
    user_roll = random.randint(1,sides)
    bot_roll = random.randint(1,sides)
    if user_roll > bot_roll:
        result = "你贏了！🎉"
    elif user_roll < bot_roll:
        result = "Bot 贏了！🤖"
    else:
        result = "平手！"
    await interaction.response.send_message(f"{interaction.user.mention} 掷 {user_roll}, Bot 掷 {bot_roll} -> {result}")

@bot.tree.command(name='draw_card', description='抽取一張隨機角色卡')
async def draw_card(interaction: discord.Interaction):
    card = random.choice(cards)
    await interaction.response.send_message(f"🎴 {interaction.user.mention} 抽到卡牌: {card}")

@bot.tree.command(name='leaderboard', description='查看等級或金幣排行榜')
async def leaderboard(interaction: discord.Interaction, type: str = "level"):
    if type == "level":
        sorted_data = sorted(bot.levels.items(), key=lambda x: x[1]["level"], reverse=True)
        description = "\n".join([f"{i+1}. <@{uid}> 等級: {data['level']}, XP: {data['xp']}" for i,(uid,data) in enumerate(sorted_data[:10])])
        await interaction.response.send_message(f"🏆 等級排行榜:\n{description}")
    elif type == "gold":
        sorted_data = sorted(bot.rpg_players.items(), key=lambda x: x[1]["gold"], reverse=True)
        description = "\n".join([f"{i+1}. <@{uid}> 金幣: {data['gold']}" for i,(uid,data) in enumerate(sorted_data[:10])])
        await interaction.response.send_message(f"💰 金幣排行榜:\n{description}")
    else:
        await interaction.response.send_message("❌ 類型錯誤，可選: level 或 gold", ephemeral=True)

# --------------------------- 啟動 Bot ---------------------------
bot.run(TOKEN, reconnect=True)
