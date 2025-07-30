import asyncio
import time
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, select
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, selectinload
from sqlalchemy.ext.asyncio import AsyncSession, create_asyncio_engine
import os
from aiohttp import web

# === НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ===
BOT_TOKEN = os.getenv("8246831652:AAFRB6Qybun4GNXHDWllyEq_yvn6DObLSh8")
ADMIN_ID = int(os.getenv("1235789985"))
CHANNEL_ID = int(os.getenv("-1002389662159"))
CHANNEL_USERNAME = os.getenv("crum_online")

# === НАСТРОЙКА БАЗЫ ДАННЫХ ===
DATABASE_URL = "sqlite+aiosqlite:///./giveaways.db"
Base = declarative_base()

# === МОДЕЛИ БАЗЫ ДАННЫХ ===
class Giveaway(Base):
    __tablename__ = 'giveaways'
    message_id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    chat_id = Column(Integer, nullable=False)
    channel_message_id = Column(Integer)
    end_time = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    participants = relationship("Participant", back_populates="giveaway", cascade="all, delete-orphan")

class Participant(Base):
    __tablename__ = 'participants'
    id = Column(Integer, primary_key=True)
    giveaway_id = Column(Integer, ForeignKey('giveaways.message_id'))
    user_id = Column(Integer, nullable=False)
    username = Column(String)
    full_name = Column(String, nullable=False)
    giveaway = relationship("Giveaway", back_populates="participants")

# === СОЗДАНИЕ БОТА И БД ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Асинхронный движок БД
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# === HEALTH-CHECK СЕРВЕР (чтобы бот не засыпал) ===
async def start_webserver():
    async def health_check(request):
        return web.Response(text="OK", status=200)
    
    app = web.Application()
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Health-check сервер запущен на порту {port}")

# === ИНИЦИАЛИЗАЦИЯ БД ===
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    asyncio.create_task(check_active_giveaways())

# === ПРОВЕРКА АКТИВНЫХ РОЗЫГРЫШЕЙ ===
async def check_active_giveaways():
    await asyncio.sleep(5)
    async with async_session() as session:
        result = await session.execute(
            selectinload(Giveaway).where(Giveaway.is_active == True)
        )
        active_giveaways = result.scalars().all()
        
        for giveaway in active_giveaways:
            time_left = (giveaway.end_time - datetime.now()).total_seconds()
            if time_left > 0:
                if time_left > 3600:
                    asyncio.create_task(send_reminder(giveaway.message_id, time_left - 3600))
                asyncio.create_task(close_giveaway_after(giveaway.message_id, time_left))
            else:
                await close_giveaway(giveaway.message_id)

# === НАПОМИНАНИЕ ЗА 1 ЧАС ===
async def send_reminder(message_id: int, delay: float):
    await asyncio.sleep(delay)
    async with async_session() as session:
        giveaway = await session.get(Giveaway, message_id)
        if not giveaway or not giveaway.is_active:
            return
        link = f"https://t.me/{CHANNEL_USERNAME}/{giveaway.channel_message_id}" if CHANNEL_USERNAME else ""
        participants = giveaway.participants
        for participant in participants:
            try:
                await bot.send_message(
                    participant.user_id,
                    f"⏰ Внимание!\n\nРозыгрыш «{giveaway.title}» завершается через 1 час!\n\nУспейте принять участие:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🎁 Участвовать", url=link)]
                    ]) if link else None
                )
            except Exception as e:
                print(f"Не удалось отправить {participant.user_id}: {e}")
            await asyncio.sleep(0.05)

# === ЗАКРЫТЬ РОЗЫГРЫШ ===
async def close_giveaway_after(message_id: int, delay: float):
    await asyncio.sleep(delay)
    await close_giveaway(message_id)

async def close_giveaway(message_id: int):
    async with async_session() as session:
        giveaway = await session.get(Giveaway, message_id)
        if giveaway and giveaway.is_active:
            giveaway.is_active = False
            await session.commit()
            try:
                await bot.edit_message_text(
                    chat_id=CHANNEL_ID,
                    message_id=giveaway.channel_message_id,
                    text=f"🎉 РОЗЫГРЫШ: {giveaway.title}\n\n⏰ Время участия завершено!\nАдминистратор выберет победителя вручную.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🏆 Посмотреть участников", callback_data=f"list_{message_id}")]
                    ])
                )
            except Exception as e:
                print(f"Ошибка обновления поста: {e}")

# === СТАРТ ===
@dp.message(Command("start"))
async def start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 Вы администратор!\n\n"
                             "Используйте:\n"
                             "/startgiveaway <название> <время> — запустить розыгрыш\n"
                             "Пример: /startgiveaway Приз 24h\n\n"
                             "/broadcast <текст> — рассылка всем участникам\n"
                             "/list <id_поста> — посмотреть участников\n"
                             "/winner <id_поста> <id_пользователя> — выбрать победителя")
    else:
        await message.answer("Нажмите кнопку ниже, чтобы участвовать в розыгрыше 👇",
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                 [InlineKeyboardButton(text="🎁 Участвовать", callback_data="join_giveaway")]
                             ]))

# === РАССЫЛКА ===
@dp.message(Command("broadcast"))
async def broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if len(message.text.split()) < 2:
        await message.answer("❗ Введите текст:\n/broadcast Привет! Скоро новый розыгрыш!")
        return
    text = message.text.split(maxsplit=1)[1]
    async with async_session() as session:
        result = await session.execute("SELECT DISTINCT user_id FROM participants")
        user_ids = [row[0] for row in result]
    success = 0
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            print(f"Ошибка: {e}")
    await message.answer(f"📬 Рассылка завершена!\n✅ Успешно: {success}")

# === ЗАПУСК РОЗЫГРЫША ===
@dp.message(Command("startgiveaway"))
async def start_giveaway(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Только для админа")
        return
    try:
        parts = message.text.split(maxsplit=2)
        title = parts[1]
        duration_str = parts[2]
    except:
        await message.answer("❗ /startgiveaway Название 24h")
        return
    try:
        if duration_str.endswith('h'):
            duration = timedelta(hours=int(duration_str[:-1]))
        elif duration_str.endswith('d'):
            duration = timedelta(days=int(duration_str[:-1]))
        elif duration_str.endswith('w'):
            duration = timedelta(weeks=int(duration_str[:-1]))
        else:
            raise ValueError
        end_time = datetime.now() + duration
    except:
        await message.answer("❗ Время: 12h, 3d, 2w")
        return
    admin_msg = await message.answer(
        f"🎉 РОЗЫГРЫШ: {title}\n⏰ До конца: {duration_str}\n\nНажмите кнопку ниже 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Участвовать", callback_data="join_giveaway")]
        ])
    )
    try:
        channel_msg = await bot.send_message(
            CHANNEL_ID,
            f"🌊 КРЫМ. РОЗЫГРЫШ\n\n🎉 Приз: {title}\n⏰ До конца: {duration_str}\n\nУчаствуйте и выигрывайте!\n\nНажмите кнопку ниже 👇",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎁 Участвовать", callback_data="join_giveaway")]
            ])
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка в канале: {str(e)}")
        return
    async with async_session() as session:
        new_giveaway = Giveaway(
            message_id=admin_msg.message_id,
            channel_message_id=channel_msg.message_id,
            title=title,
            chat_id=message.chat.id,
            end_time=end_time
        )
        session.add(new_giveaway)
        await session.commit()
    time_left = (end_time - datetime.now()).total_seconds()
    if time_left > 3600:
        asyncio.create_task(send_reminder(admin_msg.message_id, time_left - 3600))
    asyncio.create_task(close_giveaway_after(admin_msg.message_id, time_left))
    await message.answer(f"✅ Розыгрыш запущен!\nID: {admin_msg.message_id}\nЗавершится: {end_time.strftime('%d.%m %H:%M')}")

# === УЧАСТИЕ ===
@dp.callback_query(lambda c: c.data == "join_giveaway")
async def join_giveaway(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    msg_id = callback.message.message_id
    async with async_session() as session:
        giveaway = await session.execute(
            selectinload(Giveaway).where(Giveaway.channel_message_id == msg_id)
        )
        giveaway = giveaway.scalars().first()
        if not giveaway:
            giveaway = await session.get(Giveaway, msg_id)
        if not giveaway or not giveaway.is_active:
            await callback.answer("Розыгрыш завершён")
            return
        result = await session.execute(
            selectinload(Participant).where(
                (Participant.giveaway_id == giveaway.message_id) & 
                (Participant.user_id == callback.from_user.id)
            )
        )
        if result.scalars().first():
            await callback.answer("Вы уже участвуете!")
            return
        new_participant = Participant(
            giveaway_id=giveaway.message_id,
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name
        )
        session.add(new_participant)
        await session.commit()
    async with async_session() as session:
        count = await session.execute(
            "SELECT COUNT(*) FROM participants WHERE giveaway_id = :msg_id",
            {"msg_id": giveaway.message_id}
        )
        participant_count = count.scalar()
    await callback.answer("✅ Вы участвуете!")
    try:
        await bot.edit_message_text(
            chat_id=CHANNEL_ID,
            message_id=giveaway.channel_message_id,
            text=callback.message.text.split("\n\n")[0] + f"\n\nУчаствует: {participant_count} человек",
            reply_markup=callback.message.reply_markup
        )
    except Exception as e:
        print(f"Ошибка обновления: {e}")

# === ПОСМОТРЕТЬ УЧАСТНИКОВ ===
@dp.callback_query(lambda c: c.data.startswith("list_"))
async def list_participants_callback(callback: types.CallbackQuery):
    msg_id = int(callback.data.split("_")[1])
    async with async_session() as session:
        result = await session.execute(
            selectinload(Giveaway).where(Giveaway.message_id == msg_id)
        )
        giveaway = result.scalars().first()
        if not giveaway:
            await callback.message.answer("❌ Розыгрыш не найден")
            await callback.answer()
            return
        participants = giveaway.participants
        if not participants:
            await callback.message.answer("📭 Нет участников")
        else:
            result_text = f"👥 Участники «{giveaway.title}»:\n\n"
            for i, p in enumerate(participants, 1):
                username = f"@{p.username}" if p.username else "без юзернейма"
                result_text += f"{i}. {username} (ID: {p.user_id})\n"
            await callback.message.answer(result_text)
    await callback.answer()

# === ВЫБРАТЬ ПОБЕДИТЕЛЯ ===
@dp.message(Command("winner"))
async def select_winner(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, msg_id, user_id = message.text.split()
        msg_id = int(msg_id)
        user_id = int(user_id)
    except:
        await message.answer("❗ /winner <id_поста> <id_пользователя>")
        return
    async with async_session() as session:
        participant = await session.execute(
            selectinload(Participant).where(
                (Participant.giveaway_id == msg_id) & 
                (Participant.user_id == user_id)
            )
        )
        participant = participant.scalars().first()
        if not participant:
            await message.answer("❌ Пользователь не участвует")
            return
        try:
            await bot.send_message(
                user_id,
                f"🎉 Поздравляем!\n\nВы выиграли:\n<b>{participant.giveaway.title}</b>\n\nСвяжитесь с администратором!",
                parse_mode="HTML"
            )
            status = "✅ Победитель уведомлён"
        except Exception as e:
            status = f"⚠️ Не удалось написать: {str(e)}"
        try:
            await bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=participant.giveaway.channel_message_id,
                text=f"🎉 РОЗЫГРЫШ: {participant.giveaway.title}\n\n🏆 Победитель: {participant.full_name} (ID: {user_id})\n\nРозыгрыш завершён!"
            )
        except Exception as e:
            print(f"Ошибка: {e}")
        await session.delete(participant.giveaway)
        await session.commit()
    await message.answer(f"{status}\n\n✅ Розыгрыш завершён")

# === ЗАПУСК ===
async def main():
    await init_db()
    asyncio.create_task(start_webserver())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())