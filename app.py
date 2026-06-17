from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, jsonify, request
from groq import Groq
from datetime import datetime
import json
import os
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
        score = entry.get("score", 3)
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

def get_full_context(realtime_instruction=None):
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
        meal_period = "mess dinner time 7:30-9:30pm — predicting post-mess and late night rush"
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
Semester: {SEMESTER_PHASE}
Today's academic event: {academic_event.get('event', 'Regular day')} ({academic_event.get('type', 'normal')})

=== TODAY'S MESS MENU ===
Mess lunch (12:30-2:30pm): {mess_today.get('lunch', 'Unknown')}
Mess dinner (7:30-9:30pm): {mess_today.get('dinner', 'Unknown')}
Mess dinner quality: {mess_today.get('dinner_quality', 'DECENT')}

=== BEHAVIORAL PATTERNS (3 years of observation) ===
Bad mess dinner days — high canteen footfall: Monday, Thursday, Saturday
Today is a bad mess dinner day: {is_bad_dinner_day}
Lunch footfall: Only significant when mess is completely closed
Late night 10pm-2am: Always busy regardless of mess quality

=== MOST POPULAR ITEMS ===
Snacks: {', '.join(POPULAR_ITEMS['snacks'])}
Popular veg meal: {', '.join(POPULAR_ITEMS['meal_veg'])}
Popular non-veg: {', '.join(POPULAR_ITEMS['meal_nonveg'])}

=== PERMANENT ADJUSTMENTS FROM FEEDBACK ===
{json.dumps(permanent_adjustments, indent=2) if permanent_adjustments else 'None yet'}

=== RECENT FEEDBACK (last 5 days) ===
{json.dumps(recent_feedback, indent=2) if recent_feedback else 'No feedback yet'}
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
    return context

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

        context = get_full_context(realtime_instruction)

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant for a canteen owner in India. Always respond in Hindi/Hinglish. Never use markdown formatting like ** or *."
                },
                {
                    "role": "user",
                    "content": context
                }
            ],
            max_tokens=300,
            temperature=0.7
        )

        prediction = response.choices[0].message.content
        today = datetime.now()
        feedback_data = load_feedback()
        pattern_alerts = analyze_patterns(feedback_data)

        return jsonify({
            "prediction": prediction,
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