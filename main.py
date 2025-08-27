# main.py
import os
import json
import random
import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

# -------------------- 配置 (請改成你的值) --------------------
GUILD_ID = 1227929105018912839           # 目標伺服器 ID（你已提供）
ADMIN_ROLE_ID = 1227938559130861578     # 管理員角色 ID（你已提供）
ANNOUNCE_CHANNEL_ID = 1228485979090718720  # 公告頻道 ID（你指定要發公告的頻道）
# ------------------------------------------------------------

DATA_DIR = '.'
LEVEL_FILE = os.path.join(DATA_DIR, 'levels.json')
WARN_FILE = os.path.join(DATA_DIR, 'warnings.json')
CURRENCY_FILE = os.path.join(DATA_DIR, 'currency.json')
PERM_FILE = os.path.join(DATA_DIR, 'feature_perms.json')
TICKET_FILE = os.path.join(DATA_DIR, 'tickets.json')

TOKEN = os.environ.get('DISCORD_TOKEN')
if not TOKEN:
    raise RuntimeError("環境變數 DISCORD_TOKEN 未設定")

# -------------------- 檔案工具 --------------------
def load_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 初始化狀態 (使用者會有預先存在的 json)
state = {
    'levels': load_json(LEVEL_FILE, {}),
    'warnings': load_json(WARN_FILE, {}),
    'currency': load_json(CURRENCY_FILE, {}),
    'feature_perms': load_json(PERM_FILE, {}),
    'tickets': load_json(TICKET_FILE, {}),
    # small runtime-only stores
    'guess_games': {},   # key: user_id -> target
}

# -------------------- 權限檢查 --------------------
def is_admin_member(member: discord.Member) -> bool:
    if not member:
        return False
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
        allowed = state['feature_perms'].get(str(inter.user.id), False)
        if not allowed:
            await inter.response.send_message("🚫 你沒有權限，請聯絡管理員開通。", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# -------------------- Bot & Intents --------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------- on_ready 與狀態 --------------------
async def compute_member_count():
    guild = bot.get_guild(GUILD_ID)
    if guild:
        return sum(1 for m in guild.members if not m.bot)
    # fallback: sum across all guilds
    return sum(g.member_count for g in bot.guilds)

@bot.event
async def on_ready():
    # 設定 idle 狀態與狀態欄文字
    count = await compute_member_count()
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game(f"HFG 機器人 服務了 {count} 人"))
    # 同步 slash commands 到指定 guild
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ 已同步 {len(synced)} 個 slash 指令 到 guild {GUILD_ID}")
    except Exception as e:
        print("❌ 同步失敗:", e)
    print("🟢 Bot 已啟動:", bot.user)
    # 啟動每分鐘更新狀態任務（保證顯示人數即時）
    if not update_status.is_running():
        update_status.start()

@tasks.loop(minutes=1)
async def update_status():
    count = await compute_member_count()
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game(f"HFG 機器人 服務了 {count} 人"))

# -------------------- 等級系統 (訊息 XP) --------------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    uid = str(message.author.id)
    st = state['levels'].setdefault(uid, {"xp": 0, "level": 1})
    st['xp'] += 10
    # 如果達到升級門檻
    if st['xp'] >= st['level'] * 100:
        st['level'] += 1
        try:
            await message.channel.send(f"🎉 {message.author.mention} 升到等級 {st['level']}！")
        except Exception:
            pass
    save_json(LEVEL_FILE, state['levels'])
    await bot.process_commands(message)

# -------------------- 輔助函式 --------------------
def fmt_user(u: discord.User | discord.Member):
    if getattr(u, "display_name", None):
        return u.display_name
    return str(u)

# -------------------- Slash commands：管理 / 公告 / 私訊 / 經濟 / 娛樂 / 小工具 --------------------

# HELP
@bot.tree.command(name="help", description="顯示所有指令（僅顯示本伺服器）", guild=discord.Object(id=GUILD_ID))
async def help_cmd(inter: discord.Interaction):
    cmds = bot.tree.get_commands(guild=discord.Object(id=GUILD_ID))
    lines = [f"/{c.name} — {c.description}" for c in cmds]
    await inter.response.send_message("📜 指令清單:\n" + "\n".join(lines), ephemeral=True)

# ---------------- 管理類 ----------------
@bot.tree.command(name="clear", description="管理員或被授權者清除訊息", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
@app_commands.describe(amount="要刪除的訊息數量 (1~200)")
async def cmd_clear(inter: discord.Interaction, amount: app_commands.Range[int,1,200]):
    await inter.response.defer(ephemeral=True)
    deleted = await inter.channel.purge(limit=amount)
    await inter.followup.send(f"🧹 已刪除 {len(deleted)} 則訊息", ephemeral=True)

@bot.tree.command(name="kick", description="踢出成員 (管理員)", guild=discord.Object(id=GUILD_ID))
@require_admin()
@app_commands.describe(member="要踢出的使用者", reason="理由 (選填)")
async def cmd_kick(inter: discord.Interaction, member: discord.Member, reason: str = "無理由"):
    try:
        await member.kick(reason=reason)
        await inter.response.send_message(f"👢 {member.display_name} 已被踢出。理由：{reason}")
    except Exception as e:
        await inter.response.send_message(f"❌ 無法踢出：{e}", ephemeral=True)

@bot.tree.command(name="ban", description="封鎖成員 (管理員)", guild=discord.Object(id=GUILD_ID))
@require_admin()
@app_commands.describe(member="要封鎖的使用者", reason="理由 (選填)")
async def cmd_ban(inter: discord.Interaction, member: discord.Member, reason: str = "無理由"):
    try:
        await member.ban(reason=reason)
        await inter.response.send_message(f"⛔ {member.display_name} 已被封鎖。理由：{reason}")
    except Exception as e:
        await inter.response.send_message(f"❌ 無法封鎖：{e}", ephemeral=True)

@bot.tree.command(name="unban", description="解除封鎖 (管理員)", guild=discord.Object(id=GUILD_ID))
@require_admin()
@app_commands.describe(user_id="被解除封鎖的使用者 ID")
async def cmd_unban(inter: discord.Interaction, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await inter.guild.unban(user)
        await inter.response.send_message(f"✅ 已解除封鎖 {user}")
    except Exception as e:
        await inter.response.send_message(f"❌ 無法解除封鎖：{e}", ephemeral=True)

@bot.tree.command(name="mute", description="禁言 (管理員)", guild=discord.Object(id=GUILD_ID))
@require_admin()
@app_commands.describe(member="要禁言的使用者", minutes="禁言分鐘數")
async def cmd_mute(inter: discord.Interaction, member: discord.Member, minutes: int):
    try:
        until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        await member.edit(communication_disabled_until=until)
        await inter.response.send_message(f"🔇 {member.display_name} 已被禁言 {minutes} 分鐘")
    except Exception as e:
        await inter.response.send_message(f"❌ 無法禁言：{e}", ephemeral=True)

@bot.tree.command(name="unmute", description="解除禁言 (管理員)", guild=discord.Object(id=GUILD_ID))
@require_admin()
@app_commands.describe(member="解除禁言使用者")
async def cmd_unmute(inter: discord.Interaction, member: discord.Member):
    try:
        await member.edit(communication_disabled_until=None)
        await inter.response.send_message(f"🔊 {member.display_name} 已解除禁言")
    except Exception as e:
        await inter.response.send_message(f"❌ 無法解除禁言：{e}", ephemeral=True)

# ---------------- 公告 ----------------
@bot.tree.command(name="announce", description="在指定公告頻道發送 embed 公告 (管理員/授權)", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
@app_commands.describe(title="公告標題", content="公告內容")
async def cmd_announce(inter: discord.Interaction, title: str, content: str):
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if not ch:
        await inter.response.send_message("❌ 找不到公告頻道，請確認 ANNOUNCE_CHANNEL_ID。", ephemeral=True)
        return
    embed = discord.Embed(title=title, description=content, color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
    embed.set_author(name=str(inter.user), icon_url=inter.user.display_avatar.url if inter.user.display_avatar else None)
    embed.set_footer(text=f"發布人：{inter.user.display_name} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    await ch.send(embed=embed)
    await inter.response.send_message("✅ 公告已發佈。", ephemeral=True)

# ---------------- 私訊 / 發言 ----------------
@bot.tree.command(name="dm", description="向使用者發送私訊 (管理員/授權)", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
@app_commands.describe(member="接收私訊的使用者", message="私訊內容")
async def cmd_dm(inter: discord.Interaction, member: discord.Member, message: str):
    try:
        prefix = f"📩 管理員 {inter.user.display_name} 發送："
        await member.send(f"{prefix}{message}")
        await inter.response.send_message(f"✅ 已私訊 {member.display_name}", ephemeral=True)
    except discord.Forbidden:
        await inter.response.send_message("❌ 該使用者無法接收私訊或已封鎖機器人。", ephemeral=True)
    except Exception as e:
        await inter.response.send_message(f"❌ 發送失敗：{e}", ephemeral=True)

@bot.tree.command(name="say", description="代發訊息到頻道（顯示：XXX 說：）(管理員/授權)", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
@app_commands.describe(channel="目標文字頻道", message="要代發的內容")
async def cmd_say(inter: discord.Interaction, channel: discord.TextChannel, message: str):
    try:
        await channel.send(f"{inter.user.display_name} 說：{message}")
        await inter.response.send_message("✅ 已發送。", ephemeral=True)
    except Exception as e:
        await inter.response.send_message(f"❌ 發送失敗：{e}", ephemeral=True)

# ---------------- 經濟系統 ----------------
@bot.tree.command(name="balance", description="查詢餘額", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="查詢的使用者 (選填)")
async def cmd_balance(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    uid = str(m.id)
    state['currency'].setdefault(uid, 100)
    save_json(CURRENCY_FILE, state['currency'])
    await inter.response.send_message(f"💰 {m.display_name} 餘額: {state['currency'][uid]}")

@bot.tree.command(name="pay", description="轉帳給別人", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="接收者", amount="金額 (正整數)")
async def cmd_pay(inter: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0:
        await inter.response.send_message("❌ 金額必須大於 0", ephemeral=True); return
    uid_from = str(inter.user.id); uid_to = str(member.id)
    state['currency'].setdefault(uid_from, 100)
    state['currency'].setdefault(uid_to, 100)
    if state['currency'][uid_from] < amount:
        await inter.response.send_message("❌ 你的餘額不足。", ephemeral=True); return
    state['currency'][uid_from] -= amount
    state['currency'][uid_to] += amount
    save_json(CURRENCY_FILE, state['currency'])
    await inter.response.send_message(f"✅ 已轉帳 {amount} 給 {member.display_name}")

@bot.tree.command(name="daily", description="領取每日簽到獎勵 (一次/天)", guild=discord.Object(id=GUILD_ID))
async def cmd_daily(inter: discord.Interaction):
    uid = str(inter.user.id)
    user = state['currency'].setdefault(uid, 100)
    # 簡單每日限制：將 last_daily 存在 currency 下作示範
    meta_key = f"{uid}_lastdaily"
    last = state.get('meta', {}).get(meta_key)
    today = datetime.now().date().isoformat()
    if last == today:
        await inter.response.send_message("❌ 今天已領過每日獎勵。", ephemeral=True); return
    # 發放 50
    state['currency'][uid] = state['currency'].get(uid, 100) + 50
    # 保存 lastdaily
    state.setdefault('meta', {})[meta_key] = today
    save_json(CURRENCY_FILE, state['currency'])
    save_json(PERM_FILE, state.get('meta', {}))  # meta 存在於 PERM_FILE 作示範
    await inter.response.send_message("✅ 已領取今日簽到獎勵：+50")

# ---------------- 等級 / 查詢 ----------------
@bot.tree.command(name="level", description="查詢等級", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="查詢的使用者 (選填)")
async def cmd_level(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    uid = str(m.id)
    info = state['levels'].get(uid, {"xp":0,"level":1})
    await inter.response.send_message(f"⭐ {m.display_name} 等級: {info['level']} (XP: {info['xp']})")

# ---------------- 警告系統 ----------------
@bot.tree.command(name="warn", description="警告使用者 (管理員/授權)", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
@app_commands.describe(member="被警告的使用者", reason="理由")
async def cmd_warn(inter: discord.Interaction, member: discord.Member, reason: str):
    uid = str(member.id)
    state['warnings'].setdefault(uid, []).append({"by": inter.user.id, "reason": reason, "time": datetime.now(timezone.utc).isoformat()})
    save_json(WARN_FILE, state['warnings'])
    # DM 被警告者（若可）
    try:
        await member.send(f"⚠️ 你已被警告：{reason}\n目前警告次數：{len(state['warnings'][uid])}")
    except Exception:
        pass
    # 處罰：若警告 >=5 就禁言 10 分鐘（示範）
    if len(state['warnings'][uid]) >= 5:
        try:
            until = datetime.now(timezone.utc) + timedelta(minutes=10)
            await member.edit(communication_disabled_until=until)
            await inter.response.send_message(f"⚠️ {member.display_name} 已達 5 次警告，禁言 10 分鐘。")
        except Exception as e:
            await inter.response.send_message(f"警告已紀錄，但無法禁言: {e}", ephemeral=True)
            return
    await inter.response.send_message(f"⚠️ 已對 {member.display_name} 發出警告。")

@bot.tree.command(name="warnings", description="查詢使用者警告", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="查詢目標 (選填)")
async def cmd_warnings(inter: discord.Interaction, member: discord.Member | None = None):
    m = member or inter.user
    uid = str(m.id)
    warns = state['warnings'].get(uid, [])
    if not warns:
        await inter.response.send_message(f"✅ {m.display_name} 沒有警告")
        return
    lines = []
    for i,w in enumerate(warns, start=1):
        by = w.get("by")
        reason = w.get("reason")
        t = w.get("time", "")
        lines.append(f"{i}. {reason} (by <@{by}>) @ {t}")
    await inter.response.send_message("⚠️ 警告紀錄:\n" + "\n".join(lines), ephemeral=True)

@bot.tree.command(name="resetwarnings", description="重設某人的警告 (管理員)", guild=discord.Object(id=GUILD_ID))
@require_admin()
@app_commands.describe(member="目標使用者")
async def cmd_resetwarnings(inter: discord.Interaction, member: discord.Member):
    uid = str(member.id)
    state['warnings'][uid] = []
    save_json(WARN_FILE, state['warnings'])
    await inter.response.send_message(f"✅ 已清除 {member.display_name} 的警告紀錄。")

# ---------------- 客服單 (簡易) ----------------
@bot.tree.command(name="ticket", description="建立客服單 (會在 json 存檔)", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(content="客服內容")
async def cmd_ticket(inter: discord.Interaction, content: str):
    tid = str(len(state['tickets']) + 1)
    state['tickets'][tid] = {
        "user": str(inter.user.id),
        "content": content,
        "status": "open",
        "time": datetime.now(timezone.utc).isoformat()
    }
    save_json(TICKET_FILE, state['tickets'])
    await inter.response.send_message(f"🎫 已建立客服單 #{tid}，客服人員會處理。", ephemeral=True)

@bot.tree.command(name="closeticket", description="關閉客服單 (管理員)", guild=discord.Object(id=GUILD_ID))
@require_admin()
@app_commands.describe(ticket_id="客服單編號")
async def cmd_closeticket(inter: discord.Interaction, ticket_id: str):
    if ticket_id not in state['tickets']:
        await inter.response.send_message("❌ 找不到該客服單。", ephemeral=True); return
    state['tickets'][ticket_id]['status'] = 'closed'
    state['tickets'][ticket_id]['closed_by'] = str(inter.user.id)
    state['tickets'][ticket_id]['closed_at'] = datetime.now(timezone.utc).isoformat()
    save_json(TICKET_FILE, state['tickets'])
    await inter.response.send_message(f"✅ 已關閉客服單 #{ticket_id}", ephemeral=True)

# ---------------- 娛樂小遊戲 ----------------
@bot.tree.command(name="rps", description="剪刀石頭布 (選擇: rock/paper/scissors)", guild=discord.Object(id=GUILD_ID))
@app_commands.choices(choice=[
    app_commands.Choice(name="rock", value="rock"),
    app_commands.Choice(name="paper", value="paper"),
    app_commands.Choice(name="scissors", value="scissors")
])
async def cmd_rps(inter: discord.Interaction, choice: app_commands.Choice[str]):
    bot_choice = random.choice(["rock", "paper", "scissors"])
    user = choice.value
    res = "平手"
    wins = {("rock","scissors"),("paper","rock"),("scissors","paper")}
    if user == bot_choice:
        res = "平手"
    elif (user, bot_choice) in wins:
        res = "你贏了"
    else:
        res = "你輸了"
    await inter.response.send_message(f"你: {user}  | 我: {bot_choice} → **{res}**")

@bot.tree.command(name="guess_start", description="開始猜數字遊戲 (會私訊正被開始者)", guild=discord.Object(id=GUILD_ID))
@require_feature_permission()
async def cmd_guess_start(inter: discord.Interaction):
    target = random.randint(1,100)
    state['guess_games'][str(inter.user.id)] = target
    await inter.response.send_message("✅ 猜數字遊戲已開始！請使用 /guess <數字> 來猜（範圍 1~100）。", ephemeral=True)

@bot.tree.command(name="guess", description="猜數字 (1~100)", guild=discord.Object(id=GUILD_ID))
async def cmd_guess(inter: discord.Interaction, number: app_commands.Range[int,1,100]):
    key = str(inter.user.id)
    if key not in state['guess_games']:
        await inter.response.send_message("❌ 你尚未開始遊戲，請使用 /guess_start 開始。", ephemeral=True); return
    target = state['guess_games'][key]
    if number == target:
        await inter.response.send_message(f"🎉 猜中了！答案是 {target}。恭喜！")
        del state['guess_games'][key]
    elif number < target:
        await inter.response.send_message("🔺 太小了！", ephemeral=True)
    else:
        await inter.response.send_message("🔻 太大了！", ephemeral=True)

# ---------------- 文本工具 ----------------
@bot.tree.command(name="reverse", description="文字反轉", guild=discord.Object(id=GUILD_ID))
async def cmd_reverse(inter: discord.Interaction, text: str):
    await inter.response.send_message(text[::-1])

@bot.tree.command(name="mock", description="mock 文本 (隨機大小寫模仿)", guild=discord.Object(id=GUILD_ID))
async def cmd_mock(inter: discord.Interaction, text: str):
    out = "".join(c.upper() if random.random() < 0.5 else c.lower() for c in text)
    await inter.response.send_message(out)

# ---------------- 權限管理 ----------------
@bot.tree.command(name="permit", description="授予使用者功能權限 (管理員)", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def cmd_permit(inter: discord.Interaction, member: discord.Member):
    state['feature_perms'][str(member.id)] = True
    save_json(PERM_FILE, state['feature_perms'])
    await inter.response.send_message(f"✅ 已授權 {member.display_name} 使用受限功能。")

@bot.tree.command(name="revoke", description="撤銷使用者功能權限 (管理員)", guild=discord.Object(id=GUILD_ID))
@require_admin()
async def cmd_revoke(inter: discord.Interaction, member: discord.Member):
    state['feature_perms'][str(member.id)] = False
    save_json(PERM_FILE, state['feature_perms'])
    await inter.response.send_message(f"✅ 已撤銷 {member.display_name} 的授權。")

# ---------------- 幾個管理輔助命令 ----------------
@bot.tree.command(name="whoami", description="顯示你的 ID 與顯示名稱", guild=discord.Object(id=GUILD_ID))
async def cmd_whoami(inter: discord.Interaction):
    await inter.response.send_message(f"你: {inter.user} ({inter.user.id})", ephemeral=True)

@bot.tree.command(name="server_info", description="伺服器資訊", guild=discord.Object(id=GUILD_ID))
async def cmd_server_info(inter: discord.Interaction):
    g = inter.guild
    embed = discord.Embed(title=f"{g.name} 的資訊", color=discord.Color.blurple())
    embed.add_field(name="成員數", value=str(g.member_count), inline=False)
    embed.add_field(name="頻道數", value=str(len(g.channels)), inline=False)
    embed.set_footer(text=f"ID: {g.id}")
    await inter.response.send_message(embed=embed, ephemeral=True)

# ---------------- 啟動 ----------------
if __name__ == "__main__":
    # 確保 data files exist
    for path, default in [(LEVEL_FILE, {}), (WARN_FILE, {}), (CURRENCY_FILE, {}), (PERM_FILE, {}), (TICKET_FILE, {})]:
        if not os.path.exists(path):
            save_json(path, default)
    bot.run(TOKEN)
