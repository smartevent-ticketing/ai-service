# Gia cố chatbot local — 30/10/2026

## Hiện trạng công nghệ

| Thành phần | Thực tế |
|---|---|
| Hiểu câu hỏi | Bộ phân loại tiếng Việt theo luật, có hỗ trợ câu không dấu; chưa có LLM/QLoRA trong runtime |
| Sự kiện | GET API backend, chỉ kết quả công khai đã qua projection; có nút mở sự kiện |
| Hướng dẫn chung | Corpus gồm 5 tài liệu được chủ dự án duyệt cho demo local, có citation |
| Tìm trong corpus | BM25, ưu tiên câu hỏi của từng mục và độ bao phủ nội dung; loại kết quả chỉ trùng từ chung |
| Lưu chỉ mục | Catalog/release JSON bất biến, pin SHA-256, mount chỉ đọc |
| pgvector | Chưa được dùng trong chatbot; không có kết nối SQL từ AI tới database nghiệp vụ |
| Embedding/ONNX | Có adapter và benchmark offline từ trước; chưa được bật để phục vụ chat |

pgvector là một lựa chọn lưu và tìm vector, không thay thế bộ phân loại câu hỏi, dữ liệu nguồn hay kiểm tra câu trả lời. Đợt sửa này tập trung vào những nguyên nhân đã tái hiện: câu hỏi công khai bị đưa vào luồng tài khoản, corpus chưa được cấu hình, các mục tài liệu cùng từ khóa xếp hạng nhầm, thiếu kiểm tra nguồn và hội thoại bị kẹt khi làm mới.

## Những thay đổi chính

- Thêm `PUBLIC_HELP`: “Có những cách thanh toán nào?” và câu không dấu đi vào corpus, còn “Đơn của tôi đã thanh toán chưa?” giữ luồng riêng tư và không đọc corpus để suy diễn trạng thái.
- Mở luồng corpus cho hướng dẫn chung và câu hỏi hoàn tiền. Corpus hướng dẫn không cam kết điều kiện, phí hoặc hạn hoàn tiền.
- Nhận diện thêm các thành phố trong bộ seed; khi hỏi tiếp chỉ đổi thành phố, giữ từ khóa đang tìm.
- Truy xuất ưu tiên các từ đặc trưng (ví dụ MoMo) và câu hỏi của mục tài liệu; độ trùng từ trong tiêu đề chung không đủ để thay thế bằng chứng trong nội dung.
- Làm mới hội thoại đặt lại trạng thái chờ; phản hồi cũ tiếp tục bị loại bằng mã lượt yêu cầu.
- Gợi ý câu hỏi trên giao diện khớp khả năng đã bật. `/health/ready` công khai `backend=bm25`, `vector_store=null`, `semantic_enabled=false` để không nhầm với semantic RAG.

## Nguồn và phê duyệt

[Năm tài liệu hướng dẫn](../../datasets/help_review_2026_10_30/README.md) đã được người dùng xác nhận “Duyệt dùng cho demo local”. [Hồ sơ duyệt](../../datasets/help_review_2026_10_30/approval.json) pin nội dung từng tài liệu. Không dùng năm bản nháp cũ làm nguồn phục vụ.

Catalog dùng định dạng artifact `PRODUCTION` để phân biệt nguồn thật được duyệt với fixture `TEST_ONLY`; phạm vi phê duyệt vẫn chỉ là demo local, không phải nghiệm thu production. Build tạo tokenizer WordLevel local cho việc đo ngân sách chunk; đây không phải huấn luyện mô hình hiểu ngôn ngữ hoặc model embedding.

## Build và kiểm chứng

Trong môi trường dev đã cài dependency của repo:

```powershell
docker build -t smartevent-ai-service:local-public-search .
./scripts/verify-public-search.ps1 -OutputDirectory artifacts/local-chatbot-hardening-search
python scripts/build_local_help.py --search-config artifacts/local-chatbot-hardening-search/configs --output artifacts/local-chatbot-hardening
```

Các thư mục kết quả phải mới. Bộ kiểm chứng search tạo backend/PostgreSQL riêng và so sánh dữ liệu trước/sau. Builder corpus từ chối nếu nội dung khác checksum đã duyệt, hết thời hạn duyệt hoặc bằng chứng search không khớp mã nguồn. Thư viện `tokenizers` chỉ cần ở bước build, không cần trong container phục vụ.

Builder thử 17 câu hỏi có nguồn kỳ vọng qua bộ truy xuất lẫn HTTP chatbot, gồm câu không dấu và câu hỏi tiếp như “Còn MoMo thì sao?”. Đồng thời thử câu không có nguồn, câu tài khoản riêng tư, thu hồi tài liệu, catalog hết hạn, gate bị khóa và release sai checksum. Nếu kiểm tra thất bại, cấu hình kết quả được đưa về tắt RAG; không dùng bộ đó để triển khai.

Đặt `AI_REVIEWED_CONFIG_DIR=./artifacts/local-budget-fix/configs` trong `.env` của AI rồi chạy `docker compose -f docker-compose.local.yml up -d`. Runtime mount toàn bộ catalog/release và cấu hình ở chế độ chỉ đọc.

Catalog có thời hạn tối đa **7 ngày**; hồ sơ nội dung được duyệt tới 29/11/2026. Khi hết hạn catalog, chạy lại builder vào thư mục mới và kiểm tra trước khi đổi cấu hình. Nếu nội dung thay đổi hoặc hết hạn duyệt, cần chủ dự án duyệt lại. Runtime không tự sửa nguồn, gia hạn hay hạ điều kiện kiểm tra.

## Giới hạn còn lại

Tìm sự kiện theo ngày/giá, tư vấn tồn kho thật, truy vấn tài khoản qua ủy quyền và model QLoRA chưa hoàn thành. Bot giữ phản hồi rõ phạm vi thay vì tự sinh giá, số vé, trạng thái đơn hay điều kiện hoàn tiền. Bộ câu hỏi local này là kiểm tra hồi quy, không chứng minh độ chính xác tổng quát của một mô hình AI.

## Kết quả kiểm chứng bản đang chạy

- 282 test AI đạt, coverage 93,40%; Ruff và Mypy đạt, kiểm tra hướng phụ thuộc/READ_ONLY và đồng bộ cấu hình đạt.
- 112 test frontend, kiểm tra kiểu và build đạt. Lệnh `npm run check` tổng dừng ở 7 file có lỗi định dạng từ trước ngoài phạm vi bản sửa; không ghi nhận lỗi lint mới của phần chat. Các file chat được sửa đã định dạng riêng.
- Bộ corpus đã duyệt: 17 câu hỏi được thử trực tiếp qua retrieval và HTTP chatbot, cùng các kiểm tra thu hồi/hết hạn/sai checksum/khóa gate/không có nguồn/câu hỏi riêng tư.
- Sau triển khai, đã thử 10 lượt qua BFF web thật: câu hỏi thanh toán có/không dấu, hỏi tiếp MoMo, kích thước ảnh, đặt vé, sự kiện nháp, hoàn tiền, trạng thái thanh toán cá nhân, tìm Hồ Chí Minh và đổi sang Hà Nội. Các lượt đều có đúng nhánh và nguồn kỳ vọng; sự kiện vẫn có nút mở chi tiết.
- `/health/ready`: `policy_retrieval.status=ready`, `backend=bm25`, `vector_store=null`, `semantic_enabled=false`; chỉ business tool `search_events` được bật. Docker xác nhận `/app/configs` là mount chỉ đọc.
- Dữ liệu kiểm chứng đợt trước ở `artifacts/local-chatbot-hardening/`, gồm cấu hình, báo cáo nguồn và `live-web-check.json`. Bản đang phục vụ sau sửa ngân sách dùng `artifacts/local-budget-fix/configs`, có bằng chứng mới ở `live-budget-check.json`. Các thư mục thử trước đó giữ làm bằng chứng phát triển.

## Bổ sung: vòng lặp hỏi ngân sách

Đã tái hiện chuỗi “Tìm kiếm vé sự kiện dưới 500k trong tháng 11” → “1 vé” → “mỗi vé” → “Là sao”. Bản cũ hỏi phạm vi ngân sách trước khi kiểm tra khả năng xử lý giá/thời gian, rồi chuyển sang phản hồi chưa có tồn kho. Điều đó làm người dùng đi qua bước làm rõ không có kết quả sử dụng được.

Bản sửa nói rõ giới hạn ngay khi nhận yêu cầu, không hỏi phạm vi ngân sách cho luồng chưa hỗ trợ. Có thành phố/từ khóa thì chỉ tìm theo các điều kiện đó, kèm thông báo ngân sách và tháng chưa được áp dụng; thiếu điều kiện tìm kiếm thì hỏi thành phố. Các câu “1 vé”, “mỗi vé”, câu không dấu và “Là sao” giữ ngữ cảnh, không lặp câu hỏi phạm vi ngân sách. Cụm “tìm kiếm vé sự kiện” không còn bị đưa nguyên văn thành từ khóa sự kiện.

Đã thêm 9 trường hợp hồi quy cho lỗi này; chạy 168 test hội thoại/HTTP/gateway/transport/domain/settings liên quan đều đạt. Đây là đợt kiểm tra tập trung, không chạy lại bộ benchmark semantic không thay đổi. Bộ cấu hình cập nhật nằm ở `artifacts/local-budget-fix/configs`; các nguồn corpus đã được duyệt giữ nguyên nội dung và được kiểm chứng lại trước khi đổi bản chạy.

Sau triển khai đã thử đủ bốn câu trong ảnh qua BFF web thật: ngân sách 500.000 đồng được giữ nguyên, “1 vé” được nhận diện và không xuất hiện câu hỏi lặp hay phản hồi chưa có tồn kho. Hỏi tiếp “Ở Hồ Chí Minh” gọi `search_events`, trả 2 liên kết sự kiện cùng thông báo chưa áp dụng ngân sách/tháng. Câu hỏi phương thức thanh toán vẫn trả nguồn corpus đã duyệt và VNPay. Readiness báo `ready`, BM25 hoạt động; giá/tháng và tồn kho vẫn chưa được triển khai.
