
-- File: add_views_triggers_clean.sql
-- Contains only necessary VIEWS and TRIGGERS for your Flask hospital management project.
-- No index creation (safe for learning/demo DBMS project).

SET @OLD_SQL_NOTES=@@SQL_NOTES; SET SQL_NOTES=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS; SET FOREIGN_KEY_CHECKS=1;

-- ========================= VIEWS =========================

DROP VIEW IF EXISTS v_doctor_schedule;
CREATE VIEW v_doctor_schedule AS
SELECT
  a.appointment_id,
  a.doctor_id,
  CONCAT(d.first_name, ' ', d.last_name) AS doctor_name,
  a.patient_id,
  CONCAT(p.first_name, ' ', p.last_name) AS patient_name,
  a.appointment_date,
  a.appointment_time,
  a.reason_for_visit,
  a.status
FROM Appointments a
LEFT JOIN Doctors d ON d.doctor_id = a.doctor_id
LEFT JOIN Patients p ON p.patient_id = a.patient_id
WHERE a.status IN ('Scheduled','Ongoing')
  AND a.appointment_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 90 DAY);

DROP VIEW IF EXISTS v_patient_summary;
CREATE VIEW v_patient_summary AS
SELECT
  p.patient_id,
  CONCAT(p.first_name,' ',p.last_name) AS patient_name,
  MAX(CASE WHEN a.status IN ('Completed') THEN a.appointment_date END) AS last_visit,
  COUNT(DISTINCT a.appointment_id) AS total_appointments,
  COALESCE(SUM(CASE WHEN b.payment_status IN ('Pending','Unpaid') THEN IFNULL(b.amount,0) ELSE 0 END),0) AS total_due
FROM Patients p
LEFT JOIN Appointments a ON a.patient_id = p.patient_id
LEFT JOIN Billing b ON b.patient_id = p.patient_id
GROUP BY p.patient_id, patient_name;

DROP VIEW IF EXISTS v_billing_detail;
CREATE VIEW v_billing_detail AS
SELECT
  b.bill_id,
  b.treatment_id,
  b.patient_id,
  CONCAT(p.first_name,' ',p.last_name) AS patient_name,
  t.appointment_id,
  a.doctor_id,
  CONCAT(d.first_name,' ',d.last_name) AS doctor_name,
  b.bill_date,
  b.amount,
  b.payment_method,
  b.payment_status
FROM Billing b
LEFT JOIN Treatments t ON t.treatment_id = b.treatment_id
LEFT JOIN Appointments a ON a.appointment_id = t.appointment_id
LEFT JOIN Doctors d ON d.doctor_id = a.doctor_id
LEFT JOIN Patients p ON p.patient_id = b.patient_id;

DROP VIEW IF EXISTS v_patient_treatments;
CREATE VIEW v_patient_treatments AS
SELECT
  t.treatment_id,
  t.treatment_type,
  t.description,
  t.cost,
  t.treatment_date,
  t.appointment_id,
  a.patient_id,
  a.reason_for_visit
FROM Treatments t
LEFT JOIN Appointments a ON a.appointment_id = t.appointment_id;

-- ========================= TRIGGERS =========================

DROP TRIGGER IF EXISTS trg_patients_email_lower_bi;
DELIMITER $$
CREATE TRIGGER trg_patients_email_lower_bi
BEFORE INSERT ON Patients
FOR EACH ROW
BEGIN
  IF NEW.email IS NOT NULL THEN
    SET NEW.email = LOWER(NEW.email);
  END IF;
END$$
DELIMITER ;

DROP TRIGGER IF EXISTS trg_patients_email_lower_bu;
DELIMITER $$
CREATE TRIGGER trg_patients_email_lower_bu
BEFORE UPDATE ON Patients
FOR EACH ROW
BEGIN
  IF NEW.email IS NOT NULL THEN
    SET NEW.email = LOWER(NEW.email);
  END IF;
END$$
DELIMITER ;

DROP TRIGGER IF EXISTS trg_appointments_no_conflict_bi;
DELIMITER $$
CREATE TRIGGER trg_appointments_no_conflict_bi
BEFORE INSERT ON Appointments
FOR EACH ROW
BEGIN
  DECLARE clash_count INT DEFAULT 0;
  SELECT COUNT(*) INTO clash_count
  FROM Appointments a
  WHERE a.doctor_id = NEW.doctor_id
    AND a.appointment_date = NEW.appointment_date
    AND a.appointment_time = NEW.appointment_time
    AND a.status IN ('Scheduled','Ongoing');
  IF clash_count > 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Doctor already has an appointment at that time.';
  END IF;
END$$
DELIMITER ;


DROP TRIGGER IF EXISTS trg_billing_fill_patient_ai;
DELIMITER $$
CREATE TRIGGER trg_billing_fill_patient_ai
AFTER INSERT ON Billing
FOR EACH ROW
BEGIN
  IF NEW.patient_id IS NULL AND NEW.treatment_id IS NOT NULL THEN
    UPDATE Billing b
    JOIN Treatments t ON t.treatment_id = NEW.treatment_id
    JOIN Appointments a ON a.appointment_id = t.appointment_id
    SET b.patient_id = a.patient_id
    WHERE b.bill_id = NEW.bill_id;
  END IF;
END$$
DELIMITER ;

SET SQL_NOTES=@OLD_SQL_NOTES;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
