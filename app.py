from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, jsonify, request
import google.generativeai as genai
from datetime import datetime
import json
import os
import base64

app = Flask(__name__)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# ============================================================
# PERMANENT KNOWLEDGE BASE
# Based on 3 years of observation by Hall 12 resident
# ============================================================

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
    "2026-06-12": {"event": "Last day of modular courses first half", "type": "academic_end"},
    "2026-06-13": {"event": "No academic activity", "type": "holiday"},
    "2026-06-14": {"event": "No academic activity", "type": "holiday"},
    "2026-06-15": {"event": "Mid semester exam modular courses", "type": "exam"},
    "2026-06-16": {"event": "Mid semester exam modular courses", "type": "exam"},
    "2026-06-18": {"event": "Make-up examination", "type": "exam"},
    "2026-06-22": {"event": "Second half classes begin", "type": "classes_start"},
    "2026-07-10": {"event": "Classes end", "type": "classes_end"},
    "2026-07-13": {"event": "End semester examination", "type": "exam"},
    "2026-07-14": {"event": "End semester examination", "type": "exam"},
}

SEMESTER_PHASE = {
    "summer_term": {
        "start": "2026-05-21",
        "end": "2026-07-24",
        "student_count": "LOW",
        "notes": "Summer term — fewer students on campus, mostly PG and research students"
    }
}

# ============================================================
# FEEDBACK STORAGE
# ============================================================

FEEDBACK_FILE = "feedback_history.json"

def load_feedback():
    if os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE, "r") as f:
            return json.load(f)
    return {"history": [], "permanent_adjustments": {}, "pattern_alerts": []}

def save_feedback(data):
    with open(FEEDBACK_FILE, "w") as f:
        json.dump(data, f, indent=2)

def analyze_patterns(feedback_data):
    history = feedback_data.get("history", [])
    if len(history) < 3:
        return None
    
    recent = history[-7:] if len(history) >= 7 else history
    
    day_scores = {}
    for entry in recent:
        day = entry.get("day")
        score = entry.get("score", 3)
        predicted = entry.get("predicted_level")
        if day not in day_scores:
            day_scores[day] = []
        day_scores[day].append({"score": score, "predicted": predicted})
    
    alerts = []
    for day, scores in day_scores.items():
        if len(scores) >= 2:
            avg_score = sum(s["score"] for s in scores) / len(scores)
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

# ============================================================
# CONTEXT BUILDER
# ============================================================

def get_full_context(realtime_instruction=None, realtime_image=None):
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    day_name = today.strftime("%A")
    time_now = today.strftime("%H:%M")
    hour = today.hour

    academic_event = ACADEMIC_CALENDAR.get(date_str, {})
    mess_today = MESS_MENU.get(day_name, {})
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
        meal_period = "mess dinner time (7:30-9:30pm) — predicting post-mess and late night rush"
    else:
        meal_period = "late night — main canteen rush period"

    is_bad_dinner_day = day_name in MESS_KNOWLEDGE["bad_dinner_days"]

    context = f"""
You are an AI assistant for Anoop, owner of Hall 12 Canteen at IIT Kanpur.
Your job is to give him a daily demand prediction in Hindi/Hinglish like a helpful friend.

=== TODAY'S CONTEXT ===
Date: {date_str}
Day: {day_name}
Current time: {time_now}
Meal period: {meal_period}

=== ACADEMIC SITUATION ===
Semester: Summer Term 2026 (fewer students on campus, mostly PG/research)
Today's academic event: {academic_event.get('event', 'Regular day')} ({academic_event.get('type', 'normal')})

=== TODAY'S MESS MENU ===
Mess lunch (12:30-2:30pm): {mess_today.get('lunch', 'Unknown')}
Mess dinner (7:30-9:30pm): {mess_today.get('dinner', 'Unknown')}
Mess dinner quality assessment: {mess_today.get('dinner_quality', 'DECENT')}

=== BEHAVIORAL PATTERNS (3 years of observation) ===
Bad mess dinner days (high canteen footfall): Monday, Thursday, Saturday
Today is a bad mess dinner day: {is_bad_dinner_day}
Lunch footfall: Only significant when mess is completely closed
Late night (10pm-2am): Always busy regardless of mess quality

=== MOST POPULAR ITEMS ===
Snacks (always recommend stocking): {', '.join(POPULAR_ITEMS['snacks'])}
Popular veg meal: {', '.join(POPULAR_ITEMS['meal_veg'])}
Popular non-veg: {', '.join(POPULAR_ITEMS['meal_nonveg'])}

=== PERMANENT ADJUSTMENTS FROM FEEDBACK ===
{json.dumps(permanent_adjustments, indent=2) if permanent_adjustments else 'None yet'}

=== RECENT FEEDBACK (last 5 days) ===
{json.dumps(recent_feedback, indent=2) if recent_feedback else 'No feedback yet — first few days of usage'}
"""

    if realtime_instruction:
        context += f"""
=== REAL TIME INSTRUCTION FROM OWNER (HIGHEST PRIORITY) ===
{realtime_instruction}
NOTE: This real-time instruction overrides all other predictions. Give it maximum weightage.
"""

    if realtime_image:
        context += """
=== IMAGE PROVIDED ===
An image has been shared with additional context. Analyze it and incorporate into prediction.
"""

    context += """
=== YOUR TASK ===
Generate a prediction message for Anoop in Hindi/Hinglish (like a helpful friend WhatsApp message).

The message must include:
1. Overall footfall prediction: LOW / MEDIUM / HIGH
2. Which specific time slot will be busiest and why
3. Top 3 specific items to prep more of (use actual canteen menu items)
4. One practical tip for tonight
5. Keep under 100 words, warm and conversational

Start with "Bhai," and sound like a friend who knows his canteen deeply.
Do NOT use any markdown formatting like **bold** or *italic*. Plain text only.
Only output the message. Nothing else.
"""
    return context

# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/predict", methods=["GET", "POST"])
def predict():
    try:
        realtime_instruction = None
        realtime_image = None

        if request.method == "POST":
            data = request.get_json()
            realtime_instruction = data.get("instruction")
            image_data = data.get("image")
            if image_data:
                realtime_image = image_data

        context = get_full_context(realtime_instruction, realtime_image)
        model = genai.GenerativeModel("gemini-2.5-flash")

        if realtime_image:
            image_bytes = base64.b64decode(realtime_image.split(",")[1])
            response = model.generate_content([
                context,
                {"mime_type": "image/jpeg", "data": image_bytes}
            ])
        else:
            response = model.generate_content(context)

        today = datetime.now()
        feedback_data = load_feedback()
        pattern_alerts = analyze_patterns(feedback_data)

        return jsonify({
            "prediction": response.text,
            "date": today.strftime("%d %B %Y"),
            "day": today.strftime("%A"),
            "time": today.strftime("%I:%M %p"),
            "mess_quality": MESS_MENU.get(today.strftime("%A"), {}).get("dinner_quality", "DECENT"),
            "is_bad_mess_day": today.strftime("%A") in MESS_KNOWLEDGE["bad_dinner_days"],
            "pattern_alert": pattern_alerts[0] if pattern_alerts else None
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

        today = datetime.now()
        feedback_data = load_feedback()

        entry = {
            "date": today.strftime("%Y-%m-%d"),
            "day": today.strftime("%A"),
            "time": today.strftime("%H:%M"),
            "score": score,
            "predicted_level": predicted_level,
            "note": note
        }

        feedback_data["history"].append(entry)
        pattern_alerts = analyze_patterns(feedback_data)
        if pattern_alerts:
            feedback_data["pattern_alerts"] = pattern_alerts

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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)