import os
import sys
import time
import streamlit as st
from dotenv import load_dotenv

# Set page config
st.set_page_config(
    page_title="Multi-Agent Pipeline - LangGraph",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

import MultiAgents
from MultiAgents import (
    AVAILABLE_SKILLS,
    app,
    input_translator_node,
    skill_selector_node,
    drafter_agent,
    reviewer_agent,
    refiner_agent,
    output_translator_node,
)

# Custom header
st.title("LangGraph Multi-Agent Pipeline Control Center")
st.caption("He thong phoi hop giua Qwen 4B Local va 2 Tai khoan Gemini Cloud")

# Sidebar Status & Configuration
with st.sidebar:
  st.header("Trang Thai He Thong")

  has_rev_key = bool(os.getenv("GEMINI_API_KEY_REVIEWER"))
  has_ref_key = bool(os.getenv("GEMINI_API_KEY_REFINER"))

  st.write("**Ollama Model:** `qwen3:4b` (Local)")
  st.write(
      f"**Gemini Acc 1 (Reviewer):** {'SAN SANG' if has_rev_key else 'THIEU KEY'}"
  )
  st.write(
      f"**Gemini Acc 2 (Refiner):** {'SAN SANG' if has_ref_key else 'THIEU KEY'}"
  )

  st.divider()
  st.subheader(f"Danh Sach Skills ({len(AVAILABLE_SKILLS)})")
  for s_name, s_info in AVAILABLE_SKILLS.items():
    with st.expander(f"{s_name}"):
      st.write(f"**Mo ta:** {s_info.description}")
      st.code(s_info.instructions[:250] + "...", language="markdown")

# Main Interface
task_input = st.text_area(
    "Nhap yeu cau lap trinh / review / refactor cua ban:",
    value="Viết script Python kiểm tra cổng mạng (port scanner) an toàn trên localhost sử dụng đa luồng (threading).",
    height=100,
)

col1, col2 = st.columns([1, 5])
with col1:
  start_btn = st.button("Chay Multi-Agent", type="primary", use_container_width=True)

if start_btn:
  if not task_input.strip():
    st.warning("Vui long nhap noi dung nhiem vu!")
    st.stop()

  # Progress Tracker Container
  progress_bar = st.progress(0)
  status_box = st.empty()

  # Step displays
  st.subheader("Tien Trinh Xu Ly Real-Time")
  col_a, col_b = st.columns(2)

  with col_a:
    exp_trans = st.expander("1. Dich Yeu Cau (VI -> EN)", expanded=True)
    exp_draft = st.expander("3. Ban Phac Thao (Agent A - Qwen Local)", expanded=False)
    exp_refine = st.expander("5. Ban Hoan Thien (Agent C - Gemini Acc 2)", expanded=False)

  with col_b:
    exp_skill = st.expander("2. Ky Nang Duoc Chon (Skill Selector)", expanded=True)
    exp_review = st.expander("4. Danh Gia & Gop Y (Agent B - Gemini Acc 1)", expanded=False)
    exp_final = st.expander("6. Ket Qua Cuoi Cung (Tieng Viet)", expanded=True)

  state = {
      "task": task_input,
      "task_en": "",
      "selected_skill": None,
      "draft_en": "",
      "critique_en": "",
      "final_result_en": "",
      "final_result_vi": "",
  }

  total_start = time.time()

  # --- STEP 1: Translate Input ---
  status_box.info("[1/6] Dang dich yeu cau sang Tieng Anh (Qwen Local)...")
  progress_bar.progress(15)
  t0 = time.time()
  res1 = input_translator_node(state)
  state.update(res1)
  exp_trans.write(f"**Thoi gian:** {time.time() - t0:.1f}s")
  exp_trans.code(state["task_en"], language="text")

  # --- STEP 2: Skill Selector ---
  status_box.info("[2/6] Dang danh gia ky nang chuyen biet (Qwen Local)...")
  progress_bar.progress(30)
  t0 = time.time()
  res2 = skill_selector_node(state)
  state.update(res2)
  exp_skill.write(f"**Thoi gian:** {time.time() - t0:.1f}s")
  if state["selected_skill"]:
    skill_obj = AVAILABLE_SKILLS[state["selected_skill"]]
    exp_skill.success(f"Kich hoat skill: **{state['selected_skill']}**")
    exp_skill.write(skill_obj.description)
  else:
    exp_skill.info("Khong can skill dac thu. Bo qua buoc nay.")

  # --- STEP 3: Drafter ---
  status_box.info("[3/6] Agent A dang viet ban nhap ban dau bang Tieng Anh (Qwen Local)...")
  progress_bar.progress(50)
  t0 = time.time()
  res3 = drafter_agent(state)
  state.update(res3)
  exp_draft.write(f"**Thoi gian:** {time.time() - t0:.1f}s")
  exp_draft.markdown(state["draft_en"])

  # --- STEP 4: Reviewer ---
  status_box.info("[4/6] Agent B dang kiem tra bug va review bao mat (Gemini Acc 1)...")
  progress_bar.progress(70)
  t0 = time.time()
  res4 = reviewer_agent(state)
  state.update(res4)
  exp_review.write(f"**Thoi gian:** {time.time() - t0:.1f}s")
  exp_review.markdown(state["critique_en"])

  # --- STEP 5: Refiner ---
  status_box.info("[5/6] Agent C dang tong hop va hoan thien ma nguon (Gemini Acc 2)...")
  progress_bar.progress(85)
  t0 = time.time()
  res5 = refiner_agent(state)
  state.update(res5)
  exp_refine.write(f"**Thoi gian:** {time.time() - t0:.1f}s")
  exp_refine.markdown(state["final_result_en"])

  # --- STEP 6: Output Translation ---
  status_box.info("[6/6] Dang dich ket qua cuoi cung sang Tieng Viet (Qwen Local)...")
  progress_bar.progress(95)
  t0 = time.time()
  res6 = output_translator_node(state)
  state.update(res6)
  progress_bar.progress(100)

  elapsed = time.time() - total_start
  status_box.success(f"Hoan tat toan bo pipeline trong {elapsed:.1f} giay!")

  # Final Result Display
  exp_final.markdown(state["final_result_vi"])

