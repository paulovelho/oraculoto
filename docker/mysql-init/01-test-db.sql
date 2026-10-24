-- The test suite uses its own database, wiped and migrated on every run.
CREATE DATABASE IF NOT EXISTS oraculoto_test CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
GRANT ALL PRIVILEGES ON oraculoto_test.* TO 'oraculoto'@'%';
