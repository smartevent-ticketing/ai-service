# 16 — Evaluation Reproducibility & Dataset Contract v1.2

**Bắt buộc** sau mỗi run để benchmark có thể tái lập.

```yaml
run_id: null
run_at_utc: null
repository_revision:
  ai_service: null
  smartevent_backend: 200720e32a4d5b3a7c80c599896c74517de95b37
  smartevent_web: 0e5ac549af4427b4a60be47ab6e708b2003ad75e
  smartevent_infra: b82a3d4c1b0b6ba1757a55b260fe843d502ddc1d
dataset:
  schema_version: '1.2'
  train_sha256: null
  validation_sha256: null
  test_sha256: null
  split_strategy: dialogue_group_and_scenario_family
model:
  model_id: null
  revision_sha: null
  adapter_revision_sha: null
  tokenizer_revision_sha: null
  thinking_mode: null
training:
  seed: null
  packages_lock_sha256: null
  python_version: null
  gpu_type: null
  vram_gb: null
  epochs: null
  lora_rank: null
  lora_alpha: null
  lr: null
inference:
  decoding_config: null
  serving_version: null
  context_length: null
  concurrency: null
rag:
  corpus_manifest_sha256: null
  embedding_model_revision: null
  index_revision: null
jev:
  enabled: false
  vendor_model_version: null
  evaluation_set_version: null
metrics:
  macro_f1: null
  slot_f1: null
  state_delta_exact: null
  action_accuracy: null
  json_validity: null
  rag_citation_correctness: null
  p95_latency_ms: null
  cost_per_task: null
```

Các SHA bên trên được ghi tại thời điểm rà soát repository 17–18/10/2026, **không phải cam kết HEAD mới nhất trong tương lai**; luôn kiểm tra branch/commit trong PR trước mỗi implement. Không có thông tin `null` nào được tự lấp bằng suy đoán. Snapshot thiếu dataset/model/adapter SHA thì không tuyên bố benchmark tái lập.

## Dataset data contract

Chỉ dùng JSONL theo `schemas/training_sample.schema.json`; `dataset_contract=1.2`, flat slots (`budget_amount`, `budget_currency`, `budget_scope`) và state delta typed operations. Split cả `dialogue_group` lẫn `scenario_family`, kiểm tra near-duplicate, giữ golden held-out, cấm chứa data thật chưa được phép. Lưu hash và label guideline review log. Test invalid labels phải fail.

## Baselines và kiểm thử

A. Qwen2.5-1.5B/Qwen3-1.7B chưa fine-tune, prompt cố định.
B. Cùng model với schema optimized.
C. QLoRA adapter.
D. C + TODS + tool read-only executor.
E. D + RAG approved corpus.
F. E + JEV evaluator (feature flag).

Đo trên cùng tập kịch bản, cùng môi trường/traffic mix, báo cáo cả chất lượng, p50/p95, token/s và cost/task. Nếu V1 không có nguồn tài liệu approved hoặc gate tool mở, không được bịa kết quả E/F — ghi `blocked` và lý do.
