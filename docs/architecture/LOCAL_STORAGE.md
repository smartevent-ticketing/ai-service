# Lưu model và cache khi chạy local trên Windows

Checkout hiện tại: `D:/SmartEventRepos/ai-service`.

- Model gốc, adapter và bản chuyển đổi nằm trong `models/` hoặc `artifacts/` trên D.
- Cache Hugging Face, PyTorch, pip, uv và file tạm nằm trong `artifacts/model-cache/`.
- Ollama dùng `artifacts/ollama-home/`; Compose dùng bind mount, không tạo volume model mới.
- Các thư mục cache và trọng số sinh thêm đã được bỏ qua bởi Git; `models/` cũng bị loại khỏi Docker build context.

Trước khi cài dependency hoặc chạy model trực tiếp, mở PowerShell tại repo và chạy:

```powershell
. ./scripts/set-local-storage.ps1
```

Script chỉ tạo thư mục và đặt biến cho phiên PowerShell hiện tại, không tải model, không cài thư viện và không di chuyển dữ liệu hiện có. Môi trường Python nên được tạo tại `.venv/` trong checkout này.

**Docker Desktop lưu image, cache build và named volume trong ổ đĩa ảo riêng.** Các bind mount ở trên không thay đổi vị trí ổ đĩa ảo đó. Chuyển nó sang D cần thực hiện bằng thiết lập lưu trữ của Docker Desktop, áp dụng cho toàn bộ các dự án Docker trên máy. Không tự di chuyển hoặc xóa `docker_data.vhdx`; file này chứa cả dữ liệu PostgreSQL/MinIO của dự án.

Script `smartevent-infra/deploy/start-chatbot-local.ps1` mặc định chỉ chạy các image đã có, không pull/build. Ollama chỉ được chạy khi backend được cấu hình dùng Ollama và có cờ `-EnableModelRuntime`. Cờ này không tải hoặc import model. Hiện hai checkpoint chưa được nghiệm thu; cache Ollama sao chép dở không phải bộ model sẵn sàng sử dụng.
