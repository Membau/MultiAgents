from langchain_ollama import ChatOllama

# Khởi tạo mô hình chạy local qua Ollama
llm = ChatOllama(
    model="qwen3:4b",
    temperature=0.2,
    base_url="http://localhost:11434",
)