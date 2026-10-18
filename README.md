# Installation:

1. Install uv
2. Install dependencies: `uv pip install -r requirements.txt`
3. Create .env file from .env.example template, fill all required env variables


# Run server: 

```cd server && uvicorn main:app --host 0.0.0.0 --port 5000 --reload```

# migration
Auto generate 
migration script according to updated models definition in code: 
`alembic revision --autogenerate -m "add raw colun to book"`

Run the migration: `alembic upgrade head`