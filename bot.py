import logging
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import urllib.parse as up

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from fastapi import FastAPI, Request
import uvicorn

# -------------------------------
# Настройки
# -------------------------------
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN", "8400963211:AAEau9lHdOK6SOCOAyykOEkWLswxs3JS42g")
COURIER_ID = int(os.getenv("COURIER_ID", 1452105851))
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://lol_bot_mine_user:zaNVubL3czJHIQcdZWK1TNRMiBj0BAf9@dpg-d361tfnfte5s739cd29g-a.oregon-postgres.render.com/lol_bot_mine"
)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://mine-bot-ufhg.onrender.com/webhook")
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8000))

# -------------------------------
# Подключение к PostgreSQL
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
# FSM состояния
# -------------------------------
class OrderState(StatesGroup):
    waiting_for_item = State()
    waiting_for_quantity = State()

# -------------------------------
# Router / Dispatcher
# -------------------------------
router = Router()
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
dp.include_router(router)

# -------------------------------
# Команда /help
# -------------------------------
@router.message(Command("help"))
async def help_cmd(message: types.Message):
    if message.from_user.id == COURIER_ID:
        # Для админа
        text = (
            "⚙️ Команды администратора:\n\n"
            "/answer <id> <цена> — установить цену на заказ\n"
            "/done <id> — отметить заказ доставленным\n"
            "/admin_cancel <id> — отменить заказ\n"
            "/help — показать это меню"
        )
    else:
        # Для пользователя
        text = (
            "📖 Команды клиента:\n\n"
            "/order — сделать заказ\n"
            "/money_done <сумма> — подтвердить оплату\n"
            "/cancel — отменить свой последний заказ\n"
            "/help — показать это меню"
        )
    # Без parse_mode, чтобы не было ошибок парсинга
    await message.answer(text)

# -------------------------------
# Команда /start
# -------------------------------
@router.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Я бот для заказов.\n"
        "Напиши /help чтобы увидеть доступные команды."
    )

# -------------------------------
# Команда /order
# -------------------------------
@router.message(Command("order"))
async def order_cmd(message: types.Message, state: FSMContext):
    await message.answer("📦 Что хочешь заказать? Напиши название.")
    await state.set_state(OrderState.waiting_for_item)

@router.message(OrderState.waiting_for_item)
async def process_item(message: types.Message, state: FSMContext):
    await state.update_data(item=message.text.strip())
    await message.answer("🔢 Сколько штук нужно? (введи число)")
    await state.set_state(OrderState.waiting_for_quantity)

@router.message(OrderState.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    try:
        quantity = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи число (пример: 10)")
        return

    data = await state.get_data()
    item = data.get("item", "неизвестно")

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

    await message.answer(f"✅ Заказ #{order_id} создан: {item} x{quantity}")
    await state.clear()

    # Уведомляем курьера
    await message.bot.send_message(
        COURIER_ID,
        f"🚨 Новый заказ #{order_id}: {item} x{quantity}\nОт пользователя {message.from_user.id}"
    )

# -------------------------------
# Курьер ставит цену (/answer)
# -------------------------------
@router.message(Command("answer"))
async def answer_cmd(message: types.Message):
    if message.from_user.id != COURIER_ID:
        return

    try:
        _, order_id, price = message.text.split()
        order_id = int(order_id)
        price = int(price)
    except ValueError:
        await message.answer("❌ Формат: /answer order_id price")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s AND status = %s", (order_id, "waiting_price"))
    row = cur.fetchone()
    if not row:
        await message.answer("❌ Такого заказа нет или он уже обработан")
        cur.close()
        conn.close()
        return

    cur.execute(
        "UPDATE orders SET price = %s, status = %s WHERE id = %s",
        (price, "waiting_user_confirm", order_id)
    )
    conn.commit()
    cur.close()
    conn.close()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"accept_{order_id}")],
        [InlineKeyboardButton(text="❌ Отказаться", callback_data=f"reject_{order_id}")]
    ])
    await message.bot.send_message(
        row["user_id"],
        f"💰 Цена: {price} монет за {row['quantity']} шт.\nПодтверждаешь?",
        reply_markup=keyboard
    )
    await message.answer("✅ Цена отправлена клиенту")

# -------------------------------
# Кнопки: принять / отказ
# -------------------------------
@router.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: types.CallbackQuery):
    # немедленно подтверждаем callback (важно для вебхуков)
    await callback.answer("Подтверждаю...", show_alert=False)

    order_id = int(callback.data.split("_", 1)[1])
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    row = cur.fetchone()
    if not row:
        await callback.message.edit_text("❌ Заказ не найден")
        cur.close()
        conn.close()
        return

    cur.execute("UPDATE orders SET status = %s WHERE id = %s", ("accepted", order_id))
    conn.commit()
    cur.close()
    conn.close()

    await callback.message.edit_text("✅ Заказ принят! Теперь оплати: /money_done <сумма>")

    # уведомляем курьера
    await callback.bot.send_message(COURIER_ID, f"📨 Клиент подтвердил заказ #{order_id} — можно везти.")

@router.callback_query(F.data.startswith("reject_"))
async def reject_order(callback: types.CallbackQuery):
    await callback.answer("Отменяю...", show_alert=False)

    order_id = int(callback.data.split("_", 1)[1])
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    row = cur.fetchone()
    if not row:
        await callback.message.edit_text("❌ Заказ не найден")
        cur.close()
        conn.close()
        return

    cur.execute("UPDATE orders SET status = %s WHERE id = %s", ("rejected", order_id))
    conn.commit()
    cur.close()
    conn.close()

    await callback.message.edit_text("❌ Ты отказался от заказа")
    await callback.bot.send_message(COURIER_ID, f"📨 Клиент отменил заказ #{order_id}")

# -------------------------------
# Пользователь отменяет заказ (/cancel)
# -------------------------------
@router.message(Command("cancel"))
async def cancel_cmd(message: types.Message):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM orders WHERE user_id = %s AND status IN ('waiting_price','waiting_user_confirm','accepted') ORDER BY id DESC LIMIT 1",
        (message.from_user.id,)
    )
    row = cur.fetchone()
    if not row:
        await message.answer("❌ У тебя нет активных заказов для отмены")
        cur.close()
        conn.close()
        return

    cur.execute("UPDATE orders SET status = %s WHERE id = %s", ("cancelled", row["id"]))
    conn.commit()
    cur.close()
    conn.close()

    await message.answer(f"🚫 Твой заказ #{row['id']} отменён")
    await message.bot.send_message(COURIER_ID, f"⚠️ Пользователь {message.from_user.id} отменил заказ #{row['id']}")

# -------------------------------
# Админ отменяет заказ (/admin_cancel)
# -------------------------------
@router.message(Command("admin_cancel"))
async def admin_cancel_cmd(message: types.Message):
    if message.from_user.id != COURIER_ID:
        return
    try:
        _, order_id = message.text.split()
        order_id = int(order_id)
    except ValueError:
        await message.answer("❌ Формат: /admin_cancel order_id")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    row = cur.fetchone()
    if not row:
        await message.answer("❌ Такого заказа нет")
        cur.close()
        conn.close()
        return

    cur.execute("UPDATE orders SET status = %s WHERE id = %s", ("cancelled", order_id))
    conn.commit()
    cur.close()
    conn.close()

    await message.answer(f"🚫 Заказ #{order_id} отменён админом")
    await message.bot.send_message(row["user_id"], f"⚠️ Твой заказ #{order_id} был отменён админом")

# -------------------------------
# Деньги пришли (/money_done)
# -------------------------------
@router.message(Command("money_done"))
async def money_done_cmd(message: types.Message):
    try:
        _, amount = message.text.split()
        amount = int(amount)
    except ValueError:
        await message.answer("❌ Формат: /money_done сумма")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM orders WHERE user_id = %s AND status IN ('accepted','waiting_user_confirm') ORDER BY id DESC LIMIT 1",
        (message.from_user.id,)
    )
    row = cur.fetchone()
    if not row:
        await message.answer("❌ Нет активного заказа для оплаты")
        cur.close()
        conn.close()
        return

    cur.execute("UPDATE orders SET status = %s WHERE id = %s", ("paid", row["id"]))
    conn.commit()
    cur.close()
    conn.close()

    await message.answer("💵 Оплата принята! Жди доставку 🚚")
    await message.bot.send_message(COURIER_ID, f"🔥 Оплата от {message.from_user.id}: {amount} монет")

# -------------------------------
# Доставка (/done)
# -------------------------------
@router.message(Command("done"))
async def done_cmd(message: types.Message):
    if message.from_user.id != COURIER_ID:
        return
    try:
        _, order_id = message.text.split()
        order_id = int(order_id)
    except ValueError:
        await message.answer("❌ Формат: /done order_id")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    row = cur.fetchone()
    if not row:
        await message.answer("❌ Такого заказа нет")
        cur.close()
        conn.close()
        return

    cur.execute("UPDATE orders SET status = %s WHERE id = %s", ("delivered", order_id))
    conn.commit()
    cur.close()
    conn.close()

    await message.bot.send_message(row["user_id"], "📦 Твой заказ доставлен! ✅")
    await message.answer(f"✅ Заказ #{order_id} закрыт")

# -------------------------------
# FastAPI + Webhook
# -------------------------------
app = FastAPI()
bot = Bot(token=TOKEN)

@app.on_event("startup")
async def on_startup():
    logging.info("Starting bot, init DB and set webhook...")
    init_db()
    # set webhook
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook set to: {WEBHOOK_URL}")

@app.post("/webhook")
async def webhook(request: Request):
    update = await request.json()
    logging.info(f"UPDATE RECEIVED: {update}")
    # передаём "сырой" апдейт диспетчеру
    await dp.feed_raw_update(bot, update)
    return {"status": "ok"}

# -------------------------------
# Запуск
# -------------------------------
if __name__ == "__main__":
    uvicorn.run("bot:app", host=WEBAPP_HOST, port=WEBAPP_PORT)
