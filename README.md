# LangGraph Multi-Agent Autonomous Engineering Pipeline

Hệ thống phối hợp đa tác nhân thông minh (**Multi-Agent Autonomous Pipeline**) được xây dựng trên nền tảng **LangGraph**. Hệ thống kết hợp giữa **Mô hình cục bộ (Local Qwen qua Ollama)** và **Mô hình đám mây (Google Gemini API qua 2 tài khoản độc lập)** nhằm tối ưu chi phí token, bảo mật thông tin, đồng thời cung cấp khả năng **tự động nghiên cứu (Research)**, **tự đọc cấu trúc dự án (Project Context Auto-Reader)**, **tự chạy thử & đọc log console (Sandbox Code Execution)**, cùng **vòng lặp tự gỡ lỗi (Self-Correction Loop)** và **trực tiếp xuất file mã nguồn (Anti Gravity-style Artifacts)**.

---

## 1. Kiến Trúc Pipeline

Quy trình khép kín gồm 8 bước với vòng lặp tự phản hồi (Feedback Loop) dựa trên kết quả thực thi terminal:

```
                     ┌───────────────────────────┐
                     │     User Task Input       │
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │ 1. Translate Task (VI->EN)│ (Local Qwen - bảo toàn ngữ cảnh)
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │ 2. Dynamic Skill Selector │ (Chọn trong 14 domain skills)
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │ 3. Deep Research Agent    │ (Mở rộng edge cases & test design)
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │ 4. Drafter (Agent A)      │ (Local Qwen - sinh code phác thảo)
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │ 5. Reviewer (Agent B)     │ (Gemini Acc 1: gemini-3.5-flash-lite)
                     └─────────────┬─────────────┘
                                   │
                                   ▼
          ┌─────────►┌───────────────────────────┐
          │          │ 6. Refiner (Agent C)      │ (Gemini Acc 2: gemini-3.5-flash)
          │          └─────────────┬─────────────┘
          │                        │
          │                        ▼
          │          ┌───────────────────────────┐
          │          │ 7. Code Executor & Tester │ (Xuất file ra disk & chạy subprocess)
          │          └─────────────┬─────────────┘
          │                        │
  [Console Error?]                 ▼
  (Lặp tối đa 2 lần)     [Kiểm tra Exit Code?]
          │                     /         \
          └─────────── (Exit != 0)       (Exit == 0 / Hết retry)
                                             │
                                             ▼
                             ┌───────────────────────────┐
                             │ 8. Finalize & Artifacts   │ (Xuất summary.md & log console)
                             └─────────────┬─────────────┘
                                             │
                                             ▼
                             ┌───────────────────────────┐
                             │  Output Folder (Disk)     │
                             └───────────────────────────┘
```

---

## 2. Các Tính Năng Nổi Bật

### 🚀 1. Tự Động Kiểm Tra & Khởi Động Ollama Ngầm
- Không cần nhớ bật ứng dụng Ollama trước khi chạy.
- Pipeline tự động ping `http://localhost:11434/api/version`. Nếu chưa bật, hệ thống sẽ tự động kích hoạt `ollama serve` ở chế độ chạy ngầm và đợi server sẵn sàng.

### 🌐 2. Tự Đọc Toàn Bộ Cấu Trúc Dự Án (Project Context Auto-Reader)
- Truyền cờ `--project-dir <path>`: Hệ thống tự động quét và vẽ sơ đồ cây thư mục (bỏ qua `.git`, `node_modules`, `venv`, `__pycache__`), giúp các Agent hiểu rõ kiến trúc tổng thể của dự án trước khi sinh code.

### 🔬 3. Deep Research & Requirements Expansion
- Node Research phân tích sâu các rủi ro kỹ thuật:
  - Khác biệt hệ điều hành (Windows CRLF/sockets vs Linux).
  - Race conditions, timeout, quản lý tài nguyên và exception handling.
  - Thiết kế tiêu chí kiểm thử tự động (Executable Test Cases) trước khi viết code.

### ⚡ 4. Thực Thi Mã Nguồn Trong Sandbox & Đọc Log Console Thực Tế
- Mã nguồn được tự động ghi xuống ổ đĩa trong thư mục `output/`.
- Hệ thống tự động dò tìm file kiểm thử (`test_*.py`) hoặc file thực thi chính và chạy thử bằng Python venv với timeout an toàn 25 giây.
- Thu nhận toàn bộ `stdout`, `stderr` và mã thoát (`returncode`).

### 🔁 5. Vòng Lặp Tự Sửa Lỗi (Self-Correction Loop)
- Nếu console trả về lỗi (SyntaxError, ImportError, TypeError, AssertionError):
  - Hệ thống tự động lấy toàn bộ traceback từ terminal console gửi ngược lại cho Agent C (Refiner).
  - Agent C tự động phân tích nguyên nhân lỗi, viết lại mã nguồn đã fix và chạy lại kiểm thử (tự lặp tối đa 2 lần).

### 📦 6. Xuất File Chuẩn Phong Cách Anti Gravity Artifacts
- Tự động bóc tách từng file mã nguồn và lưu vào đúng cấu trúc thư mục con trong `output/<task_name>_<timestamp>/`.
- Tự động tạo file `artifact_summary.md` chứa:
  - Trạng thái kiểm thử Console: `✅ THÀNH CÔNG (Exit Code 0)` hoặc `⚠️ CẦN LƯU Ý`.
  - Toàn văn Console Output Log.
  - Báo cáo giải trình kiến trúc và hướng dẫn sử dụng bằng Tiếng Việt.

---

## 3. Cấu Trúc Thư Mục Dự Án

```
d:\Hoc_Tap\langgraph\
├── skills/                                    # 14 bộ quy chuẩn kỹ thuật phần mềm kinh điển
│   ├── clean-code/                            # SKILL.md & clean-code.mini.md
│   ├── clean-architecture/                    # SKILL.md & clean-architecture.mini.md
│   ├── a-philosophy-of-software-design/       # SKILL.md & mini.md
│   ├── the-pragmatic-programmer/              # SKILL.md & mini.md
│   ├── refactoring/                           # SKILL.md & mini.md
│   ├── refactoring-guru/                      # SKILL.md & mini.md
│   ├── domain-driven-design/                  # SKILL.md & mini.md
│   ├── domain-driven-design-distilled/        # SKILL.md & mini.md
│   ├── implementing-domain-driven-design/     # SKILL.md & mini.md
│   ├── designing-data-intensive-applications/ # SKILL.md & mini.md
│   ├── release-it/                            # SKILL.md & mini.md
│   ├── code-complete/                         # SKILL.md & mini.md
│   └── working-effectively-with-legacy-code/  # SKILL.md & mini.md
├── output/                                    # Thư mục chứa code và artifact_summary.md đã xuất
├── venv/                                      # Môi trường ảo Python
├── .env                                       # Cấu hình API Keys (không commit lên git)
├── .env.example                               # Mẫu cấu hình API Keys
├── MultiAgents.py                             # Định nghĩa Graph và toàn bộ Logic Multi-Agent
├── run_pipeline.py                            # Cầu nối CLI thực thi pipeline từ bất kỳ thư mục nào
├── app_ui.py                                  # Giao diện trực quan qua Streamlit
├── skills_list.txt                            # Danh mục đăng ký 14 domain skills
└── README.md                                  # Tài liệu hướng dẫn hệ thống
```

---

## 4. Yêu Cầu & Cài Đặt

### 1. Yêu cầu hệ thống
- Python 3.10+ trên Windows/Linux/macOS.
- [Ollama](https://ollama.com/) đã cài đặt trên máy.
- Model `qwen3:4b` trong Ollama:
  ```powershell
  ollama pull qwen3:4b
  ```
- 2 API Key Google Gemini (tạo miễn phí tại [Google AI Studio](https://aistudio.google.com/apikey)).

### 2. Thiết lập môi trường
```powershell
# Di chuyển vào thư mục dự án
cd D:\Hoc_Tap\langgraph

# Kích hoạt venv
.\venv\Scripts\activate

# Cài đặt thư viện phụ thuộc
pip install langgraph langchain-core langchain-ollama langchain-google-genai google-genai python-dotenv streamlit
```

### 3. Cấu hình khóa API (.env)
Tạo file `.env` tại thư mục gốc:
```env
# Tài khoản 1: Gemini Reviewer & Researcher (model: gemini-3.5-flash-lite)
GEMINI_API_KEY_REVIEWER="AIzaSy..."

# Tài khoản 2: Gemini Refiner & Code Synthesizer (model: gemini-3.5-flash)
GEMINI_API_KEY_REFINER="AIzaSy..."

# Cấu hình model tùy chọn (mặc định đã tối ưu)
# GEMINI_MODEL_REVIEWER="gemini-3.5-flash-lite"
# GEMINI_MODEL_REFINER="gemini-3.5-flash"
```

---

## 5. Hướng Dẫn Sử Dụng

### Cách 1: Chạy qua Command Line (Khuyên dùng trong Workflow lập trình)

#### Chạy tác vụ độc lập:
```powershell
.\venv\Scripts\python.exe run_pipeline.py --task "Viết module rate-limiter Token Bucket bằng Python hỗ trợ đa luồng và kèm unit test."
```

#### Tự động đọc ngữ cảnh toàn bộ Workspace và xuất thẳng file vào thư mục đích:
```powershell
.\venv\Scripts\python.exe run_pipeline.py `
  --task "Xây dựng service xác thực JWT và phân quyền người dùng" `
  --project-dir "D:\MyWorkspace\BackendProject" `
  --output-dir "D:\MyWorkspace\BackendProject\src\auth"
```

#### Tập trung xử lý hoặc Refactor một file cụ thể:
```powershell
.\venv\Scripts\python.exe run_pipeline.py `
  --task "Refactor file này theo nguyên lý Clean Code và viết unit test kiểm thử" `
  --file "D:\MyWorkspace\legacy_module.py"
```

### Cách 2: Chạy qua Giao diện Web (Streamlit UI)
```powershell
.\venv\Scripts\python.exe -m streamlit run app_ui.py
```
Giao diện sẽ tự động mở tại `http://localhost:8501`, hỗ trợ theo dõi từng bước xử lý theo thời gian thực.

---

## 6. Kiểm Soát Chất Lượng & Phục Hồi Lỗi (Resilience)

1. **Khả năng chịu lỗi Gemini Cloud:** Tích hợp hàm `invoke_gemini_with_fallback()` tự động chuyển đổi sang model dự phòng (`gemini-3.5-flash-lite`, `gemini-3.5-flash`, `gemini-flash-latest`) khi gặp lỗi `503 UNAVAILABLE` (quá tải đột biến) hoặc `429 RESOURCE_EXHAUSTED`.
2. **Khả năng tự vá code:** Nếu code do Agent C sinh ra không thể import hoặc fail assertion trong bài test, hệ thống tự động cung cấp traceback cho chính Agent C để tự gỡ lỗi mà không cần sự can thiệp thủ công của lập trình viên.
3. **Tiết kiệm token tối đa:** Các bước dịch thuật, chọn skill và phác thảo code ban đầu được thực hiện 100% offline bằng mô hình cục bộ Qwen 4B, chỉ sử dụng Gemini Cloud cho tầng Review kiến trúc và Tinh chỉnh sản phẩm cuối cùng.

---
*Phát triển bởi MemBau & Tui - Được hỗ trợ bởi LangGraph, Ollama & Google Gemini API.*
