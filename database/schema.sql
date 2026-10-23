-- =====================================================================
--  University Medical Center Management System
--  USJ IDBMS Coursework - Activity 04
--  File    : database/schema.sql
--  Target  : XAMPP (MariaDB 10.4+ / MySQL 5.7+ / 8.x), InnoDB, utf8mb4
-- =====================================================================

DROP DATABASE IF EXISTS university_medical_center;
CREATE DATABASE university_medical_center
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
USE university_medical_center;

-- ---------------------------------------------------------------------
-- 1. Students_Patients
-- ---------------------------------------------------------------------
CREATE TABLE Students_Patients (
    patient_id         INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    ar_number          VARCHAR(20)   NOT NULL,
    nic_number         VARCHAR(15)   NOT NULL,
    first_name         VARCHAR(50)   NOT NULL,
    last_name          VARCHAR(50)   NOT NULL,
    address            VARCHAR(255)  NOT NULL,
    height             DECIMAL(5,2)  NULL COMMENT 'Height in cm',
    weight             DECIMAL(5,2)  NULL COMMENT 'Weight in kg',
    special_conditions TEXT          NULL COMMENT 'Allergies, asthma, diabetes, etc.',
    created_at         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (patient_id),
    UNIQUE KEY uq_patient_ar  (ar_number),
    UNIQUE KEY uq_patient_nic (nic_number),
    KEY idx_patient_name (last_name, first_name),
    CONSTRAINT chk_height CHECK (height IS NULL OR height > 0),
    CONSTRAINT chk_weight CHECK (weight IS NULL OR weight > 0)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 2. Users_Roles
--    ref_id is POLYMORPHIC (Student -> patient_id, Doctor -> doctor_id,
--    Pharmacist / CounterOfficer / Admin -> NULL), so it cannot carry a real
--    foreign key. Integrity is enforced in the Flask application layer.
-- ---------------------------------------------------------------------
CREATE TABLE Users_Roles (
    user_id       INT UNSIGNED NOT NULL AUTO_INCREMENT,
    username      VARCHAR(50)  NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('Student','Doctor','Pharmacist','CounterOfficer','Admin') NOT NULL,
    ref_id        INT UNSIGNED NULL COMMENT 'patient_id or doctor_id depending on role',
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE COMMENT 'FALSE = account disabled by an Admin',
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_username (username),
    KEY idx_role_ref (role, ref_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 3. Doctors
-- ---------------------------------------------------------------------
CREATE TABLE Doctors (
    doctor_id      INT UNSIGNED NOT NULL AUTO_INCREMENT,
    doctor_name    VARCHAR(100) NOT NULL,
    specialization VARCHAR(100) NOT NULL DEFAULT 'General Practitioner',
    is_available   BOOLEAN      NOT NULL DEFAULT TRUE,
    PRIMARY KEY (doctor_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 4. Daily_Tokens
--    DAILY RESET LOGIC:
--    token_number is unique only WITHIN a date (uq_token_per_day), so
--    every new calendar day naturally starts again from 1. The next
--    number is always MAX(token_number)+1 for that token_date, issued
--    through sp_issue_token (below) which serialises concurrent calls.
-- ---------------------------------------------------------------------
CREATE TABLE Daily_Tokens (
    token_id     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    token_number INT UNSIGNED NOT NULL,
    patient_id   INT UNSIGNED NOT NULL,
    token_date   DATE         NOT NULL,
    status       ENUM('Pending','In-Consultation','Completed') NOT NULL DEFAULT 'Pending',
    issued_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (token_id),
    UNIQUE KEY uq_token_per_day (token_date, token_number),
    KEY idx_token_patient (patient_id, token_date),
    KEY idx_token_queue (token_date, status),
    CONSTRAINT fk_token_patient FOREIGN KEY (patient_id)
        REFERENCES Students_Patients (patient_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_token_positive CHECK (token_number >= 1)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 5. Medicines_Inventory
-- ---------------------------------------------------------------------
CREATE TABLE Medicines_Inventory (
    medicine_id    INT UNSIGNED NOT NULL AUTO_INCREMENT,
    medicine_name  VARCHAR(100) NOT NULL,
    category       VARCHAR(60)  NOT NULL,
    stock_quantity INT UNSIGNED NOT NULL DEFAULT 0,
    expiry_date    DATE         NULL,
    PRIMARY KEY (medicine_id),
    UNIQUE KEY uq_medicine_name (medicine_name),
    KEY idx_medicine_category (category)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 6. Prescriptions
-- ---------------------------------------------------------------------
CREATE TABLE Prescriptions (
    prescription_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    token_id        INT UNSIGNED NOT NULL,
    patient_id      INT UNSIGNED NOT NULL,
    doctor_id       INT UNSIGNED NOT NULL,
    diagnosis       TEXT         NOT NULL,
    prescribed_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status          ENUM('Pending','Dispensed') NOT NULL DEFAULT 'Pending',
    PRIMARY KEY (prescription_id),
    UNIQUE KEY uq_prescription_token (token_id),
    KEY idx_rx_patient (patient_id, prescribed_at),
    KEY idx_rx_status (status),
    CONSTRAINT fk_rx_token   FOREIGN KEY (token_id)   REFERENCES Daily_Tokens (token_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_rx_patient FOREIGN KEY (patient_id) REFERENCES Students_Patients (patient_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_rx_doctor  FOREIGN KEY (doctor_id)  REFERENCES Doctors (doctor_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 7. Prescription_Items
-- ---------------------------------------------------------------------
CREATE TABLE Prescription_Items (
    item_id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    prescription_id INT UNSIGNED NOT NULL,
    medicine_id     INT UNSIGNED NOT NULL,
    dosage          VARCHAR(100) NOT NULL COMMENT 'e.g. 1 tablet, 3 times daily, 5 days',
    quantity_given  INT UNSIGNED NOT NULL,
    PRIMARY KEY (item_id),
    UNIQUE KEY uq_rx_medicine (prescription_id, medicine_id),
    KEY idx_item_medicine (medicine_id),
    CONSTRAINT fk_item_rx  FOREIGN KEY (prescription_id) REFERENCES Prescriptions (prescription_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_item_med FOREIGN KEY (medicine_id) REFERENCES Medicines_Inventory (medicine_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_qty_positive CHECK (quantity_given >= 1)
) ENGINE=InnoDB;


-- ---------------------------------------------------------------------
-- 8. Audit_Log  (what each Admin changed; username is copied so the
--    history stays readable even if an account is removed later)
-- ---------------------------------------------------------------------
CREATE TABLE Audit_Log (
    log_id     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id    INT UNSIGNED NULL,
    username   VARCHAR(50)  NOT NULL,
    action     VARCHAR(60)  NOT NULL,
    detail     VARCHAR(500) NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (log_id),
    KEY idx_audit_time (created_at)
) ENGINE=InnoDB;

-- =====================================================================
--  DAILY TOKEN ISSUING PROCEDURE
--  Used by both the Student (self-issue) and Counter Officer (manual).
--  Returns one row: token_id, token_number, token_date.
--
--  Rules:
--   * Numbering restarts at 1 each calendar day.
--   * A patient may not hold two open tokens (Pending / In-Consultation)
--     on the same day.
--   * GET_LOCK serialises concurrent requests so two students pressing
--     the button at the same moment never receive the same number.
--
--  NOTE: This file contains DELIMITER statements. Import it with the
--  phpMyAdmin "Import" tab (not by pasting into the SQL tab).
-- =====================================================================
DELIMITER $$

CREATE PROCEDURE sp_issue_token (IN p_patient_id INT UNSIGNED)
BEGIN
    DECLARE v_next   INT UNSIGNED;
    DECLARE v_id     INT UNSIGNED;
    DECLARE v_got    INT DEFAULT 0;
    DECLARE v_open   INT DEFAULT 0;

    -- Always release the lock and roll back if anything fails
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        DO RELEASE_LOCK('token_issue_lock');
        RESIGNAL;
    END;

    IF NOT EXISTS (SELECT 1 FROM Students_Patients WHERE patient_id = p_patient_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Patient not found.';
    END IF;

    SELECT GET_LOCK('token_issue_lock', 5) INTO v_got;
    IF v_got <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Server busy issuing tokens. Please try again.';
    END IF;

    START TRANSACTION;

    SELECT COUNT(*) INTO v_open
      FROM Daily_Tokens
     WHERE patient_id = p_patient_id
       AND token_date = CURRENT_DATE
       AND status IN ('Pending', 'In-Consultation');

    IF v_open > 0 THEN
        ROLLBACK;
        DO RELEASE_LOCK('token_issue_lock');
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Patient already has an active token today.';
    END IF;

    SELECT COALESCE(MAX(token_number), 0) + 1 INTO v_next
      FROM Daily_Tokens
     WHERE token_date = CURRENT_DATE;

    INSERT INTO Daily_Tokens (token_number, patient_id, token_date, status)
    VALUES (v_next, p_patient_id, CURRENT_DATE, 'Pending');

    SET v_id = LAST_INSERT_ID();
    COMMIT;
    DO RELEASE_LOCK('token_issue_lock');

    SELECT v_id AS token_id, v_next AS token_number, CURRENT_DATE AS token_date;
END$$

DELIMITER ;

-- =====================================================================
--  HELPER VIEWS
-- =====================================================================

-- Doctor screen: green / red stock indicator (stock > 0 => GREEN, 0 => RED)
CREATE VIEW v_medicine_stock AS
SELECT medicine_id,
       medicine_name,
       category,
       stock_quantity,
       expiry_date,
       CASE WHEN stock_quantity > 0 THEN 'GREEN' ELSE 'RED' END AS stock_indicator
  FROM Medicines_Inventory;

-- Pharmacist screen: today's pending prescriptions by token number
CREATE VIEW v_pharmacy_queue AS
SELECT rx.prescription_id,
       t.token_number,
       t.token_date,
       CONCAT(p.first_name, ' ', p.last_name) AS patient_name,
       p.ar_number,
       d.doctor_name,
       rx.diagnosis,
       rx.prescribed_at,
       rx.status
  FROM Prescriptions rx
  JOIN Daily_Tokens      t ON t.token_id   = rx.token_id
  JOIN Students_Patients p ON p.patient_id = rx.patient_id
  JOIN Doctors           d ON d.doctor_id  = rx.doctor_id
 WHERE rx.status = 'Pending';
