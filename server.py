import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import (
    datetime,
    timezone,
    timedelta
)

app = Flask(__name__)
CORS(app)

# ==========================================
# CLOUD STORAGE CONFIGURATION
# ==========================================
# Replace these values with your exact Hugging Face details
HF_USERNAME = "mehtab13"
HF_SPACE_NAME = "backtestlab-data"
HF_BASE_URL = f"https://huggingface.co/spaces/{HF_USERNAME}/{HF_SPACE_NAME}/raw/main"

CHUNK_SIZE = 5000

# ==========================================
# HISTORY LIMITS
# ==========================================
TF_LIMITS = {
    # 3 MONTHS
    "m1": 90,
    # 1 YEAR
    "m5": 365,
    # 2 YEARS
    "m15": 730,
}


def to_timestamp(value):
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
        return int(
            dt.replace(
                tzinfo=timezone.utc
            ).timestamp()
        )
    except:
        return int(float(value))


def timestamp_to_datetime(ts):
    return datetime.fromtimestamp(
        ts,
        timezone.utc
    )


def next_month(year, month):
    month += 1
    if month > 12:
        return year + 1, 1
    return year, month


def load_month(symbol, tf, year, month):
    """
    Fetches the market asset block dynamically from Hugging Face 
    cloud storage instead of looking for a local local D:\\ drive.
    """
    clean_symbol = symbol.upper()
    clean_tf = tf.lower()
    
    # URL Example: https://huggingface.co/spaces/user/space/raw/main/EURCHF/m1/2003/08.json
    cloud_file_url = f"{HF_BASE_URL}/{clean_symbol}/{clean_tf}/{year}/{month:02d}.json"
    
    try:
        print(f"🚀 Middleman downloading block: {cloud_file_url}")
        response = requests.get(cloud_file_url, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ Block not found or inaccessible. HTTP Status: {response.status_code}")
            return []
            
    except Exception as e:
        print("☁️ CLOUD STORAGE FETCH ERROR:", e)
        return []


def get_candles(
    symbol,
    tf,
    start_ts,
    end_ts,
    limit=None
):
    candles = []

    dt = datetime.fromtimestamp(
        start_ts,
        timezone.utc
    )

    year = dt.year
    month = dt.month

    while True:
        monthly_data = load_month(
            symbol,
            tf,
            year,
            month
        )

        for candle in monthly_data:
            t = int(candle["time"])

            if t < start_ts:
                continue

            if t > end_ts:
                return candles

            candles.append(candle)

            if limit and len(candles) >= limit:
                return candles

        year, month = next_month(year, month)

        next_month_ts = datetime(
            year,
            month,
            1,
            tzinfo=timezone.utc
        ).timestamp()

        if next_month_ts > end_ts:
            break

    return candles


@app.route("/data")
def data():
    try:
        symbol = request.args.get(
            "symbol",
            "XAUUSD"
        )

        tf = request.args.get(
            "tf",
            "h4"
        ).lower()

        initial = request.args.get("initial")
        current = request.args.get("current")
        end = request.args.get("to")

        if not initial or not current or not end:
            return jsonify({
                "error": "Missing parameters"
            }), 400

        # ==========================================
        # CONVERT TO TIMESTAMPS
        # ==========================================
        initial_ts = to_timestamp(initial)
        current_ts = to_timestamp(current)
        end_ts = to_timestamp(end)

        # ==========================================
        # SMART HISTORY LIMITING
        # ==========================================
        history_start_ts = initial_ts

        if tf in TF_LIMITS:
            limit_days = TF_LIMITS[tf]

            current_dt = timestamp_to_datetime(
                current_ts
            )

            limited_start_dt = current_dt - timedelta(
                days=limit_days
            )

            limited_start_ts = int(
                limited_start_dt.timestamp()
            )

            history_start_ts = max(
                initial_ts,
                limited_start_ts
            )

        # ==========================================
        # HISTORY
        # ==========================================
        history = get_candles(
            symbol,
            tf,
            history_start_ts,
            current_ts
        )

        # ==========================================
        # FUTURE
        # ==========================================
        future = get_candles(
            symbol,
            tf,
            current_ts + 1,
            end_ts,
            limit=CHUNK_SIZE
        )

        # ==========================================
        # DEBUG LOG
        # ==========================================
        history_start_date = datetime.fromtimestamp(
            history_start_ts,
            timezone.utc
        ).strftime("%Y-%m-%d")

        current_date = datetime.fromtimestamp(
            current_ts,
            timezone.utc
        ).strftime("%Y-%m-%d")

        print(
            f"[{symbol}-{tf}] "
            f"HISTORY={len(history)} "
            f"FUTURE={len(future)} "
            f"RANGE={history_start_date} -> {current_date}"
        )

        return jsonify({
            "history": history,
            "data": future
        })

    except Exception as e:
        print("SERVER ERROR:", e)
        return jsonify({
            "error": str(e)
        }), 500


# ==========================================
# SAVE SESSION (Saves to Render temporary workspace)
# ==========================================
@app.route("/save_session", methods=["POST"])
def save_session():
    try:
        data = request.json
        
        sessions_dir = os.path.join(
            os.getcwd(),
            "sessions"
        )

        os.makedirs(
            sessions_dir,
            exist_ok=True
        )

        safe_name = "".join(
            c for c in data["session_name"]
            if c.isalnum() or c in (" ", "_", "-")
        ).rstrip()

        if not safe_name:
            safe_name = "session"

        filename = f"{safe_name}.json"
        path = os.path.join(
            sessions_dir,
            filename
        )

        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                data,
                f,
                indent=4
            )

        print("SESSION SAVED:", filename)
        return jsonify({
            "status": "success",
            "file": filename
        })

    except Exception as e:
        print("SAVE SESSION ERROR:", e)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port
    )
