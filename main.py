import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import json
import os

DB_NAME = 'school_grades.db'
CONFIG_FILE = 'exams.json'

st.set_page_config(page_title="TIS Notenspiegel", page_icon="🎓", layout="wide")

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """)
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
    if not os.path.exists(CONFIG_FILE):
        default_exams = ["Mathematik I", "Physik Prüfung"]
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_exams, f, ensure_ascii=False, indent=4)
        st.warning(f"Created {CONFIG_FILE} with default values.")
        return default_exams

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        exam_names = json.load(f)

    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        for name in exam_names:
            c.execute("INSERT OR IGNORE INTO exams (name) VALUES (?)", (name,))
        conn.commit()
        
    return exam_names

def get_exam_id(exam_name):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM exams WHERE name = ?", (exam_name,))
        result = c.fetchone()
        return result[0] if result else None

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

if not os.path.exists(DB_NAME):
    init_db()

available_exams = sync_config_with_db()

st.title("🎓 TIS Notenspiegel Portal")

selected_exam_name = st.selectbox("Wähle eine Prüfung aus:", options=available_exams)

current_exam_id = get_exam_id(selected_exam_name)

st.divider()

if current_exam_id is not None:
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Noteneingabe")
        grade_input = st.number_input(
            f"Deine Note im Fach {selected_exam_name}",
            min_value=1.0, 
            max_value=5.0, 
            step=0.1,
            format="%.1f"
        )
        
        if st.button("Note speichern", type="primary"):
            save_grade(current_exam_id, round(grade_input, 1))
            st.toast("Gespeichert!", icon="✅")
            st.rerun()

    with col2:
        df = get_grades_for_exam(current_exam_id)

        if not df.empty:
            st.subheader(f"Notenverteilung für {selected_exam_name}")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Studenten", len(df))
            m2.metric("Durchschnitt", f"{df['grade'].mean():.2f}")
            m3.metric("Median", f"{df['grade'].median():.1f}")

            possible_grades = np.arange(1.0, 5.1, 0.1)
            possible_grades = [round(x, 1) for x in possible_grades]
            
            grade_counts = df['grade'].value_counts()
            chart_data = grade_counts.reindex(possible_grades, fill_value=0)
            
            chart_df = pd.DataFrame(chart_data)
            chart_df.columns = ['Count']
            chart_df.index.name = 'Grade'
            
            st.bar_chart(chart_df, height=300)
        else:
            st.info(f"Es wurden noch keine Noten für {selected_exam_name} angegeben.")
else:
    st.error("Error loading exam ID. Please check configuration.")