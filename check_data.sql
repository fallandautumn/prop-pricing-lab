-- 1. buildings の欠損状況
SELECT
  count(*) AS total,
  count(station_distance) AS has_station,
  count(age) AS has_age,
  count(total_floors) AS has_total_floors,
  count(building_structure) AS has_structure,
  count(building_type) AS has_building_type
FROM buildings;

-- 1b. building_type の内訳
SELECT building_type, count(*) AS n
FROM buildings
GROUP BY building_type
ORDER BY n DESC;

-- 2. rooms(price有り) の欠損状況
SELECT
  count(*) AS total,
  count(floor) AS has_floor,
  count(liv_area) AS has_liv_area,
  count(floor_plan) AS has_floor_plan
FROM rooms WHERE price IS NOT NULL;

-- 3. 建物あたりの部屋数分布
SELECT room_count, count(*) AS num_buildings
FROM (
  SELECT building_id, count(*) AS room_count
  FROM rooms
  GROUP BY building_id
) t
GROUP BY room_count
ORDER BY room_count;