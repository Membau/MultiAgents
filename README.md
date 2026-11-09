# He Thong Multi-Agent Tuan Tu Voi LangGraph

He thong xu ly da tac nhan (Multi-Agent Pipeline) theo kien truc tuan tu su dung LangGraph, ket hop giua mo hinh cuc bo (Local LLM qua Ollama) va mo hinh dam may (Google Gemini API tu hai tai khoan doc lap).

---

## 1. Nguyen Nhan Treo Tien Trinh & Cach Khac Phuc

Khi su dung mo hinh cu (`gemini-2.5-flash`), Google API da ngung ho tro va tra ve loi 404/503 khien tien trinh bi retry vo tan va treo chet khong phan hoi.

He thong da duoc cap nhat toan dien:
- Reviewer (Tai khoan it token): Chuyen sang `gemini-3.5-flash-lite` (cuc nhanh, tiet kiem token).
- Refiner (Tai khoan nhieu token): Chuyen sang `gemini-3.5-flash` (on dinh, chat luong cao).
- Logging theo thoi gian thuc: Khong con bi buffering im lang; moi buoc hoan thanh deu bao thoi gian va so ky tu sinh ra ngay lap tuc.

---

## 2. Giao Dien Truc Quan (Streamlit UI)

De theo doi ro rang tung buoc dang chay (step-by-step progress bar, thoi gian xu ly tung agent, preview ban nhap va ket qua cuoi cung):

```powershell
.\venv\Scripts\python.exe -m streamlit run app_ui.py
```

Trinh duyet se tu dong mo tai dia chi `http://localhost:8501`.

---

## 3. Chay Qua Command-Line (CLI)

Neu muon chay truc tiep trong terminal hoac tu bat ky thu muc du an nao tren may:

```powershell
.\venv\Scripts\python.exe run_pipeline.py --task "Noi dung nhiem vu cua ban"
```

Neu co file code trong du an can truyen vao de review/refactor:

```powershell
.\venv\Scripts\python.exe run_pipeline.py --task "Review va sua loi file nay" --file "D:/du_an_khac/main.py"
```

---

## 4. Cau Hinh API Key (.env)

Mo file `.env` o thu muc goc va dien key:

```env
# Tai khoan 1 (Reviewer - gemini-3.5-flash-lite)
GEMINI_API_KEY_REVIEWER="AIzaSy..."

# Tai khoan 2 (Refiner - gemini-3.5-flash)
GEMINI_API_KEY_REFINER="AIzaSy..."
```
