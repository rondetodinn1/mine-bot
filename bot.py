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
# Состояния
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
    await message.answer("САЛАМ АЛЕЙКУМ БРАТ 🤲 Тут заказы принимаются. /order чтобы начать 🚀")

@router.message(Command("order"))
async def order_cmd(message: types.Message, state: FSMContext):
    await message.answer("Брат, какой предмет закажешь? 🗿")
    await state.set_state(OrderState.waiting_for_item)

@router.message(OrderState.waiting_for_item)
async def process_item(message: types.Message, state: FSMContext):
    await state.update_data(item=message.text.strip())
    await message.answer("Сколько штук тебе нужно? Пиши цифрой.")
    await state.set_state(OrderState.waiting_for_quantity)

@router.message(OrderState.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    try:
        quantity = int(message.text.strip())
    except:
        await message.answer("Пиши число, брат 🙏 Например: 10")
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

    await message.answer(f"✅ Заказ принят!\nПредмет: {item}\nКоличество: {quantity}")
    await state.clear()

    await message.bot.send_message(
        COURIER_ID,
        f"🚨 Новый заказ #{order_id}: {item} x{quantity}\nОт {message.from_user.id}"
    )

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
# Состояния
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
    await message.answer("САЛАМ АЛЕЙКУМ БРАТ 🤲 Тут заказы принимаются. /order чтобы начать 🚀")

@router.message(Command("order"))
async def order_cmd(message: types.Message, state: FSMContext):
    await message.answer("Брат, какой предмет закажешь? 🗿")
    await state.set_state(OrderState.waiting_for_item)

@router.message(OrderState.waiting_for_item)
async def process_item(message: types.Message, state: FSMContext):
    await state.update_data(item=message.text.strip())
    await message.answer("Сколько штук тебе нужно? Пиши цифрой.")
    await state.set_state(OrderState.waiting_for_quantity)

@router.message(OrderState.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    try:
        quantity = int(message.text.strip())
    except:
        await message.answer("Пиши число, брат 🙏 Например: 10")
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

    await message.answer(f"✅ Заказ принят!\nПредмет: {item}\nКоличество: {quantity}")
    await state.clear()

    await message.bot.send_message(
        COURIER_ID,
        f"🚨 Новый заказ #{order_id}: {item} x{quantity}\nОт {message.from_user.id}"
    )

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
