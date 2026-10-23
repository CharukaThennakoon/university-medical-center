-- =====================================================================
--  MIGRATION: adds the Admin role to an EXISTING database (keeps all data)
--  Run this ONCE in phpMyAdmin (Import tab). Do NOT re-import schema.sql,
--  because schema.sql starts with DROP DATABASE and wipes everything.
--  After this, create your first admin with:  python create_admin.py
-- =====================================================================
USE university_medical_center;

ALTER TABLE Users_Roles
    MODIFY role ENUM('Student','Doctor','Pharmacist','CounterOfficer','Admin') NOT NULL,
    ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE AFTER ref_id;

CREATE TABLE IF NOT EXISTS Audit_Log (
    log_id     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id    INT UNSIGNED NULL,
    username   VARCHAR(50)  NOT NULL,
    action     VARCHAR(60)  NOT NULL,
    detail     VARCHAR(500) NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (log_id),
    KEY idx_audit_time (created_at)
) ENGINE=InnoDB;
