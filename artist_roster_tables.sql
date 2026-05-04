CREATE TABLE artists (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    title VARCHAR(255),
    bio TEXT,
    hero_image_url TEXT,
    featured_media_type VARCHAR(16),
    featured_media_url TEXT,
    featured_media_thumbnail_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE media (
    id INT AUTO_INCREMENT PRIMARY KEY,
    artist_id INT NOT NULL,
    media_type ENUM('image', 'video') NOT NULL,
    media_url TEXT NOT NULL,
    thumbnail_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_artist
        FOREIGN KEY (artist_id)
        REFERENCES artists(id)
        ON DELETE CASCADE
);
