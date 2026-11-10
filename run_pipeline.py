import os
import sys
import time
import argparse
import subprocess

# Dinh nghia duong dan co dinh toi Engine Multi-Agent LangGraph
LANGGRAPH_DIR = r"D:\Hoc_Tap\langgraph"
PYTHON_EXE = os.path.join(LANGGRAPH_DIR, "venv", "Scripts", "python.exe")
MULTI_AGENT_SCRIPT = os.path.join(LANGGRAPH_DIR, "MultiAgents.py")

def run_multi_agent(
    task_text: str,
    file_path: str = None,
    project_dir: str = None,
    output_dir: str = None
) -> str:
    """
    Thuc thi pipeline Multi-Agent voi ho tro:
    - Tu dong doc cau truc du an & ngu canh (Auto-reader)
    - Tu dong xuat code va artifact sang thu muc output (Anti Gravity style)
    - Streaming log thoi gian thuc
    """
    if not os.path.exists(PYTHON_EXE):
        raise FileNotFoundError(f"Khong tim thay moi truong Python: {PYTHON_EXE}")

    if not os.path.exists(MULTI_AGENT_SCRIPT):
        raise FileNotFoundError(f"Khong tim thay script Multi-Agent: {MULTI_AGENT_SCRIPT}")

    # Luu task vao file tam de tranh gioi han dong lenh Windows
    temp_task_file = os.path.join(LANGGRAPH_DIR, "temp_task.txt")
    with open(temp_task_file, "w", encoding="utf-8") as f:
        f.write(task_text)

    cmd = [
        PYTHON_EXE, "-u", MULTI_AGENT_SCRIPT,
        "--task-file", temp_task_file
    ]

    if file_path:
        cmd.extend(["--file", os.path.abspath(file_path)])

    target_project = project_dir or (os.path.dirname(os.path.abspath(file_path)) if file_path else os.getcwd())
    if target_project and os.path.exists(target_project):
        cmd.extend(["--project-dir", os.path.abspath(target_project)])

    if output_dir:
        cmd.extend(["--output-dir", os.path.abspath(output_dir)])

    print("\n=== KHOI DONG MULTI-AGENT PIPELINE (AUTO-READER & ARTIFACT EXPORTER) ===")
    print(f"Task: {task_text[:100]}...")
    if file_path:
        print(f"File Context: {file_path}")
    if target_project:
        print(f"Project Workspace: {target_project}")
    print("=" * 65)
    
    start_time = time.time()

    process = subprocess.Popen(
        cmd,
        cwd=LANGGRAPH_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1
    )

    output_lines = []
    for line in iter(process.stdout.readline, ""):
        sys.stdout.write(line)
        sys.stdout.flush()
        output_lines.append(line)

    process.stdout.close()
    return_code = process.wait()

    elapsed = time.time() - start_time
    print(f"\n=== TONG THOI GIAN THUC THI: {elapsed:.1f}s ===")

    if return_code != 0:
        print(f"[Error] Pipeline ket thuc voi ma loi: {return_code}")

    return "".join(output_lines)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cau noi thuc thi Multi-Agent Pipeline tu bat ky du an nao.")
    parser.add_argument("--task", "-t", type=str, required=True, help="Noi dung yeu cau hoac nhiem vu")
    parser.add_argument("--file", "-f", type=str, default=None, help="Duong dan file context can xu ly (tuy chon)")
    parser.add_argument("--project-dir", "-p", type=str, default=None, help="Thu muc goc du an de auto-read context")
    parser.add_argument("--output-dir", "-o", type=str, default=None, help="Thu muc xuat file (Anti Gravity style)")
    args = parser.parse_args()

    run_multi_agent(
        task_text=args.task,
        file_path=args.file,
        project_dir=args.project_dir,
        output_dir=args.output_dir
    )
