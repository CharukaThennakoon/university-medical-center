-- =====================================================================
--  University Medical Center Management System
--  File : database/seed_data.sql   (run AFTER schema.sql)
--
--  DEMO LOGIN PASSWORD FOR EVERY USER:  Password@123
--  (hash generated with werkzeug pbkdf2:sha256, so Flask's
--   check_password_hash() will accept it in Phase 3)
-- =====================================================================
USE university_medical_center;

-- ---------------------------------------------------------------------
-- 1. Students_Patients (12 patients)
-- ---------------------------------------------------------------------
INSERT INTO Students_Patients
    (patient_id, ar_number, nic_number, first_name, last_name, address, height, weight, special_conditions)
VALUES
 (1,  'AR1001', '200123456789', 'Kasun',   'Wijesinghe',  '45/2, Temple Road, Nugegoda',     172.50, 64.00, NULL),
 (2,  'AR1002', '200234567891', 'Nethmi',  'Perera',      '12, Lake Drive, Maharagama',      160.00, 52.50, 'Seasonal allergic rhinitis'),
 (3,  'AR1003', '200045678912', 'Dilshan', 'Fernando',    '78, Galle Road, Dehiwala',        175.00, 70.00, NULL),
 (4,  'AR1004', '200156789123', 'Ishara',  'Jayasuriya',  '5, Park Lane, Kandy',             165.00, 58.00, NULL),
 (5,  'AR1005', '200067891234', 'Tharindu','Silva',       '23, Station Road, Gampaha',       170.00, 61.00, 'Asthma'),
 (6,  'AR1006', '200278912345', 'Sachini', 'Rajapaksha',  '9, Hill Street, Kurunegala',      158.00, 49.00, NULL),
 (7,  'AR1007', '200189123456', 'Mohamed', 'Rizwan',      '31, Main Street, Colombo 10',     168.00, 66.50, NULL),
 (8,  'AR1008', '200291234567', 'Amaya',   'Gunasekara',  '14, Church Road, Moratuwa',       162.00, 55.00, 'Type 1 diabetes'),
 (9,  'AR1009', '200112345670', 'Chamod',  'Bandara',     '60, Kandy Road, Kegalle',         178.00, 72.00, NULL),
 (10, 'AR1010', '200223456781', 'Piumi',   'Weerasinghe', '2, Beach Road, Matara',           157.00, 50.00, 'Allergic to penicillin'),
 (11, 'AR1011', '982345671V',   'Hasitha', 'Dissanayake', '88, Temple Junction, Anuradhapura',174.00, 68.00, NULL),
 (12, 'AR1012', '200334567892', 'Oshadi',  'Karunaratne', '17, Fort Road, Galle',            161.00, 54.00, 'Mild lactose intolerance');

-- ---------------------------------------------------------------------
-- 3. Doctors  (Doctor 2 is OFF duty so the availability display can be tested)
-- ---------------------------------------------------------------------
INSERT INTO Doctors (doctor_id, doctor_name, specialization, is_available) VALUES
 (1, 'Dr. Nimal Perera',    'General Practitioner', TRUE),
 (2, 'Dr. Sanduni Fernando','General Practitioner', FALSE);

-- ---------------------------------------------------------------------
-- 2. Users_Roles   (all passwords = Password@123)
--    Student   -> username = AR number, ref_id = patient_id
--    Doctor    -> ref_id = doctor_id
--    Pharmacist / CounterOfficer / Admin -> ref_id NULL
-- ---------------------------------------------------------------------
INSERT INTO Users_Roles (user_id, username, password_hash, role, ref_id) VALUES
 (1,  'AR1001',     'pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'Student', 1),
 (2,  'AR1002',     'pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'Student', 2),
 (3,  'AR1003',     'pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'Student', 3),
 (4,  'AR1004',     'pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'Student', 4),
 (5,  'AR1005',     'pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'Student', 5),
 (6,  'AR1006',     'pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'Student', 6),
 (7,  'AR1007',     'pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'Student', 7),
 (8,  'AR1008',     'pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'Student', 8),
 (9,  'doctor1',    'pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'Doctor', 1),
 (10, 'doctor2',    'pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'Doctor', 2),
 (11, 'pharmacist1','pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'Pharmacist', NULL),
 (12, 'counter1',   'pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'CounterOfficer', NULL),
 (13, 'admin1',     'pbkdf2:sha256:1000000$uBAOnN8pLmteOPDk$f7e2c9f239cad5d69e641dfae89d0fc7bd083f15e5ecefb6d2f714c8f34c6730', 'Admin', NULL);

-- ---------------------------------------------------------------------
-- 5. Medicines_Inventory (20 items; IDs 4, 10, 17 are OUT OF STOCK => RED)
-- ---------------------------------------------------------------------
INSERT INTO Medicines_Inventory (medicine_id, medicine_name, category, stock_quantity, expiry_date) VALUES
 (1,  'Paracetamol 500mg',            'Analgesic',        500, '2028-03-31'),
 (2,  'Ibuprofen 400mg',              'Analgesic / NSAID',120, '2027-11-30'),
 (3,  'Amoxicillin 500mg',            'Antibiotic',        80, '2027-08-31'),
 (4,  'Azithromycin 250mg',           'Antibiotic',         0, '2027-06-30'),
 (5,  'Cetirizine 10mg',              'Antihistamine',    200, '2028-01-31'),
 (6,  'Chlorpheniramine 4mg',         'Antihistamine',    150, '2027-12-31'),
 (7,  'Salbutamol Inhaler 100mcg',    'Respiratory',       15, '2027-09-30'),
 (8,  'Omeprazole 20mg',              'Antacid / PPI',     90, '2028-02-28'),
 (9,  'ORS Sachet',                   'Rehydration',      300, '2028-05-31'),
 (10, 'Metronidazole 400mg',          'Antibiotic',         0, '2027-10-31'),
 (11, 'Loratadine 10mg',              'Antihistamine',     60, '2027-12-31'),
 (12, 'Bromhexine Cough Syrup 100ml', 'Respiratory',       40, '2027-07-31'),
 (13, 'Vitamin C 500mg',              'Supplement',       250, '2028-04-30'),
 (14, 'Domperidone 10mg',             'Antiemetic',        70, '2027-11-30'),
 (15, 'Mefenamic Acid 500mg',         'Analgesic / NSAID',  5, '2027-05-31'),
 (16, 'Povidone Iodine Solution 60ml','Antiseptic',        25, '2028-06-30'),
 (17, 'Hyoscine Butylbromide 10mg',   'Antispasmodic',      0, '2027-09-30'),
 (18, 'Diclofenac Gel 30g',           'Topical',           30, '2027-12-31'),
 (19, 'Prednisolone 5mg',             'Corticosteroid',    45, '2027-10-31'),
 (20, 'Zinc 20mg',                    'Supplement',       100, '2028-03-31');

-- ---------------------------------------------------------------------
-- 4. Daily_Tokens
--    Dates are relative to the day you import, so the data always looks
--    fresh. Note numbering restarts at 1 on every date (daily reset).
-- ---------------------------------------------------------------------
INSERT INTO Daily_Tokens (token_id, token_number, patient_id, token_date, status) VALUES
 -- Two days ago
 (1,  1, 1, DATE_SUB(CURDATE(), INTERVAL 2 DAY), 'Completed'),
 (2,  2, 2, DATE_SUB(CURDATE(), INTERVAL 2 DAY), 'Completed'),
 (3,  3, 3, DATE_SUB(CURDATE(), INTERVAL 2 DAY), 'Completed'),
 -- Yesterday
 (4,  1, 4, DATE_SUB(CURDATE(), INTERVAL 1 DAY), 'Completed'),
 (5,  2, 5, DATE_SUB(CURDATE(), INTERVAL 1 DAY), 'Completed'),
 (6,  3, 1, DATE_SUB(CURDATE(), INTERVAL 1 DAY), 'Completed'),
 (7,  4, 6, DATE_SUB(CURDATE(), INTERVAL 1 DAY), 'Completed'),
 -- Today (live queue)
 (8,  1, 7, CURDATE(), 'Completed'),        -- already seen, prescription waiting at pharmacy
 (9,  2, 8, CURDATE(), 'In-Consultation'),  -- with the doctor right now
 (10, 3, 2, CURDATE(), 'Pending'),
 (11, 4, 9, CURDATE(), 'Pending');

-- ---------------------------------------------------------------------
-- 6. Prescriptions
-- ---------------------------------------------------------------------
INSERT INTO Prescriptions (prescription_id, token_id, patient_id, doctor_id, diagnosis, prescribed_at, status) VALUES
 (1, 1, 1, 1, 'Acute viral fever',                         TIMESTAMP(DATE_SUB(CURDATE(), INTERVAL 2 DAY), '09:15:00'), 'Dispensed'),
 (2, 2, 2, 2, 'Allergic rhinitis',                         TIMESTAMP(DATE_SUB(CURDATE(), INTERVAL 2 DAY), '09:40:00'), 'Dispensed'),
 (3, 3, 3, 1, 'Acute gastritis',                           TIMESTAMP(DATE_SUB(CURDATE(), INTERVAL 2 DAY), '10:05:00'), 'Dispensed'),
 (4, 4, 4, 1, 'Upper respiratory tract infection',         TIMESTAMP(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '08:50:00'), 'Dispensed'),
 (5, 5, 5, 2, 'Mild asthma exacerbation',                  TIMESTAMP(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '09:20:00'), 'Dispensed'),
 (6, 6, 1, 1, 'Tension headache',                          TIMESTAMP(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '10:30:00'), 'Dispensed'),
 (7, 7, 6, 2, 'Acute diarrhoea with mild dehydration',     TIMESTAMP(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '11:00:00'), 'Dispensed'),
 (8, 8, 7, 1, 'Acute pharyngitis',                         TIMESTAMP(CURDATE(), '08:45:00'),                           'Pending');

-- ---------------------------------------------------------------------
-- 7. Prescription_Items
--    (Stock figures above are already net of these quantities.)
-- ---------------------------------------------------------------------
INSERT INTO Prescription_Items (prescription_id, medicine_id, dosage, quantity_given) VALUES
 (1, 1,  '1 tablet, 3 times daily for 3 days',                  9),
 (1, 13, '1 tablet daily for 5 days',                           5),
 (2, 5,  '1 tablet at night for 5 days',                        5),
 (3, 8,  '1 capsule before breakfast for 7 days',               7),
 (3, 14, '1 tablet, 3 times daily before meals for 3 days',     9),
 (4, 3,  '1 capsule, 3 times daily for 5 days',                15),
 (4, 1,  '1 tablet, 3 times daily for 2 days',                  6),
 (4, 12, '10 ml, 3 times daily for 5 days',                     1),
 (5, 7,  '2 puffs when needed',                                 1),
 (5, 19, '2 tablets daily for 3 days',                          6),
 (6, 1,  '1 tablet, 3 times daily for 2 days',                  6),
 (7, 9,  '1 sachet after each loose stool',                     6),
 (7, 20, '1 tablet daily for 10 days',                         10),
 (8, 1,  '1 tablet, 3 times daily for 2 days',                  6),
 (8, 3,  '1 capsule, 3 times daily for 5 days',                15);

-- =====================================================================
--  QUICK SANITY CHECKS (run these in the phpMyAdmin SQL tab)
-- =====================================================================
-- SELECT * FROM v_medicine_stock;                -- GREEN / RED indicator
-- SELECT * FROM v_pharmacy_queue;                -- 1 pending prescription (token #1 today)
-- SELECT token_date, token_number FROM Daily_Tokens ORDER BY token_date, token_number;
-- CALL sp_issue_token(10);                       -- should return token #5 for today
-- CALL sp_issue_token(10);                       -- should FAIL: active token already exists
