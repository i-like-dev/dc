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

"""
===============================
Discord 超完整 Slash Bot  (main.py)
- 以 Slash Command 為主（/help、/announce、/dm、/warn...等）
- 管理 / 娛樂 / 經濟 / 等級 / 公告 / 票務(客服單) / 文字工具 / 伺服器工具 / 權限開通
- Render 若用 Web Service：內建 Flask 綁定 PORT 以避免 Port Scan Timeout
- 若用 Background Worker：一樣可運行，Flask 會綁在背景 thread，不影響 Bot
- 狀態：Idle，狀態欄顯示「HFG 機器人 服務了{服務人數}人」(每 5 分鐘自動更新)
- 不依賴外部 API（可離線運作）

必備環境變數：
  DISCORD_TOKEN

建議 requirements.txt：
  discord.py==2.6.0
  Flask

===============================
"""

# ====== 基本設定 ======
GUILD_ID: int = 1227929105018912839              # 伺服器 ID（你提供的）
ADMIN_ROLE_ID: int = 1227938559130861578         # 管理員角色 ID（你提供的）
ANNOUNCE_CHANNEL_ID: int = 1228485979090718720   # 指定公告頻道（只發在這裡）
OWNER_ID: int | None = None                      # 若要指定擁有者可填 ID，否則 None

DATA_DIR = "."  # JSON 存放位置
LEVEL_FILE = os.path.join(DATA_DIR, "levels.json")
WARN_FILE = os.path.join(DATA_DIR, "warnings.json")
CURRENCY_FILE = os.path.join(DATA_DIR, "currency.json")
PERM_FILE = os.path.join(DATA_DIR, "feature_perms.json")

TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("環境變數 DISCORD_TOKEN 未設定")

# ====== JSON 工具 ======

def load_json(path: str, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ====== Bot & 狀態 ======
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

state = {
    "levels": load_json(LEVEL_FILE, {}),       # {user_id: {xp:int, level:int}}
    "warnings": load_json(WARN_FILE, {}),      # {user_id: ["reason1", ...]}
    "currency": load_json(CURRENCY_FILE, {}),  # {user_id: balance}
    "feature_perms": load_json(PERM_FILE, {}), # {user_id: true/false}
    "guess_games": {},                         # {channel_id: answer}
    "served_count": 0,
}


def is_admin_member(member: discord.Member) -> bool:
    if OWNER_ID and member.id == OWNER_ID:
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
        # 管理員永遠有權限
        if is_admin_member(inter.user):
            return True
        allowed = state["feature_perms"].get(str(inter.user.id), False)
        if not allowed:
            await inter.response.send_message("🚫 你沒有權限，請聯絡管理員開通。", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)


# ====== on_ready / 指令同步 / 狀態任務 ======
@bot.event
async def on_ready():
    # Idle 狀態 + 狀態欄（每 5 分鐘自動更新）
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


# ====== 等級系統：聊天加經驗 ======
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    uid = str(message.author.id)
    lv = state["levels"].setdefault(uid, {"xp": 0, "level": 1})
    lv["xp"] += 10
    if lv["xp"] >= lv["level"] * 100:
        lv["level"] += 1
        await message.channel.send(f"🎉 {message.author.mention} 升級到 {lv['level']} 級!")
    save_json(LEVEL_FILE, state["levels"])

    # 讓 prefix 指令能運作（雖然我們主力是 Slash）
    await bot.process_commands(message)


# ====== /help ======
@bot.tree.command(name="help", description="顯示可用指令清單", guild=discord.Object(id=GUILD_ID))
async def help_cmd(inter: discord.Interaction):
    cmds = bot.tree.get_commands(guild=discord.Object(id=GUILD_ID))
    lines = [f"/{c.name} — {c.description}" for c in cmds]
    text = "📜 指令清單:
" + "
".join(lines)
    await inter.response.send_message(text, ephemeral=True)


# ================= 管理類（需管理員） =================
@bot.tree.command(name="clear", description="清除訊息（1-200）", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def clear(inter: discord.Interaction, amount: app_commands.Range[int, 1, 200]):
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
async def mute(inter: discord.Interaction, member: discord.Member, seconds: app_commands.Range[int, 10, 604800]):
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
async def slowmode(inter: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
    await inter.channel.edit(slowmode_delay=seconds)
    await inter.response.send_message(f"🐢 已設定慢速模式：{seconds} 秒")


@bot.tree.command(name="nick", description="修改成員暱稱", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def nick(inter: discord.Interaction, member: discord.Member, new_nick: str):
    await member.edit(nick=new_nick)
    await inter.response.send_message(f"✏️ 已將 {member.mention} 暱稱改為：{new_nick}")


@bot.tree.command(name="addrole", description="賦予身分組", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def addrole(inter: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.add_roles(role, reason=f"By {inter.user}")
    await inter.response.send_message(f"✅ 已賦予 {role.name} 給 {member.display_name}")


@bot.tree.command(name="removerole", description="移除身分組", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def removerole(inter: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.remove_roles(role, reason=f"By {inter.user}")
    await inter.response.send_message(f"✅ 已移除 {role.name} 從 {member.display_name}")


# ====== 警告系統（滿 5 次 → 禁言 10 分鐘） ======
@bot.tree.command(name="warn", description="警告用戶，滿 5 次自動禁言 10 分鐘並 DM", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def warn(inter: discord.Interaction, member: discord.Member, reason: str):
    uid = str(member.id)
    warns = state["warnings"].setdefault(uid, [])
    warns.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {reason}")
    save_json(WARN_FILE, state["warnings"])

    count = len(warns)
    await inter.response.send_message(f"⚠️ {member.display_name} 已被警告（第 {count} 次）：{reason}")

    # DM 當事人
    try:
        await member.send(f"⚠️ 你在 {inter.guild.name} 被警告（第 {count} 次）。理由：{reason}")
    except discord.Forbidden:
        pass

    # 第 5 次 → 禁言 10 分鐘
    if count >= 5:
        until = datetime.now(timezone.utc) + timedelta(minutes=10)
        try:
            await member.edit(communication_disabled_until=until)
            try:
                await member.send("你已被禁言 10 分鐘（累積 5 次警告）。")
            except discord.Forbidden:
                pass
        except Exception:
            await inter.followup.send("❌ 禁言失敗，可能缺少權限", ephemeral=True)


@bot.tree.command(name="warnings", description="查看某位用戶警告記錄", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def warnings(inter: discord.Interaction, member: discord.Member):
    logs = state["warnings"].get(str(member.id), [])
    if not logs:
        await inter.response.send_message(f"✅ {member.display_name} 沒有任何警告")
    else:
        text = "
".join(f"- {w}" for w in logs[-20:])
        await inter.response.send_message(f"⚠️ {member.display_name} 的警告紀錄（近 20 筆）：
{text}")


# ================= 權限開通（非管理功能用） =================
@bot.tree.command(name="grant", description="給予某使用者使用一般功能的權限", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def grant(inter: discord.Interaction, member: discord.Member):
    state["feature_perms"][str(member.id)] = True
    save_json(PERM_FILE, state["feature_perms"])
    await inter.response.send_message(f"🔓 已開通 {member.display_name} 的一般功能權限")


@bot.tree.command(name="revoke", description="撤銷某使用者的一般功能權限", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def revoke(inter: discord.Interaction, member: discord.Member):
    state["feature_perms"][str(member.id)] = False
    save_json(PERM_FILE, state["feature_perms"])
    await inter.response.send_message(f"🔒 已撤銷 {member.display_name} 的一般功能權限")


# ================= 公告 / DM / SAY（一般功能需開通） =================
@bot.tree.command(name="announce", description="（僅公告頻道）發送嵌入公告", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def announce(inter: discord.Interaction, title: str, content: str):
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if not ch:
        await inter.response.send_message("❌ 找不到公告頻道，請檢查 ANNOUNCE_CHANNEL_ID", ephemeral=True)
        return
    embed = discord.Embed(
        title=title,
        description=content,
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"發布人：{inter.user.display_name}")
    await ch.send(embed=embed)
    await inter.response.send_message("✅ 公告已發佈", ephemeral=True)


@bot.tree.command(name="dm", description="私訊用戶（顯示管理員名稱）", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def dm_cmd(inter: discord.Interaction, member: discord.Member, message: str):
    try:
        await member.send(f"📩 管理員 {inter.user.display_name} 發送：{message}")
        await inter.response.send_message(f"✅ 已私訊 {member.display_name}", ephemeral=True)
    except discord.Forbidden:
        await inter.response.send_message("❌ 對方關閉私訊或無法傳送", ephemeral=True)


@bot.tree.command(name="say", description="讓機器人在目前頻道說話（附上發送者）", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def say(inter: discord.Interaction, message: str):
    await inter.channel.send(f"{message}  
—— {inter.user.display_name} 說")
    await inter.response.send_message("✅ 已代發訊息", ephemeral=True)


# ================= 經濟系統（一般功能） =================
@bot.tree.command(name="balance", description="查看餘額", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def balance(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    uid = str(m.id)
    state["currency"].setdefault(uid, 100)
    save_json(CURRENCY_FILE, state["currency"])
    await inter.response.send_message(f"💰 {m.display_name} 餘額：{state['currency'][uid]}")


@bot.tree.command(name="daily", description="每日領取 $100", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def daily(inter: discord.Interaction):
    uid = str(inter.user.id)
    bal = state["currency"].setdefault(uid, 100)
    state["currency"][uid] = bal + 100
    save_json(CURRENCY_FILE, state["currency"])
    await inter.response.send_message(f"🗓️ 已領取每日獎勵，當前餘額：{state['currency'][uid]}")


@bot.tree.command(name="transfer", description="轉帳給他人", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def transfer(inter: discord.Interaction, target: discord.Member, amount: app_commands.Range[int, 1, 1000000]):
    s_uid = str(inter.user.id)
    t_uid = str(target.id)
    state["currency"].setdefault(s_uid, 100)
    state["currency"].setdefault(t_uid, 100)
    if state["currency"][s_uid] < amount:
        await inter.response.send_message("❌ 你的餘額不足", ephemeral=True)
        return
    state["currency"][s_uid] -= amount
    state["currency"][t_uid] += amount
    save_json(CURRENCY_FILE, state["currency"])
    await inter.response.send_message(f"💸 已轉帳 {amount} 給 {target.display_name}")


# ================= 娛樂功能（一般功能） =================
@bot.tree.command(name="coinflip", description="擲硬幣", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def coinflip(inter: discord.Interaction):
    await inter.response.send_message(f"🪙 {random.choice(['正面', '反面'])}")


@bot.tree.command(name="dice", description="投擲骰子（1~sides）", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def dice(inter: discord.Interaction, sides: app_commands.Range[int, 2, 120]):
    await inter.response.send_message(f"🎲 結果：{random.randint(1, sides)}")


@bot.tree.command(name="rps", description="剪刀石頭布", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def rps(inter: discord.Interaction, choice: app_commands.Choice[str]):
    # 透過 choices 參數產生下拉
    pass

# 產生 choices（避免重複裝飾器樣板，這裡直接用 transformer）
rps.__annotations__["choice"] = app_commands.Transform[str, app_commands.Choice[str]]
rps.__doc__ = "剪刀石頭布"

@rps.autocomplete("choice")
async def rps_auto(inter: discord.Interaction, current: str):
    options = ["剪刀", "石頭", "布"]
    return [app_commands.Choice(name=o, value=o) for o in options if current in o or not current]

@rps._callback
async def rps_callback(inter: discord.Interaction, choice: str):
    bot_pick = random.choice(["剪刀", "石頭", "布"])
    result = "平手"
    win = {"剪刀": "布", "石頭": "剪刀", "布": "石頭"}
    if win[choice] == bot_pick:
        result = "你贏了"
    elif win[bot_pick] == choice:
        result = "你輸了"
    await inter.response.send_message(f"你出 {choice}，我出 {bot_pick} → {result}")


@bot.tree.command(name="8ball", description="神奇八號球", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def eight_ball(inter: discord.Interaction, question: str):
    answers = ["是的", "不是", "可能", "再想想", "絕對是", "我不確定"]
    await inter.response.send_message(f"🎱 Q: {question}
A: {random.choice(answers)}")


@bot.tree.command(name="truth", description="抽一題真心話", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def truth(inter: discord.Interaction):
    qs = [
        "你最後悔的一件事是什麼？",
        "你曾經偷偷喜歡過誰？",
        "你做過最丟臉的事？",
    ]
    await inter.response.send_message("🗣️ 真心話題目：" + random.choice(qs))


@bot.tree.command(name="dare", description="抽一題大冒險", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def dare(inter: discord.Interaction):
    ds = [
        "在公開頻道打三次：我是最棒的！",
        "用你最可愛的語氣說話一分鐘",
        "隨機發一個可愛表情包",
    ]
    await inter.response.send_message("🎯 大冒險任務：" + random.choice(ds))


@bot.tree.command(name="guess", description="猜數字（1-100）開始新遊戲", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def guess(inter: discord.Interaction):
    ans = random.randint(1, 100)
    state["guess_games"][inter.channel.id] = ans
    await inter.response.send_message("我想了一個 1~100 的數字，請在聊天輸入你的猜測！")


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    # 只是占位，確保事件不衝突；主要猜題在 on_message
    pass


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    # 等級處理
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

        # 猜數字處理
        ans = state["guess_games"].get(message.channel.id)
        if ans is not None and message.content.isdigit():
            n = int(message.content)
            if n == ans:
                await message.channel.send(f"🎉 {message.author.mention} 猜對了！答案就是 {ans}")
                del state["guess_games"][message.channel.id]
            elif n < ans:
                await message.channel.send("太小了！")
            else:
                await message.channel.send("太大了！")

    await bot.process_commands(message)


# ================= 票務（客服單） =================
class CloseTicket(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="關閉客服單", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def close_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        if not isinstance(inter.channel, discord.TextChannel):
            await inter.response.send_message("❌ 只能在文字頻道使用", ephemeral=True)
            return
        if not (is_admin_member(inter.user) or inter.user == inter.channel.owner):
            # 簡單權限：只有管理或開啟者可關閉
            pass
        await inter.response.send_message("🗑️ 頻道將在 5 秒後關閉", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await inter.channel.delete(reason=f"Closed by {inter.user}")
        except Exception:
            await inter.followup.send("❌ 關閉失敗，可能缺少權限", ephemeral=True)


@bot.tree.command(name="ticket_create", description="建立客服單（會建立專屬頻道）", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def ticket_create(inter: discord.Interaction, reason: str):
    category = discord.utils.get(inter.guild.categories, name="客服單")
    if not category:
        category = await inter.guild.create_category("客服單")
    overwrites = {
        inter.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        inter.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    name = f"ticket-{inter.user.name}"[:90]
    ch = await inter.guild.create_text_channel(name=name, category=category, overwrites=overwrites)
    embed = discord.Embed(title="客服單已建立", description=f"原因：{reason}", color=discord.Color.green())
    embed.set_footer(text=f"建立者：{inter.user.display_name}")
    await ch.send(content=inter.user.mention, embed=embed, view=CloseTicket())
    await inter.response.send_message(f"✅ 已建立客服單：{ch.mention}", ephemeral=True)


# ================= 實用工具（一般功能） =================
@bot.tree.command(name="server_info", description="查看伺服器資訊", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def server_info(inter: discord.Interaction):
    g = inter.guild
    embed = discord.Embed(title=f"{g.name} 資訊", color=discord.Color.blurple())
    embed.add_field(name="👑 擁有者", value=str(g.owner), inline=False)
    embed.add_field(name="👥 成員數", value=str(g.member_count), inline=False)
    embed.add_field(name="📅 建立時間", value=g.created_at.strftime('%Y-%m-%d'), inline=False)
    await inter.response.send_message(embed=embed)


@bot.tree.command(name="userinfo", description="查看用戶資訊", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def userinfo(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    embed = discord.Embed(title=f"{m} 的資訊", color=discord.Color.greyple())
    embed.add_field(name="🆔 ID", value=str(m.id), inline=False)
    if m.joined_at:
        embed.add_field(name="📅 加入伺服器", value=m.joined_at.strftime('%Y-%m-%d'), inline=False)
    embed.add_field(name="📝 建立帳號", value=m.created_at.strftime('%Y-%m-%d'), inline=False)
    await inter.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="取得頭像", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def avatar(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    await inter.response.send_message(m.display_avatar.url)


@bot.tree.command(name="remind", description="提醒（秒）", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def remind(inter: discord.Interaction, seconds: app_commands.Range[int, 5, 86400], text: str):
    await inter.response.send_message(f"⏰ 我會在 {seconds} 秒後提醒你：{text}", ephemeral=True)
    await asyncio.sleep(int(seconds))
    await inter.followup.send(f"⏰ 提醒：{text}")


# ====== 文字工具 ======
@bot.tree.command(name="reverse", description="反轉文字", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def reverse(inter: discord.Interaction, text: str):
    await inter.response.send_message(text[::-1])


@bot.tree.command(name="mock", description="aLtErNaTiNg CaSe", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def mock(inter: discord.Interaction, text: str):
    out = ''.join(c.lower() if i % 2 else c.upper() for i, c in enumerate(text))
    await inter.response.send_message(out)


@bot.tree.command(name="clap", description="在字之間加 👏", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def clap(inter: discord.Interaction, text: str):
    await inter.response.send_message(" 👏 ".join(text.split()))


@bot.tree.command(name="owo", description="OwO 化文字", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def owo(inter: discord.Interaction, text: str):
    out = text.replace('r', 'w').replace('l', 'w').replace('R', 'W').replace('L', 'W')
    await inter.response.send_message(out + " ~")


# ================== Flask 假 Web（防 Render Port Timeout） ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"


def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


# ================== 啟動 ==================
if __name__ == "__main__":
    # 啟動 Flask 以避免 Render Web Service 掃描不到 PORT 而 Timeout
    threading.Thread(target=run_web, daemon=True).start()
    # 啟動 Discord Bot
    bot.run(TOKEN)
