import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, selectinload
from sqlalchemy.ext.asyncio import AsyncSession, create_asyncio_engine
import asyncio

# Загружаем переменные из .env
load_dotenv()
BOT_TOKEN = os.getenv("8246831652:AAFRB6Qybun4GNXHDWllyEq_yvn6DObLSh8")
ADMIN_ID = int(os.getenv("1235789985"))
CHANNEL_ID = int(os.getenv("-1002389662159"))
CHANNEL_USERNAME = os.getenv("crum_online")

# База данных
Base = declarative_base()

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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

engine = create_async_engine("sqlite+aiosqlite:///./giveaways.db", echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@dp.message(Command("start"))
async def start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 Вы администратор!")
    else:
        await message.answer("Нажмите кнопку ниже 👇",
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                 [InlineKeyboardButton(text="🎁 Участвовать", callback_data="join_giveaway")]
                             ]))

@dp.message(Command("startgiveaway"))
async def start_giveaway(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split(maxsplit=2)
        title = parts[1]
        duration_str = parts[2]
    except:
        await message.answer("❗ /startgiveaway <название> <время>")
        return
    async with async_session() as session:
        new_giveaway = Giveaway(
            message_id=message.message_id,
            title=title,
            chat_id=message.chat.id,
            end_time=datetime.now() + parse_duration(duration_str)
        )
        session.add(new_giveaway)
        await session.commit()
    await message.answer(f"✅ Розыгрыш запущен!\nID: {message.message_id}")

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
