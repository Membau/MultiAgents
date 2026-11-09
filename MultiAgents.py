import json
import os
import re
from typing import Dict, List, Optional, TypedDict
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

# Resolve base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load environment variables from .env
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Helper function to extract text cleanly from LangChain response (which can be str or list of dicts)
def extract_text(content) -> str:
  if isinstance(content, str):
    return content
  if isinstance(content, list):
    text_parts = [
        item.get("text", "") for item in content if isinstance(item, dict) and "text" in item
    ]
    if text_parts:
      return "".join(text_parts)
  return str(content)

# ==========================================
# 1. INITIALIZE MODELS (LLMs)
# ==========================================

# Model 1: Local Qwen via Ollama (Drafter, Router & Translator)
llm_local = ChatOllama(
    model="qwen3:4b",
    temperature=0.3,
    base_url="http://localhost:11434",
    timeout=60,
)

# Model 2: Gemini Account 1 (Reviewer - gemini-3.5-flash-lite)
llm_gemini_reviewer = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    google_api_key=os.getenv("GEMINI_API_KEY_REVIEWER", ""),
    temperature=0.2,
    timeout=60,
)

# Model 3: Gemini Account 2 (Refiner - gemini-3.5-flash)
llm_gemini_refiner = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY_REFINER", ""),
    temperature=0.2,
    timeout=90,
)


# ==========================================
# 2. LOAD SKILLS FROM TXT FILE & SKILL.MD
# ==========================================
class SkillInfo:

  def __init__(self, name: str, description: str, instructions: str):
    self.name = name
    self.description = description
    self.instructions = instructions


def load_skills_from_file(
    txt_path: str = "skills_list.txt",
) -> Dict[str, SkillInfo]:
  skills: Dict[str, SkillInfo] = {}

  if not os.path.isabs(txt_path):
    txt_path = os.path.join(BASE_DIR, txt_path)

  if not os.path.exists(txt_path):
    print(f"[Warning] Skills index file '{txt_path}' not found.")
    return skills

  with open(txt_path, "r", encoding="utf-8") as f:
    lines = [
        line.strip()
        for line in f
        if line.strip() and not line.strip().startswith("#")
    ]

  for line in lines:
    inline_match = re.match(r'^(.*?\.md)\s+"([^"]+)"', line)
    if inline_match:
      path, inline_desc = inline_match.group(1).strip(), inline_match.group(2).strip()
    else:
      parts = line.split(maxsplit=1)
      path = parts[0].strip()
      inline_desc = parts[1].strip().strip('"') if len(parts) > 1 else ""

    if not os.path.isabs(path):
      full_path = os.path.join(BASE_DIR, path)
    else:
      full_path = path

    if not os.path.exists(full_path):
      continue

    with open(full_path, "r", encoding="utf-8") as sf:
      content = sf.read()

    file_stem = os.path.splitext(os.path.basename(full_path))[0]
    name = file_stem
    description = inline_desc
    instructions = content

    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if frontmatter_match:
      meta_text, body_text = frontmatter_match.groups()
      instructions = body_text.strip()
      if not description:
        for meta_line in meta_text.splitlines():
          if meta_line.startswith("name:"):
            name = meta_line.replace("name:", "").strip().strip("\"'")
          elif meta_line.startswith("description:"):
            description = (
                meta_line.replace("description:", "").strip().strip("\"'")
            )
    elif not description:
      first_lines = [
          l.strip()
          for l in content.splitlines()
          if l.strip() and not l.startswith("#")
      ]
      description = first_lines[0] if first_lines else f"Skill for {file_stem}"

    skills[name] = SkillInfo(
        name=name, description=description, instructions=instructions
    )

  return skills


AVAILABLE_SKILLS = load_skills_from_file(os.path.join(BASE_DIR, "skills_list.txt"))


# ==========================================
# 3. DEFINE PIPELINE STATE
# ==========================================
class PipelineState(TypedDict):
  task: str  # Original task from user
  task_en: str  # Task translated into English
  selected_skill: Optional[str]  # Skill name chosen by Qwen or None
  draft_en: str  # Initial code/draft generated in English
  critique_en: str  # Review and critique comments in English
  final_result_en: str  # Complete refined output in English
  final_result_vi: str  # Final output translated back to Vietnamese


# ==========================================
# 4. DEFINE AGENT NODES
# ==========================================
def input_translator_node(state: PipelineState) -> dict:
  """Translate initial user task into concise, clear English prompt."""
  print("\n>>> [1/6 Input Translator - Qwen Local] Translating task to English...")
  prompt = [
      SystemMessage(
          content=(
              "You are a professional technical translator. Translate the"
              " following user request into clear, concise, and accurate"
              " English. Output ONLY the translated text without commentary."
          )
      ),
      HumanMessage(content=state["task"]),
  ]
  res = llm_local.invoke(prompt)
  translated = extract_text(res.content).strip()
  print(f"    [Translated Task]: {translated}")
  return {"task_en": translated}


def skill_selector_node(state: PipelineState) -> dict:
  """Qwen evaluates available skills from loaded skill.md files, selecting one or skipping."""
  print("\n>>> [2/6 Skill Selector - Qwen Local] Evaluating available skills...")

  if not AVAILABLE_SKILLS:
    print("    [Skill Status]: No skills found in registry. Skipping.")
    return {"selected_skill": None}

  skills_description = "\n".join(
      [f"- {name}: {info.description}" for name, info in AVAILABLE_SKILLS.items()]
  )

  prompt = [
      SystemMessage(
          content=(
              "You are an AI task router. Evaluate whether the given user task"
              " strictly requires one of the available specialized skills."
              f" Available skills:\n{skills_description}\n\n"
              'Respond ONLY with a JSON object in this format: {"skill":'
              ' "<skill_name>"} or {"skill": null} if no skill is suitable or'
              " necessary. Do not include markdown code block or any extra"
              " text."
          )
      ),
      HumanMessage(content=f"User Task: {state['task_en']}"),
  ]

  res = llm_local.invoke(prompt)
  raw_content = (
      extract_text(res.content)
      .strip()
      .replace("```json", "")
      .replace("```", "")
      .strip()
  )

  selected_skill = None
  try:
    data = json.loads(raw_content)
    skill_val = data.get("skill")
    if skill_val in AVAILABLE_SKILLS:
      selected_skill = skill_val
  except Exception:
    for skill_name in AVAILABLE_SKILLS.keys():
      if skill_name in raw_content.lower():
        selected_skill = skill_name
        break

  if selected_skill:
    info = AVAILABLE_SKILLS[selected_skill]
    print(f"    [Skill Matched]: {selected_skill} ({info.description})")
  else:
    print("    [Skill Evaluated]: No matching skill found. Skipping skill.")

  return {"selected_skill": selected_skill}


def drafter_agent(state: PipelineState) -> dict:
  """Agent A: Draft initial implementation in English, injecting full skill instructions if selected."""
  print(
      "\n>>> [3/6 Agent A - Qwen Local] Drafting initial implementation in"
      " English..."
  )

  skill_context = ""
  if state.get("selected_skill") and state["selected_skill"] in AVAILABLE_SKILLS:
    skill = AVAILABLE_SKILLS[state["selected_skill"]]
    skill_context = (
        f"\n\n--- Domain Skill Activated: {skill.name} ---\n{skill.instructions}\n---"
        " Follow the skill guidelines strictly ---"
    )

  prompt = [
      SystemMessage(
          content=(
              "You are a software engineer. Provide a structured plan and"
              " initial clean code implementation for the given task. Write all"
              f" code, explanations, and comments in English.{skill_context}"
          )
      ),
      HumanMessage(content=state["task_en"]),
  ]
  res = llm_local.invoke(prompt)
  draft = extract_text(res.content)
  print(f"    [Draft Completed]: Generated {len(draft)} characters.")
  return {"draft_en": draft}


def reviewer_agent(state: PipelineState) -> dict:
  """Agent B: Review draft, spot bugs, and suggest improvements in English."""
  print(
      "\n>>> [4/6 Agent B - Gemini 3.5 Flash-Lite (Acc 1)] Reviewing code and logic in"
      " English..."
  )

  skill_info = (
      f" (Domain Skill: {state['selected_skill']})"
      if state.get("selected_skill")
      else ""
  )
  prompt = [
      SystemMessage(
          content=(
              "You are a Senior Code Reviewer. Analyze the provided draft"
              f" against the requirements{skill_info}. Identify bugs, security"
              " vulnerabilities, logic flaws, and performance bottlenecks."
              " Provide concise, bulleted critique and actionable improvements"
              " in English."
          )
      ),
      HumanMessage(
          content=(
              f"Requirements:\n{state['task_en']}\n\nDraft"
              f" Implementation:\n{state['draft_en']}"
          )
      ),
  ]
  res = llm_gemini_reviewer.invoke(prompt)
  critique = extract_text(res.content)
  print(f"    [Review Completed]: Generated {len(critique)} characters of critique.")
  return {"critique_en": critique}


def refiner_agent(state: PipelineState) -> dict:
  """Agent C: Synthesize draft and critique into production-ready English result."""
  print(
      "\n>>> [5/6 Agent C - Gemini 3.5 Flash (Acc 2)] Synthesizing final English"
      " version..."
  )
  prompt = [
      SystemMessage(
          content=(
              "You are a Principal Software Architect. Synthesize the initial"
              " draft and the code review critique. Write the complete,"
              " production-ready final code and comprehensive explanation in"
              " English."
          )
      ),
      HumanMessage(
          content=(
              f"Task:\n{state['task_en']}\n\n"
              f"Initial Draft:\n{state['draft_en']}\n\n"
              f"Review Critique:\n{state['critique_en']}"
          )
      ),
  ]
  res = llm_gemini_refiner.invoke(prompt)
  final_en = extract_text(res.content)
  print(f"    [Refinement Completed]: Generated {len(final_en)} characters.")
  return {"final_result_en": final_en}


def output_translator_node(state: PipelineState) -> dict:
  """Translate the final response back to Vietnamese using Local Model while preserving code intact."""
  print(
      "\n>>> [6/6 Output Translator - Qwen Local] Translating final response to"
      " Vietnamese..."
  )
  prompt = [
      SystemMessage(
          content=(
              "You are a professional technical translator. Translate the"
              " explanations, instructions, and documentation in the following"
              " text into natural Vietnamese. IMPORTANT: Keep all source code,"
              " markdown code blocks, identifiers, syntax, and terminal"
              " commands intact without any modification."
          )
      ),
      HumanMessage(content=state["final_result_en"]),
  ]
  res = llm_local.invoke(prompt)
  final_vi = extract_text(res.content)
  print("    [Output Translation Completed].")
  return {"final_result_vi": final_vi}


# ==========================================
# 5. BUILD LANGGRAPH WORKFLOW
# ==========================================
workflow = StateGraph(PipelineState)

# Add Nodes
workflow.add_node("translate_input", input_translator_node)
workflow.add_node("select_skill", skill_selector_node)
workflow.add_node("drafter", drafter_agent)
workflow.add_node("reviewer", reviewer_agent)
workflow.add_node("refiner", refiner_agent)
workflow.add_node("translate_output", output_translator_node)

# Connect Sequential Edges
workflow.add_edge(START, "translate_input")
workflow.add_edge("translate_input", "select_skill")
workflow.add_edge("select_skill", "drafter")
workflow.add_edge("drafter", "reviewer")
workflow.add_edge("reviewer", "refiner")
workflow.add_edge("refiner", "translate_output")
workflow.add_edge("translate_output", END)

# Compile Workflow
app = workflow.compile()


# ==========================================
# 6. EXECUTION ENTRY POINT (CLI READY)
# ==========================================
if __name__ == "__main__":
  import argparse

  parser = argparse.ArgumentParser(description="Run Multi-Agent Pipeline.")
  parser.add_argument(
      "--task",
      type=str,
      default="Viết script Python kiểm tra cổng mạng (port check) an toàn.",
      help="Task description to execute",
  )
  parser.add_argument(
      "--task-file",
      type=str,
      default=None,
      help="Path to file containing task description",
  )
  args = parser.parse_args()

  task_text = args.task
  if args.task_file and os.path.exists(args.task_file):
    with open(args.task_file, "r", encoding="utf-8") as f:
      task_text = f.read()

  input_data = {
      "task": task_text,
      "task_en": "",
      "selected_skill": None,
      "draft_en": "",
      "critique_en": "",
      "final_result_en": "",
      "final_result_vi": "",
  }

  print("=== BẮT ĐẦU CHẠY MULTI-AGENT PIPELINE ===")
  print(f"Task: {input_data['task']}\n")

  # Stream pipeline steps
  current_state = dict(input_data)
  for output in app.stream(input_data):
    for node_name, state_update in output.items():
      print(f"--- [OK] Hoàn thành Node: {node_name} ---")
      current_state.update(state_update)

  print("\n================== KẾT QUẢ CUỐI CÙNG (VIETNAMESE) ==================")
  print(current_state.get("final_result_vi", ""))
