-- A schema-version-1 database (v0.3.0 and v0.4.0), built with the v0.4.0 code and the
-- services (submit, worker, review) on synthetic receipts, then dumped. Five receipts:
-- R-A one revision in_review; R-B two revisions (10:00 and 10:05) in_review; R-C approved by
-- alice; R-D auto_approved; R-E auto_approved then rejected by bob. Used by the migration
-- tests of spec 006 (tests/unit/test_sqlite_store.py). Synthetic ids only.
BEGIN TRANSACTION;
CREATE TABLE batch_items (
    batch_id TEXT NOT NULL,
    row INTEGER NOT NULL,
    receipt_id TEXT,
    outcome TEXT NOT NULL,
    error TEXT,
    PRIMARY KEY (batch_id, row)
);
CREATE TABLE batches (
    batch_id TEXT PRIMARY KEY,
    total INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE classifications (
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (receipt_id, revision)
);
INSERT INTO "classifications" VALUES('R-A',1,'[{"line_id": "R-A-L1", "status": "classified", "category": "food_beverage", "restricted": false, "confidence": 0.99, "subtype": "none", "recipient_kind": "none", "recipient_name": null, "unclassified_reason": null, "source": {"classifier": "hand", "model_id": "hand-written", "provider_endpoint": "none", "prompt_version": "test", "cache_key": "hand", "request_id": null, "cost_usd": null, "prompt_tokens": null, "completion_tokens": null, "cache_hit": true, "served_by": null}}]');
INSERT INTO "classifications" VALUES('R-B',1,'[{"line_id": "R-B-L1", "status": "classified", "category": "food_beverage", "restricted": false, "confidence": 0.99, "subtype": "none", "recipient_kind": "none", "recipient_name": null, "unclassified_reason": null, "source": {"classifier": "hand", "model_id": "hand-written", "provider_endpoint": "none", "prompt_version": "test", "cache_key": "hand", "request_id": null, "cost_usd": null, "prompt_tokens": null, "completion_tokens": null, "cache_hit": true, "served_by": null}}]');
INSERT INTO "classifications" VALUES('R-C',1,'[{"line_id": "R-C-L1", "status": "classified", "category": "food_beverage", "restricted": false, "confidence": 0.99, "subtype": "none", "recipient_kind": "none", "recipient_name": null, "unclassified_reason": null, "source": {"classifier": "hand", "model_id": "hand-written", "provider_endpoint": "none", "prompt_version": "test", "cache_key": "hand", "request_id": null, "cost_usd": null, "prompt_tokens": null, "completion_tokens": null, "cache_hit": true, "served_by": null}}]');
INSERT INTO "classifications" VALUES('R-D',1,'[{"line_id": "R-D-L1", "status": "classified", "category": "office_supplies", "restricted": false, "confidence": 0.99, "subtype": "none", "recipient_kind": "none", "recipient_name": null, "unclassified_reason": null, "source": {"classifier": "hand", "model_id": "hand-written", "provider_endpoint": "none", "prompt_version": "test", "cache_key": "hand", "request_id": null, "cost_usd": null, "prompt_tokens": null, "completion_tokens": null, "cache_hit": true, "served_by": null}}]');
INSERT INTO "classifications" VALUES('R-E',1,'[{"line_id": "R-E-L1", "status": "classified", "category": "office_supplies", "restricted": false, "confidence": 0.99, "subtype": "none", "recipient_kind": "none", "recipient_name": null, "unclassified_reason": null, "source": {"classifier": "hand", "model_id": "hand-written", "provider_endpoint": "none", "prompt_version": "test", "cache_key": "hand", "request_id": null, "cost_usd": null, "prompt_tokens": null, "completion_tokens": null, "cache_hit": true, "served_by": null}}]');
INSERT INTO "classifications" VALUES('R-B',2,'[{"line_id": "R-B-L1", "status": "classified", "category": "food_beverage", "restricted": false, "confidence": 0.99, "subtype": "none", "recipient_kind": "none", "recipient_name": null, "unclassified_reason": null, "source": {"classifier": "hand", "model_id": "hand-written", "provider_endpoint": "none", "prompt_version": "test", "cache_key": "hand", "request_id": null, "cost_usd": null, "prompt_tokens": null, "completion_tokens": null, "cache_hit": true, "served_by": null}}]');
CREATE TABLE evaluations (
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    version INTEGER NOT NULL,
    result TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (receipt_id, revision, version)
);
INSERT INTO "evaluations" VALUES('R-A',1,1,'{"receipt_id":"R-A","disposition":"flag","line_items":[{"line_id":"R-A-L1","description_raw":"Lunch A","category":"food_beverage","restricted":false,"confidence":0.99,"subtype":"none","recipient_kind":"none","recipient_name":null,"status":"classified","unclassified_reason":null}],"exceptions":[{"rule_id":"MEAL-01","policy_doc":"meals-and-entertainment-policy.md","severity":"medium","line_ids":[],"evidence":"Meal spend is capped at $75 per person per day for domestic travel and $100 per person per day for international travel.","explanation":"MEAL-01: the receipt as a whole: this employee''s meal spend that day is $90.00 per person across 2 meal receipt(s), above the $75.00 daily cap.","decisions":["A8"],"computed":{"cap_usd":"75.00","day_per_person_usd":"90.00","receipts_that_day":"2"}}],"review_signals":[],"run":{"classifier":"billing-fake","model_id":"fake-model","provider_endpoint":"none","prompt_version":"test","rules_version":"3dd5e8498c09","exc03_threshold":0.97,"exc03_threshold_status":"chosen_on_dev","confidence_source":"self_reported","pipeline_config_version":null}}','e0d189dc5a6e3e69505ab1b1f28206753c53a06dabaea06648f44c52ef12b336','2026-10-12T10:00:31.500000+00:00');
INSERT INTO "evaluations" VALUES('R-B',1,1,'{"receipt_id":"R-B","disposition":"flag","line_items":[{"line_id":"R-B-L1","description_raw":"Lunch B","category":"food_beverage","restricted":false,"confidence":0.99,"subtype":"none","recipient_kind":"none","recipient_name":null,"status":"classified","unclassified_reason":null}],"exceptions":[{"rule_id":"MEAL-01","policy_doc":"meals-and-entertainment-policy.md","severity":"medium","line_ids":[],"evidence":"Meal spend is capped at $75 per person per day for domestic travel and $100 per person per day for international travel.","explanation":"MEAL-01: the receipt as a whole: this employee''s meal spend that day is $90.00 per person across 2 meal receipt(s), above the $75.00 daily cap.","decisions":["A8"],"computed":{"cap_usd":"75.00","day_per_person_usd":"90.00","receipts_that_day":"2"}}],"review_signals":[],"run":{"classifier":"billing-fake","model_id":"fake-model","provider_endpoint":"none","prompt_version":"test","rules_version":"3dd5e8498c09","exc03_threshold":0.97,"exc03_threshold_status":"chosen_on_dev","confidence_source":"self_reported","pipeline_config_version":null}}','b6415880aec912ae20607c69ef2cb98cc1bd70d64ff2bd29388d48800c62704a','2026-10-12T10:00:34.500000+00:00');
INSERT INTO "evaluations" VALUES('R-C',1,1,'{"receipt_id":"R-C","disposition":"flag","line_items":[{"line_id":"R-C-L1","description_raw":"Lunch A","category":"food_beverage","restricted":false,"confidence":0.99,"subtype":"none","recipient_kind":"none","recipient_name":null,"status":"classified","unclassified_reason":null}],"exceptions":[{"rule_id":"MEAL-01","policy_doc":"meals-and-entertainment-policy.md","severity":"medium","line_ids":[],"evidence":"Meal spend is capped at $75 per person per day for domestic travel and $100 per person per day for international travel.","explanation":"MEAL-01: the receipt as a whole: this employee''s meal spend that day is $90.00 per person across 1 meal receipt(s), above the $75.00 daily cap.","decisions":["A8"],"computed":{"cap_usd":"75.00","day_per_person_usd":"90.00","receipts_that_day":"1"}}],"review_signals":[],"run":{"classifier":"billing-fake","model_id":"fake-model","provider_endpoint":"none","prompt_version":"test","rules_version":"3dd5e8498c09","exc03_threshold":0.97,"exc03_threshold_status":"chosen_on_dev","confidence_source":"self_reported","pipeline_config_version":null}}','6a52e43aec5b39ff32c7ec72ea1af9d8db687e922ff43507119f339b161f4b93','2026-10-12T10:00:37.500000+00:00');
INSERT INTO "evaluations" VALUES('R-D',1,1,'{"receipt_id":"R-D","disposition":"pass","line_items":[{"line_id":"R-D-L1","description_raw":"Spiral notebook","category":"office_supplies","restricted":false,"confidence":0.99,"subtype":"none","recipient_kind":"none","recipient_name":null,"status":"classified","unclassified_reason":null}],"exceptions":[],"review_signals":[],"run":{"classifier":"billing-fake","model_id":"fake-model","provider_endpoint":"none","prompt_version":"test","rules_version":"3dd5e8498c09","exc03_threshold":0.97,"exc03_threshold_status":"chosen_on_dev","confidence_source":"self_reported","pipeline_config_version":null}}','dd50ca0ce4d73e4c3ab4e6d6ee1ace32c70e201fd0246d432617d662bf62fd16','2026-10-12T10:00:40.500000+00:00');
INSERT INTO "evaluations" VALUES('R-E',1,1,'{"receipt_id":"R-E","disposition":"pass","line_items":[{"line_id":"R-E-L1","description_raw":"Spiral notebook","category":"office_supplies","restricted":false,"confidence":0.99,"subtype":"none","recipient_kind":"none","recipient_name":null,"status":"classified","unclassified_reason":null}],"exceptions":[],"review_signals":[],"run":{"classifier":"billing-fake","model_id":"fake-model","provider_endpoint":"none","prompt_version":"test","rules_version":"3dd5e8498c09","exc03_threshold":0.97,"exc03_threshold_status":"chosen_on_dev","confidence_source":"self_reported","pipeline_config_version":null}}','35992af4228b2fa3e5724af5838332e5ac738331b298828f25f37550dbb59896','2026-10-12T10:00:43.500000+00:00');
INSERT INTO "evaluations" VALUES('R-B',2,1,'{"receipt_id":"R-B","disposition":"flag","line_items":[{"line_id":"R-B-L1","description_raw":"Lunch B","category":"food_beverage","restricted":false,"confidence":0.99,"subtype":"none","recipient_kind":"none","recipient_name":null,"status":"classified","unclassified_reason":null}],"exceptions":[{"rule_id":"MEAL-01","policy_doc":"meals-and-entertainment-policy.md","severity":"medium","line_ids":[],"evidence":"Meal spend is capped at $75 per person per day for domestic travel and $100 per person per day for international travel.","explanation":"MEAL-01: the receipt as a whole: this employee''s meal spend that day is $95.00 per person across 2 meal receipt(s), above the $75.00 daily cap.","decisions":["A8"],"computed":{"cap_usd":"75.00","day_per_person_usd":"95.00","receipts_that_day":"2"}}],"review_signals":[],"run":{"classifier":"billing-fake","model_id":"fake-model","provider_endpoint":"none","prompt_version":"test","rules_version":"3dd5e8498c09","exc03_threshold":0.97,"exc03_threshold_status":"chosen_on_dev","confidence_source":"self_reported","pipeline_config_version":null}}','ada2a86ecd367a18c5eb8fde13213fc8db54bbb2e03bf05605f5e257a2a9623b','2026-10-12T10:05:07.500000+00:00');
INSERT INTO "evaluations" VALUES('R-A',1,2,'{"receipt_id":"R-A","disposition":"flag","line_items":[{"line_id":"R-A-L1","description_raw":"Lunch A","category":"food_beverage","restricted":false,"confidence":0.99,"subtype":"none","recipient_kind":"none","recipient_name":null,"status":"classified","unclassified_reason":null}],"exceptions":[{"rule_id":"MEAL-01","policy_doc":"meals-and-entertainment-policy.md","severity":"medium","line_ids":[],"evidence":"Meal spend is capped at $75 per person per day for domestic travel and $100 per person per day for international travel.","explanation":"MEAL-01: the receipt as a whole: this employee''s meal spend that day is $95.00 per person across 2 meal receipt(s), above the $75.00 daily cap.","decisions":["A8"],"computed":{"cap_usd":"75.00","day_per_person_usd":"95.00","receipts_that_day":"2"}}],"review_signals":[],"run":{"classifier":"billing-fake","model_id":"fake-model","provider_endpoint":"none","prompt_version":"test","rules_version":"3dd5e8498c09","exc03_threshold":0.97,"exc03_threshold_status":"chosen_on_dev","confidence_source":"self_reported","pipeline_config_version":null}}','0ff3fbc06e0dd44d7fdf550a8d92852647d7eb97f3ac08fa38d3fcdbaecd1afa','2026-10-12T10:05:10.500000+00:00');
CREATE TABLE events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    actor TEXT NOT NULL,
    at TEXT NOT NULL
);
INSERT INTO "events" VALUES(1,'R-A',1,'ReceiptSubmitted','{"content_hash":"ed058a8157dcaf84ef144cefd0f2d6e55cf4c9bc3d5493f33b06e6dd592c1dc6","idempotency_key":"R-A:ed058a8157dcaf84ef144cefd0f2d6e55cf4c9bc3d5493f33b06e6dd592c1dc6","batch_id":null}','system','2026-10-12T10:00:00.000000+00:00');
INSERT INTO "events" VALUES(2,'R-B',1,'ReceiptSubmitted','{"content_hash":"3f78ee2816accd56b6306648b26af1c9c5e37952d0a45e816c3eb8c245fddc35","idempotency_key":"R-B:3f78ee2816accd56b6306648b26af1c9c5e37952d0a45e816c3eb8c245fddc35","batch_id":null}','system','2026-10-12T10:00:01.500000+00:00');
INSERT INTO "events" VALUES(3,'R-C',1,'ReceiptSubmitted','{"content_hash":"4f147f408b4ff021b5c04425492a1437d7a35a5e15bdce79b55b4f49c5f333f8","idempotency_key":"R-C:4f147f408b4ff021b5c04425492a1437d7a35a5e15bdce79b55b4f49c5f333f8","batch_id":null}','system','2026-10-12T10:00:03.000000+00:00');
INSERT INTO "events" VALUES(4,'R-D',1,'ReceiptSubmitted','{"content_hash":"bc7122d87d3d17fa679876578d5e52bbf622392561443b272d7f8fa05c836e9d","idempotency_key":"R-D:bc7122d87d3d17fa679876578d5e52bbf622392561443b272d7f8fa05c836e9d","batch_id":null}','system','2026-10-12T10:00:04.500000+00:00');
INSERT INTO "events" VALUES(5,'R-E',1,'ReceiptSubmitted','{"content_hash":"148e5f2a1763d61e2c1b907b43aa746adee885cf572ac8ff081594170b4a46b9","idempotency_key":"R-E:148e5f2a1763d61e2c1b907b43aa746adee885cf572ac8ff081594170b4a46b9","batch_id":null}','system','2026-10-12T10:00:06.000000+00:00');
INSERT INTO "events" VALUES(6,'R-A',1,'ReceiptClassified','{"lines":1,"cache_hits":0,"calls_made":1}','worker','2026-10-12T10:00:10.500000+00:00');
INSERT INTO "events" VALUES(7,'R-B',1,'ReceiptClassified','{"lines":1,"cache_hits":0,"calls_made":1}','worker','2026-10-12T10:00:15.000000+00:00');
INSERT INTO "events" VALUES(8,'R-C',1,'ReceiptClassified','{"lines":1,"cache_hits":1,"calls_made":0}','worker','2026-10-12T10:00:19.500000+00:00');
INSERT INTO "events" VALUES(9,'R-D',1,'ReceiptClassified','{"lines":1,"cache_hits":0,"calls_made":1}','worker','2026-10-12T10:00:24.000000+00:00');
INSERT INTO "events" VALUES(10,'R-E',1,'ReceiptClassified','{"lines":1,"cache_hits":1,"calls_made":0}','worker','2026-10-12T10:00:28.500000+00:00');
INSERT INTO "events" VALUES(11,'R-A',1,'ReceiptEvaluated','{"version":1,"disposition":"flag","changed":true,"result_hash":"e0d189dc5a6e3e69505ab1b1f28206753c53a06dabaea06648f44c52ef12b336"}','worker','2026-10-12T10:00:31.500000+00:00');
INSERT INTO "events" VALUES(12,'R-B',1,'ReceiptEvaluated','{"version":1,"disposition":"flag","changed":true,"result_hash":"b6415880aec912ae20607c69ef2cb98cc1bd70d64ff2bd29388d48800c62704a"}','worker','2026-10-12T10:00:34.500000+00:00');
INSERT INTO "events" VALUES(13,'R-C',1,'ReceiptEvaluated','{"version":1,"disposition":"flag","changed":true,"result_hash":"6a52e43aec5b39ff32c7ec72ea1af9d8db687e922ff43507119f339b161f4b93"}','worker','2026-10-12T10:00:37.500000+00:00');
INSERT INTO "events" VALUES(14,'R-D',1,'ReceiptEvaluated','{"version":1,"disposition":"pass","changed":true,"result_hash":"dd50ca0ce4d73e4c3ab4e6d6ee1ace32c70e201fd0246d432617d662bf62fd16"}','worker','2026-10-12T10:00:40.500000+00:00');
INSERT INTO "events" VALUES(15,'R-E',1,'ReceiptEvaluated','{"version":1,"disposition":"pass","changed":true,"result_hash":"35992af4228b2fa3e5724af5838332e5ac738331b298828f25f37550dbb59896"}','worker','2026-10-12T10:00:43.500000+00:00');
INSERT INTO "events" VALUES(16,'R-B',2,'RevisionSuperseded','{"superseded_revision":1,"by_revision":2}','system','2026-10-12T10:05:00.000000+00:00');
INSERT INTO "events" VALUES(17,'R-B',2,'ReceiptSubmitted','{"content_hash":"ff5cea6cd9a99d41f2e37cdd30a3071053487d6396e350d4dde61dc369c4a4b9","idempotency_key":"R-B:ff5cea6cd9a99d41f2e37cdd30a3071053487d6396e350d4dde61dc369c4a4b9","batch_id":null}','system','2026-10-12T10:05:00.000000+00:00');
INSERT INTO "events" VALUES(18,'R-B',2,'ReceiptClassified','{"lines":1,"cache_hits":1,"calls_made":0}','worker','2026-10-12T10:05:04.500000+00:00');
INSERT INTO "events" VALUES(19,'R-B',2,'ReceiptEvaluated','{"version":1,"disposition":"flag","changed":true,"result_hash":"ada2a86ecd367a18c5eb8fde13213fc8db54bbb2e03bf05605f5e257a2a9623b"}','worker','2026-10-12T10:05:07.500000+00:00');
INSERT INTO "events" VALUES(20,'R-A',1,'ReceiptEvaluated','{"version":2,"disposition":"flag","changed":true,"result_hash":"0ff3fbc06e0dd44d7fdf550a8d92852647d7eb97f3ac08fa38d3fcdbaecd1afa"}','worker','2026-10-12T10:05:10.500000+00:00');
INSERT INTO "events" VALUES(21,'R-C',1,'ReceiptApproved','{"based_on_version":1,"reason_code":"policy_exception_granted","note":"ok","agreement":0}','alice','2026-10-12T10:20:30.123456+00:00');
INSERT INTO "events" VALUES(22,'R-E',1,'ReceiptRejected','{"based_on_version":1,"reason_code":"engine_missed_issue","note":null,"agreement":0}','bob','2026-10-12T10:40:00.000000+00:00');
CREATE TABLE outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN ('classify', 'evaluate')),
    state TEXT NOT NULL CHECK (state IN ('pending', 'claimed', 'done', 'cancelled', 'failed')),
    lease_until TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL
);
INSERT INTO "outbox" VALUES(1,'R-A',1,'classify','done',NULL,1,NULL,'2026-10-12T10:00:00.000000+00:00');
INSERT INTO "outbox" VALUES(2,'R-B',1,'classify','done',NULL,1,NULL,'2026-10-12T10:00:01.500000+00:00');
INSERT INTO "outbox" VALUES(3,'R-C',1,'classify','done',NULL,1,NULL,'2026-10-12T10:00:03.000000+00:00');
INSERT INTO "outbox" VALUES(4,'R-D',1,'classify','done',NULL,1,NULL,'2026-10-12T10:00:04.500000+00:00');
INSERT INTO "outbox" VALUES(5,'R-E',1,'classify','done',NULL,1,NULL,'2026-10-12T10:00:06.000000+00:00');
INSERT INTO "outbox" VALUES(6,'R-A',1,'evaluate','done',NULL,1,NULL,'2026-10-12T10:00:10.500000+00:00');
INSERT INTO "outbox" VALUES(7,'R-B',1,'evaluate','done',NULL,1,NULL,'2026-10-12T10:00:15.000000+00:00');
INSERT INTO "outbox" VALUES(9,'R-C',1,'evaluate','done',NULL,1,NULL,'2026-10-12T10:00:19.500000+00:00');
INSERT INTO "outbox" VALUES(10,'R-D',1,'evaluate','done',NULL,1,NULL,'2026-10-12T10:00:24.000000+00:00');
INSERT INTO "outbox" VALUES(11,'R-E',1,'evaluate','done',NULL,1,NULL,'2026-10-12T10:00:28.500000+00:00');
INSERT INTO "outbox" VALUES(12,'R-B',2,'classify','done',NULL,1,NULL,'2026-10-12T10:05:00.000000+00:00');
INSERT INTO "outbox" VALUES(13,'R-B',2,'evaluate','done',NULL,1,NULL,'2026-10-12T10:05:04.500000+00:00');
INSERT INTO "outbox" VALUES(14,'R-A',1,'evaluate','done',NULL,1,NULL,'2026-10-12T10:05:04.500000+00:00');
CREATE TABLE receipt_keys (
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    key TEXT NOT NULL,
    PRIMARY KEY (receipt_id, revision, key)
);
INSERT INTO "receipt_keys" VALUES('R-A',1,'day:E-1|2026-05-01');
INSERT INTO "receipt_keys" VALUES('R-B',1,'day:E-1|2026-05-01');
INSERT INTO "receipt_keys" VALUES('R-C',1,'day:E-C|2026-05-01');
INSERT INTO "receipt_keys" VALUES('R-D',1,'day:E-D|2026-05-01');
INSERT INTO "receipt_keys" VALUES('R-E',1,'day:E-E|2026-05-01');
INSERT INTO "receipt_keys" VALUES('R-B',2,'day:E-1|2026-05-01');
CREATE TABLE receipts (
    receipt_id TEXT PRIMARY KEY,
    current_revision INTEGER NOT NULL,
    state TEXT NOT NULL,
    disposition TEXT,
    evaluation_version INTEGER,
    human_acted INTEGER NOT NULL DEFAULT 0,
    notice TEXT,
    qa_sample INTEGER NOT NULL DEFAULT 0,
    failed_stage TEXT,
    failed_reason TEXT,
    updated_at TEXT NOT NULL
);
INSERT INTO "receipts" VALUES('R-A',1,'in_review','flag',2,0,NULL,0,NULL,NULL,'2026-10-12T10:05:10.500000+00:00');
INSERT INTO "receipts" VALUES('R-B',2,'in_review','flag',1,0,NULL,0,NULL,NULL,'2026-10-12T10:05:07.500000+00:00');
INSERT INTO "receipts" VALUES('R-C',1,'approved','flag',1,1,NULL,0,NULL,NULL,'2026-10-12T10:20:30.123456+00:00');
INSERT INTO "receipts" VALUES('R-D',1,'auto_approved','pass',1,0,NULL,0,NULL,NULL,'2026-10-12T10:00:40.500000+00:00');
INSERT INTO "receipts" VALUES('R-E',1,'rejected','pass',1,1,NULL,0,NULL,NULL,'2026-10-12T10:40:00+00:00');
CREATE TABLE revisions (
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('current', 'superseded')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (receipt_id, revision)
);
INSERT INTO "revisions" VALUES('R-A',1,'ed058a8157dcaf84ef144cefd0f2d6e55cf4c9bc3d5493f33b06e6dd592c1dc6','{"receipt_id":"R-A","employee_id":"E-1","employee_country":"US","entity":"GLOBAL","submitted_expense_type":"Meals - Individual","merchant_name":"Synthetic Merchant","mcc":5943,"mcc_description":"Office and stationery supply","transaction_datetime":"2026-05-01T12:00:00","currency":"USD","fx_rate_to_usd":"1.0","total_amount":"40","total_amount_usd":"40","attendee_count":null,"trip_id":null,"trip_nights":null,"pre_approval_ref":null,"itemized":true,"vat_number":null,"line_items":[{"line_id":"R-A-L1","description_raw":"Lunch A","language":"en","quantity":"1","unit_price":"40","amount":"40","amount_usd":"40"}]}','current','2026-10-12T10:00:00.000000+00:00');
INSERT INTO "revisions" VALUES('R-B',1,'3f78ee2816accd56b6306648b26af1c9c5e37952d0a45e816c3eb8c245fddc35','{"receipt_id":"R-B","employee_id":"E-1","employee_country":"US","entity":"GLOBAL","submitted_expense_type":"Meals - Individual","merchant_name":"Synthetic Merchant","mcc":5943,"mcc_description":"Office and stationery supply","transaction_datetime":"2026-05-01T12:00:00","currency":"USD","fx_rate_to_usd":"1.0","total_amount":"50","total_amount_usd":"50","attendee_count":null,"trip_id":null,"trip_nights":null,"pre_approval_ref":null,"itemized":true,"vat_number":null,"line_items":[{"line_id":"R-B-L1","description_raw":"Lunch B","language":"en","quantity":"1","unit_price":"50","amount":"50","amount_usd":"50"}]}','superseded','2026-10-12T10:00:01.500000+00:00');
INSERT INTO "revisions" VALUES('R-C',1,'4f147f408b4ff021b5c04425492a1437d7a35a5e15bdce79b55b4f49c5f333f8','{"receipt_id":"R-C","employee_id":"E-C","employee_country":"US","entity":"GLOBAL","submitted_expense_type":"Meals - Individual","merchant_name":"Synthetic Merchant","mcc":5943,"mcc_description":"Office and stationery supply","transaction_datetime":"2026-05-01T12:00:00","currency":"USD","fx_rate_to_usd":"1.0","total_amount":"90","total_amount_usd":"90","attendee_count":null,"trip_id":null,"trip_nights":null,"pre_approval_ref":null,"itemized":true,"vat_number":null,"line_items":[{"line_id":"R-C-L1","description_raw":"Lunch A","language":"en","quantity":"1","unit_price":"90","amount":"90","amount_usd":"90"}]}','current','2026-10-12T10:00:03.000000+00:00');
INSERT INTO "revisions" VALUES('R-D',1,'bc7122d87d3d17fa679876578d5e52bbf622392561443b272d7f8fa05c836e9d','{"receipt_id":"R-D","employee_id":"E-D","employee_country":"US","entity":"GLOBAL","submitted_expense_type":"Office Supplies","merchant_name":"Synthetic Merchant","mcc":5943,"mcc_description":"Office and stationery supply","transaction_datetime":"2026-05-01T12:00:00","currency":"USD","fx_rate_to_usd":"1.0","total_amount":"12.50","total_amount_usd":"12.50","attendee_count":null,"trip_id":null,"trip_nights":null,"pre_approval_ref":null,"itemized":true,"vat_number":null,"line_items":[{"line_id":"R-D-L1","description_raw":"Spiral notebook","language":"en","quantity":"1","unit_price":"12.50","amount":"12.50","amount_usd":"12.50"}]}','current','2026-10-12T10:00:04.500000+00:00');
INSERT INTO "revisions" VALUES('R-E',1,'148e5f2a1763d61e2c1b907b43aa746adee885cf572ac8ff081594170b4a46b9','{"receipt_id":"R-E","employee_id":"E-E","employee_country":"US","entity":"GLOBAL","submitted_expense_type":"Office Supplies","merchant_name":"Synthetic Merchant","mcc":5943,"mcc_description":"Office and stationery supply","transaction_datetime":"2026-05-01T12:00:00","currency":"USD","fx_rate_to_usd":"1.0","total_amount":"12.50","total_amount_usd":"12.50","attendee_count":null,"trip_id":null,"trip_nights":null,"pre_approval_ref":null,"itemized":true,"vat_number":null,"line_items":[{"line_id":"R-E-L1","description_raw":"Spiral notebook","language":"en","quantity":"1","unit_price":"12.50","amount":"12.50","amount_usd":"12.50"}]}','current','2026-10-12T10:00:06.000000+00:00');
INSERT INTO "revisions" VALUES('R-B',2,'ff5cea6cd9a99d41f2e37cdd30a3071053487d6396e350d4dde61dc369c4a4b9','{"receipt_id":"R-B","employee_id":"E-1","employee_country":"US","entity":"GLOBAL","submitted_expense_type":"Meals - Individual","merchant_name":"Synthetic Merchant","mcc":5943,"mcc_description":"Office and stationery supply","transaction_datetime":"2026-05-01T12:00:00","currency":"USD","fx_rate_to_usd":"1.0","total_amount":"55","total_amount_usd":"55","attendee_count":null,"trip_id":null,"trip_nights":null,"pre_approval_ref":null,"itemized":true,"vat_number":null,"line_items":[{"line_id":"R-B-L1","description_raw":"Lunch B","language":"en","quantity":"1","unit_price":"55","amount":"55","amount_usd":"55"}]}','current','2026-10-12T10:05:00.000000+00:00');
CREATE TABLE submissions (
    idempotency_key TEXT PRIMARY KEY,
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    batch_id TEXT,
    created_at TEXT NOT NULL
);
INSERT INTO "submissions" VALUES('R-A:ed058a8157dcaf84ef144cefd0f2d6e55cf4c9bc3d5493f33b06e6dd592c1dc6','R-A',1,'ed058a8157dcaf84ef144cefd0f2d6e55cf4c9bc3d5493f33b06e6dd592c1dc6',NULL,'2026-10-12T10:00:00.000000+00:00');
INSERT INTO "submissions" VALUES('R-B:3f78ee2816accd56b6306648b26af1c9c5e37952d0a45e816c3eb8c245fddc35','R-B',1,'3f78ee2816accd56b6306648b26af1c9c5e37952d0a45e816c3eb8c245fddc35',NULL,'2026-10-12T10:00:01.500000+00:00');
INSERT INTO "submissions" VALUES('R-C:4f147f408b4ff021b5c04425492a1437d7a35a5e15bdce79b55b4f49c5f333f8','R-C',1,'4f147f408b4ff021b5c04425492a1437d7a35a5e15bdce79b55b4f49c5f333f8',NULL,'2026-10-12T10:00:03.000000+00:00');
INSERT INTO "submissions" VALUES('R-D:bc7122d87d3d17fa679876578d5e52bbf622392561443b272d7f8fa05c836e9d','R-D',1,'bc7122d87d3d17fa679876578d5e52bbf622392561443b272d7f8fa05c836e9d',NULL,'2026-10-12T10:00:04.500000+00:00');
INSERT INTO "submissions" VALUES('R-E:148e5f2a1763d61e2c1b907b43aa746adee885cf572ac8ff081594170b4a46b9','R-E',1,'148e5f2a1763d61e2c1b907b43aa746adee885cf572ac8ff081594170b4a46b9',NULL,'2026-10-12T10:00:06.000000+00:00');
INSERT INTO "submissions" VALUES('R-B:ff5cea6cd9a99d41f2e37cdd30a3071053487d6396e350d4dde61dc369c4a4b9','R-B',2,'ff5cea6cd9a99d41f2e37cdd30a3071053487d6396e350d4dde61dc369c4a4b9',NULL,'2026-10-12T10:05:00.000000+00:00');
CREATE INDEX receipt_keys_key ON receipt_keys (key);
CREATE INDEX receipts_state ON receipts (state);
CREATE INDEX events_receipt ON events (receipt_id, seq);
CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE UNIQUE INDEX outbox_open ON outbox (receipt_id, revision, stage)
    WHERE state = 'pending';
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('events',22);
INSERT INTO "sqlite_sequence" VALUES('outbox',14);
COMMIT;
PRAGMA user_version = 1;
