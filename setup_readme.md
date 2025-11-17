# Price is... Wrong? 💸

A multiplayer price guessing game where you try to guess ridiculous prices for obscure items.

## Features

✅ **Phase 1 Complete:**
- Real-time multiplayer gameplay with WebSockets
- Game Master controls (upload sets, control game flow)
- Player interface (join without login, submit guesses)
- Difficulty-based scoring system
- Clean, fun UI with themed styling
- Scoreboard and round-by-round results
- Remote play capability

## Setup Instructions

### Prerequisites
- Python 3.8+
- pip

### Installation

1. **Install dependencies:**
```bash
pip install flask flask-socketio python-socketio
```

2. **Create directory structure:**
```
price-guessing-game/
├── app.py
├── templates/
│   ├── index.html
│   └── gamemaster.html
├── static/
│   └── uploads/
└── data/
```

3. **Run the application:**
```bash
python app.py
```

4. **Access the game:**
- Upload interface: `http://localhost:5000/gamemaster`
- Game interface: `http://localhost:5000/`

## How to Play

### For Game Masters:

1. **Upload your item sets:**
   - Go to `/gamemaster`
   - Create a set with a name and pitch line
   - Add items with:
     - Name and description
     - Image URL (use Imgur, Cloudinary, etc.)
     - Difficulty level
     - Actual price

2. **Run the game:**
   - Go to `/` and click "Join as Game Master"
   - Share the URL with players
   - Click a set to start playing
   - Control the game flow with GM buttons:
     - "Reveal Guesses" - Show all player guesses
     - "Reveal Answer" - Show actual price and scores
     - "Next Item" - Move to next item or scoreboard

### For Players:

1. Go to the game URL
2. Enter your username and click "Join as Player"
3. Wait for GM to select a set
4. View item and submit your guess
5. Watch guesses reveal and see scores
6. Compete across multiple items!

## Scoring System

The game uses a logarithmic scoring system:
- **Base Score:** Based on relative error (how far off you were as a % of actual price)
- **Difficulty Multipliers:**
  - Easy: 1.0x
  - Medium: 1.5x
  - Hard: 2.0x
  - Cruel: 3.0x

Perfect guesses = 1000 points (before multiplier)

## Remote Play

For remote play with family/friends:

### Option 1: Ngrok (Easiest)
```bash
# Install ngrok from ngrok.com
ngrok http 5000
# Share the ngrok URL with players
```

### Option 2: Deploy to Cloud
- Deploy to Render, Railway, or Heroku
- Set environment variables as needed
- Share the public URL

### Option 3: Local Network
- Find your local IP: `ipconfig` (Windows) or `ifconfig` (Mac/Linux)
- Players access: `http://YOUR_IP:5000`
- Requires same network or port forwarding

## Tips for Finding Good Items

**Best Sources:**
- eBay completed auctions (sort by highest price)
- Estate sale websites
- Rare liquor auctions
- Movie prop replica sites
- Etsy vintage/collectibles
- Luxury resale platforms

**What Makes a Good Item:**
- High price variance (could be $5 or $5000)
- Ambiguous quality from photo
- Obscure categories most people don't know
- Surprising real-world prices

## Future Enhancements (Not Yet Built)

- Automatic item sourcing from eBay API
- Player authentication
- Persistent game history
- Timer for guesses
- Team mode
- Custom scoring formulas

## Troubleshooting

**Players can't connect:**
- Check firewall settings
- Ensure port 5000 is open
- Try ngrok for easy remote access

**Images not loading:**
- Use direct image URLs (ending in .jpg, .png, etc.)
- Try imgur.com or i.imgur.com links
- Avoid sites that require login

**Game state issues:**
- Refresh all browsers
- Restart the server
- Check browser console for errors

## Tech Stack

- **Backend:** Flask + Flask-SocketIO
- **Frontend:** Vanilla JavaScript + Socket.IO client
- **Styling:** Custom CSS with gradient themes
- **Data Storage:** JSON file (simple persistent storage)

## Contributing Ideas

Want to add features? Some ideas:
- Database integration (PostgreSQL/MongoDB)
- User accounts and game history
- Mobile app version
- Voice chat integration
- Automatic eBay/Etsy sourcing
- Tournament mode with brackets

---

**Have fun and may the best guesser win!** 🎉