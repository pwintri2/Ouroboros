from sqlalchemy import Column, Integer, String, Date, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class Record(Base):
    __tablename__ = 'records'
    id = Column(Integer, primary_key=True)
    artist_name = Column(String)
    song_title = Column(String)
    album_title = Column(String)
    genre = Column(String)
    release_date = Column(Date)

# For typing and usage in search function
from sqlalchemy.orm import Session

def register_function(name=None, description=None):
    def decorator(func):
        func._registered_name = name
        func._registered_description = description
        return func
    return decorator
