import argparse
import os
import subprocess
import sys
import time

# Dinh nghia duong dan co dinh toi Engine Multi-Agent LangGraph
LANGGRAPH_DIR = r"D:\Hoc_Tap\langgraph"
PYTHON_EXE = os.path.join(LANGGRAPH_DIR, "venv", "Scripts", "python.exe")
MULTI_AGENT_SCRIPT = os.path.join(LANGGRAPH_DIR, "MultiAgents.py")


def run_multi_agent(task_text: str, file_path: str = None) -> str:
  """Thuc thi pipeline Multi-Agent voi streaming log theo thoi gian thuc, tranh treo tien trinh."""
  if not os.path.exists(PYTHON_EXE):
    raise FileNotFoundError(f"Khong tim thay moi truong Python: {PYTHON_EXE}")

  if not os.path.exists(MULTI_AGENT_SCRIPT):
    raise FileNotFoundError(
        f"Khong tim thay script Multi-Agent: {MULTI_AGENT_SCRIPT}"
    )

  full_task = task_text
  if file_path:
    if os.path.exists(file_path):
      with open(file_path, "r", encoding="utf-8") as f:
        file_content = f.read()
      full_task = f"{task_text}\n\n[File Context: {file_path}]\n{file_content}"
    else:
      print(f"[Warning] Khong tim thay file context: {file_path}")

  # Luu task vao file tam de tranh gioi han do dai dong lenh Windows (WinError 206)
  temp_task_file = os.path.join(LANGGRAPH_DIR, "temp_task.txt")
  with open(temp_task_file, "w", encoding="utf-8") as f:
    f.write(full_task)

  # Goi subprocess voi tham so unbuffered (-u) de in log ngay lap tuc
  cmd = [PYTHON_EXE, "-u", MULTI_AGENT_SCRIPT, "--task-file", temp_task_file]

  print("\n=== KHOI DONG MULTI-AGENT PIPELINE ===")
  start_time = time.time()

  process = subprocess.Popen(
      cmd,
      cwd=LANGGRAPH_DIR,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      encoding="utf-8",
      errors="replace",
      bufsize=1,
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
  parser = argparse.ArgumentParser(
      description="Cau noi thuc thi Multi-Agent Pipeline tu bat ky du an nao."
  )
  parser.add_argument(
      "--task",
      "-t",
      type=str,
      required=True,
      help="Noi dung yeu cau hoac nhiem vu",
  )
  parser.add_argument(
      "--file",
      "-f",
      type=str,
      default=None,
      help="Duong dan file context can xu ly (tuy chon)",
  )
  args = parser.parse_args()

  run_multi_agent(task_text=args.task, file_path=args.file)
