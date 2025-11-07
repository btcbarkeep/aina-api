import os
from typing import Generator
from sqlmodel import SQLModel, create_engine, Session

# ---- DATABASE URL CONFIG ----
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Render/Neon compatibility fix
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

# Fallback for local development
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./aina.db"

# ---- ENGINE SETUP ----
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=True, connect_args=connect_args)

# ---- DB INIT ----
def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)

# ---- SESSION GENERATOR ----
def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
