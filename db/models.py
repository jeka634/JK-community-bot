from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Enum as SqlEnum
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    username = Column(String)
    ton_address = Column(String)
    is_veteran = Column(Boolean, default=False)
    is_legendary = Column(Boolean, default=False)
    referred_by = Column(Integer, ForeignKey('users.id'))
    referral_link = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    banned = Column(Boolean, default=False)
    balance = relationship('Balance', uselist=False, back_populates='user')
    daily_limit = relationship('DailyLimit', uselist=False, back_populates='user')

class Balance(Base):
    __tablename__ = 'balances'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    jk_balance = Column(Integer, default=0)
    user = relationship('User', back_populates='balance')

class DailyLimit(Base):
    __tablename__ = 'daily_limits'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    date = Column(DateTime, default=datetime.utcnow)
    earned_today = Column(Integer, default=0)
    user = relationship('User', back_populates='daily_limit')

class Ban(Base):
    __tablename__ = 'bans'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    reason = Column(String)
    banned_at = Column(DateTime, default=datetime.utcnow)
    unban_tx = Column(String)

class Referral(Base):
    __tablename__ = 'referrals'
    id = Column(Integer, primary_key=True)
    inviter_id = Column(Integer, ForeignKey('users.id'))
    invited_id = Column(Integer, ForeignKey('users.id'))
    bonus_given = Column(Boolean, default=False)

class Setting(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True)
    value = Column(String)

class DiceGameDB(Base):
    __tablename__ = 'dice_games'
    id = Column(Integer, primary_key=True)
    initiator_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    opponent_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)
    accepted = Column(Boolean, default=False)
    initiator_paid = Column(Boolean, default=False)
    opponent_paid = Column(Boolean, default=False)
    winner_id = Column(Integer, ForeignKey('users.id'))
    finished = Column(Boolean, default=False)
    temp_wallet = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow) 