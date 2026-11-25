import asyncio, time, random, os
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

TOKEN = os.getenv("BOT_TOKEN")
DB = "game.db"

bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------- БАЗА ----------
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                money INTEGER DEFAULT 500,
                energy INTEGER DEFAULT 100,
                health INTEGER DEFAULT 100,
                level INTEGER DEFAULT 1,
                xp INTEGER DEFAULT 0,
                job TEXT DEFAULT 'Курьер',
                last_work INTEGER DEFAULT 0,
                last_rest INTEGER DEFAULT 0,
                last_bonus INTEGER DEFAULT 0
            )""")
        await db.commit()

async def get_player(uid):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        row = await cur.fetchone()
        if row:
            return dict(row)
        await db.execute("INSERT INTO players (user_id) VALUES (?)", (uid,))
        await db.commit()
        cur = await db.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        return dict(await cur.fetchone())

async def update(uid, **kw):
    fields = ", ".join(f"{k}=?" for k in kw)
    vals = list(kw.values()) + [uid]
    async with aiosqlite.connect(DB) as db:
        await db.execute(f"UPDATE players SET {fields} WHERE user_id=?", vals)
        await db.commit()

# ---------- РАБОТЫ ----------
JOBS = {
    "Курьер":      {"pay": (30, 60),  "energy": 15, "lvl": 1},
    "Продавец":    {"pay": (50, 90),  "energy": 20, "lvl": 2},
    "Офис-менеджер":{"pay": (80, 140), "energy": 25, "lvl": 3},
    "Программист": {"pay": (150, 250),"energy": 30, "lvl": 5},
    "Директор":    {"pay": (300, 500),"energy": 35, "lvl": 8},
}

def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💼 Работать"), KeyboardButton(text="😴 Отдыхать")],
        [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="📊 Профиль")],
        [KeyboardButton(text="🎁 Бонус"), KeyboardButton(text="💼 Сменить работу")],
    ], resize_keyboard=True)

# ---------- ХЕНДЛЕРЫ ----------
@dp.message(Command("start"))
async def start(m: Message):
    await get_player(m.from_user.id)
    await m.answer(
        "👋 Привет! Это твой симулятор современной жизни.\n"
        "Здесь ты работаешь, отдыхаешь, покупаешь вещи и растишь уровень.\n\n"
        "Начни с профиля 👇",
        reply_markup=main_kb()
    )

@dp.message(F.text == "📊 Профиль")
async def profile(m: Message):
    p = await get_player(m.from_user.id)
    await m.answer(
        f"👤 <b>Твой профиль</b>\n\n"
        f"💼 Работа: <b>{p['job']}</b>\n"
        f"💰 Деньги: <b>{p['money']}</b>\n"
        f"⚡ Энергия: {p['energy']}/100\n"
        f"❤️ Здоровье: {p['health']}/100\n"
        f"⭐ Уровень: {p['level']} (XP {p['xp']}/{p['level']*100})"
    )

@dp.message(F.text == "💼 Работать")
async def work(m: Message):
    p = await get_player(m.from_user.id)
    now = int(time.time())
    if now - p['last_work'] < 60:
        return await m.answer(f"⏳ Подожди {60-(now-p['last_work'])} сек. перед новой сменой.")
    if p['energy'] < 20:
        return await m.answer("😩 Мало энергии — отдохни.")

    job = JOBS.get(p['job'], JOBS["Курьер"])
    earn = random.randint(*job['pay'])
    xp_gain = random.randint(5, 15)
    money, energy, xpv, lvl = p['money']+earn, p['energy']-job['energy'], p['xp']+xp_gain, p['level']

    if xpv >= lvl*100:
        xpv -= lvl*100
        lvl += 1
        await m.answer(f"🎉 Новый уровень! Теперь {lvl}")

    await update(m.from_user.id, money=money, energy=energy, xp=xpv, level=lvl, last_work=now)
    await m.answer(f"💼 Ты поработал {p['job']}!\n+{earn}💰 | +{xp_gain}XP | -{job['energy']}⚡")

@dp.message(F.text == "😴 Отдыхать")
async def rest(m: Message):
    p = await get_player(m.from_user.id)
    now = int(time.time())
    if now - p['last_rest'] < 30:
        return await m.answer("⏳ Ещё рано отдыхать.")
    e = min(100, p['energy']+30)
    h = min(100, p['health']+5)
    await update(m.from_user.id, energy=e, health=h, last_rest=now)
    await m.answer(f"😴 Отдохнул! ⚡ {e}/100, ❤️ {h}/100")

@dp.message(F.text == "🎁 Бонус")
async def bonus(m: Message):
    p = await get_player(m.from_user.id)
    now = int(time.time())
    if now - p['last_bonus'] < 86400:
        left = 86400 - (now - p['last_bonus'])
        h, mm = left//3600, (left%3600)//60
        return await m.answer(f"⏳ Бонус через {h} ч {mm} мин.")
    amount = random.randint(100, 300)
    await update(m.from_user.id, money=p['money']+amount, last_bonus=now)
    await m.answer(f"🎁 Ежедневный бонус: +{amount}💰")

@dp.message(F.text == "💼 Сменить работу")
async def change_job(m: Message):
    p = await get_player(m.from_user.id)
    kb = []
    for name, info in JOBS.items():
        if p['level'] >= info['lvl']:
            kb.append([InlineKeyboardButton(text=f"{name} ({info['pay'][0]}-{info['pay'][1]}💰)", callback_data=f"job:{name}")])
        else:
            kb.append([InlineKeyboardButton(text=f"🔒 {name} (ур.{info['lvl']})", callback_data="no")])
    await m.answer("Выбери работу:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("job:"))
async def set_job(cb: CallbackQuery):
    job = cb.data.split(":")[1]
    await update(cb.from_user.id, job=job)
    await cb.message.edit_text(f"✅ Теперь ты работаешь: <b>{job}</b>")
    await cb.answer()

@dp.callback_query(F.data == "no")
async def no_lvl(cb: CallbackQuery):
    await cb.answer("🔒 Недостаточный уровень", show_alert=True)

@dp.message(F.text == "🛒 Магазин")
async def shop(m: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍔 Еда (+30⚡) — 50💰", callback_data="buy:food")],
        [InlineKeyboardButton(text="💊 Аптечка (+30❤️) — 80💰", callback_data="buy:med")],
    ])
    await m.answer("🛒 <b>Магазин</b>\nЧто покупаем?", reply_markup=kb)

@dp.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery):
    item = cb.data.split(":")[1]
    p = await get_player(cb.from_user.id)
    if item == "food":
        if p['money'] < 50: return await cb.answer("💸 Мало денег", show_alert=True)
        e = min(100, p['energy']+30)
        await update(cb.from_user.id, money=p['money']-50, energy=e)
        await cb.message.edit_text(f"🍔 Съел еду! ⚡ {e}/100")
    elif item == "med":
        if p['money'] < 80: return await cb.answer("💸 Мало денег", show_alert=True)
        h = min(100, p['health']+30)
        await update(cb.from_user.id, money=p['money']-80, health=h)
        await cb.message.edit_text(f"💊 Подлечился! ❤️ {h}/100")
    await cb.answer()

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
