-- Disposable fixture only; never execute against the application database.
INSERT INTO event_areas (id, event_id, name, area_type, capacity)
SELECT md5('price-area-' || id)::uuid, id, 'Price fixture area', 'STANDING', 100
FROM events WHERE slug LIKE 'ai-integration-public-%' OR slug LIKE 'ai-hidden-%';

INSERT INTO ticket_types (id, event_id, event_area_id, name, status)
SELECT md5('price-type-' || id)::uuid, id, md5('price-area-' || id)::uuid, 'Price fixture ticket',
 CASE WHEN slug = 'ai-integration-public-9' THEN 'INACTIVE' ELSE 'ACTIVE' END
FROM events WHERE slug LIKE 'ai-integration-public-%' OR slug LIKE 'ai-hidden-%';

INSERT INTO ticket_sale_phases
 (id, ticket_type_id, name, price, quantity, sale_start_at, sale_end_at, status, sold_out_at)
SELECT md5('price-phase-' || id)::uuid, md5('price-type-' || id)::uuid, 'Fixture current phase',
 CASE slug WHEN 'ai-integration-public-1' THEN 499999
           WHEN 'ai-integration-public-2' THEN 500000
           WHEN 'ai-integration-public-3' THEN 500001 ELSE 100000 END,
 100,
 CASE WHEN slug = 'ai-integration-public-5' THEN now() + interval '1 day' ELSE now() - interval '2 days' END,
 CASE WHEN slug = 'ai-integration-public-6' THEN now() - interval '1 day' ELSE now() + interval '60 days' END,
 CASE WHEN slug = 'ai-integration-public-4' THEN 'PAUSED' ELSE 'ACTIVE' END,
 CASE WHEN slug = 'ai-integration-public-7' THEN now() ELSE NULL END
FROM events WHERE slug LIKE 'ai-integration-public-%' OR slug LIKE 'ai-hidden-%';

INSERT INTO inventory_counters
 (id, event_id, event_area_id, ticket_type_id, sale_phase_id, total_quantity, sold_quantity)
SELECT md5('price-stock-' || id)::uuid, id, md5('price-area-' || id)::uuid,
 md5('price-type-' || id)::uuid, md5('price-phase-' || id)::uuid, 100,
 CASE WHEN slug = 'ai-integration-public-8' THEN 100 ELSE 0 END
FROM events WHERE slug LIKE 'ai-integration-public-%' OR slug LIKE 'ai-hidden-%';

-- A cheaper draft phase must not affect price evidence for public event 1.
INSERT INTO ticket_sale_phases
 (id, ticket_type_id, name, price, quantity, sale_start_at, sale_end_at, status)
SELECT md5('price-draft-phase-' || id)::uuid, md5('price-type-' || id)::uuid,
 'Fixture cheaper draft', 1, 100, now() - interval '1 day', now() + interval '60 days', 'DRAFT'
FROM events WHERE slug = 'ai-integration-public-1';
INSERT INTO inventory_counters
 (id, event_id, event_area_id, ticket_type_id, sale_phase_id, total_quantity)
SELECT md5('price-draft-stock-' || id)::uuid, id, md5('price-area-' || id)::uuid,
 md5('price-type-' || id)::uuid, md5('price-draft-phase-' || id)::uuid, 100
FROM events WHERE slug = 'ai-integration-public-1';
