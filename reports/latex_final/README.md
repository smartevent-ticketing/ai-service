# Báo cáo LaTeX SmartEvent

Điểm vào: `main.tex`. Bản PDF sau hiệu chỉnh ngày 31/10/2026 có 45 trang.

## Biên dịch

Tại thư mục này, với MiKTeX/TeX Live và các gói đã cài:

```shell
pdflatex -interaction=nonstopmode -halt-on-error -no-shell-escape main.tex
pdflatex -interaction=nonstopmode -halt-on-error -no-shell-escape main.tex
```

Chạy thêm một lượt nếu LaTeX yêu cầu cập nhật tham chiếu. Không cần shell escape hoặc tải model AI.

## Phạm vi hiệu chỉnh

- Sửa tóm tắt, mở đầu, bốn chương, kết luận và nguồn tham khảo nội bộ.
- Phân biệt thiết kế v1.2 với runtime, token accuracy với độ đúng tác vụ, benchmark nhỏ với nghiệm thu tích hợp.
- Sửa mô tả BM25, RRF, fail-closed, tool gate, BFF và kiểm tra ngân sách token.
- Thay kết quả hybrid chưa có artifact bằng kết quả ngoại tuyến có nguồn; cập nhật kiểm thử theo biên bản 30/10.
- Giữ thông tin thành viên, bìa và các ô ảnh/nhận xét/chấm điểm cần người phụ trách điền.
- Không sửa mã ứng dụng/cấu hình và không chạy lại kiểm thử ứng dụng trong đợt sửa báo cáo.

`evidence/source_manifest.json` lưu đường dẫn và SHA-256 của các nguồn đã đối chiếu. `evidence/latex_validation.json` ghi kết quả kiểm tra PDF. Số liệu huấn luyện lịch sử chưa có đủ log/manifest để tái lập độc lập; không xem là bằng chứng nghiệm thu hiện hành.

Thư mục báo cáo hiện bị Git bỏ qua theo cấu hình có sẵn. Đợt này không sửa `.gitignore` và không đưa báo cáo lên GitHub.
