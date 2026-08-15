-- age が実は西暦（建築年）のまま保存されていた行を修正する。
-- 建物の築年数が200年を超えることは現実的にありえないため、
-- age > 200 を「西暦が誤って入っている」行の判定に使う。

-- 修正前の件数・値の確認
SELECT id, title, age
FROM buildings
WHERE age > 200
ORDER BY age;

-- 実際の修正（現在年 - 建築年 に変換）
UPDATE buildings
SET age = EXTRACT(YEAR FROM CURRENT_DATE)::int - age
WHERE age > 200;

-- 修正後の分布確認
SELECT min(age), max(age), avg(age)::numeric(10,1)
FROM buildings
WHERE age IS NOT NULL;
