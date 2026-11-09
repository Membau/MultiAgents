# LangGraph Multi-Agent Collaboration Pipeline

He thong phoi hop da tac nhan (Multi-Agent Sequential Pipeline) duoc xay dung tren nen tang LangGraph. He thong ket hop giua mo hinh cuc bo (Local LLM qua Ollama) va mo hinh dam may (Google Gemini API tu hai tai khoan doc lap) nham toi uu hoa chi phi token, tang cuong tinh bao mat va nang cao chat luong tao ma nguon.

---

## 1. Kien Truc Pipeline

Luong xu ly di qua 6 buoc tuan tu khep kin:

```
[User Task (VI)]
       |
       v
[1. Translate Input (VI -> EN)] (Qwen 4B Local)
       |
       v
[2. Skill Selector] (Qwen 4B Local - doc tu skills_list.txt)
       |
       v
[3. Agent A - Drafter] (Qwen 4B Local - viet code/phac thao ban dau)
       |
       v
[4. Agent B - Reviewer] (Gemini 3.5 Flash-Lite - Tai khoan 1 - it token)
       |
       v
[5. Agent C - Refiner] (Gemini 3.5 Flash - Tai khoan 2 - nhieu token)
       |
       v
[6. Translate Output (EN -> VI)] (Qwen 4B Local)
       |
       v
[Ket Qua Hoan Thien]
```

### Chi Tiet Cac Node
1. **Translate Input (VI -> EN)**: Chuyen doi yeu cau ky thuat sang Tieng Anh de cac agent suy luan voi do chinh xac cao nhat.
2. **Skill Selector**: Danh gia de bai voi danh sach ky nang chuyen biet. Neu phu hop se nap toan bo tap lenh cua skill do vao Agent; neu khong phu hop se tu dong bo qua.
3. **Agent A (Drafter - Local Qwen 4B)**: Lap dan y va sinh code phac thao ban dau hoan toan offline, khong ton chi phi cloud.
4. **Agent B (Reviewer - Gemini 3.5 Flash-Lite)**: Su dung tai khoan it token de kiem tra loi logic, lo hong bao mat va xuat checklist danh gia ngan gon.
5. **Agent C (Refiner - Gemini 3.5 Flash)**: Su dung tai khoan co han muc token cao de tong hop, sua loi va viet lai toan bo bo ma nguon chuan production.
6. **Translate Output (EN -> VI)**: Su dung Qwen Local de chuyen ngu phan giai thich sang Tieng Viet tu nhien, dong thoi bao toan 100% cac khoi ma nguon (code blocks).

---

## 2. Cau Truc Thu Muc

```
langgraph/
|-- skills/                      # Thu muc chua cac tap tin huong dan ky nang (.md)
|   |-- network.md
|   |-- web_scraping.md
|   |-- data_analysis.md
|   |-- database_sql.md
|   `-- file_processing.md
|-- .env.example                 # File mau khai bao API Key
|-- .gitignore                   # Bo qua .env, venv va cache
|-- MultiAgents.py               # Dinh nghia Graph va logic thuc thi chinh cua LangGraph
|-- app_ui.py                    # Giao dien web giam sat truc quan bang Streamlit
|-- chatollama.py                # Script mau ket noi Ollama
|-- run_pipeline.py              # Script CLI goi pipeline tu bat ky workspace nao
|-- skills_list.txt              # Danh muc dang ky cac skill kem mo ta
`-- README.md                    # Tai lieu huong dan
```

---

## 3. Yeu Cau He Thong

- Python 3.10 tro len.
- Ollama da cai dat va chay tai dia chi `http://localhost:11434`.
- Model `qwen3:4b` tren Ollama:
  ```powershell
  ollama run qwen3:4b
  ```
- 2 API Key hop le cua Google Gemini tu 2 tai khoan khac nhau.

---

## 4. Cai Dat & Cau Hinh

### Buoc 1: Cai dat moi truong ao va thu vien

```powershell
# Tao moi truong ao (neu chua co)
python -m venv venv

# Kich hoat moi truong ao tren Windows
.\venv\Scripts\Activate.ps1

# Cai dat cac thu vien can thiet
pip install langgraph langchain-core langchain-ollama langchain-google-genai python-dotenv streamlit
```

### Buoc 2: Thiet lap khoa API (.env)

Tao file `.env` tai thu muc goc (sao chep tu `.env.example`) va dien khoa API:

```env
# Tai khoan 1 (Reviewer - it token): gemini-3.5-flash-lite
GEMINI_API_KEY_REVIEWER="AIzaSy..."

# Tai khoan 2 (Refiner - nhieu token): gemini-3.5-flash
GEMINI_API_KEY_REFINER="AIzaSy..."
```

---

## 5. Huong Dan Su Dung

### Cach 1: Su dung giao dien Streamlit UI (Khuyen dung)

Giao dien web truc quan cho phep theo doi tien do theo thoi gian thuc, xem thoi gian phan hoi cua tung Agent va noi dung chi tiet tung buoc:

```powershell
.\venv\Scripts\python.exe -m streamlit run app_ui.py
```
Trinh duyet se tu dong mo tai: `http://localhost:8501`

### Cach 2: Chay truc tiep qua Command Line (CLI)

Chay ngay tai thu muc du an:

```powershell
.\venv\Scripts\python.exe run_pipeline.py --task "Viet script Python quet cong mang tren localhost su dung threading"
```

Truyen kem tap tin ma nguon tu mot du an khac de review/refactor:

```powershell
.\venv\Scripts\python.exe run_pipeline.py --task "Review va toi uu file nay" --file "D:/OtherProject/main.py"
```

---

## 6. Quan Ly Ky Nang (Skills System)

He thong tu dong nap cac skill duoc khai bao trong `skills_list.txt`:

```text
skills/network.md "ky nang ve kien truc mang, quet cong, lap trinh socket va bao mat mang"
skills/web_scraping.md "ky nang boc tach du lieu web, HTTP request va parse HTML"
skills/data_analysis.md "ky nang xu ly du lieu bang, thong ke tinh toan voi pandas va numpy"
```

Moi file markdown trong thu muc `skills/` chua cac quy chuan code va chi dan rieng biet. Khi Qwen phat hien yeu cau lien quan, chi dan nay se duoc nap truc tiep vao prompt cua Agent Drafter de dinh huong code chuan xac.
