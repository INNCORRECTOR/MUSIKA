-- Add email to existing admission_applications (run once if the column is missing).
ALTER TABLE admission_applications
  ADD COLUMN email VARCHAR(254) DEFAULT NULL AFTER date_of_birth;
