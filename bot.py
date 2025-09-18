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
# Настройка
# -------------------------------
TOKEN = "8400963211:AAEau9lHdOK6SOCOAyykOEkWLswxs3JS42g"
COURIER_ID = 1452105851
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://lol_bot_mine_user:zaNVubL3czJHIQcdZWK1TNRMiBj0BAf9@dpg-d361tfnfte5s739cd29g-a.oregon-postgres.render.com/lol_bot_mine"
)
WEBHOOK_URL = "https://mine-bot-ufhg.onrender.com/webhook"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8000))

# -------------------------------
# Подключение к БД
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
    await message.answer(
        "САЛАМ АЛЕЙКУМ БРАААТ 🤲\n"
        "Заказ → /order"
    )

@router.message(Command("order"))
async def order_cmd(message: types.Message, state: FSMContext):
    await message.answer("БРААТ, КАКОЙ ПРЕДМЕТ ТЫ ХОЧ?? 🗿")
    await state.set_state(OrderState.waiting_for_item)

@router.message(OrderState.waiting_for_item)
async def process_item(message: types.Message, state: FSMContext):
    await state.update_data(item=message.text.strip())
    await message.answer("СКОЛЬКО ШТУКА НАДО ТЕБЕ, БРАТ?? ЦИФРА ПИШИ")
    await state.set_state(OrderState.waiting_for_quantity)

@router.message(OrderState.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    try:
        quantity = int(message.text.strip())
    except:
        await message.answer("ЭЭЭ БРАТ 🤦‍♂️ ЦИФРА, НАПРИМЕР: 10")
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
    await state.clear()

    await message.answer(f"📝 ЗАКАЗ ЗАПИСАЛ!\n{item} x{quantity}")
    await message.bot.send_message(
        COURIER_ID,
        f"🚨 НОВЫЙ ЗАКАЗ #{order_id}: {item} x{quantity}\nОТ {message.from_user.id}"
    )

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
        await message.answer("Формат: /answer order_id price")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s AND status = %s", (order_id, "waiting_price"))
    row = cur.fetchone()
    if not row:
        await message.answer("Такого заказа нет")
        cur.close()
        conn.close()
        return

    cur.execute("UPDATE orders SET price = %s, status = %s WHERE id = %s",
                (price, "waiting_user_confirm", order_id))
    conn.commit()
    cur.close()
    conn.close()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton("ДА ✅", callback_data=f"accept_{order_id}")],
            [InlineKeyboardButton("НЕТ ❌", callback_data=f"reject_{order_id}")]
        ]
    )
    await message.bot.send_message(row["user_id"], f"💰 Цена: {price} монет за {row['quantity']} шт. Нормально?", reply_markup=keyboard)
    await message.answer("Цена отправлена клиенту")

# -------------------------------
# Принятие / отказ
# -------------------------------
@router.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status = %s WHERE id = %s", ("accepted", order_id))
    conn.commit()
    cur.close()
    conn.close()
    await callback.message.edit_text("✅ Заказ принят! Теперь плати /money_done сумма")
    await callback.answer()

@router.callback_query(F.data.startswith("reject_"))
async def reject_order(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status = %s WHERE id = %s", ("rejected", order_id))
    conn.commit()
    cur.close()
    conn.close()
    await callback.message.edit_text("❌ Ты отказался от заказа")
    await callback.answer()

# -------------------------------
# Деньги пришли
# -------------------------------
@router.message(Command("money_done"))
async def money_done_cmd(message: types.Message):
    try:
        _, amount = message.text.split()
        amount = int(amount)
    except:
        await message.answer("Формат: /money_done сумма")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE user_id=%s AND status=%s ORDER BY id DESC LIMIT 1", (message.from_user.id, "accepted"))
    row = cur.fetchone()
    if not row:
        await message.answer("Нет активного заказа")
        return

    cur.execute("UPDATE orders SET status=%s WHERE id=%s", ("paid", row["id"]))
    conn.commit()
    cur.close()
    conn.close()
    await message.answer("💵 Деньга получена! Жди доставку 🚚")
    await message.bot.send_message(COURIER_ID, f"🔥 Оплата от {message.from_user.id}: {amount} монет")

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
        await message.answer("Формат: /done order_id")
        return
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id=%s", (order_id,))
    row = cur.fetchone()
    if not row:
        await message.answer("Такого заказа нет")
        return
    cur.execute("UPDATE orders SET status=%s WHERE id=%s", ("delivered", order_id))
    conn.commit()
    cur.close()
    conn.close()
    await message.bot.send_message(row["user_id"], "📦 Посылка доставлена!")
    await message.answer(f"✅ Заказ #{order_id} закрыт")

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
    logging.info(f"UPDATE RECEIVED: {update}")
    await dp.feed_raw_update(bot, update)
    return {"status": "ok"}

# -------------------------------
# Запуск
# -------------------------------
if __name__ == "__main__":
    uvicorn.run("bot:app", host=WEBAPP_HOST, port=WEBAPP_PORT)
