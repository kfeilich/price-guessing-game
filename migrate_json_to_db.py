"""
Migration script to import game_sets.json into PostgreSQL database
Usage: python migrate_json_to_db.py your_game_sets.json
"""

import json
import sys
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class GameSet(Base):
    __tablename__ = 'game_sets'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    pitch_line = Column(Text, nullable=False)
    items = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

def migrate_json_to_db(json_file, database_url=None):
    """
    Migrate JSON data to database
    
    Args:
        json_file: Path to game_sets.json file
        database_url: PostgreSQL connection string (or None for local SQLite)
    """
    # Setup database connection
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        engine = create_engine(database_url)
    else:
        engine = create_engine('sqlite:///game_sets.db')
    
    # Create tables
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Load JSON data
        with open(json_file, 'r') as f:
            game_sets = json.load(f)
        
        print(f"Found {len(game_sets)} sets to migrate")
        
        # Import each set
        for set_data in game_sets:
            # Check if set already exists by name
            existing = session.query(GameSet).filter_by(name=set_data['name']).first()
            
            if existing:
                print(f"  Updating existing set: {set_data['name']}")
                existing.pitch_line = set_data['pitch_line']
                existing.items = set_data['items']
                existing.updated_at = datetime.utcnow()
            else:
                print(f"  Creating new set: {set_data['name']}")
                new_set = GameSet(
                    name=set_data['name'],
                    pitch_line=set_data['pitch_line'],
                    items=set_data['items'],
                    created_at=datetime.fromisoformat(set_data.get('created_at', datetime.utcnow().isoformat()))
                )
                session.add(new_set)
        
        session.commit()
        print(f"\n✅ Successfully migrated {len(game_sets)} sets!")
        
        # Show what's in the database
        all_sets = session.query(GameSet).all()
        print(f"\nDatabase now contains {len(all_sets)} sets:")
        for s in all_sets:
            print(f"  - {s.name} ({len(s.items)} items)")
            
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python migrate_json_to_db.py <path_to_game_sets.json>")
        print("\nOptional: Set DATABASE_URL environment variable for PostgreSQL")
        print("Example: DATABASE_URL='postgresql://user:pass@host/db' python migrate_json_to_db.py data.json")
        sys.exit(1)
    
    json_file = sys.argv[1]
    database_url = os.environ.get('DATABASE_URL')
    
    if not os.path.exists(json_file):
        print(f"❌ File not found: {json_file}")
        sys.exit(1)
    
    migrate_json_to_db(json_file, database_url)
