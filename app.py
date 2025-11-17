from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import json
from datetime import datetime
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
socketio = SocketIO(app, cors_allowed_origins="*")

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('data', exist_ok=True)

# Game state (in production, use Redis or database)
game_rooms = {}
game_sets = []

# Load game sets from file if exists
def load_game_sets():
    global game_sets
    if os.path.exists('data/game_sets.json'):
        with open('data/game_sets.json', 'r') as f:
            game_sets = json.load(f)

def save_game_sets():
    with open('data/game_sets.json', 'w') as f:
        json.dump(game_sets, f, indent=2)

load_game_sets()

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
        
        if set_id is not None and set_id != '':
            # Update existing set
            found = False
            for i, game_set in enumerate(game_sets):
                if game_set['id'] == set_id:
                    game_sets[i] = {
                        'id': set_id,
                        'name': set_name,
                        'pitch_line': pitch_line,
                        'items': items,
                        'created_at': game_set.get('created_at', datetime.now().isoformat()),
                        'updated_at': datetime.now().isoformat()
                    }
                    found = True
                    save_game_sets()
                    return jsonify({'success': True, 'set_id': set_id, 'updated': True})
            
            if not found:
                return jsonify({'success': False, 'error': 'Set not found'}), 404
        else:
            # Create new set - find next available ID
            max_id = max([s['id'] for s in game_sets], default=-1)
            new_id = max_id + 1
            
            game_set = {
                'id': new_id,
                'name': set_name,
                'pitch_line': pitch_line,
                'items': items,
                'created_at': datetime.now().isoformat()
            }
            
            game_sets.append(game_set)
            save_game_sets()
            
            return jsonify({'success': True, 'set_id': game_set['id']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/get_sets')
def get_sets():
    return jsonify(game_sets)

@app.route('/delete_set/<int:set_id>', methods=['DELETE'])
def delete_set(set_id):
    global game_sets
    game_sets = [s for s in game_sets if s['id'] != set_id]
    save_game_sets()
    return jsonify({'success': True})

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
        game_set = next((s for s in game_sets if s['id'] == set_id), None)
        if game_set:
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
