import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./googlemaps.db",
)

# Use check_same_thread=False for SQLite to allow multi-threaded access
connect_args = {}
engine_kwargs = {
    "connect_args": connect_args,
    "pool_pre_ping": True,
}
if "sqlite" in DATABASE_URL:
    connect_args["check_same_thread"] = False
else:
    engine_kwargs["pool_recycle"] = 300

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

