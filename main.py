import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import json
import os
import hashlib

# --- CONFIGURATION ---
DB_NAME = 'school_grades.db'
CONFIG_FILE = 'exams.json'

# MD5 Hash for password '1234'
ADMIN_PASSWORD_HASH = 'b4c4334f4c0021045671e4bd58dd2377'

st.set_page_config(page_title="Grade Tracker", page_icon="🎓", layout="wide")

# --- LOGIN LOGIC ---
def check_login():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.markdown("## 🔒 Access Restricted")
        password_input = st.text_input("Please enter the password:", type="password")
        
        if st.button("Login"):
            input_hash = hashlib.md5(password_input.encode()).hexdigest()
            if input_hash == ADMIN_PASSWORD_HASH:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.stop()

check_login()

# ==========================================
# APP CONTENT
# ==========================================

# --- DATABASE FUNCTIONS ---

def init_db():
    """Creates the tables with the new schema (supporting min/max/step)."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # Table 1: Exams now stores grading configuration
        c.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                min_grade REAL DEFAULT 1.0,
                max_grade REAL DEFAULT 5.0,
                step_size REAL DEFAULT 0.1
            )
        """)
        # Table 2: Grades (unchanged)
        c.execute("""
            CREATE TABLE IF NOT EXISTS grades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER,
                grade REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(exam_id) REFERENCES exams(id)
            )
        """)
        conn.commit()

def sync_config_with_db():
    """
    Reads exams.json and updates the database with names and grading scales.
    Returns the list of exam names.
    """
    if not os.path.exists(CONFIG_FILE):
        # Create default file if missing
        default_data = [
            {"name": "Math 101", "min": 1.0, "max": 5.0, "step": 0.1},
            {"name": "Databases", "min": 0.0, "max": 40.0, "step": 1.0}
        ]
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, ensure_ascii=False, indent=4)
        st.warning(f"Created {CONFIG_FILE} with default values.")
        return [x['name'] for x in default_data]

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        exams_config = json.load(f)

    exam_names = []
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        for exam in exams_config:
            name = exam['name']
            exam_names.append(name)
            # Use SQLite Upsert (On Conflict Update) to update settings if they change in JSON
            c.execute("""
                INSERT INTO exams (name, min_grade, max_grade, step_size) 
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    min_grade=excluded.min_grade,
                    max_grade=excluded.max_grade,
                    step_size=excluded.step_size
            """, (name, exam['min'], exam['max'], exam['step']))
        conn.commit()
        
    return exam_names

def get_exam_details(exam_name):
    """Fetches the ID and grading config for a specific exam."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # Retrieve config along with ID
        c.execute("SELECT id, min_grade, max_grade, step_size FROM exams WHERE name = ?", (exam_name,))
        result = c.fetchone()
        if result:
            return {
                'id': result[0],
                'min': result[1],
                'max': result[2],
                'step': result[3]
            }
        return None

def save_grade(exam_id, grade):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO grades (exam_id, grade) VALUES (?, ?)", (exam_id, grade))
        conn.commit()

def get_grades_for_exam(exam_id):
    with sqlite3.connect(DB_NAME) as conn:
        query = "SELECT grade FROM grades WHERE exam_id = ?"
        df = pd.read_sql_query(query, conn, params=(exam_id,))
    return df

# --- APP START ---

if not os.path.exists(DB_NAME):
    init_db()

# Sync JSON config to DB on every load
available_exam_names = sync_config_with_db()

with st.sidebar:
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

st.title("🎓 Student Grade Portal")

# 1. Exam Selection
selected_exam_name = st.selectbox("Select Exam:", options=available_exam_names)

# Get details (ID + Min/Max/Step)
exam_data = get_exam_details(selected_exam_name)

st.divider()

if exam_data:
    current_exam_id = exam_data['id']
    min_g = exam_data['min']
    max_g = exam_data['max']
    step_g = exam_data['step']

    col1, col2 = st.columns([1, 2])

    # 2. Input Section (Dynamic based on exam config)
    with col1:
        st.subheader("Enter Grade")
        st.caption(f"Range: {min_g} - {max_g}")
        
        # Calculate appropriate formatting string based on step size
        # If step is integer (1.0), show "0", else show "0.1"
        fmt = "%d" if step_g.is_integer() else "%.1f"
        
        grade_input = st.number_input(
            f"Your result for {selected_exam_name}",
            min_value=float(min_g), 
            max_value=float(max_g), 
            step=float(step_g),
            format=fmt
        )
        
        if st.button("Submit Grade", type="primary"):
            save_grade(current_exam_id, grade_input)
            st.toast("Grade Saved!")
            st.rerun()

    # 3. Visualization Section
    with col2:
        df = get_grades_for_exam(current_exam_id)

        if not df.empty:
            st.subheader(f"Statistics for {selected_exam_name}")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Students", len(df))
            m2.metric("Average", f"{df['grade'].mean():.2f}")
            m3.metric("Median", f"{df['grade'].median():.1f}")

            # DYNAMIC CHART RANGE
            # Create range based on this specific exam's min/max/step
            # We add a small epsilon (1e-9) to max to ensure the last value is included
            possible_grades = np.arange(min_g, max_g + step_g/1000, step_g)
            
            # Clean floating point errors
            if step_g.is_integer():
                possible_grades = [int(x) for x in possible_grades]
            else:
                possible_grades = [round(x, 2) for x in possible_grades]
            
            grade_counts = df['grade'].value_counts()
            
            # Reindex to show the full scale (0 to 40, or 1.0 to 5.0)
            chart_data = grade_counts.reindex(possible_grades, fill_value=0)
            
            chart_df = pd.DataFrame(chart_data)
            chart_df.columns = ['Count']
            chart_df.index.name = 'Points/Grade'
            
            st.bar_chart(chart_df, height=300)
        else:
            st.info(f"No results entered for {selected_exam_name} yet.")
else:
    st.error("Error loading exam configuration.")