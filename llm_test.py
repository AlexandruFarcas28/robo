from flask import Flask, request, jsonify
from flask_cors import CORS

import datetime
import threading
import requests
import re
import difflib

from ctransformers import AutoModelForCausalLM

MODEL_PATH = "D:/openhermes-2.5-mistral-7b.Q4_K_M.gguf"

app = Flask(__name__)
CORS(app)

model_lock = threading.Lock()
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH, model_type="mistral", gpu_layers=0
)

# --- Mapping, helper functions, etc ---
_COMMAND_LIST = [
    "what time is it", "tell me a joke", "weather", "weather in",
    "sleep", "wake up", "help", "search", "what date it is"
]

def normalize_text(text: str) -> str:
    import unicodedata
    text = text.lower()
    text = unicodedata.normalize('NFD', text)
    return ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')

def _is_similar(a: str, b: str, threshold: float = 0.6) -> bool:
    return difflib.SequenceMatcher(None, a, b).ratio() > threshold

def _map_to_known(cmd: str):
    match = difflib.get_close_matches(cmd, _COMMAND_LIST, n=1, cutoff=0.5)
    if match:
        return match[0]
    if cmd.startswith("search "):
        return "search"
    if cmd.startswith("weather in "):
        return "weather in"
    if cmd.strip() == "weather":
        return "weather"
    return cmd

def weather_code_to_description(code):
    codes = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Depositing rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
        80: "Rain showers", 95: "Thunderstorm", 99: "Hail thunderstorm"
    }
    return codes.get(code, "Unknown")

def get_location_by_ip():
    try:
        r = requests.get("https://ipinfo.io/json", timeout=5)
        data = r.json()
        loc = data.get("loc", "")
        city = data.get("city", "Unknown city")
        if loc:
            lat, lon = loc.split(",")
            return {"city": city, "lat": float(lat), "lon": float(lon)}
    except Exception as e:
        return None
    return None

def ask_question(prompt):
    with model_lock:
        result = model(
            prompt,
            max_new_tokens=100,
            temperature=0.7
        )
    if hasattr(result, '__iter__') and not isinstance(result, str):
        answer = ''.join(result)
    else:
        answer = result
    return answer.strip()

def process_command(cmd: str):
    lower  = cmd.lower()
    mapped = _map_to_known(cmd)

    # Date/time
    if "date" in lower and "time" not in lower:
        now = datetime.datetime.now()
        return now.strftime("%B %d, %Y")
    if "time" in lower and "date" not in lower:
        now = datetime.datetime.now()
        return now.strftime("%H:%M")

    # Weather
    if mapped == "weather":
        loc = get_location_by_ip()
        if not loc:
            return "I couldn't determine your location."
        lat, lon, city = loc["lat"], loc["lon"], loc["city"]
    elif mapped == "weather in":
        parts = cmd.split(None, 2)
        city = parts[2] if len(parts) > 2 else None
        if city:
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
            try:
                r = requests.get(geo_url, timeout=5)
                geo = r.json()
                if 'results' not in geo or not geo['results']:
                    return f"Couldn't find coordinates for {city}"
                loc_data = geo['results'][0]
                lat = loc_data['latitude']
                lon = loc_data['longitude']
                city = loc_data['name']
            except Exception as e:
                return f"Geolocation failed: {e}"
        else:
            return "Please specify a city for weather."
    else:
        city, lat, lon = None, None, None

    if mapped in ("weather", "weather in"):
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&current=temperature_2m,weathercode"
        )
        try:
            r = requests.get(url, timeout=5)
            data = r.json()
            temp = data['current']['temperature_2m']
            code = data['current']['weathercode']
            desc = weather_code_to_description(code)
            return f"Weather in {city}: {desc}, {temp}°C"
        except Exception as e:
            return f"Failed to fetch weather: {e}"

    if mapped in ("tell me a joke", "joke"):
        prompt = "Tell me a clever joke in at most three sentences."
        joke = ask_question(prompt)
        parts = re.split(r'(?<=[\.\!?])\s+', joke)
        snippet = " ".join(parts[:3]).strip()
        if not re.match(r'.*[\.\!?]"?$', snippet):
            snippet += '.'
        return snippet

    if mapped == "help":
        return (
            "You can say: what time is it, weather, tell me a joke, search <query>, etc."
        )

    if mapped == "search":
        parts = cmd.split(None, 1)
        query = parts[1] if len(parts) > 1 else ""
        if not query:
            return "Please specify a search query."
        try:
            from googlesearch import search as gsearch
            url = next(gsearch(query, num=1, stop=1, pause=2.0))
            resp = requests.get(url, timeout=5)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            meta = (soup.find('meta', attrs={'name': 'description'}) or
                    soup.find('meta', attrs={'property': 'og:description'}))
            raw = meta.get('content', '').strip() if meta else ''
            if not raw:
                full = soup.get_text(separator=' ', strip=True)
                raw = (full[:500] + '…') if len(full) > 500 else full
            sentences = re.split(r'(?<=[\.!?])\s+', raw)
            snippet = " ".join(sentences[:2]).strip()
            prompt = f"Please summarize the following in two sentences:\n\n{snippet}"
            summary = ask_question(prompt)
            parts = re.split(r'(?<=[\.!?])\s+', summary)
            result = " ".join(parts[:2]).strip()
            if not result.endswith(('.', '!', '?')):
                result += '.'
            return result
        except Exception as e:
            return f"Search error: {e}"

    # Everything else, use LLM
    prompt = f"Imagine you're a friendly robot assistant named Sam. Reply to: {cmd}"
    answer = ask_question(prompt)
    return answer

# --- Flask endpoint ---
@app.route('/ai-command', methods=['POST'])
def ai_command():
    data = request.json
    cmd = data.get('command', '')
    if not cmd:
        return jsonify({"status": "error", "msg": "Comandă goală"})
    answer = process_command(cmd)
    return jsonify({"status": "ok", "msg": answer})

if __name__ == "__main__":
    print("SAM AI server started! Ascultă pe portul 5005 ...")
    app.run(host="0.0.0.0", port=5005)
