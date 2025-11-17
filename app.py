from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import json
from datetime import datetime
import secrets
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
socketio = SocketIO(app, cors_allowed_origins="*")

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database setup
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

if DATABASE_URL:
    engine = create_engine(DATABASE_URL)
else:
    # Fallback to SQLite for local development
    engine = create_engine('sqlite:///game_sets.db')

Base = declarative_base()

class GameSet(Base):
    __tablename__ = 'game_sets'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    pitch_line = Column(Text, nullable=False)
    items = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

Base.metadata.create_all(engine)
Session = scoped_session(sessionmaker(bind=engine))

# Game state (in production, use Redis or database)
game_rooms = {}

# Scoring function - exponential penalty for errors
def calculate_score(guess, actual, difficulty):
    if actual == 0:
        actual = 0.01  # Avoid division by zero
    
    # Relative error (as percentage)
    relative_error = abs(guess - actual) / actual
    
    # Base score with exponential penalty
    # Perfect guess = 1000 points
    # 10% error = ~600 points
    # 50% error = ~100 points  
    # 90%+ error = near 0 points
    if relative_error == 0:
        base_score = 1000
    elif relative_error < 0.05:
        # Very close guesses (within 5%) - high scores
        base_score = 1000 - (relative_error * 4000)
    elif relative_error < 0.20:
        # Close guesses (5-20%) - good scores
        base_score = 800 - (relative_error * 3000)
    elif relative_error < 0.50:
        # Moderate guesses (20-50%) - mediocre scores
        base_score = 500 - (relative_error * 800)
    else:
        # Bad guesses (50%+) - very low scores with steep falloff
        base_score = max(0, 100 * (1 / (relative_error + 0.1)))
    
    # Difficulty multiplier
    multipliers = {'easy': 1.0, 'medium': 1.5, 'hard': 2.0, 'cruel': 3.0}
    final_score = int(base_score * multipliers.get(difficulty, 1.0))
    
    return final_score

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/gamemaster')
def gamemaster():
    return render_template('gamemaster.html')

@app.route('/upload_set', methods=['POST'])
def upload_set():
    try:
        data = request.json
        set_name = data.get('set_name')
        pitch_line = data.get('pitch_line')
        items = data.get('items', [])
        set_id = data.get('set_id')  # If provided, we're updating
        
        db_session = Session()
        
        try:
            if set_id is not None and set_id != '':
                # Update existing set
                game_set = db_session.query(GameSet).filter_by(id=set_id).first()
                if game_set:
                    game_set.name = set_name
                    game_set.pitch_line = pitch_line
                    game_set.items = items
                    game_set.updated_at = datetime.utcnow()
                    db_session.commit()
                    return jsonify({'success': True, 'set_id': set_id, 'updated': True})
                else:
                    return jsonify({'success': False, 'error': 'Set not found'}), 404
            else:
                # Create new set
                game_set = GameSet(
                    name=set_name,
                    pitch_line=pitch_line,
                    items=items
                )
                db_session.add(game_set)
                db_session.commit()
                
                return jsonify({'success': True, 'set_id': game_set.id})
        finally:
            db_session.close()
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/get_sets')
def get_sets():
    db_session = Session()
    try:
        sets = db_session.query(GameSet).all()
        result = []
        for s in sets:
            result.append({
                'id': s.id,
                'name': s.name,
                'pitch_line': s.pitch_line,
                'items': s.items,
                'created_at': s.created_at.isoformat() if s.created_at else None
            })
        return jsonify(result)
    finally:
        db_session.close()

@app.route('/delete_set/<int:set_id>', methods=['DELETE'])
def delete_set(set_id):
    db_session = Session()
    try:
        game_set = db_session.query(GameSet).filter_by(id=set_id).first()
        if game_set:
            db_session.delete(game_set)
            db_session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Set not found'}), 404
    finally:
        db_session.close()

@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')

@socketio.on('join_game')
def handle_join_game(data):
    room = data.get('room', 'default')
    username = data.get('username', 'Anonymous')
    is_gm = data.get('is_gm', False)
    
    join_room(room)
    
    if room not in game_rooms:
        game_rooms[room] = {
            'players': {},
            'gm': None,
            'current_set': None,
            'current_item_index': 0,
            'guesses': {},
            'scores': {},
            'state': 'lobby'  # lobby, playing, guessing, reveal_guesses, reveal_answer, scoreboard
        }
    
    if is_gm:
        game_rooms[room]['gm'] = request.sid
    else:
        game_rooms[room]['players'][request.sid] = username
        game_rooms[room]['scores'][request.sid] = 0
    
    emit('game_state', game_rooms[room], room=room)
    emit('player_joined', {'username': username, 'is_gm': is_gm}, room=room)

@socketio.on('start_set')
def handle_start_set(data):
    room = data.get('room', 'default')
    set_id = data.get('set_id')
    
    if room in game_rooms and request.sid == game_rooms[room]['gm']:
        db_session = Session()
        try:
            game_set_db = db_session.query(GameSet).filter_by(id=set_id).first()
            if game_set_db:
                game_set = {
                    'id': game_set_db.id,
                    'name': game_set_db.name,
                    'pitch_line': game_set_db.pitch_line,
                    'items': game_set_db.items
                }
                
                game_rooms[room]['current_set'] = game_set
                game_rooms[room]['current_item_index'] = 0
                game_rooms[room]['state'] = 'playing'
                game_rooms[room]['guesses'] = {}
                
                # Reset scores for new game
                for player_id in game_rooms[room]['scores']:
                    game_rooms[room]['scores'][player_id] = 0
                
                current_item = game_set['items'][0]
                emit('show_item', {
                    'item': current_item,
                    'index': 0,
                    'total': len(game_set['items']),
                    'state': 'playing'
                }, room=room)
        finally:
            db_session.close()

@socketio.on('submit_guess')
def handle_submit_guess(data):
    room = data.get('room', 'default')
    guess = float(data.get('guess', 0))
    
    if room in game_rooms and request.sid in game_rooms[room]['players']:
        game_rooms[room]['guesses'][request.sid] = guess
        
        # Notify GM and all players that a guess was submitted
        username = game_rooms[room]['players'][request.sid]
        emit('guess_submitted', {
            'username': username,
            'total_guesses': len(game_rooms[room]['guesses']),
            'total_players': len(game_rooms[room]['players'])
        }, room=room)

@socketio.on('reveal_guesses')
def handle_reveal_guesses(data):
    room = data.get('room', 'default')
    
    if room in game_rooms and request.sid == game_rooms[room]['gm']:
        guesses_with_names = []
        for player_id, guess in game_rooms[room]['guesses'].items():
            username = game_rooms[room]['players'].get(player_id, 'Unknown')
            guesses_with_names.append({'username': username, 'guess': guess})
        
        game_rooms[room]['state'] = 'reveal_guesses'
        emit('show_guesses', {'guesses': guesses_with_names}, room=room)

@socketio.on('reveal_answer')
def handle_reveal_answer(data):
    room = data.get('room', 'default')
    
    if room in game_rooms and request.sid == game_rooms[room]['gm']:
        current_set = game_rooms[room]['current_set']
        item_index = game_rooms[room]['current_item_index']
        current_item = current_set['items'][item_index]
        actual_price = current_item['price']
        difficulty = current_item['difficulty']
        
        # Calculate scores
        results = []
        for player_id, guess in game_rooms[room]['guesses'].items():
            username = game_rooms[room]['players'].get(player_id, 'Unknown')
            score = calculate_score(guess, actual_price, difficulty)
            game_rooms[room]['scores'][player_id] += score
            results.append({
                'username': username,
                'guess': guess,
                'score': score,
                'total_score': game_rooms[room]['scores'][player_id]
            })
        
        game_rooms[room]['state'] = 'reveal_answer'
        emit('show_answer', {
            'actual_price': actual_price,
            'results': results
        }, room=room)

@socketio.on('next_item')
def handle_next_item(data):
    room = data.get('room', 'default')
    
    if room in game_rooms and request.sid == game_rooms[room]['gm']:
        game_rooms[room]['current_item_index'] += 1
        current_set = game_rooms[room]['current_set']
        item_index = game_rooms[room]['current_item_index']
        
        if item_index < len(current_set['items']):
            # Next item
            game_rooms[room]['state'] = 'playing'
            game_rooms[room]['guesses'] = {}
            current_item = current_set['items'][item_index]
            emit('show_item', {
                'item': current_item,
                'index': item_index,
                'total': len(current_set['items']),
                'state': 'playing'
            }, room=room)
        else:
            # Game over - show scoreboard
            scoreboard = []
            for player_id, score in game_rooms[room]['scores'].items():
                username = game_rooms[room]['players'].get(player_id, 'Unknown')
                scoreboard.append({'username': username, 'score': score})
            
            scoreboard.sort(key=lambda x: x['score'], reverse=True)
            game_rooms[room]['state'] = 'scoreboard'
            emit('show_scoreboard', {'scoreboard': scoreboard}, room=room)

@socketio.on('back_to_lobby')
def handle_back_to_lobby(data):
    room = data.get('room', 'default')
    
    if room in game_rooms and request.sid == game_rooms[room]['gm']:
        game_rooms[room]['state'] = 'lobby'
        game_rooms[room]['current_set'] = None
        game_rooms[room]['current_item_index'] = 0
        game_rooms[room]['guesses'] = {}
        emit('return_to_lobby', {}, room=room)

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Client disconnected: {request.sid}')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, debug=False, host='0.0.0.0', port=port)
