# Model nền Qwen cho demo SmartEvent

**Built with Qwen.** Đây là bản sao nguyên trạng của model nền, không phải model
SmartEvent đã gộp LoRA. Adapter NLU/RAG của dự án được lưu riêng trong `models/`.

| Vai trò | Model nền | Phiên bản upstream cố định | Giấy phép |
|---|---|---|---|
| NLU | Qwen/Qwen2.5-1.5B-Instruct | `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` | Apache-2.0 |
| RAG | Qwen/Qwen2.5-3B-Instruct | `aa8e72537993ba99e69dfaafa59ed015b17504d1` | Qwen Research License |

Model 3B chỉ dùng cho nghiên cứu/đánh giá phi thương mại theo giấy phép đi kèm.
Mỗi model có file LICENSE nguyên văn của upstream. NOTICE giữ thông tin tác giả.
Không gán giấy phép Apache-2.0 của model 1.5B cho model 3B.

## Tải từ GitHub Releases

Trang phát hành dự kiến:
https://github.com/smartevent-ticketing/ai-service/releases/tag/qwen25-base-models-20261030

Chỉ khi bản phát hành đã công khai và có `base-models-manifest.json` mới tải được.
Các file khoảng 9,26 GB được chia thành nhiều phần dưới 2 GiB để đáp ứng giới hạn
GitHub. Clone Git thông thường không tự tải những asset này.

Tải file `download_base_models.py` từ Assets của bản phát hành. Trong thư mục
`ai-service`, chạy bằng Python 3.11 trở lên:

```powershell
python download_base_models.py --output .models/base
```

Nếu đã clone nhánh chứa công cụ phát hành:

```powershell
python scripts/release/download_base_models.py --output .models/base
```

Script tải tuần tự, ghép đúng tên file gốc và kiểm tra SHA-256 của từng phần lẫn
file hoàn chỉnh. Không cần GPU để tải/ghép model. Cần khoảng 10 GB chỗ trống cho
đầu ra. Khi chạy lại, file hoàn chỉnh có hash đúng sẽ được giữ; file khác không
bị ghi đè. Không đưa thư mục `.models` vào Git.

Sau khi đã có launcher demo và môi trường PEFT/CUDA tương ứng:

```powershell
.\scripts\local\run_sequential.ps1 `
  -BaseModelPath .models/base/nlu `
  -RagBaseModelPath .models/base/rag
```

Vẫn cần giải nén adapter và chuẩn bị corpus theo tài liệu demo. Bản phát hành
model nền không thay thế các bước cài thư viện, kiểm thử và cấu hình ứng dụng.

## Khởi chạy phát hành bằng tài khoản GitHub của bạn

Nếu kết nối GitHub của ChatGPT không có quyền ghi, dùng PowerShell thông thường
tại `ai-service`:

```powershell
gh auth login --hostname github.com --scopes workflow
.\.venv\Scripts\python.exe scripts/release/publish_base_models.py --start-workflow
```

Tài khoản phải có quyền ghi vào `smartevent-ticketing/ai-service` và quyền cập
nhật workflow. Lệnh thứ hai tạo nhánh `publish/base-models-qwen25-20261030` từ
`main` trên GitHub và chỉ thêm sáu file phục vụ xuất model cùng manifest nguồn.
Nó không commit, checkout hay đẩy các thay đổi ứng dụng đang làm dở trên máy.
Push nhánh sẽ khởi chạy workflow tải và xuất model bằng GitHub Actions.

Lệnh in link Actions để theo dõi. Chỉ khi job thành công và release đã công khai
mới có thể tải model từ trang Releases. Nếu nhánh đã tồn tại, vào Actions để
chạy lại job thay vì ghi đè nhánh hoặc asset khác.

## Tính toàn vẹn và phát hành

`models/base-models-source.json` khóa phiên bản, kích thước và SHA-256 của đúng
các trọng số/cấu hình đã có trên máy phát triển. Workflow tải bản gốc từ URL
Hugging Face chứa commit cố định và từ chối nếu khác hash. Trọng số không bị
lượng tử hóa lại hoặc chỉnh sửa trước khi phát hành.

Workflow tạo draft, tải lên từng phần và kiểm tra digest do GitHub trả về. Chỉ
sau khi tất cả model, LICENSE, NOTICE, hướng dẫn và manifest được xác minh mới
công khai release. Lỗi tải/hash/upload giữ release ở draft. Chạy lại có thể
dùng lại asset có cùng kích thước và digest; asset khác không bị ghi đè.

Nguồn giấy phép:
- https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/blob/989aa7980e4cf806f80c7fef2b1adb7bc71aa306/LICENSE
- https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/aa8e72537993ba99e69dfaafa59ed015b17504d1/LICENSE
