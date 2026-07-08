from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, jsonify, request
from groq import Groq
from datetime import datetime, timezone, timedelta

def now_ist():
    IST = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(IST).replace(tzinfo=None)
import json
import os
import requests
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

import base64
firebase_creds_b64 = os.environ.get("FIREBASE_CREDENTIALS_B64")
if firebase_creds_b64:
    import tempfile
    creds_json = base64.b64decode(firebase_creds_b64).decode("utf-8")
    creds_dict = json.loads(creds_json)
    cred = credentials.Certificate(creds_dict)
else:
    cred = credentials.Certificate("firebase-credentials.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

MESS_KNOWLEDGE = {
    "bad_dinner_days": ["Monday", "Thursday", "Saturday"],
    "mess_lunch_timing": "12:30 PM to 2:30 PM",
    "mess_dinner_timing": "7:30 PM to 9:30 PM",
    "lunch_significant": False,
    "notes": "Lunch footfall only increases when mess is completely closed"
}

POPULAR_ITEMS = {
    "snacks": ["Samosa", "Bun Butter Cheese", "Chips", "Ice Cream", "Cold Drinks", "Soft Drinks"],
    "meal_veg": ["Paneer dishes (any)", "Paneer Tikka", "Paneer Butter Masala", "Shahi Paneer"],
    "meal_nonveg": ["Chicken Biryani", "Mutton Biryani", "Any Non-veg Biryani"],
    "drinks": ["Cold Coffee", "Masala Cold Drinks", "Lemon Soda", "Badam Shake"]
}

MESS_MENU = {
    "Monday": {
        "lunch": "Dum Aloo, Dal Makhani, Butter Chicken, Hyderabadi Paneer",
        "dinner": "Veg Biryani, Kali Masoor Dal, Aloo Matar Tamatar, Roasted Chicken, Paneer Tikka, Rabdi Malpua",
        "dinner_quality": "BAD"
    },
    "Tuesday": {
        "lunch": "Egg Biryani, Paneer Lababdar, Raj Bhog",
        "dinner": "Chhola Kulcha, Kabab Roll, Matar Mushroom",
        "dinner_quality": "DECENT"
    },
    "Wednesday": {
        "lunch": "Chicken Bharra, Chilli Paneer, Hakka Noodles",
        "dinner": "Kadhai Paneer, Egg Curry, Panchratan Dal, Paani Poori, Besan Halwa",
        "dinner_quality": "DECENT"
    },
    "Thursday": {
        "lunch": "Chilli Chicken, Paneer Tikka Masala, Dahi Bhalla",
        "dinner": "Sev Tamatar, Lal Masoor Dal, Fish Finger, Crispy Corn, Chicken Changezi, Shahi Tukda",
        "dinner_quality": "BAD"
    },
    "Friday": {
        "lunch": "Fish Curry, Paneer Kathi Roll, Kalakand",
        "dinner": "Chhola Masala, Arhar Dal, Egg Roll, Paneer Korma, Chicken Biryani, Chandrakala",
        "dinner_quality": "GOOD"
    },
    "Saturday": {
        "lunch": "Paneer Khurchan, Moong Dal Halwa",
        "dinner": "Aloo Matar Tamatar, Moong Dal Tadka, Poori, Chicken Malai Tikka, Honey Chilli Potato, Paneer Do Pyaza",
        "dinner_quality": "BAD"
    },
    "Sunday": {
        "lunch": "Tawa Fish, Ras Malai, Chilli Mushroom",
        "dinner": "Paneer Korma, Chicken Korma, Garlic Naan, Pulao, Gulab Jamun",
        "dinner_quality": "GOOD"
    }
}

ACADEMIC_CALENDAR = {
    "2026-06-15": {"event": "Mid semester exam modular courses", "type": "exam"},
    "2026-06-16": {"event": "Mid semester exam modular courses", "type": "exam"},
    "2026-06-18": {"event": "Make-up examination", "type": "exam"},
    "2026-06-22": {"event": "Second half classes begin", "type": "classes_start"},
    "2026-07-10": {"event": "Classes end", "type": "classes_end"},
    "2026-07-13": {"event": "End semester examination", "type": "exam"},
    "2026-07-14": {"event": "End semester examination", "type": "exam"},
}

SEMESTER_PHASE = "Summer Term 2026 — fewer students on campus, mostly PG and research students"

def get_weather():
    try:
        api_key = os.environ.get("TOMORROW_API_KEY")
        url = f"https://api.tomorrow.io/v4/weather/forecast?location=26.5123,80.2329&apikey={api_key}&units=metric"
        response = requests.get(url, timeout=5)
        data = response.json()

        if "timelines" not in data:
            return None

        hourly = data["timelines"]["hourly"]
        
        forecasts = []
        for item in hourly[:4]:
            time = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
            time_ist = time + timedelta(hours=5, minutes=30)
            values = item["values"]
            
            temp = round(values.get("temperature", 0))
            feels_like = round(values.get("temperatureApparent", temp))
            humidity = round(values.get("humidity", 0))
            rain_prob = round(values.get("precipitationProbability", 0))
            wind_speed = round(values.get("windSpeed", 0))
            weather_code = values.get("weatherCode", 1000)
            
            condition_map = {
                1000: "Clear", 1100: "Clear", 1101: "Clouds",
                1102: "Clouds", 1001: "Clouds", 2000: "Fog",
                2100: "Fog", 4000: "Drizzle", 4001: "Rain",
                4200: "Rain", 4201: "Rain", 5000: "Snow",
                5001: "Snow", 5100: "Snow", 5101: "Snow",
                6000: "Drizzle", 6001: "Rain", 6200: "Rain",
                6201: "Rain", 7000: "Thunderstorm", 7101: "Thunderstorm",
                7102: "Thunderstorm", 8000: "Thunderstorm"
            }
            condition = condition_map.get(weather_code, "Clouds")
            
            forecasts.append({
                "time": time_ist.strftime("%I:%M %p"),
                "temp": temp,
                "feels_like": feels_like,
                "humidity": humidity,
                "condition": condition,
                "description": condition.lower(),
                "rain_probability": rain_prob,
                "wind_speed": wind_speed
            })

        current = forecasts[0] if forecasts else None

        if current:
            if current["condition"] == "Thunderstorm":
                impact = "SUDDEN STORM — chai, Maggi aur hot snacks ki demand spike hogi. Extra stock rakhna."
            elif current["condition"] in ["Rain", "Drizzle"] or current["rain_probability"] > 40:
                impact = "RAIN/DRIZZLE — chai aur hot snack demand HIGH. Samosa aur Maggi jaldi bikengi. Cold drinks demand kam hogi."
            elif current["temp"] > 42:
                impact = "EXTREME HEAT — cold drinks aur ice cream demand VERY HIGH shaam ko aur raat ko."
            elif current["temp"] > 38:
                impact = "HOT WEATHER — cold drinks aur ice cream demand HIGH. Thirst-driven snack rush expected."
            elif current["temp"] < 15:
                impact = "COLD WEATHER — chai aur hot snacks demand HIGH. Late night mein warm food zyada bikegi."
            else:
                impact = "PLEASANT WEATHER — standard snack demand. No weather-driven spike expected."

            return {
                "current": current,
                "forecasts": forecasts,
                "impact": impact
            }
        return None

    except Exception as e:
        print(f"Weather fetch error: {e}")
        return None

def get_weather_change_alert(current_weather):
    try:
        if not current_weather:
            return None

        weather_ref = db.collection("canteen").document("weather_history")
        weather_doc = weather_ref.get()

        yesterday_weather = None
        if weather_doc.exists:
            history = weather_doc.to_dict()
            yesterday_weather = history.get("yesterday")

        today_str = now_ist().strftime("%Y-%m-%d")
        
        if not yesterday_weather or yesterday_weather.get("date") == today_str:
            db.collection("canteen").document("weather_history").set({
                "yesterday": {
                    "temp": current_weather["temp"],
                    "condition": current_weather["condition"],
                    "rain_probability": current_weather["rain_probability"],
                    "date": today_str
                }
            })
            return None

        prev_temp = yesterday_weather.get("temp", current_weather["temp"])
        prev_condition = yesterday_weather.get("condition", "Clear")
        prev_rain = yesterday_weather.get("rain_probability", 0)

        curr_temp = current_weather["temp"]
        curr_condition = current_weather["condition"]
        curr_rain = current_weather["rain_probability"]

        alert = None

        if curr_rain > 60 and prev_rain < 20:
            alert = {
                "type": "SUDDEN_RAIN",
                "message": "Achanak barish aa rahi hai — chai aur hot snacks ki demand suddenly badh sakti hai. Samosa aur Maggi extra rakhna."
            }
        elif curr_condition == "Thunderstorm" and prev_condition not in ["Thunderstorm", "Rain"]:
            alert = {
                "type": "STORM",
                "message": "Achanak toofan — students bahar nahi niklenge. Late night canteen rush drop ho sakta hai."
            }
        elif curr_temp > prev_temp + 4 and curr_temp > 40:
            alert = {
                "type": "HEAT_SPIKE",
                "message": f"Temperature achanak {curr_temp}°C — kal se kaafi zyada garmi. Cold drinks aur ice cream ka stock check karo shaam se pehle."
            }

        db.collection("canteen").document("weather_history").set({
            "yesterday": {
                "temp": curr_temp,
                "condition": curr_condition,
                "rain_probability": curr_rain,
                "date": today_str
            }
        })

        return alert

    except Exception as e:
        print(f"Weather alert error: {e}")
        return None

def get_mess_menu():
    try:
        doc_ref = db.collection("canteen").document("mess_menu")
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            return data.get("menu", MESS_MENU), data.get("uploaded_at", "hardcoded default")
        return MESS_MENU, "hardcoded default"
    except Exception as e:
        print(f"Menu fetch error: {e}")
        return MESS_MENU, "hardcoded default"

def assess_dinner_quality(dinner_main, dinner_extra):
    main_lower = dinner_main.lower()
    extra_lower = dinner_extra.lower() if dinner_extra else ""
    
    paneer_keywords = ["paneer", "kadhai paneer", "shahi paneer", 
                       "paneer tikka", "paneer korma", "paneer butter",
                       "paneer do pyaza", "paneer khurchan", "paneer lababdar"]
    
    chicken_keywords = ["murgh", "roasted chicken", "butter chicken",
                        "chicken biryani", "chicken changezi", 
                        "chicken malai", "chicken korma"]
    
    good_extra_keywords = ["fish finger", "roasted chicken", "butter chicken",
                           "chicken biryani", "chicken changezi", "chicken malai",
                           "chicken korma", "malai tikka", "chaat", "aloo chaat",
                           "samosa chaat"]
    
    has_paneer_main = any(k in main_lower for k in paneer_keywords)
    has_chicken_main = any(k in main_lower for k in chicken_keywords)
    
    if has_paneer_main or has_chicken_main:
        return "GOOD"
    
    has_good_extra = any(k in extra_lower for k in good_extra_keywords)
    if has_good_extra:
        return "DECENT"
    
    return "BAD"

def save_mess_menu(menu_dict):
    try:
        for day in menu_dict:
            dinner_main = menu_dict[day].get("dinner", "")
            dinner_extra = menu_dict[day].get("dinner_extra", "")
            menu_dict[day]["dinner_quality"] = assess_dinner_quality(dinner_main, dinner_extra)
        
        doc_ref = db.collection("canteen").document("mess_menu")
        previous = doc_ref.get()
        if previous.exists:
            db.collection("canteen").document("mess_menu_backup").set(previous.to_dict())
        doc_ref.set({
            "menu": menu_dict,
            "uploaded_at": now_ist().strftime("%Y-%m-%d %H:%M")
        })
        return True
    except Exception as e:
        print(f"Menu save error: {e}")
        return False

def extract_menu_from_image(image_bytes, mime_type="image/jpeg"):
    try:
        import base64
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        
        prompt = """You are reading a mess menu from IIT Kanpur Hall 12.

The menu table has these columns in this exact order:
Day | Breakfast (IGNORE) | Lunch | Extra Lunch | Dinner | Extra Dinner

Rules:
- Main columns (Lunch, Dinner) contain regular included mess items
- Extra columns (Extra Lunch, Extra Dinner) contain paid special items
- Breakfast column must be completely ignored
- Never mix main and extra items together
- Read colored text columns as extra items

Return ONLY a valid JSON object in this exact format, nothing else:

{
  "Monday": {
    "lunch": "main lunch items only",
    "lunch_extra": "paid extra lunch items only",
    "dinner": "main dinner items only",
    "dinner_extra": "paid extra dinner items only",
    "dinner_quality": "BAD or DECENT or GOOD"
  },
  "Tuesday": {
    "lunch": "main lunch items only",
    "lunch_extra": "paid extra lunch items only",
    "dinner": "main dinner items only",
    "dinner_extra": "paid extra dinner items only",
    "dinner_quality": "BAD or DECENT or GOOD"
  },
  "Wednesday": {
    "lunch": "main lunch items only",
    "lunch_extra": "paid extra lunch items only",
    "dinner": "main dinner items only",
    "dinner_extra": "paid extra dinner items only",
    "dinner_quality": "BAD or DECENT or GOOD"
  },
  "Thursday": {
    "lunch": "main lunch items only",
    "lunch_extra": "paid extra lunch items only",
    "dinner": "main dinner items only",
    "dinner_extra": "paid extra dinner items only",
    "dinner_quality": "BAD or DECENT or GOOD"
  },
  "Friday": {
    "lunch": "main lunch items only",
    "lunch_extra": "paid extra lunch items only",
    "dinner": "main dinner items only",
    "dinner_extra": "paid extra dinner items only",
    "dinner_quality": "BAD or DECENT or GOOD"
  },
  "Saturday": {
    "lunch": "main lunch items only",
    "lunch_extra": "paid extra lunch items only",
    "dinner": "main dinner items only",
    "dinner_extra": "paid extra dinner items only",
    "dinner_quality": "BAD or DECENT or GOOD"
  },
  "Sunday": {
    "lunch": "main lunch items only",
    "lunch_extra": "paid extra lunch items only",
    "dinner": "main dinner items only",
    "dinner_extra": "paid extra dinner items only",
    "dinner_quality": "BAD or DECENT or GOOD"
  }
}

For dinner_quality — follow these rules STRICTLY:

STEP 1: Look at MAIN dinner items only. Does it contain paneer (any dish) or chicken (any dish)?
- YES → dinner_quality = "GOOD". Stop here. Do not look at extra.
- NO → go to STEP 2.

STEP 2: Look at extra dinner items. Does it contain fish finger, chicken dish, or chaat/fast food snacks?
- YES → dinner_quality = "DECENT"
- NO → dinner_quality = "BAD"

IMPORTANT: Extra items containing paneer or chicken do NOT make quality GOOD. Only main items can make quality GOOD.
Return only the JSON. No markdown, no explanation, nothing else."""

        response = groq_client.chat.completions.create(
    model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            max_tokens=1000,
            temperature=0.1
        )
        
        result = response.choices[0].message.content.strip()
        result = result.replace("```json", "").replace("```", "").strip()
        menu_dict = json.loads(result)
        return menu_dict
        
    except Exception as e:
        print(f"Menu extraction error: {e}")
        return None

def extract_menu_from_pdf(pdf_bytes):
    try:
        import fitz
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
            f.write(pdf_bytes)
            temp_path = f.name
        
        doc = fitz.open(temp_path)
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("jpeg")
        doc.close()
        os.unlink(temp_path)
        
        return extract_menu_from_image(img_bytes, "image/jpeg")
        
    except Exception as e:
        print(f"PDF extraction error: {e}")
        return None

def load_feedback():
    try:
        doc_ref = db.collection("canteen").document("feedback")
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return {"history": [], "permanent_adjustments": {}, "pattern_alerts": []}
    except Exception as e:
        print(f"Firebase read error: {e}")
        return {"history": [], "permanent_adjustments": {}, "pattern_alerts": []}

def save_feedback(data):
    try:
        doc_ref = db.collection("canteen").document("feedback")
        doc_ref.set(data)
    except Exception as e:
        print(f"Firebase write error: {e}")

def analyze_patterns(feedback_data):
    history = feedback_data.get("history", [])
    if len(history) < 3:
        return None
    recent = history[-7:] if len(history) >= 7 else history
    day_scores = {}
    for entry in recent:
        day = entry.get("day")
        score = entry.get("score")
        if score is None:
            continue
        if day not in day_scores:
            day_scores[day] = []
        day_scores[day].append(score)
    alerts = []
    for day, scores in day_scores.items():
        if len(scores) >= 2:
            avg_score = sum(scores) / len(scores)
            if avg_score <= 1.5:
                alerts.append({
                    "type": "consistent_negative",
                    "day": day,
                    "message": f"{day} predictions are consistently wrong. Should I permanently adjust?"
                })
            elif avg_score >= 4.5:
                alerts.append({
                    "type": "consistent_positive",
                    "day": day,
                    "message": f"{day} predictions are consistently accurate. Pattern confirmed."
                })
    return alerts if alerts else None

def log_usage(request):
    try:
        user_agent = request.headers.get('User-Agent', 'unknown')
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        today = now_ist()
        
        device = "unknown"
        if 'android' in user_agent.lower():
            device = "Android"
        if 'iphone' in user_agent.lower():
            device = "iPhone"
        
        import re
        model_match = re.search(r';\s*([A-Z0-9]+)\)', user_agent)
        device_model = model_match.group(1) if model_match else "unknown"
        
        log_entry = {
            "timestamp": today.strftime("%Y-%m-%d %H:%M:%S"),
            "date": today.strftime("%Y-%m-%d"),
            "day": today.strftime("%A"),
            "time": today.strftime("%H:%M"),
            "device": device,
            "device_model": device_model,
            "user_agent": user_agent,
            "ip_address": ip_address
        }
        
        db.collection("canteen").document("usage_log").collection("sessions").add(log_entry)
        print(f"Usage logged: {today.strftime('%Y-%m-%d %H:%M')} from {device} {device_model}")
        
    except Exception as e:
        print(f"Usage log error: {e}")

def get_full_context(realtime_instruction=None):
    today = now_ist()
    date_str = today.strftime("%Y-%m-%d")
    day_name = today.strftime("%A")
    time_now = today.strftime("%H:%M")
    hour = today.hour

    academic_event = ACADEMIC_CALENDAR.get(date_str, {})
    
    try:
        events_ref = db.collection("canteen").document("events")
        events_doc = events_ref.get()
        hostel_event = None
        quiz_week_active = False
        if events_doc.exists:
            events_data = events_doc.to_dict()
            events = events_data.get("events", {})
            hostel_event = events.get(date_str)
            quiz_week_active = events_data.get("quiz_week_active", False)
    except:
        hostel_event = None
        quiz_week_active = False
    
    current_menu, menu_source = get_mess_menu()
    mess_today = current_menu.get(day_name, {})
    feedback_data = load_feedback()
    recent_feedback = feedback_data["history"][-5:] if feedback_data["history"] else []
    permanent_adjustments = feedback_data.get("permanent_adjustments", {})

    if hour < 12:
        meal_period = "morning — predicting for lunch and dinner"
    elif hour < 15:
        meal_period = "lunch time — mess is open, predicting for dinner and late night"
    elif hour < 20:
        meal_period = "evening — mess dinner starting soon at 7:30pm, predicting dinner rush"
    elif hour < 22:
        meal_period = "mess dinner time 7:30-9:30pm — predicting post-mess and late night rush"
    else:
        meal_period = "late night — main canteen rush period"

    current_menu, menu_source = get_mess_menu()
    mess_today = current_menu.get(day_name, {})
    dinner_quality = mess_today.get("dinner_quality", "DECENT")
    dinner_main = mess_today.get("dinner", "")
    dinner_extra = mess_today.get("dinner_extra", "")
    lunch_extra = mess_today.get("lunch_extra", "")
    
    is_bad_dinner_day = dinner_quality == "BAD"
    is_decent_dinner_day = dinner_quality == "DECENT"
    is_good_dinner_day = dinner_quality == "GOOD"

    if is_good_dinner_day:
        dinner_quality_desc = "students will prefer mess, canteen dinner footfall will be LOW"
    elif is_decent_dinner_day:
        dinner_quality_desc = "mixed — some students go to extra counter, canteen dinner footfall MEDIUM"
    else:
        dinner_quality_desc = "students likely to consider canteen for dinner, footfall will be HIGH"

    if day_name in ['Saturday', 'Sunday']:
        day_lunch_desc = "Weekend — lunch canteen footfall possible if mess lunch is not good"
    else:
        day_lunch_desc = "Weekday — lunch canteen footfall LOW regardless of menu"

    weather_data = get_weather()
    weather_alert = get_weather_change_alert(weather_data["current"]) if weather_data else None
    print(f"Weather data: {weather_data}")

    print("Building context...")
    context = f"""
You are an AI assistant for Anoop, owner of Hall 12 Canteen at IIT Kanpur.
Your job is to give him a daily demand prediction in Hindi/Hinglish like a helpful friend.

=== TODAY'S CONTEXT ===
Date: {date_str}
Day: {day_name}
Current time: {time_now}
Meal period: {meal_period}

=== ACADEMIC SITUATION ===
Semester: {SEMESTER_PHASE}
Today's academic event: {academic_event.get('event', 'Regular day')} ({academic_event.get('type', 'normal')})

=== HOSTEL EVENTS TODAY ===
{f"Event: {hostel_event['name']} — Expected impact: {hostel_event['impact']}" if hostel_event else "No special hostel events today"}

=== TODAY'S MESS MENU ===
Mess lunch (12:30-2:30pm): {mess_today.get('lunch', 'Unknown')}
Mess lunch extra (paid): {lunch_extra or 'None'}
Mess dinner (7:30-9:30pm): {dinner_main or 'Unknown'}
Mess dinner extra (paid): {dinner_extra or 'None'}
Mess dinner quality: {dinner_quality}
Dinner quality reasoning: {'GOOD — main dinner has paneer/chicken, students prefer mess' if is_good_dinner_day else 'DECENT — main dinner basic but extra has quality items' if is_decent_dinner_day else 'BAD — main dinner basic, extra also not exciting, students may prefer canteen'}

=== WEATHER CONDITIONS IN KANPUR TODAY ===
{f'''
Current temperature: {weather_data["current"]["temp"]}°C (feels like {weather_data["current"]["feels_like"]}°C)
Condition: {weather_data["current"]["condition"]} — {weather_data["current"]["description"]}
Rain probability: {weather_data["current"]["rain_probability"]}%
Humidity: {weather_data["current"]["humidity"]}%
Wind speed: {weather_data["current"]["wind_speed"]} m/s
Weather impact on footfall: {weather_data["impact"]}

Upcoming forecast:
{chr(10).join([f'  {f["time"]}: {f.get("temp","?")}°C, {f.get("condition","?")}, Rain: {f.get("rain_probability","?")}%' for f in weather_data["forecasts"][1:]])}
''' if weather_data else "Weather data unavailable — proceed without weather context"}

=== BEHAVIORAL PATTERNS (validated through observation and merchant conversations) ===
Dinner footfall logic:
- GOOD mess dinner (paneer/chicken in main): Students strongly prefer mess. Canteen dinner footfall LOW. Late night still busy.
- DECENT mess dinner (good items only in extra): Some students stay in mess for extra. Canteen dinner footfall MEDIUM.
- BAD mess dinner (nothing exciting in main or extra): Students consider canteen for dinner. Canteen dinner footfall HIGH.

Today's dinner quality: {dinner_quality} — {dinner_quality_desc}

Lunch footfall logic:
- Weekday lunch: Students have classes, they eat in mess regardless of menu. Canteen lunch footfall LOW.
- Saturday/Sunday/Holiday lunch: Students have freedom. If lunch menu is bad, some may come to canteen.
- Today is {day_name}: {day_lunch_desc}

Late night 10pm-2am: Always busy regardless of mess quality. This is the most reliable rush period.

Two meals effect: On weekends/holidays, if students came to canteen for lunch, only 2-3 out of 10 will come again for dinner. Midnight snacking is separate and not affected.

Weather effect on snacks (NOT on meal decisions — both mess and canteen are inside hostel):
- Extreme heat (above 40C): Cold drinks and ice cream demand HIGH in evening
- Sudden rain: Chai and hot snack demand spikes unexpectedly  
- Normal weather: Standard evening snack pattern

Exam/quiz season effect on midnight rush:
- During mid-sem/end-sem exam weeks: Midnight rush significantly higher than normal
- Quiz weeks (manually flagged): Moderate increase in midnight rush
- Quiz week currently active: {quiz_week_active}
{f"IMPORTANT: Quiz week is ON — midnight rush will be HIGHER than normal tonight. Students studying late will come for snacks." if quiz_week_active else ""}

=== MOST POPULAR ITEMS ===
Snacks: {', '.join(POPULAR_ITEMS['snacks'])}
Popular veg meal: {', '.join(POPULAR_ITEMS['meal_veg'])}
Popular non-veg: {', '.join(POPULAR_ITEMS['meal_nonveg'])}

=== PERMANENT ADJUSTMENTS FROM FEEDBACK ===
{json.dumps(permanent_adjustments, indent=2) if permanent_adjustments else 'None yet'}

=== RECENT FEEDBACK (last 5 days) ===
{json.dumps(recent_feedback, indent=2) if recent_feedback else 'No feedback yet'}

=== STRUCTURED INSIGHTS FROM FEEDBACK NOTES ===
{chr(10).join([
    f"- {h.get('day')} {h.get('date')}: stockout={h['parsed_note'].get('stockout_item')}, footfall={h['parsed_note'].get('footfall_vs_prediction')}, issue={h['parsed_note'].get('issue')}, positive={h['parsed_note'].get('positive')}"
    for h in recent_feedback 
    if h.get('parsed_note') and any(v for v in h['parsed_note'].values() if v)
]) if any(h.get('parsed_note') for h in recent_feedback) else 'No structured insights yet — feedback notes will be analysed as they come in'}
"""

    if realtime_instruction:
        context += f"""
=== REAL TIME INSTRUCTION FROM OWNER (HIGHEST PRIORITY) ===
{realtime_instruction}
NOTE: This real-time instruction overrides all other predictions. Give it maximum weightage.
"""

    context += """
=== YOUR TASK ===
Generate a prediction message for Anoop in Hindi/Hinglish like a helpful friend WhatsApp message.
Include:
1. Overall footfall: LOW / MEDIUM / HIGH
2. Which time slot will be busiest and why
3. Top 3 specific items to prep more of
4. One practical tip
Keep under 100 words. Warm and conversational. Start with "Bhai,".
Do NOT use any markdown formatting. Plain text only.
Only output the message. Nothing else.
"""

    return context, {
        "dinner_quality": dinner_quality,
        "is_bad_dinner_day": is_bad_dinner_day
    }

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/predict", methods=["GET", "POST"])
def predict():
    try:
        realtime_instruction = None
        if request.method == "POST":
            data = request.get_json()
            realtime_instruction = data.get("instruction")

        log_usage(request)
        context, menu_meta = get_full_context(realtime_instruction)
        dinner_quality = menu_meta["dinner_quality"]
        is_bad_dinner_day = menu_meta["is_bad_dinner_day"]

        reasoning_prompt = context + """
=== YOUR TASK — CALL 1: STRUCTURED REASONING ===
Analyze all the context above and return ONLY a valid JSON object.
No explanation, no markdown, no extra text. Just the JSON.

{
  "footfall_level": "HIGH or MEDIUM or LOW",
  "confidence": 0.0 to 1.0,
  "busiest_slot": "e.g. 10pm - 2am",
  "reasoning": "2-3 sentence explanation of why in English",
  "top_items": ["item1", "item2", "item3"],
  "practical_tip": "One specific actionable tip for Anoop in English",
  "weather_factor": "HIGH or LOW or NONE",
  "mess_factor": "HIGH or LOW or NONE",
  "academic_factor": "HIGH or LOW or NONE"
}

Base your decision on all signals: mess quality, day of week, weather, academic calendar, hostel events, time of day, and feedback history.
Return ONLY the JSON. Nothing else.
"""

        reasoning_response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a demand prediction engine. Return only valid JSON. No markdown, no explanation, no extra text."
                },
                {
                    "role": "user",
                    "content": reasoning_prompt
                }
            ],
            max_tokens=400,
            temperature=0.3
        )

        reasoning_text = reasoning_response.choices[0].message.content.strip()
        reasoning_text = reasoning_text.replace("```json", "").replace("```", "").strip()
        
        try:
            structured = json.loads(reasoning_text)
        except:
            structured = {
                "footfall_level": "MEDIUM",
                "confidence": 0.5,
                "busiest_slot": "10pm - 2am",
                "reasoning": "Could not parse structured response",
                "top_items": ["Samosa", "Cold Drinks", "Paneer Tikka"],
                "practical_tip": "Stock standard items",
                "weather_factor": "NONE",
                "mess_factor": "NONE",
                "academic_factor": "NONE"
            }

        hindi_prompt = f"""
You are an operational assistant for Anoop, owner of Hall 12 canteen at IIT Kanpur.

Based on this analysis:
- Footfall today: {structured['footfall_level']}
- Busiest time: {structured['busiest_slot']}
- Top items to prep: {', '.join(structured['top_items'])}
- Key reason: {structured['reasoning']}
- Practical tip: {structured['practical_tip']}

Write a short Hinglish message to Anoop. Start with "Bhai,".
The items to prep are already shown above — do NOT list them again.
Instead focus on: the RIGHT TIME to start preparation, any specific insight about today that changes his routine, and one thing he might miss if he doesn't act now.
Keep it under 45 words. Warm, practical, specific to today.
Do NOT use markdown. Only output the message.
"""

        hindi_response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You write warm Hindi/Hinglish messages. Never use markdown formatting like ** or *."
                },
                {
                    "role": "user",
                    "content": hindi_prompt
                }
            ],
            max_tokens=200,
            temperature=0.7
        )

        hindi_message = hindi_response.choices[0].message.content.strip()
        weather_data = get_weather()
        today = now_ist()
        feedback_data = load_feedback()
        pattern_alerts = analyze_patterns(feedback_data)

        today_str = today.strftime("%Y-%m-%d")
        already_logged_today = any(
            h.get("date") == today_str 
            for h in feedback_data.get("history", [])
        )
        
        if not already_logged_today:
            prediction_entry = {
                "date": today_str,
                "day": today.strftime("%A"),
                "time": today.strftime("%H:%M"),
                "predicted_level": structured.get("footfall_level", "MEDIUM"),
                "score": None,
                "note": ""
            }
            feedback_data["history"].append(prediction_entry)
            save_feedback(feedback_data)

        return jsonify({
            "prediction": hindi_message,
            "structured": structured,
            "date": today.strftime("%d %B %Y"),
            "day": today.strftime("%A"),
            "time": today.strftime("%I:%M %p"),
            "mess_quality": dinner_quality,
            "is_bad_mess_day": is_bad_dinner_day,
            "pattern_alert": pattern_alerts[0] if pattern_alerts else None,
            "weather": weather_data["current"] if weather_data else None,
            "weather_impact": weather_data["impact"] if weather_data else None
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/feedback", methods=["POST"])
def feedback():
    try:
        data = request.get_json()
        score = data.get("score")
        predicted_level = data.get("predicted_level")
        note = data.get("note", "")
        today = now_ist()

        feedback_data = load_feedback()
        entry = {
            "date": today.strftime("%Y-%m-%d"),
            "day": today.strftime("%A"),
            "time": today.strftime("%H:%M"),
            "score": score,
            "predicted_level": predicted_level,
            "note": note
        }
        is_pending_update = data.get("is_pending_update", False)
        pending_date = data.get("date")
        
        if is_pending_update and pending_date:
            updated = False
            for i, h in enumerate(feedback_data["history"]):
                if h.get("date") == pending_date and not h.get("score"):
                    feedback_data["history"][i]["score"] = score
                    feedback_data["history"][i]["note"] = note
                    updated = True
                    break
            if not updated:
                feedback_data["history"].append(entry)
        else:
            feedback_data["history"].append(entry)
        pattern_alerts = analyze_patterns(feedback_data)
        if pattern_alerts:
            feedback_data["pattern_alerts"] = pattern_alerts

        if note and len(note.strip()) > 3:
            try:
                parse_response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {
                            "role": "system",
                            "content": "You extract structured data from canteen feedback notes. Return only valid JSON."
                        },
                        {
                            "role": "user",
                            "content": f"""Extract structured information from this canteen feedback note: "{note}"

Return ONLY a JSON object with these fields (use null if not mentioned):
{{
  "stockout_item": "item that ran out (string or null)",
  "footfall_vs_prediction": "higher/lower/as_expected/null",
  "weather_impact": "yes/no/null",
  "issue": "brief description of main issue (string or null)",
  "positive": "brief description of what went well (string or null)"
}}

Return only the JSON. Nothing else."""
                        }
                    ],
                    max_tokens=150,
                    temperature=0.1
                )
                parsed_text = parse_response.choices[0].message.content.strip()
                parsed_text = parsed_text.replace("```json", "").replace("```", "").strip()
                parsed_data = json.loads(parsed_text)
                
                if is_pending_update and pending_date:
                    for i, h in enumerate(feedback_data["history"]):
                        if h.get("date") == pending_date:
                            feedback_data["history"][i]["parsed_note"] = parsed_data
                            break
                else:
                    if feedback_data["history"]:
                        feedback_data["history"][-1]["parsed_note"] = parsed_data
                        
            except Exception as parse_error:
                print(f"Note parsing error: {parse_error}")

        save_feedback(feedback_data)

        return jsonify({
            "status": "saved",
            "pattern_alert": pattern_alerts[0] if pattern_alerts else None
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/adjust", methods=["POST"])
def adjust():
    try:
        data = request.get_json()
        day = data.get("day")
        adjustment = data.get("adjustment")
        feedback_data = load_feedback()
        if "permanent_adjustments" not in feedback_data:
            feedback_data["permanent_adjustments"] = {}
        feedback_data["permanent_adjustments"][day] = adjustment
        save_feedback(feedback_data)
        return jsonify({"status": "adjusted", "day": day, "adjustment": adjustment})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/upload-menu", methods=["POST"])
def upload_menu():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files["file"]
        filename = file.filename.lower()
        file_bytes = file.read()
        
        if filename.endswith(".pdf"):
            menu_dict = extract_menu_from_pdf(file_bytes)
        elif filename.endswith((".jpg", ".jpeg", ".png")):
            menu_dict = extract_menu_from_image(file_bytes)
        else:
            return jsonify({"error": "Only PDF, JPG, or PNG files accepted"}), 400
        
        if not menu_dict:
            return jsonify({"error": "Could not extract menu from file"}), 500
        
        success = save_mess_menu(menu_dict)
        if success:
            return jsonify({"status": "success", "menu": menu_dict})
        else:
            return jsonify({"error": "Could not save menu"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/revert-menu", methods=["POST"])
def revert_menu():
    try:
        backup_ref = db.collection("canteen").document("mess_menu_backup")
        backup = backup_ref.get()
        if backup.exists:
            db.collection("canteen").document("mess_menu").set(backup.to_dict())
            return jsonify({"status": "reverted"})
        else:
            db.collection("canteen").document("mess_menu").delete()
            return jsonify({"status": "reverted to hardcoded default"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get-menu", methods=["GET"])
def get_menu():
    try:
        current_menu, menu_source = get_mess_menu()
        return jsonify({"menu": current_menu, "source": menu_source})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/add-event", methods=["POST"])
def add_event():
    try:
        data = request.get_json()
        date = data.get("date")
        name = data.get("name")
        impact = data.get("impact")
        
        events_ref = db.collection("canteen").document("events")
        events_doc = events_ref.get()
        
        if events_doc.exists:
            events = events_doc.to_dict().get("events", {})
        else:
            events = {}
            
        events[date] = {"name": name, "impact": impact}
        events_ref.set({"events": events})
        
        return jsonify({"status": "saved", "date": date, "name": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/history", methods=["GET"])
def history():
    try:
        feedback_data = load_feedback()
        return jsonify({"history": feedback_data.get("history", [])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/pending-feedback", methods=["GET"])
def pending_feedback():
    try:
        feedback_data = load_feedback()
        history = feedback_data.get("history", [])
        
        today = now_ist().strftime("%Y-%m-%d")
        
        from datetime import timedelta
        yesterday = (now_ist() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        pending = None
        for entry in reversed(history):
            if entry.get("date") == yesterday and not entry.get("score"):
                pending = entry
                break
       
        return jsonify({"pending": pending})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/accuracy", methods=["GET"])
def accuracy():
    try:
        feedback_data = load_feedback()
        history = feedback_data.get("history", [])
        
        if not history:
            return jsonify({"weeks": [], "overall": 0})
        
        from datetime import datetime, timedelta
        
        weeks = {}
        for entry in history:
            if not entry.get("score"):
                continue
            try:
                date = datetime.strptime(entry["date"], "%Y-%m-%d")
                app_start = datetime.strptime("2026-06-19", "%Y-%m-%d")
                if date < app_start:
                    continue
                days_since_start = (date - app_start).days
                week_num = days_since_start // 7 + 1
                week_key = f"Week {week_num}"
                if week_key not in weeks:
                    weeks[week_key] = {"total": 0, "total_score": 0, "start_date": entry["date"]}
                weeks[week_key]["total"] += 1
                weeks[week_key]["total_score"] += entry["score"]
            except:
                continue
        
        week_list = []
        week_starts = {
            1: "Jun 19",
            2: "Jun 27",
            3: "Jul 4",
            4: "Jul 11"
        }
        week_list = []
        for week_key, data in sorted(weeks.items(), key=lambda x: int(x[0].split()[1])):
            avg_score = round(data["total_score"] / data["total"], 1) if data["total"] > 0 else 0
            accuracy_pct = round((avg_score / 5) * 100) if data["total"] > 0 else 0
            week_num = int(week_key.split()[1])
            week_list.append({
                "week": week_starts.get(week_num, week_key),
                "total": data["total"],
                "avg_score": avg_score,
                "accuracy": accuracy_pct,
                "start_date": data["start_date"]
            })
        
        overall_score = round(sum(w["avg_score"] for w in week_list) / len(week_list), 1) if week_list else 0
        overall = round((overall_score / 5) * 100) if week_list else 0
        
        return jsonify({"weeks": week_list, "overall": overall})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/quiz-week", methods=["POST"])
def quiz_week():
    try:
        data = request.get_json()
        active = data.get("active", False)
        
        events_ref = db.collection("canteen").document("events")
        events_doc = events_ref.get()
        
        if events_doc.exists:
            events_data = events_doc.to_dict()
        else:
            events_data = {"events": {}}
            
        events_data["quiz_week_active"] = active
        events_ref.set(events_data)
        
        return jsonify({"status": "saved", "quiz_week_active": active})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/quiz-week-status", methods=["GET"])
def quiz_week_status():
    try:
        events_ref = db.collection("canteen").document("events")
        events_doc = events_ref.get()
        active = False
        if events_doc.exists:
            active = events_doc.to_dict().get("quiz_week_active", False)
        return jsonify({"quiz_week_active": active})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/mess-status", methods=["GET"])
def mess_status():
    try:
        today = now_ist()
        day_name = today.strftime("%A")
        current_menu, menu_source = get_mess_menu()
        mess_today = current_menu.get(day_name, {})
        dinner_quality = mess_today.get("dinner_quality", "DECENT")
        dinner_main = mess_today.get("dinner", "")
        dinner_extra = mess_today.get("dinner_extra", "")
        
        is_bad = dinner_quality == "BAD"
        is_good = dinner_quality == "GOOD"
        
        return jsonify({
            "dinner_quality": dinner_quality,
            "dinner_main": dinner_main,
            "dinner_extra": dinner_extra,
            "is_bad_dinner_day": is_bad,
            "is_good_dinner_day": is_good,
            "day": day_name
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)