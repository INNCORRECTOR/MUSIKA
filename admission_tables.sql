CREATE TABLE IF NOT EXISTS admission_applications (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  first_name VARCHAR(120) NOT NULL,
  last_name VARCHAR(120) NOT NULL,
  gender VARCHAR(30) DEFAULT NULL,
  date_of_birth DATE DEFAULT NULL,
  email VARCHAR(254) DEFAULT NULL,
  guardian_name VARCHAR(180) DEFAULT NULL,
  guardian_relation VARCHAR(50) DEFAULT NULL,
  guardian_occupation VARCHAR(180) DEFAULT NULL,
  address_line TEXT DEFAULT NULL,
  city VARCHAR(120) DEFAULT NULL,
  state VARCHAR(120) DEFAULT NULL,
  pin_code VARCHAR(20) DEFAULT NULL,
  special_remarks TEXT DEFAULT NULL,
  discipline VARCHAR(150) DEFAULT NULL,
  grade VARCHAR(100) DEFAULT NULL,
  affiliated VARCHAR(150) DEFAULT NULL,
  preferred_teacher VARCHAR(150) DEFAULT NULL,
  passport_photo_url VARCHAR(1024) DEFAULT NULL,
  passport_photo_key VARCHAR(512) DEFAULT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'new',
  is_seen TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_admission_status_created_at (status, created_at),
  KEY ix_admission_created_at (created_at),
  KEY ix_admission_name (last_name, first_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS admission_disciplines (
  id INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(150) NOT NULL,
  is_active TINYINT NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_admission_disciplines_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS admission_grades (
  id INT NOT NULL AUTO_INCREMENT,
  discipline_id INT NOT NULL,
  name VARCHAR(100) NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  is_active TINYINT NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_admission_grades_discipline_id (discipline_id),
  CONSTRAINT fk_admission_grades_discipline
    FOREIGN KEY (discipline_id)
    REFERENCES admission_disciplines(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS admission_teachers (
  id INT NOT NULL AUTO_INCREMENT,
  discipline_id INT NOT NULL,
  name VARCHAR(150) NOT NULL,
  is_active TINYINT NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_admission_teachers_discipline_id (discipline_id),
  CONSTRAINT fk_admission_teachers_discipline
    FOREIGN KEY (discipline_id)
    REFERENCES admission_disciplines(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS admission_contacts (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  admission_id BIGINT UNSIGNED NOT NULL,
  contact_value VARCHAR(40) NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  KEY ix_admission_contacts_admission_id (admission_id),
  CONSTRAINT fk_admission_contacts_application
    FOREIGN KEY (admission_id)
    REFERENCES admission_applications(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS admission_admin_reviews (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  admission_id BIGINT UNSIGNED NOT NULL,
  reviewed_by_user_id INT DEFAULT NULL,
  accepted TINYINT(1) DEFAULT NULL,
  fees_amount_inr DECIMAL(10,2) DEFAULT NULL,
  invoice_no VARCHAR(100) DEFAULT NULL,
  invoice_dated DATE DEFAULT NULL,
  payment_method VARCHAR(30) DEFAULT NULL,
  course_start_date DATE DEFAULT NULL,
  course_duration VARCHAR(120) DEFAULT NULL,
  class_type VARCHAR(30) DEFAULT NULL,
  remarks TEXT DEFAULT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_admission_admin_reviews_admission_id (admission_id),
  KEY ix_admission_admin_reviews_user_id (reviewed_by_user_id),
  CONSTRAINT fk_admission_reviews_application
    FOREIGN KEY (admission_id)
    REFERENCES admission_applications(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_admission_reviews_user
    FOREIGN KEY (reviewed_by_user_id)
    REFERENCES users(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Singleton row (id=1): bank / UPI / QR for fee instructions (admin, PDF, email, WhatsApp).
CREATE TABLE IF NOT EXISTS admission_payment_settings (
  id INT NOT NULL,
  account_holder_name VARCHAR(180) DEFAULT NULL,
  bank_account_number VARCHAR(40) DEFAULT NULL,
  bank_ifsc VARCHAR(20) DEFAULT NULL,
  upi_id VARCHAR(100) DEFAULT NULL,
  scanner_image_url VARCHAR(1024) DEFAULT NULL,
  scanner_image_key VARCHAR(512) DEFAULT NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO admission_payment_settings (id) VALUES (1);
