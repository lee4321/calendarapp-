BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "events" (
	"id"	INTEGER NOT NULL,
	"user_id"	INTEGER NOT NULL,
	"import_id"	INTEGER NOT NULL,
	"status"	TEXT,
	"priority"	NUMERIC,
	"wbs"	TEXT,
	"rollup"	INTEGER,
	"milestone"	INTEGER,
	"percent_complete"	REAL,
	"name"	TEXT,
	"effort"	REAL,
	"duration"	REAL,
	"start_date"	TEXT,
	"end_date"	TEXT,
	"earliest_start_date"	TEXT,
	"latest_start_date"	TEXT,
	"earliest_end_date"	TEXT,
	"latest_end_date"	TEXT,
	"predecessors"	TEXT,
	"resource_names"	TEXT,
	"resource_group"	TEXT,
	"notes"	TEXT,
	"icon"	TEXT,
	"color"	TEXT,
	"tags"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE INDEX IF NOT EXISTS "date" ON "events" (
	"start_date"	ASC
);
COMMIT;
