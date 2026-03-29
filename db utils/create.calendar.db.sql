BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "colors" (
	"EN"	TEXT NOT NULL,
	"ES"	TEXT NOT NULL,
	"DE"	TEXT NOT NULL,
	"FR"	TEXT NOT NULL,
	"hex"	TEXT NOT NULL,
	"red"	INTEGER NOT NULL,
	"green"	INTEGER NOT NULL,
	"blue"	INTEGER NOT NULL
);
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
	"marks"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "icon" (
	"filename"	TEXT,
	"name"	TEXT NOT NULL,
	"alternativenames"	TEXT,
	"svg"	TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS "import_history" (
	"id"	INTEGER NOT NULL UNIQUE,
	"userid"	TEXT,
	"filename"	TEXT,
	"date"	TEXT,
	"filehash"	TEXT,
	"command"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "import_sequence" (
	"next_id"	INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS "palettes" (
	"name"	TEXT,
	"palette"	TEXT
);
CREATE TABLE IF NOT EXISTS "papersizes" (
	"group"	TEXT,
	"name"	TEXT,
	"width_mm"	REAL,
	"height_mm"	REAL,
	"width_in"	REAL,
	"height_in"	REAL,
	"width_points"	REAL,
	"height_points"	REAL,
	"landscape"	INTEGER,
	"field10"	TEXT,
	"field11"	TEXT,
	"field12"	TEXT,
	"field13"	TEXT,
	"field14"	TEXT,
	"field15"	TEXT
);
CREATE TABLE IF NOT EXISTS "patterns" (
	"name"	TEXT NOT NULL,
	"svg"	TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS "specialdays" (
	"id"	TEXT,
	"company"	TEXT,
	"user"	TEXT,
	"country"	TEXT NOT NULL,
	"language"	TEXT NOT NULL,
	"startdate"	TEXT,
	"enddate"	TEXT,
	"name"	TEXT,
	"notes"	TEXT,
	"icon"	TEXT,
	"nonworkday"	INTEGER DEFAULT 0,
	"fullday"	INTEGER DEFAULT 1,
	"starthour"	TEXT,
	"endhour"	TEXT marks TEXT,
	"daycolor"	TEXT,
	"visible"	INTEGER DEFAULT 1,
	"pattern"	NUMERIC,
	"patterncolor"	TEXT
);
CREATE INDEX IF NOT EXISTS "date" ON "events" (
	"start_date"	ASC
);
CREATE INDEX IF NOT EXISTS "name" ON "patterns" (
	"name"	ASC
);
CREATE INDEX IF NOT EXISTS "names" ON "colors" (
	"EN"	ASC
);
COMMIT;
