-- create database
CREATE DATABASE IF NOT EXISTS dealsdb;
USE dealsdb;

-- deals table
CREATE TABLE IF NOT EXISTS deals (
    dealid INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    expiry_date DATE,
    promotion VARCHAR(255),
    description TEXT,
    affiliate_link VARCHAR(2083),
    category VARCHAR(100)
);

-- customers table
CREATE TABLE IF NOT EXISTS customers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    picture VARCHAR(2083)
);

-- saved deals table
CREATE TABLE IF NOT EXISTS saved_deals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    deal_id INT NOT NULL,
    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_save (customer_id, deal_id),
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (deal_id) REFERENCES deals(dealid) ON DELETE CASCADE
);
