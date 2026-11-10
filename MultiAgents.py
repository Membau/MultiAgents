import os
import sys
import re
import json
import time
import shutil
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, TypedDict
from dotenv import load_dotenv

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END

# Resolve base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load environment variables from .env
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Maximum automatic debug & fix attempts when console execution fails
MAX_EXECUTION_RETRIES = 2


# ==========================================
# 0. HELPER FUNCTIONS & GEMINI API RESILIENCE
# ==========================================

def ensure_ollama_running(host: str = "http://localhost:11434", timeout: int = 2) -> bool:
    """
    Checks if Ollama service is reachable. If not, attempts to auto-launch it in the background.
    """
    import urllib.request

    try:
        with urllib.request.urlopen(f"{host}/api/version", timeout=timeout) as response:
            if response.status == 200:
                return True
    except Exception:
        pass

    print("[Ollama] Dịch vụ Ollama chưa bật. Đang tự động khởi động Ollama ngầm...")
    
    ollama_bin = (
        shutil.which("ollama")
        or os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
        or r"C:\Users\LENOVO\AppData\Local\Programs\Ollama\ollama.exe"
    )
    
    if os.path.exists(ollama_bin):
        try:
            creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
            subprocess.Popen(
                [ollama_bin, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
            for _ in range(6):
                time.sleep(1)
                try:
                    with urllib.request.urlopen(f"{host}/api/version", timeout=1) as response:
                        if response.status == 200:
                            print("[Ollama] Đã tự động khởi động và kết nối Ollama thành công!")
                            return True
                except Exception:
                    continue
        except Exception as e:
            print(f"[Ollama Warning] Tự động bật Ollama thất bại: {e}")

    print("[Ollama Warning] Không thể kết nối tới Ollama. MemBau vui lòng mở ứng dụng Ollama trên máy.")
    return False


def extract_text(content) -> str:
    """Extract clean string from LangChain response."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [item.get("text", "") for item in content if isinstance(item, dict) and "text" in item]
        if text_parts:
            return "".join(text_parts)
    return str(content)


def get_gemini_api_key(role: str = "reviewer") -> str:
    """
    Resolve Gemini API key following official Google AI Studio recommendations.
    Supports multi-account setup (REVIEWER & REFINER) with fallbacks.
    """
    if role == "reviewer":
        key = (
            os.getenv("GEMINI_API_KEY_REVIEWER")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or ""
        )
    else:
        key = (
            os.getenv("GEMINI_API_KEY_REFINER")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or ""
        )
    return key.strip()


def invoke_gemini_with_fallback(
    models: List[str],
    api_key: str,
    messages: list,
    temperature: float = 0.2,
    timeout: int = 90
) -> str:
    """
    Invokes Gemini with automatic model fallback and retry logic.
    Handles temporary 503 high demand spikes and quota boundaries.
    """
    last_err = None
    for model_name in models:
        try:
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=temperature,
                timeout=timeout,
                max_retries=2
            )
            res = llm.invoke(messages)
            text = extract_text(res.content).strip()
            if text:
                return text
        except Exception as e:
            err_msg = str(e)
            print(f"    [Gemini Warning] Model '{model_name}' failed: {err_msg[:120]}... Trying fallback...")
            last_err = e
            time.sleep(1.5)
            continue
            
    raise RuntimeError(f"All Gemini fallback models failed. Last error: {last_err}")


# ==========================================
# 1. INITIALIZE LOCAL LLM & GEMINI CANDIDATES
# ==========================================

# Model 1: Local Qwen via Ollama (Router, Drafter & Translator)
llm_local = ChatOllama(
    model="qwen3:4b",
    temperature=0.3,
    base_url="http://localhost:11434",
    timeout=60
)

# Gemini API Model Priority Lists (tested and verified on Google AI Studio)
GEMINI_REVIEWER_MODELS = [
    os.getenv("GEMINI_MODEL_REVIEWER", "gemini-3.5-flash-lite"),
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash"
]

GEMINI_REFINER_MODELS = [
    os.getenv("GEMINI_MODEL_REFINER", "gemini-3.5-flash"),
    "gemini-3.5-flash-lite",
    "gemini-pro-latest",
    "gemini-flash-latest"
]


# ==========================================
# 2. SKILLS LOADER (STANDARD SKILL FOLDERS)
# ==========================================
class SkillInfo:
    def __init__(self, name: str, description: str, instructions: str, file_path: str):
        self.name = name
        self.description = description
        self.instructions = instructions
        self.file_path = file_path


def load_skills() -> Dict[str, SkillInfo]:
    """
    Scans skills directory and skills_list.txt.
    Supports modern skill folders containing SKILL.md and optimized .mini.md.
    """
    skills: Dict[str, SkillInfo] = {}
    skills_dir = os.path.join(BASE_DIR, "skills")
    
    if not os.path.exists(skills_dir):
        return skills

    for entry in os.scandir(skills_dir):
        if not entry.is_dir() or entry.name.startswith((".", "_")):
            continue
            
        skill_dir = entry.path
        skill_file = os.path.join(skill_dir, "SKILL.md")
        if not os.path.exists(skill_file):
            continue

        with open(skill_file, "r", encoding="utf-8") as sf:
            content = sf.read()

        name = entry.name
        description = ""
        
        fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            frontmatter = fm_match.group(1)
            name_m = re.search(r"^name:\s*(.+)$", frontmatter, re.M)
            desc_m = re.search(r"^description:\s*(.+)$", frontmatter, re.M)
            if name_m:
                name = name_m.group(1).strip().strip("\"'")
            if desc_m:
                description = desc_m.group(1).strip().strip("\"'")

        mini_candidate = os.path.join(skill_dir, f"{entry.name}.mini.md")
        if os.path.exists(mini_candidate):
            with open(mini_candidate, "r", encoding="utf-8") as mf:
                instructions = mf.read().strip()
        else:
            instructions = content.strip()

        if not description:
            description = f"Software design and engineering skill for {name}"

        skills[name] = SkillInfo(
            name=name,
            description=description,
            instructions=instructions,
            file_path=skill_file
        )

    return skills

AVAILABLE_SKILLS = load_skills()


# ==========================================
# 3. PROJECT CONTEXT & FILE ARTIFACT EXPORTER
# ==========================================

def scan_project_context(project_dir: str, max_depth: int = 3, max_files: int = 60) -> str:
    """
    Scans workspace/project folder structure and generates a readable directory tree.
    Ignores common non-essential folders (.git, venv, node_modules, output, etc.).
    """
    if not os.path.exists(project_dir):
        return f"[Project Directory not found: {project_dir}]"

    ignore_dirs = {
        ".git", "venv", ".venv", "__pycache__", "node_modules", 
        ".idea", ".vscode", "output", "dist", "build", ".gemini"
    }
    
    tree_lines = [f"Project Root: {os.path.abspath(project_dir)}"]
    count = 0
    
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
        rel_path = os.path.relpath(root, project_dir)
        depth = 0 if rel_path == "." else rel_path.count(os.sep) + 1
        
        if depth > max_depth:
            continue
            
        indent = "  " * depth
        if rel_path != ".":
            tree_lines.append(f"{indent}📁 {os.path.basename(root)}/")
            
        for file in files:
            if file.startswith(".") or file.endswith((".pyc", ".log", ".tmp")):
                continue
            tree_lines.append(f"{indent}  📄 {file}")
            count += 1
            if count >= max_files:
                tree_lines.append(f"{indent}  ... [truncated {max_files}+ files]")
                return "\n".join(tree_lines)
                
    return "\n".join(tree_lines)


def write_code_files_to_disk(final_en: str, output_dir: str) -> Dict[str, str]:
    """
    Parses code blocks and writes physical source files into output_dir.
    """
    os.makedirs(output_dir, exist_ok=True)
    created_files: Dict[str, str] = {}
    normalized_en = final_en.replace("\r\n", "\n")

    # Pattern 1: ### FILE: <rel_path> \n ```<lang> ... ```
    pattern_explicit = re.compile(
        r'(?:###|##|#)\s*(?:FILE|File|Filename):\s*([^\r\n]+)\s*\n```[a-zA-Z0-9_\-\+\.]*\n(.*?)```',
        re.DOTALL
    )
    matches = pattern_explicit.findall(normalized_en)

    if not matches:
        # Pattern 2: ```<lang>:path/to/file.ext \n ... ```
        pattern_colon = re.compile(
            r'```[a-zA-Z0-9_\-\+\.]*:(.+?)\n(.*?)```',
            re.DOTALL
        )
        matches = pattern_colon.findall(normalized_en)

    if matches:
        for file_rel_path, code_body in matches:
            clean_rel = file_rel_path.strip().strip("`'\" ")
            target_path = os.path.join(output_dir, clean_rel)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(code_body.strip() + "\n")
            created_files[clean_rel] = target_path
    else:
        # Fallback: Extract raw code blocks
        code_block_match = re.findall(r'```([a-zA-Z0-9_\-\+\.]*)\n(.*?)```', normalized_en, re.DOTALL)
        if code_block_match:
            for idx, (lang, code_body) in enumerate(code_block_match):
                lang = lang.lower().strip()
                ext = "py" if "python" in lang or not lang else ("js" if "javascript" in lang else ("json" if "json" in lang else ("sh" if "bash" in lang or "sh" in lang else "txt")))
                filename = f"solution_{idx+1}.{ext}" if len(code_block_match) > 1 else f"solution.{ext}"
                target_path = os.path.join(output_dir, filename)
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(code_body.strip() + "\n")
                created_files[filename] = target_path

    return created_files


# ==========================================
# 4. PIPELINE STATE
# ==========================================
class PipelineState(TypedDict):
    task: str                       # Original task from user
    task_en: str                    # Translated prompt
    project_dir: Optional[str]      # Target workspace / project directory
    project_tree: Optional[str]     # Auto-scanned file tree
    file_context: Optional[str]     # Specific file contents or background context
    selected_skill: Optional[str]   # Selected skill name
    research_notes: str             # Research & requirements expansion
    draft_en: str                   # Agent A draft
    critique_en: str                # Agent B critique
    final_result_en: str            # Agent C synthesis
    final_result_vi: str            # Vietnamese explanation
    output_dir: Optional[str]       # Target output directory
    created_files: Dict[str, str]   # Exported physical files
    execution_logs: str             # Console stdout and stderr from running tests
    execution_success: bool         # Whether execution succeeded (exit code 0)
    retry_count: int                # Self-correction loop count


# ==========================================
# 5. DEFINE AGENT NODES
# ==========================================

def input_translator_node(state: PipelineState) -> dict:
    """Node 1: Translates user task and context into clear technical English."""
    ensure_ollama_running()
    print("\n>>> [1/7 Input Translator - Qwen Local] Translating task to English...")
    prompt = [
        SystemMessage(content=(
            "You are a professional technical translator. Translate the following user request into "
            "clear, concise, and accurate English. Output ONLY the translated text without commentary."
        )),
        HumanMessage(content=state["task"])
    ]
    res = llm_local.invoke(prompt)
    translated = extract_text(res.content).strip()
    print(f"    [Translated Task]: {translated}")
    return {"task_en": translated}


def skill_selector_node(state: PipelineState) -> dict:
    """Node 2: Evaluates available skills and matches the most relevant domain rules."""
    print("\n>>> [2/7 Skill Selector - Qwen Local] Evaluating available skills...")
    
    if not AVAILABLE_SKILLS:
        print("    [Skill Status]: No skills found in registry. Skipping.")
        return {"selected_skill": None}

    skills_description = "\n".join([
        f"- {name}: {info.description}" 
        for name, info in AVAILABLE_SKILLS.items()
    ])

    prompt = [
        SystemMessage(content=(
            "You are an AI task router. Evaluate whether the given technical task strictly benefits from "
            f"one of the available specialized skills.\nAvailable skills:\n{skills_description}\n\n"
            "Respond ONLY with a JSON object in this format: {\"skill\": \"<skill_name>\"} "
            "or {\"skill\": null} if no skill is necessary. Do not include markdown code block or extra text."
        )),
        HumanMessage(content=f"Task: {state['task_en']}")
    ]
    
    res = llm_local.invoke(prompt)
    raw_content = extract_text(res.content).strip().replace("```json", "").replace("```", "").strip()
    
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
        print("    [Skill Evaluated]: No specialized skill strictly required.")

    return {"selected_skill": selected_skill}


def research_agent_node(state: PipelineState) -> dict:
    """
    Node 3 (NEW): Deep Research & Requirement Expansion.
    Inspects runtime environment, analyzes edge cases, security, and verifies dependencies.
    """
    print("\n>>> [3/7 Research & Expansion Agent - Gemini/Local] Deep researching task requirements...")

    # Gather local python environment context
    py_version = sys.version.split()[0]
    os_name = sys.platform
    local_env_info = f"Python {py_version} on {os_name}"

    skill_info = f"Skill: {state['selected_skill']}" if state.get("selected_skill") else "General Best Practices"
    
    prompt = [
        SystemMessage(content=(
            "You are a Principal Software Research Engineer. Conduct a thorough technical analysis "
            "and expand the user requirements before drafting code. Address:\n"
            "1. Architectural Boundaries & Modularity (following Clean Code/DDD).\n"
            "2. Edge Cases, Race Conditions & Platform Differences (e.g. Windows vs Linux socket/paths).\n"
            "3. Required Standard vs Third-Party Libraries (prefer standard library unless instructed).\n"
            "4. Verifiable Success Criteria & Executable Test Design.\n"
            "Keep your research notes concise, highly technical, and actionable."
        )),
        HumanMessage(content=(
            f"User Task: {state['task_en']}\n"
            f"Active Domain: {skill_info}\n"
            f"Environment Context: {local_env_info}\n"
            f"Project Tree Context:\n{state.get('project_tree', 'N/A')}"
        ))
    ]

    key = get_gemini_api_key("reviewer")
    if key:
        try:
            research_text = invoke_gemini_with_fallback(
                models=GEMINI_REVIEWER_MODELS,
                api_key=key,
                messages=prompt,
                temperature=0.3,
                timeout=60
            )
        except Exception:
            res = llm_local.invoke(prompt)
            research_text = extract_text(res.content)
    else:
        res = llm_local.invoke(prompt)
        research_text = extract_text(res.content)

    print(f"    [Research Completed]: Synthesized {len(research_text)} characters of domain insights.")
    return {"research_notes": research_text}


def drafter_agent(state: PipelineState) -> dict:
    """Node 4: Agent A (Local Qwen) writes initial modular solution with research insights."""
    print("\n>>> [4/7 Agent A - Qwen Local] Drafting initial solution in English...")
    
    skill_context = ""
    if state.get("selected_skill") and state["selected_skill"] in AVAILABLE_SKILLS:
        skill = AVAILABLE_SKILLS[state["selected_skill"]]
        skill_context = (
            f"\n\n--- Domain Skill Activated: {skill.name} ---\n"
            f"{skill.instructions}\n"
            "--- Follow the skill guidelines strictly ---"
        )

    project_context = ""
    if state.get("project_tree"):
        project_context += f"\n\n--- Project File Tree ---\n{state['project_tree']}\n"
    if state.get("file_context"):
        project_context += f"\n\n--- File / Code Context ---\n{state['file_context']}\n"

    research_context = f"\n\n--- Research Notes & Architecture Guidance ---\n{state.get('research_notes', '')}\n"

    prompt = [
        SystemMessage(content=(
            "You are a Software Engineer. Provide a clean implementation plan and initial modular code. "
            "Always include an automated test routine (e.g. test_*.py or an executable test runner) to verify functionality. "
            "Structure your files clearly using markers like: ### FILE: <path/to/file>\n```<lang>\n<code>\n```. "
            f"Write in English.{skill_context}{project_context}{research_context}"
        )),
        HumanMessage(content=state["task_en"])
    ]
    res = llm_local.invoke(prompt)
    draft = extract_text(res.content)
    print(f"    [Draft Completed]: Generated {len(draft)} characters.")
    return {"draft_en": draft}


def reviewer_agent(state: PipelineState) -> dict:
    """Node 5: Agent B (Gemini Account 1) reviews draft, checks bugs, architecture and edge cases."""
    print("\n>>> [5/7 Agent B - Gemini Reviewer] Reviewing code & architecture...")
    
    key = get_gemini_api_key("reviewer")
    if not key:
        print("    [Warning]: Missing Gemini Reviewer Key. Skipping review step.")
        return {"critique_en": "No critique available (Gemini Reviewer key missing)."}

    skill_info = f" (Domain Skill: {state['selected_skill']})" if state.get("selected_skill") else ""
    messages = [
        SystemMessage(content=(
            "You are a Senior Code Reviewer and Security Architect. Analyze the provided draft against the "
            f"requirements{skill_info} and Research Notes. Identify bugs, logic flaws, architectural violations, security holes, and missing edge cases. "
            "Give actionable, bulleted critique and concrete code suggestions in English."
        )),
        HumanMessage(content=(
            f"Requirements:\n{state['task_en']}\n\n"
            f"Research Notes:\n{state.get('research_notes', 'N/A')}\n\n"
            f"Initial Draft:\n{state['draft_en']}"
        ))
    ]
    
    critique = invoke_gemini_with_fallback(
        models=GEMINI_REVIEWER_MODELS,
        api_key=key,
        messages=messages,
        temperature=0.2,
        timeout=60
    )
    print(f"    [Review Completed]: Generated {len(critique)} characters of critique.")
    return {"critique_en": critique}


def refiner_agent(state: PipelineState) -> dict:
    """Node 6: Agent C (Gemini Account 2) synthesizes production-ready files + fixes console errors."""
    retry_num = state.get("retry_count", 0)
    if retry_num > 0:
        print(f"\n>>> [6/7 Agent C - Gemini Refiner] [SELF-CORRECTION #{retry_num}] Fixing code based on Console Error Log...")
    else:
        print("\n>>> [6/7 Agent C - Gemini Refiner] Synthesizing final production-ready files...")
    
    key = get_gemini_api_key("refiner")
    if not key:
        print("    [Warning]: Missing Gemini Refiner Key. Using draft as fallback.")
        return {"final_result_en": state["draft_en"]}

    # If this is a self-correction turn, inject console error log
    console_feedback_prompt = ""
    if state.get("execution_logs") and not state.get("execution_success"):
        console_feedback_prompt = (
            "\n\n======================================================\n"
            "🚨 CRITICAL CONSOLE EXECUTION FAILURE - ACTION REQUIRED:\n"
            "The previous code failed when executed in the terminal console!\n"
            f"Console Traceback / Output:\n{state['execution_logs']}\n\n"
            "Carefully analyze the traceback, fix the root cause (syntax, import, type error, or assertion), "
            "and output the COMPLETE corrected file(s) so they execute cleanly without error.\n"
            "======================================================\n"
        )

    messages = [
        SystemMessage(content=(
            "You are a Principal Software Architect. Synthesize the initial draft, reviewer critique, "
            "and research insights into complete, production-ready source files.\n"
            "CRITICAL OUTPUT FORMAT REQUIREMENT:\n"
            "Format EVERY file with an explicit header line:\n"
            "### FILE: <relative_path/filename.ext>\n"
            "```<language>\n"
            "<complete code here>\n"
            "```\n"
            "Always include an automated test file (e.g. test_runner.py or test_*.py) with an `if __name__ == '__main__':` "
            "block so the system can automatically execute and verify your code in the console!\n"
            "Do NOT truncate code with comments like '// TODO' or '...rest of code...'. Write fully operational code."
            f"{console_feedback_prompt}"
        )),
        HumanMessage(content=(
            f"Task:\n{state['task_en']}\n\n"
            f"Initial Draft:\n{state['draft_en']}\n\n"
            f"Reviewer Critique:\n{state['critique_en']}"
        ))
    ]
    
    final_en = invoke_gemini_with_fallback(
        models=GEMINI_REFINER_MODELS,
        api_key=key,
        messages=messages,
        temperature=0.2,
        timeout=90
    )
    print(f"    [Refinement Completed]: Generated {len(final_en)} characters.")
    return {"final_result_en": final_en}


def code_executor_node(state: PipelineState) -> dict:
    """
    Node 7 (NEW): Code Executor & Console Log Reader.
    Directly writes generated files to disk, runs tests in a sandbox subprocess,
    and captures stdout/stderr for verification or self-correction.
    """
    print("\n>>> [Executing & Testing] Writing files to disk and running console tests...")

    output_dir = state.get("output_dir")
    if not output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', state.get("task", "task")[:25]).strip('_') or "run"
        output_dir = os.path.join(BASE_DIR, "output", f"{slug}_{timestamp}")
        
    created_files = write_code_files_to_disk(state["final_result_en"], output_dir)
    print(f"    [Files Written]: {len(created_files)} file(s) in {output_dir}")
    for rel in created_files:
        print(f"      -> {rel}")

    # Determine execution entrypoint
    py_files = [p for rel, p in created_files.items() if p.endswith(".py")]
    test_file = None
    for p in py_files:
        basename = os.path.basename(p).lower()
        if "test" in basename:
            test_file = p
            break
    if not test_file and py_files:
        test_file = py_files[0]

    if not test_file:
        print("    [Execution]: No Python script found to execute. Skipping test run.")
        return {
            "output_dir": output_dir,
            "created_files": created_files,
            "execution_logs": "No executable Python files generated.",
            "execution_success": True
        }

    # Run script in subprocess
    print(f"    [Console Run]: Executing '{os.path.basename(test_file)}'...")
    try:
        proc = subprocess.run(
            [sys.executable, os.path.abspath(test_file)],
            cwd=output_dir,
            capture_output=True,
            text=True,
            timeout=25,
            encoding="utf-8",
            errors="replace"
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        return_code = proc.returncode

        combined_logs = []
        if stdout:
            combined_logs.append(f"--- STDOUT ---\n{stdout}")
        if stderr:
            combined_logs.append(f"--- STDERR ---\n{stderr}")
        combined_logs.append(f"--- EXIT CODE: {return_code} ---")
        log_str = "\n".join(combined_logs)

        if return_code == 0:
            print(f"    ✅ [Console Success]: Process completed with exit code 0!")
            if stdout:
                print(f"       Output: {stdout[:200]}...")
            success = True
        else:
            print(f"    ❌ [Console Error]: Process exited with code {return_code}!")
            if stderr:
                print(f"       Error: {stderr[:250]}...")
            success = False

    except subprocess.TimeoutExpired:
        log_str = "❌ Execution timed out after 25 seconds (Possible infinite loop or hanging network call)."
        print(f"    {log_str}")
        success = False
    except Exception as e:
        log_str = f"❌ Execution failed to spawn process: {e}"
        print(f"    {log_str}")
        success = False

    new_retry_count = state.get("retry_count", 0) + (0 if success else 1)

    return {
        "output_dir": output_dir,
        "created_files": created_files,
        "execution_logs": log_str,
        "execution_success": success,
        "retry_count": new_retry_count
    }


def should_retry_or_finalize(state: PipelineState) -> str:
    """
    Conditional Edge: Checks if console execution passed or if we should trigger self-correction loop.
    """
    if state.get("execution_success"):
        return "finalize"
    
    if state.get("retry_count", 0) <= MAX_EXECUTION_RETRIES:
        print(f"\n🔁 [Self-Correction Router] Execution failed! Routing back to Refiner (Retry {state['retry_count']}/{MAX_EXECUTION_RETRIES})...")
        return "retry_refiner"
    
    print("\n⚠️ [Self-Correction Router] Reached maximum retry attempts. Proceeding to finalize report.")
    return "finalize"


def translate_and_finalize_node(state: PipelineState) -> dict:
    """
    Node 8: Translates summary into Vietnamese and updates artifact_summary.md with console test results.
    """
    print("\n>>> [Finalizing & Exporting Artifact] Writing Vietnamese summary & console verification report...")
    
    prompt = [
        SystemMessage(content=(
            "You are a technical documentation specialist. Provide a clear, natural Vietnamese summary "
            "explaining the architecture, implementation choices, and execution instructions for the solution. "
            "Do NOT re-translate the raw source code files; summarize their roles and explain how to run them."
        )),
        HumanMessage(content=state["final_result_en"])
    ]
    res = llm_local.invoke(prompt)
    final_vi = extract_text(res.content)
    
    output_dir = state.get("output_dir", os.path.join(BASE_DIR, "output"))
    os.makedirs(output_dir, exist_ok=True)
    
    # Write artifact_summary.md (Anti Gravity style)
    summary_path = os.path.join(output_dir, "artifact_summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("# Báo Cáo Triển Khai & Kiểm Thử Tự Động (Anti Gravity Artifact)\n\n")
        f.write(f"**Thời gian xuất:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Thư mục Output:** `{os.path.abspath(output_dir)}`\n\n")
        f.write(f"**Trạng Thái Kiểm Thử Console:** {'✅ THÀNH CÔNG (Exit Code 0)' if state.get('execution_success') else '⚠️ CẦN LƯU Ý / GẶP LỖI'}\n\n")
        
        f.write("## 1. Danh Sách Tệp Đã Tạo\n")
        created_files = state.get("created_files", {})
        if created_files:
            for rel, abs_path in created_files.items():
                f.write(f"- [`{rel}`]({abs_path})\n")
        else:
            f.write("- *(Không có file code riêng biệt)*\n")

        f.write("\n## 2. Kết Quả Chạy Thử Thực Tế (Console Execution Log)\n\n")
        f.write("```text\n")
        f.write(state.get("execution_logs", "No execution log recorded."))
        f.write("\n```\n\n")

        f.write("## 3. Giải Trình & Hướng Dẫn Sử Dụng (Tiếng Việt)\n\n")
        f.write(final_vi)
        f.write("\n\n---\n*Được tạo và tự động kiểm thử bởi LangGraph Multi-Agent Engine*\n")

    created_files["artifact_summary.md"] = summary_path
    return {
        "final_result_vi": final_vi,
        "created_files": created_files
    }

# Backward compatibility aliases for Streamlit UI or older scripts
output_translator_node = translate_and_finalize_node
output_translator_and_exporter_node = translate_and_finalize_node


# ==========================================
# 6. BUILD WORKFLOW GRAPH WITH SELF-CORRECTION LOOP
# ==========================================
workflow = StateGraph(PipelineState)

# Add Nodes
workflow.add_node("translate_input", input_translator_node)
workflow.add_node("select_skill", skill_selector_node)
workflow.add_node("research", research_agent_node)
workflow.add_node("drafter", drafter_agent)
workflow.add_node("reviewer", reviewer_agent)
workflow.add_node("refiner", refiner_agent)
workflow.add_node("executor", code_executor_node)
workflow.add_node("finalize", translate_and_finalize_node)

# Sequential Edges
workflow.add_edge(START, "translate_input")
workflow.add_edge("translate_input", "select_skill")
workflow.add_edge("select_skill", "research")
workflow.add_edge("research", "drafter")
workflow.add_edge("drafter", "reviewer")
workflow.add_edge("reviewer", "refiner")
workflow.add_edge("refiner", "executor")

# Conditional Edge: Self-Correction Feedback Loop based on Console Output
workflow.add_conditional_edges(
    "executor",
    should_retry_or_finalize,
    {
        "retry_refiner": "refiner",
        "finalize": "finalize"
    }
)
workflow.add_edge("finalize", END)

# Compile Workflow
app = workflow.compile()


# ==========================================
# 7. CLI ENTRY POINT
# ==========================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LangGraph Multi-Agent Pipeline with Auto-Reader, Research & Console Verification.")
    parser.add_argument("--task", type=str, default="Viết script Python kiểm tra cổng mạng (port check) an toàn.", help="Task description")
    parser.add_argument("--task-file", type=str, default=None, help="Path to file containing task description")
    parser.add_argument("--project-dir", type=str, default=None, help="Project or workspace directory to read context from")
    parser.add_argument("--file", type=str, default=None, help="Target file context to inspect or edit")
    parser.add_argument("--output-dir", type=str, default=None, help="Target output directory for generated files")
    args = parser.parse_args()

    task_text = args.task
    if args.task_file and os.path.exists(args.task_file):
        with open(args.task_file, "r", encoding="utf-8") as f:
            task_text = f.read()

    file_context_data = ""
    if args.file and os.path.exists(args.file):
        with open(args.file, "r", encoding="utf-8") as f:
            file_context_data = f"[File: {args.file}]\n{f.read()}"

    proj_dir = args.project_dir or (os.path.dirname(args.file) if args.file else None)
    proj_tree = scan_project_context(proj_dir) if proj_dir else ""

    input_data: PipelineState = {
        "task": task_text,
        "task_en": "",
        "project_dir": proj_dir,
        "project_tree": proj_tree,
        "file_context": file_context_data,
        "selected_skill": None,
        "research_notes": "",
        "draft_en": "",
        "critique_en": "",
        "final_result_en": "",
        "final_result_vi": "",
        "output_dir": args.output_dir,
        "created_files": {},
        "execution_logs": "",
        "execution_success": False,
        "retry_count": 0
    }

    print("=== BẮT ĐẦU CHẠY MULTI-AGENT PIPELINE (AUTO-RESEARCH, RUN & CONSOLE VERIFY) ===")
    print(f"Task: {input_data['task']}")
    if proj_dir:
        print(f"Project Workspace: {proj_dir}")
    print()

    current_state = dict(input_data)
    for output in app.stream(input_data):
        for node_name, state_update in output.items():
            print(f"--- [OK] Hoàn thành Node: {node_name} ---")
            current_state.update(state_update)

    print("\n================== KẾT QUẢ CUỐI CÙNG & TỆP XUẤT (ANTI GRAVITY STYLE) ==================")
    print(f"Thư mục xuất: {current_state.get('output_dir') or 'output/'}")
    for fname, fpath in current_state.get("created_files", {}).items():
        print(f" - {fname}: {fpath}")
    print("\n--- BÁO CÁO KIỂM THỬ CONSOLE ---")
    print(current_state.get("execution_logs", ""))
    print("\n--- BÁO CÁO GIẢI TRÌNH (TIẾNG VIỆT) ---")
    print(current_state.get("final_result_vi", ""))
