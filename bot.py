import asyncio
import logging
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import urllib.parse as up
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from fastapi import FastAPI, Request
import uvicorn

# -------------------------------
# Настройка брат
# -------------------------------
TOKEN = "8400963211:AAHGgS1GvY34nlkzWVb7XHPkh1CzP_Jwj24"
COURIER_ID = 1452105851
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://lol_bot_mine_user:zaNVubL3czJHIQcdZWK1TNRMiBj0BAf9@dpg-d361tfnfte5s739cd29g-a.oregon-postgres.render.com/lol_bot_mine"
)
WEBHOOK_URL = "https://mine-bot-ntqg.onrender.com/webhook"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8000))

# -------------------------------
# Подключение к Постгрес
# -------------------------------
def get_conn():
    up.uses_netloc.append("postgres")
    url = up.urlparse(DB_URL)

    return psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port or 5432,
        sslmode="require",
        cursor_factory=RealDictCursor
    )

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            item TEXT NOT NULL,
            quantity INT NOT NULL DEFAULT 1,
            price INT,
            status TEXT NOT NULL
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

# -------------------------------
# Состояния брат
# -------------------------------
class OrderState(StatesGroup):
    waiting_for_item = State()
    waiting_for_quantity = State()

# -------------------------------
# Роутер
# -------------------------------
router = Router()

# -------------------------------
# Команды
# -------------------------------
@router.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("САЛАМ АЛЕЙКУМ БРАААТ 🤲🤲 ЭТО БОТ ДЕЛА КАК ЗАКАЗЫВАЙ ПРЕДМЕТ КОТО МОЖ ДОБУТЬ ВЫЖИВАНИЕ, КАСТРАЦИЯ МЫШЬ СЕЙЧАС НЕТ БРАТ, ПОТОМ БУДЕТ АЛЛАХ ЗНАЕТ. ЗАКАЗ /order БРАТИШЬКААА")

@router.message(Command("order"))
async def order_cmd(message: types.Message, state: FSMContext):
    await message.answer("БРААТ, КАКОЙ ПРЕДМЕТ ТЫ ХОЧ?? 🗿 ПИШИ НАЗВАНИЕ ТОЧНО КАК В ИГРА БЕЗ ФАНТАЗИЯ, НЕ УМНИЧАЙ")
    await state.set_state(OrderState.waiting_for_item)

@router.message(OrderState.waiting_for_item)
async def process_item(message: types.Message, state: FSMContext):
    await state.update_data(item=message.text.strip())
    await message.answer("СКОЛЬКО ШТУКА НАДО ТЕБЕ, БРАТ?? ЦИФРА ПИШИ, НЕ БУКВА")
    await state.set_state(OrderState.waiting_for_quantity)

@router.message(OrderState.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    try:
        quantity = int(message.text.strip())
    except:
        await message.answer("ЭЭЭ БРАТ 🤦‍♂️ ТЫ ЦИФРА ПИШИ, НАПРИМЕР: 10, НЕ АБРАКАДАБРА")
        return

    data = await state.get_data()
    item = data["item"]

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (user_id, item, quantity, status) VALUES (%s, %s, %s, %s) RETURNING id",
        (message.from_user.id, item, quantity, "waiting_price")
    )
    order_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()

    await message.answer(f"📝 ТВОЙ ЗАКАЗ ЗАПИСАЛ БРАТ!\nПРЕДМЕТ: {item}\nКОЛИЧЕСТВО: {quantity}\nЖДИ, МИХАИЛИК СКОРО ЦЕНА СКАЖЕТ, НЕ НЕРВИРОВАЙСЯ")
    await state.clear()

    await message.bot.send_message(COURIER_ID, f"🚨 НОВЫЙ ЗАКАЗ #{order_id}: {item} x{quantity}\nОТ КЛИЕНТ {message.from_user.id}, ДВИЖЕНИЕ НАДО СДЕЛАТЬ БЫСТРО")

# -------------------------------
# Курьер цену ставит
# -------------------------------
@router.message(Command("answer"))
async def answer_cmd(message: types.Message):
    if message.from_user.id != COURIER_ID:
        return

    try:
        _, order_id, price = message.text.split()
        order_id = int(order_id)
        price = int(price)
    except:
        await message.answer("ФОРМАТ ПРАВИЛЬНО ПИШИ БРАТ 👉 /answer order_id price")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s AND status = %s", (order_id, "waiting_price"))
    row = cur.fetchone()

    if not row:
        await message.answer("ЭЭ БРАТ 🤨 ТАКОЙ ЗАКАЗ НЕТУ, ТЫ ВРУН?")
        return

    cur.execute("UPDATE orders SET price = %s, status = %s WHERE id = %s", (price, "waiting_user_confirm", order_id))
    conn.commit()
    cur.close()
    conn.close()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="ДААА БРАТ ✅", callback_data=f"accept_{order_id}")],
            [InlineKeyboardButton(text="ИДИ НАХУЙ ДОРОГА 💸❌", callback_data="reject")]
        ]
    )
    await message.bot.send_message(row["user_id"], f"💰 БРАТ, ЦЕНА ГОТОВА: {price} МОНЕТ ЗА {row['quantity']} ШТУКА. НОРМАЛЬНО??", reply_markup=keyboard)
    await message.answer("📨 ЦЕНА ОТПРАВИЛ КЛИЕНТУ, ВСЕ КРАСОТА")

# -------------------------------
# Деньги пришли
# -------------------------------
@router.message(Command("money_done"))
async def money_done_cmd(message: types.Message):
    try:
        _, amount = message.text.split()
        amount = int(amount)
    except:
        await message.answer("ФОРМАТ ПРАВИЛЬНЫЙ, БРАТ: /money_done сумма 💵")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE user_id = %s AND status = %s ORDER BY id DESC LIMIT 1", (message.from_user.id, "accepted"))
    row = cur.fetchone()
    if not row:
        await message.answer("ЭЭ БРАТ 🤔 У ТЕБЯ ЗАКАЗ НЕТ АКТИВНЫЙ, ЧЕ МУТИШЬ?")
        return

    cur.execute("UPDATE orders SET status = %s WHERE id = %s", ("paid", row["id"]))
    conn.commit()
    cur.close()
    conn.close()

    await message.answer("💵 ДЕНЬГА ПОЛУЧИЛ Я, БРАТ! ЖДИ ПОСЫЛКА, СКОРО ПРИДЕТ 🚚")
    await message.bot.send_message(COURIER_ID, f"🔥 ДЕНЬГА ОТ {message.from_user.id} ({amount} МОНЕТ). БРАТ, ГАЗУЙ НАХУЙ, ПОСЫЛКА ВЕЗИ БЫСТРО!")

# -------------------------------
# Доставка
# -------------------------------
@router.message(Command("done"))
async def done_cmd(message: types.Message):
    if message.from_user.id != COURIER_ID:
        return

    try:
        _, order_id = message.text.split()
        order_id = int(order_id)
    except:
        await message.answer("ФОРМАТ БРАТ: /done order_id 📦")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    row = cur.fetchone()

    if not row:
        await message.answer("ЭЭЭ БРАТ 😡 ЗАКАЗ ТАКОЙ НЕТУ, ТЫ ЧТО ПРИДУМАЛ?")
        return

    cur.execute("UPDATE orders SET status = %s WHERE id = %s", ("delivered", order_id))
    conn.commit()
    cur.close()
    conn.close()

    await message.bot.send_message(row["user_id"], "📦 БРААТ! ПОСЫЛКА ПРИЕХАЛА, БЕРИ СВОЙ ШТУКА 🙌")
    await message.answer(f"✅ ЗАКАЗ #{order_id} ЗАКРЫТ, БРАТ, ВСЕ ПО КРАСОТЕ")

# -------------------------------
# FastAPI + Webhook
# -------------------------------
app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher()
dp.include_router(router)

@app.on_event("startup")
async def on_startup():
    logging.basicConfig(level=logging.INFO)
    init_db()
    await bot.set_webhook(WEBHOOK_URL)

@app.post("/webhook")
async def webhook(request: Request):
    update = await request.json()
    await dp.feed_raw_update(bot, update)
    return {"status": "ok"}

# -------------------------------
# Запуск
# -------------------------------
if __name__ == "__main__":
    uvicorn.run("bot:app", host=WEBAPP_HOST, port=WEBAPP_PORT)
import asyncio
import logging
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import urllib.parse as up
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from fastapi import FastAPI, Request
import uvicorn
