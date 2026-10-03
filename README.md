# Digital Library: Online Library Management System

A web application where users can browse books, read PDFs online, and prepare for exams with study materials and previous question papers. An admin panel manages all the content.

Built with **Python Flask, SQLite, HTML, CSS and JavaScript**.

## Features

**User side**
- Home page with hero search, category cards and latest books
- Search books by title, author or subject
- Filter books by category
- Book details page with an in-browser PDF reader
- Exam Preparation: study materials and previous question papers
- Search and filter study materials by exam
- Responsive design for desktop, tablet and mobile

**Admin side**
- Dashboard with statistics
- Add, edit and delete books with PDF upload
- Manage categories (a category with books can't be deleted)
- Upload and delete study materials and question papers
- Confirmation popups and success/error notifications

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, JavaScript |
| Backend | Python, Flask (Jinja2 templates) |
| Database | SQLite |
| Files | PDFs stored in a local `uploads/` folder |

## Screenshots

_Add screenshots of the Home page, Books page, PDF reader and Admin dashboard here._

## Project Structure

```
library-management/
├── app.py                 # Flask app: database, routes, upload validation
├── requirements.txt
├── database.db            # created automatically
├── uploads/               # PDF files
├── static/
│   ├── css/style.css
│   └── js/script.js
└── templates/             # HTML pages (base.html is the shared layout)
```

## Database

| Table | Main columns |
|---|---|
| categories | id, name (unique), description |
| books | id, title, author, subject, description, category_id (FK), pdf_file, created_at |
| study_materials | id, title, description, subject, exam_name, material_type, year, pdf_file, created_at |

## How to Run

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the app
python app.py
```

Open http://127.0.0.1:5000. The database, sample books and sample PDFs are created automatically on first run. The admin panel is at `/admin`.

## Security and Validation

- SQL queries use parameter placeholders (protects against SQL injection)
- Uploads are checked for a `.pdf` extension **and** the `%PDF-` file signature
- Uploaded file names are sanitized and made unique with a UUID
- Upload size limit of 50 MB
- Deletes use POST requests with a confirmation popup

## Future Improvements

- Admin login and user accounts (authentication and authorization)
- Book cover image upload
- Pagination for large libraries
- Save books to a personal "My Library"
- Deployment to a cloud host

## Author

[Chandru P] · [https://github.com/CHANDRU-P-001] · [https://www.linkedin.com/in/chandru-p-7a01a3332/]