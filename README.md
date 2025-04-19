
# deals app

this is a simple flask-based deals app where:
- admins can create/update/delete deals (with jwt auth)
- customers can view deals after signing in with google

---

## setup 

### 1. clone the repo
```bash
git clone https://github.com/itsknk/deals_webapp.git
cd deals-app
```

### 2. set up environment
```bash
chmod +x setup.sh
./setup.sh
```

this will:
- create a virtual environment
- install dependencies
- copy `.env.example` to `.env`

### 3. update `.env`
edit the `.env` file and fill in your own google oauth creds or use the provided ones if available. also, make sure to fill the db creds.
```env
MYSQL_HOST=localhost
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_password
MYSQL_DB=dealsdb
```

### 4. database setup

before running the app, create the mysql db and table using the provided `schema.sql`.

### start your mysql server, then log in:

```bash
mysql -u your_mysql_user -p
```

### run the schema:

```sql
SOURCE schema.sql;
```

---

## run the app
```bash
source venv/bin/activate
python3 app.py
```

visit:
- `http://localhost:5050/viewer` → customer Google login + user deals dashboard
- `http://localhost:5050/admin/login` → admin panel

---

## tech stack
- flask + jwt + mysql
- google goauth 2.0 for customer login
- session-based auth for viewer
