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

-- Date/price acceptance cases. Only insert into the isolated test database.
CREATE TEMP TABLE ai_filter_cases AS
SELECT label, n, price,
       md5('ai-filter-event-' || label)::uuid AS event_id,
       md5('ai-filter-area-' || label)::uuid AS area_id,
       md5('ai-filter-type-' || label)::uuid AS type_id,
       md5('ai-filter-phase-' || label)::uuid AS phase_id
FROM (VALUES
    ('lt', 1, 100000), ('eq', 2, 200000), ('high', 3, 300000),
    ('inactive', 4, 1000), ('type-inactive', 5, 1000), ('sold', 6, 1000),
    ('future', 7, 1000), ('expired', 8, 1000), ('hidden', 9, 1000),
    ('bad-area', 10, 1000), ('bad-counter', 11, 1000)
) AS cases(label, n, price);

INSERT INTO events (id, organizer_id, name, slug, start_time, end_time, status, city)
SELECT event_id, 'b0000000-0000-0000-0000-000000000002',
       'AI_FILTER_ ' || label, 'ai-filter-' || label,
       now() + interval '3 days' + n * interval '1 hour',
       now() + interval '3 days' + (n + 1) * interval '1 hour',
       CASE WHEN label = 'hidden' THEN 'DRAFT' ELSE 'PUBLISHED' END, 'Hồ Chí Minh'
FROM ai_filter_cases;
INSERT INTO event_areas (id, event_id, name, capacity)
SELECT area_id, event_id, 'Fixture standing area', 10 FROM ai_filter_cases;
INSERT INTO ticket_types (id, event_id, event_area_id, name, status)
SELECT type_id, event_id,
       CASE WHEN label = 'bad-area' THEN md5('ai-filter-area-hidden')::uuid ELSE area_id END,
       'Fixture ticket',
       CASE WHEN label = 'type-inactive' THEN 'INACTIVE' ELSE 'ACTIVE' END
FROM ai_filter_cases;
INSERT INTO ticket_sale_phases
    (id, ticket_type_id, name, price, quantity, sale_start_at, sale_end_at, status)
SELECT phase_id, type_id, 'Fixture sale phase', price, 10,
       CASE WHEN label = 'future' THEN now() + interval '1 day'
            ELSE now() - interval '2 days' END,
       CASE WHEN label = 'expired' THEN now() - interval '1 day'
            ELSE now() + interval '2 days' END,
       CASE WHEN label = 'inactive' THEN 'DRAFT' ELSE 'ACTIVE' END
FROM ai_filter_cases;
INSERT INTO inventory_counters
    (id, event_id, event_area_id, ticket_type_id, sale_phase_id, total_quantity, sold_quantity)
SELECT md5('ai-filter-stock-' || label)::uuid,
       CASE WHEN label = 'bad-counter' THEN md5('ai-filter-event-hidden')::uuid ELSE event_id END,
       area_id, type_id, phase_id, 10,
       CASE WHEN label = 'sold' THEN 10 ELSE 0 END
FROM ai_filter_cases;
