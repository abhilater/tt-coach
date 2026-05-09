from app.core.db import get_engine
from sqlalchemy.orm import sessionmaker
from app.models.schema import Video

engine = get_engine()
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

videos = db.query(Video).limit(5).all()
for v in videos:
    print(f"ID: {v.id}, Title: {v.title}, Views: {v.view_count}, Published: {v.published_at}")

db.close()
