USE campusbuzz;

-- Create tables
CREATE TABLE students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    roll_number VARCHAR(50),
    department VARCHAR(50),
    year VARCHAR(10)
);

CREATE TABLE hosts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    designation VARCHAR(100),
    department VARCHAR(100)
);

CREATE TABLE events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    venue VARCHAR(255) NOT NULL,
    host_id INT NOT NULL,
    FOREIGN KEY (host_id) REFERENCES hosts(id)
);

CREATE TABLE event_registrations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    event_id INT NOT NULL,
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (event_id) REFERENCES events(id),
    UNIQUE (student_id, event_id)
);

SELECT * FROM students;
SELECT * FROM hosts;
SELECT * FROM events;
SELECT * FROM event_registrations;
