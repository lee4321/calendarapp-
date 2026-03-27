-- Generate 30 palettes of 15 random colors from the colors table.
-- Usage: sqlite3 calendar.db < generate_random_palettes.sql

-- Remove any previous Random_XX palettes so the script is idempotent.
DELETE FROM palettes WHERE name GLOB 'Random_[0-9][0-9]';

-- Assign each color a random rank within each of 30 palette slots,
-- then keep only the top 15 per slot and aggregate into CSV strings.
WITH RECURSIVE seq(n) AS (
    VALUES (1)
    UNION ALL
    SELECT n + 1 FROM seq WHERE n < 30
),
ranked AS (
    SELECT
        seq.n AS palette_num,
        c.hex,
        row_number() OVER (
            PARTITION BY seq.n
            ORDER BY random()
        ) AS rn
    FROM seq
    CROSS JOIN colors c
)
INSERT INTO palettes (name, palette)
SELECT
    'Random_' || printf('%02d', palette_num),
    group_concat(hex, ',')
FROM ranked
WHERE rn <= 15
GROUP BY palette_num
ORDER BY palette_num;
