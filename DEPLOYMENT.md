# Pool Cue Deployment Options

## Option 1: Railway (Recommended for starting out)

### Setup:
1. Create account at https://railway.app
2. Connect GitHub repo
3. Railway auto-detects Flask

### Required files (already created):
- requirements.txt
- Procfile (create below)

### Environment Variables to set in Railway:
- SECRET_KEY
- FLASK_ENV=production
- DATABASE_URL (Railway provides PostgreSQL)

---

## Option 2: Render

### Setup:
1. Create account at https://render.com
2. Create new "Web Service"
3. Connect GitHub repo
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `gunicorn run:app`

---

## Option 3: Heroku

### Setup:
```bash
# Install Heroku CLI
brew tap heroku/brew && brew install heroku

# Login
heroku login

# Create app
heroku create poolcue-app

# Add PostgreSQL
heroku addons:create heroku-postgresql:mini

# Set environment variables
heroku config:set FLASK_ENV=production
heroku config:set SECRET_KEY=your-secret-key

# Deploy
git push heroku main
```

---

## Production Requirements

### requirements.txt additions for production:
```
gunicorn==21.2.0
psycopg2-binary==2.9.9
```

### Procfile (create in project root):
```
web: gunicorn run:app --bind 0.0.0.0:$PORT
```
