CREATE DATABASE IF NOT EXISTS dealsdb;
USE dealsdb;

CREATE TABLE IF NOT EXISTS deals (
    dealid INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    expiry_date DATE,
    promotion VARCHAR(255),
    description TEXT,
    affiliate_link VARCHAR(2083)
);

CREATE TABLE IF NOT EXISTS customers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255),
    picture VARCHAR(2083),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

