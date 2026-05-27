import os
import requests
import datetime
import threading  # Added for keep-alive
import time       # Added for keep-alive
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# The base path pointing to your Hugging Face space files repository
HF_BASE_URL = "https://huggingface.co/spaces/mehtab13/backtestlab-data/raw/main"

# --- Keep-Alive Background Task ---
def keep_alive_task():
    while True:
        print(f"[{datetime.datetime.now()}] 🕒 Server is alive and running.")
        time.sleep(6) # Logs every 6 seconds

# Start the background task
thread = threading.Thread(target=keep_alive_task, daemon=True)
thread.start()
# ----------------------------------

def parse_date(date_str):
    """Safely parse incoming ISO date strings from the frontend workspace."""
    try:
        if not date_str:
            return None
        # Handle full ISO format by splitting out trailing time offsets
        clean_date = date_str.split('T')[0]
        return datetime.datetime.strptime(clean_date, "%Y-%m-%d").date()
    except Exception as e:
        print(f"❌ Date parsing failure for value '{date_str}': {e}")
        return None

@app.route('/', methods=['GET'])
def home():
    return "Server is active."

@app.route('/data', methods=['GET'])
def get_market_data():
    symbol = request.args.get('symbol', 'XAUUSD').upper()
    tf = request.args.get('tf', 'h4').lower()
    initial_str = request.args.get('initial')
    current_str = request.args.get('current')
    to_str = request.args.get('to')

    start_date = parse_date(initial_str) or parse_date(current_str)
    end_date = parse_date(to_str)

    if not start_date or not end_date:
        return jsonify({"error": "Invalid date parameters provided"}), 404

    history_candles = []
    future_candles = []

    # Calculate month blocks to scan between start and end ranges
    current_check = datetime.date(start_date.year, start_date.month, 1)
    target_end = datetime.date(end_date.year, end_date.month, 1)

    while current_check <= target_end:
        year_str = str(current_check.year)
        # Matches your single-digit month file names (1.json, 2.json, etc.)
        month_str = str(current_check.month)
        
        # Lowercase asset symbol folder layout (xauusd)
        symbol_path = symbol.lower()
        
        # FIXED: Routes through separate nested subfolders: /xauusd/h4/2021/1.json
        block_url = f"{HF_BASE_URL}/{symbol_path}/{tf}/{year_str}/{month_str}.json"
        print(f"🚀 Middleman downloading block: {block_url}")

        try:
            response = requests.get(block_url, timeout=10)
            if response.status_code == 200:
                month_data = response.json()
                if isinstance(month_data, list):
                    for candle in month_data:
                        if 'time' in candle:
                            # Convert timestamp to date object for sorting logic boundaries
                            c_date = datetime.datetime.fromtimestamp(candle['time']).date()
                            
                            # Allocate candles into history vs future live queue arrays
                            if c_date < start_date:
                                history_candles.append(candle)
                            elif start_date <= c_date <= end_date:
                                future_candles.append(candle)
            else:
                print(f"⚠️ Block not found or inaccessible. HTTP Status: {response.status_code} for URL: {block_url}")
        except Exception as e:
            print(f"❌ Exception occurred while requesting block chunk data: {e}")

        # Step to next calendar month block iteration securely
        if current_check.month == 12:
            current_check = datetime.date(current_check.year + 1, 1, 1)
        else:
            current_check = datetime.date(current_check.year, current_check.month + 1, 1)

    # Sort array blocks safely via timestamp keys to guarantee chronological chart rendering
    history_candles.sort(key=lambda x: x.get('time', 0))
    future_candles.sort(key=lambda x: x.get('time', 0))

    print(f"[{symbol}-{tf}] HISTORY={len(history_candles)} FUTURE={len(future_candles)} RANGE={start_date} -> {end_date}")

    return jsonify({
        "history": history_candles,
        "data": future_candles
    })

if __name__ == '__main__':
    # Bind to environment port assigned by Render or default local fallback
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
