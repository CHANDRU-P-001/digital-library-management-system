# Digital Library: Online Library Management System

## 🔗 Live Demo
**https://chandru1501.pythonanywhere.com**

Register your own free account to explore user features (browse books, wishlist, reviews, profile, dark mode).

---

A full-stack digital library platform where users can browse, search, read, review, and save books online, prepare for exams with study materials, and track their reading activity — all with a secure authentication system. An admin panel manages every aspect of the content with analytics and audit logging.

Built with **Python, Flask, SQLite, HTML, CSS and JavaScript**.

## Features

### 🔐 Authentication & Security
- Username/password login and registration (passwords hashed with Werkzeug)
- Separate Admin login with role-based access control
- "Forgot Password" recovery via a personal security question
- Login required for all main pages (login-gate)
- Password show/hide toggle on all password fields
- Change password from Settings

### 📚 Browsing & Reading
- Home page with hero search, category cards, and latest books
- Live search autocomplete (type-ahead suggestions)
- Search books by title, author or subject; filter by category
- Pagination on the Books page
- Book details page with an in-browser PDF reader
- Book cover image uploads, category images
- "Similar Books" recommendations based on category
- "Book of the Day" featured banner (admin-controlled)
- Book download tracking

### ❤️ Personalization
- Wishlist: save/remove books with a heart icon
- Book ratings and written reviews
- Continue Reading / Recently Accessed books on the Home page
- Reading streaks and achievement badges
- Instagram-style user profile with photo upload and bio
- Personal Activity Feed
- Export personal reading list and wishlist as a PDF
- Dark mode toggle

### 📝 Exam Preparation
- Dedicated section for study materials and previous question papers
- Search and filter by exam, subject, and year

### 🛠️ Admin Panel
- Dashboard with live statistics
- Full CRUD for books, categories, and study materials
- Book and category image management
- Registered Users management with full profile view
- Support Messages: users message the admin; admin can reply and resolve
- Admin Activity Log: full audit trail
- Student Activity Report with CSV export
- Analytics dashboard with interactive charts (Chart.js)
- Bulk actions: select and delete multiple books at once

### 🎨 UI/UX
- Fully responsive design (desktop, tablet, mobile)
- Dark mode with a dedicated color palette
- Breadcrumb navigation
- Skeleton loading states for charts and images
- Share book button
- Confirmation popups for destructive actions
- Toast notifications
- Custom 404 page

### ✅ Quality
- 16 automated tests using `pytest`

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, JavaScript |
| Backend | Python, Flask (Jinja2 templates) |
| Database | SQLite |
| Charts | Chart.js (CDN) |
| Testing | pytest |
| Deployment | PythonAnywhere |
| Version Control | Git & GitHub |

## Screenshots

_Add screenshots here: Home page, Books page, PDF reader, Admin Analytics dashboard, Profile page._

## Project Structure

```
library-management/
├── app.py
├── requirements.txt
├── test_app.py
├── database.db
├── uploads/
├── static/
│   ├── css/style.css
│   └── js/script.js
└── templates/
```

## Database Schema

| Table | Purpose |
|---|---|
| `users` | Accounts, roles, profile details, security question |
| `categories` | Book categories (with optional images) |
| `books` | Book metadata, PDF/cover files, featured flag, download count |
| `study_materials` | Exam prep notes and question papers |
| `wishlist` | User ↔ Book saved relationships |
| `reviews` | Ratings and comments |
| `reading_history` | Tracks last-read books per user |
| `support_messages` | User-to-admin Help Center messages |
| `activity_log` | Daily visit tracking (reading streaks) |
| `user_activity` | Personal activity feed |
| `admin_activity_log` | Admin audit trail |

## How to Run Locally

```bash
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac / Linux

pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000.

## Running Tests

```bash
pytest -v
```

## Security & Validation

- Passwords hashed with Werkzeug (never stored as plain text)
- SQL queries use parameter placeholders (protects against SQL injection)
- File uploads validated by extension **and** file signature
- Uploaded file names sanitized and made unique with a UUID
- Role-based access control enforced server-side
- Destructive actions use POST requests with confirmation popups

## Future Improvements

- CSRF token protection
- Login rate-limiting
- Migration to MySQL/PostgreSQL for multi-instance scaling

## Author

**Chandru P**
GitHub: [github.com/CHANDRU-P-001](https://github.com/CHANDRU-P-001)
LinkedIn: [linkedin.com/in/chandru-p-7a01a3332](https://www.linkedin.com/in/chandru-p-7a01a3332/)