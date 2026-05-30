-- 데이터베이스 스키마 및 초기 데이터
-- 이 폴더(data)는 .gitignore 에 의해 업로드되지 않습니다.
-- app.py 최초 실행 시 이 스키마로 data/board.db 가 생성됩니다.

-- 사용자: 최소한의 정보만 (이메일 / 별명 / 비밀번호)
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    nickname      TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 게시글: 제목 없이 본문만, 카테고리 보유
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    category   TEXT NOT NULL DEFAULT '자유',
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 댓글
CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 좋아요: (게시글, 사용자) 조합당 1개
CREATE TABLE IF NOT EXISTS likes (
    post_id    INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (post_id, user_id),
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_posts_created   ON posts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_category  ON posts (category);
CREATE INDEX IF NOT EXISTS idx_comments_post   ON comments (post_id);
CREATE INDEX IF NOT EXISTS idx_likes_post      ON likes (post_id);
