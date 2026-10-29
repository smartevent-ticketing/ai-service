-- ONLY for the disposable database created by verify-public-search.ps1.
INSERT INTO events (id, organizer_id, name, slug, description, start_time, end_time, status, city)
SELECT md5('ai-public-search-fixture-' || n)::uuid,
 'b0000000-0000-0000-0000-000000000002',
 'AI integration public ' || lpad(n::text, 2, '0'), 'ai-integration-public-' || n,
 'Fixture description, not projected into model context',
 now() + n * interval '1 day', now() + n * interval '1 day' + interval '3 hours',
 'PUBLISHED', 'Hồ Chí Minh'
FROM generate_series(1, 25) n;
INSERT INTO events (id, organizer_id, name, slug, start_time, end_time, status, city)
SELECT md5('ai-hidden-fixture-' || state)::uuid,
 'b0000000-0000-0000-0000-000000000002',
 'AI_GATE_HIDDEN ' || state, 'ai-hidden-' || lower(state),
 now() + interval '1 day', now() + interval '2 days', state, 'Hồ Chí Minh'
FROM (VALUES ('DRAFT'), ('PENDING_APPROVAL'), ('CANCELLED')) s(state);
